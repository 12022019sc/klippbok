"""Klippbok image domain data models.

Pydantic v2 models for image metadata and validation results. These models
flow through the image processing pipeline:

    probe -> validate -> bucket -> export

All models are immutable (frozen) -- they represent facts about images,
not mutable state.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from klippbok.video.models import Severity, ValidationIssue


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_IMAGE_FORMATS: set[str] = {"png", "jpeg", "webp", "tiff"}
"""Lowercase Pillow format names that klippbok can process.

Note: PIL reports 'jpeg' (not 'jpg') for JPEG files. Both .jpg and .jpeg
extensions map to format 'jpeg'. PIL reports 'tiff' for all TIFF files.
"""

SUPPORTED_IMAGE_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
"""File extensions recognized as supported images during discovery."""


# ---------------------------------------------------------------------------
# Image metadata from Pillow
# ---------------------------------------------------------------------------

class ImageMetadata(BaseModel):
    """Metadata extracted from an image file via Pillow.

    This is the raw probe result -- no validation or judgment, just facts.
    The validate module compares these facts against requirements to
    produce ValidationIssues.
    """

    model_config = ConfigDict(frozen=True)

    path: Path
    """Absolute or relative path to the image file."""

    width: int
    """Image width in pixels."""

    height: int
    """Image height in pixels."""

    format: str
    """Lowercase format name: 'png', 'jpeg', 'webp'. PIL's Image.format lowered."""

    color_mode: str
    """PIL color mode: 'RGB', 'RGBA', 'L', 'P', etc."""

    file_size: int | None = None
    """File size in bytes, if available."""

    has_alpha: bool = False
    """True if the image has an alpha channel (RGBA, LA, PA)."""

    is_corrupt: bool = False
    """True if Pillow's verify() detected corruption."""

    n_frames: int = 1
    """Number of frames/pages in the image (>1 for animated GIFs, multi-page TIFFs)."""

    @property
    def display_resolution(self) -> str:
        """Human-readable resolution string like '1920x1080'."""
        return f"{self.width}x{self.height}"

    @property
    def pixel_count(self) -> int:
        """Total number of pixels (width * height)."""
        return self.width * self.height

    @property
    def aspect_ratio(self) -> float:
        """Aspect ratio as a float (width / height).

        Returns 0.0 if height is zero (corrupt images).
        """
        if self.height == 0:
            return 0.0
        return self.width / self.height


# ---------------------------------------------------------------------------
# Validation results
# ---------------------------------------------------------------------------

class ImageValidation(BaseModel):
    """Complete validation result for a single image.

    Combines the raw metadata with all validation findings.
    Follows the same pattern as ClipValidation in video/models.py.
    """

    model_config = ConfigDict(frozen=True)

    metadata: ImageMetadata
    """The probed metadata for this image."""

    issues: list[ValidationIssue] = Field(default_factory=list)
    """All validation findings, in check order."""

    @property
    def is_valid(self) -> bool:
        """True if there are no errors (warnings are acceptable)."""
        return not any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def errors(self) -> list[ValidationIssue]:
        """Only the error-severity issues."""
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Only the warning-severity issues."""
        return [i for i in self.issues if i.severity == Severity.WARNING]


# ---------------------------------------------------------------------------
# Phase 3: Import result models
# ---------------------------------------------------------------------------

class ImageImportEntry(BaseModel):
    """Per-image result of the import pipeline.

    Carries all information gathered during a single image's journey through
    the import pipeline: probed metadata, validation result, assigned bucket,
    quality scores, and duplicate status.
    """

    model_config = ConfigDict(frozen=True)

    path: Path
    """Path to the image file."""

    metadata: ImageMetadata | None = None
    """Probed image metadata, or None if probing failed."""

    validation: ImageValidation | None = None
    """Validation result, or None if validation was skipped."""

    bucket: tuple[int, int] | None = None
    """Assigned training bucket (width, height), or None if not bucketed."""

    blur_score: float | None = None
    """Laplacian variance blur score. Higher = sharper. None if not computed."""

    phash: str | None = None
    """Perceptual hash string for near-duplicate detection. None if not computed."""

    is_near_duplicate: bool = False
    """True if this image was flagged as a near-duplicate of another."""

    duplicate_of: Path | None = None
    """Path to the original image if this is a near-duplicate."""

    skipped: bool = False
    """True if this image was skipped (e.g. already imported in a prior run)."""

    video_meta: dict[str, float | str] | None = None
    """Video-specific metadata from ffprobe: duration, fps, codec. None for images."""


class ImageImportReport(BaseModel):
    """Summary of a batch image import operation.

    Aggregates per-image entries into summary counts and statistics for
    reporting at the end of an import run.
    """

    model_config = ConfigDict(frozen=True)

    total_discovered: int
    """Total number of image files found on disk."""

    imported: int
    """Number of images successfully imported."""

    skipped_existing: int
    """Number of images skipped because they were already in the dataset."""

    rejected: int
    """Number of images rejected due to validation errors."""

    warned: int
    """Number of images imported with warnings."""

    near_duplicates_flagged: int
    """Number of images flagged as near-duplicates."""

    entries: list[ImageImportEntry] = Field(default_factory=list)
    """Per-image import results."""

    @property
    def bucket_distribution(self) -> dict[str, int]:
        """Count of non-skipped entries per bucket key, e.g. {'512x512': 47}.

        Only includes entries that have a bucket assigned and were not skipped.
        """
        dist: dict[str, int] = {}
        for e in self.entries:
            if e.bucket and not e.skipped:
                key = f"{e.bucket[0]}x{e.bucket[1]}"
                dist[key] = dist.get(key, 0) + 1
        return dist
