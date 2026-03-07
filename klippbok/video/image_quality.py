"""Image quality scoring for extracted reference images.

Uses OpenCV to compute sharpness (Laplacian variance) and detect
blank/uniform frames. These are the quality gates that prevent garbage
reference images from corrupting the VAE latent representation.

WHY Laplacian variance: the Laplacian operator detects edges and
texture. A sharp image has high Laplacian variance (lots of detail).
A blurry or blank image has low variance (uniform regions). This is
the standard computational sharpness metric — simple, fast, robust.

All functions work on file paths (not pre-loaded arrays) so they
can be used standalone from the CLI without loading OpenCV upfront.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from klippbok.video.extract_models import ImageValidation


def compute_sharpness(image_path: str | Path) -> float:
    """Compute sharpness of an image using Laplacian variance.

    Loads the image as grayscale, applies the Laplacian operator
    (second-order derivative — detects edges), and returns the
    variance of the result. Higher = sharper = more detail.

    Typical ranges:
    - Blank/solid color: < 1.0
    - Very blurry: 1-50
    - Normal video frame: 50-500
    - Sharp photograph: 500-5000+

    Args:
        image_path: Path to the image file (PNG, JPG, etc.).

    Returns:
        Laplacian variance as a float. Higher = sharper.

    Raises:
        FileNotFoundError: if the image file doesn't exist.
        ValueError: if the file can't be read as an image.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # cv2.imread returns None for unreadable files (not an exception)
    gray = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError(
            f"Cannot read image '{image_path}'. "
            f"File may be corrupted or not a supported image format."
        )

    # Laplacian detects edges; variance measures how much edge content there is
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    return float(laplacian.var())


def is_blank(image_path: str | Path, threshold: float = 5.0) -> bool:
    """Detect if an image is effectively blank (uniform color).

    A blank frame has almost no texture or edge information — it's
    a solid color, a black frame, or a white frame. These are useless
    as reference images because they carry no visual information for
    the VAE to encode.

    Uses Laplacian variance: if the variance is below the threshold,
    the image is considered blank.

    Args:
        image_path: Path to the image file.
        threshold: Laplacian variance below this = blank.
            Default 5.0 catches solid colors and near-uniform frames.
            Increase to catch slightly textured but still useless frames.

    Returns:
        True if the image is blank/uniform, False if it has content.

    Raises:
        FileNotFoundError: if the image file doesn't exist.
        ValueError: if the file can't be read as an image.
    """
    return compute_sharpness(image_path) < threshold


def score_frame(image_path: str | Path, face_app: object | None = None) -> float:
    """Compute a composite quality score for a video frame.

    Combines multiple factors that correlate with "good reference frame"
    for character LoRA training:

    1. Face presence (if face_app provided) — THE dominant factor. Frames
       with clear, large faces score dramatically higher. Face area relative
       to frame size determines the boost.
    2. Sharpness (Laplacian variance) — penalizes blurry/blank frames
    3. Brightness — penalizes too dark (<40 mean) or too bright (>220 mean)
    4. Colorfulness — prefers frames with color variety over monochrome/gray
    5. Contrast — prefers frames with good dynamic range

    All sub-scores are normalized to 0-1 and combined with weights.
    When face detection is available, face presence gets 40% weight
    because for character LoRA, a clear face IS the best frame.

    Args:
        image_path: Path to the image file.
        face_app: Optional InsightFace FaceAnalysis instance for face
            detection. If None, face scoring is skipped and other
            factors are reweighted.

    Returns:
        Composite score as float (higher = better). Range roughly 0-1.

    Raises:
        FileNotFoundError: if the image file doesn't exist.
        ValueError: if the file can't be read as an image.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Cannot read image '{image_path}'.")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    frame_area = h * w

    # 1. Sharpness: Laplacian variance, log-scaled to compress range
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    sharpness_raw = float(laplacian.var())
    # Log scale: maps ~5 -> 0.3, ~100 -> 0.7, ~500 -> 0.9, ~2000 -> 1.0
    sharpness_score = min(1.0, max(0.0, np.log1p(sharpness_raw) / 8.0))

    # Reject near-blank frames outright
    if sharpness_raw < 5.0:
        return 0.0

    # 2. Brightness: penalize too dark or too bright
    mean_brightness = float(gray.mean())
    if mean_brightness < 40:
        brightness_score = mean_brightness / 40.0
    elif mean_brightness > 220:
        brightness_score = max(0.0, (255 - mean_brightness) / 35.0)
    elif mean_brightness < 60:
        brightness_score = 0.7 + 0.3 * (mean_brightness - 40) / 20.0
    elif mean_brightness > 180:
        brightness_score = 0.7 + 0.3 * (220 - mean_brightness) / 40.0
    else:
        brightness_score = 1.0

    # 3. Colorfulness: Hasler & Süsstrunk metric
    b, g, r = cv2.split(img.astype(np.float64))
    rg = r - g
    yb = 0.5 * (r + g) - b
    colorfulness_raw = float(np.sqrt(rg.var() + yb.var()) + 0.3 * np.sqrt(rg.mean()**2 + yb.mean()**2))
    colorfulness_score = min(1.0, colorfulness_raw / 80.0)

    # 4. Contrast: standard deviation of grayscale
    contrast_raw = float(gray.std())
    contrast_score = min(1.0, contrast_raw / 60.0)

    # 5. Face detection (if available)
    # Sub-scores: face_area_score, face_sharpness_score, face_pose_score, face_det_score
    face_area_score = 0.0
    face_sharpness_score = 0.0
    face_pose_score = 0.0
    face_det_score_val = 0.0
    has_face_detection = False
    if face_app is not None:
        has_face_detection = True
        try:
            faces = face_app.get(img)
            if faces:
                # Pick the largest face as the primary subject
                best_face = None
                best_face_area = 0.0
                for face in faces:
                    bbox = face.bbox  # [x1, y1, x2, y2]
                    face_w = bbox[2] - bbox[0]
                    face_h = bbox[3] - bbox[1]
                    face_area = face_w * face_h
                    if face_area > best_face_area:
                        best_face_area = face_area
                        best_face = face

                if best_face is not None:
                    bbox = best_face.bbox
                    face_ratio = best_face_area / frame_area

                    # 5a. Face area ratio (reweighted from 40% to 10%)
                    if face_ratio > 0.15:
                        face_area_score = 1.0
                    elif face_ratio > 0.05:
                        face_area_score = 0.6 + 0.4 * (face_ratio - 0.05) / 0.10
                    elif face_ratio > 0.01:
                        face_area_score = 0.3 + 0.3 * (face_ratio - 0.01) / 0.04
                    else:
                        face_area_score = 0.1

                    # 5b. Face region sharpness — Laplacian on cropped face bbox
                    x1 = max(0, int(bbox[0]))
                    y1 = max(0, int(bbox[1]))
                    x2 = min(w, int(bbox[2]))
                    y2 = min(h, int(bbox[3]))
                    if x2 > x1 and y2 > y1:
                        face_crop_gray = gray[y1:y2, x1:x2]
                        face_lap = cv2.Laplacian(face_crop_gray, cv2.CV_64F)
                        face_sharpness_raw = float(face_lap.var())
                        face_sharpness_score = min(1.0, max(0.0, np.log1p(face_sharpness_raw) / 8.0))

                    # 5c. Head pose (frontality) — from face.pose [pitch, yaw, roll]
                    pose = getattr(best_face, 'pose', None)
                    if pose is not None and len(pose) >= 2:
                        pitch, yaw = abs(float(pose[0])), abs(float(pose[1]))
                        # Score: frontal=1.0, 45° yaw=~0.5, extreme=0.0
                        face_pose_score = max(0.0, 1.0 - min(1.0, (yaw / 45.0 + pitch / 35.0) / 2.0))
                    else:
                        face_pose_score = 0.5  # neutral if pose unavailable

                    # 5d. Detection confidence — direct 0-1 score
                    det_score = getattr(best_face, 'det_score', None)
                    if det_score is not None:
                        face_det_score_val = float(det_score)
                    else:
                        face_det_score_val = 0.5  # neutral if unavailable
        except Exception:
            pass  # face detection failure is not fatal

    # Weighted combination
    if has_face_detection:
        # Character LoRA: face signals get 50% total weight
        score = (
            0.20 * face_sharpness_score
            + 0.15 * sharpness_score
            + 0.10 * face_pose_score
            + 0.10 * face_det_score_val
            + 0.10 * face_area_score
            + 0.15 * brightness_score
            + 0.10 * colorfulness_score
            + 0.10 * contrast_score
        )
    else:
        # No face detection — rely on visual quality metrics
        score = (
            0.35 * sharpness_score
            + 0.30 * brightness_score
            + 0.20 * colorfulness_score
            + 0.15 * contrast_score
        )

    return score


def validate_extracted_image(
    image_path: str | Path,
    expected_width: int | None = None,
    expected_height: int | None = None,
) -> ImageValidation:
    """Validate an extracted reference image for quality and resolution.

    Checks three things:
    1. Sharpness — is there enough detail for the VAE?
    2. Blank detection — is this a solid color / black / white frame?
    3. Resolution — does it match the expected dimensions from the source video?

    Args:
        image_path: Path to the image to validate.
        expected_width: Expected width in pixels (from source video metadata).
            None to skip resolution check.
        expected_height: Expected height in pixels.
            None to skip resolution check.

    Returns:
        ImageValidation with all quality metrics.

    Raises:
        FileNotFoundError: if the image file doesn't exist.
        ValueError: if the file can't be read as an image.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Load to get dimensions (need color image for width/height)
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(
            f"Cannot read image '{image_path}'. "
            f"File may be corrupted or not a supported image format."
        )

    height, width = img.shape[:2]

    # Compute sharpness on grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    sharpness = float(laplacian.var())

    # Resolution check
    resolution_ok = True
    if expected_width is not None and expected_height is not None:
        resolution_ok = (width == expected_width and height == expected_height)

    return ImageValidation(
        path=image_path,
        width=width,
        height=height,
        sharpness=sharpness,
        is_blank=sharpness < 5.0,
        resolution_ok=resolution_ok,
        expected_width=expected_width,
        expected_height=expected_height,
    )
