"""The guardrail layer: egress filtering, rate limiting, budget enforcement.

Each guardrail is deterministic and unit-tested. Nothing here depends on the
model behaving well. Time is injected (a ``clock`` callable) so the rate limiter
and budget tracker are testable without sleeping. See DESIGN.md sections 1-4.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field

# --- Egress filtering (DESIGN.md section 3) --------------------------------

# Backstop redaction patterns. These are intentionally conservative and their
# limits are documented in the tests: they catch common shapes, not every
# possible format. Redaction is a last gate, not a reason to put secrets in
# context in the first place.
_EMAIL = re.compile(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
# Lookbehind instead of \b so a leading "+64" is consumed, not left behind.
_NZ_MOBILE = re.compile(r"(?<![\w+])(?:\+?64[ -]?|0)2\d(?:[ -]?\d){6,8}\b")
# NZ NHI: 3 letters then 4 digits (legacy) or 3 letters, 2 digits, 2 letters
# (new). ASCII mode so case folding cannot match look-alikes such as the Kelvin
# sign.
_NHI = re.compile(
    r"\b[A-HJ-NP-Z]{3}\d{2}(?:\d{2}|[A-HJ-NP-Z]{2})\b", re.IGNORECASE | re.ASCII
)
_NHI_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"


def _is_valid_nhi(candidate: str) -> bool:
    """Check character per the NZ NHI standard: weights 7..2 over the first six
    characters (letters A=1..Z=24, skipping I and O), then mod 11 (legacy,
    numeric check) or mod 24 (new, alphabetic check)."""
    nhi = candidate.upper()
    values = [int(c) if c.isdigit() else _NHI_ALPHABET.index(c) + 1 for c in nhi[:6]]
    total = sum(v * w for v, w in zip(values, range(7, 1, -1), strict=True))
    if nhi[6].isdigit():
        remainder = total % 11
        return remainder != 0 and str((11 - remainder) % 10) == nhi[6]
    return _NHI_ALPHABET[23 - total % 24] == nhi[6]


def _redact_nhi(match: re.Match[str]) -> str:
    # Fail closed: a mistyped NHI still identifies someone, so the check
    # character only picks the label, never whether to redact.
    if _is_valid_nhi(match.group()):
        return "[REDACTED_NHI]"
    return "[REDACTED_NHI_CANDIDATE]"


class RedactionFilter:
    """Redacts personal identifiers and blocks configured secret values."""

    def __init__(self, blocked_secrets: tuple[str, ...] = ()) -> None:
        # Longest first so a secret that contains another is masked whole.
        secrets = sorted({s for s in blocked_secrets if s}, key=len, reverse=True)
        self._secrets = (
            re.compile("|".join(map(re.escape, secrets)), re.IGNORECASE)
            if secrets
            else None
        )

    def scrub(self, text: str) -> str:
        if self._secrets is not None:
            text = self._secrets.sub("[REDACTED_SECRET]", text)
        text = _EMAIL.sub("[REDACTED_EMAIL]", text)
        text = _NZ_MOBILE.sub("[REDACTED_PHONE]", text)
        text = _NHI.sub(_redact_nhi, text)
        return text


# --- Rate limiting (DESIGN.md section 1) -----------------------------------


class RateLimiter:
    """Per-key sliding-window limiter. ``clock`` returns monotonic seconds."""

    def __init__(self, max_per_hour: int, clock: Callable[[], float]) -> None:
        self._max = max_per_hour
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self._clock()
        window = self._hits[key]
        cutoff = now - 3600
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= self._max:
            return False
        window.append(now)
        return True


# --- Budget enforcement (DESIGN.md section 4) ------------------------------


class BudgetExceeded(RuntimeError):
    """Raised when a call would push spend past the hard ceiling."""


@dataclass
class BudgetTracker:
    """Tracks process-local spend with a soft alert and a hard stop.

    Process-local by design: this is the fast, cheap ceiling. The durable
    backstop is the provider-side spend limit (DESIGN.md section 4).
    """

    ceiling_usd: float
    alert_fraction: float = 0.8
    spent_usd: float = 0.0
    _alerted: bool = field(default=False, repr=False)

    def check(self, projected_cost_usd: float) -> None:
        if self.spent_usd + projected_cost_usd > self.ceiling_usd:
            raise BudgetExceeded(
                f"spend {self.spent_usd:.2f} + {projected_cost_usd:.2f} "
                f"exceeds ceiling {self.ceiling_usd:.2f}"
            )

    def record(self, cost_usd: float) -> bool:
        """Record actual spend. Returns True once when the alert is first crossed."""
        self.spent_usd += cost_usd
        if (
            not self._alerted
            and self.spent_usd >= self.ceiling_usd * self.alert_fraction
        ):
            self._alerted = True
            return True
        return False
