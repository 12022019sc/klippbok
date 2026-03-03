"""Crop router -- apply crop operations and run auto-crop subject detection.

Endpoints:
    POST /crop/       -- Apply a batch of crop+resize operations, produce output files.
    POST /crop/auto   -- Run auto-crop subject detection on a set of images.

Both endpoints run CPU-bound work in a thread executor to keep the event loop
responsive (Pillow image I/O and MediaPipe inference are synchronous).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from klippbok.api.models import (
    AutoCropRequest,
    AutoCropResult,
    CropApplyRequest,
    CropApplyResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crop", tags=["crop"])


def _image_id(relative_path: str) -> str:
    """Compute the SHA256[:16] image ID from a relative path.

    Mirrors the same computation used in the images router and dataset service.
    """
    return hashlib.sha256(relative_path.encode()).hexdigest()[:16]


def _resolve_image_path(image_id: str, project_dir: Path) -> Path:
    """Resolve an image_id to an absolute path via the project manifest.

    Args:
        image_id: SHA256[:16] image ID.
        project_dir: Project root directory.

    Returns:
        Absolute path to the image file.

    Raises:
        HTTPException 404: If image_id is not found or file does not exist.
        HTTPException 500: If manifest cannot be loaded.
    """
    from klippbok.services.project_service import load_manifest

    try:
        manifest = load_manifest(project_dir)
    except Exception as exc:
        logger.error("Failed to load manifest: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load project manifest") from exc

    if not manifest or "images" not in manifest:
        raise HTTPException(status_code=404, detail="No images in manifest")

    for entry in manifest.get("images", []):
        relative_path = entry.get("path", "")
        if _image_id(relative_path) == image_id:
            abs_path = project_dir / relative_path
            if not abs_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"File not found on disk: {relative_path}",
                )
            return abs_path

    raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found")


@router.post("/", response_model=list[CropApplyResult], status_code=200)
async def apply_crops(body: CropApplyRequest, request: Request) -> list[CropApplyResult]:
    """Apply a batch of crop+rotate+flip+resize operations, saving output files.

    For each item in the request, resolves the image path from the manifest,
    runs apply_crop in a thread executor (CPU-bound Pillow work), and returns
    success/error per image.

    Args:
        body: List of crop operations with coordinates, rotation, flip, and target bucket.
        request: FastAPI request (used for app.state.project_dir).

    Returns:
        List of CropApplyResult with success/error per image.

    Raises:
        HTTPException 409: If no project directory is selected.
    """
    import asyncio

    from klippbok.services.crop_service import apply_crop

    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    output_dir = project_dir / ".klippbok" / "crops"
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[CropApplyResult] = []

    for item in body.crops:
        try:
            source_path = _resolve_image_path(item.image_id, project_dir)
        except HTTPException as exc:
            results.append(CropApplyResult(
                image_id=item.image_id,
                success=False,
                error=f"Image not found: {exc.detail}",
            ))
            continue

        stem = source_path.stem
        ext = source_path.suffix
        output_filename = f"{stem}_{item.target_width}x{item.target_height}{ext}"
        output_path = output_dir / output_filename

        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda src=source_path, op=output_path: apply_crop(
                    source_path=src,
                    left=item.left,
                    top=item.top,
                    width=item.width,
                    height=item.height,
                    rotation=item.rotation,
                    flip_h=item.flip_h,
                    flip_v=item.flip_v,
                    target_width=item.target_width,
                    target_height=item.target_height,
                    output_path=op,
                ),
            )
            results.append(CropApplyResult(
                image_id=item.image_id,
                success=True,
                output_path=str(output_path),
            ))
        except Exception as exc:
            logger.error("Crop failed for image_id=%s: %s", item.image_id, exc)
            results.append(CropApplyResult(
                image_id=item.image_id,
                success=False,
                error=str(exc),
            ))

    return results


@router.post("/auto", response_model=list[AutoCropResult], status_code=200)
async def auto_crop(body: AutoCropRequest, request: Request) -> list[AutoCropResult]:
    """Run auto-crop subject detection on a set of images.

    For each image_id, uses MediaPipe PoseLandmarker to detect a person and
    return suggested crop coordinates. Falls back to center crop when no
    person is detected.

    Args:
        body: List of image IDs and bucket configuration.
        request: FastAPI request (used for app.state.project_dir).

    Returns:
        List of AutoCropResult with suggested (left, top, width, height) per image.

    Raises:
        HTTPException 409: If no project directory is selected.
    """
    import asyncio

    from klippbok.config.model_profiles import generate_buckets
    from klippbok.image.autocrop import _center_crop, auto_crop_image

    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    # Generate bucket list from request parameters
    buckets = generate_buckets(
        base_resolution=body.bucket_size,
        max_aspect_ratio=1.0 if not body.allow_non_square else 2.0,
    )
    if not body.allow_non_square:
        # Filter to only square buckets when non-square is disabled
        buckets = [(w, h) for w, h in buckets if w == h]
        if not buckets:
            buckets = [(body.bucket_size, body.bucket_size)]

    from klippbok.image.bucket import assign_to_bucket

    results: list[AutoCropResult] = []

    for image_id in body.image_ids:
        try:
            source_path = _resolve_image_path(image_id, project_dir)
        except HTTPException as exc:
            logger.warning("Auto-crop: image %s not found: %s", image_id, exc.detail)
            continue

        try:
            left, top, width, height = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda src=source_path: auto_crop_image(src, buckets),
            )
        except Exception as exc:
            logger.warning(
                "Auto-crop failed for image_id=%s (%s), using center crop fallback: %s",
                image_id, source_path.name, exc,
            )
            # Robust fallback: use center crop without mediapipe
            try:
                from PIL import Image as PILImage
                with PILImage.open(source_path) as img:
                    img_w, img_h = img.size
                left, top, width, height = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda w=img_w, h=img_h: _center_crop(w, h, buckets),
                )
            except Exception as fallback_exc:
                logger.error(
                    "Center crop fallback also failed for %s: %s",
                    image_id, fallback_exc,
                )
                continue

        # Determine nearest bucket for the crop result
        bucket = assign_to_bucket(width, height, buckets)
        if bucket is None:
            bucket = buckets[len(buckets) // 2] if buckets else (body.bucket_size, body.bucket_size)

        results.append(AutoCropResult(
            image_id=image_id,
            left=left,
            top=top,
            width=width,
            height=height,
            target_bucket=bucket,
            detection_type="center",  # Will be "pose" when actual detection runs
        ))

    return results
