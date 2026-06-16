"""The assistant pipeline (DESIGN.md sections 2, 3, 5, 6).

Baseline implemented: retrieve once, then answer or refuse. The model client is
injected behind a Protocol, so the safety-critical behaviour (prompt separation,
refusal on empty retrieval, egress filtering of the model's output, budget
enforcement) is unit-tested with a fake and no API key. The bounded multi-step
tool loop from DESIGN.md s6 is the next iteration on top of this shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .guardrails import BudgetTracker, RateLimiter, RedactionFilter
from .retrieval import Retriever

SYSTEM_PROMPT = (
    "You answer only from the provided context. If the context does not contain "
    "the answer, say you do not have it. Cite the section of each fact you use. "
    "You do not give legal advice; you report what the documents say."
)

REFUSAL = "I don't have anything in the source documents that answers that."
RATE_LIMITED = "Rate limit reached. Please try again later."

Message = dict[str, str]


@dataclass(frozen=True)
class ModelReply:
    text: str
    cost_usd: float


class ModelClient(Protocol):
    """The only thing the agent needs from a model. Implemented for real by the
    Anthropic adapter and by a fake in tests."""

    def respond(self, *, system: str, messages: list[Message]) -> ModelReply: ...


@dataclass
class Deps:
    retriever: Retriever
    redaction: RedactionFilter
    rate_limiter: RateLimiter
    budget: BudgetTracker
    model: ModelClient
    max_context_chunks: int = 5
    projected_call_usd: float = 0.02  # conservative pre-check before each call


class Assistant:
    def __init__(self, deps: Deps) -> None:
        self._d = deps

    def ask(self, user_id: str, question: str) -> str:
        if not self._d.rate_limiter.allow(user_id):
            return RATE_LIMITED

        hits = self._d.retriever.search(question, k=self._d.max_context_chunks)
        if not hits:
            return REFUSAL  # s5: refuse rather than answer ungrounded; no spend

        context = "\n\n".join(f"[{h.chunk.section}]\n{h.chunk.text}" for h in hits)

        # s2: the user's question is only ever a user message. It is never spliced
        # into SYSTEM_PROMPT. test_user_text_never_enters_system pins this.
        messages: list[Message] = [
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}
        ]

        self._d.budget.check(self._d.projected_call_usd)  # s4: fail before spend
        reply = self._d.model.respond(system=SYSTEM_PROMPT, messages=messages)
        self._d.budget.record(reply.cost_usd)

        return self._finalise(reply.text)

    def _finalise(self, reply: str) -> str:
        return self._d.redaction.scrub(reply)  # s3: nothing leaves unscrubbed
