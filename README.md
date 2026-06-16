# grounded

A retrieval-augmented assistant for high-stakes domains, where a confidently
wrong answer is the failure mode that matters most. The reference corpus is
public compliance text (the NZ Privacy Act 2020 and the OWASP Top 10), so the
whole thing is reproducible with no proprietary data.

The interesting part is not "it answers questions about documents." That is a
solved problem. The interesting part is everything built around the model so it
stays safe and honest under load: it refuses when the documents do not support
an answer, it cannot be talked out of its instructions by user input, it never
leaks a secret or a personal identifier in a reply, and it stops itself before
it runs up a bill. Those properties are enforced in code and pinned by tests,
not requested politely in a prompt.

> Not legal advice. This is an engineering demo of grounded retrieval and
> guardrails. The corpus is public reference text used purely to exercise the
> system.

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
written up in [DESIGN.md](./DESIGN.md). That document is the point of this repo;
read it before the code. A few decisions are deliberately left open and marked
`DECIDE:` because they depend on tradeoffs the author should make and defend
rather than inherit.

## Running it

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"   # .venv/bin/pip on macOS/Linux
pytest                                    # deterministic, no network, no API key
```

The test suite needs no API key and makes no network calls: the guardrails are
unit-tested through injected fakes, the same way the real service is wired. To
run the assistant for real you need an Anthropic API key (see
[DESIGN.md](./DESIGN.md) for configuration), but the safety properties are
verifiable without it, which is the point.

```bash
export ANTHROPIC_API_KEY=...            # required only for a live run
grounded ask "When can an agency refuse access to personal information?"
```

## Architecture

```
user query
   -> guardrails: rate limit, prompt separation (user text never enters system)
   -> retrieval: keyword over the chunked corpus (semantic layer is next, DESIGN.md)
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
  filtering of model output). 13 tests, green.
- **Wired, needs a key to run live:** `grounded ask` against the bundled
  synthetic `sample_corpus/`, via the Anthropic adapter.
- **Author's remaining work (the parts that make it credible):** the four
  `DECIDE:` calls in DESIGN.md (semantic retrieval: embedding model, vector
  store, chunking, hybrid merge), wiring the eval harness in `evals/`, and
  recording real eval numbers. These are deliberately left to be made and
  defended by hand, not generated.
