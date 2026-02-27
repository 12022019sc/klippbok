"""Klippbok image domain -- probing, validation, and discovery.

Provides tools for working with image files in dataset curation:
- Probe images for metadata (dimensions, format, color mode)
- Validate images against structural requirements
- Discover image files in directories

Quick start:
    from klippbok.image import probe_image, validate_image, discover_images
    from klippbok.image import ImageMetadata, ImageValidation

    meta = probe_image("photo.png")
    result = validate_image(meta)
    images = discover_images("./dataset/")
"""

from klippbok.image.errors import (
    ImageError,
    ImageProbeError,
    ImageValidationError,
)
from klippbok.image.models import (
    SUPPORTED_IMAGE_EXTENSIONS,
    SUPPORTED_IMAGE_FORMATS,
    ImageMetadata,
    ImageValidation,
)

__all__ = [
    # Models
    "ImageMetadata",
    "ImageValidation",
    "SUPPORTED_IMAGE_FORMATS",
    "SUPPORTED_IMAGE_EXTENSIONS",
    # Errors
    "ImageError",
    "ImageProbeError",
    "ImageValidationError",
]
