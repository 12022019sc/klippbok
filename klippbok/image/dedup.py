"""Perceptual hash-based near-duplicate image detection.

Uses imagehash's pHash (perceptual hash) algorithm to detect
near-identical images: resized copies, re-encoded versions,
and minor crop variants. NOT for "similar but different" detection.

Hash persistence: hashes are stored as hex strings in the project
manifest. On subsequent imports, existing hashes are loaded from
manifest and new images are compared against them.
"""

from __future__ import annotations

from pathlib import Path

import imagehash
from PIL import Image

from klippbok.image.models import ImageMetadata

PHASH_THRESHOLD: int = 10
"""Maximum Hamming distance for two images to be considered near-duplicates.
pHash with hash_size=8 produces 64-bit hashes. Threshold 10 catches
resized, re-compressed, and minor-crop variants."""

# Format preference for keeper selection (lower = preferred)
_FORMAT_PREFERENCE: dict[str, int] = {"png": 0, "tiff": 1, "webp": 2, "jpeg": 3}


def compute_phash(image_path: Path | str) -> str:
    """Compute perceptual hash for an image file.

    Args:
        image_path: Path to the image file.

    Returns:
        Hex string representation of the pHash (for manifest storage).
    """
    with Image.open(image_path) as img:
        h = imagehash.phash(img)  # hash_size=8 default = 64-bit hash
    return str(h)


def are_near_duplicates(hash_hex_a: str, hash_hex_b: str, threshold: int = PHASH_THRESHOLD) -> bool:
    """Check if two images are near-duplicates by pHash distance.

    Args:
        hash_hex_a: Hex string of first image's pHash.
        hash_hex_b: Hex string of second image's pHash.
        threshold: Maximum Hamming distance to consider as duplicates.

    Returns:
        True if Hamming distance <= threshold.
    """
    ha = imagehash.hex_to_hash(hash_hex_a)
    hb = imagehash.hex_to_hash(hash_hex_b)
    return bool((ha - hb) <= threshold)


def select_keeper(images: list[ImageMetadata]) -> ImageMetadata:
    """Select the image to keep from a near-duplicate group.

    Strategy: highest resolution wins. Tiebreaker: prefer lossless
    format (PNG > TIFF > WEBP > JPEG).

    Args:
        images: List of ImageMetadata for near-duplicate images.

    Returns:
        The ImageMetadata that should be kept.

    Raises:
        ValueError: If images list is empty.
    """
    if not images:
        raise ValueError("Cannot select keeper from empty list")

    return min(
        images,
        key=lambda m: (
            -m.pixel_count,
            _FORMAT_PREFERENCE.get(m.format, 99),
        ),
    )
