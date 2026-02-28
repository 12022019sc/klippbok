# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-27)

**Core value:** Take raw images/video of any size and produce correctly bucketed, captioned, training-ready datasets for any supported diffusion model through an intuitive web interface.
**Current focus:** Phase 4 - GUI (Phase 3 complete)

## Current Position

Phase: 4 of 8 (Web GUI Foundation) -- In progress
Plan: 1 of ~3 in phase 4 -- in progress
Status: In progress
Last activity: 2026-02-28 -- Completed 04-01-PLAN.md (FastAPI backend shell)

Progress: [█████████░] ~60% (9 of ~15 estimated plans)

## Performance Metrics

**Velocity:**
- Total plans completed: 8
- Average duration: ~4min
- Total execution time: ~24min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-architecture-foundation | 3 | ~12min | ~4min |
| 02-model-configuration | 2 | ~7min | ~3.5min |
| 03-image-import-quality | 3 | ~5min | ~5min |

**Recent Trend:**
- Last 5 plans: 02-01 (4min), 02-02 (3min), 03-01 (5min), 03-02 (5min), 03-03 (5min)
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
- [03-01]: CMYK warning reuses IMAGE_RGBA_CONVERSION code (color conversion semantics are the same)
- [03-01]: n_frames on ImageMetadata (not validate_image param) -- keeps validation interface clean, pure-logic
- [03-02]: assign_to_bucket takes bucket list (not model profile) -- pure function, caller provides context
- [03-02]: scipy installed (1.17.1); imagehash installed (4.3.2) for pHash
- [03-02]: BLUR_THRESHOLD = 100.0 as module constant, not parameter -- fixed threshold semantics
- [03-02]: test_image_blur.py (not test_image_quality.py) to avoid collision with video domain test file
- [03-03]: np.bool_ returned by imagehash requires explicit bool() cast in are_near_duplicates
- [03-03]: Solid-color images produce identical pHash -- dedup tests use textured gradient images
- [03-03]: batch_import_images persists only non-skipped entries (skipped already in manifest)
- [03-03]: imported count = all non-skipped (including rejected); rejected is a subset
- [04-01 API-01]: SHA256[:16] of relative_path as image ID -- stable, portable, URL-safe
- [04-01 API-02]: Thumbnail cache key = SHA256[:16] of absolute path (different from image ID -- invalidates on move)
- [04-01 API-03]: Routers registered before StaticFiles mount (SPA catch-all safety)
- [04-01 API-04]: project_dir on app.state (no global state -- testable factory pattern)
- [04-01 API-05]: Top-level klippbok/__main__.py as thin dispatcher; submodule CLIs remain independent

03-01 SUMMARY: TIFF format support, 5 new IssueCodes, ImageImportEntry/ImageImportReport models, n_frames field
03-02 SUMMARY: assign_to_bucket (argmin AR), needs_upscale, compute_blur_score (scipy Laplacian), is_blurry (threshold 100.0)
03-03 SUMMARY: compute_phash (imagehash pHash hex), are_near_duplicates (Hamming <= 10), select_keeper (resolution + format), batch_import_images (full pipeline), save_image_entries (manifest persistence)
04-01 SUMMARY: FastAPI app factory (create_app), SHA256[:16] image ID, gallery+thumbnail endpoints, klippbok serve CLI, uvicorn/fastapi/sse-starlette installed

### Pending Todos

None.

### Blockers/Concerns

- [Research]: react-advanced-cropper custom stencil for bucket-ratio snapping needs a spike before Phase 5 commitment
- [Research]: WD Tagger v3 ONNX preprocessing (448x448, normalization) must be verified against reference implementation before Phase 6
- [Research]: Auto-crop subject detection for anime content needs evaluation before Phase 5 plan 4

## Session Continuity

Last session: 2026-02-28T17:10:00Z
Stopped at: Completed 04-01-PLAN.md (1/3 in Phase 4 -- In progress)
Resume file: None
