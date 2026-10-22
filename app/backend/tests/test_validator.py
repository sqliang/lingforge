"""Regression tests for deterministic generated-source boundaries."""

from pathlib import Path

import pytest

from lingforge.execution.validator import SourcePolicyError, validate_source_tree


def write_minimal_project(root: Path, source: str = "export const value = 1;") -> None:
    """Create the smallest tree accepted by the source-policy allowlist."""
    (root / "src").mkdir()
    (root / "src" / "App.tsx").write_text(source, encoding="utf-8")
    (root / "package.json").write_text("{}", encoding="utf-8")


def test_accepts_allowlisted_react_source(tmp_path: Path) -> None:
    write_minimal_project(tmp_path, "import React from 'react'; export const App = () => <main />;")
    validate_source_tree(tmp_path)


def test_ignores_node_modules_and_dist_from_build(tmp_path: Path) -> None:
    """A worktree re-validated after a build must not count dependency/output trees."""
    write_minimal_project(tmp_path)
    dependency_dir = tmp_path / "node_modules" / "react"
    dependency_dir.mkdir(parents=True)
    (dependency_dir / "index.js").write_text("module.exports = {}", encoding="utf-8")
    dist_dir = tmp_path / "dist" / "assets"
    dist_dir.mkdir(parents=True)
    (dist_dir / "index.js").write_text("console.log(1)", encoding="utf-8")
    validate_source_tree(tmp_path)


def test_accepts_platform_owned_pnpm_lockfile(tmp_path: Path) -> None:
    """The fixed template lockfile must survive validation before an offline build."""
    write_minimal_project(tmp_path)
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    validate_source_tree(tmp_path)


def test_accepts_platform_owned_vite_config_import(tmp_path: Path) -> None:
    """The fixed Vite configuration imports only the locked platform dependency."""
    write_minimal_project(tmp_path)
    (tmp_path / "vite.config.ts").write_text("import { defineConfig } from 'vite';", encoding="utf-8")
    validate_source_tree(tmp_path)


def test_accepts_isolated_preview_local_storage(tmp_path: Path) -> None:
    """Generated apps may retain non-sensitive UI state in their separate preview origin."""
    write_minimal_project(tmp_path, "localStorage.setItem('todos', '[]');")
    validate_source_tree(tmp_path)


@pytest.mark.parametrize("source", ["eval('x')", "import fs from 'fs';", "const m = import('x');"])
def test_rejects_dangerous_generated_source(tmp_path: Path, source: str) -> None:
    write_minimal_project(tmp_path, source)
    with pytest.raises(SourcePolicyError):
        validate_source_tree(tmp_path)


def test_rejects_write_outside_generated_allowlist(tmp_path: Path) -> None:
    write_minimal_project(tmp_path)
    (tmp_path / ".env").write_text("secret", encoding="utf-8")
    with pytest.raises(SourcePolicyError, match="allowlist"):
        validate_source_tree(tmp_path)
