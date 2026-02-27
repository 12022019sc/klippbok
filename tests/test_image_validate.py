"""Tests for klippbok.image.validate -- pure Python, no Pillow needed.

Tests accumulative validation logic with hand-crafted ImageMetadata.
"""

from pathlib import Path

import pytest

from klippbok.image.models import ImageMetadata, ImageValidation
from klippbok.image.validate import validate_image
from klippbok.video.models import IssueCode, Severity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_meta(**kwargs) -> ImageMetadata:
    """Create ImageMetadata with sensible defaults."""
    defaults = dict(
        path=Path("/test/photo.png"),
        width=1920,
        height=1080,
        format="png",
        color_mode="RGB",
        file_size=100_000,
    )
    defaults.update(kwargs)
    return ImageMetadata(**defaults)


def _issue_codes(result: ImageValidation) -> list[IssueCode]:
    """Extract issue codes from validation result."""
    return [i.code for i in result.issues]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestValidateImage:
    """Tests for validate_image function."""

    def test_valid_rgb_png(self) -> None:
        """Valid RGB PNG produces no issues."""
        meta = _make_meta()
        result = validate_image(meta)
        assert result.is_valid is True
        assert result.issues == []

    def test_corrupt_image(self) -> None:
        """Corrupt image produces IMAGE_CORRUPT error."""
        meta = _make_meta(
            is_corrupt=True, width=0, height=0,
            format="unknown", color_mode="unknown",
        )
        result = validate_image(meta)
        assert not result.is_valid
        assert IssueCode.IMAGE_CORRUPT in _issue_codes(result)
        corrupt_issue = result.errors[0]
        assert corrupt_issue.severity == Severity.ERROR
        assert "corrupt" in corrupt_issue.message.lower()

    def test_unsupported_format(self) -> None:
        """Unsupported format produces IMAGE_FORMAT_UNSUPPORTED error."""
        meta = _make_meta(format="bmp")
        result = validate_image(meta)
        assert not result.is_valid
        assert IssueCode.IMAGE_FORMAT_UNSUPPORTED in _issue_codes(result)

    def test_rgba_produces_warning(self) -> None:
        """RGBA image produces IMAGE_RGBA_CONVERSION warning."""
        meta = _make_meta(color_mode="RGBA", has_alpha=True)
        result = validate_image(meta)
        # Warning only -- still valid
        assert result.is_valid is True
        assert IssueCode.IMAGE_RGBA_CONVERSION in _issue_codes(result)
        assert len(result.warnings) == 1
        assert "alpha" in result.warnings[0].message.lower()

    def test_has_alpha_without_rgba_mode(self) -> None:
        """has_alpha=True triggers warning even if mode is not 'RGBA'."""
        meta = _make_meta(color_mode="LA", has_alpha=True)
        result = validate_image(meta)
        assert IssueCode.IMAGE_RGBA_CONVERSION in _issue_codes(result)

    def test_below_min_resolution(self) -> None:
        """Image below minimum resolution produces error."""
        meta = _make_meta(width=50, height=50)
        result = validate_image(meta, min_resolution=256)
        assert not result.is_valid
        assert IssueCode.IMAGE_BELOW_MIN_RESOLUTION in _issue_codes(result)

    def test_one_dimension_below_min(self) -> None:
        """Image with one dimension below minimum produces error."""
        meta = _make_meta(width=512, height=100)
        result = validate_image(meta, min_resolution=256)
        assert not result.is_valid
        assert IssueCode.IMAGE_BELOW_MIN_RESOLUTION in _issue_codes(result)

    def test_at_min_resolution_is_valid(self) -> None:
        """Image exactly at minimum resolution is valid."""
        meta = _make_meta(width=256, height=256)
        result = validate_image(meta, min_resolution=256)
        assert IssueCode.IMAGE_BELOW_MIN_RESOLUTION not in _issue_codes(result)

    def test_accumulative_multiple_issues(self) -> None:
        """Corrupt RGBA image with unsupported format produces 3 issues."""
        meta = _make_meta(
            is_corrupt=True,
            width=0,
            height=0,
            format="bmp",
            color_mode="RGBA",
            has_alpha=True,
        )
        result = validate_image(meta, min_resolution=256)
        codes = _issue_codes(result)
        # Should have corruption, format, resolution, and RGBA -- 4 issues
        assert IssueCode.IMAGE_CORRUPT in codes
        assert IssueCode.IMAGE_FORMAT_UNSUPPORTED in codes
        assert IssueCode.IMAGE_BELOW_MIN_RESOLUTION in codes
        assert IssueCode.IMAGE_RGBA_CONVERSION in codes
        assert len(result.issues) == 4

    def test_valid_jpeg(self) -> None:
        """Valid JPEG image produces no issues."""
        meta = _make_meta(format="jpeg", width=512, height=512)
        result = validate_image(meta)
        assert result.is_valid is True

    def test_valid_webp(self) -> None:
        """Valid WebP image produces no issues."""
        meta = _make_meta(format="webp", width=512, height=512)
        result = validate_image(meta)
        assert result.is_valid is True

    def test_custom_min_resolution(self) -> None:
        """Custom min_resolution is respected."""
        meta = _make_meta(width=128, height=128)
        # Default min is 256, should fail
        result_default = validate_image(meta)
        assert not result_default.is_valid

        # With min=64, should pass
        result_low = validate_image(meta, min_resolution=64)
        assert result_low.is_valid
