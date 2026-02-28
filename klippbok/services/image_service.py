"""Image import and validation service.

Stateless service functions that compose image probing, validation,
and discovery into higher-level operations. Both CLI and future
API/GUI routes call these functions.

All functions are pure -- no side effects, no state.
"""

from __future__ import annotations

import logging
from pathlib import Path

from klippbok.image.bucket import assign_to_bucket, needs_upscale
from klippbok.image.dedup import are_near_duplicates, compute_phash
from klippbok.image.discover import discover_images
from klippbok.image.models import (
    ImageImportEntry,
    ImageImportReport,
    ImageMetadata,
    ImageValidation,
)
from klippbok.image.probe import probe_image
from klippbok.image.quality import compute_blur_score, is_blurry
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

    # Step 2: Discover images
    discovered_paths = discover_images(directory, recursive=recursive)
    total_discovered = len(discovered_paths)

    # Step 3: Separate new vs already-imported (canonical relative path comparison)
    project_dir_resolved = project_dir.resolve()
    entries: list[ImageImportEntry] = []
    skipped_existing = 0

    for img_path in discovered_paths:
        try:
            rel_str = str(img_path.resolve().relative_to(project_dir_resolved))
        except ValueError:
            rel_str = str(img_path)

        if rel_str in known_paths:
            # Already imported -- skip silently
            entries.append(ImageImportEntry(
                path=img_path,
                skipped=True,
            ))
            skipped_existing += 1
            continue

        # Step 3a: Probe
        try:
            metadata = probe_image(img_path)
        except Exception as exc:
            logger.error("Failed to probe image '%s': %s", img_path, exc)
            entries.append(ImageImportEntry(path=img_path))
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
                with Image.open(img_path) as pil_img:
                    blur_score = compute_blur_score(pil_img)
                    blurry = is_blurry(pil_img)
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
                logger.warning("Failed to compute blur score for '%s': %s", img_path, exc)

        # Step 3e: pHash computation (skip corrupt images)
        phash_hex: str | None = None
        if not metadata.is_corrupt:
            try:
                phash_hex = compute_phash(img_path)
            except Exception as exc:
                logger.warning("Failed to compute pHash for '%s': %s", img_path, exc)

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
                hash_map[phash_hex] = img_path

        # Merge extra issues into validation (ImageValidation is frozen, create new)
        if extra_issues:
            validation = ImageValidation(
                metadata=metadata,
                issues=list(validation.issues) + extra_issues,
            )

        entries.append(ImageImportEntry(
            path=img_path,
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
    project_dir_resolved_str = str(project_dir_resolved)

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


def _entry_to_dict(entry: ImageImportEntry, to_rel: object) -> dict:
    """Serialize an ImageImportEntry to a manifest dict.

    Args:
        entry: The entry to serialize.
        to_rel: Callable that converts a Path to a relative path string.

    Returns:
        Dict for inclusion in manifest["images"].
    """
    d: dict = {
        "type": "image",
        "path": to_rel(entry.path),  # type: ignore[operator]
        "status": "valid" if (entry.validation and entry.validation.is_valid) else "invalid",
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
        d["near_duplicate_of"] = to_rel(entry.duplicate_of)  # type: ignore[operator]

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
