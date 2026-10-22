"""Deterministic source policy checks before an untrusted app reaches Docker build."""

from pathlib import Path
import re


ALLOWED_ROOT_FILES = {"index.html", "package.json", "pnpm-lock.yaml", "tsconfig.json", "tsconfig.node.json", "vite.config.ts"}
# `public/` holds static assets for the generated app; the Preview Gateway serves it with
# a restrictive CSP (no inline script execution) from an isolated origin.
ALLOWED_PREFIXES = ("src/", "public/")
ALLOWED_DEPENDENCIES = {"@vitejs/plugin-react", "vite", "typescript", "react", "react-dom"}
FORBIDDEN_IMPORTS = ("node:", "child_process", "fs", "net", "http", "https", "worker_threads")
# Local/session storage belongs to the generated application origin, which is isolated
# from the workbench by Preview Gateway. It may therefore support ordinary offline UI
# state. Dynamic execution and platform-cookie access remain prohibited.
FORBIDDEN_APIS = ("eval(", "new Function", "import(", "document.cookie")
MAX_FILES = 200
MAX_FILE_BYTES = 200_000


class SourcePolicyError(ValueError):
    """A generated source tree crossed a platform-owned safety boundary."""


def _relative(root: Path, path: Path) -> str:
    relative = path.relative_to(root).as_posix()
    if relative.startswith("../") or "/../" in relative:
        raise SourcePolicyError("Path traversal is not allowed")
    return relative


def validate_source_tree(root: Path) -> None:
    """Reject unsafe paths, dependency drift, imports and browser escape hatches.

    This intentionally conservative lexical pass is the first deterministic guard. The
    TypeScript compiler and locked package manager remain the second guard in Build Runner.
    """
    # The build runner copies node_modules into the worktree; dependency and build
    # output directories are never "generated source" and must not count toward the
    # file budget or trip the path/suffix checks (repair re-validates after a build).
    files = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and "node_modules" not in path.parts
        and "dist" not in path.parts
    ]
    if len(files) > MAX_FILES:
        raise SourcePolicyError(f"Generated project exceeds {MAX_FILES} files")
    for path in files:
        relative = _relative(root, path)
        if not (relative in ALLOWED_ROOT_FILES or relative.startswith(ALLOWED_PREFIXES)):
            raise SourcePolicyError(f"Generated file is outside the allowlist: {relative}")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise SourcePolicyError(f"Generated file is too large: {relative}")
        # The platform-owned `pnpm-lock.yaml` is part of the immutable template.
        # It is allowlisted by its exact root name above, so accepting its YAML suffix
        # does not open a directory for agent-controlled configuration files.
        # SVG is admitted for static assets; the preview CSP (`default-src 'self'`, no
        # inline script) keeps it passive when served from the isolated preview origin.
        if path.suffix not in {".ts", ".tsx", ".css", ".html", ".json", ".yaml", ".svg"}:
            raise SourcePolicyError(f"Unsupported generated file type: {relative}")
        if path.suffix in {".ts", ".tsx"}:
            content = path.read_text(encoding="utf-8")
            if any(token in content for token in FORBIDDEN_APIS):
                raise SourcePolicyError(f"Dangerous browser API in {relative}")
            for module_name in re.findall(r"(?:from\s+|import\s*\()\s*['\"]([^'\"]+)", content):
                if module_name.startswith(FORBIDDEN_IMPORTS):
                    raise SourcePolicyError(f"Forbidden import {module_name} in {relative}")
                # `vite` and its platform plugins occur only in the platform-owned Vite
                # configuration. Agents cannot modify that root file, while generated
                # application sources still remain constrained to relative/React imports.
                if not (
                    module_name.startswith((".", "/", "react"))
                    or module_name in {"vite", "@vitejs/plugin-react", "@tailwindcss/vite"}
                ):
                    raise SourcePolicyError(f"Dependency import is not allowlisted: {module_name}")
