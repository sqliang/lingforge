"""Prompt render tests: role/persona wiring and interpolation for every agent role."""

from lite_atoms.agents.prompts.builder import render_builder_prompt
from lite_atoms.agents.prompts.planner import render_planner_instructions, render_retry_feedback
from lite_atoms.agents.prompts.titles import render_title_prompt


def test_builder_prompt_without_diagnostics_is_builder() -> None:
    prompt = render_builder_prompt(None)
    assert "You are the Builder" in prompt
    assert "Build diagnostics" not in prompt
    # The capability boundary must be stated for both personas.
    assert "src/ and public/" in prompt


def test_builder_prompt_with_diagnostics_is_repair() -> None:
    prompt = render_builder_prompt("TS2322: Type 'string' is not assignable")
    assert "You are the Repair" in prompt
    assert "Build diagnostics to repair:\nTS2322" in prompt


def test_planner_instructions_embed_request_and_schema() -> None:
    instructions = render_planner_instructions("build a todo app")
    assert instructions.endswith("User request:\nbuild a todo app")
    assert "acceptanceCriteria" in instructions
    assert "exactly one JSON object" in instructions


def test_planner_retry_feedback_carries_rejection_reason() -> None:
    feedback = render_retry_feedback(ValueError("features must have 1-12 items"))
    assert "features must have 1-12 items" in feedback
    assert "corrected JSON object only" in feedback


def test_title_prompt_embeds_request() -> None:
    prompt = render_title_prompt("帮我创建一个待办事项应用")
    assert prompt.endswith("帮我创建一个待办事项应用")
    assert "at most 6 words" in prompt
