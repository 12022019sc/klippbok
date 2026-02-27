"""Tests for klippbok.image.models -- pure Python, no Pillow needed.

Tests the Pydantic models for image metadata, validation results,
and constants. All data is hand-crafted.
"""

from pathlib import Path

import pytest

from klippbok.image.models import (
    SUPPORTED_IMAGE_EXTENSIONS,
    SUPPORTED_IMAGE_FORMATS,
    ImageMetadata,
    ImageValidation,
)
from klippbok.video.models import (
    IssueCode,
    Severity,
    ValidationIssue,
)


# ---------------------------------------------------------------------------
# ImageMetadata
# ---------------------------------------------------------------------------

class TestImageMetadata:
    """Tests for the ImageMetadata model."""

    def _make_meta(self, **kwargs) -> ImageMetadata:
        """Helper: create ImageMetadata with sensible defaults."""
        defaults = dict(
            path=Path("/test/photo.png"),
            width=1920,
            height=1080,
            format="png",
            color_mode="RGB",
        )
        defaults.update(kwargs)
        return ImageMetadata(**defaults)

    def test_basic_creation(self) -> None:
        """Create metadata with required fields."""
        meta = self._make_meta()
        assert meta.width == 1920
        assert meta.height == 1080
        assert meta.format == "png"
        assert meta.color_mode == "RGB"

    def test_frozen(self) -> None:
        """ImageMetadata is immutable -- assigning to a field raises."""
        meta = self._make_meta()
        with pytest.raises(Exception):
            meta.width = 1280  # type: ignore[misc]

    def test_display_resolution(self) -> None:
        """display_resolution formats as WxH."""
        meta = self._make_meta(width=1920, height=1080)
        assert meta.display_resolution == "1920x1080"

    def test_pixel_count(self) -> None:
        """pixel_count is width * height."""
        meta = self._make_meta(width=100, height=200)
        assert meta.pixel_count == 20_000

    def test_aspect_ratio(self) -> None:
        """aspect_ratio is width / height."""
        meta = self._make_meta(width=1920, height=1080)
        assert abs(meta.aspect_ratio - (1920 / 1080)) < 0.001

    def test_aspect_ratio_zero_height(self) -> None:
        """aspect_ratio returns 0.0 when height is zero (corrupt image)."""
        meta = self._make_meta(width=0, height=0)
        assert meta.aspect_ratio == 0.0

    def test_default_optional_fields(self) -> None:
        """Optional fields default to None/False."""
        meta = self._make_meta()
        assert meta.file_size is None
        assert meta.has_alpha is False
        assert meta.is_corrupt is False

    def test_all_fields(self) -> None:
        """Create metadata with all fields populated."""
        meta = self._make_meta(
            file_size=123456,
            has_alpha=True,
            is_corrupt=False,
        )
        assert meta.file_size == 123456
        assert meta.has_alpha is True
        assert meta.is_corrupt is False


# ---------------------------------------------------------------------------
# ImageValidation
# ---------------------------------------------------------------------------

class TestImageValidation:
    """Tests for the ImageValidation model."""

    def _make_meta(self, **kwargs) -> ImageMetadata:
        defaults = dict(
            path=Path("/test/photo.png"),
            width=1920,
            height=1080,
            format="png",
            color_mode="RGB",
        )
        defaults.update(kwargs)
        return ImageMetadata(**defaults)

    def test_no_issues_is_valid(self) -> None:
        """Validation with no issues is valid."""
        v = ImageValidation(metadata=self._make_meta())
        assert v.is_valid is True
        assert v.errors == []
        assert v.warnings == []

    def test_warning_only_still_valid(self) -> None:
        """Validation with only warnings is still valid."""
        issue = ValidationIssue(
            code=IssueCode.IMAGE_RGBA_CONVERSION,
            severity=Severity.WARNING,
            message="Has alpha channel",
            field="color_mode",
        )
        v = ImageValidation(metadata=self._make_meta(), issues=[issue])
        assert v.is_valid is True
        assert len(v.warnings) == 1
        assert len(v.errors) == 0

    def test_error_makes_invalid(self) -> None:
        """Validation with an error is invalid."""
        issue = ValidationIssue(
            code=IssueCode.IMAGE_FORMAT_UNSUPPORTED,
            severity=Severity.ERROR,
            message="Unsupported format",
            field="format",
        )
        v = ImageValidation(metadata=self._make_meta(), issues=[issue])
        assert v.is_valid is False
        assert len(v.errors) == 1

    def test_mixed_errors_and_warnings(self) -> None:
        """Validation separates errors and warnings correctly."""
        error = ValidationIssue(
            code=IssueCode.IMAGE_CORRUPT,
            severity=Severity.ERROR,
            message="Corrupt",
            field="file",
        )
        warning = ValidationIssue(
            code=IssueCode.IMAGE_RGBA_CONVERSION,
            severity=Severity.WARNING,
            message="Alpha",
            field="color_mode",
        )
        v = ImageValidation(
            metadata=self._make_meta(), issues=[error, warning]
        )
        assert v.is_valid is False
        assert len(v.errors) == 1
        assert len(v.warnings) == 1


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    """Tests for image format constants."""

    def test_supported_formats(self) -> None:
        """SUPPORTED_IMAGE_FORMATS contains expected values."""
        assert "png" in SUPPORTED_IMAGE_FORMATS
        assert "jpeg" in SUPPORTED_IMAGE_FORMATS
        assert "webp" in SUPPORTED_IMAGE_FORMATS
        assert "bmp" not in SUPPORTED_IMAGE_FORMATS

    def test_supported_extensions(self) -> None:
        """SUPPORTED_IMAGE_EXTENSIONS contains expected values."""
        assert ".png" in SUPPORTED_IMAGE_EXTENSIONS
        assert ".jpg" in SUPPORTED_IMAGE_EXTENSIONS
        assert ".jpeg" in SUPPORTED_IMAGE_EXTENSIONS
        assert ".webp" in SUPPORTED_IMAGE_EXTENSIONS
        assert ".bmp" not in SUPPORTED_IMAGE_EXTENSIONS


# ---------------------------------------------------------------------------
# IssueCode enum extensions
# ---------------------------------------------------------------------------

class TestImageIssueCodes:
    """Tests for the new image-specific IssueCode values."""

    @pytest.mark.parametrize("code_name", [
        "IMAGE_FORMAT_UNSUPPORTED",
        "IMAGE_CORRUPT",
        "IMAGE_RGBA_CONVERSION",
        "IMAGE_NO_VALID_BUCKET",
        "IMAGE_BELOW_MIN_RESOLUTION",
    ])
    def test_issue_code_exists(self, code_name: str) -> None:
        """Each image IssueCode value exists on the enum."""
        assert hasattr(IssueCode, code_name)
        code = getattr(IssueCode, code_name)
        assert code.value == code_name
