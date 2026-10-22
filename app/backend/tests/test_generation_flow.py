"""Generation-flow unit tests: streaming callback, abort, write guidance, and naming."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from lingforge.agents.tools.worktree_files import build_reference_excerpts, build_worktree_tools
from lingforge.agents.errors import AgentAborted
from lingforge.agents.titles import generate_project_title
from lingforge.worker.main import RunCancelled, _raise_if_cancel_requested

CALLBACK_CALLS: list[tuple[str, str]] = []


def _callback(path: str, content: str) -> None:
    CALLBACK_CALLS.append((path, content))


def _write_tool(worktree: Path, should_abort=None):
    tools = {
        tool.name: tool
        for tool in build_worktree_tools(
            worktree, on_file_written=_callback, should_abort=should_abort
        )
    }
    return tools["write_source"]


def test_write_source_streams_written_file(tmp_path: Path) -> None:
    CALLBACK_CALLS.clear()
    _write_tool(tmp_path).invoke({"path": "src/App.tsx", "content": "export default 1;"})
    assert CALLBACK_CALLS == [("src/App.tsx", "export default 1;")]
    assert (tmp_path / "src" / "App.tsx").read_text() == "export default 1;"


def test_write_source_outside_allowlist_returns_guidance(tmp_path: Path) -> None:
    """Allowlist violations must be recoverable feedback, never a Run-killing exception."""
    CALLBACK_CALLS.clear()
    result = _write_tool(tmp_path).invoke({"path": "package.json", "content": "{}"})
    assert result.startswith("rejected:")
    assert CALLBACK_CALLS == []
    assert not (tmp_path / "package.json").exists()


def test_write_source_allows_public_assets(tmp_path: Path) -> None:
    CALLBACK_CALLS.clear()
    result = _write_tool(tmp_path).invoke({"path": "public/logo.svg", "content": "<svg />"})
    assert result == "wrote public/logo.svg"
    assert (tmp_path / "public" / "logo.svg").exists()


def test_write_source_oversize_returns_guidance(tmp_path: Path) -> None:
    CALLBACK_CALLS.clear()
    result = _write_tool(tmp_path).invoke({"path": "src/big.ts", "content": "x" * 200_001})
    assert result.startswith("rejected:")
    assert CALLBACK_CALLS == []


def test_write_source_aborts_between_tool_calls(tmp_path: Path) -> None:
    with pytest.raises(AgentAborted):
        _write_tool(tmp_path, should_abort=lambda: True).invoke(
            {"path": "src/App.tsx", "content": "x"}
        )
    assert not (tmp_path / "src" / "App.tsx").exists()


def test_all_tools_abort_when_cancel_requested(tmp_path: Path) -> None:
    """read/list/write must all unwind promptly once the owner cancels the Run."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text("x")
    tools = {tool.name: tool for tool in build_worktree_tools(tmp_path, should_abort=lambda: True)}
    with pytest.raises(AgentAborted):
        tools["read_source"].invoke({"path": "src/App.tsx"})
    with pytest.raises(AgentAborted):
        tools["list_sources"].invoke({})


def test_cancel_check_passes_without_request() -> None:
    with patch("lingforge.worker.main.repository.cancel_requested", return_value=False):
        _raise_if_cancel_requested("00000000-0000-0000-0000-000000000000")  # type: ignore[arg-type]


def test_cancel_check_raises_after_request() -> None:
    with (
        patch("lingforge.worker.main.repository.cancel_requested", return_value=True),
        pytest.raises(RunCancelled),
    ):
        _raise_if_cancel_requested("00000000-0000-0000-0000-000000000000")  # type: ignore[arg-type]


def test_generate_project_title_uses_model_text() -> None:
    response = SimpleNamespace(content='"Todo Manager"\n')
    with patch("lingforge.agents.titles._model") as model:
        model.return_value.invoke.return_value = response
        assert generate_project_title("帮我创建一个待办事项应用") == "Todo Manager"


def test_generate_project_title_rejects_empty_output() -> None:
    response = SimpleNamespace(content="  \n")
    with (
        patch("lingforge.agents.titles._model") as model,
        pytest.raises(ValueError, match="empty"),
    ):
        model.return_value.invoke.return_value = response
        generate_project_title("帮我创建一个待办事项应用")


def test_reference_excerpts_line_range(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text("l1\nl2\nl3\nl4\nl5")
    excerpts = build_reference_excerpts(
        tmp_path, [{"path": "src/App.tsx", "start_line": 2, "end_line": 4}]
    )
    assert excerpts == [
        {"path": "src/App.tsx", "start_line": 2, "end_line": 4, "excerpt": "2: l2\n3: l3\n4: l4"}
    ]


def test_reference_excerpts_full_file_and_skips(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text("hello")
    excerpts = build_reference_excerpts(
        tmp_path,
        [
            {"path": "src/App.tsx"},  # no line range → whole file
            {"path": "package.json"},  # outside allowlist → skipped
            {"path": "src/Missing.tsx"},  # missing → skipped
        ],
    )
    assert excerpts == [
        {"path": "src/App.tsx", "start_line": None, "end_line": None, "excerpt": "hello"}
    ]


def test_write_source_budget_rejects_new_files_but_allows_rewrites(tmp_path: Path) -> None:
    """Past the soft budget, new files get consolidation guidance; rewrites still work."""
    src = tmp_path / "src"
    src.mkdir()
    for index in range(80):
        (src / f"file{index}.ts").write_text("x")
    result = _write_tool(tmp_path).invoke({"path": "src/file80.ts", "content": "new"})
    assert result.startswith("rejected:")
    assert not (src / "file80.ts").exists()
    result = _write_tool(tmp_path).invoke({"path": "src/file0.ts", "content": "rewritten"})
    assert result == "wrote src/file0.ts"
    assert (src / "file0.ts").read_text() == "rewritten"
