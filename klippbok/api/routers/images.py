"""Images router -- list and thumbnail endpoints for the gallery.

Endpoints:
    GET /images/           -- List all images from the project manifest.
    GET /images/{id}/thumbnail -- Return a cached JPEG thumbnail for an image.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from klippbok.api.models import GalleryResponse, ImageStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/images", tags=["images"])


def _image_id(relative_path: str) -> str:
    """Compute the image ID from its relative path.

    Args:
        relative_path: Path relative to project root.

    Returns:
        SHA256 hex digest of the path, truncated to 16 characters.
    """
    return hashlib.sha256(relative_path.encode()).hexdigest()[:16]


def _entry_to_response(entry: dict) -> ImageStatusResponse:
    """Convert a manifest image dict to an ImageStatusResponse.

    Args:
        entry: A dict from manifest["images"].

    Returns:
        ImageStatusResponse for the API.
    """
    relative_path = entry.get("path", "")
    image_id = _image_id(relative_path)

    # resolution_ok: True if IMAGE_UPSCALE_REQUIRED issue is absent
    issues = entry.get("issues", [])
    issue_codes = {i.get("code") for i in issues}
    resolution_ok = "IMAGE_UPSCALE_REQUIRED" not in issue_codes
    quality_pass = "IMAGE_BLUR_DETECTED" not in issue_codes

    # Duplicate detection
    is_near_duplicate = "near_duplicate_of" in entry
    phash = entry.get("phash")
    duplicate_group_id = phash[:8] if is_near_duplicate and phash else None

    return ImageStatusResponse(
        id=image_id,
        relative_path=relative_path,
        thumbnail_url=f"/api/v1/images/{image_id}/thumbnail",
        width=entry.get("width", 0),
        height=entry.get("height", 0),
        resolution_ok=resolution_ok,
        quality_pass=quality_pass,
        bucket=entry.get("bucket"),
        is_near_duplicate=is_near_duplicate,
        duplicate_group_id=duplicate_group_id,
        caption=entry.get("caption"),
    )


@router.get("/", response_model=GalleryResponse)
def list_images(request: Request) -> GalleryResponse:
    """List all images from the project manifest.

    Reads the project manifest and returns all image entries as a gallery.
    Returns an empty gallery if no manifest exists or contains no images.

    Args:
        request: FastAPI request (used to access app.state.project_dir).

    Returns:
        GalleryResponse with total count and list of ImageStatusResponse.
    """
    from klippbok.services.project_service import load_manifest

    project_dir: Path = request.app.state.project_dir

    try:
        manifest = load_manifest(project_dir)
    except Exception as exc:
        logger.error("Failed to load manifest from %s: %s", project_dir, exc)
        return GalleryResponse(total=0, images=[])

    if not manifest or "images" not in manifest:
        return GalleryResponse(total=0, images=[])

    images = [_entry_to_response(entry) for entry in manifest["images"]]
    return GalleryResponse(total=len(images), images=images)


@router.get("/{image_id}/thumbnail")
def get_image_thumbnail(image_id: str, request: Request) -> FileResponse:
    """Return a cached JPEG thumbnail for the given image.

    Locates the image by matching the computed SHA256 ID against all
    manifest entries, then generates (and caches) a 300x300 JPEG thumbnail.

    Args:
        image_id: SHA256[:16] ID of the image (from list_images response).
        request: FastAPI request (used to access app.state.project_dir).

    Returns:
        FileResponse with the JPEG thumbnail.

    Raises:
        HTTPException 404: If the image ID is not found in the manifest.
        HTTPException 404: If the image file does not exist on disk.
        HTTPException 500: If thumbnail generation fails.
    """
    from klippbok.api.thumbnail import get_thumbnail
    from klippbok.services.project_service import load_manifest

    project_dir: Path = request.app.state.project_dir
    cache_dir = project_dir / ".klippbok" / "thumbnails"

    try:
        manifest = load_manifest(project_dir)
    except Exception as exc:
        logger.error("Failed to load manifest: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load project manifest") from exc

    if not manifest or "images" not in manifest:
        raise HTTPException(status_code=404, detail="No images in manifest")

    # Find matching entry by computing ID for each relative_path
    matching_entry: dict | None = None
    for entry in manifest["images"]:
        relative_path = entry.get("path", "")
        if _image_id(relative_path) == image_id:
            matching_entry = entry
            break

    if matching_entry is None:
        raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found")

    relative_path = matching_entry.get("path", "")
    abs_path = project_dir / relative_path

    if not abs_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Image file not found on disk: {relative_path}",
        )

    try:
        thumb_path = get_thumbnail(abs_path, cache_dir)
    except Exception as exc:
        logger.error("Thumbnail generation failed for '%s': %s", abs_path, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate thumbnail: {exc}",
        ) from exc

    return FileResponse(thumb_path, media_type="image/jpeg")
