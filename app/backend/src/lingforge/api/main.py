"""FastAPI control plane: authenticated commands, snapshots, and persisted SSE."""

import json
import time
from pathlib import Path
from uuid import UUID
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from lingforge.api.schemas import (
    ContractResponse,
    ContractUpdateRequest,
    CreateProjectRequest,
    CreateRunRequest,
    BuildLogResponse,
    MessageResponse,
    ProjectFileResponse,
    PreviewTicketResponse,
    ProjectResponse,
    RunResponse,
    VersionResponse,
)
from lingforge.application import repository, version_files
from lingforge.security.auth import CurrentUserId
from lingforge.security.preview_ticket import issue_preview_ticket
from lingforge.settings import settings

app = FastAPI(title="LingForge API", version="0.1.0")
# Local workbench: any origin may call the API. Authentication is per-request bearer
# tokens (no cookies, allow_credentials stays False), so a wildcard origin does not
# widen the credential surface; ownership is still enforced on every endpoint.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
)


def run_response(row: dict) -> RunResponse:
    return RunResponse(id=row["id"], project_id=row["project_id"], kind=row["kind"], status=row["status"], stage=row["stage"], repair_attempts=row["repair_attempts"], mode=row.get("mode", "build"), error_code=row["error_code"], error_message=row["error_message"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/projects", response_model=ProjectResponse, status_code=201)
def create_project(payload: CreateProjectRequest, user_id: CurrentUserId) -> dict:
    project = repository.create_project(user_id, payload.prompt)
    # Git provisioning is deterministic and deliberately happens outside the DB transaction.
    project_dir = settings.projects_root / str(project["id"])
    project_dir.mkdir(parents=True, exist_ok=True)
    return project


@app.get("/v1/projects", response_model=list[ProjectResponse])
def get_projects(user_id: CurrentUserId) -> list[dict]:
    return repository.list_projects(user_id)


@app.get("/v1/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: UUID, user_id: CurrentUserId) -> dict:
    try:
        return repository.get_project(project_id, user_id)
    except PermissionError:
        raise HTTPException(404, "Project not found")


@app.get("/v1/projects/{project_id}/preview-ticket", response_model=PreviewTicketResponse)
def create_preview_ticket(project_id: UUID, user_id: CurrentUserId) -> dict[str, str]:
    """Authorize stable preview access and return a one-time bootstrap URL, not a file URL."""
    try:
        artifact_id = repository.stable_artifact_id(project_id, user_id)
        ticket, expires_at = issue_preview_ticket(artifact_id)
        return {"bootstrap_url": f"{settings.preview_origin}/session?ticket={ticket}", "expires_at": expires_at.isoformat()}
    except PermissionError:
        raise HTTPException(404, "Project not found")
    except ValueError:
        raise HTTPException(404, "No stable preview is available")


@app.post("/v1/projects/{project_id}/runs", response_model=RunResponse, status_code=202)
def start_run(project_id: UUID, payload: CreateRunRequest, user_id: CurrentUserId) -> RunResponse:
    try:
        references = [item.model_dump() for item in payload.references]
        return run_response(repository.create_run(project_id, user_id, payload.kind, payload.request_id, payload.instruction, references, payload.mode))
    except PermissionError:
        raise HTTPException(404, "Project not found")
    except ValueError as error:
        raise HTTPException(409, str(error))


@app.get("/v1/projects/{project_id}/versions", response_model=list[VersionResponse])
def get_versions(project_id: UUID, user_id: CurrentUserId) -> list[dict]:
    """List promoted versions for the version switcher; newest first."""
    try:
        return repository.list_versions(project_id, user_id)
    except PermissionError:
        raise HTTPException(404, "Project not found")


@app.get("/v1/projects/{project_id}/versions/{version_id}/files", response_model=list[str])
def get_version_files(project_id: UUID, version_id: UUID, user_id: CurrentUserId) -> list[str]:
    """List tracked files at one historical commit, read from the Git object store."""
    try:
        version = repository.get_version(project_id, version_id, user_id)
        return version_files.list_files(project_id, version["commit_sha"])
    except PermissionError:
        raise HTTPException(404, "Version not found")
    except version_files.VersionFilesError as error:
        raise HTTPException(404, str(error))


@app.get("/v1/projects/{project_id}/versions/{version_id}/files/{path:path}", response_model=ProjectFileResponse)
def get_version_file(project_id: UUID, version_id: UUID, path: str, user_id: CurrentUserId) -> dict[str, str]:
    """Read one bounded file at one historical commit."""
    try:
        version = repository.get_version(project_id, version_id, user_id)
        return {"path": path, "content": version_files.read_file(project_id, version["commit_sha"], path)}
    except PermissionError:
        raise HTTPException(404, "Version not found")
    except version_files.VersionFilesError as error:
        raise HTTPException(404, str(error))


@app.get("/v1/projects/{project_id}/versions/{version_id}/preview-ticket", response_model=PreviewTicketResponse)
def create_version_preview_ticket(project_id: UUID, version_id: UUID, user_id: CurrentUserId) -> dict[str, str]:
    """Authorize preview of the artifact built for one historical version."""
    try:
        artifact_id = repository.artifact_id_for_version(project_id, version_id, user_id)
        ticket, expires_at = issue_preview_ticket(artifact_id)
        return {"bootstrap_url": f"{settings.preview_origin}/session?ticket={ticket}", "expires_at": expires_at.isoformat()}
    except PermissionError:
        raise HTTPException(404, "Version not found")
    except ValueError:
        raise HTTPException(404, "No preview artifact exists for this version")


@app.get("/v1/projects/{project_id}/messages", response_model=list[MessageResponse])
def get_messages(project_id: UUID, user_id: CurrentUserId) -> list[dict]:
    """Return the persisted conversation (user instructions and assistant summaries)."""
    try:
        return repository.list_messages(project_id, user_id)
    except PermissionError:
        raise HTTPException(404, "Project not found")


@app.get("/v1/projects/{project_id}/contracts", response_model=list[ContractResponse])
def get_contracts(project_id: UUID, user_id: CurrentUserId) -> list[dict]:
    """Return immutable Contract versions visible to the project owner."""
    try:
        return repository.list_contracts(project_id, user_id)
    except PermissionError:
        raise HTTPException(404, "Project not found")


@app.put("/v1/projects/{project_id}/contracts", response_model=ContractResponse, status_code=201)
def create_contract(project_id: UUID, payload: ContractUpdateRequest, user_id: CurrentUserId) -> dict:
    """Create a new editable Contract version after server-side schema validation."""
    try:
        return repository.create_draft_contract(project_id, user_id, payload.content)
    except PermissionError:
        raise HTTPException(404, "Project not found")
    except ValueError as error:
        raise HTTPException(422, str(error))


@app.post("/v1/projects/{project_id}/runs/{run_id}/cancel", response_model=RunResponse)
def cancel_run(project_id: UUID, run_id: UUID, user_id: CurrentUserId) -> RunResponse:
    """Request cooperative cancellation; terminal state arrives via the SSE stream."""
    try:
        return run_response(repository.request_cancel(project_id, run_id, user_id))
    except PermissionError:
        raise HTTPException(404, "Run not found")
    except ValueError as error:
        raise HTTPException(409, str(error))


@app.get("/v1/projects/{project_id}/runs/{run_id}", response_model=RunResponse)
def get_run(project_id: UUID, run_id: UUID, user_id: CurrentUserId) -> RunResponse:
    try:
        return run_response(repository.get_run(project_id, run_id, user_id))
    except PermissionError:
        raise HTTPException(404, "Run not found")


@app.get("/v1/projects/{project_id}/runs", response_model=list[RunResponse])
def get_runs(project_id: UUID, user_id: CurrentUserId) -> list[RunResponse]:
    """Return Run snapshots; SSE supplies the detailed event stream for the active one."""
    try:
        return [run_response(row) for row in repository.list_runs(project_id, user_id)]
    except PermissionError:
        raise HTTPException(404, "Project not found")


@app.get("/v1/projects/{project_id}/build-log", response_model=BuildLogResponse | None)
def get_build_log(project_id: UUID, user_id: CurrentUserId) -> dict | None:
    try:
        return repository.latest_build_log(project_id, user_id)
    except PermissionError:
        raise HTTPException(404, "Project not found")


def _stable_file_path(project_id: UUID, path: str, owner_id: str) -> tuple[Path, str]:
    """Authorize first, then resolve a stable repository path without traversal."""
    repository.get_project(project_id, owner_id)
    repository_root = (settings.projects_root / str(project_id) / "repository").resolve()
    candidate = (repository_root / path).resolve()
    if repository_root not in candidate.parents or not candidate.is_file():
        raise HTTPException(404, "File not found")
    return candidate, candidate.relative_to(repository_root).as_posix()


@app.get("/v1/projects/{project_id}/files", response_model=list[str])
def get_stable_files(project_id: UUID, user_id: CurrentUserId) -> list[str]:
    """List only validated files belonging to the stable repository version."""
    repository.get_project(project_id, user_id)
    repository_root = settings.projects_root / str(project_id) / "repository"
    if not repository_root.is_dir():
        return []
    return sorted(
        path.relative_to(repository_root).as_posix()
        for path in repository_root.rglob("*")
        if path.is_file() and ".git" not in path.parts and "node_modules" not in path.parts
    )


@app.get("/v1/projects/{project_id}/files/{path:path}", response_model=ProjectFileResponse)
def get_stable_file(project_id: UUID, path: str, user_id: CurrentUserId) -> dict[str, str]:
    """Read a bounded UTF-8 stable source file selected by the workspace explorer."""
    candidate, relative_path = _stable_file_path(project_id, path, user_id)
    if candidate.stat().st_size > 200_000:
        raise HTTPException(413, "File is too large to display")
    return {"path": relative_path, "content": candidate.read_text(encoding="utf-8")}


@app.post("/v1/projects/{project_id}/contracts/{contract_id}/approve")
def approve_contract(project_id: UUID, contract_id: UUID, user_id: CurrentUserId) -> dict:
    try:
        return repository.approve_contract(project_id, contract_id, user_id)
    except PermissionError:
        raise HTTPException(404, "Project not found")
    except ValueError as error:
        raise HTTPException(409, str(error))


@app.get("/v1/projects/{project_id}/runs/{run_id}/events")
def stream_events(
    project_id: UUID,
    run_id: UUID,
    user_id: CurrentUserId,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Replay persisted events, then poll for appended events until a terminal Run state.

    Deliberately a sync generator: FastAPI runs it in a worker thread, so the database
    polling below never blocks the ASGI event loop that serves every other request.
    """
    try:
        last_sequence = int(last_event_id or 0)
        repository.get_run(project_id, run_id, user_id)
    except (ValueError, PermissionError):
        raise HTTPException(404, "Run not found")

    def generate():
        sequence = last_sequence
        while True:
            for row in repository.events_after(project_id, run_id, user_id, sequence):
                sequence = row["sequence"]
                yield f"id: {sequence}\nevent: {row['type']}\ndata: {json.dumps(repository.event_envelope(run_id, row))}\n\n"
            run = repository.get_run(project_id, run_id, user_id)
            if run["status"] in {"completed", "failed", "cancelled"}:
                return
            yield ": heartbeat\n\n"
            time.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})
