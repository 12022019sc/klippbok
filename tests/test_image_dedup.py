"""Tests for klippbok.image.dedup -- perceptual hash and near-duplicate detection.

Tests use real Pillow images created on disk via tmp_path fixture.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PIL import Image

from klippbok.image.dedup import (
    PHASH_THRESHOLD,
    are_near_duplicates,
    compute_phash,
    select_keeper,
)
from klippbok.image.models import ImageMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_solid(path: Path, color: tuple[int, int, int], size: tuple[int, int] = (100, 100)) -> Path:
    """Save a solid-color PNG image."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color=color)
    img.save(path, format="PNG")
    return path


def _save_textured(path: Path, base_color: tuple[int, int, int], size: tuple[int, int] = (128, 128)) -> Path:
    """Save an image with texture (gradient) so pHash has meaningful content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    import numpy as np
    w, h = size
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            arr[y, x] = [
                min(255, base_color[0] + x * 2),
                min(255, base_color[1] + y * 2),
                min(255, base_color[2] + (x + y)),
            ]
    img = Image.fromarray(arr, "RGB")
    img.save(path, format="PNG")
    return path


def _make_metadata(
    path: Path,
    width: int,
    height: int,
    fmt: str = "png",
) -> ImageMetadata:
    """Create an ImageMetadata for testing select_keeper."""
    return ImageMetadata(
        path=path,
        width=width,
        height=height,
        format=fmt,
        color_mode="RGB",
    )


# ---------------------------------------------------------------------------
# compute_phash tests
# ---------------------------------------------------------------------------

class TestComputePhash:
    def test_phash_returns_hex_string(self, tmp_path: Path):
        img_path = _save_solid(tmp_path / "red.png", (255, 0, 0))
        result = compute_phash(img_path)
        assert isinstance(result, str)
        assert len(result) > 0
        assert re.fullmatch(r"[0-9a-f]+", result), f"Not hex: {result!r}"

    def test_phash_consistent(self, tmp_path: Path):
        img_path = _save_solid(tmp_path / "red.png", (255, 0, 0))
        h1 = compute_phash(img_path)
        h2 = compute_phash(img_path)
        assert h1 == h2

    def test_phash_identical_images_same_hash(self, tmp_path: Path):
        # Same textured content at different paths -- must produce identical hash
        path_a = _save_textured(tmp_path / "a.png", (200, 100, 50))
        path_b = _save_textured(tmp_path / "b.png", (200, 100, 50))
        assert compute_phash(path_a) == compute_phash(path_b)

    def test_phash_different_images_different_hash(self, tmp_path: Path):
        # Use textured images with clearly different gradient patterns
        red_path = _save_textured(tmp_path / "red_gradient.png", (200, 10, 10))
        # Inverted gradient -- very different frequency content
        blue_path = _save_textured(tmp_path / "blue_gradient.png", (10, 10, 200))
        assert compute_phash(red_path) != compute_phash(blue_path)


# ---------------------------------------------------------------------------
# are_near_duplicates tests
# ---------------------------------------------------------------------------

class TestAreNearDuplicates:
    def test_identical_hashes_are_duplicates(self, tmp_path: Path):
        # Use a textured image so pHash has meaningful content
        img_path = _save_textured(tmp_path / "textured.png", (150, 80, 30))
        h = compute_phash(img_path)
        assert are_near_duplicates(h, h) is True

    def test_resized_image_is_near_duplicate(self, tmp_path: Path):
        original = _save_textured(tmp_path / "original.png", (150, 100, 50), size=(128, 128))
        # Resize to 64x64 -- pHash should be similar (same visual content)
        img = Image.open(original)
        small = img.resize((64, 64))
        small_path = tmp_path / "small.png"
        small.save(small_path, format="PNG")
        h_orig = compute_phash(original)
        h_small = compute_phash(small_path)
        assert are_near_duplicates(h_orig, h_small) is True

    def test_different_images_not_duplicates(self, tmp_path: Path):
        # Red gradient (increasing) vs inverted gradient -- very different DCT
        red_path = _save_textured(tmp_path / "red_grad.png", (200, 10, 10))
        # Checkerboard -- completely different frequency content
        checker = Image.new("RGB", (128, 128))
        pixels = checker.load()
        for x in range(128):
            for y in range(128):
                pixels[x, y] = (255, 255, 255) if (x // 8 + y // 8) % 2 == 0 else (0, 0, 0)
        checker_path = tmp_path / "checker.png"
        checker.save(checker_path, format="PNG")
        h_red = compute_phash(red_path)
        h_checker = compute_phash(checker_path)
        assert are_near_duplicates(h_red, h_checker) is False

    def test_phash_threshold_constant(self):
        assert PHASH_THRESHOLD == 10


# ---------------------------------------------------------------------------
# select_keeper tests
# ---------------------------------------------------------------------------

class TestSelectKeeper:
    def test_keeper_highest_resolution(self, tmp_path: Path):
        large = _make_metadata(tmp_path / "large.png", 1920, 1080, "png")
        small = _make_metadata(tmp_path / "small.png", 640, 480, "png")
        assert select_keeper([large, small]) == large
        assert select_keeper([small, large]) == large

    def test_keeper_same_resolution_prefers_png(self, tmp_path: Path):
        png_img = _make_metadata(tmp_path / "img.png", 512, 512, "png")
        jpg_img = _make_metadata(tmp_path / "img.jpg", 512, 512, "jpeg")
        assert select_keeper([png_img, jpg_img]) == png_img
        assert select_keeper([jpg_img, png_img]) == png_img

    def test_keeper_same_resolution_prefers_webp_over_jpeg(self, tmp_path: Path):
        webp_img = _make_metadata(tmp_path / "img.webp", 512, 512, "webp")
        jpg_img = _make_metadata(tmp_path / "img.jpg", 512, 512, "jpeg")
        assert select_keeper([webp_img, jpg_img]) == webp_img
        assert select_keeper([jpg_img, webp_img]) == webp_img

    def test_keeper_single_image(self, tmp_path: Path):
        only = _make_metadata(tmp_path / "only.png", 800, 600, "png")
        assert select_keeper([only]) == only

    def test_keeper_resolution_trumps_format(self, tmp_path: Path):
        large_jpg = _make_metadata(tmp_path / "large.jpg", 1024, 1024, "jpeg")
        small_png = _make_metadata(tmp_path / "small.png", 512, 512, "png")
        # 1024x1024 JPEG beats 512x512 PNG -- resolution wins
        assert select_keeper([large_jpg, small_png]) == large_jpg

    def test_keeper_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            select_keeper([])

    def test_keeper_png_over_tiff_same_resolution(self, tmp_path: Path):
        png_img = _make_metadata(tmp_path / "img.png", 512, 512, "png")
        tiff_img = _make_metadata(tmp_path / "img.tiff", 512, 512, "tiff")
        assert select_keeper([png_img, tiff_img]) == png_img
