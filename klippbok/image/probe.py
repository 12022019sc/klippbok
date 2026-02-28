"""Image metadata extraction using Pillow.

Probes image files to extract dimensions, format, color mode, and
corruption status. Uses Pillow's Image.open() + .verify() for
integrity checking.

This is pure Pillow -- no external tools needed (unlike video probing
which requires ffprobe).
"""

from __future__ import annotations

import logging
from pathlib import Path

from klippbok.image.errors import ImageError, ImageProbeError
from klippbok.image.models import ImageMetadata

logger = logging.getLogger(__name__)

try:
    from PIL import Image
except ImportError:
    raise ImageError(
        "Pillow is required for image processing. "
        "Install with: pip install klippbok[image]"
    )


def probe_image(path: Path | str) -> ImageMetadata:
    """Extract metadata from an image file.

    Uses Pillow's Image.open() + .verify() for corruption detection,
    then re-opens for metadata extraction (verify() closes the file).

    Args:
        path: Path to the image file.

    Returns:
        ImageMetadata with all fields populated.
        If the file is corrupt, returns ImageMetadata with is_corrupt=True
        and zero dimensions.

    Raises:
        ImageProbeError: If the file doesn't exist or can't be opened at all.
    """
    path = Path(path)

    if not path.exists():
        raise ImageProbeError(str(path), "File does not exist")

    if not path.is_file():
        raise ImageProbeError(str(path), "Path is not a file")

    # Phase 1: Verify integrity
    is_corrupt = False
    try:
        with Image.open(path) as img:
            img.verify()
    except Exception as exc:
        logger.debug("Image verify failed for '%s': %s", path, exc)
        is_corrupt = True

    if is_corrupt:
        try:
            file_size = path.stat().st_size
        except OSError:
            file_size = None

        return ImageMetadata(
            path=path,
            width=0,
            height=0,
            format="unknown",
            color_mode="unknown",
            file_size=file_size,
            has_alpha=False,
            is_corrupt=True,
        )

    # Phase 2: Extract metadata (verify() closes the image, must re-open)
    try:
        with Image.open(path) as img:
            fmt = img.format
            format_str = fmt.lower() if fmt else "unknown"
            color_mode = img.mode
            has_alpha = "A" in color_mode
            width = img.width
            height = img.height
            n_frames = getattr(img, "n_frames", 1)
    except Exception as exc:
        raise ImageProbeError(
            str(path),
            f"Failed to read image metadata: {exc}",
        ) from exc

    try:
        file_size = path.stat().st_size
    except OSError:
        file_size = None

    return ImageMetadata(
        path=path,
        width=width,
        height=height,
        format=format_str,
        color_mode=color_mode,
        file_size=file_size,
        has_alpha=has_alpha,
        is_corrupt=False,
        n_frames=n_frames,
    )
