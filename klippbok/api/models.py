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

    project_dir: str
    """Absolute path to the project directory."""

    active_profile: str | None
    """Currently active model profile name, or None if not set."""


class SettingsUpdate(BaseModel):
    """Request body for updating project settings."""

    active_profile: str | None = None
    """New active model profile name, or None to clear."""
