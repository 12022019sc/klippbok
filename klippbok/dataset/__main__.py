"""CLI entry point for dataset validation and organization.

Usage:
    python -m klippbok.dataset validate <path>
    python -m klippbok.dataset validate <path> --manifest
    python -m klippbok.dataset validate <path> --buckets
    python -m klippbok.dataset validate <path> --quality --duplicates
    python -m klippbok.dataset validate <path> --json
    python -m klippbok.dataset organize <path> -o <output>
    python -m klippbok.dataset organize <path> -o <output> -t musubi
    python -m klippbok.dataset organize <path> -o <output> -l klippbok --manifest

The validate command discovers, validates, and reports on a dataset.
The organize command takes validated data and produces a clean,
trainer-ready directory with optional trainer config generation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the dataset CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m klippbok.dataset",
        description="Klippbok dataset validation and organization tools.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run.")

    # validate command
    validate = subparsers.add_parser(
        "validate",
        help="Validate a dataset: check completeness, quality, and organization.",
    )
    validate.add_argument(
        "path",
        help="Path to the dataset folder (or a klippbok_data.yaml config file).",
    )
    validate.add_argument(
        "--config",
        help="Path to a klippbok_data.yaml config file. If not provided, uses defaults.",
    )
    validate.add_argument(
        "--manifest",
        action="store_true",
        help="Write a klippbok_manifest.json file to the dataset folder.",
    )
    validate.add_argument(
        "--buckets",
        action="store_true",
        help="Show bucketing preview (how samples would be grouped for training).",
    )
    validate.add_argument(
        "--quality",
        action="store_true",
        help="Enable quality checks (blur, exposure) on reference images.",
    )
    validate.add_argument(
        "--duplicates",
        action="store_true",
        help="Enable perceptual duplicate detection on reference images.",
    )
    validate.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON instead of formatted report.",
    )

    # organize command
    organize = subparsers.add_parser(
        "organize",
        help="Organize validated data into a clean, trainer-ready directory.",
    )
    organize.add_argument(
        "path",
        help="Source dataset folder.",
    )
    organize.add_argument(
        "--output", "-o",
        required=True,
        help="Output directory for organized files.",
    )
    organize.add_argument(
        "--layout", "-l",
        choices=["flat", "klippbok"],
        default="flat",
        help="Output layout: flat (default, universal) or klippbok (hierarchical).",
    )
    organize.add_argument(
        "--trainer", "-t",
        action="append",
        dest="trainers",
        metavar="NAME",
        help="Generate trainer config: musubi, aitoolkit. Repeatable.",
    )
    organize.add_argument(
        "--concepts",
        help=(
            "Only organize clips from these triage concept folders. "
            "Comma-separated names matching subfolders of the source path. "
            "Example: --concepts hollygolightly,cat"
        ),
    )
    organize.add_argument(
        "--move",
        action="store_true",
        help="Move files instead of copy (destructive).",
    )
    organize.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would happen without touching files.",
    )
    organize.add_argument(
        "--strict",
        action="store_true",
        help="Also exclude samples with warnings (default: only exclude errors).",
    )
    organize.add_argument(
        "--config", "-c",
        help="Path to klippbok_data.yaml config file.",
    )
    organize.add_argument(
        "--manifest",
        action="store_true",
        help="Write klippbok_manifest.json to output directory.",
    )

    return parser


def _format_validate_hint(dataset_path: Path) -> str:
    """Build a copy-pasteable organize command hint.

    Printed after validate completes so the user knows how to
    proceed to the next step.

    Args:
        dataset_path: The path used in the validate command.

    Returns:
        Formatted hint string.
    """
    # Use forward slashes for readability
    path_str = str(dataset_path).replace("\\", "/")
    return (
        "\nNext step: organize for training\n"
        f"  python -m klippbok.dataset organize {path_str} -o <output_dir>\n"
        f"  python -m klippbok.dataset organize {path_str} -o <output_dir> -t musubi\n"
        f"  python -m klippbok.dataset organize {path_str} -o <output_dir> -t aitoolkit\n"
    )


def cmd_validate(args: argparse.Namespace) -> int:
    """Run the validate command.

    Delegates business logic to the service layer, keeping only
    argument parsing and output formatting here.
    """
    from klippbok.config.data_schema import KlippbokDataConfig
    from klippbok.dataset.manifest import build_manifest, write_manifest
    from klippbok.dataset.report import (
        print_bucketing_report,
        print_validation_report,
    )
    from klippbok.services import dataset_service

    dataset_path = Path(args.path).resolve()

    # Load or create config
    config: KlippbokDataConfig
    config_dir: Path

    if args.config:
        config_path = Path(args.config).resolve()
        config_dir = config_path.parent
        from klippbok.config.loader import load_config
        config = load_config(str(config_path))
    else:
        config_dir = dataset_path if dataset_path.is_dir() else dataset_path.parent
        config = KlippbokDataConfig(
            datasets=[{"path": str(dataset_path)}],
        )

    # Run validation via service layer (handles quality/duplicate overrides)
    try:
        report = dataset_service.validate(
            config, config_dir,
            quality=args.quality,
            duplicates=args.duplicates,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Output
    if args.json_output:
        manifest = build_manifest(report, config)
        print(json.dumps(manifest, indent=2))
    else:
        print_validation_report(report)

    # Bucketing preview via service layer
    if args.buckets:
        bucket_result = dataset_service.preview_bucketing(
            report,
            min_bucket_size=config.bucketing.min_bucket_size,
        )
        if args.json_output:
            # Bucketing as JSON
            bucket_dict = {
                "step_size": bucket_result.step_size,
                "total_buckets": bucket_result.total_buckets,
                "total_assigned": bucket_result.total_assigned,
                "buckets": [
                    {
                        "key": b.bucket_key,
                        "count": b.count,
                        "samples": b.samples,
                    }
                    for b in bucket_result.buckets
                ],
            }
            print(json.dumps(bucket_dict, indent=2))
        else:
            print_bucketing_report(bucket_result)

    # Write manifest (backwards-compatible klippbok_manifest.json)
    if args.manifest:
        manifest_path = dataset_path / "klippbok_manifest.json"
        if not dataset_path.is_dir():
            manifest_path = dataset_path.parent / "klippbok_manifest.json"
        write_manifest(report, config, manifest_path)
        print(f"\nManifest written to: {manifest_path}")

    # Print organize hint (only for non-JSON output with valid samples)
    if not args.json_output and report.valid_samples > 0:
        print(_format_validate_hint(dataset_path))

    return 0 if report.is_valid else 1


def cmd_organize(args: argparse.Namespace) -> int:
    """Run the organize command.

    Delegates business logic to the service layer, keeping only
    argument parsing and output formatting here.
    """
    from klippbok.config.data_schema import KlippbokDataConfig
    from klippbok.dataset.errors import OrganizeError
    from klippbok.dataset.models import OrganizeLayout
    from klippbok.dataset.report import print_organize_report
    from klippbok.services import dataset_service

    source_path = Path(args.path).resolve()
    output_path = Path(args.output).resolve()

    # Layout
    layout = OrganizeLayout.DIMLJUS if args.layout == "klippbok" else OrganizeLayout.FLAT

    # Config
    config: KlippbokDataConfig | None = None
    if args.config:
        from klippbok.config.loader import load_config
        config = load_config(str(Path(args.config).resolve()))

    # Delegate to service layer (handles concept resolution, config
    # construction, and organize_dataset call)
    try:
        result = dataset_service.organize(
            source_dir=source_path,
            output_dir=output_path,
            layout=layout,
            config=config,
            copy=not args.move,
            include_warnings=not args.strict,
            dry_run=args.dry_run,
            trainers=args.trainers,
            concepts=args.concepts,
        )
    except ValueError as e:
        # Concept resolution errors
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except OrganizeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Show which concepts were selected (after successful resolution)
    if args.concepts:
        names = [c.strip() for c in args.concepts.split(",") if c.strip()]
        print(f"Concepts: {', '.join(names)}")

    # Report
    print_organize_report(result)

    # Manifest (backwards-compatible klippbok_manifest.json)
    if args.manifest and not args.dry_run:
        from klippbok.dataset.manifest import write_manifest
        from klippbok.dataset.validate import validate_all

        if config is None:
            config = KlippbokDataConfig(datasets=[{"path": str(source_path)}])
        report = validate_all(config, config_dir=source_path)
        manifest_path = output_path / "klippbok_manifest.json"
        write_manifest(report, config, manifest_path)
        print(f"\nManifest written to: {manifest_path}")

    return 0


def main() -> None:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "validate":
        sys.exit(cmd_validate(args))
    elif args.command == "organize":
        sys.exit(cmd_organize(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
