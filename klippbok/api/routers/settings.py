"""Settings router -- read and update project settings.

Endpoints:
    GET /settings/       -- Return current project settings.
    PUT /settings/       -- Update project settings (project_dir, active_profile).
    DELETE /settings/project -- Delete project data (.klippbok/) and clear active project.
    POST /settings/shutdown  -- Gracefully shut down the server and child processes.
    GET /settings/tools  -- Return external tool paths (onetrainer_path, model_dir).
    PUT /settings/tools  -- Update external tool paths and validate existence.

The PUT endpoint sets app.state.project_dir at runtime, enabling the
project picker flow where users select a project from the web UI.
"""

from __future__ import annotations

import logging
import os
import signal
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from pydantic import BaseModel

from klippbok.api.models import ProfileInfo, SettingsResponse, SettingsUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


class ToolSettingsUpdate(BaseModel):
    """Request body for updating external tool paths."""

    onetrainer_path: str | None = None
    model_dir: str | None = None


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
    anchor_word: str | None = None
    try:
        manifest = load_manifest(project_dir)
        if manifest:
            active_profile = manifest.get("active_profile")
            anchor_word = manifest.get("anchor_word")
    except Exception as exc:
        logger.warning("Could not read settings from manifest: %s", exc)

    return SettingsResponse(
        project_dir=str(project_dir),
        active_profile=active_profile,
        anchor_word=anchor_word,
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

    from klippbok.services.project_service import load_manifest

    # Load existing manifest to read/update active_profile
    manifest = None
    try:
        manifest = load_manifest(project_dir)
    except Exception:
        pass

    active_profile: str | None = body.active_profile
    dirty = False

    if active_profile is not None and manifest is not None:
        manifest["active_profile"] = active_profile
        dirty = True
        logger.info("Active profile set to: %s", active_profile)
    elif active_profile is None and manifest is not None:
        active_profile = manifest.get("active_profile")

    if body.anchor_word is not None and manifest is not None:
        manifest["anchor_word"] = body.anchor_word
        dirty = True
        logger.info("Anchor word set to: %s", body.anchor_word)

    if dirty:
        import json
        manifest_path = project_dir / ".klippbok" / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

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


@router.get("/profiles", response_model=list[ProfileInfo])
def list_available_profiles() -> list[ProfileInfo]:
    """List all available model profiles (built-in + custom).

    Returns a compact summary of each profile for display in the Settings
    page model profile dropdown.

    Returns:
        List of ProfileInfo objects ordered built-in first, then custom.
    """
    from klippbok.config.model_config import list_profiles

    profiles = list_profiles()
    return [
        ProfileInfo(
            name=p.name,
            display_name=p.display_name,
            caption_style=p.caption_style or "booru",
            base_resolution=p.base_resolution or 512,
        )
        for p in profiles
    ]


@router.post("/shutdown")
async def shutdown_server() -> dict:
    """Gracefully shut down the server and any child processes.

    Kills all active upscale subprocesses, then sends SIGTERM to the
    current process to trigger uvicorn's graceful shutdown.

    Returns:
        {"status": "shutting_down"} (client may not receive this if shutdown is fast).
    """
    from klippbok.services.upscale_service import _procs

    # Kill any running upscale subprocesses
    for op_id, proc in list(_procs.items()):
        try:
            proc.kill()
            logger.info("Killed upscale subprocess %s (pid=%d) during shutdown", op_id, proc.pid)
        except OSError:
            pass
    _procs.clear()

    logger.info("Server shutdown requested via API")

    # Send SIGTERM to ourselves to trigger uvicorn's graceful shutdown
    os.kill(os.getpid(), signal.SIGTERM)

    return {"status": "shutting_down"}


@router.get("/tools")
def get_tool_settings() -> dict:
    """Return external tool paths from global config.

    Returns:
        Dict with onetrainer_path and model_dir (both may be None).
    """
    from klippbok.services.global_config_service import load_global_config

    config = load_global_config()
    ot_section = config.get("onetrainer", {})

    return {
        "onetrainer_path": ot_section.get("onetrainer_path"),
        "model_dir": ot_section.get("model_dir"),
    }


@router.put("/tools")
def update_tool_settings(body: ToolSettingsUpdate) -> dict:
    """Update external tool paths in global config.

    Validates that paths exist as directories (when provided).
    Saves under the 'onetrainer' key in global config.

    Args:
        body: ToolSettingsUpdate with onetrainer_path and/or model_dir.

    Returns:
        Dict with updated onetrainer_path and model_dir values.

    Raises:
        HTTPException 400: If a provided path does not exist.
    """
    from klippbok.services.global_config_service import load_global_config, save_global_config

    if body.onetrainer_path is not None:
        p = Path(body.onetrainer_path)
        if not p.exists():
            raise HTTPException(
                status_code=400,
                detail=f"OneTrainer path does not exist: {body.onetrainer_path}",
            )

    if body.model_dir is not None:
        p = Path(body.model_dir)
        if not p.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Model directory does not exist: {body.model_dir}",
            )

    config = load_global_config()
    ot_section = config.setdefault("onetrainer", {})

    if body.onetrainer_path is not None:
        ot_section["onetrainer_path"] = body.onetrainer_path
    if body.model_dir is not None:
        ot_section["model_dir"] = body.model_dir

    save_global_config(config)
    logger.info(
        "Tool settings updated: onetrainer_path=%s, model_dir=%s",
        body.onetrainer_path,
        body.model_dir,
    )

    return {
        "onetrainer_path": ot_section.get("onetrainer_path"),
        "model_dir": ot_section.get("model_dir"),
    }
