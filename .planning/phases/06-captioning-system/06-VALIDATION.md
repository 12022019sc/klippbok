---
phase: 6
slug: captioning-system
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-03
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` |
| **Quick run command** | `pytest tests/test_wd_tagger.py tests/test_caption_service.py tests/test_caption_api.py -x` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_wd_tagger.py tests/test_caption_service.py tests/test_caption_api.py -x`
- **After every plan wave:** Run `pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | CAPT-01 | unit | `pytest tests/test_wd_tagger.py::test_prepare_image -x` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | CAPT-01 | unit | `pytest tests/test_wd_tagger.py -x` | ❌ W0 | ⬜ pending |
| 06-02-01 | 02 | 1 | CAPT-02 | unit (mock) | `pytest tests/test_caption_service.py::test_nl_caption_gemini -x` | ❌ W0 | ⬜ pending |
| 06-02-02 | 02 | 1 | CAPT-03 | unit | `pytest tests/test_caption_service.py::test_caption_routing -x` | ❌ W0 | ⬜ pending |
| 06-02-03 | 02 | 1 | CAPT-04 | unit | `pytest tests/test_caption_service.py::test_style_override -x` | ❌ W0 | ⬜ pending |
| 06-03-01 | 03 | 2 | CAPT-05 | integration | `pytest tests/test_caption_api.py::test_update_caption -x` | ❌ W0 | ⬜ pending |
| 06-03-02 | 03 | 2 | GUI-04 | manual | N/A | N/A | ⬜ pending |
| 06-04-01 | 04 | 2 | CAPT-06 | unit | `pytest tests/test_caption_service.py::test_trigger_prepend -x` | ❌ W0 | ⬜ pending |
| 06-04-02 | 04 | 2 | CAPT-07 | unit | `pytest tests/test_caption_service.py::test_batch_operations -x` | ❌ W0 | ⬜ pending |
| 06-04-03 | 04 | 2 | CAPT-08 | unit | `pytest tests/test_caption_scoring.py::test_image_scoring_config -x` | ❌ W0 | ⬜ pending |
| 06-04-04 | 04 | 2 | GUI-06 | manual | N/A | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_wd_tagger.py` — stubs for CAPT-01 (preprocessing, threshold filtering). Use 32x32 test PNG; mock onnxruntime
- [ ] `tests/test_caption_service.py` — stubs for CAPT-02, CAPT-03, CAPT-04, CAPT-06, CAPT-07. Mock WD Tagger and VLM backends
- [ ] `tests/test_caption_api.py` — stubs for CAPT-05 (PATCH endpoint, manifest + sidecar sync). Use TestClient with temp project dir
- [ ] `tests/test_caption_scoring.py` — add `test_image_scoring_config()` to existing file (no new file needed)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CaptionPanel renders caption text in lightbox footer | GUI-04 | React UI visual verification | Open gallery, click image, verify caption text appears in lightbox footer with edit capability |
| SettingsPage profile dropdown changes active_profile | GUI-06 | React UI interaction | Open settings, change model profile dropdown, verify caption style updates |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
