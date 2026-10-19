# grounded

A retrieval-augmented assistant for high-stakes domains, where a confidently
wrong answer is the failure mode that matters most. It ships with a short
synthetic data-handling policy (`sample_corpus/`), so it runs with no
proprietary data. Drop public reference text such as the NZ Privacy Act 2020
into `data/corpus/` (gitignored) to try it on something real.

The interesting part is not "it answers questions about documents." That is a
solved problem. The interesting part is everything built around the model so it
stays safe and honest under load: it refuses when the documents do not support
an answer, it cannot be talked out of its instructions by user input, it never
leaks a secret or a personal identifier in a reply, and it stops itself before
it runs up a bill. Those properties are enforced in code and pinned by tests,
not requested politely in a prompt.

> Not legal advice. This is an engineering demo of grounded retrieval and
> guardrails.

## The problem

LLM assistants over a document set fail in predictable, expensive ways:

- they hallucinate an answer when the documents do not actually contain one
- they follow instructions embedded in user input ("ignore your rules and...")
- they echo back sensitive values that appeared somewhere in context
- they have no spend ceiling, so a loop or an abusive caller is a billing event

In a low-stakes chatbot these are annoyances. In a compliance, health, or
finance setting they are incidents. This project treats each one as a property
the system must guarantee, not a behaviour it should aspire to.

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
filter must never let out (see `src/grounded/config.py`).

```bash
export ANTHROPIC_API_KEY=...            # required only for a live run
grounded ask "When can an agency refuse access to personal information?"
```

## Architecture

```
user query
   -> guardrails: rate limit, prompt separation (user text never enters system)
   -> retrieval: keyword over the chunked corpus, common words excluded
   -> agent: retrieve, then answer from context or refuse if ungrounded
   -> guardrails: egress filter (redact PII, block secret shapes), budget check
   -> reply
```

Transport (`cli.py`) is thin and holds no behaviour. The agent takes its model
client injected behind a Protocol, so the service is exercised in tests with a
fake (no network, no API key) and the safety behaviour is pinned deterministically.

## Status

Runnable baseline.

- **Done and tested (no API key needed):** the guardrail layer (redaction, rate
  limit, budget), structure-aware chunking, keyword retrieval, and the agent's
  safety behaviour (prompt separation, refusal on empty retrieval, egress
  filtering of model output). 18 tests, green.
- **Wired, needs a key to run live:** `grounded ask` against the bundled
  synthetic `sample_corpus/`, via the Anthropic adapter.
- **Not done yet:** semantic retrieval (open decisions in DESIGN.md), wiring
  the eval harness in `evals/` to the live model, and recording eval numbers.
  No eval results are claimed until they have been run and dated.
