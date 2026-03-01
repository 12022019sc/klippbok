"""Settings router -- read and update project settings.

Endpoints:
    GET /settings/       -- Return current project settings.
    PUT /settings/       -- Update project settings (project_dir, active_profile).
    DELETE /settings/project -- Delete project data (.klippbok/) and clear active project.

The PUT endpoint sets app.state.project_dir at runtime, enabling the
project picker flow where users select a project from the web UI.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from klippbok.api.models import SettingsResponse, SettingsUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/", response_model=SettingsResponse)
def get_settings(request: Request) -> SettingsResponse:
    """Return current project settings.

    Returns project_dir as None when no project is active (user hasn't
    selected one yet). The frontend uses this to show the project picker.

    Args:
        request: FastAPI request (used to access app.state.project_dir).

    Returns:
        SettingsResponse with project_dir and active_profile.
    """
    from klippbok.services.project_service import load_manifest

    project_dir: Path | None = request.app.state.project_dir

    if project_dir is None:
        return SettingsResponse(project_dir=None, active_profile=None)

    active_profile: str | None = None
    try:
        manifest = load_manifest(project_dir)
        if manifest:
            active_profile = manifest.get("active_profile")
    except Exception as exc:
        logger.warning("Could not read active_profile from manifest: %s", exc)

    return SettingsResponse(
        project_dir=str(project_dir),
        active_profile=active_profile,
    )


@router.put("/", response_model=SettingsResponse)
def update_settings(body: SettingsUpdate, request: Request) -> SettingsResponse:
    """Update project settings.

    When project_dir is provided, validates the path exists (as a directory),
    creates the .klippbok/ subdirectory if needed, and sets it as the active
    project on app.state. All subsequent API calls will use this project.

    Args:
        body: Fields to update (project_dir, active_profile).
        request: FastAPI request (used to access app.state.project_dir).

    Returns:
        SettingsResponse reflecting the current state after update.
    """
    # Update project_dir if provided
    if body.project_dir is not None:
        new_dir = Path(body.project_dir).resolve()
        if not new_dir.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Directory does not exist: {new_dir}",
            )
        if not new_dir.is_dir():
            raise HTTPException(
                status_code=400,
                detail=f"Path is not a directory: {new_dir}",
            )
        # Create .klippbok/ subdirectory for thumbnails, manifest, etc.
        klippbok_dir = new_dir / ".klippbok"
        klippbok_dir.mkdir(exist_ok=True)

        request.app.state.project_dir = new_dir
        logger.info("Project directory set to: %s", new_dir)

    project_dir: Path | None = request.app.state.project_dir

    if project_dir is None:
        return SettingsResponse(project_dir=None, active_profile=body.active_profile)

    # Read current profile from manifest
    from klippbok.services.project_service import load_manifest

    active_profile: str | None = body.active_profile
    if active_profile is None:
        try:
            manifest = load_manifest(project_dir)
            if manifest:
                active_profile = manifest.get("active_profile")
        except Exception:
            pass

    return SettingsResponse(
        project_dir=str(project_dir),
        active_profile=active_profile,
    )


@router.delete("/project")
def delete_project(request: Request) -> dict:
    """Delete project data (.klippbok/ directory) and clear active project.

    Removes the .klippbok/ subdirectory (thumbnails, manifest, cache) from
    the active project directory. The user's original media files are NOT
    affected. Clears the active project on app.state so the frontend shows
    the project picker.

    Args:
        request: FastAPI request (used to access app.state.project_dir).

    Returns:
        Dict with status "deleted".

    Raises:
        HTTPException 404: If no project is active.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=404, detail="No active project")

    klippbok_dir = project_dir / ".klippbok"
    if klippbok_dir.exists():
        shutil.rmtree(klippbok_dir)
        logger.info("Deleted project data: %s", klippbok_dir)

    request.app.state.project_dir = None
    return {"status": "deleted"}
