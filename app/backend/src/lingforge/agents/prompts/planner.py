"""Prompt definitions for the Planner role (Build Contract generation).

The Planner needs a strict JSON-only instruction that weaker models must not see diluted;
that is why it uses a plain model call instead of the Deep Agents harness (see the header
comment in agents/planner.py). Any wording change here alters contract quality — verify
against real user prompts before shipping it.
"""

from __future__ import annotations


INSTRUCTIONS_TEMPLATE = """You are the Planner for LingForge. Return exactly one JSON object.
It must contain title, summary, features (1-12 strings), components (objects with name and responsibility),
nonGoals (strings), and acceptanceCriteria (strings). Do not emit markdown, code, or prose outside the JSON.
User request:\n"""

# Appended as an extra user message when a draft fails validation, so the model sees the
# concrete rejection reason and retries with a corrected object instead of a fresh guess.
RETRY_FEEDBACK_TEMPLATE = (
    "Your previous JSON was rejected: {error}. Return a corrected JSON object only."
)


def render_planner_instructions(prompt: str) -> str:
    """Render the system-level instructions, embedding the user's app request."""
    return INSTRUCTIONS_TEMPLATE + prompt


def render_retry_feedback(error: Exception) -> str:
    """Render the retry user message carrying the validation failure reason."""
    return RETRY_FEEDBACK_TEMPLATE.format(error=error)
