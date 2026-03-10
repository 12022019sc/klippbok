---
phase: 08-export-pipeline
plan: "02"
subsystem: onetrainer-integration
tags: [python, subprocess, gpu, training, service]
dependency_graph:
  requires: []
  provides:
    - klippbok/services/onetrainer_service.py
    - klippbok/services/gpu_service.py
  affects:
    - future export router (08-03+) — will call detect_onetrainer, launch_onetrainer_headless
tech_stack:
  added: []
  patterns:
    - module-level _ot_procs dict for subprocess tracking (mirrors _procs in upscale_service.py)
    - daemon thread stdout reader with asyncio.Queue event bus
    - loop.call_soon_threadsafe for thread-to-async bridge
    - patchable module-level list (_ONETRAINER_COMMON_PATHS) for test isolation
    - nvidia-smi subprocess with timeout and fallback path
key_files:
  created:
    - klippbok/services/onetrainer_service.py
    - klippbok/services/gpu_service.py
    - tests/test_onetrainer_service.py
  modified: []
decisions:
  - "[08-02 OT-01]: _ONETRAINER_COMMON_PATHS patched via monkeypatch in tests to prevent real installation hits during test runs"
  - "[08-02 OT-02]: detect_onetrainer validates both venv/Scripts/python.exe and scripts/train.py — both required for a functional headless install"
  - "[08-02 OT-03]: launch_onetrainer_gui uses Popen with close_fds=True for detached process — no tracking, no stdout capture"
  - "[08-02 GPU-01]: VRAM_BUSY_THRESHOLD_MB = 4096 (4GB) — well above idle noise (~500MB) and below minimum LoRA training footprint (~8GB) on RTX 5080"
  - "[08-02 GPU-02]: nvidia-smi fallback to C:\\Windows\\System32\\nvidia-smi.exe for Windows systems where it is not on PATH"
  - "[08-02 GPU-03]: is_gpu_busy returns False (assume OK) when VRAM cannot be queried — fail-open for non-NVIDIA systems"
metrics:
  duration: "~4 minutes"
  completed: "2026-03-10"
  tasks_completed: 2
  files_created: 3
  tests_added: 37
---

# Phase 8 Plan 02: OneTrainer Integration Service Summary

**One-liner:** OneTrainer subprocess launch + progress parsing + GPU VRAM monitoring via nvidia-smi with graceful fallbacks.

## What Was Built

### `klippbok/services/onetrainer_service.py`

Provides detection, subprocess launch, progress parsing, and graceful stop for OneTrainer — the external LoRA training tool. Mirrors the subprocess management pattern from `upscale_service.py`.

**Exports:**
- `detect_onetrainer(configured_path)` — checks configured path first, then `_ONETRAINER_COMMON_PATHS`; validates `venv/Scripts/python.exe` and `scripts/train.py`
- `launch_onetrainer_headless(ot_root, preset_path, queue, op_id)` — spawns `train.py` with OT venv Python, starts daemon stdout reader thread, stores proc in `_ot_procs`
- `launch_onetrainer_gui(ot_root, preset_path)` — detached Popen with `train_ui.py`, no tracking
- `stop_onetrainer(op_id)` — SIGTERM to process, returns bool
- `is_training_active()` — checks any `_ot_procs` entry has `poll() is None`
- `parse_training_output(line)` — strips ANSI codes, regex for `Epoch N/M` pattern
- Error pattern constants: `OOM_PATTERNS`, `FILE_NOT_FOUND_PATTERNS`, `CUDA_ERROR_PATTERNS`

### `klippbok/services/gpu_service.py`

Queries GPU VRAM usage via nvidia-smi to detect whether training is already running.

**Exports:**
- `VRAM_BUSY_THRESHOLD_MB = 4096` — 4GB threshold (safe signal for RTX 5080 16GB)
- `get_gpu_vram_used_mb()` — runs nvidia-smi with timeout=5s, falls back to full Windows path
- `is_gpu_busy(threshold_mb)` — returns False if VRAM unavailable (fail-open)

### `tests/test_onetrainer_service.py`

37 tests covering detection, progress parsing, error pattern matching, process management, and GPU service VRAM logic.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test isolation: real OneTrainer installation hit by detection tests**
- **Found during:** Task 1 GREEN phase
- **Issue:** Tests `test_returns_none_when_python_missing` and `test_returns_none_when_train_missing` passed `configured_path` pointing to fake dirs but did not patch `_ONETRAINER_COMMON_PATHS` — the detection fell through to real install at `C:\GenAI\Data\Packages\OneTrainer`
- **Fix:** Updated 3 tests to also `monkeypatch.setattr(onetrainer_service, "_ONETRAINER_COMMON_PATHS", [])` so only the configured path is checked
- **Files modified:** `tests/test_onetrainer_service.py`
- **Commit:** 1730c7b (same commit as implementation)

## Self-Check: PASSED

- FOUND: `klippbok/services/onetrainer_service.py`
- FOUND: `klippbok/services/gpu_service.py`
- FOUND: `tests/test_onetrainer_service.py`
- FOUND: `.planning/phases/08-export-pipeline/08-02-SUMMARY.md`
- FOUND commit: `637cd38` — test(08-02): add failing tests
- FOUND commit: `1730c7b` — feat(08-02): implement services
