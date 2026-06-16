"""Deterministic tests for the guardrail layer.

These are the proof that the safety properties hold. No network, no API key, no
sleeping: time is injected. If a guardrail cannot be tested like this, it is not
a control (DESIGN.md section 1).
"""

from __future__ import annotations

import pytest

from grounded.guardrails import (
    BudgetExceeded,
    BudgetTracker,
    RateLimiter,
    RedactionFilter,
)


class FakeClock:
    """A controllable monotonic clock for the rate limiter."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


# --- Redaction -------------------------------------------------------------


def test_redacts_email_phone_and_nhi() -> None:
    f = RedactionFilter()
    out = f.scrub("contact jane.doe@example.org or 021 234 5678, nhi ABC1234")
    assert "jane.doe@example.org" not in out
    assert "021 234 5678" not in out
    assert "ABC1234" not in out
    assert "[REDACTED_EMAIL]" in out
    assert "[REDACTED_NHI]" in out


def test_blocks_configured_secret_value() -> None:
    f = RedactionFilter(blocked_secrets=("sk-live-supersecret",))
    assert "sk-live-supersecret" not in f.scrub("the key is sk-live-supersecret ok")


def test_documents_a_known_limit_novel_identifier_format() -> None:
    # Honest about the backstop's edges: an unusual format is not caught. This
    # is why redaction is a last gate, not the only defence (DESIGN.md s3).
    f = RedactionFilter()
    unusual = "ID#=AB-12-CD-34"
    assert unusual in f.scrub(unusual)


# --- Rate limiting ---------------------------------------------------------


def test_blocks_after_limit_then_recovers_after_window() -> None:
    clock = FakeClock()
    limiter = RateLimiter(max_per_hour=2, clock=clock)
    assert limiter.allow("user-1") is True
    assert limiter.allow("user-1") is True
    assert limiter.allow("user-1") is False  # third within the hour
    clock.advance(3601)
    assert limiter.allow("user-1") is True  # window has rolled over


def test_limits_are_per_key() -> None:
    clock = FakeClock()
    limiter = RateLimiter(max_per_hour=1, clock=clock)
    assert limiter.allow("user-1") is True
    assert limiter.allow("user-2") is True  # a different key is unaffected


# --- Budget ----------------------------------------------------------------


def test_hard_stop_refuses_call_over_ceiling() -> None:
    b = BudgetTracker(ceiling_usd=1.0)
    b.record(0.90)
    b.check(0.05)  # fine
    with pytest.raises(BudgetExceeded):
        b.check(0.20)  # would exceed


def test_soft_alert_fires_once() -> None:
    b = BudgetTracker(ceiling_usd=1.0, alert_fraction=0.8)
    assert b.record(0.5) is False
    assert b.record(0.4) is True  # crosses 0.8
    assert b.record(0.05) is False  # does not fire again
