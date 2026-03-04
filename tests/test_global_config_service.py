"""Unit tests for klippbok.services.global_config_service.

Tests cover:
- load_global_config() returns {} when config file is absent
- load_global_config() parses JSON correctly when file exists
- save_global_config() creates directory if needed
- save_global_config() + load_global_config() round-trip
- save_global_config() uses atomic write (temp file + os.replace)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# load_global_config
# ---------------------------------------------------------------------------


def test_load_global_config_returns_empty_dict_when_file_absent(tmp_path: Path) -> None:
    """load_global_config() returns {} when ~/.klippbok/config.json does not exist."""
    fake_config_file = tmp_path / "config.json"

    with patch("klippbok.services.global_config_service._GLOBAL_CONFIG_FILE", fake_config_file):
        from klippbok.services.global_config_service import load_global_config
        result = load_global_config()

    assert result == {}


def test_load_global_config_parses_json_when_file_exists(tmp_path: Path) -> None:
    """load_global_config() returns parsed dict when config.json has valid JSON."""
    fake_config_file = tmp_path / "config.json"
    expected = {"provider": "lm_studio", "gemini_api_key": "test-key"}
    fake_config_file.write_text(json.dumps(expected), encoding="utf-8")

    with patch("klippbok.services.global_config_service._GLOBAL_CONFIG_FILE", fake_config_file):
        from klippbok.services.global_config_service import load_global_config
        result = load_global_config()

    assert result == expected


def test_load_global_config_returns_empty_dict_on_invalid_json(tmp_path: Path) -> None:
    """load_global_config() returns {} when the file contains invalid JSON."""
    fake_config_file = tmp_path / "config.json"
    fake_config_file.write_text("{ invalid json }", encoding="utf-8")

    with patch("klippbok.services.global_config_service._GLOBAL_CONFIG_FILE", fake_config_file):
        from klippbok.services.global_config_service import load_global_config
        result = load_global_config()

    assert result == {}


# ---------------------------------------------------------------------------
# save_global_config
# ---------------------------------------------------------------------------


def test_save_global_config_creates_directory_if_absent(tmp_path: Path) -> None:
    """save_global_config() creates ~/.klippbok/ directory if it does not exist."""
    nested_dir = tmp_path / "nested" / "klippbok"
    fake_config_file = nested_dir / "config.json"

    assert not nested_dir.exists()

    with patch("klippbok.services.global_config_service._GLOBAL_CONFIG_FILE", fake_config_file):
        from klippbok.services.global_config_service import save_global_config
        save_global_config({"provider": "gemini"})

    assert nested_dir.exists()
    assert fake_config_file.exists()


def test_save_global_config_round_trips_correctly(tmp_path: Path) -> None:
    """save_global_config() then load_global_config() returns the original dict."""
    fake_config_file = tmp_path / "config.json"
    original = {
        "provider": "lm_studio",
        "lm_studio_base_url": "http://localhost:1234/v1",
        "gemini_api_key": "my-api-key",
    }

    with patch("klippbok.services.global_config_service._GLOBAL_CONFIG_FILE", fake_config_file):
        from klippbok.services.global_config_service import load_global_config, save_global_config
        save_global_config(original)
        result = load_global_config()

    assert result == original


def test_save_global_config_uses_atomic_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """save_global_config() writes to a temp file then os.replace (atomic)."""
    import klippbok.services.global_config_service as gcs_module

    fake_config_file = tmp_path / "config.json"
    monkeypatch.setattr(gcs_module, "_GLOBAL_CONFIG_FILE", fake_config_file)

    replace_calls: list[tuple] = []
    original_replace = os.replace

    def mock_replace(src: str, dst: str) -> None:
        replace_calls.append((src, dst))
        original_replace(src, dst)

    monkeypatch.setattr(os, "replace", mock_replace)

    from klippbok.services.global_config_service import save_global_config
    save_global_config({"test": "value"})

    assert len(replace_calls) == 1, "os.replace should be called exactly once"
    src, dst = replace_calls[0]
    assert dst == str(fake_config_file), "os.replace destination must be the config file"
    # Source must be a temp file in the same directory
    assert Path(src).parent == fake_config_file.parent


def test_save_global_config_writes_valid_json(tmp_path: Path) -> None:
    """save_global_config() produces valid JSON that can be parsed back."""
    fake_config_file = tmp_path / "config.json"
    data = {"nested": {"key": "value"}, "list": [1, 2, 3]}

    with patch("klippbok.services.global_config_service._GLOBAL_CONFIG_FILE", fake_config_file):
        from klippbok.services.global_config_service import save_global_config
        save_global_config(data)

    raw = fake_config_file.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed == data
