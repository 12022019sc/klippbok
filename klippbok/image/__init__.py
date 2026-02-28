"""Klippbok image domain -- probing, validation, discovery, bucketing, quality, and dedup.

Provides tools for working with image files in dataset curation:
- Probe images for metadata (dimensions, format, color mode)
- Validate images against structural requirements
- Discover image files in directories
- Assign images to training resolution buckets by aspect ratio
- Detect blurry images via Laplacian variance (advisory, non-blocking)
- Compute perceptual hashes and detect near-duplicate images

Quick start:
    from klippbok.image import probe_image, validate_image, discover_images
    from klippbok.image import ImageMetadata, ImageValidation
    from klippbok.image import assign_to_bucket, compute_blur_score
    from klippbok.image import compute_phash, are_near_duplicates, select_keeper

    meta = probe_image("photo.png")
    result = validate_image(meta)
    images = discover_images("./dataset/")

    from klippbok.config.model_profiles import generate_buckets
    buckets = generate_buckets(512)
    bucket = assign_to_bucket(meta.width, meta.height, buckets)
"""

from klippbok.image.bucket import assign_to_bucket, needs_upscale
from klippbok.image.dedup import (
    PHASH_THRESHOLD,
    are_near_duplicates,
    compute_phash,
    select_keeper,
)
from klippbok.image.discover import discover_images
from klippbok.image.errors import (
    ImageError,
    ImageProbeError,
    ImageValidationError,
)
from klippbok.image.models import (
    SUPPORTED_IMAGE_EXTENSIONS,
    SUPPORTED_IMAGE_FORMATS,
    ImageImportEntry,
    ImageImportReport,
    ImageMetadata,
    ImageValidation,
)
from klippbok.image.probe import probe_image
from klippbok.image.quality import BLUR_THRESHOLD, compute_blur_score, is_blurry
from klippbok.image.validate import validate_image

__all__ = [
    # Models
    "ImageMetadata",
    "ImageValidation",
    "ImageImportEntry",
    "ImageImportReport",
    "SUPPORTED_IMAGE_FORMATS",
    "SUPPORTED_IMAGE_EXTENSIONS",
    # Probe
    "probe_image",
    # Validate
    "validate_image",
    # Discovery
    "discover_images",
    # Bucket assignment
    "assign_to_bucket",
    "needs_upscale",
    # Quality / blur detection
    "compute_blur_score",
    "is_blurry",
    "BLUR_THRESHOLD",
    # Perceptual hash / dedup
    "compute_phash",
    "are_near_duplicates",
    "select_keeper",
    "PHASH_THRESHOLD",
    # Errors
    "ImageError",
    "ImageProbeError",
    "ImageValidationError",
]
