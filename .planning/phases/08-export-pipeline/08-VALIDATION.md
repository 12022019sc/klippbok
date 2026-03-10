---
phase: 8
slug: export-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing, no new install needed) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `pytest tests/test_export_service.py tests/test_export_api.py -x` |
| **Full suite command** | `pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_export_service.py tests/test_export_api.py -x`
- **After every plan wave:** Run `pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | EXPT-01 | unit | `pytest tests/test_export_service.py::test_kohya_folder_structure -x` | ❌ W0 | ⬜ pending |
| 08-01-02 | 01 | 1 | EXPT-01 | unit | `pytest tests/test_export_service.py::test_kohya_toml_content -x` | ❌ W0 | ⬜ pending |
| 08-01-03 | 01 | 1 | EXPT-02 | unit | `pytest tests/test_export_service.py::test_aitoolkit_yaml_image_mode -x` | ❌ W0 | ⬜ pending |
| 08-01-04 | 01 | 1 | EXPT-03 | unit | `pytest tests/test_export_service.py::test_onetrainer_concept_json -x` | ❌ W0 | ⬜ pending |
| 08-01-05 | 01 | 1 | EXPT-03 | unit | `pytest tests/test_export_service.py::test_onetrainer_preset_paths -x` | ❌ W0 | ⬜ pending |
| 08-02-01 | 02 | 1 | EXPT-05 | unit | `pytest tests/test_export_service.py::test_caption_txt_written -x` | ❌ W0 | ⬜ pending |
| 08-02-02 | 02 | 1 | EXPT-05 | unit | `pytest tests/test_export_service.py::test_stem_matching -x` | ❌ W0 | ⬜ pending |
| 08-02-03 | 02 | 1 | EXPT-06 | unit | `pytest tests/test_export_service.py::test_crop_only_filter -x` | ❌ W0 | ⬜ pending |
| 08-02-04 | 02 | 1 | EXPT-07 | unit | `pytest tests/test_export_service.py::test_config_file_paths -x` | ❌ W0 | ⬜ pending |
| 08-03-01 | 03 | 2 | GUI-07 | integration | `pytest tests/test_export_api.py::test_start_export -x` | ❌ W0 | ⬜ pending |
| 08-03-02 | 03 | 2 | GUI-07 | unit | `pytest tests/test_export_service.py::test_validation_scan -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_export_service.py` — stubs for EXPT-01 through EXPT-07 (manifest filtering, file copy, caption write, config generation)
- [ ] `tests/test_export_api.py` — stubs for GUI-07 (SSE start, events, cancel endpoints)

*Existing infrastructure covers framework needs — pytest already present.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Export UI flow end-to-end | GUI-07 | Requires browser interaction | 1. Open Export page 2. Select trainer format 3. Configure options 4. Click Export 5. Verify download/output |
| OneTrainer process launch | EXPT-04 | Requires OneTrainer installed | 1. Configure OneTrainer path 2. Export with "launch trainer" 3. Verify process starts |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
