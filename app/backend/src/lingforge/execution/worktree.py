"""Ephemeral Git worktrees for untrusted generated source.

Only the trusted Worker invokes this module. Agent tools receive an already-created
directory and can never select a host path, repository, or Git credential.
"""

from pathlib import Path
import os
import shutil
from uuid import UUID

from dulwich import porcelain
from dulwich.repo import Repo
from lingforge.settings import settings


TEMPLATE_ROOT = Path(os.getenv("TEMPLATE_ROOT", "/app/templates/react-vite-tailwind"))


class WorktreeError(RuntimeError):
    """Raised when deterministic repository setup or commit creation fails."""


COMMITTER = b"LingForge Worker <worker@lingforge.local>"
BUILD_UID = 10001
BUILD_GID = 10001


def _commit(directory: Path, message: str) -> str:
    """Create a standard Git commit without granting a model a Git executable."""
    try:
        porcelain.add(str(directory))
        commit = porcelain.commit(str(directory), message=message.encode("utf-8"), committer=COMMITTER)
        return commit.decode("ascii")
    except Exception as error:
        raise WorktreeError(f"Could not create Git commit: {error}") from error


def _grant_build_runner_access(worktree: Path) -> None:
    """Hand the ephemeral source tree to the rootless build UID, not to the model.

    The trusted Worker creates the tree on a Docker volume as root. The separate Build
    Runner deliberately executes as UID 10001; normalizing ownership here lets it create
    `node_modules` and `dist` without weakening the Runner to root.
    """
    try:
        for entry in (worktree, *worktree.rglob("*")):
            if not entry.is_symlink():
                os.chown(entry, BUILD_UID, BUILD_GID)
    except OSError as error:
        raise WorktreeError(f"Could not prepare rootless build worktree: {error}") from error


def create_worktree(project_id: UUID, run_id: UUID) -> Path:
    """Create a disposable source directory based on the current stable project tree.

    A failed Run only removes this directory; its source can therefore never overwrite the
    project repository or the version currently shown by Preview.
    """
    project_root = settings.projects_root / str(project_id)
    run_root = project_root / ".runs" / str(run_id)
    if run_root.exists():
        raise WorktreeError("A worktree already exists for this Run")
    run_root.parent.mkdir(parents=True, exist_ok=True)
    source_root = project_root / "repository"
    if source_root.exists():
        shutil.copytree(source_root, run_root, ignore=shutil.ignore_patterns(".runs", "dist", "node_modules"))
    else:
        shutil.copytree(TEMPLATE_ROOT, run_root)
        porcelain.init(str(run_root))
        _commit(run_root, "Initialize generated application template")
    _grant_build_runner_access(run_root)
    return run_root


def promote_worktree(project_id: UUID, worktree: Path, message: str) -> str:
    """Commit a validated worktree and atomically replace the local source mirror.

    Database promotion happens later as a Saga step. If that final transaction fails, the
    repository commit may be orphaned, but `stable_version_id` remains unchanged.
    """
    repository = Repo(str(worktree))
    status = porcelain.status(str(worktree))
    if status.staged or status.unstaged or status.untracked:
        commit_sha = _commit(worktree, message[:200])
    else:
        commit_sha = repository.head().decode("ascii")
    repository_root = settings.projects_root / str(project_id) / "repository"
    replacement = repository_root.with_name("repository.next")
    if replacement.exists():
        shutil.rmtree(replacement)
    shutil.copytree(worktree, replacement, ignore=shutil.ignore_patterns(".runs", "dist", "node_modules"))
    if repository_root.exists():
        shutil.rmtree(repository_root)
    replacement.rename(repository_root)
    return commit_sha


def cleanup_worktree(worktree: Path) -> None:
    """Best-effort cleanup after terminal Run state; never removes the stable repository."""
    if worktree.exists() and ".runs" in worktree.parts:
        shutil.rmtree(worktree, ignore_errors=True)
