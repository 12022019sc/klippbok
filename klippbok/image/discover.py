"""Media file discovery in directories.

Scans directories for supported image and video files.
Returns sorted lists of paths for downstream processing.
"""

from __future__ import annotations

from pathlib import Path

from klippbok.image.errors import ImageError
from klippbok.image.models import SUPPORTED_IMAGE_EXTENSIONS

SUPPORTED_VIDEO_EXTENSIONS: set[str] = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
"""File extensions recognized as supported video files during discovery."""

SUPPORTED_MEDIA_EXTENSIONS: set[str] = SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS
"""Combined set of all supported media file extensions."""


def discover_images(
    directory: Path | str,
    recursive: bool = False,
) -> list[Path]:
    """Find all supported image files in a directory.

    Scans for files with supported extensions (.png, .jpg, .jpeg, .webp).
    Skips hidden files (names starting with '.').

    Args:
        directory: Directory to scan.
        recursive: If True, scan subdirectories too.

    Returns:
        Sorted list of image file paths with supported extensions.

    Raises:
        ImageError: If directory doesn't exist or is not a directory.
    """
    directory = Path(directory)

    if not directory.exists():
        raise ImageError(
            f"Directory does not exist: {directory}. "
            f"Check the path and try again."
        )

    if not directory.is_dir():
        raise ImageError(
            f"Path is not a directory: {directory}. "
            f"Provide a directory path, not a file path."
        )

    if recursive:
        candidates = directory.rglob("*")
    else:
        candidates = directory.iterdir()

    images: list[Path] = []
    for path in candidates:
        # Skip non-files
        if not path.is_file():
            continue

        # Skip hidden files
        if path.name.startswith("."):
            continue

        # Check extension (case-insensitive)
        if path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            images.append(path)

    return sorted(images)


def discover_media(
    directory: Path | str,
    recursive: bool = False,
) -> list[Path]:
    """Find all supported media files (images + videos) in a directory.

    Scans for files with supported image and video extensions.
    Skips hidden files (names starting with '.').

    Args:
        directory: Directory to scan.
        recursive: If True, scan subdirectories too.

    Returns:
        Sorted list of media file paths with supported extensions.

    Raises:
        ImageError: If directory doesn't exist or is not a directory.
    """
    directory = Path(directory)

    if not directory.exists():
        raise ImageError(
            f"Directory does not exist: {directory}. "
            f"Check the path and try again."
        )

    if not directory.is_dir():
        raise ImageError(
            f"Path is not a directory: {directory}. "
            f"Provide a directory path, not a file path."
        )

    if recursive:
        candidates = directory.rglob("*")
    else:
        candidates = directory.iterdir()

    media: list[Path] = []
    for path in candidates:
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() in SUPPORTED_MEDIA_EXTENSIONS:
            media.append(path)

    return sorted(media)
