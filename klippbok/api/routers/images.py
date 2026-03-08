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

# Hardcoded MIME type map — avoids mimetypes.guess_type which reads from the
# Windows registry and can return non-standard types like "image/pjpeg".
MEDIA_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
}

router = APIRouter(prefix="/images", tags=["images"])


# ---------------------------------------------------------------------------
# File-serving endpoint — MUST be registered BEFORE /{image_id} catch-all
# routes, otherwise FastAPI captures "file" as an image_id path parameter.
# ---------------------------------------------------------------------------


@router.get("/file")
def serve_file(path: str, request: Request) -> FileResponse:
    """Serve an arbitrary file from within the project directory.

    Used by the frontend to display face cluster thumbnails and concept
    reference images whose absolute paths are returned by the triage API.

    Args:
        path: Absolute path to the file to serve.
        request: FastAPI request (used to access app.state.project_dir).

    Returns:
        FileResponse with appropriate MIME type.

    Raises:
        HTTPException 403: If the file is outside the project directory.
        HTTPException 404: If the file does not exist.
        HTTPException 409: If no project directory is selected.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    file_path = Path(path).resolve()
    # Security: ensure file is under project_dir
    if not str(file_path).startswith(str(project_dir.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    suffix = file_path.suffix.lower()
    media_type = MEDIA_TYPES.get(suffix, "application/octet-stream")
    return FileResponse(file_path, media_type=media_type)


def _image_id(relative_path: str) -> str:
    """Compute the image ID from its relative path.

    Args:
        relative_path: Path relative to project root.

    Returns:
        SHA256 hex digest of the path, truncated to 16 characters.
    """
    return hashlib.sha256(relative_path.encode()).hexdigest()[:16]


def _entry_to_response(
    entry: dict,
    triage_lookup: dict[str, dict] | None = None,
    project_dir: Path | None = None,
) -> ImageStatusResponse:
    """Convert a manifest image dict to an ImageStatusResponse.

    Args:
        entry: A dict from manifest["images"].
        triage_lookup: Optional triage results by relative path.
        project_dir: Project root for resolving file paths (used for file stats).

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

    # Media type: "video" or "image" (default for backward compatibility)
    media_type = entry.get("type", "image")
    is_video = media_type == "video"

    # Triage results from path-based lookup
    triage_data = triage_lookup.get(relative_path) if triage_lookup else None

    # File stats (size, creation time) — read from disk
    file_size: int | None = None
    created_at: str | None = None
    if project_dir:
        abs_path = project_dir / relative_path
        try:
            st = abs_path.stat()
            file_size = st.st_size
            from datetime import datetime, timezone
            created_at = datetime.fromtimestamp(st.st_ctime, tz=timezone.utc).isoformat()
        except OSError:
            pass

    return ImageStatusResponse(
        id=image_id,
        relative_path=relative_path,
        thumbnail_url=f"/api/v1/images/{image_id}/thumbnail",
        width=entry.get("width", 0),
        height=entry.get("height", 0),
        resolution_ok=resolution_ok,
        quality_pass=quality_pass,
        blur_score=entry.get("blur_score"),
        format=entry.get("format"),
        file_size=file_size,
        created_at=created_at,
        bucket=entry.get("bucket"),
        is_near_duplicate=is_near_duplicate,
        duplicate_group_id=duplicate_group_id,
        caption=entry.get("caption"),
        media_type=media_type,
        full_url=f"/api/v1/images/{image_id}/full",
        video_url=f"/api/v1/images/{image_id}/video" if is_video else None,
        duration=entry.get("duration"),
        fps=entry.get("fps"),
        codec=entry.get("codec"),
        triage_classification=triage_data["classification"] if triage_data else None,
        best_score=triage_data["best_score"] if triage_data else None,
    )


def _find_entry_by_id(
    image_id: str,
    project_dir: Path,
) -> tuple[dict, Path]:
    """Look up a manifest entry by its computed ID.

    Args:
        image_id: SHA256[:16] ID of the image.
        project_dir: Project root directory.

    Returns:
        Tuple of (manifest entry dict, absolute file path).

    Raises:
        HTTPException 409: If no project directory is selected.
        HTTPException 404: If the ID is not found or the file is missing on disk.
        HTTPException 500: If the manifest cannot be loaded.
    """
    from klippbok.services.project_service import load_manifest

    try:
        manifest = load_manifest(project_dir)
    except Exception as exc:
        logger.error("Failed to load manifest: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load project manifest") from exc

    if not manifest or "images" not in manifest:
        raise HTTPException(status_code=404, detail="No images in manifest")

    for entry in manifest["images"]:
        relative_path = entry.get("path", "")
        if _image_id(relative_path) == image_id:
            abs_path = project_dir / relative_path
            if not abs_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"File not found on disk: {relative_path}",
                )
            return entry, abs_path

    raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found")


def _build_triage_lookup(project_dir: Path) -> dict[str, dict]:
    """Build a lookup dict from triage results, keyed by relative path.

    Triage results store item_path as absolute paths. We normalize them
    to relative paths (stripping the project_dir prefix) so they match
    the gallery manifest's path field.

    Args:
        project_dir: Project root directory.

    Returns:
        Dict mapping relative_path -> {classification, best_score}.
        Empty dict if no triage manifest exists.
    """
    import json as _json

    triage_path = project_dir / ".klippbok" / "triage_manifest.json"
    if not triage_path.exists():
        return {}

    try:
        data = _json.loads(triage_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    lookup: dict[str, dict] = {}
    project_str = str(project_dir.resolve())

    for result in data.get("results", []):
        item_path = result.get("item_path", "")
        # Normalize: strip project_dir prefix to get relative path
        resolved = str(Path(item_path).resolve())
        if resolved.startswith(project_str):
            rel = resolved[len(project_str):].lstrip("/\\")
            # Normalize separators to forward slashes (matches manifest)
            rel = rel.replace("\\", "/")
        else:
            rel = item_path

        lookup[rel] = {
            "classification": result.get("classification"),
            "best_score": result.get("best_score"),
        }

    return lookup


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

    project_dir: Path | None = request.app.state.project_dir

    if project_dir is None:
        return GalleryResponse(total=0, images=[])

    try:
        manifest = load_manifest(project_dir)
    except Exception as exc:
        logger.error("Failed to load manifest from %s: %s", project_dir, exc)
        return GalleryResponse(total=0, images=[])

    if not manifest or "images" not in manifest:
        return GalleryResponse(total=0, images=[])

    # Load triage results and build a path-based lookup.
    # Triage item_path is absolute; we normalize to relative_path for joining.
    triage_lookup = _build_triage_lookup(project_dir)

    images = [
        _entry_to_response(entry, triage_lookup=triage_lookup, project_dir=project_dir)
        for entry in manifest["images"]
        if (project_dir / entry.get("path", "")).exists()
    ]
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
    from klippbok.api.thumbnail import get_thumbnail, get_video_thumbnail

    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")
    cache_dir = project_dir / ".klippbok" / "thumbnails"

    entry, abs_path = _find_entry_by_id(image_id, project_dir)

    try:
        if entry.get("type") == "video":
            thumb_path = get_video_thumbnail(abs_path, cache_dir)
        else:
            thumb_path = get_thumbnail(abs_path, cache_dir)
    except Exception as exc:
        logger.error("Thumbnail generation failed for '%s': %s", abs_path, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate thumbnail: {exc}",
        ) from exc

    return FileResponse(thumb_path, media_type="image/jpeg")


@router.get("/{image_id}/full")
def get_image_full(image_id: str, request: Request) -> FileResponse:
    """Return the original full-resolution file.

    Args:
        image_id: SHA256[:16] ID of the image.
        request: FastAPI request (used to access app.state.project_dir).

    Returns:
        FileResponse with the original file, media type guessed from extension.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    _entry, abs_path = _find_entry_by_id(image_id, project_dir)
    media_type = MEDIA_TYPES.get(abs_path.suffix.lower(), "application/octet-stream")
    return FileResponse(abs_path, media_type=media_type)


@router.get("/{image_id}/video")
def get_video_file(image_id: str, request: Request) -> FileResponse:
    """Stream a video file for playback in the lightbox.

    Validates that the manifest entry is a video before serving.

    Args:
        image_id: SHA256[:16] ID of the video.
        request: FastAPI request (used to access app.state.project_dir).

    Returns:
        FileResponse with the video file.

    Raises:
        HTTPException 400: If the entry is not a video.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    entry, abs_path = _find_entry_by_id(image_id, project_dir)
    if entry.get("type") != "video":
        raise HTTPException(status_code=400, detail="Entry is not a video")

    media_type = MEDIA_TYPES.get(abs_path.suffix.lower(), "video/mp4")
    return FileResponse(abs_path, media_type=media_type)
