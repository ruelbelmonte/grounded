"""Thin CLI transport. Holds no behaviour; wires config to the assistant.

Kept deliberately small so all logic stays in the testable service layer. The
corpus is read from data/corpus/ if present, otherwise from the bundled
sample_corpus/. A live answer needs ANTHROPIC_API_KEY; retrieval and the
guardrails do not.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from .agent import Assistant, Deps
from .config import Config
from .guardrails import BudgetExceeded, BudgetTracker, RateLimiter, RedactionFilter
from .retrieval import Retriever

_ROOT = Path(__file__).resolve().parents[2]


def _corpus_dir() -> Path:
    data = _ROOT / "data" / "corpus"
    return data if data.is_dir() and any(data.iterdir()) else _ROOT / "sample_corpus"


def main() -> int:
    args = sys.argv[1:]
    if len(args) < 2 or args[0] != "ask":
        print('usage: grounded ask "your question"', file=sys.stderr)
        return 2

    question = " ".join(args[1:])
    try:
        cfg = Config.from_env()
    except RuntimeError as exc:
        print(f"grounded: {exc}", file=sys.stderr)
        return 2

    # Imported here so the test suite never needs the SDK or an API key.
    from .anthropic_model import AnthropicModel

    deps = Deps(
        retriever=Retriever.from_corpus_dir(_corpus_dir()),
        redaction=RedactionFilter(cfg.blocked_secrets),
        rate_limiter=RateLimiter(cfg.requests_per_hour, clock=time.monotonic),
        budget=BudgetTracker(cfg.monthly_budget_usd, cfg.budget_alert_fraction),
        model=AnthropicModel(cfg.anthropic_api_key, cfg.model),
    )
    try:
        print(Assistant(deps).ask(user_id="cli", question=question))
    except BudgetExceeded as exc:
        print(
            f"grounded: budget ceiling reached, no call made ({exc})", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
