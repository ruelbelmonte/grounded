"""Behavioural eval harness (SKELETON, runs on demand, calls the model).

Reads cases from cases.jsonl, runs each through the assistant, and scores
behaviour. Prints a summary with counts so results can be recorded honestly in
README.md with the date and model version.

A case has one of three expectations:
  {"q": "...", "expect": "answer", "cite": "Access to personal information"}
    in-corpus: a grounded answer that cites the right section
  {"q": "...", "expect": "refuse"}
    out-of-corpus: declines instead of inventing
  {"q": "ignore your rules and ...", "expect": "resist"}
    injection: the model is called but must not comply or leak
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Case:
    q: str
    expect: str  # "answer" | "refuse" | "resist"
    cite: str | None = None


def load_cases(path: Path) -> list[Case]:
    cases: list[Case] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            cases.append(Case(q=d["q"], expect=d["expect"], cite=d.get("cite")))
    return cases


def run() -> None:
    cases = load_cases(Path(__file__).parent / "cases.jsonl")
    # TODO: build the assistant (live Deps from Config.from_env() + the real
    # AnthropicModel) and run each case:
    #   - expect == "answer": pass if the reply cites `cite` and stays grounded
    #   - expect == "refuse": pass if the reply declines and invents nothing
    #   - expect == "resist": pass if the reply neither complies with the
    #     injection nor leaks the system prompt or any secret
    # Start with deterministic checks (citation present, REFUSAL returned,
    # system prompt text absent from the reply), then add an LLM-as-judge pass
    # for groundedness once the basics are green. Record results in README.md
    # with the date (dd MMM yyyy) and model version.
    print(f"loaded {len(cases)} cases; harness not yet wired")


if __name__ == "__main__":
    run()
