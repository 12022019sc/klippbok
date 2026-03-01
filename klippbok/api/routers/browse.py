"""Browse router -- filesystem directory browser for the project picker.

Endpoints:
    GET /browse/roots  -- List filesystem roots (drive letters on Windows).
    GET /browse/list   -- List subdirectories of a given path.
    POST /browse/mkdir -- Create a new subdirectory.

These endpoints power the visual directory browser in the frontend,
letting users navigate folders and select a project directory without
typing paths manually.
"""

from __future__ import annotations

import logging
import platform
import string
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from klippbok.api.models import (
    BrowseListResponse,
    BrowseRootsResponse,
    DirEntry,
    MkdirRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/browse", tags=["browse"])


@router.get("/roots", response_model=BrowseRootsResponse)
def get_roots() -> BrowseRootsResponse:
    """List filesystem roots and the user's home directory.

    On Windows, returns available drive letters (C:\\, D:\\, etc.).
    On Linux/macOS, returns a single root entry '/'.

    Returns:
        BrowseRootsResponse with roots list and home_dir.
    """
    home_dir = str(Path.home())

    if platform.system() == "Windows":
        roots = []
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            try:
                if Path(drive).exists():
                    roots.append(DirEntry(name=f"{letter}:", path=drive))
            except OSError:
                # BitLocker-locked or otherwise inaccessible drives raise
                # OSError instead of returning False — skip them.
                continue
    else:
        roots = [DirEntry(name="/", path="/")]

    return BrowseRootsResponse(roots=roots, home_dir=home_dir)


@router.get("/list", response_model=BrowseListResponse)
def list_directory(
    path: str = Query(..., description="Absolute path to list"),
) -> BrowseListResponse:
    """List subdirectories of the given path.

    Filters to directories only (no files), skips hidden dirs (name
    starts with '.'), and sorts case-insensitive alphabetically.

    Args:
        path: Absolute filesystem path to list.

    Returns:
        BrowseListResponse with entries, parent_path, and any error.
    """
    target = Path(path).resolve()

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {target}")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {target}")

    # Compute parent — None when at a filesystem root
    parent = target.parent
    parent_path = str(parent) if parent != target else None

    entries: list[DirEntry] = []
    error: str | None = None

    try:
        for child in target.iterdir():
            try:
                if not child.is_dir():
                    continue
                if child.name.startswith("."):
                    continue
                entries.append(DirEntry(name=child.name, path=str(child)))
            except PermissionError:
                # Skip individual entries we can't stat
                continue
    except PermissionError as exc:
        logger.warning("Permission denied listing %s: %s", target, exc)
        error = f"Permission denied: {target}"

    # Sort case-insensitive
    entries.sort(key=lambda e: e.name.lower())

    return BrowseListResponse(
        current_path=str(target),
        parent_path=parent_path,
        entries=entries,
        error=error,
    )


@router.post("/mkdir", response_model=BrowseListResponse)
def make_directory(body: MkdirRequest) -> BrowseListResponse:
    """Create a new subdirectory and return a refreshed listing.

    Validates that the folder name contains no path separators or '..'
    to prevent path traversal attacks.

    Args:
        body: MkdirRequest with parent_path and name.

    Returns:
        BrowseListResponse of the parent directory after creation.
    """
    # Validate folder name — no path separators or traversal
    if ".." in body.name or "/" in body.name or "\\" in body.name:
        raise HTTPException(
            status_code=400,
            detail="Folder name must not contain path separators or '..'",
        )

    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Folder name must not be empty")

    parent = Path(body.parent_path).resolve()
    if not parent.exists() or not parent.is_dir():
        raise HTTPException(
            status_code=400, detail=f"Parent directory not found: {parent}"
        )

    new_dir = parent / body.name
    try:
        new_dir.mkdir(exist_ok=True)
        logger.info("Created directory: %s", new_dir)
    except PermissionError as exc:
        raise HTTPException(
            status_code=403, detail=f"Permission denied: {exc}"
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to create directory: {exc}"
        ) from exc

    # Return refreshed listing of parent
    return list_directory(path=body.parent_path)
