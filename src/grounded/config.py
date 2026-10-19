"""Configuration, loaded from the environment and validated at startup.

Fail fast: a missing or malformed value is an error at construction, not a
surprise on the first request. Secrets come from the environment, never from
code or a checked-in file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str
    model: str = "claude-sonnet-4-6"
    # Guardrail limits. See DESIGN.md for why each exists.
    requests_per_hour: int = 60
    monthly_budget_usd: float = 20.0
    budget_alert_fraction: float = 0.8
    max_agent_steps: int = 4
    # Secret values that must never appear in an outgoing reply. Loaded from the
    # environment so the list itself is never hard-coded.
    blocked_secrets: tuple[str, ...] = ()

    @staticmethod
    def from_env() -> Config:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is required")
        blocked = tuple(
            s for s in os.environ.get("GROUNDED_BLOCKED_SECRETS", "").split(",") if s
        )
        return Config(anthropic_api_key=key, blocked_secrets=blocked)
