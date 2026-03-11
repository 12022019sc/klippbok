"""Crop router -- apply crop operations and run auto-crop subject detection.

Endpoints:
    POST /crop/       -- Apply a batch of crop+resize operations, produce output files.
    POST /crop/auto   -- Run auto-crop subject detection on a set of images.

Both endpoints run CPU-bound work in a thread executor to keep the event loop
responsive (Pillow image I/O and MediaPipe inference are synchronous).
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from klippbok.api.models import (
    AutoCropRequest,
    AutoCropResult,
    CropApplyRequest,
    CropApplyResult,
)
from klippbok.utils.paths import image_id as _image_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crop", tags=["crop"])


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
    successful_outputs: list[Path] = []

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
            successful_outputs.append(output_path)
        except Exception as exc:
            logger.error("Crop failed for image_id=%s: %s", item.image_id, exc)
            results.append(CropApplyResult(
                image_id=item.image_id,
                success=False,
                error=str(exc),
            ))

    # Register cropped outputs in the manifest so the Caption tab can find them
    if successful_outputs:
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _register_crop_outputs(project_dir, successful_outputs),
        )

    return results


def _register_crop_outputs(project_dir: Path, output_paths: list[Path]) -> None:
    """Add cropped images to the manifest so they're available for captioning.

    Each entry gets ``source: "crop"`` so the Caption page can filter to
    only show training-ready cropped images.
    """
    import json

    from klippbok.image.probe import probe_image
    from klippbok.services.project_service import MANIFEST_DIR, MANIFEST_FILE, load_manifest

    manifest = load_manifest(project_dir)
    if not manifest:
        logger.warning("No manifest found; cannot register crop outputs")
        return

    existing_paths = {e.get("path") for e in manifest.get("images", [])}

    added = 0
    for output_path in output_paths:
        try:
            rel_path = output_path.resolve().relative_to(project_dir.resolve()).as_posix()
        except ValueError:
            logger.warning("Cannot relativize crop output: %s", output_path)
            continue

        # Skip if already registered (e.g. re-crop)
        if rel_path in existing_paths:
            # Update existing entry dimensions
            for entry in manifest["images"]:
                if entry.get("path") == rel_path:
                    try:
                        meta = probe_image(output_path)
                        entry["width"] = meta.width
                        entry["height"] = meta.height
                        entry["source"] = "crop"
                    except Exception:
                        pass
                    break
            added += 1
            continue

        try:
            meta = probe_image(output_path)
        except Exception as exc:
            logger.warning("Failed to probe crop output %s: %s", output_path, exc)
            continue

        manifest["images"].append({
            "type": "image",
            "path": rel_path,
            "status": "valid",
            "width": meta.width,
            "height": meta.height,
            "format": meta.format.lower() if meta.format else "unknown",
            "source": "crop",
            "issues": [],
        })
        added += 1

    if added > 0:
        manifest_path = project_dir / MANIFEST_DIR / MANIFEST_FILE
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        logger.info("Registered %d crop outputs in manifest", added)


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

        detection_type = "center"
        try:
            left, top, width, height, detection_type = await asyncio.get_event_loop().run_in_executor(
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
                detection_type = "center"
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
            detection_type=detection_type,
        ))

    return results
