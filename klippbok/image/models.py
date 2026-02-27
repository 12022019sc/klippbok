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

SUPPORTED_IMAGE_FORMATS: set[str] = {"png", "jpeg", "webp"}
"""Lowercase Pillow format names that klippbok can process.

Note: PIL reports 'jpeg' (not 'jpg') for JPEG files. Both .jpg and .jpeg
extensions map to format 'jpeg'.
"""

SUPPORTED_IMAGE_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".webp"}
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
