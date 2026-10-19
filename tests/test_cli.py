"""CLI error handling, with the model adapter stubbed out so no SDK call or
network access happens."""

from __future__ import annotations

import sys
import types

import pytest

from grounded import cli
from grounded.guardrails import BudgetExceeded


class _OverBudgetAssistant:
    def __init__(self, deps: object) -> None:
        pass

    def ask(self, user_id: str, question: str) -> str:
        raise BudgetExceeded("spend 20.00 + 0.02 exceeds ceiling 20.00")


def test_budget_exceeded_exits_non_zero_with_a_clean_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub = types.ModuleType("grounded.anthropic_model")
    stub.AnthropicModel = lambda *args, **kwargs: object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "grounded.anthropic_model", stub)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setattr(cli, "Assistant", _OverBudgetAssistant)
    monkeypatch.setattr(sys, "argv", ["grounded", "ask", "request access"])

    assert cli.main() == 1
    err = capsys.readouterr().err
    assert "budget ceiling reached" in err
    assert "Traceback" not in err
