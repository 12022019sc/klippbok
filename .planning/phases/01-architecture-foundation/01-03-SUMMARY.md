---
phase: 01-architecture-foundation
plan: 03
subsystem: dataset-image-unified
tags: [sample-pair, discovery, image-service, dependency-groups, unified-model]
dependency-graph:
  requires: ["01-01", "01-02"]
  provides:
    - "Unified SamplePair with type discriminator (image/video)"
    - "Discovery with target_type parameter (video/image/mixed)"
    - "Image service (import_image, import_images, validate_image_file)"
    - "pyproject.toml [image] and [gui] dependency groups"
  affects: ["phase-02-model-config", "phase-03-bucketing", "phase-04-gui", "phase-05-crop"]
tech-stack:
  added: []
  patterns: ["type-discriminator-with-default", "target_type-parameter-pattern"]
key-files:
  created:
    - klippbok/services/image_service.py
    - tests/test_sample_pair_unified.py
    - tests/test_image_service.py
  modified:
    - klippbok/dataset/models.py
    - klippbok/dataset/discover.py
    - klippbok/services/__init__.py
    - pyproject.toml
    - tests/test_dataset_discover.py
decisions:
  - id: UNI-01
    title: Type discriminator defaults to "video"
    choice: "Literal['image', 'video'] with default 'video'"
    reason: "Zero breakage for all existing code that constructs SamplePair without specifying type"
  - id: UNI-02
    title: target_type parameter for discovery
    choice: "String parameter with values 'video', 'image', 'mixed'"
    reason: "Preserves backwards compatibility while enabling image-as-target and mixed workflows"
  - id: UNI-03
    title: SUPPORTED_IMAGE_EXTENSIONS import for target classification
    choice: "Conditional import from klippbok.image.models with fallback"
    reason: "Reuses the image module's extension set; gracefully degrades if image optional dep not installed"
metrics:
  duration: ~4min
  completed: 2026-02-27
---

# Phase 01 Plan 03: Unified SamplePair Summary

**Unified SamplePair with type discriminator, target_type discovery parameter, image service, and [image]/[gui] dependency groups**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-02-27T22:03:26Z
- **Completed:** 2026-02-27T22:07:47Z
- **Tasks:** 2/2
- **Files modified:** 9 (2 created, 5 modified, 2 new test files)

## Accomplishments

- Added `type: Literal["image", "video"]` discriminator to SamplePair with `"video"` default for full backwards compatibility
- Added `format` and `color_mode` optional fields for image-specific metadata
- Added `target_type` parameter to `_classify_extension`, `discover_files`, and `discover_dataset`
- Imported `SUPPORTED_IMAGE_EXTENSIONS` from image module for target classification with fallback
- Created `image_service.py` with `import_image`, `import_images`, `validate_image_file` stateless functions
- Added `[image]` dependency group (Pillow>=9.0) and `[gui]` placeholder to pyproject.toml
- Updated `[triage]` to depend on `[image]` instead of direct Pillow dependency
- 40 new tests (26 for unified model/discovery + 14 for image service)
- Full suite: 1000 passed, 4 skipped (pre-existing scene detection skips)

## Task Commits

1. **Task 1: Unify SamplePair and add target_type to discovery** - `fd55bd5` (feat)
2. **Task 2: Create image service and finalize dependency groups** - `c93b3e5` (feat)

## Files Created/Modified

- `klippbok/dataset/models.py` - Added type discriminator, format, color_mode fields to SamplePair
- `klippbok/dataset/discover.py` - Added target_type parameter to classification and discovery functions
- `klippbok/services/image_service.py` - New stateless image import and validation service
- `klippbok/services/__init__.py` - Added image_service to re-exports
- `pyproject.toml` - Added [image], [gui] groups; updated [triage], [all], [dev]
- `tests/test_sample_pair_unified.py` - 26 tests for unified SamplePair model
- `tests/test_dataset_discover.py` - Added 13 tests for target_type discovery
- `tests/test_image_service.py` - 14 tests for image service functions

## Decisions Made

| ID | Decision | Choice | Reason |
|----|----------|--------|--------|
| UNI-01 | Type discriminator default | `"video"` default | Zero breakage for existing code |
| UNI-02 | Discovery target_type | String param with video/image/mixed | Backwards compatible while enabling new workflows |
| UNI-03 | Image extensions source | Import from klippbok.image.models with fallback | Reuses single source of truth; graceful degradation |

## Deviations from Plan

None -- plan executed exactly as written.

## Verification Results

- `pytest` full suite: 1000 passed, 4 skipped
- SamplePair default type is "video" -- verified
- SamplePair image type creation -- verified
- `from klippbok.services import image_service` -- clean import
- pyproject.toml valid with [image] and [gui] groups -- verified
- `python -m klippbok.dataset --help` still shows validate and organize commands (ARCH-07)

## Next Phase Readiness

- Unified SamplePair ready for mixed image+video dataset workflows
- Image service ready for CLI and GUI consumption
- [image] dependency group enables `pip install klippbok[image]`
- [gui] placeholder ready for Phase 4 dependencies
- No blockers for Phase 2 (model config) or Phase 3 (bucketing)

---
*Phase: 01-architecture-foundation*
*Completed: 2026-02-27*
