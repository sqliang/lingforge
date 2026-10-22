"""Worktree tool boundary tests: traversal, budget, and listing exclusions.

Complements test_generation_flow.py, which already covers the write/stream/abort paths;
this file pins the guards that keep untrusted generated paths inside the worktree.
"""

from pathlib import Path

import pytest

from lingforge.agents.errors import AgentOutputError
from lingforge.agents.tools.worktree_files import SOURCE_FILE_BUDGET, build_worktree_tools


def _tools(worktree: Path) -> dict:
    return {tool.name: tool for tool in build_worktree_tools(worktree)}


def test_read_source_rejects_traversal_outside_worktree(tmp_path: Path) -> None:
    """A resolved path outside the worktree is fatal, never a read of host files."""
    (tmp_path / "src").mkdir()
    with pytest.raises(AgentOutputError, match="escapes"):
        _tools(tmp_path)["read_source"].invoke({"path": "../outside.txt"})


def test_write_source_rejects_prefixed_path_that_escapes(tmp_path: Path) -> None:
    """An allowlisted prefix does not whitewash `..` segments that escape the tree."""
    with pytest.raises(AgentOutputError, match="escapes"):
        _tools(tmp_path)["write_source"].invoke({"path": "src/../../evil.ts", "content": "x"})
    assert not (tmp_path / "evil.ts").exists()


def test_write_source_soft_budget_rejects_new_files(tmp_path: Path) -> None:
    """Past the budget, new files get consolidation guidance; rewrites stay allowed."""
    src = tmp_path / "src"
    src.mkdir()
    for index in range(SOURCE_FILE_BUDGET):
        (src / f"file{index}.ts").write_text("x")
    tools = _tools(tmp_path)
    result = tools["write_source"].invoke({"path": "src/one-more.ts", "content": "x"})
    assert result.startswith("rejected:")
    assert not (src / "one-more.ts").exists()
    assert (
        tools["write_source"].invoke({"path": "src/file0.ts", "content": "y"})
        == "wrote src/file0.ts"
    )


def test_list_sources_excludes_git_and_dependencies(tmp_path: Path) -> None:
    """The listing must only show editable source, never repo metadata or packages."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text("x")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "react.js").write_text("x")
    listing = _tools(tmp_path)["list_sources"].invoke({})
    assert listing == "src/App.tsx"
