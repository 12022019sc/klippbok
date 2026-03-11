"""Canonical path utilities for manifest-format paths and image IDs.

All image IDs in klippbok are SHA256[:16] of the manifest-format relative
path string (forward slashes, relative to project root).  This module is
the single source of truth for that computation.

Functions:
    image_id        -- SHA256[:16] of a manifest-format relative path string.
    to_manifest_path -- Convert any path (absolute or relative) to manifest format.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def image_id(relative_path: str) -> str:
    """Compute the image ID from a manifest-format relative path string.

    Args:
        relative_path: Path string exactly as stored in manifest.json
            (forward slashes, relative to project root).

    Returns:
        SHA256 hex digest of the path, truncated to 16 characters.
    """
    return hashlib.sha256(relative_path.encode()).hexdigest()[:16]


def to_manifest_path(path: Path, project_dir: Path) -> str:
    """Convert any path (absolute or relative) to manifest-format string.

    Manifest paths use forward slashes and are relative to the project root.
    This normalizes Windows backslashes and resolves absolute paths.

    Args:
        path: File path (absolute or relative).
        project_dir: Project root directory.

    Returns:
        Forward-slash relative path string suitable for manifest storage
        and image_id() computation.
    """
    try:
        rel = path.resolve().relative_to(project_dir.resolve())
    except ValueError:
        rel = path
    return str(rel).replace("\\", "/")
