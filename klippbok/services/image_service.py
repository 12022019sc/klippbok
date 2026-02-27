"""Image import and validation service.

Stateless service functions that compose image probing, validation,
and discovery into higher-level operations. Both CLI and future
API/GUI routes call these functions.

All functions are pure -- no side effects, no state.
"""

from __future__ import annotations

import logging
from pathlib import Path

from klippbok.image.discover import discover_images
from klippbok.image.models import ImageMetadata, ImageValidation
from klippbok.image.probe import probe_image
from klippbok.image.validate import validate_image

logger = logging.getLogger(__name__)


def import_image(
    path: Path,
    min_resolution: int = 256,
    max_resolution: int = 4096,
) -> tuple[ImageMetadata, ImageValidation]:
    """Probe and validate a single image file.

    Extracts metadata via Pillow, then validates against resolution
    and format requirements.

    Args:
        path: Path to the image file.
        min_resolution: Minimum dimension (width or height) in pixels.
        max_resolution: Maximum dimension in pixels.

    Returns:
        Tuple of (ImageMetadata, ImageValidation).

    Raises:
        ImageProbeError: If the file doesn't exist or can't be opened.
    """
    metadata = probe_image(path)
    validation = validate_image(metadata, min_resolution, max_resolution)
    return metadata, validation


def import_images(
    directory: Path,
    recursive: bool = False,
    min_resolution: int = 256,
    max_resolution: int = 4096,
) -> list[tuple[ImageMetadata, ImageValidation]]:
    """Discover, probe, and validate all images in a directory.

    Scans for supported image files, then probes and validates each one.

    Args:
        directory: Directory to scan for images.
        recursive: If True, scan subdirectories too.
        min_resolution: Minimum dimension (width or height) in pixels.
        max_resolution: Maximum dimension in pixels.

    Returns:
        List of (ImageMetadata, ImageValidation) tuples, one per image.
    """
    paths = discover_images(directory, recursive=recursive)
    results: list[tuple[ImageMetadata, ImageValidation]] = []

    for path in paths:
        try:
            result = import_image(path, min_resolution, max_resolution)
            results.append(result)
        except Exception as exc:
            logger.error(
                "Failed to import image '%s': %s",
                path,
                exc,
            )
            raise

    return results


def validate_image_file(
    path: Path,
    min_resolution: int = 256,
    max_resolution: int = 4096,
) -> ImageValidation:
    """Convenience: probe + validate, return only the validation result.

    Args:
        path: Path to the image file.
        min_resolution: Minimum dimension (width or height) in pixels.
        max_resolution: Maximum dimension in pixels.

    Returns:
        ImageValidation with all found issues.

    Raises:
        ImageProbeError: If the file doesn't exist or can't be opened.
    """
    _, validation = import_image(path, min_resolution, max_resolution)
    return validation
