"""Read-only access to historical project versions stored in the local Git mirror.

The stable repository keeps every promoted commit, so historical versions can be served
straight from the object store without touching the working tree or the stable pointer.
"""

from uuid import UUID

from dulwich.objects import Tree
from dulwich.repo import Repo

from lingforge.settings import settings

MAX_FILE_BYTES = 200_000


class VersionFilesError(ValueError):
    """The requested historical version or file is not readable."""


def _open_repo(project_id: UUID) -> Repo:
    repository_root = settings.projects_root / str(project_id) / "repository"
    if not repository_root.is_dir():
        raise VersionFilesError("Project repository not found")
    return Repo(str(repository_root))


def _tree_at(repo: Repo, commit_sha: str) -> Tree:
    try:
        commit = repo[commit_sha.encode("ascii")]
    except KeyError as error:
        raise VersionFilesError("Version commit not found") from error
    return repo[commit.tree]


def list_files(project_id: UUID, commit_sha: str) -> list[str]:
    """List every tracked file path at one commit, excluding dependency directories."""
    repo = _open_repo(project_id)
    paths: list[str] = []

    def walk(tree: Tree, prefix: str) -> None:
        for name, mode, sha in tree.items():
            entry = prefix + name.decode()
            if mode & 0o40000:
                walk(repo[sha], entry + "/")
            else:
                paths.append(entry)

    walk(_tree_at(repo, commit_sha), "")
    return sorted(path for path in paths if "node_modules/" not in path and ".git/" not in path)


def read_file(project_id: UUID, commit_sha: str, path: str) -> str:
    """Read one bounded UTF-8 file at one commit; traversal outside the tree is rejected."""
    if not path or ".." in path.split("/"):
        raise VersionFilesError("File not found in this version")
    repo = _open_repo(project_id)
    node = _tree_at(repo, commit_sha)
    for segment in path.split("/"):
        try:
            _mode, sha = node[segment.encode()]
        except KeyError as error:
            raise VersionFilesError("File not found in this version") from error
        node = repo[sha]
    data: bytes = node.data
    if len(data) > MAX_FILE_BYTES:
        raise VersionFilesError("File is too large to display")
    return data.decode("utf-8")
