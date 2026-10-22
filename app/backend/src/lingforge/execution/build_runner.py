"""Rootless, network-isolated TypeScript and Vite production build runner."""

from dataclasses import dataclass
from pathlib import Path
import time

import docker
from docker.errors import DockerException

from lingforge.settings import settings


@dataclass(frozen=True)
class BuildResult:
    """Build outcome retained as a bounded diagnostic, never as raw agent output."""

    succeeded: bool
    log: str
    duration_ms: int


def run_build(worktree: Path) -> BuildResult:
    """Run locked dependencies in a constrained Docker container with no network access."""
    started = time.monotonic()
    container = None
    try:
        # The Worker itself runs inside a container, so its `/var/lib/...` path is not
        # a host bind source for the Docker socket. Mount the shared named volume by
        # name and constrain the command's working directory to this Run's leaf tree.
        relative_worktree = worktree.relative_to(settings.projects_root).as_posix()
        workspace = f"/projects/{relative_worktree}"
        client = docker.from_env()
        container = client.containers.run(
            settings.build_runner_image,
            # Do not use `cp -a`: BusyBox then tries to preserve the image's root-owned
            # dependency ownership and fails under the rootless build UID. A recursive
            # copy preserves the locked bytes while making the mounted worktree writable.
            # Docker SDK splits a string command into argv. This image deliberately uses
            # `/bin/sh -lc`, so the complete script must remain one argument after `-c`.
            # node_modules is removed again afterwards (success or failure): the shared
            # worktree must stay dependency-free for re-validation and promotion.
            [f"cd {workspace} && cp -R /opt/dependencies/node_modules ./ && (pnpm run typecheck && pnpm run build); rc=$?; rm -rf node_modules; exit $rc"],
            detach=True,
            network_mode="none",
            user="10001:10001",
            nano_cpus=1_000_000_000,
            mem_limit="512m",
            pids_limit=128,
            read_only=True,
            tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
            volumes={settings.projects_volume_name: {"bind": "/projects", "mode": "rw"}},
            working_dir="/projects",
        )
        result = container.wait(timeout=120)
        output = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")[-16_000:]
        return BuildResult(result.get("StatusCode") == 0, output, int((time.monotonic() - started) * 1000))
    except DockerException as error:
        return BuildResult(False, f"Build runner infrastructure error: {error}", int((time.monotonic() - started) * 1000))
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except DockerException:
                pass
