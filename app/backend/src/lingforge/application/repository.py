"""Product persistence operations with explicit ownership and event sequencing."""

import json
from datetime import timezone
from typing import Any
from uuid import UUID, uuid4
from psycopg import Connection
from lingforge.infrastructure.db import transaction


def validate_contract(content: dict[str, Any]) -> None:
    """Perform the inexpensive Contract boundary checks before it reaches a Run.

    Full JSON Schema validation belongs here rather than in an agent prompt: an approved
    Contract is a product input and can be edited by users as well as produced by Planner.
    The Planner calls this same function to detect unusable model output before persistence.
    """
    required = {"title", "summary", "features", "components", "nonGoals", "acceptanceCriteria"}
    missing = required - set(content)
    if missing:
        raise ValueError(f"Build Contract is missing fields: {', '.join(sorted(missing))}")
    if not isinstance(content["features"], list) or not 1 <= len(content["features"]) <= 12:
        raise ValueError("Build Contract must contain between 1 and 12 features")
    if not isinstance(content["components"], list) or not content["components"]:
        raise ValueError("Build Contract must define at least one component")


def _row_to_project(row: dict[str, Any]) -> dict[str, Any]:
    project = {key: row[key] for key in ("id", "title", "original_prompt", "lifecycle_status", "stable_version_id")}
    # Present on list responses only; the workspace derives Run state from the runs query.
    project["latest_run_status"] = row.get("latest_run_status")
    return project


def create_project(owner_id: str, prompt: str) -> dict[str, Any]:
    """Persist an initial project record; repository provisioning follows in the service layer.

    The title starts as a placeholder; the Worker replaces it with a semantic, model
    generated name in parallel with planning, so project creation never waits on a model.
    """
    project_id = uuid4()
    with transaction() as connection:
        row = connection.execute(
            """insert into app.projects (id, owner_id, title, original_prompt, lifecycle_status)
               values (%s, %s, %s, %s, 'draft') returning *""",
            (project_id, owner_id, "New Project", prompt),
        ).fetchone()
    return _row_to_project(row)


def update_project_title(project_id: UUID, title: str) -> None:
    """Replace the placeholder title with the Worker's semantic name."""
    with transaction() as connection:
        connection.execute("update app.projects set title=%s, updated_at=now() where id=%s", (title[:60], project_id))


def list_projects(owner_id: str) -> list[dict[str, Any]]:
    """List owner projects with the newest Run's status for list-level progress badges."""
    with transaction() as connection:
        rows = connection.execute(
            """select p.id, p.title, p.original_prompt, p.lifecycle_status, p.stable_version_id,
                 (select r.status from app.agent_runs r where r.project_id = p.id
                  order by r.created_at desc limit 1) as latest_run_status
               from app.projects p where p.owner_id=%s and p.archived_at is null order by p.updated_at desc""",
            (owner_id,),
        ).fetchall()
    return [_row_to_project(row) for row in rows]


def get_project(project_id: UUID, owner_id: str) -> dict[str, Any]:
    """Read one project projection after an explicit owner check."""
    with transaction() as connection:
        return _row_to_project(owned_project(connection, project_id, owner_id))


def stable_artifact_id(project_id: UUID, owner_id: str) -> UUID:
    """Find the ready artifact behind the owner's stable pointer, never a candidate build."""
    with transaction() as connection:
        owned_project(connection, project_id, owner_id)
        row = connection.execute(
            """select artifact.id from app.projects project
               join app.project_versions version on version.id = project.stable_version_id
               join app.preview_artifacts artifact on artifact.build_id = version.build_id
               where project.id=%s and artifact.state='ready'""",
            (project_id,),
        ).fetchone()
    if not row:
        raise ValueError("No stable preview is available")
    return row["id"]


def owned_project(connection: Connection, project_id: UUID, owner_id: str) -> dict[str, Any]:
    row = connection.execute("select * from app.projects where id=%s and owner_id=%s", (project_id, owner_id)).fetchone()
    if not row:
        raise PermissionError("Project not found")
    return row


def create_run(
    project_id: UUID,
    owner_id: str,
    kind: str,
    request_id: UUID,
    instruction: str | None,
    references: list[dict[str, Any]] | None = None,
    mode: str = "build",
) -> dict[str, Any]:
    """Create one idempotent Run. The partial index prevents concurrent writers."""
    references = references or []
    if any(".." in str(item.get("path", "")).split("/") for item in references):
        raise ValueError("Reference paths may not escape the project")
    if mode not in {"build", "plan"}:
        raise ValueError("Run mode must be 'build' or 'plan'")
    with transaction() as connection:
        project = owned_project(connection, project_id, owner_id)
        existing = connection.execute(
            "select * from app.agent_runs where project_id=%s and request_id=%s", (project_id, request_id)
        ).fetchone()
        if existing:
            return existing
        contract = connection.execute(
            "select id from app.build_contracts where project_id=%s and status='approved'", (project_id,)
        ).fetchone()
        if kind != "initial" and not contract:
            raise ValueError("An approved Build Contract is required")
        run_id = uuid4()
        connection.execute(
            """insert into app.agent_runs
              (id, project_id, kind, request_id, contract_id, base_version_id, status, stage, mode)
              values (%s,%s,%s,%s,%s,%s,'queued',%s,%s)""",
            (run_id, project_id, kind, request_id, contract["id"] if contract else None, project["stable_version_id"], "planning" if kind == "initial" else "generating", mode),
        )
        if instruction:
            # References are part of the owner's instruction: the visible text carries a
            # human-readable note, while the structured payload rides in `summary` so the
            # Worker can rebuild precise excerpts without a schema migration.
            note = ""
            if references:
                labels = [
                    f"{item['path']}" + (f" (L{item['start_line']}-{item['end_line']})" if item.get("start_line") else "")
                    for item in references
                ]
                note = "\n\n引用: " + ", ".join(labels)
            connection.execute(
                "insert into app.messages (id, project_id, run_id, role, visible_content, summary) values (%s,%s,%s,'user',%s,%s)",
                (uuid4(), project_id, run_id, instruction + note, json.dumps(references) if references else None),
            )
        append_event(connection, run_id, "run.queued", {"stage": "planning" if kind == "initial" else "generating"})
        return connection.execute("select * from app.agent_runs where id=%s", (run_id,)).fetchone()


def request_cancel(project_id: UUID, run_id: UUID, owner_id: str) -> dict[str, Any]:
    """Request cooperative cancellation of one active Run.

    Runs not held by a Worker (queued, awaiting_approval) finish cancellation inside
    this transaction. A claimed/running Run only records the request; the Worker
    observes it at the next stage boundary and performs the terminal transition.
    The stable pointer is never touched by cancellation.
    """
    with transaction() as connection:
        owned_project(connection, project_id, owner_id)
        run = connection.execute(
            "select * from app.agent_runs where id=%s and project_id=%s", (run_id, project_id)
        ).fetchone()
        if not run:
            raise PermissionError("Run not found")
        if run["status"] in {"queued", "awaiting_approval"}:
            row = connection.execute(
                """update app.agent_runs set status='cancelled', stage=null,
                     cancel_requested_at=now(), completed_at=now()
                   where id=%s returning *""",
                (run_id,),
            ).fetchone()
            append_event(connection, run_id, "run.cancelled", {"stage": run["stage"]})
            return row
        if run["status"] in {"claimed", "running"}:
            return connection.execute(
                """update app.agent_runs set status='cancelling', cancel_requested_at=now()
                   where id=%s returning *""",
                (run_id,),
            ).fetchone()
        raise ValueError(f"Run cannot be cancelled from status {run['status']}")


def cancel_requested(run_id: UUID) -> bool:
    """Read the durable cancel flag; the Worker polls this only at stage boundaries."""
    with transaction() as connection:
        row = connection.execute("select cancel_requested_at from app.agent_runs where id=%s", (run_id,)).fetchone()
        return bool(row and row["cancel_requested_at"])


def get_run_instruction(run_id: UUID) -> str | None:
    """Return the newest user instruction attached to a Run, if any."""
    with transaction() as connection:
        row = connection.execute(
            "select visible_content from app.messages where run_id=%s and role='user' order by created_at desc limit 1",
            (run_id,),
        ).fetchone()
        return row["visible_content"] if row else None


def get_run_references(run_id: UUID) -> list[dict[str, Any]]:
    """Return the structured code references attached to a Run's instruction, if any."""
    with transaction() as connection:
        row = connection.execute(
            """select summary from app.messages
               where run_id=%s and role='user' and summary is not null
               order by created_at desc limit 1""",
            (run_id,),
        ).fetchone()
    if not row:
        return []
    try:
        return json.loads(row["summary"])
    except (TypeError, json.JSONDecodeError):
        return []


def list_versions(project_id: UUID, owner_id: str) -> list[dict[str, Any]]:
    """List promoted versions newest first, with stability and preview availability flags."""
    with transaction() as connection:
        owned_project(connection, project_id, owner_id)
        return connection.execute(
            """select v.id, v.commit_sha, v.message, v.origin_kind, v.created_at,
                 (p.stable_version_id = v.id) as is_stable,
                 exists(select 1 from app.preview_artifacts a where a.build_id = v.build_id and a.state='ready') as has_artifact
               from app.project_versions v join app.projects p on p.id = v.project_id
               where v.project_id=%s order by v.created_at desc""",
            (project_id,),
        ).fetchall()


def get_version(project_id: UUID, version_id: UUID, owner_id: str) -> dict[str, Any]:
    """Read one version row after an explicit owner check."""
    with transaction() as connection:
        owned_project(connection, project_id, owner_id)
        row = connection.execute(
            "select * from app.project_versions where id=%s and project_id=%s", (version_id, project_id)
        ).fetchone()
        if not row:
            raise PermissionError("Version not found")
        return row


def artifact_id_for_version(project_id: UUID, version_id: UUID, owner_id: str) -> UUID:
    """Resolve the ready preview artifact built for one version, if one exists."""
    version = get_version(project_id, version_id, owner_id)
    with transaction() as connection:
        artifact = connection.execute(
            "select id from app.preview_artifacts where build_id=%s and state='ready'", (version["build_id"],)
        ).fetchone()
    if not artifact:
        raise ValueError("No preview artifact exists for this version")
    return artifact["id"]


def list_messages(project_id: UUID, owner_id: str) -> list[dict[str, Any]]:
    """List the conversation visible to the owner, oldest first."""
    with transaction() as connection:
        owned_project(connection, project_id, owner_id)
        return connection.execute(
            "select id, run_id, role, visible_content, created_at from app.messages where project_id=%s order by created_at",
            (project_id,),
        ).fetchall()


def list_contracts(project_id: UUID, owner_id: str) -> list[dict[str, Any]]:
    """List immutable versions; ownership is checked before exposing Contract contents."""
    with transaction() as connection:
        owned_project(connection, project_id, owner_id)
        return connection.execute(
            """select id, project_id, version, content_json, status
               from app.build_contracts where project_id=%s order by version desc""",
            (project_id,),
        ).fetchall()


def create_draft_contract(project_id: UUID, owner_id: str, content: dict[str, Any]) -> dict[str, Any]:
    """Append (never overwrite) a user-editable Contract version.

    The version allocation is protected by the project row lock. It is a short database
    transaction and never includes model execution, preserving the Worker lease invariant.
    """
    validate_contract(content)
    with transaction() as connection:
        owned_project(connection, project_id, owner_id)
        connection.execute("select id from app.projects where id=%s for update", (project_id,))
        version = connection.execute(
            "select coalesce(max(version), 0) + 1 as next_version from app.build_contracts where project_id=%s",
            (project_id,),
        ).fetchone()["next_version"]
        row = connection.execute(
            """insert into app.build_contracts (id, project_id, version, content_json, status, created_by)
               values (%s,%s,%s,%s::jsonb,'draft',%s) returning id, project_id, version, content_json, status""",
            (uuid4(), project_id, version, json.dumps(content), owner_id),
        ).fetchone()
        return row


def append_event(connection: Connection, run_id: UUID, event_type: str, payload: dict[str, Any]) -> int:
    """Allocate a monotonic event sequence in the same short transaction as its write."""
    row = connection.execute(
        "update app.agent_runs set next_event_sequence=next_event_sequence+1 where id=%s returning next_event_sequence-1 as sequence",
        (run_id,),
    ).fetchone()
    sequence = row["sequence"]
    connection.execute(
        """insert into app.run_events (id, run_id, sequence, type, payload_json)
           values (%s,%s,%s,%s,%s::jsonb)""",
        (uuid4(), run_id, sequence, event_type, json.dumps(payload)),
    )
    return sequence


def get_run(project_id: UUID, run_id: UUID, owner_id: str) -> dict[str, Any]:
    with transaction() as connection:
        owned_project(connection, project_id, owner_id)
        row = connection.execute("select * from app.agent_runs where id=%s and project_id=%s", (run_id, project_id)).fetchone()
    if not row:
        raise PermissionError("Run not found")
    return row


def list_runs(project_id: UUID, owner_id: str) -> list[dict[str, Any]]:
    """Return newest first so a workspace reopened after navigation finds its active Run."""
    with transaction() as connection:
        owned_project(connection, project_id, owner_id)
        return connection.execute(
            "select * from app.agent_runs where project_id=%s order by created_at desc", (project_id,)
        ).fetchall()


def latest_build_log(project_id: UUID, owner_id: str) -> dict[str, Any] | None:
    """Expose only the bounded deterministic diagnostic, never raw agent/tool traces."""
    with transaction() as connection:
        owned_project(connection, project_id, owner_id)
        return connection.execute(
            """select attempt_no, status, diagnostics_ref as diagnostics
               from app.build_attempts attempt
               join app.agent_runs run on run.id=attempt.run_id
               where run.project_id=%s order by attempt.started_at desc limit 1""",
            (project_id,),
        ).fetchone()


def events_after(project_id: UUID, run_id: UUID, owner_id: str, sequence: int) -> list[dict[str, Any]]:
    with transaction() as connection:
        owned_project(connection, project_id, owner_id)
        return connection.execute(
            "select sequence, type, schema_version, payload_json, created_at from app.run_events where run_id=%s and sequence>%s order by sequence",
            (run_id, sequence),
        ).fetchall()


def approve_contract(project_id: UUID, contract_id: UUID, owner_id: str) -> dict[str, Any]:
    """Approve a draft and requeue the single waiting initial Run atomically."""
    with transaction() as connection:
        owned_project(connection, project_id, owner_id)
        connection.execute("update app.build_contracts set status='superseded', superseded_at=now() where project_id=%s and status='approved'", (project_id,))
        contract = connection.execute(
            """update app.build_contracts set status='approved', approved_at=now()
               where id=%s and project_id=%s and status='draft' returning *""", (contract_id, project_id)
        ).fetchone()
        if not contract:
            raise ValueError("Draft contract not found")
        run = connection.execute(
            """update app.agent_runs set contract_id=%s, status='queued', stage='generating', lease_expires_at=null
               where project_id=%s and kind='initial' and status='awaiting_approval' returning *""",
            (contract_id, project_id),
        ).fetchone()
        if run:
            append_event(connection, run["id"], "run.queued", {"stage": "generating"})
        connection.execute("update app.projects set lifecycle_status='ready', updated_at=now() where id=%s", (project_id,))
        return contract


def auto_approve_contract(project_id: UUID, contract_id: UUID, run_id: UUID, owner_id: str) -> None:
    """Approve the fresh draft and requeue the still-running planning Run atomically.

    The manual API approval path (`approve_contract`) finds the initial Run paused at
    `awaiting_approval`; the Worker's auto-approve flow instead holds it at `running`,
    so requeueing must target the Run by id rather than by lifecycle state.
    """
    with transaction() as connection:
        owned_project(connection, project_id, owner_id)
        connection.execute(
            "update app.build_contracts set status='superseded', superseded_at=now() where project_id=%s and status='approved'",
            (project_id,),
        )
        approved = connection.execute(
            """update app.build_contracts set status='approved', approved_at=now()
               where id=%s and project_id=%s and status='draft' returning *""",
            (contract_id, project_id),
        ).fetchone()
        if not approved:
            raise ValueError("Draft contract not found")
        run = connection.execute(
            """update app.agent_runs set contract_id=%s, status='queued', stage='generating', lease_expires_at=null
               where id=%s and status='running' returning *""",
            (contract_id, run_id),
        ).fetchone()
        if not run:
            raise ValueError("Planning run is no longer active")
        append_event(connection, run_id, "contract.ready", {"contractId": str(contract_id), "version": approved["version"]})
        append_event(connection, run_id, "run.queued", {"stage": "generating"})
        connection.execute("update app.projects set lifecycle_status='ready', updated_at=now() where id=%s", (project_id,))


def claim_next_run(worker_id: str) -> dict[str, Any] | None:
    """Lease one queued Run without holding a transaction across model or Docker work."""
    with transaction() as connection:
        row = connection.execute(
            """with candidate as (
                 select id from app.agent_runs where status='queued' order by created_at for update skip locked limit 1
               ) update app.agent_runs r set status='claimed', lease_expires_at=now()+interval '2 minutes', started_at=coalesce(started_at, now())
               from candidate where r.id=candidate.id returning r.*"""
        ).fetchone()
        if row:
            append_event(connection, row["id"], "run.claimed", {"leaseExpiresAt": row["lease_expires_at"].isoformat() if row["lease_expires_at"] else None})
        return row


def update_run(run_id: UUID, *, status: str, stage: str | None = None, error_code: str | None = None, error_message: str | None = None) -> None:
    with transaction() as connection:
        connection.execute(
            """update app.agent_runs set status=%s, stage=%s, error_code=%s, error_message=%s,
                 completed_at=case when %s in ('completed','failed','cancelled') then now() else completed_at end where id=%s""",
            (status, stage, error_code, error_message, status, run_id),
        )


def event_envelope(run_id: UUID, row: dict[str, Any]) -> dict[str, Any]:
    return {"schemaVersion": row["schema_version"], "runId": str(run_id), "sequence": row["sequence"], "at": row["created_at"].astimezone(timezone.utc).isoformat(), "payload": row["payload_json"]}
