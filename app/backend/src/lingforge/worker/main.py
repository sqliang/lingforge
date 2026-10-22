"""Worker state machine for planning, generation, validation, build, repair and promotion."""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from lingforge.agents.builder import generate_source
from lingforge.agents.errors import AgentAborted
from lingforge.agents.planner import plan_contract
from lingforge.agents.titles import generate_project_title
from lingforge.application import repository
from lingforge.execution.build_runner import run_build
from lingforge.execution.validator import validate_source_tree
from lingforge.execution.worktree import cleanup_worktree, create_worktree, promote_worktree
from lingforge.infrastructure.db import transaction


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
WORKER_ID = os.getenv("WORKER_ID", f"worker-{uuid4()}")


class RunCancelled(Exception):
    """The owner requested cancellation; stop at the current stage boundary."""


def _event(run_id: UUID, event_type: str, payload: dict) -> None:
    """Persist a small, user-safe lifecycle event before API streams it via SSE."""
    with transaction() as connection:
        repository.append_event(connection, run_id, event_type, payload)


def _raise_if_cancel_requested(run_id: UUID) -> None:
    """Abort the Run at a stage boundary when the owner asked for cancellation.

    A stage already in flight (one model call or one Docker build) runs to its end;
    cancelling mid-stage would leave the ephemeral worktree in an unknown state.
    """
    if repository.cancel_requested(run_id):
        raise RunCancelled()


def _transition(run_id: UUID, stage: str, event_type: str) -> None:
    _raise_if_cancel_requested(run_id)
    repository.update_run(run_id, status="running", stage=stage)
    _event(run_id, event_type, {"stage": stage})


def _on_file_written(run_id: UUID, path: str, content: str) -> None:
    """Stream one generated file to the workspace as it is written.

    Event persistence must never break the build: a transient database hiccup only
    drops one file notification, the stable promotion path is unaffected.
    """
    try:
        _event(run_id, "builder.file_written", {"path": path, "content": content[:30_000], "bytes": len(content.encode("utf-8"))})
    except Exception:
        logger.warning("Could not persist builder.file_written for %s", path, exc_info=True)


def _contract_for_run(run: dict) -> dict:
    with transaction() as connection:
        row = connection.execute("select content_json from app.build_contracts where id=%s", (run["contract_id"],)).fetchone()
    if not row:
        raise RuntimeError("Run has no approved Build Contract")
    return row["content_json"]


def _persist_plan(run: dict) -> None:
    """Plan a Contract, then either auto-approve it or pause the initial Run for approval.

    While the Planner reasons, a parallel lightweight call replaces the placeholder
    project title with a semantic name; naming is best-effort and never blocks the Run.
    """
    _transition(run["id"], "planning", "planner.started")
    with transaction() as connection:
        project = connection.execute(
            "select original_prompt, owner_id, title from app.projects where id=%s", (run["project_id"],)
        ).fetchone()
    prompt = project["original_prompt"]
    should_abort = lambda: repository.cancel_requested(run["id"])  # noqa: E731
    with ThreadPoolExecutor(max_workers=2) as pool:
        title_future = pool.submit(generate_project_title, prompt) if project["title"] == "New Project" else None
        contract = plan_contract(prompt, should_abort=should_abort)
        if title_future:
            try:
                repository.update_project_title(run["project_id"], title_future.result())
            except Exception:
                logger.warning("Could not generate a semantic project title", exc_info=True)
    # A cancel requested during the long Planner call must win over pausing for approval.
    _raise_if_cancel_requested(run["id"])
    created = repository.create_draft_contract(run["project_id"], str(project["owner_id"]), contract)
    if run.get("mode", "build") == "build":
        # Build mode: approve immediately and requeue the same initial Run for
        # generation. Plan mode below pauses for user review and editing instead.
        repository.auto_approve_contract(run["project_id"], created["id"], run["id"], str(project["owner_id"]))
        return
    repository.update_run(run["id"], status="awaiting_approval", stage="planning")
    with transaction() as connection:
        connection.execute("update app.projects set lifecycle_status='awaiting_approval', updated_at=now() where id=%s", (run["project_id"],))
    _event(run["id"], "contract.ready", {"contractId": str(created["id"]), "version": created["version"]})


def _record_attempt(run_id: UUID, attempt_no: int, result, status: str) -> UUID:
    """Store bounded build diagnostics for the owner and potential one-time Repair."""
    attempt_id = uuid4()
    with transaction() as connection:
        connection.execute(
            """insert into app.build_attempts (id, run_id, attempt_no, status, duration_ms, diagnostics_ref, completed_at)
               values (%s,%s,%s,%s,%s,%s,now())""",
            (attempt_id, run_id, attempt_no, status, result.duration_ms, result.log[-16_000:]),
        )
    return attempt_id


def _record_assistant_message(run: dict, content: str) -> None:
    """Persist the user-visible assistant summary so a page refresh keeps chat history."""
    with transaction() as connection:
        connection.execute(
            "insert into app.messages (id, project_id, run_id, role, visible_content) values (%s,%s,%s,'assistant',%s)",
            (uuid4(), run["project_id"], run["id"], content[:2000]),
        )


def _promote(run: dict, worktree, build_id: UUID, summary: str) -> None:
    """Create a candidate commit and atomically advance product state only after success.

    Artifact copy/upload is intentionally a separate pre-transaction Saga step. The local
    P0 preview reads the immutable `dist` directory by build id; a later Storage adapter can
    replace that copy without changing promotion semantics.
    """
    from shutil import copytree
    from lingforge.settings import settings

    _transition(run["id"], "committing", "commit.started")
    commit_sha = promote_worktree(run["project_id"], worktree, "Generate application")
    artifact_id = uuid4()
    artifact_dir = settings.artifacts_root / str(artifact_id)
    copytree(worktree / "dist", artifact_dir)
    _transition(run["id"], "promoting", "preview.uploaded")
    version_id = uuid4()
    with transaction() as connection:
        connection.execute("select pg_advisory_xact_lock(hashtext(%s))", (str(run["project_id"]),))
        connection.execute("update app.build_attempts set status='succeeded', source_commit_sha=%s where id=%s", (commit_sha, build_id))
        connection.execute(
            """insert into app.preview_artifacts (id, build_id, storage_key, integrity_hash, manifest_json, state)
               values (%s,%s,%s,%s,'{}'::jsonb,'ready')""",
            (artifact_id, build_id, str(artifact_id), commit_sha),
        )
        connection.execute(
            """insert into app.project_versions (id, project_id, commit_sha, parent_version_id, build_id, template_version, message, origin_kind)
               select %s,%s,%s,stable_version_id,%s,template_version,'Generated application',%s from app.projects where id=%s""",
            (version_id, run["project_id"], commit_sha, build_id, run["kind"], run["project_id"]),
        )
        connection.execute("update app.projects set stable_version_id=%s, lifecycle_status='ready', updated_at=now() where id=%s", (version_id, run["project_id"]))
        connection.execute("update app.agent_runs set status='completed', stage='promoting', completed_at=now() where id=%s", (run["id"],))
        # The assistant summary lands in the same transaction as promotion: history is
        # only visible when the stable pointer actually advanced.
        connection.execute(
            "insert into app.messages (id, project_id, run_id, role, visible_content) values (%s,%s,%s,'assistant',%s)",
            (uuid4(), run["project_id"], run["id"], f"{summary.strip()[:1800]}\n\nCommit: {commit_sha[:8]}"),
        )
        repository.append_event(connection, run["id"], "version.promoted", {"versionId": str(version_id), "artifactId": str(artifact_id)})


def process_run(run: dict) -> None:
    """Process one leased Run; every failure preserves the current stable pointer."""
    worktree = None
    try:
        if run["kind"] == "initial" and run["stage"] == "planning":
            _persist_plan(run)
            return
        contract = _contract_for_run(run)
        worktree = create_worktree(run["project_id"], run["id"])
        on_file_written = lambda path, content: _on_file_written(run["id"], path, content)  # noqa: E731
        # Polled between Builder tool calls so a stop request unwinds the model session
        # instead of waiting for the whole generation stage to finish.
        should_abort = lambda: repository.cancel_requested(run["id"])  # noqa: E731
        instruction = repository.get_run_instruction(run["id"]) if run["kind"] != "initial" else None
        references = repository.get_run_references(run["id"]) if run["kind"] != "initial" else []
        _transition(run["id"], "generating", "builder.started")
        summary = generate_source(worktree, contract, on_file_written=on_file_written, should_abort=should_abort, instruction=instruction, references=references)
        _transition(run["id"], "validating", "validation.started")
        validate_source_tree(worktree)
        _transition(run["id"], "typechecking", "build.started")
        result = run_build(worktree)
        build_id = _record_attempt(run["id"], 1, result, "succeeded" if result.succeeded else "failed")
        if not result.succeeded:
            _transition(run["id"], "repairing", "repair.started")
            with transaction() as connection:
                connection.execute("update app.agent_runs set repair_attempts=1 where id=%s", (run["id"],))
            summary = generate_source(worktree, contract, result.log, on_file_written=on_file_written, should_abort=should_abort, instruction=instruction)
            validate_source_tree(worktree)
            _transition(run["id"], "typechecking", "build.retry_started")
            repaired = run_build(worktree)
            build_id = _record_attempt(run["id"], 2, repaired, "succeeded" if repaired.succeeded else "failed")
            if not repaired.succeeded:
                raise RuntimeError("Repair could not produce a build: " + repaired.log[-1000:])
        _promote(run, worktree, build_id, summary)
    except (RunCancelled, AgentAborted):
        # Cooperative cancellation: keep diagnostics, clean the worktree below, and
        # leave the stable pointer exactly where it was.
        repository.update_run(run["id"], status="cancelled", stage=None)
        _event(run["id"], "run.cancelled", {"stage": run["stage"]})
        _record_assistant_message(run, "本次生成已取消，稳定版本未受影响。")
    except Exception as error:
        if repository.cancel_requested(run["id"]):
            # The abort watcher closes the model client mid-request; the interrupted
            # call surfaces as a provider/transport error, but the owner's cancel
            # request — not the transport error — decides the terminal state.
            repository.update_run(run["id"], status="cancelled", stage=None)
            _event(run["id"], "run.cancelled", {"stage": run["stage"]})
            _record_assistant_message(run, "本次生成已取消，稳定版本未受影响。")
            return
        # No unexpected provider, filesystem, or Docker exception may leak a partial
        # candidate into the stable pointer. Keep diagnostics bounded and user-safe.
        logger.exception("Run %s failed", run["id"])
        repository.update_run(run["id"], status="failed", error_code="run_failed", error_message=str(error)[:1000])
        _event(run["id"], "run.failed", {"code": "run_failed", "message": str(error)[:1000]})
        _record_assistant_message(run, f"运行失败：{str(error)[:500]}")
    finally:
        if worktree:
            cleanup_worktree(worktree)


def main() -> None:
    """Poll the Postgres-backed queue; leases prevent duplicate work across Worker replicas."""
    while True:
        run = repository.claim_next_run(WORKER_ID)
        if run:
            process_run(run)
        else:
            time.sleep(1)


if __name__ == "__main__":
    main()
