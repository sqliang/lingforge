"""Prompt definition for semantic project naming (one bounded plain model call)."""

from __future__ import annotations


INSTRUCTIONS_TEMPLATE = (
    "Generate a concise project name (at most 6 words, no quotes) for this app request. "
    "Reply with the name only.\n\n"
)


def render_title_prompt(prompt: str) -> str:
    """Render the single-shot naming message for the user's app request."""
    return INSTRUCTIONS_TEMPLATE + prompt
