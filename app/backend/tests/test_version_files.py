"""Version file access tests: historical commits are read straight from the object store."""

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from dulwich import porcelain

from lingforge.application import version_files


def _commit_file(repo_dir: Path, path: str, content: str, message: str) -> str:
    target = repo_dir / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    porcelain.add(str(repo_dir), [path])
    return porcelain.commit(str(repo_dir), message=message.encode(), committer=b"Test <t@t>" ).decode()


@pytest.fixture()
def repo_setup(tmp_path: Path):
    project_id = uuid4()
    repo_dir = tmp_path / str(project_id) / "repository"
    repo_dir.mkdir(parents=True)
    porcelain.init(str(repo_dir))
    first = _commit_file(repo_dir, "src/App.tsx", "v1", "first")
    second = _commit_file(repo_dir, "src/App.tsx", "v2", "second")
    with patch("lingforge.application.version_files.settings") as mock_settings:
        mock_settings.projects_root = tmp_path
        yield project_id, first, second


def test_list_files_at_commit(repo_setup) -> None:
    project_id, first, _second = repo_setup
    assert version_files.list_files(project_id, first) == ["src/App.tsx"]


def test_read_file_at_each_commit(repo_setup) -> None:
    project_id, first, second = repo_setup
    assert version_files.read_file(project_id, first, "src/App.tsx") == "v1"
    assert version_files.read_file(project_id, second, "src/App.tsx") == "v2"


def test_read_file_rejects_traversal(repo_setup) -> None:
    project_id, first, _second = repo_setup
    with pytest.raises(version_files.VersionFilesError):
        version_files.read_file(project_id, first, "../secret.txt")


def test_read_file_missing_path(repo_setup) -> None:
    project_id, first, _second = repo_setup
    with pytest.raises(version_files.VersionFilesError):
        version_files.read_file(project_id, first, "src/Missing.tsx")
