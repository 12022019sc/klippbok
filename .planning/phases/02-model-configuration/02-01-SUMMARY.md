---
phase: 02-model-configuration
plan: 01
subsystem: config
tags: [pydantic, model-profiles, bucket-generation, sd15, sdxl, flux, pony]

requires:
  - phase: 01-architecture-foundation
    provides: config module patterns (frozen Pydantic models, defaults.py constants)
provides:
  - ModelProfile frozen schema with caption_style and base_resolution validation
  - BucketConfig with power-of-2 step_size validation
  - TrainingHints with learning rate, rank, alpha defaults
  - generate_buckets pixel-budget algorithm (kohya-compatible)
  - Four built-in profiles (SD1.5, SDXL, Flux, Pony) with BUILTIN_PROFILES lookup
  - Public API re-exported from klippbok.config
affects: [02-model-configuration plan 02, 03-image-bucketing, 06-captioning, 08-export]

tech-stack:
  added: []
  patterns:
    - "Frozen Pydantic models for immutable config profiles"
    - "Pixel-budget bucket generation (kohya/sd-scripts compatible)"
    - "Module-level constants for built-in profiles"

key-files:
  created:
    - klippbok/config/model_profiles.py
    - klippbok/config/model_defaults.py
    - tests/test_model_profiles.py
    - tests/test_bucket_generation.py
  modified:
    - klippbok/config/__init__.py

key-decisions:
  - "max_aspect_ratio defaults to 2.0 (covers portrait/landscape up to 1:2)"
  - "step_size validated as power of 2 (aligns with VAE compression factors)"
  - "base_resolution validated as multiple of step_size at model level"

patterns-established:
  - "ModelProfile frozen schema: name, display_name, base_resolution, caption_style, bucket_config, training_hints"
  - "generate_buckets(base_resolution, step_size, min_dimension, max_dimension, max_aspect_ratio) -> list[tuple[int,int]]"

duration: 4min
completed: 2026-02-27
---

# Phase 2 Plan 1: Model Profile Schema Summary

**Frozen ModelProfile schema with kohya-compatible pixel-budget bucket generation and four built-in profiles (SD1.5/SDXL/Flux/Pony)**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-02-27T23:59:42Z
- **Completed:** 2026-02-28T00:03:24Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- ModelProfile frozen Pydantic v2 schema with caption_style, base_resolution alignment, and step_size power-of-2 validation
- Pixel-budget bucket generation algorithm producing kohya-compatible resolution pairs within pixel budget, step-aligned, aspect-ratio-constrained
- Four built-in profiles with correct values: SD1.5 (512/booru), SDXL (1024/NL), Flux (1024/NL/alpha=1.0), Pony (1024/booru)
- 28 TDD tests covering schema validation, bucket constraints, built-in profile values, and public API

## Task Commits

1. **Task 1: ModelProfile schema + generate_buckets** - `dab1e58` (feat)
2. **Task 2: Built-in profiles + config __init__.py** - `7ee7675` (feat)

## Files Created/Modified

- `klippbok/config/model_profiles.py` - ModelProfile, BucketConfig, TrainingHints schemas and generate_buckets function
- `klippbok/config/model_defaults.py` - SD15/SDXL/Flux/Pony profile constants and BUILTIN_PROFILES dict
- `klippbok/config/__init__.py` - Re-exports ModelProfile, BucketConfig, TrainingHints, generate_buckets, BUILTIN_PROFILES
- `tests/test_model_profiles.py` - 17 tests for schema validation and built-in profiles
- `tests/test_bucket_generation.py` - 11 tests for bucket generation algorithm

## Decisions Made

- max_aspect_ratio defaults to 2.0 (practical range for training, matches common trainer min=base/2, max=base*2)
- step_size validated as power of 2 to align with VAE spatial compression factors
- base_resolution validated as multiple of step_size via model_validator (catches misalignment at construction)
- BucketConfig defaults: step_size=64, min_dimension=256, max_dimension=1024 (SD1.5-oriented defaults)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Model profile schema ready for Plan 2 (per-project override system and custom profiles)
- generate_buckets ready for Phase 3 (image bucketing) to consume
- Built-in profiles ready for Phase 6 (captioning) to determine caption_style
- Full test suite passes (1028 tests, 0 regressions)

---
*Phase: 02-model-configuration*
*Completed: 2026-02-27*
