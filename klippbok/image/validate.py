"""Accumulative image validation against structural requirements.

Compares probed image metadata against requirements to find issues:
corruption, unsupported format, resolution, color mode.

This is pure logic -- no Pillow needed. All inputs are Python objects,
making it fast and easy to test.

Bucket-aware validation is deferred to Phase 3 (needs model profiles).
"""

from __future__ import annotations

from klippbok.image.models import (
    SUPPORTED_IMAGE_FORMATS,
    ImageMetadata,
    ImageValidation,
)
from klippbok.video.models import (
    IssueCode,
    Severity,
    ValidationIssue,
)


def validate_image(
    metadata: ImageMetadata,
    min_resolution: int = 256,
    max_resolution: int = 4096,
) -> ImageValidation:
    """Validate an image against structural requirements.

    Collects ALL issues (accumulative, never fail-fast). Every image
    gets checked against every rule, so the user sees the full picture
    in one pass.

    Phase 1 checks: format, corruption, dimensions, color mode.
    Bucket-aware validation deferred to Phase 3 (needs model profiles).

    Args:
        metadata: Probed image metadata.
        min_resolution: Minimum dimension (width or height) in pixels.
        max_resolution: Maximum dimension in pixels.

    Returns:
        ImageValidation with all found issues.
    """
    issues: list[ValidationIssue] = []

    # 1. Corruption check
    if metadata.is_corrupt:
        issues.append(ValidationIssue(
            code=IssueCode.IMAGE_CORRUPT,
            severity=Severity.ERROR,
            message=(
                "Image file is corrupt or truncated. "
                "Re-download or re-export this file."
            ),
            field="file",
            actual="corrupt",
            expected="valid image",
        ))

    # 2. Format check
    if metadata.format not in SUPPORTED_IMAGE_FORMATS:
        supported_list = ", ".join(sorted(SUPPORTED_IMAGE_FORMATS))
        issues.append(ValidationIssue(
            code=IssueCode.IMAGE_FORMAT_UNSUPPORTED,
            severity=Severity.ERROR,
            message=(
                f"Image format '{metadata.format}' is not supported. "
                f"Supported formats: {supported_list}. "
                f"Convert this image to PNG, JPEG, or WebP."
            ),
            field="format",
            actual=metadata.format,
            expected=supported_list,
        ))

    # 3. Dimensions below minimum
    if (
        metadata.width < min_resolution
        or metadata.height < min_resolution
    ):
        issues.append(ValidationIssue(
            code=IssueCode.IMAGE_BELOW_MIN_RESOLUTION,
            severity=Severity.ERROR,
            message=(
                f"Image is {metadata.display_resolution} -- "
                f"below minimum {min_resolution}x{min_resolution}. "
                f"Use a higher-resolution source image."
            ),
            field="resolution",
            actual=metadata.display_resolution,
            expected=f">={min_resolution}x{min_resolution}",
        ))

    # 4. RGBA / alpha channel check
    if metadata.color_mode == "RGBA" or metadata.has_alpha:
        issues.append(ValidationIssue(
            code=IssueCode.IMAGE_RGBA_CONVERSION,
            severity=Severity.WARNING,
            message=(
                "Image has alpha channel (RGBA). Will be flattened to "
                "RGB with white background during export."
            ),
            field="color_mode",
            actual=metadata.color_mode,
            expected="RGB",
        ))

    return ImageValidation(metadata=metadata, issues=issues)
