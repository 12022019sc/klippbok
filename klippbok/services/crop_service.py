"""Crop application service using Pillow.

Stateless functions that apply crop coordinates to source images and
produce output files at exact target bucket dimensions.

Decision SVC-01: Module-level stateless functions (no classes).
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Rotation map: degrees -> Pillow Transpose constant name
_ROTATION_MAP = {
    90: "ROTATE_90",
    180: "ROTATE_180",
    270: "ROTATE_270",
}


def apply_crop(
    source_path: Path,
    left: int,
    top: int,
    width: int,
    height: int,
    rotation: int,
    flip_h: bool,
    flip_v: bool,
    target_width: int,
    target_height: int,
    output_path: Path,
) -> Path:
    """Apply crop parameters to a source image and save at target dimensions.

    Processing order:
    1. Open source image and convert to RGB (handles RGBA, CMYK, L, etc.)
    2. Apply rotation (0, 90, 180, 270 degrees) using lossless Transpose
    3. Apply flips (horizontal and/or vertical)
    4. Crop to (left, top, left+width, top+height)
    5. Resize to (target_width, target_height) with LANCZOS resampling
    6. Save to output_path

    Note: Rotation is applied BEFORE crop. Crop coordinates are in the
    post-rotation image space.

    Args:
        source_path: Path to the source image file.
        left: Left edge of crop region in post-rotation image coordinates.
        top: Top edge of crop region in post-rotation image coordinates.
        width: Width of crop region in pixels.
        height: Height of crop region in pixels.
        rotation: Rotation in degrees (0, 90, 180, or 270). Other values
            are silently ignored (no rotation applied).
        flip_h: If True, apply horizontal flip (mirror left-right).
        flip_v: If True, apply vertical flip (mirror top-bottom).
        target_width: Output image width (bucket dimension).
        target_height: Output image height (bucket dimension).
        output_path: Path where the cropped+resized image will be saved.

    Returns:
        output_path (same as the input argument, for chaining).

    Raises:
        OSError: If source image cannot be opened or output cannot be saved.
        PIL.UnidentifiedImageError: If source is not a valid image.
    """
    from PIL import Image

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as img:
        # Convert to RGB regardless of input mode (handles RGBA, CMYK, L, P, etc.)
        img = img.convert("RGB")

        # 1. Apply rotation (lossless 90-degree transpose)
        if rotation in _ROTATION_MAP:
            transpose_attr = getattr(Image.Transpose, _ROTATION_MAP[rotation])
            img = img.transpose(transpose_attr)

        # 2. Apply flips
        if flip_h:
            img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if flip_v:
            img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

        # 3. Crop to selection
        cropped = img.crop((left, top, left + width, top + height))

        # 4. Resize to exact bucket dimensions with LANCZOS (high-quality downscale)
        resized = cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)

        # 5. Save
        resized.save(output_path)

    logger.debug(
        "apply_crop: %s -> %s (%dx%d crop at (%d,%d) -> %dx%d bucket)",
        source_path.name,
        output_path.name,
        width,
        height,
        left,
        top,
        target_width,
        target_height,
    )

    return output_path


def apply_crops_batch(
    crops: list,
    project_dir: Path,
) -> list:
    """Apply a list of crop operations to produce bucket-sized output images.

    Output images are saved to: {project_dir}/.klippbok/crops/{stem}_{bw}x{bh}{ext}

    Args:
        crops: List of CropApplyItem objects from klippbok.api.models.
            Each item must have: image_id, source_path (resolved), left, top,
            width, height, rotation, flip_h, flip_v, target_width, target_height.
        project_dir: Project root directory.

    Returns:
        List of CropApplyResult objects with success/error per image.
    """
    from klippbok.api.models import CropApplyResult

    output_dir = project_dir / ".klippbok" / "crops"
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[CropApplyResult] = []

    for item in crops:
        source_path = Path(item.source_path)
        stem = source_path.stem
        ext = source_path.suffix
        output_filename = f"{stem}_{item.target_width}x{item.target_height}{ext}"
        output_path = output_dir / output_filename

        try:
            apply_crop(
                source_path=source_path,
                left=item.left,
                top=item.top,
                width=item.width,
                height=item.height,
                rotation=item.rotation,
                flip_h=item.flip_h,
                flip_v=item.flip_v,
                target_width=item.target_width,
                target_height=item.target_height,
                output_path=output_path,
            )
            results.append(CropApplyResult(
                image_id=item.image_id,
                success=True,
                output_path=str(output_path),
            ))
        except Exception as exc:
            logger.error(
                "apply_crops_batch: failed to crop image_id=%s: %s",
                item.image_id,
                exc,
            )
            results.append(CropApplyResult(
                image_id=item.image_id,
                success=False,
                error=str(exc),
            ))

    return results
