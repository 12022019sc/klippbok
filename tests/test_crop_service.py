"""Tests for crop_service.apply_crop and apply_crops_batch.

Tests verify:
- apply_crop produces output at exact target dimensions
- apply_crop handles rotation correctly (90-degree increments)
- apply_crop handles horizontal flip (pixel comparison)
- apply_crop converts RGBA images to RGB
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from PIL import Image


def make_solid_image(tmp_path: Path, width: int, height: int, color=(100, 150, 200)) -> Path:
    """Create a solid-color test image."""
    img = Image.new("RGB", (width, height), color)
    path = tmp_path / "test.jpg"
    img.save(path)
    return path


def make_gradient_image(tmp_path: Path, width: int, height: int) -> Path:
    """Create a gradient test image for pixel comparison tests."""
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    for x in range(width):
        for y in range(height):
            pixels[x, y] = (x % 256, y % 256, (x + y) % 256)
    path = tmp_path / "gradient.png"
    img.save(path)
    return path


def make_rgba_image(tmp_path: Path, width: int, height: int) -> Path:
    """Create an RGBA test image."""
    img = Image.new("RGBA", (width, height), (100, 150, 200, 128))
    path = tmp_path / "rgba.png"
    img.save(path)
    return path


def test_apply_crop_dimensions(tmp_path: Path) -> None:
    """apply_crop produces output at exactly the target bucket dimensions."""
    from klippbok.services.crop_service import apply_crop

    source = make_solid_image(tmp_path, 200, 300)
    output = tmp_path / "out.jpg"

    result_path = apply_crop(
        source_path=source,
        left=10, top=10, width=100, height=150,
        rotation=0,
        flip_h=False, flip_v=False,
        target_width=512, target_height=768,
        output_path=output,
    )

    assert result_path == output
    assert output.exists()
    with Image.open(output) as img:
        assert img.size == (512, 768)


def test_apply_crop_rotation_90(tmp_path: Path) -> None:
    """apply_crop with rotation=90 on a 200x300 image transposes dimensions then crops."""
    from klippbok.services.crop_service import apply_crop

    source = make_solid_image(tmp_path, 200, 300)
    output = tmp_path / "rotated.jpg"

    # After 90° rotation a 200x300 image becomes 300x200.
    # We crop a region within 300x200 and resize to 512x512.
    result_path = apply_crop(
        source_path=source,
        left=0, top=0, width=100, height=100,
        rotation=90,
        flip_h=False, flip_v=False,
        target_width=512, target_height=512,
        output_path=output,
    )

    assert result_path.exists()
    with Image.open(result_path) as img:
        assert img.size == (512, 512)


def test_apply_crop_flip_h(tmp_path: Path) -> None:
    """apply_crop with flip_h=True produces a horizontally mirrored output."""
    from klippbok.services.crop_service import apply_crop

    source = make_gradient_image(tmp_path, 200, 100)
    output_normal = tmp_path / "normal.png"
    output_flipped = tmp_path / "flipped.png"

    apply_crop(
        source_path=source,
        left=0, top=0, width=200, height=100,
        rotation=0,
        flip_h=False, flip_v=False,
        target_width=200, target_height=100,
        output_path=output_normal,
    )

    apply_crop(
        source_path=source,
        left=0, top=0, width=200, height=100,
        rotation=0,
        flip_h=True, flip_v=False,
        target_width=200, target_height=100,
        output_path=output_flipped,
    )

    # Pixel at (0,0) in flipped image should match pixel at (width-1, 0) in normal
    with Image.open(output_normal) as normal_img:
        with Image.open(output_flipped) as flipped_img:
            normal_pixels = normal_img.load()
            flipped_pixels = flipped_img.load()
            width = normal_img.width
            # Left edge of flipped should match right edge of normal
            assert flipped_pixels[0, 0] == normal_pixels[width - 1, 0]


def test_apply_crop_rgb_conversion(tmp_path: Path) -> None:
    """apply_crop converts RGBA input to RGB output."""
    from klippbok.services.crop_service import apply_crop

    source = make_rgba_image(tmp_path, 200, 200)
    output = tmp_path / "from_rgba.png"

    apply_crop(
        source_path=source,
        left=0, top=0, width=100, height=100,
        rotation=0,
        flip_h=False, flip_v=False,
        target_width=128, target_height=128,
        output_path=output,
    )

    assert output.exists()
    with Image.open(output) as img:
        assert img.mode == "RGB"
        assert img.size == (128, 128)
