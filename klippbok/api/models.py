"""Pydantic response schemas for the klippbok API.

These models define the JSON contract between the FastAPI backend
and the React frontend.
"""

from __future__ import annotations

from pydantic import BaseModel


class ImageStatusResponse(BaseModel):
    """Response model for a single image entry in the gallery.

    Fields mirror the manifest structure produced by batch_import_images,
    with computed fields added for frontend convenience (id, thumbnail_url).
    """

    id: str
    """SHA256 of relative_path, truncated to 16 hex characters."""

    relative_path: str
    """Path relative to the project root (e.g. 'images/photo.jpg')."""

    thumbnail_url: str
    """URL to fetch the JPEG thumbnail (e.g. '/api/v1/images/{id}/thumbnail')."""

    width: int
    """Image width in pixels."""

    height: int
    """Image height in pixels."""

    resolution_ok: bool
    """True if the image does NOT require upscaling to fit its bucket."""

    quality_pass: bool
    """True if no blur was detected (IMAGE_BLUR_DETECTED issue absent)."""

    bucket: str | None
    """Assigned training bucket, e.g. '768x512', or None if not assigned."""

    is_near_duplicate: bool
    """True if the image was flagged as a near-duplicate of another image."""

    duplicate_group_id: str | None
    """First 8 hex chars of the pHash for grouping duplicates, or None."""

    caption: str | None
    """Caption text if available, or None."""

    media_type: str = "image"
    """Media type: 'image' or 'video'."""

    full_url: str = ""
    """URL to fetch the full-resolution original file."""

    video_url: str | None = None
    """URL to stream the video file, or None for images."""


class GalleryResponse(BaseModel):
    """Response model for the image gallery list endpoint."""

    total: int
    """Total number of images in the response."""

    images: list[ImageStatusResponse]
    """List of image status objects."""


class ImportRequest(BaseModel):
    """Request body for starting a batch import."""

    directory: str
    """Absolute or relative path to the directory to import from."""

    recursive: bool = False
    """If True, scan subdirectories for images."""


class ImportStarted(BaseModel):
    """Response returned when a batch import is started."""

    operation_id: str
    """UUID identifying this import operation. Use for SSE progress stream."""


class ImportProgress(BaseModel):
    """SSE event payload for import progress updates."""

    operation_id: str
    """UUID of the import operation."""

    current: int
    """Number of images processed so far."""

    total: int
    """Total number of images to process."""

    message: str
    """Human-readable status message."""

    status: str
    """Operation status: 'running' | 'complete' | 'error'."""


class SettingsResponse(BaseModel):
    """Response model for reading current project settings."""

    project_dir: str | None
    """Absolute path to the project directory, or None if no project is active."""

    active_profile: str | None
    """Currently active model profile name, or None if not set."""


class SettingsUpdate(BaseModel):
    """Request body for updating project settings."""

    project_dir: str | None = None
    """Set the active project directory. Creates .klippbok/ if needed."""

    active_profile: str | None = None
    """New active model profile name, or None to clear."""


# --- Directory browser models ---


class DirEntry(BaseModel):
    """A single directory entry for the filesystem browser."""

    name: str
    """Display name (e.g. 'Documents')."""

    path: str
    """Absolute path (e.g. 'C:\\Users\\Shayne\\Documents')."""


class BrowseRootsResponse(BaseModel):
    """Response for listing filesystem roots (drive letters on Windows)."""

    roots: list[DirEntry]
    """Drive letters on Windows, ['/'] on Linux/macOS."""

    home_dir: str
    """User home directory — default start location for the browser."""


class BrowseListResponse(BaseModel):
    """Response for listing subdirectories of a given path."""

    current_path: str
    """Resolved absolute path being listed."""

    parent_path: str | None
    """Parent directory, or None when at a filesystem root."""

    entries: list[DirEntry]
    """Subdirectories only, sorted case-insensitive alphabetically."""

    error: str | None = None
    """Permission or access error message, if any."""


class MkdirRequest(BaseModel):
    """Request body for creating a new subdirectory."""

    parent_path: str
    """Parent directory where the new folder will be created."""

    name: str
    """Name of the new folder (no path separators or '..' allowed)."""
