"""Project service -- manifest persistence for session-to-session state.

The project manifest (``.klippbok/manifest.json``) stores sample state
so that processing can be resumed across sessions. It uses relative
paths for portability -- move the project folder and the manifest
still works.

This is separate from the existing ``klippbok_manifest.json`` (validation
snapshot). The project manifest tracks *processing state*, not just
validation results.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from klippbok.dataset.models import SamplePair
from klippbok.video.models import Severity


MANIFEST_DIR = ".klippbok"
MANIFEST_FILE = "manifest.json"


def save_manifest(
    project_dir: Path,
    samples: list[dict],
    *,
    version: str = "1",
) -> Path:
    """Write the project manifest to ``.klippbok/manifest.json``.

    Creates the ``.klippbok/`` directory if it does not exist.

    Args:
        project_dir: Root of the project directory.
        samples: List of sample dicts (see :func:`sample_to_manifest_entry`).
        version: Manifest schema version.

    Returns:
        Path to the written manifest file.
    """
    manifest_dir = project_dir / MANIFEST_DIR
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / MANIFEST_FILE

    now = datetime.now(timezone.utc).isoformat()

    # Preserve created timestamp if manifest already exists
    existing = load_manifest(project_dir)
    created = existing["created"] if existing and "created" in existing else now

    data = {
        "version": version,
        "created": created,
        "updated": now,
        "samples": samples,
    }

    manifest_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def load_manifest(project_dir: Path) -> dict | None:
    """Read the project manifest if it exists.

    Args:
        project_dir: Root of the project directory.

    Returns:
        Parsed manifest dict, or ``None`` if no manifest is found.

    Raises:
        ValueError: If the manifest exists but is missing the ``version`` field.
    """
    manifest_path = project_dir / MANIFEST_DIR / MANIFEST_FILE
    if not manifest_path.exists():
        return None

    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    if "version" not in data:
        raise ValueError(
            f"Invalid manifest at {manifest_path}: missing 'version' field. "
            f"The file may be corrupted or from an incompatible version."
        )

    return data


def manifest_exists(project_dir: Path) -> bool:
    """Check whether a project manifest exists.

    Args:
        project_dir: Root of the project directory.

    Returns:
        ``True`` if ``.klippbok/manifest.json`` exists.
    """
    return (project_dir / MANIFEST_DIR / MANIFEST_FILE).exists()


def sample_to_manifest_entry(
    sample: SamplePair,
    project_dir: Path,
) -> dict:
    """Convert a :class:`SamplePair` to a manifest dict entry.

    Uses relative paths for portability. Serializes issues so they
    can be restored later.

    Args:
        sample: The sample pair to convert.
        project_dir: Root directory for computing relative paths.

    Returns:
        Dict suitable for inclusion in the manifest ``samples`` list.
    """
    def _relative(p: Path | None) -> str | None:
        if p is None:
            return None
        try:
            return str(p.relative_to(project_dir))
        except ValueError:
            return str(p)

    entry: dict = {
        "stem": sample.stem,
        "target": _relative(sample.target),
        "type": "video",
        "status": "valid" if sample.is_valid else "invalid",
    }

    if sample.caption is not None:
        entry["caption"] = _relative(sample.caption)
    if sample.reference is not None:
        entry["reference"] = _relative(sample.reference)
    if sample.width is not None:
        entry["width"] = sample.width
    if sample.height is not None:
        entry["height"] = sample.height
    if sample.frame_count is not None:
        entry["frame_count"] = sample.frame_count

    if sample.issues:
        entry["issues"] = [
            {
                "code": issue.code.value,
                "severity": issue.severity.value,
                "message": issue.message,
            }
            for issue in sample.issues
        ]

    return entry
