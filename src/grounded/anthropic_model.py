"""Anthropic-backed ModelClient. Imported only by the CLI, never by the test
suite, so the deterministic tests need neither the SDK nor an API key.

Pricing constants are for the configured model; if the model changes, update
these in the same change (a real spend tracker that lies about price is worse
than none).
"""

from __future__ import annotations

from typing import cast

import anthropic
from anthropic.types import MessageParam, TextBlock

from .agent import Message, ModelReply

# claude-sonnet-4-6 list pricing, USD per token. Verify against current pricing
# before trusting the spend numbers.
_INPUT_USD_PER_TOKEN = 3.0 / 1_000_000
_OUTPUT_USD_PER_TOKEN = 15.0 / 1_000_000


class AnthropicModel:
    def __init__(self, api_key: str, model: str, max_tokens: int = 1024) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def respond(self, *, system: str, messages: list[Message]) -> ModelReply:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=cast("list[MessageParam]", messages),
        )
        text = "".join(b.text for b in resp.content if isinstance(b, TextBlock))
        cost = (
            resp.usage.input_tokens * _INPUT_USD_PER_TOKEN
            + resp.usage.output_tokens * _OUTPUT_USD_PER_TOKEN
        )
        return ModelReply(text=text, cost_usd=cost)
