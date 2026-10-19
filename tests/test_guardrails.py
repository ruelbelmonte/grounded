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


# NHIs below use the ZZZ prefix, which the NHI standard reserves for testing.


def test_redacts_email_phone_and_nhi() -> None:
    f = RedactionFilter()
    out = f.scrub("contact jane.doe@example.org or 021 000 0000, nhi ZZZ0016")
    assert "jane.doe@example.org" not in out
    assert "021 000 0000" not in out
    assert "ZZZ0016" not in out
    assert "[REDACTED_EMAIL]" in out
    assert "[REDACTED_NHI]" in out


@pytest.mark.parametrize(
    "mobile",
    [
        "021 000 0000",
        "0210000000",
        "+64 21 000 0000",
        "+6421 000 0000",
        "+64-21-000-0000",
    ],
)
def test_redacts_nz_mobile_formats_without_leftovers(mobile: str) -> None:
    assert RedactionFilter().scrub(f"call {mobile} now") == "call [REDACTED_PHONE] now"


@pytest.mark.parametrize("nhi", ["ZZZ0016", "zzz0024", "ZZZ00AX", "zzz00ax"])
def test_redacts_valid_nhi_in_either_format_and_case(nhi: str) -> None:
    assert RedactionFilter().scrub(f"nhi {nhi}.") == "nhi [REDACTED_NHI]."


@pytest.mark.parametrize("token", ["AWS2023", "ZZZ0017", "ZZZ00AY"])
def test_leaves_nhi_shaped_tokens_with_a_bad_check_character(token: str) -> None:
    assert token in RedactionFilter().scrub(f"see {token} here")


def test_blocks_configured_secret_value() -> None:
    f = RedactionFilter(blocked_secrets=("sk-live-supersecret",))
    assert "sk-live-supersecret" not in f.scrub("the key is sk-live-supersecret ok")


def test_blocks_configured_secret_regardless_of_case() -> None:
    f = RedactionFilter(blocked_secrets=("sk-live-supersecret",))
    assert f.scrub("key SK-LIVE-SuperSecret ok") == "key [REDACTED_SECRET] ok"


def test_masks_overlapping_secrets_whole() -> None:
    f = RedactionFilter(blocked_secrets=("abc", "abc-123"))
    assert f.scrub("x abc-123 y") == "x [REDACTED_SECRET] y"


def test_documents_a_known_limit_novel_identifier_format() -> None:
    # Honest about the backstop's edges: an unusual format is not caught. This
    # is why redaction is a last gate, not the only defence (DESIGN.md s3).
    f = RedactionFilter()
    unusual = "ID#=AB-12-CD-34"
    assert unusual in f.scrub(unusual)


# Known gaps (README "Limitations"). strict=True: if one starts passing, the
# docs are out of date and this suite fails until they are updated.
@pytest.mark.parametrize(
    "identifier",
    [
        pytest.param("(04) 000 0000", id="nz-landline"),
        pytest.param("+64 4 000 0000", id="nz-landline-international"),
        pytest.param("ZZZ0017", id="mistyped-nhi"),
        pytest.param("01/01/1970", id="date-of-birth"),
        pytest.param("000-000-000", id="ird-number"),
        pytest.param("4111 1111 1111 1111", id="card-number"),
        pytest.param("Jane Doe", id="personal-name"),
        pytest.param("sk-live-supersecreX", id="near-miss-secret"),
    ],
)
@pytest.mark.xfail(strict=True, reason="not covered by pattern-based redaction")
def test_known_redaction_gaps(identifier: str) -> None:
    f = RedactionFilter(blocked_secrets=("sk-live-supersecret",))
    assert identifier not in f.scrub(f"value: {identifier}")


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
