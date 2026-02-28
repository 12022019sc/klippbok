"""Tests for klippbok.image.quality -- blur detection via Laplacian variance.

Uses Pillow to generate synthetic test images with known sharpness properties:
- Solid color: near-zero variance (blurry)
- Checkerboard: very high variance (sharp)
No file I/O -- all in-memory PIL Images.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from klippbok.image.quality import BLUR_THRESHOLD, compute_blur_score, is_blurry


# ---------------------------------------------------------------------------
# Helpers -- generate test images with known properties
# ---------------------------------------------------------------------------

def _solid_image(size: tuple[int, int] = (256, 256), color: int = 128) -> Image.Image:
    """Solid gray image -- no edges, Laplacian variance near 0."""
    return Image.new("RGB", size, (color, color, color))


def _checkerboard_image(size: tuple[int, int] = (256, 256)) -> Image.Image:
    """Alternating black/white pixel checkerboard -- maximum edge density."""
    width, height = size
    arr = np.zeros((height, width), dtype=np.uint8)
    # Alternating pixels: (x+y) even = white, odd = black
    for y in range(height):
        for x in range(width):
            arr[y, x] = 255 if (x + y) % 2 == 0 else 0
    return Image.fromarray(arr, mode="L").convert("RGB")


# ---------------------------------------------------------------------------
# compute_blur_score
# ---------------------------------------------------------------------------

class TestComputeBlurScore:
    """Tests for compute_blur_score() -- Laplacian variance metric."""

    def test_blur_score_solid_image_low(self) -> None:
        """Solid color 256x256 returns score near 0 (< 10)."""
        img = _solid_image()
        score = compute_blur_score(img)
        assert score < 10.0, f"Expected < 10 for solid image, got {score}"

    def test_blur_score_checkerboard_high(self) -> None:
        """256x256 checkerboard returns high score (> 1000)."""
        img = _checkerboard_image()
        score = compute_blur_score(img)
        assert score > 1000.0, f"Expected > 1000 for checkerboard, got {score}"

    def test_blur_score_returns_float(self) -> None:
        """Result is a float."""
        img = _solid_image()
        result = compute_blur_score(img)
        assert isinstance(result, float)

    def test_blur_score_positive(self) -> None:
        """Result is always >= 0."""
        img = _solid_image()
        assert compute_blur_score(img) >= 0.0

    def test_blur_score_grayscale_image(self) -> None:
        """Grayscale L-mode image works without error."""
        img = Image.new("L", (256, 256), 128)
        score = compute_blur_score(img)
        assert isinstance(score, float)
        assert score >= 0.0

    def test_blur_score_rgba_image(self) -> None:
        """RGBA image works -- internally converts to grayscale."""
        img = Image.new("RGBA", (256, 256), (128, 64, 32, 255))
        score = compute_blur_score(img)
        assert isinstance(score, float)
        assert score >= 0.0

    def test_blur_score_small_image(self) -> None:
        """Very small 32x32 image doesn't crash."""
        img = _solid_image(size=(32, 32))
        score = compute_blur_score(img)
        assert isinstance(score, float)


# ---------------------------------------------------------------------------
# is_blurry
# ---------------------------------------------------------------------------

class TestIsBlurry:
    """Tests for is_blurry() -- fixed-threshold blur classification."""

    def test_solid_image_is_blurry(self) -> None:
        """Solid color image is detected as blurry."""
        img = _solid_image()
        assert is_blurry(img) is True

    def test_checkerboard_not_blurry(self) -> None:
        """High-contrast checkerboard is NOT blurry."""
        img = _checkerboard_image()
        assert is_blurry(img) is False

    def test_blur_threshold_constant(self) -> None:
        """BLUR_THRESHOLD is exactly 100.0."""
        assert BLUR_THRESHOLD == 100.0
