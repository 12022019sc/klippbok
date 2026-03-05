"""Unit tests for klippbok.caption.joycaption.

Tests cover:
- detect_joycaption() returns None when no venv found at any candidate path
- detect_joycaption() returns Path when venv/Scripts/python.exe exists (Windows)
- detect_joycaption() returns Path when venv/bin/python exists (Linux)
- detect_joycaption() checks JOYCAPTION_PATH env var as a candidate
- _JOYCAPTION_COMMON_PATHS is a patchable module-level list
- _JOYCAPTION_RUNNER_SCRIPT has valid Python syntax
- run_joycaption_image() accepts caption_mode parameter and passes --mode
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_detect_joycaption_returns_none_when_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """detect_joycaption() returns None when no JoyCaption venv exists at any candidate path."""
    import klippbok.caption.joycaption as jc_module

    # Point to empty directories
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setattr(jc_module, "_JOYCAPTION_COMMON_PATHS", [empty_dir, tmp_path / "nonexistent"])

    from klippbok.caption.joycaption import detect_joycaption
    result = detect_joycaption()

    assert result is None


def test_detect_joycaption_returns_path_for_windows_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """detect_joycaption() returns the matching Path when venv/Scripts/python.exe exists (Windows)."""
    import klippbok.caption.joycaption as jc_module

    install_dir = tmp_path / "JoyCaption"
    python_exe = install_dir / "venv" / "Scripts" / "python.exe"
    python_exe.parent.mkdir(parents=True)
    python_exe.touch()

    monkeypatch.setattr(jc_module, "_JOYCAPTION_COMMON_PATHS", [install_dir])

    from klippbok.caption.joycaption import detect_joycaption
    result = detect_joycaption()

    assert result == install_dir


def test_detect_joycaption_returns_path_for_linux_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """detect_joycaption() returns the matching Path when venv/bin/python exists (Linux)."""
    import klippbok.caption.joycaption as jc_module

    install_dir = tmp_path / "JoyCaption"
    python_bin = install_dir / "venv" / "bin" / "python"
    python_bin.parent.mkdir(parents=True)
    python_bin.touch()

    monkeypatch.setattr(jc_module, "_JOYCAPTION_COMMON_PATHS", [install_dir])

    from klippbok.caption.joycaption import detect_joycaption
    result = detect_joycaption()

    assert result == install_dir


def test_detect_joycaption_checks_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """detect_joycaption() finds an installation specified via JOYCAPTION_PATH env var.

    Uses _build_joycaption_paths() to verify that JOYCAPTION_PATH is included
    in the candidate list. We control the full paths list so static paths that
    exist on disk don't interfere with the assertion.
    """
    env_install_dir = tmp_path / "custom" / "JoyCaption"
    python_exe = env_install_dir / "venv" / "Scripts" / "python.exe"
    python_exe.parent.mkdir(parents=True)
    python_exe.touch()

    monkeypatch.setenv("JOYCAPTION_PATH", str(env_install_dir))

    import klippbok.caption.joycaption as jc_module

    # Verify _build_joycaption_paths() includes the env var path
    new_paths = jc_module._build_joycaption_paths()
    assert env_install_dir in new_paths, "_build_joycaption_paths() must include JOYCAPTION_PATH"

    # Override the module-level list to contain ONLY the env var path
    # (prevents the static C:\GenAI\Tools\JoyCaption path from matching if it exists)
    monkeypatch.setattr(jc_module, "_JOYCAPTION_COMMON_PATHS", [env_install_dir])

    from klippbok.caption.joycaption import detect_joycaption
    result = detect_joycaption()

    assert result == env_install_dir


def test_joycaption_common_paths_is_patchable(monkeypatch: pytest.MonkeyPatch) -> None:
    """_JOYCAPTION_COMMON_PATHS is a module-level list that can be patched in tests."""
    import klippbok.caption.joycaption as jc_module

    original = jc_module._JOYCAPTION_COMMON_PATHS
    monkeypatch.setattr(jc_module, "_JOYCAPTION_COMMON_PATHS", [])

    assert jc_module._JOYCAPTION_COMMON_PATHS == []

    # Restore
    monkeypatch.setattr(jc_module, "_JOYCAPTION_COMMON_PATHS", original)
    assert jc_module._JOYCAPTION_COMMON_PATHS == original


def test_detect_joycaption_returns_first_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """detect_joycaption() returns the first matching installation when multiple exist."""
    import klippbok.caption.joycaption as jc_module

    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    for d in (first_dir, second_dir):
        python_exe = d / "venv" / "Scripts" / "python.exe"
        python_exe.parent.mkdir(parents=True)
        python_exe.touch()

    monkeypatch.setattr(jc_module, "_JOYCAPTION_COMMON_PATHS", [first_dir, second_dir])

    from klippbok.caption.joycaption import detect_joycaption
    result = detect_joycaption()

    assert result == first_dir


def test_runner_script_syntax() -> None:
    """_JOYCAPTION_RUNNER_SCRIPT compiles without syntax errors.

    The inline runner script executes in a separate Python interpreter where
    syntax errors are only caught at runtime. This test catches them at test time.
    (Pitfall 3 from RESEARCH.md)
    """
    from klippbok.caption.joycaption import _JOYCAPTION_RUNNER_SCRIPT

    # compile() validates syntax without executing
    compile(_JOYCAPTION_RUNNER_SCRIPT, "<joycaption_runner>", "exec")


def test_runner_script_has_mode_argument() -> None:
    """_JOYCAPTION_RUNNER_SCRIPT contains --mode argument for caption mode selection."""
    from klippbok.caption.joycaption import _JOYCAPTION_RUNNER_SCRIPT

    assert "--mode" in _JOYCAPTION_RUNNER_SCRIPT, (
        "_JOYCAPTION_RUNNER_SCRIPT must add --mode argument to control prompt selection"
    )


def test_runner_script_has_all_mode_prompts() -> None:
    """_JOYCAPTION_RUNNER_SCRIPT contains all 5 caption mode prompts."""
    from klippbok.caption.joycaption import _JOYCAPTION_RUNNER_SCRIPT

    required_modes = [
        "booru_tags",
        "context_only_tags",
        "context_only_natural",
        "descriptive",
        "straightforward",
    ]
    for mode in required_modes:
        assert mode in _JOYCAPTION_RUNNER_SCRIPT, (
            f"MODE_PROMPTS in runner script must contain key '{mode}'"
        )


def test_run_joycaption_image_accepts_caption_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_joycaption_image() accepts caption_mode parameter and passes --mode to subprocess."""
    import subprocess
    import klippbok.caption.joycaption as jc_module

    # Create a fake JoyCaption installation
    venv_dir = tmp_path / "venv" / "Scripts"
    venv_dir.mkdir(parents=True)
    python_exe = venv_dir / "python.exe"
    python_exe.write_text("fake")

    # Capture subprocess.Popen call args
    captured_cmd: list[list[str]] = []

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            captured_cmd.append(cmd)
            self.stdout = None
            self.returncode = 0

    monkeypatch.setattr(jc_module.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(jc_module.platform, "system", lambda: "Windows")

    from klippbok.caption.joycaption import run_joycaption_image

    run_joycaption_image(tmp_path, [], trigger_word="", caption_mode="descriptive")

    assert len(captured_cmd) == 1
    cmd = captured_cmd[0]
    assert "--mode" in cmd, "run_joycaption_image must pass --mode to subprocess"
    mode_idx = cmd.index("--mode")
    assert cmd[mode_idx + 1] == "descriptive", (
        f"--mode value should be 'descriptive', got '{cmd[mode_idx + 1]}'"
    )
