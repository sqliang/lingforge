"""Semantic project naming via one bounded plain model call."""

from lite_atoms.agents.errors import AgentOutputError
from lite_atoms.agents.model import _model
from lite_atoms.agents.prompts.titles import render_title_prompt


def generate_project_title(prompt: str) -> str:
    """Best-effort semantic project title; the caller keeps the placeholder on failure.

    This deliberately uses the plain model adapter, not a Deep Agent: naming needs one
    bounded completion without any tool capability.
    """
    response = _model().invoke(render_title_prompt(prompt))
    lines = str(response.content).strip().strip('"').splitlines()
    title = (lines[0].strip() if lines else "")[:60]
    if not title:
        raise AgentOutputError("Model returned an empty project title")
    return title
