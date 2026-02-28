---
phase: 03-image-import-quality
plan: 02
subsystem: image
tags: [bucket-assignment, blur-detection, laplacian, scipy, numpy, pillow, tdd]

# Dependency graph
requires:
  - phase: 02-model-configuration
    provides: generate_buckets() for creating bucket lists used in testing
  - phase: 03-01
    provides: ImageMetadata, IssueCode enums for image domain models

provides:
  - assign_to_bucket: argmin aspect ratio matching to nearest training bucket
  - needs_upscale: detects when image is smaller than its assigned bucket
  - compute_blur_score: Laplacian variance (numpy+scipy, no OpenCV)
  - is_blurry: fixed 100.0 threshold blur classification
  - BLUR_THRESHOLD constant exported from klippbok.image public API

affects:
  - 03-03 (near-duplicate detection / image import pipeline consumes these functions)
  - Phase 5 (crop UI -- bucket assignment drives aspect ratio snapping)

# Tech tracking
tech-stack:
  added:
    - scipy>=1.9 (installed for convolve2d Laplacian convolution)
  patterns:
    - Pure function modules (no side effects, no file I/O) for easy composition
    - TDD RED-GREEN cycle: failing import error -> implementation -> all pass
    - Fixed threshold as named constant (BLUR_THRESHOLD = 100.0, not a parameter)

key-files:
  created:
    - klippbok/image/bucket.py
    - klippbok/image/quality.py
    - tests/test_image_bucket.py
    - tests/test_image_blur.py
  modified:
    - klippbok/image/__init__.py

key-decisions:
  - "assign_to_bucket takes bucket list as input (not model profile) -- pure function, caller provides context"
  - "SD1.5 pixel budget (512^2=262144) does not include 768x512 -- test corrected to use 640x384"
  - "scipy installed from pyproject.toml [image] extras (was declared in 03-01, installed in 03-02)"
  - "Blur quality is advisory only -- is_blurry returns bool, never blocks import pipeline"
  - "Test file named test_image_blur.py (not test_image_quality.py) to avoid conflict with existing video domain test"

patterns-established:
  - "image domain modules are pure functions: input in, result out, no class state"
  - "BLUR_THRESHOLD as module-level constant (not param) enforces fixed threshold semantics"

# Metrics
duration: 3min
completed: 2026-02-28
---

# Phase 3 Plan 02: Bucket Assignment and Blur Detection Summary

**Nearest-bucket assignment via argmin aspect ratio (NovelAI/kohya algorithm) and Laplacian variance blur detection using numpy+scipy -- both as pure functions composable into the import pipeline.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-02-28T05:22:37Z
- **Completed:** 2026-02-28T05:25:57Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- `assign_to_bucket` selects the closest bucket from `generate_buckets()` output using argmin aspect ratio delta; returns None for extreme ARs or empty bucket list
- `needs_upscale` flags images where either dimension is smaller than the assigned bucket (True = upscale would be needed)
- `compute_blur_score` applies a 3x3 Laplacian kernel via `scipy.signal.convolve2d` and returns the variance as a float; higher = sharper
- `is_blurry` wraps compute_blur_score with fixed threshold 100.0; advisory only, never blocks import
- All five symbols exported from `klippbok.image` public API
- 22 tests across both modules pass; 1109 total tests pass with 4 skipped, zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Bucket assignment and upscale detection** - `d5366d5` (feat)
2. **Task 2: Blur detection and __init__ exports** - `17c0c48` (feat)

**Plan metadata:** (docs commit follows)

_Note: Both tasks followed TDD RED-GREEN cycle (import error = RED confirmed, implementation = GREEN)._

## Files Created/Modified

- `klippbok/image/bucket.py` - assign_to_bucket (argmin AR delta), needs_upscale
- `klippbok/image/quality.py` - compute_blur_score (scipy Laplacian), is_blurry, BLUR_THRESHOLD
- `klippbok/image/__init__.py` - exports assign_to_bucket, needs_upscale, compute_blur_score, is_blurry, BLUR_THRESHOLD
- `tests/test_image_bucket.py` - 12 tests (SD1.5/SDXL fixtures, edge cases, upscale detection)
- `tests/test_image_blur.py` - 10 tests (solid/checkerboard images, grayscale/RGBA/small)

## Decisions Made

- **assign_to_bucket takes bucket list, not model profile** -- keeps it a pure function; caller provides the bucket list from `generate_buckets()`. No coupling to profile loading.
- **scipy installed here** -- was declared in pyproject.toml `[image]` extras in 03-01 but not installed. Installed now for blur detection.
- **BLUR_THRESHOLD is a constant, not a parameter** -- per project decision that quality checks use fixed thresholds, not user-adjustable values.
- **Test file named `test_image_blur.py`** -- `test_image_quality.py` already exists for `klippbok.video.image_quality` (OpenCV-based video frame quality). Used distinct name to avoid collision.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected test_exact_bucket_match expected bucket**

- **Found during:** Task 1 (GREEN phase test run)
- **Issue:** Plan specified `768x512` as the "exact bucket match" test case, but SD1.5 (512^2=262,144 pixel budget) does not include (768, 512) because 768*512=393,216 exceeds the budget. Test failed with actual bucket (640, 384).
- **Fix:** Updated test to use (640, 384) which is the widest bucket in the SD1.5 set, with a precondition assertion to document why.
- **Files modified:** tests/test_image_bucket.py
- **Verification:** Test passes; checked generate_buckets(512) output to confirm (640, 384) is valid.
- **Committed in:** d5366d5 (Task 1 commit)

**2. [Rule 3 - Blocking] Installed scipy (declared extra, not yet installed)**

- **Found during:** Task 2 setup (scipy import fails)
- **Issue:** scipy>=1.9 was declared in pyproject.toml [image] extras in 03-01 but not installed in the environment. `from scipy.signal import convolve2d` would fail at test collection.
- **Fix:** Ran `pip install "scipy>=1.9"` to install scipy 1.17.1.
- **Verification:** `python -c "import scipy"` succeeds; all blur tests pass.
- **Committed in:** 17c0c48 (Task 2 commit, scipy not committed -- env-only change)

---

**Total deviations:** 2 auto-fixed (1 bug in test expectation, 1 blocking missing dependency)
**Impact on plan:** Both necessary -- test fix ensures correct assertions, scipy install enables blur detection. No scope creep.

## Issues Encountered

None beyond the deviations documented above.

## User Setup Required

None - no external service configuration required. scipy is pip-installable; no API keys or dashboards needed.

## Next Phase Readiness

- Bucket assignment and blur detection are ready for consumption by the import pipeline (03-03)
- 03-03 will also need imagehash>=4.3 (also declared in pyproject.toml extras but not yet installed) for near-duplicate detection
- All image domain public API symbols are now exported from `klippbok.image`

---
*Phase: 03-image-import-quality*
*Completed: 2026-02-28*
