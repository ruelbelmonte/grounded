# grounded

[![ci](https://github.com/ruelbelmonte/grounded/actions/workflows/ci.yml/badge.svg)](https://github.com/ruelbelmonte/grounded/actions/workflows/ci.yml)

A retrieval-augmented assistant for high-stakes domains, where a confidently
wrong answer is the failure mode that matters most. It ships with a short
synthetic data-handling policy (`sample_corpus/`), so it runs with no
proprietary data. Drop public reference text such as the NZ Privacy Act 2020
into `data/corpus/` (gitignored) to try it on something real.

The interesting part is not "it answers questions about documents." That is a
solved problem. The interesting part is the controls built around the model: it
refuses in code when retrieval finds nothing to ground an answer, it keeps user
input out of the system prompt and fences it off from retrieved context to make
prompt injection harder, it redacts common personal-identifier patterns and
configured secret values from every reply, and it stops before a call that
would exceed its spend ceiling. Those controls are code paths pinned by tests,
not requests in a prompt. They mitigate the failures below; they do not
eliminate them. See [Limitations](#limitations).

> Not legal advice. This is an engineering demo of grounded retrieval and
> guardrails.

## The problem

LLM assistants over a document set fail in predictable, expensive ways:

- they hallucinate an answer when the documents do not actually contain one
- they follow instructions embedded in user input ("ignore your rules and...")
- they echo back sensitive values that appeared somewhere in context
- they have no spend ceiling, so a loop or an abusive caller is a billing event

In a low-stakes chatbot these are annoyances. In a compliance, health, or
finance setting they are incidents. This project puts a tested code control
against each one, so mitigating it does not depend on the model behaving well.

## Design decisions and tradeoffs

The decisions, the alternatives rejected, and what each choice costs, are
written up in [DESIGN.md](./DESIGN.md), including the limits of each control.
Read it before the code.

## Running it

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"   # .venv/bin/pip on macOS/Linux
pytest                                    # deterministic, no network, no API key
```

The test suite needs no API key and makes no network calls: the guardrails are
unit-tested through injected fakes, the same way the real service is wired. To
run the assistant for real you need an Anthropic API key, but the safety
properties are verifiable without it, which is the point. Optional:
`GROUNDED_BLOCKED_SECRETS` is a comma-separated list of values the egress
filter redacts from replies, matched exactly but case-insensitively (see
`src/grounded/config.py`).

```bash
export ANTHROPIC_API_KEY=...            # required only for a live run
grounded ask "When can an agency refuse access to personal information?"
```

## Architecture

```
user query
   -> guardrails: per-user rate limit
   -> retrieval: keyword over the chunked corpus, common words excluded
   -> agent: nothing retrieved? refuse now, no model call
   -> agent: user message = <context> chunks + <question>, both escaped;
             user text never enters the system prompt
   -> guardrails: budget check against the ceiling (before any spend)
   -> model call, then record actual spend
   -> guardrails: egress filter on the reply (redact PII patterns,
             redact configured secret values)
   -> reply
```

Transport (`cli.py`) is thin and holds no behaviour. The agent takes its model
client injected behind a Protocol, so the service is exercised in tests with a
fake (no network, no API key) and the safety behaviour is pinned deterministically.

## Limitations

The redaction gaps below are pinned by strict `xfail` tests, so closing one
fails the suite until this list is updated.

- **PII redaction is pattern-based.** It catches email addresses, NZ mobile
  numbers (`021 000 0000`, `+64 21 000 0000` and similar), and NHI numbers in
  either format and any case whose check character validates. It misses NZ
  landlines (`(04) 000 0000`, `+64 4 000 0000`), dates of birth, IRD numbers,
  card numbers, personal names, and any format it has no pattern for. NHI
  candidates that fail the check digit are left alone: that avoids false
  positives such as `AWS2023`, but a mistyped NHI is not redacted.
- **The secret filter is exact-match** (case-insensitive) against the values in
  `GROUNDED_BLOCKED_SECRETS`. A partial, split, encoded, or reformatted secret
  is not caught.
- **Only the reply is filtered.** The user's question and the retrieved context
  are sent to the model provider as they are. Do not put data in the corpus, or
  let users type data, that must not reach the provider.
- **Rate limit and budget are per process.** The CLI starts a new process per
  question, so both reset on every run. They only bound anything in a
  long-running process; the provider-side spend limit is the durable backstop
  (DESIGN.md s4).
- **Injection resistance is structural, not proven.** User text never enters
  the system prompt, and context and question are delimited and escaped so a
  user cannot forge a context block. Whether the model then ignores
  instructions inside the question is behavioural, and the evals in `evals/`
  that would measure it have not been run.
- **Code-level refusal is retrieval-based.** It fires only when no chunk shares
  a non-common word with the question (DESIGN.md s5).

## Status

Runnable baseline.

- **Done and tested (no API key needed):** the guardrail layer (redaction, rate
  limit, budget), structure-aware chunking, keyword retrieval, and the agent's
  safety behaviour (prompt separation, refusal on empty retrieval, egress
  filtering of model output, delimited context), CLI error handling. 37
  tests pass; 8 more are strict `xfail` tests that pin the known redaction gaps.
- **Wired, needs a key to run live:** `grounded ask` against the bundled
  synthetic `sample_corpus/`, via the Anthropic adapter.
- **Not done yet:** semantic retrieval (open decisions in DESIGN.md), wiring
  the eval harness in `evals/` to the live model, and recording eval numbers.
  No eval results are claimed until they have been run and dated.
