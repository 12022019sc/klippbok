"""Tests for klippbok.services.image_service.

Uses real Pillow images on disk via tmp_path fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from klippbok.services.image_service import (
    import_image,
    import_images,
    validate_image_file,
)
from klippbok.video.models import IssueCode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_png(path: Path, width: int = 512, height: int = 512) -> Path:
    """Create a valid PNG image at the given path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    img.save(path, format="PNG")
    return path


def _create_corrupt_file(path: Path) -> Path:
    """Create a file with .png extension but corrupt content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"this is not a valid image file at all")
    return path


# ---------------------------------------------------------------------------
# import_image
# ---------------------------------------------------------------------------

class TestImportImage:
    def test_valid_png(self, tmp_path: Path):
        img_path = _create_png(tmp_path / "photo.png", 800, 600)
        metadata, validation = import_image(img_path)
        assert metadata.width == 800
        assert metadata.height == 600
        assert metadata.format == "png"
        assert metadata.color_mode == "RGB"
        assert not metadata.is_corrupt
        assert validation.is_valid

    def test_valid_jpeg(self, tmp_path: Path):
        img_path = tmp_path / "photo.jpg"
        img = Image.new("RGB", (640, 480), color=(200, 100, 50))
        img.save(img_path, format="JPEG")
        metadata, validation = import_image(img_path)
        assert metadata.format == "jpeg"
        assert validation.is_valid

    def test_corrupt_file(self, tmp_path: Path):
        img_path = _create_corrupt_file(tmp_path / "bad.png")
        metadata, validation = import_image(img_path)
        assert metadata.is_corrupt
        assert not validation.is_valid
        error_codes = [i.code for i in validation.errors]
        assert IssueCode.IMAGE_CORRUPT in error_codes

    def test_below_min_resolution(self, tmp_path: Path):
        img_path = _create_png(tmp_path / "tiny.png", 64, 64)
        metadata, validation = import_image(img_path, min_resolution=256)
        assert not validation.is_valid
        error_codes = [i.code for i in validation.errors]
        assert IssueCode.IMAGE_BELOW_MIN_RESOLUTION in error_codes

    def test_custom_resolution_thresholds(self, tmp_path: Path):
        img_path = _create_png(tmp_path / "ok.png", 128, 128)
        metadata, validation = import_image(img_path, min_resolution=64)
        assert validation.is_valid

    def test_rgba_warning(self, tmp_path: Path):
        img_path = tmp_path / "alpha.png"
        img = Image.new("RGBA", (512, 512), color=(128, 128, 128, 255))
        img.save(img_path, format="PNG")
        metadata, validation = import_image(img_path)
        assert metadata.has_alpha
        assert metadata.color_mode == "RGBA"
        warning_codes = [i.code for i in validation.warnings]
        assert IssueCode.IMAGE_RGBA_CONVERSION in warning_codes
        # RGBA is a warning, not an error -- still valid
        assert validation.is_valid


# ---------------------------------------------------------------------------
# import_images
# ---------------------------------------------------------------------------

class TestImportImages:
    def test_directory_with_images(self, tmp_path: Path):
        _create_png(tmp_path / "a.png", 512, 512)
        _create_png(tmp_path / "b.png", 640, 480)
        results = import_images(tmp_path)
        assert len(results) == 2

    def test_empty_directory(self, tmp_path: Path):
        results = import_images(tmp_path)
        assert results == []

    def test_mixed_files_only_images(self, tmp_path: Path):
        """Non-image files are ignored."""
        _create_png(tmp_path / "photo.png")
        (tmp_path / "clip.mp4").write_bytes(b"fake video")
        (tmp_path / "notes.txt").write_text("just a caption")
        results = import_images(tmp_path)
        assert len(results) == 1

    def test_recursive(self, tmp_path: Path):
        _create_png(tmp_path / "a.png")
        _create_png(tmp_path / "subdir" / "b.png")
        results = import_images(tmp_path, recursive=True)
        assert len(results) == 2

    def test_non_recursive(self, tmp_path: Path):
        _create_png(tmp_path / "a.png")
        _create_png(tmp_path / "subdir" / "b.png")
        results = import_images(tmp_path, recursive=False)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# validate_image_file
# ---------------------------------------------------------------------------

class TestValidateImageFile:
    def test_valid_image(self, tmp_path: Path):
        img_path = _create_png(tmp_path / "good.png", 1024, 768)
        validation = validate_image_file(img_path)
        assert validation.is_valid
        assert len(validation.errors) == 0

    def test_invalid_image(self, tmp_path: Path):
        img_path = _create_corrupt_file(tmp_path / "bad.png")
        validation = validate_image_file(img_path)
        assert not validation.is_valid

    def test_returns_only_validation(self, tmp_path: Path):
        """validate_image_file returns ImageValidation, not a tuple."""
        img_path = _create_png(tmp_path / "test.png")
        result = validate_image_file(img_path)
        from klippbok.image.models import ImageValidation
        assert isinstance(result, ImageValidation)
