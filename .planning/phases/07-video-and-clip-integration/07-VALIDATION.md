---
phase: 7
slug: video-and-clip-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-05
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing, configured in pyproject.toml) |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] testpaths = ["tests"] |
| **Quick run command** | `pytest tests/test_triage_models.py tests/test_video_probe.py -x` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -k "not test_video_api"` (skip API integration tests needing running server)
- **After every plan wave:** Run `pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | GUI-08 | integration | `pytest tests/test_video_api.py::test_ingest_start -x` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | GUI-08 | integration | `pytest tests/test_video_api.py::test_scan -x` | ❌ W0 | ⬜ pending |
| 07-01-03 | 01 | 1 | GUI-08 | integration | `pytest tests/test_video_api.py::test_extract_start -x` | ❌ W0 | ⬜ pending |
| 07-01-04 | 01 | 1 | GUI-08 | integration | `pytest tests/test_video_api.py::test_ingest_cancel -x` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 1 | ARCH-08 | unit | `pytest tests/test_triage_service.py::test_triage_images -x` | ❌ W0 | ⬜ pending |
| 07-02-02 | 02 | 1 | ARCH-08 | unit | `pytest tests/test_triage_service.py::test_triage_manifest_write -x` | ❌ W0 | ⬜ pending |
| 07-02-03 | 02 | 2 | ARCH-08 | unit | `pytest tests/test_face_service.py::test_face_embeddings -x` | ❌ W0 | ⬜ pending |
| 07-02-04 | 02 | 2 | ARCH-08 | unit | `pytest tests/test_face_service.py::test_face_clustering -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_video_api.py` — stubs for GUI-08 API integration (ingest, scan, extract endpoints)
- [ ] `tests/test_triage_service.py` — stubs for ARCH-08 image-mode triage and manifest writing
- [ ] `tests/test_face_service.py` — stubs for InsightFace embedding and DBSCAN clustering (with mocked insightface for CI)
- [ ] `tests/test_video_service.py` — stubs for extracted video service functions

*(All existing test files in `tests/` cover prior phases and remain unaffected)*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Video playback in lightbox | GUI-08 | Browser `<video>` element rendering | 1. Import a video clip 2. Click thumbnail in gallery 3. Verify lightbox shows video with play controls |
| Play button overlay on thumbnails | GUI-08 | Visual CSS overlay | 1. Import video clips 2. Verify play icon + duration badge appear on gallery thumbnails |
| Triage score color overlays | ARCH-08 | Visual CSS rendering | 1. Run triage on images 2. Verify green/yellow/grey score badges on gallery items |
| InsightFace suggested subjects panel | ARCH-08 | End-to-end face clustering UX | 1. Import images with faces 2. Run face detection 3. Verify suggested subjects panel shows clustered groups |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
