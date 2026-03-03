---
phase: 05
slug: interactive-crop-editor
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-03
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.0+ |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `pytest tests/test_image_autocrop.py tests/test_crop_service.py tests/test_upscale_service.py -x` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_image_autocrop.py tests/test_crop_service.py tests/test_upscale_service.py -x`
- **After every plan wave:** Run `pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 0 | CROP-02 | unit | `pytest tests/test_crop_service.py::test_snap_to_nearest_bucket -x` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 0 | CROP-07 | unit | `pytest tests/test_image_autocrop.py::test_auto_crop_detects_person -x` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 0 | CROP-08 | unit | `pytest tests/test_image_autocrop.py::test_auto_crop_center_fallback -x` | ❌ W0 | ⬜ pending |
| 05-01-04 | 01 | 0 | CROP-09 | unit | `pytest tests/test_image_autocrop.py::test_auto_crop_coords_in_bounds -x` | ❌ W0 | ⬜ pending |
| 05-01-05 | 01 | 0 | CROP-apply | unit | `pytest tests/test_crop_service.py::test_apply_crop_dimensions -x` | ❌ W0 | ⬜ pending |
| 05-01-06 | 01 | 0 | CROP-apply | unit | `pytest tests/test_crop_service.py::test_apply_crop_rotation -x` | ❌ W0 | ⬜ pending |
| 05-01-07 | 01 | 0 | Upscale | unit | `pytest tests/test_upscale_service.py::test_detect_seedvr2 -x` | ❌ W0 | ⬜ pending |
| 05-02-01 | 01 | 1 | CROP-01 | manual-only | n/a — browser interaction | n/a | ⬜ pending |
| 05-02-02 | 02 | 1 | CROP-04 | unit | `pytest tests/test_image_bucket.py -x` | ✅ existing | ⬜ pending |
| 05-03-01 | 03 | 2 | CROP-05 | manual-only | n/a — browser interaction | n/a | ⬜ pending |
| 05-03-02 | 03 | 2 | CROP-06 | manual-only | n/a — browser interaction | n/a | ⬜ pending |
| 05-03-03 | 03 | 2 | CROP-03 | manual-only | n/a — browser keyboard event | n/a | ⬜ pending |
| 05-04-01 | 04 | 2 | GUI-05 | manual-only | n/a — browser navigation | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_image_autocrop.py` — stubs for CROP-07, CROP-08, CROP-09
- [ ] `tests/test_crop_service.py` — stubs for CROP-02 snap math, apply_crop dimensions, apply_crop rotation
- [ ] `tests/test_upscale_service.py` — stubs for detect_seedvr2 path detection
- [ ] `tests/fixtures/person_sample.jpg` — small test image with a person (for MediaPipe detection tests)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Crop rectangle renders and is draggable | CROP-01 | Browser canvas interaction | Open crop editor, verify rectangle appears, drag to reposition |
| CTRL+release triggers snap | CROP-03 | Browser keyboard event | Hold CTRL, resize freeform, release CTRL, verify snap to bucket |
| Zoom slider works on high-res images | CROP-05 | Browser interaction | Load high-res image, use zoom slider, verify smooth zoom |
| Rotation/flip controls work | CROP-06 | Browser interaction | Click 90° rotate, H-flip, V-flip, verify transformations apply |
| /crop route navigable from gallery | GUI-05 | Browser navigation | Click image in gallery, verify crop editor opens |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
