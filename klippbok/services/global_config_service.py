"""Global configuration service for klippbok.

Provides atomic read/write access to the user-level config file at
~/.klippbok/config.json. This file stores provider settings, API keys,
and other preferences that persist across projects.

All functions are module-level stateless (per SVC-01 decision).

Key functions:
  - load_global_config: Read and parse config.json, returning {} if absent.
  - save_global_config: Write config atomically (temp file + os.replace).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Path constants (follow path convention from klippbok/config/model_config.py) ──

_USER_KLIPPBOK_DIR: Path = Path.home() / ".klippbok"
_GLOBAL_CONFIG_FILE: Path = _USER_KLIPPBOK_DIR / "config.json"


def load_global_config() -> dict:
    """Read and parse the global config file.

    Returns an empty dict when the file does not exist or contains invalid JSON.
    Never raises — callers can always rely on receiving a dict.

    Returns:
        Parsed config dict, or {} if the file is absent or unreadable.
    """
    config_file = _GLOBAL_CONFIG_FILE
    if not config_file.is_file():
        logger.debug("Global config not found at %s; returning defaults.", config_file)
        return {}

    try:
        raw = config_file.read_text(encoding="utf-8")
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Global config at %s contains invalid JSON: %s. Returning defaults.",
            config_file,
            exc,
        )
        return {}
    except OSError as exc:
        logger.warning(
            "Could not read global config at %s: %s. Returning defaults.",
            config_file,
            exc,
        )
        return {}


def save_global_config(config: dict) -> None:
    """Write config to disk atomically using a temp file + os.replace.

    Creates the ~/.klippbok/ directory if it does not exist.
    The atomic write pattern prevents corruption if the process is interrupted.

    Args:
        config: The configuration dict to persist.

    Raises:
        OSError: If the directory cannot be created or the file cannot be written.
    """
    config_file = _GLOBAL_CONFIG_FILE
    config_dir = config_file.parent

    # Create directory if it doesn't exist
    config_dir.mkdir(parents=True, exist_ok=True)

    # Write to a temp file in the same directory (same filesystem for atomic rename)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=config_dir, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.write("\n")  # POSIX convention: newline at end of file
        # Atomic rename: on POSIX this is guaranteed atomic; on Windows it replaces
        os.replace(tmp_path, str(config_file))
        logger.debug("Saved global config to %s", config_file)
    except Exception:
        # Clean up temp file if something went wrong
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
