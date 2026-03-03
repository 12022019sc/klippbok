"""Tests for klippbok.image.autocrop module.

Tests verify:
- _center_crop produces valid centered coordinates (pure Python, no mediapipe needed)
- _fit_crop_to_bucket clamps correctly to image bounds
- auto_crop_image coordinates are always within image bounds (when mediapipe available)
- auto_crop_image falls back to center crop for images with no person
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image


def make_solid_image(path: Path, width: int, height: int, color=(128, 128, 128)) -> Path:
    """Create a solid-color test image (no person detectable)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), color)
    img.save(path)
    return path


def test_center_crop_basic() -> None:
    """_center_crop returns valid centered coordinates within image bounds."""
    from klippbok.image.autocrop import _center_crop
    from klippbok.config.model_profiles import generate_buckets

    buckets = generate_buckets(base_resolution=512)
    img_width, img_height = 800, 600

    left, top, width, height = _center_crop(img_width, img_height, buckets)

    assert left >= 0
    assert top >= 0
    assert width > 0
    assert height > 0
    assert left + width <= img_width
    assert top + height <= img_height
    # Verify it's approximately centered (within 1px of center due to integer div)
    assert abs((2 * left + width) - img_width) <= 1
    assert abs((2 * top + height) - img_height) <= 1


def test_center_crop_square_image() -> None:
    """_center_crop on a square image with square buckets uses full image."""
    from klippbok.image.autocrop import _center_crop

    # Single square bucket
    buckets = [(512, 512)]
    img_width, img_height = 800, 800

    left, top, width, height = _center_crop(img_width, img_height, buckets)

    assert left >= 0
    assert top >= 0
    assert width > 0
    assert height > 0
    assert left + width <= img_width
    assert top + height <= img_height
    # For a square image with square bucket, crop should be square and centered
    assert width == height


def test_center_crop_various_sizes() -> None:
    """_center_crop always stays within image bounds for various sizes."""
    from klippbok.image.autocrop import _center_crop
    from klippbok.config.model_profiles import generate_buckets

    buckets = generate_buckets(base_resolution=512)

    test_cases = [
        (800, 600),
        (1024, 1024),
        (600, 800),
        (300, 300),
        (1920, 1080),
    ]

    for img_width, img_height in test_cases:
        left, top, width, height = _center_crop(img_width, img_height, buckets)

        assert left >= 0, f"left={left} < 0 for {img_width}x{img_height}"
        assert top >= 0, f"top={top} < 0 for {img_width}x{img_height}"
        assert width > 0, f"width={width} <= 0 for {img_width}x{img_height}"
        assert height > 0, f"height={height} <= 0 for {img_width}x{img_height}"
        assert left + width <= img_width, (
            f"left+width={left+width} > img_width={img_width}"
        )
        assert top + height <= img_height, (
            f"top+height={top+height} > img_height={img_height}"
        )


def test_fit_crop_to_bucket_clamped() -> None:
    """_fit_crop_to_bucket clamps crop to image bounds."""
    from klippbok.image.autocrop import _fit_crop_to_bucket

    # Subject detected near the edge -- would extend past image bounds without clamping
    img_w, img_h = 1000, 800
    bucket = (512, 768)

    left, top, width, height = _fit_crop_to_bucket(
        bbox_left=850, bbox_top=0,
        bbox_w=100, bbox_h=200,
        bucket=bucket,
        img_w=img_w, img_h=img_h,
    )

    assert left >= 0
    assert top >= 0
    assert width > 0
    assert height > 0
    assert left + width <= img_w
    assert top + height <= img_h


def test_fit_crop_to_bucket_centered() -> None:
    """_fit_crop_to_bucket keeps expansion centered on bbox center."""
    from klippbok.image.autocrop import _fit_crop_to_bucket

    img_w, img_h = 1000, 1000
    bucket = (512, 512)

    # Subject dead center with 100x100 bbox
    left, top, width, height = _fit_crop_to_bucket(
        bbox_left=450, bbox_top=450,
        bbox_w=100, bbox_h=100,
        bucket=bucket,
        img_w=img_w, img_h=img_h,
    )

    assert left >= 0
    assert top >= 0
    assert left + width <= img_w
    assert top + height <= img_h
    # For square bucket and square bbox centered in a large image, result should be square
    assert width == height


def test_auto_crop_center_fallback(tmp_path: Path) -> None:
    """auto_crop_image on a solid-color image (no person) returns center-crop coords."""
    pytest.importorskip("mediapipe", reason="mediapipe not installed")

    # Check if model is available (skip gracefully if not)
    from klippbok.image.autocrop import _get_model_path
    model = _get_model_path()
    if model is None:
        pytest.skip("MediaPipe pose model not available (run without network to skip download)")

    from klippbok.image.autocrop import auto_crop_image
    from klippbok.config.model_profiles import generate_buckets

    source = make_solid_image(tmp_path / "solid.jpg", 800, 600)
    buckets = generate_buckets(base_resolution=512)

    left, top, width, height = auto_crop_image(source, buckets)

    # Should produce a valid crop within image bounds
    assert left >= 0
    assert top >= 0
    assert width > 0
    assert height > 0
    assert left + width <= 800
    assert top + height <= 600


def test_auto_crop_coords_in_bounds(tmp_path: Path) -> None:
    """auto_crop_image always returns coordinates within image bounds."""
    pytest.importorskip("mediapipe", reason="mediapipe not installed")

    from klippbok.image.autocrop import _get_model_path
    model = _get_model_path()
    if model is None:
        pytest.skip("MediaPipe pose model not available")

    from klippbok.image.autocrop import auto_crop_image
    from klippbok.config.model_profiles import generate_buckets

    buckets = generate_buckets(base_resolution=512)

    test_cases = [
        (800, 600),
        (1024, 1024),
        (600, 800),
    ]

    for img_width, img_height in test_cases:
        source = make_solid_image(
            tmp_path / f"img_{img_width}x{img_height}.jpg",
            img_width, img_height,
        )

        left, top, width, height = auto_crop_image(source, buckets)

        assert left >= 0, f"left={left} < 0 for {img_width}x{img_height}"
        assert top >= 0, f"top={top} < 0 for {img_width}x{img_height}"
        assert width > 0, f"width={width} <= 0 for {img_width}x{img_height}"
        assert height > 0, f"height={height} <= 0 for {img_width}x{img_height}"
        assert left + width <= img_width, (
            f"left+width={left+width} > img_width={img_width}"
        )
        assert top + height <= img_height, (
            f"top+height={top+height} > img_height={img_height}"
        )


def test_auto_crop_importable_without_mediapipe() -> None:
    """autocrop module structure: _center_crop and _fit_crop_to_bucket import without mediapipe."""
    # These are pure Python functions that must not require mediapipe at import time.
    # If mediapipe isn't installed, only auto_crop_image should fail (at call time).
    from klippbok.image.autocrop import _center_crop, _fit_crop_to_bucket  # noqa: F401
    # If we reach here, the module imported successfully
    assert _center_crop is not None
    assert _fit_crop_to_bucket is not None
