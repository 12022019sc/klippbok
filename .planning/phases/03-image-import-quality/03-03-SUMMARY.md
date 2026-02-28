---
phase: 03-image-import-quality
plan: "03"
name: perceptual-hash-dedup-and-batch-import-pipeline
subsystem: image
tags: [imagehash, phash, dedup, batch-import, manifest, pipeline, tdd]

dependency-graph:
  requires:
    - "03-01: image models, validation, probe (ImageImportEntry, ImageImportReport)"
    - "03-02: assign_to_bucket, needs_upscale, compute_blur_score, is_blurry"
  provides:
    - "compute_phash: hex string pHash via imagehash.phash()"
    - "are_near_duplicates: Hamming distance <= 10 threshold comparison"
    - "select_keeper: highest resolution, PNG > TIFF > WEBP > JPEG tiebreaker"
    - "batch_import_images: full discover->probe->validate->bucket->blur->dedup->persist pipeline"
    - "save_image_entries: manifest persistence for 'images' key"
  affects:
    - "Phase 4 (GUI): batch_import_images is the backend for import UI"
    - "Phase 5 (Crop): uses manifest images entries for source data"
    - "Phase 6 (Captioning): skips near-duplicate images"

tech-stack:
  added:
    - "imagehash==4.3.2: pHash computation via imagehash.phash()"
    - "PyWavelets==1.9.0: installed as imagehash dependency"
  patterns:
    - "Incremental hash map: detect duplicates within same batch and across runs"
    - "Frozen model reconstruction: new ImageValidation() to append extra issues"
    - "Canonical relative path comparison: str(path.resolve().relative_to(project_dir))"

file-tracking:
  created:
    - "klippbok/image/dedup.py"
    - "tests/test_image_dedup.py"
  modified:
    - "klippbok/image/__init__.py"
    - "klippbok/services/image_service.py"
    - "klippbok/services/project_service.py"
    - "tests/test_image_service.py"

decisions:
  - id: "03-03-DEDUP-01"
    decision: "imagehash returns np.bool_ not Python bool -- explicit bool() cast needed in are_near_duplicates"
    rationale: "Test used 'is True' which fails for np.bool_. Explicit cast makes API clean."
  - id: "03-03-DEDUP-02"
    decision: "Solid-color test images produce identical pHash (all flat DCT content) -- use textured gradients for dedup tests"
    rationale: "pHash works on DCT frequency components; uniform content has no frequency variation. Tests must use images with actual spatial structure."
  - id: "03-03-PIPE-01"
    decision: "batch_import_images persists only non-skipped entries to manifest (skipped entries already in manifest)"
    rationale: "Prevents duplicate entries on re-import. Skip logic loads known paths from manifest, new entries appended."
  - id: "03-03-PIPE-02"
    decision: "imported count = all non-skipped images (including rejected with errors)"
    rationale: "Matches user mental model: 'discovered 10, skipped 2, imported 8' where imported includes errored ones. rejected is a subset."

metrics:
  duration: "~5 min"
  completed: "2026-02-28"
  tasks-completed: 2
  tests-added: 26
  tests-total-after: 1135
---

# Phase 3 Plan 03: Perceptual Hash Dedup and Batch Import Pipeline Summary

**One-liner:** pHash dedup via imagehash (Hamming <= 10 threshold) wired into full batch import pipeline with manifest persistence.

## Objective

Implement perceptual hash dedup module and wire the complete batch import pipeline -- discover, skip existing, probe, validate, bucket, blur, dedup, persist -- into a single `batch_import_images` function.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Implement perceptual hash dedup module | 0af4ae0 | klippbok/image/dedup.py, tests/test_image_dedup.py |
| 2 | Wire batch import pipeline with manifest persistence | 868a58d | klippbok/services/image_service.py, project_service.py, tests/test_image_service.py |

## What Was Built

### `klippbok/image/dedup.py`

Three public functions:

- **`compute_phash(image_path)`** -- opens image with Pillow, computes pHash via `imagehash.phash()`, returns hex string for manifest storage
- **`are_near_duplicates(hash_hex_a, hash_hex_b)`** -- converts hex strings back to `ImageHash` objects, computes Hamming distance, returns `bool` (explicit cast from `np.bool_`)
- **`select_keeper(images)`** -- picks ImageMetadata with highest pixel_count; tiebreaker on `_FORMAT_PREFERENCE` dict (png=0, tiff=1, webp=2, jpeg=3)

**`PHASH_THRESHOLD = 10`** -- catches resized, re-compressed, minor-crop variants of same image.

### `klippbok/services/image_service.py` -- `batch_import_images`

Full pipeline in correct order:

1. Load manifest -> build `known_paths` set and `hash_map` (prior hashes)
2. Discover images via `discover_images()`
3. Per-image: probe -> validate -> bucket -> blur -> pHash -> dedup check
4. Extra issues appended to validation (IMAGE_EXTREME_ASPECT, IMAGE_UPSCALE_REQUIRED, IMAGE_BLUR_DETECTED, IMAGE_NEAR_DUPLICATE)
5. Report counts computed (imported = all non-skipped; rejected = subset with errors)
6. Persist non-skipped entries to manifest via `save_image_entries()`

**Incremental hash map:** After computing each image's pHash, it's added to `hash_map` so subsequent images in the same batch can detect duplicates against it.

### `klippbok/services/project_service.py` -- `save_image_entries`

Loads existing manifest, appends new image entries to `manifest["images"]`, preserves existing "samples" and other keys. Creates `.klippbok/` directory if needed.

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| 03-03-DEDUP-01 | Explicit `bool()` cast in `are_near_duplicates` | imagehash returns `np.bool_`; `is True` identity check fails |
| 03-03-DEDUP-02 | Use textured gradient images for pHash tests | Solid-color images have identical DCT content = same pHash regardless of color |
| 03-03-PIPE-01 | Persist only non-skipped entries (no duplicates in manifest) | Already-imported files skipped via path comparison; only new entries appended |
| 03-03-PIPE-02 | `imported` = all non-skipped (including rejected) | Matches user mental model; `rejected` is a subset of `imported` |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] np.bool_ identity comparison failure in are_near_duplicates**

- **Found during:** Task 1 GREEN phase -- `test_identical_hashes_are_duplicates` failed with `np.True_ is True`
- **Issue:** `imagehash`'s `-` operator returns `np.bool_` not Python `bool`; `is True` identity check fails
- **Fix:** Added `bool()` cast: `return bool((ha - hb) <= PHASH_THRESHOLD)`
- **Files modified:** `klippbok/image/dedup.py`
- **Commit:** 0af4ae0

**2. [Rule 1 - Bug] Solid-color images produce identical pHash regardless of color**

- **Found during:** Task 1 GREEN phase -- `test_phash_different_images_different_hash` failed (both red and blue solid images produced `'8000000000000000'`)
- **Issue:** pHash operates on DCT frequency components; solid-color images have no spatial frequency variation, producing identical hashes
- **Fix:** Replaced solid-color test images with gradient-textured images (`_save_textured()` helper) that have meaningful spatial content
- **Files modified:** `tests/test_image_dedup.py`
- **Commit:** 0af4ae0

## Next Phase Readiness

Phase 3 is complete. All three plans delivered:
- 03-01: TIFF support, 5 IssueCodes, ImageImportEntry/ImageImportReport models
- 03-02: assign_to_bucket, needs_upscale, compute_blur_score, is_blurry
- 03-03: compute_phash, are_near_duplicates, select_keeper, batch_import_images

**Phase 4 (GUI) can begin.** `batch_import_images` is the backend endpoint for the import UI.

**Known constraints for future phases:**
- Near-duplicate detection is within-batch + cross-import (hash map accumulated from manifest)
- pHash threshold 10 is fixed (not user-configurable per 03-03 spec)
- `select_keeper` is available but `batch_import_images` does not auto-remove duplicates -- flags only. Removal is a future concern.
