"""Tests for klippbok.image.models -- pure Python, no Pillow needed.

Tests the Pydantic models for image metadata, validation results,
and constants. All data is hand-crafted.
"""

from pathlib import Path

import pytest

from klippbok.image.models import (
    SUPPORTED_IMAGE_EXTENSIONS,
    SUPPORTED_IMAGE_FORMATS,
    ImageImportEntry,
    ImageImportReport,
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


# ---------------------------------------------------------------------------
# Phase 3: TIFF format constant extensions
# ---------------------------------------------------------------------------

class TestTiffFormatConstants:
    """Tests for TIFF format support in constants."""

    def test_supported_formats_includes_tiff(self) -> None:
        """'tiff' is in SUPPORTED_IMAGE_FORMATS."""
        assert "tiff" in SUPPORTED_IMAGE_FORMATS

    def test_supported_extensions_includes_tif_and_tiff(self) -> None:
        """'.tif' and '.tiff' are in SUPPORTED_IMAGE_EXTENSIONS."""
        assert ".tif" in SUPPORTED_IMAGE_EXTENSIONS
        assert ".tiff" in SUPPORTED_IMAGE_EXTENSIONS


# ---------------------------------------------------------------------------
# Phase 3: New IssueCode values
# ---------------------------------------------------------------------------

class TestPhase3IssueCodes:
    """Tests for the five new Phase 3 IssueCode values."""

    def test_issue_code_image_upscale_required(self) -> None:
        """IssueCode.IMAGE_UPSCALE_REQUIRED exists with correct value."""
        assert hasattr(IssueCode, "IMAGE_UPSCALE_REQUIRED")
        assert IssueCode.IMAGE_UPSCALE_REQUIRED.value == "IMAGE_UPSCALE_REQUIRED"

    def test_issue_code_image_blur_detected(self) -> None:
        """IssueCode.IMAGE_BLUR_DETECTED exists with correct value."""
        assert hasattr(IssueCode, "IMAGE_BLUR_DETECTED")
        assert IssueCode.IMAGE_BLUR_DETECTED.value == "IMAGE_BLUR_DETECTED"

    def test_issue_code_image_near_duplicate(self) -> None:
        """IssueCode.IMAGE_NEAR_DUPLICATE exists with correct value."""
        assert hasattr(IssueCode, "IMAGE_NEAR_DUPLICATE")
        assert IssueCode.IMAGE_NEAR_DUPLICATE.value == "IMAGE_NEAR_DUPLICATE"

    def test_issue_code_image_extreme_aspect(self) -> None:
        """IssueCode.IMAGE_EXTREME_ASPECT exists with correct value."""
        assert hasattr(IssueCode, "IMAGE_EXTREME_ASPECT")
        assert IssueCode.IMAGE_EXTREME_ASPECT.value == "IMAGE_EXTREME_ASPECT"

    def test_issue_code_image_tiff_multipage(self) -> None:
        """IssueCode.IMAGE_TIFF_MULTIPAGE exists with correct value."""
        assert hasattr(IssueCode, "IMAGE_TIFF_MULTIPAGE")
        assert IssueCode.IMAGE_TIFF_MULTIPAGE.value == "IMAGE_TIFF_MULTIPAGE"


# ---------------------------------------------------------------------------
# Phase 3: ImageImportEntry model
# ---------------------------------------------------------------------------

def _make_image_metadata(**kwargs) -> ImageMetadata:
    """Helper: create ImageMetadata with sensible defaults."""
    defaults = dict(
        path=Path("/test/photo.png"),
        width=1024,
        height=768,
        format="png",
        color_mode="RGB",
    )
    defaults.update(kwargs)
    return ImageMetadata(**defaults)


class TestImageImportEntry:
    """Tests for the ImageImportEntry model."""

    def test_import_entry_is_frozen(self) -> None:
        """ImageImportEntry is immutable -- assigning to a field raises."""
        entry = ImageImportEntry(path=Path("x.png"))
        with pytest.raises(Exception):
            entry.path = Path("y.png")  # type: ignore[misc]

    def test_import_entry_minimal(self) -> None:
        """ImageImportEntry with only path has correct defaults."""
        entry = ImageImportEntry(path=Path("x.png"))
        assert entry.path == Path("x.png")
        assert entry.metadata is None
        assert entry.validation is None
        assert entry.bucket is None
        assert entry.blur_score is None
        assert entry.phash is None
        assert entry.is_near_duplicate is False
        assert entry.duplicate_of is None
        assert entry.skipped is False

    def test_import_entry_full(self) -> None:
        """ImageImportEntry with all fields round-trips correctly."""
        meta = _make_image_metadata()
        validation = ImageValidation(metadata=meta)
        entry = ImageImportEntry(
            path=Path("/test/photo.png"),
            metadata=meta,
            validation=validation,
            bucket=(512, 512),
            blur_score=150.5,
            phash="abcdef1234567890",
            is_near_duplicate=False,
            duplicate_of=None,
            skipped=False,
        )
        assert entry.path == Path("/test/photo.png")
        assert entry.metadata == meta
        assert entry.validation == validation
        assert entry.bucket == (512, 512)
        assert entry.blur_score == 150.5
        assert entry.phash == "abcdef1234567890"
        assert entry.is_near_duplicate is False
        assert entry.duplicate_of is None
        assert entry.skipped is False

    def test_import_entry_skipped(self) -> None:
        """ImageImportEntry with skipped=True for already-imported files."""
        entry = ImageImportEntry(path=Path("/test/already.png"), skipped=True)
        assert entry.skipped is True
        assert entry.path == Path("/test/already.png")

    def test_import_entry_near_duplicate(self) -> None:
        """ImageImportEntry captures near-duplicate information."""
        entry = ImageImportEntry(
            path=Path("/test/dup.png"),
            is_near_duplicate=True,
            duplicate_of=Path("/test/original.png"),
        )
        assert entry.is_near_duplicate is True
        assert entry.duplicate_of == Path("/test/original.png")


# ---------------------------------------------------------------------------
# Phase 3: ImageImportReport model
# ---------------------------------------------------------------------------

class TestImageImportReport:
    """Tests for the ImageImportReport model."""

    def test_import_report_is_frozen(self) -> None:
        """ImageImportReport is immutable -- assigning raises."""
        report = ImageImportReport(
            total_discovered=0,
            imported=0,
            skipped_existing=0,
            rejected=0,
            warned=0,
            near_duplicates_flagged=0,
        )
        with pytest.raises(Exception):
            report.imported = 5  # type: ignore[misc]

    def test_import_report_counts(self) -> None:
        """ImageImportReport stores counts correctly."""
        report = ImageImportReport(
            total_discovered=10,
            imported=7,
            skipped_existing=2,
            rejected=1,
            warned=3,
            near_duplicates_flagged=1,
        )
        assert report.total_discovered == 10
        assert report.imported == 7
        assert report.skipped_existing == 2
        assert report.rejected == 1
        assert report.warned == 3
        assert report.near_duplicates_flagged == 1

    def test_import_report_bucket_distribution(self) -> None:
        """bucket_distribution returns correct counts per bucket key."""
        entries = [
            ImageImportEntry(path=Path(f"/test/{i}.png"), bucket=(512, 512))
            for i in range(3)
        ] + [
            ImageImportEntry(path=Path(f"/test/wide{i}.png"), bucket=(768, 512))
            for i in range(2)
        ]
        report = ImageImportReport(
            total_discovered=5,
            imported=5,
            skipped_existing=0,
            rejected=0,
            warned=0,
            near_duplicates_flagged=0,
            entries=entries,
        )
        dist = report.bucket_distribution
        assert dist["512x512"] == 3
        assert dist["768x512"] == 2

    def test_import_report_bucket_distribution_excludes_skipped(self) -> None:
        """bucket_distribution skips entries with skipped=True."""
        entries = [
            ImageImportEntry(path=Path("/test/a.png"), bucket=(512, 512)),
            ImageImportEntry(path=Path("/test/b.png"), bucket=(512, 512), skipped=True),
        ]
        report = ImageImportReport(
            total_discovered=2,
            imported=1,
            skipped_existing=1,
            rejected=0,
            warned=0,
            near_duplicates_flagged=0,
            entries=entries,
        )
        dist = report.bucket_distribution
        assert dist["512x512"] == 1

    def test_import_report_empty(self) -> None:
        """ImageImportReport with zero counts and empty entries works."""
        report = ImageImportReport(
            total_discovered=0,
            imported=0,
            skipped_existing=0,
            rejected=0,
            warned=0,
            near_duplicates_flagged=0,
        )
        assert report.entries == []
        assert report.bucket_distribution == {}
