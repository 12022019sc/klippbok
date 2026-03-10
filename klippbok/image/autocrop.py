"""Automatic crop subject detection using MediaPipe Pose.

Uses MediaPipe's Tasks API (PoseLandmarker) for full-body detection.
Requires a pose landmarker model file (.task) to be available.

Model discovery order:
1. MEDIAPIPE_POSE_MODEL env var (path to .task file)
2. {package_dir}/models/pose_landmarker_full.task (vendored)
3. ~/.klippbok/models/pose_landmarker_full.task (user cache)
4. Download on first use to user cache location

Algorithm — "subject-fitted crop with safety floor":
  1. Detect pose landmarks, discard any outside [0,1] image range.
  2. Compute tight bounding box from in-bounds landmarks + 25% padding.
  3. Pick bucket by IMAGE AR (not bbox AR) — handles extreme ARs.
  4. Expand padded bbox to fill bucket AR.
  5. Enforce a minimum crop size (70% of image short edge) so bad
     detections never produce absurdly small crops.
  6. Center on face (or body center), clamped to image bounds.

This zooms in on the subject when there's excess background, keeps
full body when the person fills the frame, and gracefully handles
MediaPipe's out-of-bounds landmark predictions.

When no person is detected: falls back to a plain center crop.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Default model filename for the full pose landmarker
_POSE_MODEL_FILENAME = "pose_landmarker_full.task"

# Public download URL for the full pose landmarker model (~5MB)
_POSE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_full/float16/latest/pose_landmarker_full.task"
)


def _get_model_path() -> Path | None:
    """Locate the pose landmarker model file.

    Search order:
    1. MEDIAPIPE_POSE_MODEL env var
    2. {package}/models/pose_landmarker_full.task
    3. ~/.klippbok/models/pose_landmarker_full.task

    Returns:
        Path to model file if found, else None.
    """
    # 1. Environment variable override
    env_path = os.environ.get("MEDIAPIPE_POSE_MODEL")
    if env_path and Path(env_path).is_file():
        return Path(env_path)

    # 2. Vendored alongside this module
    package_model = Path(__file__).parent / "models" / _POSE_MODEL_FILENAME
    if package_model.is_file():
        return package_model

    # 3. User cache directory
    user_model = Path.home() / ".klippbok" / "models" / _POSE_MODEL_FILENAME
    if user_model.is_file():
        return user_model

    return None


def _download_model(dest: Path) -> Path:
    """Download the pose landmarker model to dest.

    Args:
        dest: Destination path for the downloaded model file.

    Returns:
        dest path.

    Raises:
        RuntimeError: If download fails.
    """
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading MediaPipe pose model to %s ...", dest)
    try:
        urllib.request.urlretrieve(_POSE_MODEL_URL, str(dest))
    except Exception as exc:
        raise RuntimeError(
            f"Failed to download MediaPipe pose model from {_POSE_MODEL_URL}: {exc}\n"
            f"Set MEDIAPIPE_POSE_MODEL env var to a local .task file path, or "
            f"place the model at {dest}"
        ) from exc
    logger.info("Downloaded pose model: %s", dest)
    return dest


def _ensure_model() -> Path:
    """Get or download the pose landmarker model.

    Returns:
        Path to the model file.

    Raises:
        RuntimeError: If model not found and download fails.
    """
    model_path = _get_model_path()
    if model_path is not None:
        return model_path

    # Download to user cache
    user_model = Path.home() / ".klippbok" / "models" / _POSE_MODEL_FILENAME
    return _download_model(user_model)


def auto_crop_image(
    image_path: Path,
    buckets: list[tuple[int, int]],
) -> tuple[int, int, int, int, str]:
    """Detect a person in an image and return crop coordinates for the body.

    Uses MediaPipe PoseLandmarker to detect body landmarks. Falls back to
    center crop when no person is detected.

    Args:
        image_path: Path to the source image.
        buckets: List of valid (width, height) bucket dimensions from
            generate_buckets(). Must not be empty.

    Returns:
        (left, top, width, height, detection_type) crop coordinates in image
        pixel space. detection_type is ``"pose"`` when a person was detected,
        ``"center"`` when falling back to center crop. Coordinates are always
        clamped to the image bounds.

    Raises:
        ImportError: If mediapipe is not installed.
        RuntimeError: If the pose model cannot be found or downloaded.
        OSError: If image_path cannot be read.
    """
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    from PIL import Image as PILImage

    from klippbok.image.bucket import assign_to_bucket

    # Get image dimensions
    with PILImage.open(image_path) as pil_img:
        img_width, img_height = pil_img.size

    model_path = _ensure_model()

    base_options = mp_python.BaseOptions(model_asset_path=str(model_path))
    options = mp_vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=mp_vision.RunningMode.IMAGE,
    )

    try:
        with mp_vision.PoseLandmarker.create_from_options(options) as detector:
            mp_image = mp.Image.create_from_file(str(image_path))
            result = detector.detect(mp_image)
    except Exception as exc:
        logger.warning(
            "auto_crop_image: pose detection failed for %s (%s), using center crop",
            image_path.name, exc,
        )
        return (*_center_crop(img_width, img_height, buckets), "center")

    if not result.pose_landmarks:
        logger.debug(
            "auto_crop_image: no pose detected in %s, using center crop",
            image_path.name,
        )
        return (*_center_crop(img_width, img_height, buckets), "center")

    # -- Subject-fitted crop with safety floor --
    landmarks = result.pose_landmarks[0]
    _FACE_IDS = range(0, 11)  # nose, eyes, mouth, ears

    # Step 1: Filter to in-bounds landmarks only (discard wild predictions)
    in_bounds = [
        lm for lm in landmarks
        if 0.0 <= lm.x <= 1.0 and 0.0 <= lm.y <= 1.0
    ]
    if not in_bounds:
        return (*_center_crop(img_width, img_height, buckets), "center")

    # Step 2: Subject bounding box from in-bounds landmarks
    xs = [lm.x * img_width for lm in in_bounds]
    ys = [lm.y * img_height for lm in in_bounds]
    subj_left = int(min(xs))
    subj_top = int(min(ys))
    subj_right = int(max(xs))
    subj_bottom = int(max(ys))
    subj_w = subj_right - subj_left
    subj_h = subj_bottom - subj_top

    # Step 3: Add 25% padding around subject (generous but bounded)
    pad_x = int(subj_w * 0.25)
    pad_y = int(subj_h * 0.25)
    padded_left = max(0, subj_left - pad_x)
    padded_top = max(0, subj_top - pad_y)
    padded_right = min(img_width, subj_right + pad_x)
    padded_bottom = min(img_height, subj_bottom + pad_y)
    padded_w = padded_right - padded_left
    padded_h = padded_bottom - padded_top

    # Step 4: Choose bucket by IMAGE AR (handles extreme ARs gracefully)
    bucket = assign_to_bucket(img_width, img_height, buckets)
    if bucket is None:
        # Image has extreme AR (e.g., very tall phone screenshots).
        # Pick the most portrait/landscape bucket instead.
        image_ar = img_width / img_height
        if image_ar < 1.0:
            bucket = min(buckets, key=lambda b: b[0] / b[1])  # most portrait
        else:
            bucket = max(buckets, key=lambda b: b[0] / b[1])  # most landscape
    bucket_ar = bucket[0] / bucket[1]

    # Step 5: Expand padded subject bbox to fill bucket AR
    if padded_w / max(padded_h, 1) >= bucket_ar:
        crop_w = padded_w
        crop_h = int(crop_w / bucket_ar)
    else:
        crop_h = padded_h
        crop_w = int(crop_h * bucket_ar)

    # Step 6: Enforce minimum size — at least 70% of image short edge.
    # Prevents bad detections from producing absurdly small crops.
    min_dim = int(min(img_width, img_height) * 0.70)
    if crop_w < min_dim or crop_h < min_dim:
        if bucket_ar >= 1.0:
            crop_w = max(crop_w, min_dim)
            crop_h = int(crop_w / bucket_ar)
        else:
            crop_h = max(crop_h, min_dim)
            crop_w = int(crop_h * bucket_ar)

    # Step 7: Clamp to image bounds (preserve AR)
    if crop_w > img_width or crop_h > img_height:
        if img_width / img_height >= bucket_ar:
            crop_h = min(crop_h, img_height)
            crop_w = int(crop_h * bucket_ar)
        else:
            crop_w = min(crop_w, img_width)
            crop_h = int(crop_w / bucket_ar)
    crop_w = min(crop_w, img_width)
    crop_h = min(crop_h, img_height)

    # Step 8: Center on subject bbox midpoint.
    # The bbox center naturally sits at the body's vertical midpoint,
    # which avoids wasting crop space on empty sky above the head
    # (as face-centering would).
    cx = (subj_left + subj_right) // 2
    cy = (subj_top + subj_bottom) // 2

    # Step 9: Position crop, clamped to image bounds
    left = max(0, min(cx - crop_w // 2, img_width - crop_w))
    top = max(0, min(cy - crop_h // 2, img_height - crop_h))

    return left, top, crop_w, crop_h, "pose"


def _center_crop(
    img_width: int,
    img_height: int,
    buckets: list[tuple[int, int]],
) -> tuple[int, int, int, int]:
    """Return centered crop coordinates at the nearest bucket aspect ratio.

    Finds the bucket whose aspect ratio is closest to the image's aspect
    ratio, computes the largest crop region at that AR that fits within
    the image, and centers it.

    Does NOT require mediapipe to be installed -- pure Python math.

    Args:
        img_width: Image width in pixels.
        img_height: Image height in pixels.
        buckets: List of valid (width, height) bucket dimensions.

    Returns:
        (left, top, width, height) centered crop coordinates.
    """
    from klippbok.image.bucket import assign_to_bucket

    # Find the bucket whose AR is closest to the image AR
    bucket = assign_to_bucket(img_width, img_height, buckets)
    if bucket is None:
        # Extreme aspect ratio -- use the largest square that fits
        side = min(img_width, img_height)
        left = (img_width - side) // 2
        top = (img_height - side) // 2
        return left, top, side, side

    bucket_w, bucket_h = bucket
    bucket_ar = bucket_w / bucket_h
    image_ar = img_width / img_height

    # Compute the largest crop at bucket_ar that fits within image bounds
    if image_ar >= bucket_ar:
        # Image is wider than bucket ratio -- constrained by height
        crop_h = img_height
        crop_w = int(crop_h * bucket_ar)
    else:
        # Image is taller than bucket ratio -- constrained by width
        crop_w = img_width
        crop_h = int(crop_w / bucket_ar)

    # Clamp to image bounds (can happen due to integer rounding)
    crop_w = min(crop_w, img_width)
    crop_h = min(crop_h, img_height)

    # Center the crop
    left = (img_width - crop_w) // 2
    top = (img_height - crop_h) // 2

    return left, top, crop_w, crop_h


def _fit_crop_to_bucket(
    bbox_left: int,
    bbox_top: int,
    bbox_w: int,
    bbox_h: int,
    bucket: tuple[int, int],
    img_w: int,
    img_h: int,
    *,
    focus_point: tuple[int, int] | None = None,
) -> tuple[int, int, int, int]:
    """Expand or contract a bbox to match the bucket aspect ratio.

    Keeps the expansion centered on the focus point (or bbox center) and
    clamps to image bounds.

    Does NOT require mediapipe to be installed -- pure Python math.

    Args:
        bbox_left: Left edge of the bounding box.
        bbox_top: Top edge of the bounding box.
        bbox_w: Width of the bounding box.
        bbox_h: Height of the bounding box.
        bucket: Target (width, height) bucket tuple.
        img_w: Full image width for clamping.
        img_h: Full image height for clamping.
        focus_point: Optional (x, y) center to prefer when positioning
            the crop. When provided, the crop is centered on this point
            instead of the bbox geometric center.

    Returns:
        (left, top, width, height) crop coordinates clamped to image bounds.
    """
    bucket_w, bucket_h = bucket
    bucket_ar = bucket_w / bucket_h

    # Use focus_point as crop center when available, otherwise bbox center
    if focus_point is not None:
        cx, cy = focus_point
    else:
        cx = bbox_left + bbox_w // 2
        cy = bbox_top + bbox_h // 2

    # Expand to match bucket AR while covering the bbox
    if bbox_w / max(bbox_h, 1) >= bucket_ar:
        # bbox is wider than bucket -- expand height to match
        new_w = bbox_w
        new_h = int(new_w / bucket_ar)
    else:
        # bbox is taller than bucket -- expand width to match
        new_h = bbox_h
        new_w = int(new_h * bucket_ar)

    # Ensure the crop region is at least as large as the bbox
    new_w = max(new_w, bbox_w)
    new_h = max(new_h, bbox_h)

    # Shrink to fit image while preserving bucket AR
    if new_w > img_w or new_h > img_h:
        if img_w / img_h >= bucket_ar:
            # Image is wider than bucket AR — height is the constraint
            new_h = min(new_h, img_h)
            new_w = int(new_h * bucket_ar)
        else:
            # Image is taller than bucket AR — width is the constraint
            new_w = min(new_w, img_w)
            new_h = int(new_w / bucket_ar)

    # Center on bbox center, slide to stay within image bounds
    new_left = max(0, min(cx - new_w // 2, img_w - new_w))
    new_top = max(0, min(cy - new_h // 2, img_h - new_h))

    return new_left, new_top, new_w, new_h
