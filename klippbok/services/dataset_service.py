"""Dataset service -- stateless business logic for validation and organization.

Extracted from ``klippbok.dataset.__main__`` so that CLI, API, and GUI
can all call the same functions without duplicating logic.

All functions accept explicit inputs and return structured results.
No print statements, no sys.exit, no argparse references.
"""

from __future__ import annotations

from pathlib import Path

from klippbok.config.data_schema import KlippbokDataConfig
from klippbok.dataset.bucketing import BucketingResult, preview_bucketing as _preview_bucketing
from klippbok.dataset.models import (
    DatasetReport,
    OrganizeLayout,
    OrganizeResult,
)
from klippbok.dataset.organize import organize_dataset
from klippbok.dataset.validate import validate_all


def validate(
    config: KlippbokDataConfig,
    config_dir: Path,
    *,
    quality: bool = False,
    duplicates: bool = False,
) -> DatasetReport:
    """Validate all datasets defined in *config*.

    Applies optional CLI-style quality/duplicate overrides to the config,
    then delegates to :func:`klippbok.dataset.validate.validate_all`.

    Args:
        config: The data config describing dataset sources.
        config_dir: Base directory for resolving relative paths.
        quality: If ``True``, enable blur and exposure quality checks
            using sensible defaults when not already configured.
        duplicates: If ``True``, enable perceptual duplicate detection.

    Returns:
        A :class:`DatasetReport` spanning all configured sources.
    """
    if quality:
        config = config.model_copy(update={
            "quality": config.quality.model_copy(update={
                "blur_threshold": config.quality.blur_threshold or 50.0,
                "exposure_range": config.quality.exposure_range or (0.05, 0.95),
            }),
        })
    if duplicates:
        config = config.model_copy(update={
            "quality": config.quality.model_copy(update={
                "check_duplicates": True,
            }),
        })

    return validate_all(config, config_dir=config_dir)


def _resolve_concepts(
    source_path: Path,
    concepts_str: str,
) -> list[Path]:
    """Resolve concept names to subdirectory paths.

    Scans *source_path* for subdirectories matching the requested concept
    names. Returns the matched paths or raises with a helpful error
    listing what is actually available.

    Args:
        source_path: Parent triage directory (e.g. sorted/).
        concepts_str: Comma-separated concept names (e.g. "holly,cat").

    Returns:
        List of resolved subdirectory paths.

    Raises:
        ValueError: If any requested concept names do not match a subdirectory.
    """
    requested = [c.strip() for c in concepts_str.split(",") if c.strip()]

    available = sorted(
        d.name for d in source_path.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )

    matched: list[Path] = []
    unmatched: list[str] = []

    for name in requested:
        concept_dir = source_path / name
        if concept_dir.is_dir():
            matched.append(concept_dir)
        else:
            unmatched.append(name)

    if unmatched:
        available_str = ", ".join(available) if available else "(no subfolders found)"
        msg = (
            f"Concept folder(s) not found: {', '.join(unmatched)}\n"
            f"Available in {source_path}: {available_str}"
        )
        raise ValueError(msg)

    return matched


def organize(
    source_dir: Path,
    output_dir: Path,
    layout: OrganizeLayout,
    *,
    config: KlippbokDataConfig | None = None,
    copy: bool = True,
    include_warnings: bool = True,
    dry_run: bool = False,
    trainers: list[str] | None = None,
    concepts: str | None = None,
) -> OrganizeResult:
    """Organize a validated dataset into a clean, trainer-ready directory.

    Handles concept resolution (``--concepts`` CLI flag) and delegates
    to :func:`klippbok.dataset.organize.organize_dataset`.

    Args:
        source_dir: Path to the source dataset folder.
        output_dir: Where to place organized files.
        layout: Output layout (FLAT or DIMLJUS).
        config: Data config for validation. ``None`` uses defaults.
        copy: ``True`` to copy files, ``False`` to move them.
        include_warnings: ``True`` to include samples with warnings
            but no errors. ``False`` for strict mode.
        dry_run: ``True`` to preview without touching files.
        trainers: List of trainer names to generate configs for.
        concepts: Comma-separated concept folder names to filter by,
            or ``None`` to organize all samples.

    Returns:
        An :class:`OrganizeResult` with organized/skipped samples.

    Raises:
        ValueError: If concept names do not match subdirectories.
        OrganizeError: If source does not exist or has zero valid samples.
    """
    if concepts is not None:
        concept_dirs = _resolve_concepts(source_dir, concepts)

        if config is None:
            config = KlippbokDataConfig(
                datasets=[{"path": str(d)} for d in concept_dirs],
            )
        else:
            config = config.model_copy(update={
                "datasets": [{"path": str(d)} for d in concept_dirs],
            })

    return organize_dataset(
        source_dir=source_dir,
        output_dir=output_dir,
        layout=layout,
        config=config,
        copy=copy,
        include_warnings=include_warnings,
        dry_run=dry_run,
        trainers=trainers,
    )


def preview_bucketing(
    report: DatasetReport,
    min_bucket_size: int = 2,
) -> BucketingResult:
    """Preview how samples would be distributed into training buckets.

    Thin wrapper around :func:`klippbok.dataset.bucketing.preview_bucketing`
    for a consistent service API.

    Args:
        report: Validated dataset report with sample metadata.
        min_bucket_size: Minimum samples per bucket before a warning
            is generated.

    Returns:
        A :class:`BucketingResult` with assignments and bucket groups.
    """
    return _preview_bucketing(report, min_bucket_size=min_bucket_size)
