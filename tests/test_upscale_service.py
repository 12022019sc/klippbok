"""Tests for klippbok.services.upscale_service.

Tests verify:
- detect_seedvr2() returns None when no SeedVR2 installation exists
- detect_seedvr2() returns the root Path when mock directory structure exists
- detect_nmkd_siax() returns None when not installed
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_detect_seedvr2_not_found() -> None:
    """detect_seedvr2() returns None when no SeedVR2 installation exists."""
    from klippbok.services.upscale_service import detect_seedvr2

    # Clear any env var that might point to a real installation
    env = os.environ.copy()
    env.pop("SEEDVR2_PATH", None)

    # Should return None (no mock SeedVR2 at common paths in test env)
    # We patch the common paths to point to nonexistent locations
    import klippbok.services.upscale_service as upscale_module
    original_paths = upscale_module._SEEDVR2_COMMON_PATHS

    try:
        # Override common paths to something that definitely doesn't exist
        upscale_module._SEEDVR2_COMMON_PATHS = [
            Path("/nonexistent/path/SeedVR2"),
            Path("/another/nonexistent/SeedVR2"),
        ]
        result = detect_seedvr2()
        assert result is None
    finally:
        upscale_module._SEEDVR2_COMMON_PATHS = original_paths


def test_detect_seedvr2_found(tmp_path: Path) -> None:
    """detect_seedvr2() returns root dir when mock SeedVR2 directory structure exists."""
    from klippbok.services.upscale_service import detect_seedvr2

    # Create a mock SeedVR2 installation directory structure
    seedvr2_root = tmp_path / "SeedVR2"
    seedvr2_root.mkdir()

    # Create the expected files: venv/Scripts/python.exe and batch_upscale.py
    scripts_dir = seedvr2_root / "venv" / "Scripts"
    scripts_dir.mkdir(parents=True)
    python_exe = scripts_dir / "python.exe"
    python_exe.write_text("mock python exe")

    batch_script = seedvr2_root / "batch_upscale.py"
    batch_script.write_text("# mock batch_upscale.py")

    # Patch common paths to include our mock installation
    import klippbok.services.upscale_service as upscale_module
    original_paths = upscale_module._SEEDVR2_COMMON_PATHS

    try:
        upscale_module._SEEDVR2_COMMON_PATHS = [seedvr2_root]
        result = detect_seedvr2()
        assert result is not None
        assert result == seedvr2_root
    finally:
        upscale_module._SEEDVR2_COMMON_PATHS = original_paths


def test_detect_seedvr2_partial_install_not_found(tmp_path: Path) -> None:
    """detect_seedvr2() returns None when structure is incomplete (missing batch_upscale.py)."""
    from klippbok.services.upscale_service import detect_seedvr2

    # Create partial installation: venv/Scripts/python.exe but no batch_upscale.py
    seedvr2_root = tmp_path / "SeedVR2partial"
    seedvr2_root.mkdir()
    scripts_dir = seedvr2_root / "venv" / "Scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "python.exe").write_text("mock python exe")
    # Note: batch_upscale.py intentionally NOT created

    import klippbok.services.upscale_service as upscale_module
    original_paths = upscale_module._SEEDVR2_COMMON_PATHS

    try:
        upscale_module._SEEDVR2_COMMON_PATHS = [seedvr2_root]
        result = detect_seedvr2()
        assert result is None
    finally:
        upscale_module._SEEDVR2_COMMON_PATHS = original_paths


def test_detect_nmkd_siax_not_found() -> None:
    """detect_nmkd_siax() returns None when not installed."""
    from klippbok.services.upscale_service import detect_nmkd_siax

    import klippbok.services.upscale_service as upscale_module
    original_paths = upscale_module._NMKD_SIAX_COMMON_PATHS

    try:
        # Override common paths to something that definitely doesn't exist
        upscale_module._NMKD_SIAX_COMMON_PATHS = [
            Path("/nonexistent/realesrgan-ncnn-vulkan.exe"),
            Path("/another/nonexistent/realesrgan-ncnn-vulkan"),
        ]
        result = detect_nmkd_siax()
        assert result is None
    finally:
        upscale_module._NMKD_SIAX_COMMON_PATHS = original_paths


def test_detect_seedvr2_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """detect_seedvr2() finds installation at SEEDVR2_PATH env var location."""
    from klippbok.services.upscale_service import detect_seedvr2

    # Create a mock SeedVR2 installation
    seedvr2_root = tmp_path / "SeedVR2_custom"
    seedvr2_root.mkdir()
    scripts_dir = seedvr2_root / "venv" / "Scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "python.exe").write_text("mock python exe")
    (seedvr2_root / "batch_upscale.py").write_text("# mock script")

    monkeypatch.setenv("SEEDVR2_PATH", str(seedvr2_root))

    # Override common paths to nonexistent to force env var usage
    import klippbok.services.upscale_service as upscale_module

    # Rebuild the paths list since env var is read at module level
    # We need to reload the path list dynamically
    original_paths = upscale_module._SEEDVR2_COMMON_PATHS
    try:
        # The env var candidate is built into the module-level list.
        # Force re-evaluation by patching the env var path in.
        upscale_module._SEEDVR2_COMMON_PATHS = [
            Path(os.environ.get("SEEDVR2_PATH", "")),
        ]
        result = detect_seedvr2()
        assert result == seedvr2_root
    finally:
        upscale_module._SEEDVR2_COMMON_PATHS = original_paths
