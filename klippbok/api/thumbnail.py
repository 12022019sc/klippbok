"""Server-side thumbnail generation with disk cache.

Thumbnails are generated on demand and cached to disk as JPEG files.
The cache key is a SHA256 hash of the absolute file path, so moving
the project directory invalidates the cache gracefully.

Supports both images (via Pillow) and videos (via ffmpeg).
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

THUMB_MAX_SIZE = (300, 300)
"""Maximum thumbnail dimensions. Pillow thumbnail() preserves aspect ratio."""


def get_thumbnail(image_path: Path, cache_dir: Path) -> Path:
    """Return the cached JPEG thumbnail for the given image, generating it if needed.

    The cache key is a SHA256 hash of the absolute resolved path, so path
    changes invalidate the cache. Alpha channels are stripped before saving
    to ensure JPEG compatibility.

    Args:
        image_path: Absolute path to the source image file.
        cache_dir: Directory where thumbnail JPEG files are cached.

    Returns:
        Path to the cached JPEG thumbnail file.

    Raises:
        FileNotFoundError: If image_path does not exist.
        OSError: If the cache directory cannot be created or the thumbnail
            cannot be written.
    """
    from PIL import Image

    # Compute cache key from absolute path
    abs_path = image_path.resolve()
    path_hash = hashlib.sha256(str(abs_path).encode()).hexdigest()[:16]
    thumb_path = cache_dir / f"{path_hash}.jpg"

    if thumb_path.exists():
        logger.debug("Thumbnail cache hit: %s -> %s", abs_path.name, thumb_path)
        return thumb_path

    # Generate thumbnail
    cache_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(abs_path) as img:
        img = img.convert("RGB")  # strip alpha for JPEG safety
        img.thumbnail(THUMB_MAX_SIZE, Image.LANCZOS)
        img.save(thumb_path, format="JPEG", quality=85, optimize=True)

    logger.debug("Thumbnail generated: %s -> %s", abs_path.name, thumb_path)
    return thumb_path


def generate_video_thumbnail(video_path: Path, cache_dir: Path) -> Path:
    """Alias for get_video_thumbnail — generate and cache a JPEG thumbnail for a video.

    The cache key is SHA256[:16] of the absolute path, matching [04-01 API-02] pattern.
    Returns the cached file path on subsequent calls without re-running ffmpeg.

    Args:
        video_path: Path to the source video file.
        cache_dir: Directory where thumbnail JPEG files are cached.

    Returns:
        Path to the cached JPEG thumbnail file.
    """
    return get_video_thumbnail(video_path, cache_dir)


def get_video_thumbnail(video_path: Path, cache_dir: Path) -> Path:
    """Return a cached JPEG thumbnail for a video, extracting a frame via ffmpeg if needed.

    Extracts a single frame at ~1 second into the video (or frame 0 if shorter).
    The frame is scaled to fit within 300x300 while preserving aspect ratio.

    Args:
        video_path: Absolute path to the source video file.
        cache_dir: Directory where thumbnail JPEG files are cached.

    Returns:
        Path to the cached JPEG thumbnail file.

    Raises:
        FileNotFoundError: If video_path does not exist.
        RuntimeError: If ffmpeg fails to extract a frame.
    """
    abs_path = video_path.resolve()
    path_hash = hashlib.sha256(str(abs_path).encode()).hexdigest()[:16]
    thumb_path = cache_dir / f"{path_hash}.jpg"

    if thumb_path.exists():
        logger.debug("Video thumbnail cache hit: %s -> %s", abs_path.name, thumb_path)
        return thumb_path

    cache_dir.mkdir(parents=True, exist_ok=True)

    # Try extracting frame at 1 second, fall back to 0 if that fails
    for seek_time in ("1", "0"):
        cmd = [
            "ffmpeg", "-y",
            "-ss", seek_time,
            "-i", str(abs_path),
            "-vframes", "1",
            "-vf", "scale=300:300:force_original_aspect_ratio=decrease",
            "-f", "image2",
            str(thumb_path),
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0 and thumb_path.exists():
            logger.debug("Video thumbnail generated (ss=%s): %s -> %s", seek_time, abs_path.name, thumb_path)
            return thumb_path

    raise RuntimeError(
        f"ffmpeg failed to extract thumbnail from '{abs_path}': "
        f"{result.stderr.decode(errors='replace')[:500]}"
    )
