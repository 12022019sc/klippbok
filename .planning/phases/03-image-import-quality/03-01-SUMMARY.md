---
phase: 03-image-import-quality
plan: 01
subsystem: image
tags: [pydantic, pillow, tiff, image-import, models, validation]

# Dependency graph
requires:
  - phase: 01-architecture-foundation
    provides: IssueCode enum in video/models.py (single source of truth for all validation codes)
  - phase: 01-architecture-foundation
    provides: ImageMetadata, ImageValidation, probe_image, validate_image, discover_images in klippbok.image

provides:
  - TIFF format support (.tif/.tiff) in SUPPORTED_IMAGE_FORMATS/EXTENSIONS constants
  - n_frames field on ImageMetadata for multi-page TIFF detection
  - Five new IssueCode values: IMAGE_UPSCALE_REQUIRED, IMAGE_BLUR_DETECTED, IMAGE_NEAR_DUPLICATE, IMAGE_EXTREME_ASPECT, IMAGE_TIFF_MULTIPAGE
  - ImageImportEntry frozen Pydantic model: per-image result with metadata, validation, bucket, phash, blur_score, duplicate status
  - ImageImportReport frozen Pydantic model: batch import summary with counts and bucket_distribution property
  - CMYK color mode warning in validate_image (reuses IMAGE_RGBA_CONVERSION code)
  - IMAGE_TIFF_MULTIPAGE warning for n_frames > 1 in validate_image
  - imagehash>=4.3 and scipy>=1.9 in [image] optional dependency group

affects:
  - 03-02 (bucket assignment): uses ImageImportEntry.bucket field
  - 03-03 (quality checks): uses ImageImportEntry.blur_score, phash, is_near_duplicate, IMAGE_BLUR_DETECTED, IMAGE_NEAR_DUPLICATE
  - 03-04 (service orchestration): uses ImageImportReport as output structure

# Tech tracking
tech-stack:
  added:
    - imagehash>=4.3 (in pyproject.toml [image] extras, not yet installed)
    - scipy>=1.9 (in pyproject.toml [image] extras, not yet installed)
  patterns:
    - TDD (RED-GREEN) cycle for all new code
    - Frozen Pydantic v2 models for all data flow objects
    - Accumulative validation (all checks run, no fail-fast)
    - Reuse existing IssueCode values for related warnings (CMYK reuses IMAGE_RGBA_CONVERSION)

key-files:
  created:
    - (no new files - all extensions to existing modules)
  modified:
    - klippbok/video/models.py - Five new IMAGE_* IssueCode enum values
    - klippbok/image/models.py - TIFF in constants, n_frames on ImageMetadata, ImageImportEntry, ImageImportReport
    - klippbok/image/probe.py - n_frames extraction via getattr(img, 'n_frames', 1)
    - klippbok/image/validate.py - CMYK warning (check 5) and IMAGE_TIFF_MULTIPAGE warning (check 6)
    - klippbok/image/__init__.py - Export ImageImportEntry and ImageImportReport
    - pyproject.toml - imagehash and scipy in [image] extras
    - tests/test_image_models.py - Phase 3 test classes for constants, IssueCodes, ImportEntry, ImportReport
    - tests/test_image_probe.py - TIFF probe tests (single, multi-page, CMYK, .tif extension)
    - tests/test_image_validate.py - TIFF validation tests (format accepted, CMYK warning, multipage warning)
    - tests/test_image_discover.py - Updated test_returns_only_images to include tiff as supported

key-decisions:
  - "CMYK warning reuses IMAGE_RGBA_CONVERSION code -- both represent color mode conversion needs"
  - "n_frames field added to ImageMetadata (not a separate parameter) -- keeps validation pure-logic, no Pillow needed in validate"
  - "imagehash and scipy added to pyproject.toml extras but not installed yet -- dependency declaration only"

patterns-established:
  - "ImageImportEntry: single source of truth for per-image pipeline results flowing to Phase 3 plans"
  - "ImageImportReport: batch summary pattern with computed bucket_distribution property"
  - "n_frames=getattr(img, 'n_frames', 1): safe Pillow multi-frame extraction pattern"

# Metrics
duration: 4min
completed: 2026-02-28
---

# Phase 3 Plan 01: Image Foundation Models and TIFF Support Summary

**TIFF format support (.tif/.tiff) with multi-page/CMYK detection, five new Phase 3 IssueCode values, and ImageImportEntry/ImageImportReport frozen Pydantic models forming the Phase 3 pipeline foundation**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-28T05:08:27Z
- **Completed:** 2026-02-28T05:12:44Z
- **Tasks:** 2 (TDD: 2 RED commits + 2 GREEN commits)
- **Files modified:** 10

## Accomplishments

- Extended SUPPORTED_IMAGE_FORMATS/EXTENSIONS constants to include TIFF (format name "tiff", extensions .tif/.tiff), making discover_images() automatically find TIFF files with no code changes to discover.py
- Added five new IssueCode values to video/models.py for Phase 3 quality pipeline: IMAGE_UPSCALE_REQUIRED, IMAGE_BLUR_DETECTED, IMAGE_NEAR_DUPLICATE, IMAGE_EXTREME_ASPECT, IMAGE_TIFF_MULTIPAGE
- Created ImageImportEntry (per-image pipeline result) and ImageImportReport (batch summary with bucket_distribution) frozen Pydantic models -- the output contract for all Phase 3 plans
- Updated probe_image to extract n_frames from Pillow images; added CMYK and multi-page TIFF warnings to validate_image

## Task Commits

Each task was committed atomically:

1. **Task 1: TIFF support, IssueCodes, import models** - `3fc40c9` (feat)
2. **Task 2: TIFF-aware probing and validation** - `08db59f` (feat)

**Plan metadata:** (pending docs commit)

_Note: TDD tasks -- RED phase failures confirmed before each GREEN phase implementation_

## Files Created/Modified

- `klippbok/video/models.py` - Five new IMAGE_* IssueCode enum values (IMAGE_UPSCALE_REQUIRED, IMAGE_BLUR_DETECTED, IMAGE_NEAR_DUPLICATE, IMAGE_EXTREME_ASPECT, IMAGE_TIFF_MULTIPAGE)
- `klippbok/image/models.py` - Extended SUPPORTED_* constants for TIFF, n_frames field on ImageMetadata, new ImageImportEntry and ImageImportReport classes
- `klippbok/image/probe.py` - n_frames extraction: `getattr(img, 'n_frames', 1)` after Image.open()
- `klippbok/image/validate.py` - CMYK color mode warning (check 5), IMAGE_TIFF_MULTIPAGE warning (check 6)
- `klippbok/image/__init__.py` - Export ImageImportEntry and ImageImportReport in imports and __all__
- `pyproject.toml` - imagehash>=4.3 and scipy>=1.9 added to [image] optional extras
- `tests/test_image_models.py` - Added TestTiffFormatConstants, TestPhase3IssueCodes, TestImageImportEntry, TestImageImportReport classes
- `tests/test_image_probe.py` - Added TestProbeImageTiff: single-page, multi-page (n_frames=3), CMYK, .tif extension tests
- `tests/test_image_validate.py` - Added TestValidateImageTiff: format accepted, CMYK warning, multipage warning tests
- `tests/test_image_discover.py` - Updated test_returns_only_images to reflect .tiff as now-supported extension

## Decisions Made

- **CMYK warning reuses IMAGE_RGBA_CONVERSION code** -- CMYK is a color conversion scenario like RGBA. Creating a dedicated IMAGE_CMYK_CONVERSION code would duplicate semantics. Reuse keeps the enum focused.
- **n_frames on ImageMetadata, not validate_image parameter** -- validate_image is designed as pure logic taking only ImageMetadata. Adding n_frames as a separate parameter would break the interface contract. The field belongs on the metadata object.
- **imagehash and scipy declared in pyproject.toml but not installed** -- These are needed for Phase 3 plan 3 (dedup/quality checks). Declaring now prevents future plan from having to touch pyproject.toml unnecessarily.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_returns_only_images in test_image_discover.py**

- **Found during:** Task 2 (full test suite run after GREEN phase)
- **Issue:** The existing test created a `.tiff` file and expected only 1 result (just .png), asserting that .tiff was NOT a supported extension. This was correct pre-Task 1, but after extending SUPPORTED_IMAGE_EXTENSIONS to include .tiff, the test was now testing stale behavior that contradicts the plan's intent.
- **Fix:** Updated the test to assert 2 results (both .png and .tiff), explicitly asserting that both are included and that .bmp/.gif are excluded.
- **Files modified:** tests/test_image_discover.py
- **Verification:** Full test suite passes (1087 passed, 4 skipped)
- **Committed in:** 08db59f (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Test was testing pre-TIFF behavior that the plan explicitly changes. Fix is correct -- the test now verifies the intended behavior.

## Issues Encountered

None -- both TDD cycles went as expected. RED phases failed precisely on the missing functionality, GREEN phases implemented cleanly.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- ImageImportEntry and ImageImportReport are ready for 03-02 (bucket assignment), which will populate the `bucket` field
- Five new IssueCode values are ready for 03-03 (quality checks) and 03-04 (dedup)
- TIFF discovery, probing, and validation are fully integrated into the existing pipeline
- imagehash and scipy are declared in pyproject.toml; 03-03 will need to run `pip install klippbok[image]` to actually install them

---
*Phase: 03-image-import-quality*
*Completed: 2026-02-28*
