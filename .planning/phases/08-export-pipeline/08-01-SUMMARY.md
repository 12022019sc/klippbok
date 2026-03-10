---
phase: 08-export-pipeline
plan: "01"
subsystem: export
tags: [export, manifest, kohya, aitoolkit, onetrainer, tdd]
dependency_graph:
  requires:
    - klippbok/services/project_service.py (load_manifest)
    - klippbok/config/model_config.py (get_profile)
  provides:
    - klippbok/services/export_service.py
  affects: []
tech_stack:
  added: [pyyaml]
  patterns: [pydantic-models, tdd, manifest-filtering, trainer-config-generation]
key_files:
  created:
    - klippbok/services/export_service.py
    - tests/test_export_service.py
  modified: []
decisions:
  - "EXPT-YAML-01: PyYAML used for ai-toolkit YAML generation (already in project deps)"
  - "EXPT-TOML-01: kohya TOML written as string concatenation matching musubi pattern in trainers.py"
  - "EXPT-OT-01: training_preset.json based on user Prodigy preset (rank 64, 7 epochs, batch 2, 768px) with TODO markers for base_model_name"
  - "EXPT-PROGRESS-01: progress_cb signature is (current: int, total: int) — called after each file copy"
  - "EXPT-CAPTION-01: caption .txt files always written from manifest entry.get('caption', '') — never from disk files"
metrics:
  duration: "4 minutes"
  completed: "2026-03-10"
  tasks_completed: 2
  files_changed: 2
---

# Phase 8 Plan 01: Export Service Summary

**One-liner:** Manifest-filtered image export pipeline with kohya TOML, ai-toolkit YAML, and OneTrainer concept.json + Prodigy training preset generation.

## What Was Built

`klippbok/services/export_service.py` — the core export backend for Phase 8. Provides all functions the API router (08-02) will consume.

### Key Functions

| Function | Purpose |
|----------|---------|
| `get_export_candidates(project_dir)` | Filter manifest images by `source="crop"` |
| `validate_export_candidates(entries)` | Pre-flight check for missing/empty captions |
| `get_export_defaults(project_dir)` | Model-aware defaults from `active_profile` + `anchor_word` |
| `_copy_images_with_captions(entries, ...)` | Copy images + write stem-matched .txt from manifest |
| `generate_kohya_export(...)` | `{repeats}_{trigger} {class}/` folder + `kohya_config.toml` |
| `generate_aitoolkit_export(...)` | `images/` folder + `aitoolkit_config.yaml` |
| `generate_onetrainer_export(...)` | `images/` + `output/` + `concept.json` + `training_preset.json` |
| `perform_export(project_dir, config, ...)` | Full pipeline dispatcher → `ExportResult` |

### Models

- `ExportConfig` — trainer, repeats, trigger_word, class_name, concept_name, output_dir
- `ExportResult` — status, image_count, config_path, output_dir

### Config File Contents

**kohya_config.toml:**
```toml
[general]
shuffle_caption = false
caption_extension = ".txt"
keep_tokens = 1

[[datasets]]
resolution = 512
batch_size = 1

  [[datasets.subsets]]
  image_dir = "./5_sks person"
  class_tokens = "sks person"
  num_repeats = 5
```

**aitoolkit_config.yaml:** datasets section with `folder_path: ./images`, `caption_ext: txt`, `resolution: [512, 512]` — no `is_video` field.

**concept.json:** OneTrainer concept array with `path`, `name`, `type: STANDARD`, `text.prompt_source: sample`, `image_variations` with aspect ratio bucketing, `balancing: REPEATS`, `repeats`.

**training_preset.json:** Prodigy optimizer preset (rank 64, 7 epochs, batch 2) with TODO marker for `base_model_name`.

## Test Coverage

35 tests in `tests/test_export_service.py`:
- `TestGetExportCandidates` (4 tests) — filtering logic including edge cases
- `TestValidateExportCandidates` (5 tests) — missing/empty caption detection
- `TestExportConfig` (2 tests) — model defaults and custom values
- `TestGetExportDefaults` (3 tests) — resolution from profile, concept_name from folder
- `TestCopyImagesWithCaptions` (3 tests) — copy, empty caption, progress callback
- `TestGenerateKohyaExport` (4 tests) — folder structure, TOML content, forward slashes, captions
- `TestGenerateAiToolkitExport` (4 tests) — images folder, YAML content, no is_video, forward slashes
- `TestGenerateOneTrainerExport` (5 tests) — folder structure, concept.json, prompt_source, training_preset, forward slashes
- `TestPerformExport` (5 tests) — all three trainers, dir creation, result fields

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test assertion used quoted YAML string format**
- **Found during:** Task 2, GREEN phase
- **Issue:** Test asserted `'caption_ext: "txt"'` but PyYAML outputs `caption_ext: txt` (no quotes for plain strings)
- **Fix:** Changed assertion to `"caption_ext:" in content and "txt" in content`
- **Files modified:** tests/test_export_service.py
- **Commit:** 3dba524

### Implementation Notes

Tasks 1 and 2 were implemented together in a single GREEN phase since the trainer generators are tightly coupled with the copy helper from Task 1. Both tasks share the same commit (`3dba524`).

## Self-Check: PASSED

- klippbok/services/export_service.py: FOUND
- tests/test_export_service.py: FOUND
- commit 3dba524: FOUND
- All 35 tests pass
