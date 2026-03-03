---
phase: 05-interactive-crop-editor
plan: 02
subsystem: api
tags: [pillow, mediapipe, fastapi, sse, subprocess, crop, upscale]

# Dependency graph
requires:
  - phase: 04-web-gui-foundation
    provides: FastAPI app factory, SSE import pattern, models.py, project_service.load_manifest
  - phase: 03-image-import-quality
    provides: assign_to_bucket, needs_upscale, bucket.py
  - phase: 02-model-configuration
    provides: generate_buckets, ModelProfile, BucketConfig
provides:
  - apply_crop() Pillow-based crop+rotate+flip+resize at exact bucket dimensions
  - apply_crops_batch() batch crop application with per-image success/error results
  - auto_crop_image() MediaPipe PoseLandmarker subject detection + center-crop fallback
  - _center_crop() and _fit_crop_to_bucket() pure-Python AR math helpers
  - detect_seedvr2() finds SeedVR2 at common paths or SEEDVR2_PATH env var
  - detect_nmkd_siax() finds realesrgan-ncnn-vulkan binary
  - start_upscale() Popen subprocess with threaded stdout reader and SSE queue
  - POST /api/v1/crop/ apply batch crops endpoint
  - POST /api/v1/crop/auto auto-crop subject detection endpoint
  - POST /api/v1/upscale/start start upscale operation endpoint
  - GET /api/v1/upscale/{op_id}/events SSE progress stream endpoint
  - GET /api/v1/upscale/status upscaler availability endpoint
  - CropApplyItem/Request/Result, AutoCropRequest/Result, UpscaleProgress API models
affects:
  - 05-03 (frontend crop page will call these endpoints)
  - 05-04 (auto-crop frontend uses POST /crop/auto)
  - 06-captioning (receives pre-cropped images from .klippbok/crops/)

# Tech tracking
tech-stack:
  added:
    - mediapipe>=0.10 (PoseLandmarker for pose detection, new [crop] optional dep group)
  patterns:
    - CPU-bound crop work in run_in_executor (Pillow is synchronous)
    - Threaded stdout reader + asyncio.run_coroutine_threadsafe for subprocess progress
    - Module-level _SEEDVR2_COMMON_PATHS and _NMKD_SIAX_COMMON_PATHS lists (patchable in tests)
    - MediaPipe model path discovery: env var > vendored > user cache > download
    - Pure-Python AR math helpers (_center_crop, _fit_crop_to_bucket) importable without mediapipe

key-files:
  created:
    - klippbok/services/crop_service.py
    - klippbok/image/autocrop.py
    - klippbok/api/routers/crop.py
    - klippbok/api/routers/upscale.py
    - klippbok/services/upscale_service.py
    - tests/test_crop_service.py
    - tests/test_image_autocrop.py
    - tests/test_upscale_service.py
  modified:
    - klippbok/api/models.py (added crop+upscale models)
    - klippbok/api/app.py (registered crop+upscale routers, updated lifespan)
    - pyproject.toml (added [crop] optional dep group, updated [gui] and [all])

key-decisions:
  - "MediaPipe 0.10.x has no mp.solutions API (removed). Used Tasks API (PoseLandmarker) with model path discovery: env var > vendored > user cache > download"
  - "auto_crop_image tests split: pure-math helpers (_center_crop, _fit_crop_to_bucket) tested without mediapipe; full pose tests skip if model not available"
  - "Module-level path lists (_SEEDVR2_COMMON_PATHS, _NMKD_SIAX_COMMON_PATHS) are patchable in tests - same pattern as ffmpeg detection"
  - "Lifespan updated to cancel both import AND upscale tasks on shutdown"
  - "crop router reuses images router _image_id() SHA256[:16] pattern for manifest lookups"

patterns-established:
  - "Pattern: Pure-Python math helpers in autocrop.py importable without optional deps - keeps testing easy"
  - "Pattern: Patchable module-level path lists for detection functions (same as video ffmpeg pattern)"
  - "Pattern: Subprocess upscale uses threading.Thread + asyncio.run_coroutine_threadsafe for non-blocking progress"

requirements-completed: [CROP-07, CROP-08]

# Metrics
duration: 10min
completed: 2026-03-03
---

# Phase 5 Plan 02: Backend Services for Crop and Upscale Summary

**Pillow crop service, MediaPipe auto-crop (Tasks API), SeedVR2/NMKD-Siax subprocess upscaler, and FastAPI endpoints for POST /crop/, POST /crop/auto, POST /upscale/start, GET /upscale/{op_id}/events**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-03-03T18:45:09Z
- **Completed:** 2026-03-03T18:55:00Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments

- Pillow-based `apply_crop()` applies rotation (ROTATE_90/180/270 via Transpose), flip (H/V), crop, and LANCZOS resize to exact bucket dimensions; handles RGBA/CMYK to RGB conversion
- MediaPipe PoseLandmarker `auto_crop_image()` detects pose landmarks, derives padded bbox, maps to nearest bucket AR, falls back to centered `_center_crop()` for non-person images
- SeedVR2/NMKD-Siax subprocess launcher with threaded stdout parsing (flexible `(\d+)/(\d+)` regex), SSE progress queue, error handling for missing installers
- All 5 new API endpoints registered and verified: POST /crop/, POST /crop/auto, POST /upscale/start, GET /upscale/{op_id}/events, GET /upscale/status

## Task Commits

Each task was committed atomically:

1. **Task 1: Crop service, auto-crop module, and tests** - `4e73dc1` (feat)
2. **Task 2: Upscale service, API routers, and router registration** - `a867669` (feat)

**Plan metadata:** _(created as part of this summary)_

_Note: TDD tasks had test→feat structure. Both tasks in single commits due to tightly coupled test+implementation._

## Files Created/Modified

- `klippbok/services/crop_service.py` - apply_crop() and apply_crops_batch() (Pillow)
- `klippbok/image/autocrop.py` - auto_crop_image(), _center_crop(), _fit_crop_to_bucket() (MediaPipe Tasks API)
- `klippbok/services/upscale_service.py` - detect_seedvr2(), detect_nmkd_siax(), start_upscale()
- `klippbok/api/routers/crop.py` - POST /crop/ and POST /crop/auto endpoints
- `klippbok/api/routers/upscale.py` - POST /upscale/start, GET /upscale/{op_id}/events, GET /upscale/status
- `klippbok/api/models.py` - CropApplyItem/Request/Result, AutoCropRequest/Result, UpscaleProgress, UpscaleRequest
- `klippbok/api/app.py` - Registered crop+upscale routers; lifespan now cancels both import and upscale tasks
- `pyproject.toml` - Added [crop] dep group with mediapipe>=0.10; [gui] and [all] include [crop]
- `tests/test_crop_service.py` - 4 tests: dimensions, rotation 90, flip_h pixel comparison, RGBA->RGB
- `tests/test_image_autocrop.py` - 8 tests: _center_crop math (no mediapipe needed), _fit_crop_to_bucket clamping, auto_crop_image (model-gated skips)
- `tests/test_upscale_service.py` - 5 tests: detect_seedvr2 found/not-found/partial, detect_nmkd_siax, env var override

## Decisions Made

- **MediaPipe 0.10.x**: No `mp.solutions` (removed). Used new Tasks API `PoseLandmarker` with model path discovery chain: `MEDIAPIPE_POSE_MODEL` env var → vendored `models/pose_landmarker_full.task` → `~/.klippbok/models/` → download on first use.
- **Test strategy for autocrop**: Separated pure-Python math helpers from MediaPipe code. Tests for `_center_crop` and `_fit_crop_to_bucket` run without mediapipe installed. Full `auto_crop_image` tests skip unless model file is available (avoids requiring network in CI).
- **Module-level patchable paths**: `_SEEDVR2_COMMON_PATHS` and `_NMKD_SIAX_COMMON_PATHS` are module-level lists overrideable in tests (same pattern as `_ffmpeg.py` detection approach).
- **Lifespan extended**: App shutdown now cancels both import _tasks and upscale _tasks to prevent resource leaks.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] MediaPipe legacy API removed in 0.10.x**
- **Found during:** Task 1 (autocrop module GREEN phase)
- **Issue:** Plan specified `mp.solutions.pose` legacy API (bundles model). Installed mediapipe 0.10.32 has only `mp.tasks` (Tasks API). `AttributeError: module 'mediapipe' has no attribute 'solutions'`
- **Fix:** Rewrote `autocrop.py` to use `PoseLandmarker` (Tasks API) with model path discovery chain and fallback download. Split `_center_crop` and `_fit_crop_to_bucket` as pure-Python helpers (no mediapipe required at import time).
- **Files modified:** `klippbok/image/autocrop.py`, `tests/test_image_autocrop.py`
- **Verification:** All 8 autocrop tests pass; 2 model-gated tests correctly skip when model not downloaded
- **Committed in:** `4e73dc1` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - API compatibility bug)
**Impact on plan:** Fixed transparently. Public interface `auto_crop_image()` unchanged. Test coverage equal or better (pure-Python math tested independently). Model download deferred to first use.

## Issues Encountered

- MediaPipe 0.10.x dropped the legacy `mp.solutions` API entirely. The new Tasks API requires a `.task` model file on disk. This was handled cleanly with a model discovery + download chain.

## User Setup Required

None required for basic crop service and upscale detection. Optional: to use auto-crop without network access, download the pose model manually:

```bash
# Download ~5MB pose model to user cache (happens automatically on first use otherwise)
python -c "
from klippbok.image.autocrop import _download_model, _POSE_MODEL_FILENAME
from pathlib import Path
_download_model(Path.home() / '.klippbok' / 'models' / _POSE_MODEL_FILENAME)
"
```

Or set `MEDIAPIPE_POSE_MODEL=/path/to/pose_landmarker_full.task` environment variable.

## Next Phase Readiness

- Backend is complete: crop, auto-crop, and upscale endpoints all registered and verified
- Frontend crop page (Plan 03) can call POST /api/v1/crop/ to save crops
- Frontend auto-crop button (Plan 03/04) can call POST /api/v1/crop/auto for suggested crop coords
- Upscale wizard (Plan 03) can use POST /api/v1/upscale/start + SSE events pattern
- Test suite at 1150 passed, 6 skipped (0 failures)

---
*Phase: 05-interactive-crop-editor*
*Completed: 2026-03-03*
