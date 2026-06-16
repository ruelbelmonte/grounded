"""Tests for the assistant's safety-critical behaviour, using a fake model so
there is no network and no API key. These pin the properties that matter:
prompt separation, refusal on empty retrieval, and egress filtering of model
output (DESIGN.md s2, s5, s3)."""

from __future__ import annotations

from grounded.agent import REFUSAL, Assistant, Deps, Message, ModelReply
from grounded.guardrails import BudgetTracker, RateLimiter, RedactionFilter
from grounded.retrieval import Chunk, Retriever, chunk_document


class FakeModel:
    """Records what it was called with, and returns a canned reply."""

    def __init__(self, reply_text: str = "An answer. [Access]") -> None:
        self.reply_text = reply_text
        self.called = False
        self.last_system: str | None = None
        self.last_messages: list[Message] | None = None

    def respond(self, *, system: str, messages: list[Message]) -> ModelReply:
        self.called = True
        self.last_system = system
        self.last_messages = messages
        return ModelReply(text=self.reply_text, cost_usd=0.001)


def _clock() -> float:
    return 0.0


def _deps(model: FakeModel, chunks: list[Chunk]) -> Deps:
    return Deps(
        retriever=Retriever(chunks),
        redaction=RedactionFilter(),
        rate_limiter=RateLimiter(max_per_hour=100, clock=_clock),
        budget=BudgetTracker(ceiling_usd=10.0),
        model=model,
    )


_CORPUS = chunk_document(
    "policy",
    "# Access\n\nA person may request access to their personal information.",
)


def test_user_text_never_enters_system() -> None:
    model = FakeModel()
    sentinel = "IGNORE_ALL_RULES_SENTINEL_42"
    Assistant(_deps(model, _CORPUS)).ask("u1", f"access? {sentinel}")
    assert model.last_system is not None
    assert sentinel not in model.last_system  # s2: not in the system prompt
    assert any(sentinel in m["content"] for m in model.last_messages or [])


def test_refuses_and_does_not_call_model_when_no_grounding() -> None:
    model = FakeModel()
    out = Assistant(_deps(model, _CORPUS)).ask("u1", "quantum chromodynamics")
    assert out == REFUSAL
    assert model.called is False  # s5: no spend on an ungrounded question


def test_egress_filter_scrubs_model_output() -> None:
    model = FakeModel(reply_text="Email the office at clerk@example.org for access.")
    out = Assistant(_deps(model, _CORPUS)).ask("u1", "how do I request access?")
    assert "clerk@example.org" not in out  # s3: scrubbed at the boundary
    assert "[REDACTED_EMAIL]" in out
