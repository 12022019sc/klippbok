"""Tests for OneTrainer integration service and GPU VRAM monitoring service.

Covers:
- detect_onetrainer: detection at configured path and common paths
- parse_training_output: epoch/step extraction from tqdm-style lines
- Error pattern detection: OOM, file-not-found, CUDA errors
- GPU service: nvidia-smi parsing and threshold logic
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── OneTrainer detection tests ─────────────────────────────────────────────


def _make_fake_ot_root(tmp_path: Path, has_python: bool = True, has_train: bool = True) -> Path:
    """Create a fake OneTrainer root with expected structure."""
    ot_root = tmp_path / "OneTrainer"
    if has_python:
        python_dir = ot_root / "venv" / "Scripts"
        python_dir.mkdir(parents=True)
        (python_dir / "python.exe").touch()
    if has_train:
        scripts_dir = ot_root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "train.py").touch()
    return ot_root


class TestDetectOnetrainer:
    def test_detects_valid_installation(self, tmp_path: Path, monkeypatch) -> None:
        """detect_onetrainer returns root when both python.exe and train.py exist."""
        from klippbok.services import onetrainer_service

        ot_root = _make_fake_ot_root(tmp_path)
        monkeypatch.setattr(onetrainer_service, "_ONETRAINER_COMMON_PATHS", [])
        result = onetrainer_service.detect_onetrainer(configured_path=str(ot_root))
        assert result == ot_root

    def test_returns_none_when_python_missing(self, tmp_path: Path, monkeypatch) -> None:
        """detect_onetrainer returns None when venv/Scripts/python.exe is absent."""
        from klippbok.services import onetrainer_service

        ot_root = _make_fake_ot_root(tmp_path, has_python=False, has_train=True)
        # Patch common paths to empty so only configured_path is checked
        monkeypatch.setattr(onetrainer_service, "_ONETRAINER_COMMON_PATHS", [])
        result = onetrainer_service.detect_onetrainer(configured_path=str(ot_root))
        assert result is None

    def test_returns_none_when_train_missing(self, tmp_path: Path, monkeypatch) -> None:
        """detect_onetrainer returns None when scripts/train.py is absent."""
        from klippbok.services import onetrainer_service

        ot_root = _make_fake_ot_root(tmp_path, has_python=True, has_train=False)
        # Patch common paths to empty so only configured_path is checked
        monkeypatch.setattr(onetrainer_service, "_ONETRAINER_COMMON_PATHS", [])
        result = onetrainer_service.detect_onetrainer(configured_path=str(ot_root))
        assert result is None

    def test_configured_path_checked_first(self, tmp_path: Path, monkeypatch) -> None:
        """Configured path takes priority over common paths."""
        from klippbok.services import onetrainer_service

        ot_root = _make_fake_ot_root(tmp_path)
        monkeypatch.setattr(onetrainer_service, "_ONETRAINER_COMMON_PATHS", [])
        result = onetrainer_service.detect_onetrainer(configured_path=str(ot_root))
        assert result == ot_root

    def test_falls_back_to_common_paths(self, tmp_path: Path, monkeypatch) -> None:
        """detect_onetrainer finds install via common paths when no configured path."""
        from klippbok.services import onetrainer_service

        ot_root = _make_fake_ot_root(tmp_path)
        monkeypatch.setattr(onetrainer_service, "_ONETRAINER_COMMON_PATHS", [ot_root])
        result = onetrainer_service.detect_onetrainer(configured_path=None)
        assert result == ot_root

    def test_returns_none_when_not_found_anywhere(self, tmp_path: Path, monkeypatch) -> None:
        """detect_onetrainer returns None when install not found at any path."""
        from klippbok.services import onetrainer_service

        monkeypatch.setattr(onetrainer_service, "_ONETRAINER_COMMON_PATHS", [tmp_path / "nonexistent"])
        result = onetrainer_service.detect_onetrainer(configured_path=None)
        assert result is None

    def test_returns_path_object(self, tmp_path: Path, monkeypatch) -> None:
        """detect_onetrainer always returns a Path (not str) on success."""
        from klippbok.services import onetrainer_service

        ot_root = _make_fake_ot_root(tmp_path)
        monkeypatch.setattr(onetrainer_service, "_ONETRAINER_COMMON_PATHS", [])
        result = onetrainer_service.detect_onetrainer(configured_path=str(ot_root))
        assert isinstance(result, Path)


# ── parse_training_output tests ────────────────────────────────────────────


class TestParseTrainingOutput:
    @pytest.mark.parametrize("line,expected", [
        # Standard tqdm epoch line
        ("Epoch 1/10: 100%|████████| 100/100 [00:30<00:00,  3.33it/s]", {"epoch": 1, "total_epochs": 10}),
        # Epoch with spaces
        ("Epoch 5/20:  50%|██      | 50/100 [00:15<00:15,  3.33it/s]", {"epoch": 5, "total_epochs": 20}),
        # Minimal epoch line
        ("Epoch 3/10", {"epoch": 3, "total_epochs": 10}),
        # Epoch with colon
        ("Epoch: 7/15", {"epoch": 7, "total_epochs": 15}),
    ])
    def test_extracts_epoch_progress(self, line: str, expected: dict) -> None:
        """parse_training_output extracts epoch/total_epochs from tqdm lines."""
        from klippbok.services.onetrainer_service import parse_training_output

        result = parse_training_output(line)
        assert result is not None
        assert result["epoch"] == expected["epoch"]
        assert result["total_epochs"] == expected["total_epochs"]

    @pytest.mark.parametrize("line", [
        "Loading model from checkpoint...",
        "Training started.",
        "  loss: 0.0123",
        "",
        "100/100 [00:30<00:00]",  # No "Epoch" keyword
    ])
    def test_returns_none_for_non_epoch_lines(self, line: str) -> None:
        """parse_training_output returns None for lines without epoch pattern."""
        from klippbok.services.onetrainer_service import parse_training_output

        result = parse_training_output(line)
        assert result is None

    def test_handles_ansi_escape_codes(self) -> None:
        """parse_training_output handles ANSI codes in tqdm output."""
        from klippbok.services.onetrainer_service import parse_training_output

        # Line with ANSI color codes (common in tqdm output)
        line = "\x1b[A\x1b[2KEpoch 2/5: 100%|████| 100/100 [00:10<00:00]"
        result = parse_training_output(line)
        assert result is not None
        assert result["epoch"] == 2
        assert result["total_epochs"] == 5


# ── Error pattern detection tests ──────────────────────────────────────────


class TestErrorPatterns:
    def test_oom_patterns_defined(self) -> None:
        """OOM_PATTERNS module constant is a non-empty list."""
        from klippbok.services.onetrainer_service import OOM_PATTERNS

        assert isinstance(OOM_PATTERNS, list)
        assert len(OOM_PATTERNS) > 0

    def test_oom_patterns_detect_cuda_oom(self) -> None:
        """OOM_PATTERNS match known CUDA out-of-memory messages."""
        from klippbok.services.onetrainer_service import OOM_PATTERNS

        oom_lines = [
            "torch.cuda.OutOfMemoryError: CUDA out of memory.",
            "RuntimeError: CUDA out of memory. Tried to allocate ...",
            "out of memory",
        ]
        for line in oom_lines:
            matched = any(pat in line for pat in OOM_PATTERNS)
            assert matched, f"OOM pattern not matched for: {line!r}"

    def test_file_not_found_patterns_defined(self) -> None:
        """FILE_NOT_FOUND_PATTERNS module constant is a non-empty list."""
        from klippbok.services.onetrainer_service import FILE_NOT_FOUND_PATTERNS

        assert isinstance(FILE_NOT_FOUND_PATTERNS, list)
        assert len(FILE_NOT_FOUND_PATTERNS) > 0

    def test_file_not_found_patterns_match(self) -> None:
        """FILE_NOT_FOUND_PATTERNS match missing file messages."""
        from klippbok.services.onetrainer_service import FILE_NOT_FOUND_PATTERNS

        lines = [
            "FileNotFoundError: No such file or directory: '/path/to/model.safetensors'",
            "No such file or directory",
        ]
        for line in lines:
            matched = any(pat in line for pat in FILE_NOT_FOUND_PATTERNS)
            assert matched, f"File-not-found pattern not matched for: {line!r}"

    def test_cuda_error_patterns_defined(self) -> None:
        """CUDA_ERROR_PATTERNS module constant is a non-empty list."""
        from klippbok.services.onetrainer_service import CUDA_ERROR_PATTERNS

        assert isinstance(CUDA_ERROR_PATTERNS, list)
        assert len(CUDA_ERROR_PATTERNS) > 0

    def test_cuda_error_patterns_match(self) -> None:
        """CUDA_ERROR_PATTERNS match CUDA initialization errors."""
        from klippbok.services.onetrainer_service import CUDA_ERROR_PATTERNS

        lines = [
            "CUDA error: device-side assert triggered",
            "CUDA initialization: No GPUs found",
        ]
        for line in lines:
            matched = any(pat in line for pat in CUDA_ERROR_PATTERNS)
            assert matched, f"CUDA error pattern not matched for: {line!r}"


# ── is_training_active and stop_onetrainer tests ───────────────────────────


class TestProcessManagement:
    def test_is_training_active_returns_false_when_no_procs(self, monkeypatch) -> None:
        """is_training_active returns False when _ot_procs is empty."""
        from klippbok.services import onetrainer_service

        monkeypatch.setattr(onetrainer_service, "_ot_procs", {})
        assert onetrainer_service.is_training_active() is False

    def test_is_training_active_returns_true_when_running(self, monkeypatch) -> None:
        """is_training_active returns True when a process is still running."""
        from klippbok.services import onetrainer_service

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # None = still running
        monkeypatch.setattr(onetrainer_service, "_ot_procs", {"op-1": mock_proc})
        assert onetrainer_service.is_training_active() is True

    def test_is_training_active_returns_false_when_proc_done(self, monkeypatch) -> None:
        """is_training_active returns False when all processes have exited."""
        from klippbok.services import onetrainer_service

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # 0 = exited successfully
        monkeypatch.setattr(onetrainer_service, "_ot_procs", {"op-1": mock_proc})
        assert onetrainer_service.is_training_active() is False

    def test_stop_onetrainer_terminates_and_returns_true(self, monkeypatch) -> None:
        """stop_onetrainer terminates a running process and returns True."""
        from klippbok.services import onetrainer_service

        mock_proc = MagicMock()
        monkeypatch.setattr(onetrainer_service, "_ot_procs", {"op-1": mock_proc})
        result = onetrainer_service.stop_onetrainer("op-1")
        assert result is True
        mock_proc.terminate.assert_called_once()

    def test_stop_onetrainer_returns_false_for_unknown_op(self, monkeypatch) -> None:
        """stop_onetrainer returns False when op_id not in _ot_procs."""
        from klippbok.services import onetrainer_service

        monkeypatch.setattr(onetrainer_service, "_ot_procs", {})
        result = onetrainer_service.stop_onetrainer("nonexistent-op")
        assert result is False


# ── GPU service tests ──────────────────────────────────────────────────────


class TestGpuService:
    def test_vram_busy_threshold_defined(self) -> None:
        """VRAM_BUSY_THRESHOLD_MB is defined and reasonable (> 1GB)."""
        from klippbok.services.gpu_service import VRAM_BUSY_THRESHOLD_MB

        assert isinstance(VRAM_BUSY_THRESHOLD_MB, int)
        assert VRAM_BUSY_THRESHOLD_MB > 1024  # At least 1GB

    def test_get_gpu_vram_used_mb_parses_output(self) -> None:
        """get_gpu_vram_used_mb parses nvidia-smi output correctly."""
        from klippbok.services.gpu_service import get_gpu_vram_used_mb

        mock_result = MagicMock()
        mock_result.stdout = "4096\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = get_gpu_vram_used_mb()
            assert result == 4096
            assert mock_run.called

    def test_get_gpu_vram_used_mb_returns_none_on_failure(self) -> None:
        """get_gpu_vram_used_mb returns None when nvidia-smi is not available."""
        from klippbok.services.gpu_service import get_gpu_vram_used_mb

        with patch("subprocess.run", side_effect=FileNotFoundError("nvidia-smi not found")):
            result = get_gpu_vram_used_mb()
            assert result is None

    def test_get_gpu_vram_used_mb_returns_none_on_non_integer(self) -> None:
        """get_gpu_vram_used_mb returns None when output cannot be parsed as int."""
        from klippbok.services.gpu_service import get_gpu_vram_used_mb

        mock_result = MagicMock()
        mock_result.stdout = "N/A\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = get_gpu_vram_used_mb()
            assert result is None

    def test_is_gpu_busy_returns_true_above_threshold(self) -> None:
        """is_gpu_busy returns True when VRAM usage exceeds threshold."""
        from klippbok.services.gpu_service import is_gpu_busy

        with patch("klippbok.services.gpu_service.get_gpu_vram_used_mb", return_value=8192):
            result = is_gpu_busy(threshold_mb=4096)
            assert result is True

    def test_is_gpu_busy_returns_false_below_threshold(self) -> None:
        """is_gpu_busy returns False when VRAM usage is below threshold."""
        from klippbok.services.gpu_service import is_gpu_busy

        with patch("klippbok.services.gpu_service.get_gpu_vram_used_mb", return_value=512):
            result = is_gpu_busy(threshold_mb=4096)
            assert result is False

    def test_is_gpu_busy_returns_false_when_vram_unavailable(self) -> None:
        """is_gpu_busy returns False (assume OK) when VRAM check fails."""
        from klippbok.services.gpu_service import is_gpu_busy

        with patch("klippbok.services.gpu_service.get_gpu_vram_used_mb", return_value=None):
            result = is_gpu_busy(threshold_mb=4096)
            assert result is False

    def test_is_gpu_busy_uses_default_threshold(self) -> None:
        """is_gpu_busy uses VRAM_BUSY_THRESHOLD_MB as default threshold."""
        from klippbok.services.gpu_service import VRAM_BUSY_THRESHOLD_MB, is_gpu_busy

        # Just above threshold
        with patch("klippbok.services.gpu_service.get_gpu_vram_used_mb", return_value=VRAM_BUSY_THRESHOLD_MB + 1):
            assert is_gpu_busy() is True

        # Just at threshold (not strictly greater)
        with patch("klippbok.services.gpu_service.get_gpu_vram_used_mb", return_value=VRAM_BUSY_THRESHOLD_MB):
            assert is_gpu_busy() is False

    def test_get_gpu_vram_used_mb_timeout(self) -> None:
        """get_gpu_vram_used_mb uses a timeout to avoid hanging."""
        from klippbok.services.gpu_service import get_gpu_vram_used_mb

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("nvidia-smi", 5)):
            result = get_gpu_vram_used_mb()
            assert result is None
