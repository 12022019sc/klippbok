# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-27)

**Core value:** Take raw images/video of any size and produce correctly bucketed, captioned, training-ready datasets for any supported diffusion model through an intuitive web interface.
**Current focus:** Phase 3 - Image Import and Quality

## Current Position

Phase: 3 of 8 (Image Import and Quality)
Plan: 0 of 3 in current phase
Status: Ready to plan
Last activity: 2026-02-28 -- Phase 2 complete (2/2 plans, verified)

Progress: [█████░░░░░] ~33% (5 of ~15 estimated plans)

## Performance Metrics

**Velocity:**
- Total plans completed: 5
- Average duration: ~4min
- Total execution time: ~19min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-architecture-foundation | 3 | ~12min | ~4min |
| 02-model-configuration | 2 | ~7min | ~3.5min |

**Recent Trend:**
- Last 5 plans: 01-02 (4min), 01-03 (4min), 02-01 (4min), 02-02 (3min)
- Trend: Stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 8 phases derived from 55 requirements; research suggested 5 phases but comprehensive depth warranted finer granularity
- [Roadmap]: Phase 6 (Captioning) depends on Phase 2 (Model Config) + Phase 4 (GUI) -- not Phase 5 (Crop) -- enabling parallel work streams
- [Roadmap]: Phase 7 (Video/CLIP) is independent of Phases 5-6, can be reordered if priorities shift
- [01-01 SVC-01]: Module-level stateless functions for services (no classes)
- [01-01 SVC-02]: Concept resolution moved to dataset_service.py as private helper
- [01-01 SVC-03]: Project manifest (.klippbok/manifest.json) separate from validation manifest (klippbok_manifest.json)
- [01-02]: Reused video/models.py IssueCode enum for image codes (single source of truth)
- [01-02]: Pillow verify+re-open pattern for corruption detection
- [01-02]: RGBA triggers warning not error -- auto-flatten to RGB during export
- [01-03 UNI-01]: Type discriminator defaults to "video" for zero breakage
- [01-03 UNI-02]: target_type parameter with video/image/mixed values for discovery
- [01-03 UNI-03]: SUPPORTED_IMAGE_EXTENSIONS imported from image module with fallback
- [02-01]: max_aspect_ratio defaults to 2.0 for bucket generation
- [02-01]: step_size validated as power of 2 (VAE compression alignment)
- [02-01]: base_resolution validated as multiple of step_size via model_validator
- [02-02]: Override fields flattened (bucket_step_size) instead of nested dicts for simpler JSON
- [02-02]: Built-in profiles cannot be deleted or overwritten by custom profiles
- [02-02]: Custom profiles stored as individual JSON files in ~/.klippbok/profiles/

### Pending Todos

None.

### Blockers/Concerns

- [Research]: react-advanced-cropper custom stencil for bucket-ratio snapping needs a spike before Phase 5 commitment
- [Research]: WD Tagger v3 ONNX preprocessing (448x448, normalization) must be verified against reference implementation before Phase 6
- [Research]: Auto-crop subject detection for anime content needs evaluation before Phase 5 plan 4

## Session Continuity

Last session: 2026-02-28
Stopped at: Phase 2 complete, verified, ready for Phase 3
Resume file: None
