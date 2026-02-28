"""Tests for klippbok.services.image_service.

Uses real Pillow images on disk via tmp_path fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from klippbok.services.image_service import (
    batch_import_images,
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


# ---------------------------------------------------------------------------
# Helpers for batch import tests
# ---------------------------------------------------------------------------

def _create_textured_png(path: Path, width: int = 512, height: int = 512, seed: int = 0) -> Path:
    """Create a visually distinct textured PNG image.

    Uses a gradient that varies by seed so different calls produce
    images with distinct pHash values.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    import numpy as np
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            arr[y, x] = [
                (x * 2 + seed * 50) % 256,
                (y * 2 + seed * 80) % 256,
                (x + y + seed * 30) % 256,
            ]
    img = Image.fromarray(arr, "RGB")
    img.save(path, format="PNG")
    return path


# ---------------------------------------------------------------------------
# batch_import_images
# ---------------------------------------------------------------------------

class TestBatchImportImages:
    def test_batch_import_discovers_images(self, tmp_path: Path):
        img_dir = tmp_path / "images"
        _create_textured_png(img_dir / "a.png", seed=1)
        _create_textured_png(img_dir / "b.png", seed=2)
        _create_textured_png(img_dir / "c.png", seed=3)
        (img_dir / "notes.txt").write_text("not an image")

        report = batch_import_images(img_dir, tmp_path)

        assert report.total_discovered == 3  # text file ignored

    def test_batch_import_skips_existing(self, tmp_path: Path):
        img_dir = tmp_path / "images"
        _create_textured_png(img_dir / "a.png", seed=1)
        _create_textured_png(img_dir / "b.png", seed=2)

        # First import
        report1 = batch_import_images(img_dir, tmp_path)
        assert report1.skipped_existing == 0
        assert report1.imported == 2

        # Second import -- both should be skipped
        report2 = batch_import_images(img_dir, tmp_path)
        assert report2.skipped_existing == 2
        assert report2.imported == 0

    def test_batch_import_rejects_corrupt(self, tmp_path: Path):
        img_dir = tmp_path / "images"
        _create_textured_png(img_dir / "good.png", seed=1)
        _create_corrupt_file(img_dir / "bad.png")

        report = batch_import_images(img_dir, tmp_path)

        assert report.total_discovered == 2
        assert report.rejected > 0

    def test_batch_import_with_buckets(self, tmp_path: Path):
        from klippbok.config.model_profiles import generate_buckets
        img_dir = tmp_path / "images"
        _create_textured_png(img_dir / "photo.png", width=512, height=512, seed=10)

        buckets = generate_buckets(512)
        report = batch_import_images(img_dir, tmp_path, buckets=buckets)

        # Non-corrupt entry should have a bucket assigned
        non_skipped = [e for e in report.entries if not e.skipped]
        assert len(non_skipped) > 0
        assigned = [e for e in non_skipped if e.bucket is not None]
        assert len(assigned) > 0

    def test_batch_import_blur_scores(self, tmp_path: Path):
        img_dir = tmp_path / "images"
        _create_textured_png(img_dir / "sharp.png", seed=5)

        report = batch_import_images(img_dir, tmp_path)

        non_skipped = [e for e in report.entries if not e.skipped]
        assert len(non_skipped) > 0
        for entry in non_skipped:
            if entry.metadata and not entry.metadata.is_corrupt:
                assert entry.blur_score is not None
                assert isinstance(entry.blur_score, float)

    def test_batch_import_phash_computed(self, tmp_path: Path):
        img_dir = tmp_path / "images"
        _create_textured_png(img_dir / "photo.png", seed=7)

        report = batch_import_images(img_dir, tmp_path)

        non_corrupt = [
            e for e in report.entries
            if not e.skipped and e.metadata and not e.metadata.is_corrupt
        ]
        assert len(non_corrupt) > 0
        for entry in non_corrupt:
            assert entry.phash is not None
            assert isinstance(entry.phash, str)
            assert len(entry.phash) > 0

    def test_batch_import_report_counts_accurate(self, tmp_path: Path):
        img_dir = tmp_path / "images"
        _create_textured_png(img_dir / "a.png", seed=1)
        _create_textured_png(img_dir / "b.png", seed=2)

        report = batch_import_images(img_dir, tmp_path)

        # total_discovered == imported + skipped_existing
        assert report.total_discovered == report.imported + report.skipped_existing

    def test_batch_import_persists_to_manifest(self, tmp_path: Path):
        img_dir = tmp_path / "images"
        _create_textured_png(img_dir / "photo.png", seed=3)

        batch_import_images(img_dir, tmp_path)

        manifest_path = tmp_path / ".klippbok" / "manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "images" in data
        assert len(data["images"]) > 0

    def test_batch_import_manifest_roundtrip(self, tmp_path: Path):
        img_dir = tmp_path / "images"
        _create_textured_png(img_dir / "photo.png", seed=4)

        report = batch_import_images(img_dir, tmp_path)

        manifest_path = tmp_path / ".klippbok" / "manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))

        assert "images" in data
        saved_entries = data["images"]
        non_skipped_entries = [e for e in report.entries if not e.skipped]
        # All non-skipped entries should be in manifest
        assert len(saved_entries) == len(non_skipped_entries)
        # Each entry has required fields
        for entry in saved_entries:
            assert "type" in entry
            assert entry["type"] == "image"
            assert "path" in entry
            assert "status" in entry

    def test_batch_import_dedup_within_batch(self, tmp_path: Path):
        """Importing two identical images in same batch flags one as near-duplicate."""
        img_dir = tmp_path / "images"
        original = _create_textured_png(img_dir / "original.png", seed=9)
        # Copy identical content to a different filename
        import shutil
        shutil.copy(original, img_dir / "copy.png")

        report = batch_import_images(img_dir, tmp_path)

        assert report.near_duplicates_flagged > 0
        near_dup_entries = [e for e in report.entries if e.is_near_duplicate]
        assert len(near_dup_entries) > 0

    def test_batch_import_bucket_distribution(self, tmp_path: Path):
        from klippbok.config.model_profiles import generate_buckets
        img_dir = tmp_path / "images"
        _create_textured_png(img_dir / "a.png", width=512, height=512, seed=11)
        _create_textured_png(img_dir / "b.png", width=512, height=512, seed=12)

        buckets = generate_buckets(512)
        report = batch_import_images(img_dir, tmp_path, buckets=buckets)

        dist = report.bucket_distribution
        # Should have at least one bucket with count > 0
        assert len(dist) > 0
        assert all(count > 0 for count in dist.values())
