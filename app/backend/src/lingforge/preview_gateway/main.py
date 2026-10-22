"""Preview origin: exchange an API ticket for an artifact-scoped HttpOnly session."""

from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse

from lingforge.security.preview_ticket import verify_preview_ticket
from lingforge.settings import settings


app = FastAPI(title="LingForge Preview Gateway")


def _artifact_directory(artifact_id: UUID) -> Path:
    """Resolve only a UUID-named immutable artifact below the configured artifact root."""
    target = (settings.artifacts_root / str(artifact_id)).resolve()
    if settings.artifacts_root.resolve() not in target.parents or not target.is_dir():
        raise HTTPException(404, "Preview artifact not found")
    return target


@app.get("/session")
def create_preview_session(ticket: str) -> RedirectResponse:
    """Redeem a short-lived ticket once; redirect removes it from the visible URL/history."""
    try:
        artifact_id = verify_preview_ticket(ticket)
        _artifact_directory(artifact_id)
    except PermissionError:
        raise HTTPException(403, "Invalid preview ticket")
    response = RedirectResponse(f"/preview/{artifact_id}/index.html", status_code=303)
    response.set_cookie("preview_artifact", str(artifact_id), httponly=True, samesite="lax", max_age=300)
    return response


@app.get("/assets/{requested_path:path}")
def serve_legacy_asset(requested_path: str, request: Request) -> FileResponse:
    """Serve absolute /assets links of pre-relative-base artifacts via the session cookie.

    Artifacts built before the template switched to `base: "./"` reference /assets/...
    at the origin root. The HttpOnly artifact cookie scopes those requests to the same
    immutable directory, so one project's session cannot read another project's assets.
    """
    cookie = request.cookies.get("preview_artifact")
    try:
        artifact_id = UUID(cookie or "")
    except ValueError:
        raise HTTPException(403, "Preview session required")
    root = _artifact_directory(artifact_id)
    assets_root = (root / "assets").resolve()
    candidate = (assets_root / requested_path).resolve()
    if assets_root not in candidate.parents or not candidate.is_file():
        raise HTTPException(404, "Preview asset not found")
    return FileResponse(candidate, headers={"Cache-Control": "private, no-store"})


@app.get("/preview/{artifact_id}/{requested_path:path}")
def serve_preview(artifact_id: UUID, requested_path: str, request: Request) -> FileResponse:
    """Serve a generated app only when the browser session is bound to the same artifact."""
    if request.cookies.get("preview_artifact") != str(artifact_id):
        raise HTTPException(403, "Preview session required")
    root = _artifact_directory(artifact_id)
    candidate = (root / requested_path).resolve()
    if root not in candidate.parents and candidate != root:
        raise HTTPException(404, "Preview file not found")
    if not candidate.is_file():
        # Client-side routing still loads the immutable application shell.
        candidate = root / "index.html"
    return FileResponse(candidate, headers={
        "Content-Security-Policy": "default-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors http://localhost:3000 http://127.0.0.1:3000",
        "Cache-Control": "private, no-store",
    })
