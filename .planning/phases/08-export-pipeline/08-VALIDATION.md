---
phase: 8
slug: export-pipeline
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-10
validated: 2026-03-12
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing, no new install needed) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `pytest tests/test_export_service.py tests/test_export_api.py tests/test_onetrainer_service.py -x` |
| **Full suite command** | `pytest tests/ -x` |
| **Actual runtime** | ~5.4 seconds (100 tests) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_export_service.py tests/test_export_api.py -x`
- **After every plan wave:** Run `pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5.4 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | EXPT-01 | unit | `pytest tests/test_export_service.py::TestGenerateKohyaExport::test_creates_correct_folder_structure -x` | ✅ | ✅ green |
| 08-01-02 | 01 | 1 | EXPT-01 | unit | `pytest tests/test_export_service.py::TestGenerateKohyaExport::test_writes_kohya_toml -x` | ✅ | ✅ green |
| 08-01-03 | 01 | 1 | EXPT-02 | unit | `pytest tests/test_export_service.py::TestGenerateAiToolkitExport::test_writes_yaml_config -x` | ✅ | ✅ green |
| 08-01-04 | 01 | 1 | EXPT-03 | unit | `pytest tests/test_export_service.py::TestGenerateOneTrainerExport::test_writes_concept_json -x` | ✅ | ✅ green |
| 08-01-05 | 01 | 1 | EXPT-03 | unit | `pytest tests/test_export_service.py::TestGenerateOneTrainerExport::test_writes_training_preset_json -x` | ✅ | ✅ green |
| 08-02-01 | 02 | 1 | EXPT-05 | unit | `pytest tests/test_export_service.py::TestCopyImagesWithCaptions::test_copies_image_and_writes_txt -x` | ✅ | ✅ green |
| 08-02-02 | 02 | 1 | EXPT-05 | unit | `pytest tests/test_export_service.py::TestCopyImagesWithCaptions::test_copies_image_and_writes_txt -x` | ✅ | ✅ green |
| 08-02-03 | 02 | 1 | EXPT-06 | unit | `pytest tests/test_export_service.py::TestGetExportCandidates::test_returns_only_crop_entries -x` | ✅ | ✅ green |
| 08-02-04 | 02 | 1 | EXPT-07 | unit | `pytest tests/test_export_service.py::TestPerformExport -x` | ✅ | ✅ green |
| 08-03-01 | 03 | 2 | GUI-07 | integration | `pytest tests/test_export_api.py::TestExportStartEndpoint::test_start_returns_op_id -x` | ✅ | ✅ green |
| 08-03-02 | 03 | 2 | GUI-07 | integration | `pytest tests/test_export_api.py::TestExportValidateEndpoint::test_validate_returns_candidates_and_issues -x` | ✅ | ✅ green |
| 08-04-01 | 04 | 2 | GUI-07 | integration | `pytest tests/test_export_api.py::TestTrainStatusEndpoint -x` | ✅ | ✅ green |
| 08-04-02 | 04 | 2 | GUI-07 | integration | `pytest tests/test_export_api.py::TestTrainStopEndpoint -x` | ✅ | ✅ green |
| 08-04-03 | 04 | 2 | GUI-07 | integration | `pytest tests/test_export_api.py::TestTrainLaunchGuiEndpoint -x` | ✅ | ✅ green |
| 08-04-04 | 04 | 2 | GUI-07 | integration | `pytest tests/test_export_api.py::TestTrainModelsEndpoint -x` | ✅ | ✅ green |
| 08-04-05 | 04 | 2 | GUI-07 | integration | `pytest tests/test_export_api.py::TestSettingsToolsGetEndpoint -x` | ✅ | ✅ green |
| 08-04-06 | 04 | 2 | GUI-07 | integration | `pytest tests/test_export_api.py::TestSettingsToolsPutEndpoint -x` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_export_service.py` — 35 tests for EXPT-01 through EXPT-07 (manifest filtering, file copy, caption write, config generation)
- [x] `tests/test_export_api.py` — 28 tests for GUI-07 (export endpoints + training endpoints + settings tools)
- [x] `tests/test_onetrainer_service.py` — 37 tests for EXPT-04 (OneTrainer detection, parsing, process management, GPU service)

*All 100 tests pass.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Export UI flow end-to-end | GUI-07 | Requires browser interaction | 1. Open Export page 2. Select trainer format 3. Configure options 4. Click Export 5. Verify download/output |
| OneTrainer process launch | EXPT-04 | Requires OneTrainer installed | 1. Configure OneTrainer path 2. Export with "launch trainer" 3. Verify process starts |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s (actual: 5.4s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ✅ validated 2026-03-12

---

## Validation Audit 2026-03-12

| Metric | Count |
|--------|-------|
| Gaps found | 6 |
| Resolved | 6 |
| Escalated | 0 |
