"""Settings router -- read and update project settings.

Endpoints:
    GET /settings/  -- Return current project settings.
    PUT /settings/  -- Update project settings (stub for Phase 4).

Phase 4 note: Profile persistence is a stub. The GET endpoint reads
the active_profile from the project manifest if present. The PUT endpoint
returns the updated settings without persisting -- wired in a future phase.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request

from klippbok.api.models import SettingsResponse, SettingsUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/", response_model=SettingsResponse)
def get_settings(request: Request) -> SettingsResponse:
    """Return current project settings.

    Reads the project directory from app state and the active model profile
    from the project manifest (if present).

    Args:
        request: FastAPI request (used to access app.state.project_dir).

    Returns:
        SettingsResponse with project_dir and active_profile.
    """
    from klippbok.services.project_service import load_manifest

    project_dir: Path = request.app.state.project_dir

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
    """Update project settings (Phase 4 stub -- does not persist).

    Full persistence will be wired in a future phase. For now, this returns
    the settings as if they were updated, allowing the frontend to function.

    Args:
        body: Fields to update (active_profile).
        request: FastAPI request (used to access app.state.project_dir).

    Returns:
        SettingsResponse reflecting the requested update.
    """
    project_dir: Path = request.app.state.project_dir

    logger.info(
        "Settings update requested (stub): active_profile=%s",
        body.active_profile,
    )

    return SettingsResponse(
        project_dir=str(project_dir),
        active_profile=body.active_profile,
    )
