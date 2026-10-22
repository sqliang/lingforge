"""Planner boundary tests: JSON mode output is validated and retried, never persisted raw."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from lingforge.agents.planner import plan_contract
from lingforge.agents.errors import AgentOutputError


def _valid_contract() -> dict:
    return {
        "title": "Todo app",
        "summary": "A small todo application",
        "features": ["Add todos", "Toggle completion"],
        "components": [{"name": "TodoList", "responsibility": "Render todos"}],
        "nonGoals": ["Authentication"],
        "acceptanceCriteria": ["User can add a todo"],
    }


def _model_returning(payloads: list[str]):
    """Build a fake chat model that answers each invoke with the next payload."""
    answers = iter(payloads)

    class FakeModel:
        def invoke(self, _messages):
            return SimpleNamespace(content=next(answers))

    return FakeModel()


def _patch_model(payloads: list[str]):
    return patch("lingforge.agents.planner._model", return_value=_model_returning(payloads))


def test_accepts_valid_contract_on_first_attempt() -> None:
    with _patch_model([json.dumps(_valid_contract())]):
        assert plan_contract("build a todo app")["title"] == "Todo app"


def test_retries_with_feedback_after_invalid_contract() -> None:
    invalid = {**_valid_contract(), "features": []}
    with _patch_model([json.dumps(invalid), json.dumps(_valid_contract())]):
        assert plan_contract("build a todo app")["features"] == ["Add todos", "Toggle completion"]


def test_raises_after_exhausting_attempts() -> None:
    invalid = {**_valid_contract(), "features": [f"feature-{index}" for index in range(20)]}
    with _patch_model([json.dumps(invalid)] * 3), pytest.raises(AgentOutputError, match="between 1 and 12 features"):
        plan_contract("build a todo app")


def test_retries_when_model_returns_non_json() -> None:
    with _patch_model(["sure, here is your plan!", json.dumps(_valid_contract())]):
        assert plan_contract("build a todo app")["title"] == "Todo app"


def test_falls_back_when_provider_rejects_json_mode() -> None:
    """A provider without JSON mode must not kill planning; plain text is retried."""

    class FlakyModel:
        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, _messages):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("response_format is not supported for this model")
            return SimpleNamespace(content=json.dumps(_valid_contract()))

    shared = FlakyModel()
    with patch("lingforge.agents.planner._model", side_effect=lambda json_mode=False: shared):
        assert plan_contract("build a todo app")["title"] == "Todo app"
