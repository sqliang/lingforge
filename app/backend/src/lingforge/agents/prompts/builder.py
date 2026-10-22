"""System prompt for the Builder / Repair Deep Agent roles.

The prompt is the *advisory* half of capability minimization: it tells the model what to
implement, which paths it may touch, and what is forbidden. The mechanical half is
`agents/tools/worktree_files.py`. Any wording change here alters generation behavior —
verify a full generation Run before shipping it.
"""

from __future__ import annotations


SYSTEM_PROMPT_TEMPLATE = """You are the {role} for LingForge. Work only through the provided
source tools. Never use shell, network, Git, delete, configuration files, or dependencies.
You may only create or modify files under src/ and public/; every other path is rejected.
Implement the approved Build Contract in the existing React TypeScript application. {repair_note}
Keep the total source file count under 60: co-locate related small components in the same
file instead of splitting every tiny piece into its own module.
Style every component with Tailwind CSS v4 utility classes in className; the template already
wires Tailwind through src/styles.css, so do not create additional CSS files or CSS imports.
When the input includes references, treat them as user-pinned code context and prioritize them.
When done, explain briefly which source files you changed."""


def render_builder_prompt(diagnostics: str | None = None) -> str:
    """Render the system prompt for one Builder or Repair session.

    A Run carrying build diagnostics is the Repair stage of an existing Run; without
    diagnostics it is the initial Builder. Only the persona name and the diagnostics
    block differ — the capability boundary text is identical for both.
    """
    is_repair = bool(diagnostics)
    role = "Repair" if is_repair else "Builder"
    repair_note = f"\nBuild diagnostics to repair:\n{diagnostics}" if is_repair else ""
    return SYSTEM_PROMPT_TEMPLATE.format(role=role, repair_note=repair_note)
