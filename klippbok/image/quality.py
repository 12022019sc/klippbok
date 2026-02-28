"""Image quality assessment -- blur detection via Laplacian variance.

Uses numpy + scipy for Laplacian convolution. No OpenCV dependency.
The Laplacian variance measures edge sharpness: higher values mean
sharper images, lower values mean more blur.

Threshold 100.0 is a fixed pass/fail value per project decisions.
Quality checks are advisory only -- they never block import.
"""

from __future__ import annotations

import numpy as np
from PIL import Image
from scipy.signal import convolve2d

# Standard 3x3 Laplacian kernel (same operator as cv2.Laplacian)
_LAPLACIAN_KERNEL = np.array([
    [0,  1,  0],
    [1, -4,  1],
    [0,  1,  0],
], dtype=np.float64)

BLUR_THRESHOLD: float = 100.0
"""Fixed pass/fail threshold for blur detection. Images with Laplacian
variance below this value are flagged as blurry. Not user-adjustable."""


def compute_blur_score(img: Image.Image) -> float:
    """Compute Laplacian variance as a blur/sharpness metric.

    Higher values indicate sharper images. Lower values indicate blur.
    Uses grayscale conversion internally.

    Args:
        img: PIL Image in any mode (RGB, RGBA, L, etc.).

    Returns:
        Laplacian variance as a float. Higher = sharper.
    """
    gray = np.array(img.convert("L"), dtype=np.float64)
    laplacian = convolve2d(gray, _LAPLACIAN_KERNEL, mode="valid")
    return float(laplacian.var())


def is_blurry(img: Image.Image) -> bool:
    """Check if an image is blurry (Laplacian variance below threshold).

    Args:
        img: PIL Image in any mode.

    Returns:
        True if the image's blur score is below BLUR_THRESHOLD.
    """
    return compute_blur_score(img) < BLUR_THRESHOLD
