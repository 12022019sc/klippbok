---
phase: 07-video-and-clip-integration
plan: "01"
subsystem: video-api
tags: [video, service-layer, api, sse, thumbnails, tdd]
dependency_graph:
  requires:
    - klippbok/video/ (probe, validate, scene, split, extract modules)
    - klippbok/api/routers/import_.py (SSE pattern reference)
    - klippbok/api/thumbnail.py (cache key pattern)
    - klippbok/services/ (SVC-01 stateless module pattern)
  provides:
    - klippbok/services/video_service.py
    - klippbok/api/routers/video.py
    - klippbok/api/thumbnail.generate_video_thumbnail
  affects:
    - klippbok/api/app.py (router registration + lifespan shutdown)
tech_stack:
  added: []
  patterns:
    - SSE via asyncio.Queue + sse_starlette (same as import_.py)
    - module-level stateless service functions (SVC-01)
    - SHA256[:16] cache key for thumbnails (API-02 pattern)
    - run_in_executor for CPU-bound calls in async routes
key_files:
  created:
    - klippbok/services/video_service.py
    - klippbok/api/routers/video.py
    - tests/test_video_service.py
    - tests/test_video_api.py
  modified:
    - klippbok/api/thumbnail.py (added generate_video_thumbnail)
    - klippbok/api/app.py (registered video router, added to lifespan shutdown)
decisions:
  - "[07-01 VID-01]: generate_video_thumbnail is a thin alias for get_video_thumbnail -- avoids breaking existing callers while providing the documented export name"
  - "[07-01 VID-02]: Thumbnail endpoint resolves clip by scanning project then matching clip_id -- keeps clip lookup consistent with clips list endpoint"
  - "[07-01 VID-03]: extract_frames returns list[Path] (not ExtractionReport) -- simpler API for service consumers; ExtractionReport details are an implementation detail"
  - "[07-01 VID-04]: ingest_video progress_callback uses run_coroutine_threadsafe to bridge sync executor thread to async queue -- prevents event loop blocking"
metrics:
  duration: 473s
  completed_date: "2026-03-05"
  tasks_completed: 2
  files_changed: 6
---

# Phase 7 Plan 1: Video Service and API Router Summary

Video pipeline service layer extracted from CLI, exposed via FastAPI router with SSE progress.

## What Was Built

**video_service.py** — Three stateless service functions extracted from `klippbok/video/__main__.py`:
- `scan_project_videos(project_dir, config)` — wraps probe_directory + validate_directory, returns ScanReport
- `ingest_video(video_path, output_dir, ...)` — scene detection + split, supports triage_segments shortcut and progress_callback for SSE
- `extract_frames(clips_dir, output_dir, frames_per_clip)` — wraps extract_directory, returns list[Path]

**thumbnail.py extension** — Added `generate_video_thumbnail(video_path, cache_dir)` as a named alias for `get_video_thumbnail` (the underlying ffmpeg extraction was already implemented). SHA256[:16] cache key matches [04-01 API-02] pattern.

**video.py router** — 9 endpoints following the SSE pattern from import_.py:
- `POST /video/ingest/start` — background task + asyncio.Queue, returns operation_id
- `GET /video/ingest/{op_id}/events` — SSE stream with ingest_progress / ingest_done / ingest_error events
- `POST /video/ingest/{op_id}/cancel` — task cancellation
- `GET /video/scan` — synchronous clip metadata scan
- `POST /video/extract/start` — background extraction task
- `GET /video/extract/{op_id}/events` — SSE stream for extraction progress
- `POST /video/extract/{op_id}/cancel` — extraction cancellation
- `GET /video/clips` — clip list with metadata and thumbnail URLs
- `GET /video/clips/{clip_id}/thumbnail` — serve cached JPEG

**app.py** — video_router registered before StaticFiles mount; _ingest_tasks and _extract_tasks added to lifespan shutdown cancellation loop.

## Tests

- 12 unit tests in `test_video_service.py` — mocked probe_directory, validate_directory, detect_scenes, split_video_at_scenes, split_video_segments, extract_directory, and subprocess.run
- 15 integration tests in `test_video_api.py` — TestClient with mocked service functions, all endpoints covered

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing export] generate_video_thumbnail as alias for get_video_thumbnail**
- **Found during:** Task 1
- **Issue:** `get_video_thumbnail` already fully implemented in thumbnail.py, plan called for `generate_video_thumbnail` as the new export name
- **Fix:** Added `generate_video_thumbnail` as a thin alias that calls `get_video_thumbnail` -- provides the documented export without duplicating logic and without removing the existing function
- **Files modified:** klippbok/api/thumbnail.py

**2. [Rule 1 - Bug] Test mocking for extract_directory**
- **Found during:** Task 1 test run
- **Issue:** Initial service imported extract_directory as `_extract_directory` (private alias), blocking patch from finding the symbol
- **Fix:** Changed import to use direct name `extract_directory` so tests can patch `klippbok.services.video_service.extract_directory`
- **Files modified:** klippbok/services/video_service.py, tests/test_video_service.py

**3. [Rule 1 - Bug] Thumbnail endpoint test needed scan mock**
- **Found during:** Task 2 test run
- **Issue:** `GET /video/clips/{clip_id}/thumbnail` scans project to find clip by ID -- test was not mocking scan_project_videos, causing 404
- **Fix:** Added `patch("klippbok.api.routers.video.scan_project_videos", ...)` to the thumbnail test
- **Files modified:** tests/test_video_api.py

## Self-Check: PASSED

All created files verified on disk:
- FOUND: klippbok/services/video_service.py
- FOUND: klippbok/api/routers/video.py
- FOUND: tests/test_video_service.py
- FOUND: tests/test_video_api.py
- FOUND: klippbok/api/thumbnail.py (modified)
- FOUND: klippbok/api/app.py (modified)

Commits verified:
- 5b15134: feat(07-01): extract video service layer and add generate_video_thumbnail
- e5662fb: feat(07-01): add video API router with SSE ingest/extract and clips endpoints
