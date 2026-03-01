"""Image import and validation service.

Stateless service functions that compose image probing, validation,
and discovery into higher-level operations. Both CLI and future
API/GUI routes call these functions.

All functions are pure -- no side effects, no state.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from klippbok.image.bucket import assign_to_bucket, needs_upscale
from klippbok.image.dedup import are_near_duplicates, compute_phash
from klippbok.image.discover import (
    SUPPORTED_VIDEO_EXTENSIONS,
    discover_images,
    discover_media,
)
from klippbok.image.models import (
    ImageImportEntry,
    ImageImportReport,
    ImageMetadata,
    ImageValidation,
)
from klippbok.image.probe import probe_image
from klippbok.image.quality import BLUR_THRESHOLD, compute_blur_score
from klippbok.image.validate import validate_image
from klippbok.video.models import IssueCode, Severity, ValidationIssue

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


def batch_import_images(
    directory: Path,
    project_dir: Path,
    buckets: list[tuple[int, int]] | None = None,
    max_aspect_ratio: float = 2.0,
    recursive: bool = False,
    min_resolution: int = 256,
    max_resolution: int = 4096,
) -> ImageImportReport:
    """Full batch import pipeline: discover, probe, validate, bucket, quality, dedup, persist.

    Pipeline steps:
    1. Load existing manifest to build known-paths skip set and existing hash map
    2. Discover image files in directory
    3. For each new (non-skipped) image:
       a. Probe -- extract ImageMetadata
       b. Validate -- format, resolution, color mode
       c. Assign bucket (if buckets provided)
       d. Compute blur score and check blurriness
       e. Compute pHash for dedup
       f. Check against accumulated hash map (within-batch + prior imports)
       g. Append quality/dedup issues to validation
    4. Build ImageImportReport with accurate counts
    5. Persist all results to manifest under "images" key

    Args:
        directory: Directory to scan for images.
        project_dir: Project root for manifest persistence.
        buckets: Valid bucket dimensions (from generate_buckets). If None, skip bucketing.
        max_aspect_ratio: Maximum aspect ratio for bucket assignment.
        recursive: If True, scan subdirectories.
        min_resolution: Minimum dimension for validation.
        max_resolution: Maximum dimension for validation.

    Returns:
        ImageImportReport with complete results.
    """
    from klippbok.services.project_service import load_manifest, save_image_entries

    # Step 1: Load existing manifest for skip set and prior hashes
    manifest = load_manifest(project_dir)
    known_paths: set[str] = set()
    hash_map: dict[str, Path] = {}  # phash_hex -> keeper path

    if manifest and "images" in manifest:
        for entry in manifest["images"]:
            if "path" in entry:
                known_paths.add(entry["path"])
            if "phash" in entry and "path" in entry:
                hash_map[entry["phash"]] = project_dir / entry["path"]

    # Step 2: Discover media (images + videos)
    discovered_paths = discover_media(directory, recursive=recursive)
    total_discovered = len(discovered_paths)

    # Step 3: Separate new vs already-imported (canonical relative path comparison)
    project_dir_resolved = project_dir.resolve()
    entries: list[ImageImportEntry] = []
    skipped_existing = 0

    for media_path in discovered_paths:
        try:
            rel_str = str(media_path.resolve().relative_to(project_dir_resolved))
        except ValueError:
            rel_str = str(media_path)

        if rel_str in known_paths:
            # Already imported -- skip silently
            entries.append(ImageImportEntry(
                path=media_path,
                skipped=True,
            ))
            skipped_existing += 1
            continue

        is_video = media_path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS

        if is_video:
            # Video path: probe via ffprobe, skip image-specific processing
            entries.append(_import_video(media_path))
            continue

        # Image path: full pipeline (probe, validate, bucket, blur, phash, dedup)
        # Step 3a: Probe
        try:
            metadata = probe_image(media_path)
        except Exception as exc:
            logger.error("Failed to probe image '%s': %s", media_path, exc)
            entries.append(ImageImportEntry(path=media_path))
            continue

        # Step 3b: Validate
        validation = validate_image(metadata, min_resolution, max_resolution)
        extra_issues: list[ValidationIssue] = []

        # Step 3c: Bucket assignment (only if not corrupt and buckets provided)
        assigned_bucket: tuple[int, int] | None = None
        if buckets and not metadata.is_corrupt:
            assigned_bucket = assign_to_bucket(
                metadata.width, metadata.height, buckets, max_aspect_ratio
            )
            if assigned_bucket is None:
                extra_issues.append(ValidationIssue(
                    code=IssueCode.IMAGE_EXTREME_ASPECT,
                    severity=Severity.WARNING,
                    message=(
                        f"Image aspect ratio {metadata.aspect_ratio:.2f} exceeds "
                        f"max_aspect_ratio={max_aspect_ratio}. No valid bucket found."
                    ),
                    field="aspect_ratio",
                    actual=f"{metadata.aspect_ratio:.2f}",
                    expected=f"<={max_aspect_ratio}",
                ))
            else:
                if needs_upscale(metadata.width, metadata.height, assigned_bucket[0], assigned_bucket[1]):
                    extra_issues.append(ValidationIssue(
                        code=IssueCode.IMAGE_UPSCALE_REQUIRED,
                        severity=Severity.WARNING,
                        message=(
                            f"Image {metadata.display_resolution} is smaller than "
                            f"bucket {assigned_bucket[0]}x{assigned_bucket[1]}. "
                            f"Upscaling will be required."
                        ),
                        field="resolution",
                        actual=metadata.display_resolution,
                        expected=f"{assigned_bucket[0]}x{assigned_bucket[1]}",
                    ))

        # Step 3d: Blur score (skip corrupt images)
        blur_score: float | None = None
        if not metadata.is_corrupt:
            try:
                from PIL import Image
                with Image.open(media_path) as pil_img:
                    blur_score = compute_blur_score(pil_img)
                    blurry = blur_score < BLUR_THRESHOLD
                if blurry:
                    extra_issues.append(ValidationIssue(
                        code=IssueCode.IMAGE_BLUR_DETECTED,
                        severity=Severity.WARNING,
                        message=(
                            f"Image appears blurry (Laplacian variance={blur_score:.1f} "
                            f"< threshold 100.0). May reduce training quality."
                        ),
                        field="blur_score",
                        actual=f"{blur_score:.1f}",
                        expected=">=100.0",
                    ))
            except Exception as exc:
                logger.warning("Failed to compute blur score for '%s': %s", media_path, exc)

        # Step 3e: pHash computation (skip corrupt images)
        phash_hex: str | None = None
        if not metadata.is_corrupt:
            try:
                phash_hex = compute_phash(media_path)
            except Exception as exc:
                logger.warning("Failed to compute pHash for '%s': %s", media_path, exc)

        # Step 3f: Near-duplicate check against accumulated hash map
        is_near_dup = False
        dup_of: Path | None = None
        if phash_hex is not None:
            for existing_hash, existing_path in hash_map.items():
                if are_near_duplicates(phash_hex, existing_hash):
                    is_near_dup = True
                    dup_of = existing_path
                    extra_issues.append(ValidationIssue(
                        code=IssueCode.IMAGE_NEAR_DUPLICATE,
                        severity=Severity.WARNING,
                        message=(
                            f"Image is a near-duplicate of {existing_path.name}. "
                            f"Consider removing to avoid training on duplicates."
                        ),
                        field="phash",
                        actual=phash_hex,
                        expected="unique",
                    ))
                    break
            # Add this image's hash to the map regardless (so subsequent images
            # in same batch can detect duplicates of this one)
            if not is_near_dup:
                hash_map[phash_hex] = media_path

        # Merge extra issues into validation (ImageValidation is frozen, create new)
        if extra_issues:
            validation = ImageValidation(
                metadata=metadata,
                issues=list(validation.issues) + extra_issues,
            )

        entries.append(ImageImportEntry(
            path=media_path,
            metadata=metadata,
            validation=validation,
            bucket=assigned_bucket,
            blur_score=blur_score,
            phash=phash_hex,
            is_near_duplicate=is_near_dup,
            duplicate_of=dup_of,
            skipped=False,
        ))

    # Step 4: Compute accurate counts
    non_skipped = [e for e in entries if not e.skipped]
    imported = len(non_skipped)  # all non-skipped are "imported" (even with errors)
    rejected = sum(
        1 for e in non_skipped
        if e.validation is not None and not e.validation.is_valid
    )
    warned = sum(
        1 for e in non_skipped
        if e.validation is not None
        and e.validation.is_valid
        and len(e.validation.warnings) > 0
    )
    near_duplicates_flagged = sum(1 for e in non_skipped if e.is_near_duplicate)

    report = ImageImportReport(
        total_discovered=total_discovered,
        imported=imported,
        skipped_existing=skipped_existing,
        rejected=rejected,
        warned=warned,
        near_duplicates_flagged=near_duplicates_flagged,
        entries=entries,
    )

    # Step 5: Persist results to manifest
    def _to_rel(p: Path) -> str:
        try:
            return str(p.resolve().relative_to(project_dir_resolved))
        except ValueError:
            return str(p)

    manifest_entries: list[dict] = []
    for entry in non_skipped:
        manifest_entries.append(_entry_to_dict(entry, _to_rel))

    save_image_entries(project_dir, manifest_entries)

    return report


def _probe_video(video_path: Path) -> dict:
    """Probe a video file using ffprobe and return metadata.

    Args:
        video_path: Absolute path to the video file.

    Returns:
        Dict with width, height, duration, fps, and codec fields.
    """
    import json
    import subprocess

    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0:
        logger.warning("ffprobe failed for '%s': %s", video_path, result.stderr.decode(errors="replace")[:200])
        return {"width": 0, "height": 0}

    data = json.loads(result.stdout)
    video_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        return {"width": 0, "height": 0}

    # Parse frame rate from r_frame_rate (e.g. "30/1" or "24000/1001")
    fps = 0.0
    r_frame_rate = video_stream.get("r_frame_rate", "0/1")
    try:
        num, den = r_frame_rate.split("/")
        if int(den) > 0:
            fps = round(int(num) / int(den), 2)
    except (ValueError, ZeroDivisionError):
        pass

    return {
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "duration": float(data.get("format", {}).get("duration", 0)),
        "fps": fps,
        "codec": video_stream.get("codec_name", "unknown"),
    }


def _import_video(video_path: Path) -> ImageImportEntry:
    """Import a single video file — probe metadata, skip image-specific steps.

    Args:
        video_path: Path to the video file.

    Returns:
        ImageImportEntry with video metadata (no validation/bucket/blur/phash).
    """
    try:
        video_meta = _probe_video(video_path)
        # Create a minimal ImageMetadata-like structure for consistency
        metadata = ImageMetadata(
            path=video_path,
            width=video_meta.get("width", 0),
            height=video_meta.get("height", 0),
            format="video",
            color_mode="RGB",
        )
        return ImageImportEntry(
            path=video_path,
            metadata=metadata,
            skipped=False,
        )
    except Exception as exc:
        logger.error("Failed to probe video '%s': %s", video_path, exc)
        return ImageImportEntry(path=video_path)


def _entry_to_dict(entry: ImageImportEntry, to_rel: Callable[[Path], str]) -> dict:
    """Serialize an ImageImportEntry to a manifest dict.

    Args:
        entry: The entry to serialize.
        to_rel: Callable that converts a Path to a relative path string.

    Returns:
        Dict for inclusion in manifest["images"].
    """
    is_video = entry.path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS

    # Videos skip image validation (entry.validation is None), so use
    # metadata presence as a validity proxy instead.
    if is_video:
        status = "valid" if (entry.metadata and entry.metadata.width > 0) else "invalid"
    else:
        status = "valid" if (entry.validation and entry.validation.is_valid) else "invalid"

    d: dict = {
        "type": "video" if is_video else "image",
        "path": to_rel(entry.path),
        "status": status,
    }

    if entry.metadata:
        d["width"] = entry.metadata.width
        d["height"] = entry.metadata.height
        d["format"] = entry.metadata.format

    if entry.bucket:
        d["bucket"] = f"{entry.bucket[0]}x{entry.bucket[1]}"

    if entry.phash is not None:
        d["phash"] = entry.phash

    if entry.blur_score is not None:
        d["blur_score"] = entry.blur_score

    if entry.is_near_duplicate and entry.duplicate_of is not None:
        d["near_duplicate_of"] = to_rel(entry.duplicate_of)

    if entry.validation and entry.validation.issues:
        d["issues"] = [
            {
                "code": issue.code.value,
                "severity": issue.severity.value,
                "message": issue.message,
            }
            for issue in entry.validation.issues
        ]

    return d
