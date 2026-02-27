"""Tests for klippbok.image.probe -- uses real Pillow images on disk.

Creates test images using Pillow fixtures in tmp_path. No mocking.
"""

from pathlib import Path

import pytest
from PIL import Image

from klippbok.image.errors import ImageProbeError
from klippbok.image.probe import probe_image


# ---------------------------------------------------------------------------
# Fixtures -- create real images on disk
# ---------------------------------------------------------------------------

@pytest.fixture()
def rgb_png(tmp_path: Path) -> Path:
    """Create a valid 100x80 RGB PNG."""
    path = tmp_path / "test_rgb.png"
    img = Image.new("RGB", (100, 80), color=(255, 0, 0))
    img.save(path, format="PNG")
    return path


@pytest.fixture()
def rgb_jpeg(tmp_path: Path) -> Path:
    """Create a valid 120x90 RGB JPEG."""
    path = tmp_path / "test_rgb.jpg"
    img = Image.new("RGB", (120, 90), color=(0, 255, 0))
    img.save(path, format="JPEG")
    return path


@pytest.fixture()
def rgba_png(tmp_path: Path) -> Path:
    """Create a valid 100x100 RGBA PNG (has alpha)."""
    path = tmp_path / "test_rgba.png"
    img = Image.new("RGBA", (100, 100), color=(0, 0, 255, 128))
    img.save(path, format="PNG")
    return path


@pytest.fixture()
def webp_image(tmp_path: Path) -> Path:
    """Create a valid 200x150 RGB WebP."""
    path = tmp_path / "test.webp"
    img = Image.new("RGB", (200, 150), color=(128, 128, 128))
    img.save(path, format="WEBP")
    return path


@pytest.fixture()
def corrupt_image(tmp_path: Path) -> Path:
    """Create a corrupt file with .png extension."""
    path = tmp_path / "corrupt.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\ngarbage_data_not_a_real_image")
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestProbeImage:
    """Tests for probe_image function."""

    def test_rgb_png(self, rgb_png: Path) -> None:
        """Probe returns correct metadata for RGB PNG."""
        meta = probe_image(rgb_png)
        assert meta.width == 100
        assert meta.height == 80
        assert meta.format == "png"
        assert meta.color_mode == "RGB"
        assert meta.has_alpha is False
        assert meta.is_corrupt is False
        assert meta.file_size is not None
        assert meta.file_size > 0

    def test_rgb_jpeg(self, rgb_jpeg: Path) -> None:
        """Probe returns correct metadata for RGB JPEG."""
        meta = probe_image(rgb_jpeg)
        assert meta.width == 120
        assert meta.height == 90
        assert meta.format == "jpeg"
        assert meta.color_mode == "RGB"
        assert meta.has_alpha is False
        assert meta.is_corrupt is False

    def test_rgba_png(self, rgba_png: Path) -> None:
        """Probe detects alpha channel in RGBA PNG."""
        meta = probe_image(rgba_png)
        assert meta.width == 100
        assert meta.height == 100
        assert meta.format == "png"
        assert meta.color_mode == "RGBA"
        assert meta.has_alpha is True
        assert meta.is_corrupt is False

    def test_webp(self, webp_image: Path) -> None:
        """Probe returns correct metadata for WebP."""
        meta = probe_image(webp_image)
        assert meta.width == 200
        assert meta.height == 150
        assert meta.format == "webp"
        assert meta.color_mode == "RGB"
        assert meta.is_corrupt is False

    def test_corrupt_file(self, corrupt_image: Path) -> None:
        """Probe returns is_corrupt=True for corrupt file."""
        meta = probe_image(corrupt_image)
        assert meta.is_corrupt is True
        assert meta.width == 0
        assert meta.height == 0
        assert meta.format == "unknown"
        assert meta.color_mode == "unknown"
        assert meta.file_size is not None

    def test_nonexistent_path(self, tmp_path: Path) -> None:
        """Probe raises ImageProbeError for nonexistent file."""
        fake_path = tmp_path / "does_not_exist.png"
        with pytest.raises(ImageProbeError, match="does not exist"):
            probe_image(fake_path)

    def test_directory_path(self, tmp_path: Path) -> None:
        """Probe raises ImageProbeError for a directory path."""
        with pytest.raises(ImageProbeError, match="not a file"):
            probe_image(tmp_path)

    def test_path_is_stored(self, rgb_png: Path) -> None:
        """Probe stores the path on the metadata."""
        meta = probe_image(rgb_png)
        assert meta.path == rgb_png

    def test_display_resolution(self, rgb_png: Path) -> None:
        """Probed metadata has correct display_resolution property."""
        meta = probe_image(rgb_png)
        assert meta.display_resolution == "100x80"

    def test_pixel_count(self, rgb_png: Path) -> None:
        """Probed metadata has correct pixel_count property."""
        meta = probe_image(rgb_png)
        assert meta.pixel_count == 100 * 80
