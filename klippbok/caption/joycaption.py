"""JoyCaption subprocess detection.

Finds an existing JoyCaption installation by checking common install paths
and the JOYCAPTION_PATH environment variable.

JoyCaption runs as a subprocess in its own venv (unlike VLM backends which
use API calls). This module only handles detection — the subprocess launch
lives in the router/service that orchestrates caption generation.

Pattern mirrors detect_seedvr2() in klippbok/services/upscale_service.py.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _build_joycaption_paths() -> list[Path]:
    """Build the list of candidate JoyCaption paths to check."""
    candidates: list[Path] = [
        Path(r"C:\GenAI\Tools\JoyCaption"),
        Path.home() / "GenAI" / "Tools" / "JoyCaption",
    ]
    env_path = os.environ.get("JOYCAPTION_PATH")
    if env_path:
        candidates.append(Path(env_path))
    return candidates


# Module-level list (can be patched in tests — mirrors _SEEDVR2_COMMON_PATHS pattern)
_JOYCAPTION_COMMON_PATHS: list[Path] = _build_joycaption_paths()


def detect_joycaption() -> Path | None:
    """Find a JoyCaption installation at known paths.

    Checks each candidate path for the presence of a Python executable in
    the venv:
    - venv/Scripts/python.exe (Windows)
    - venv/bin/python (Linux/macOS)

    Also checks the JOYCAPTION_PATH environment variable (included in
    _JOYCAPTION_COMMON_PATHS at module load time via _build_joycaption_paths).

    Returns:
        Root directory of the JoyCaption installation, or None if not found.
    """
    for candidate in _JOYCAPTION_COMMON_PATHS:
        if not candidate:
            continue
        # Support both Windows (Scripts) and Linux/macOS (bin) venv layouts
        python_candidates = [
            candidate / "venv" / "Scripts" / "python.exe",  # Windows
            candidate / "venv" / "bin" / "python",           # Linux/macOS
        ]

        if any(p.is_file() for p in python_candidates):
            logger.debug("Found JoyCaption installation at: %s", candidate)
            return candidate

    logger.debug("JoyCaption not found at any of: %s", _JOYCAPTION_COMMON_PATHS)
    return None
