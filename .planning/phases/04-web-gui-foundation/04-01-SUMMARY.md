---
phase: 04
plan: 01
subsystem: api
tags: [fastapi, uvicorn, sse-starlette, thumbnail, cli, gallery]

dependency_graph:
  requires:
    - 03-03  # batch_import_images and save_image_entries (manifest persistence)
    - 01-01  # project_service.load_manifest
  provides:
    - FastAPI app factory (create_app)
    - Image gallery REST endpoint (GET /api/v1/images)
    - Thumbnail REST endpoint (GET /api/v1/images/{id}/thumbnail)
    - Disk-cached JPEG thumbnail generation
    - klippbok serve CLI entry point
    - python -m klippbok.api alternative entry point
  affects:
    - 04-02  # React frontend calls these endpoints
    - 04-03  # Additional API endpoints will use same app factory pattern

tech_stack:
  added:
    - fastapi[standard]>=0.100
    - uvicorn[standard]>=0.20
    - sse-starlette>=3.2.0
  patterns:
    - FastAPI app factory (create_app injection pattern for testability)
    - Router-before-StaticFiles registration order (SPA catch-all safety)
    - SHA256[:16] image ID from relative path (stable, portable)
    - Disk-cached JPEG thumbnails keyed by SHA256[:16] of absolute path

key_files:
  created:
    - klippbok/api/__init__.py
    - klippbok/api/app.py
    - klippbok/api/models.py
    - klippbok/api/thumbnail.py
    - klippbok/api/routers/__init__.py
    - klippbok/api/routers/images.py
    - klippbok/api/__main__.py
    - klippbok/__main__.py
  modified:
    - pyproject.toml

decisions:
  - id: API-01
    choice: "SHA256[:16] of relative_path as image ID"
    rationale: "Stable across server restarts, portable (no absolute paths), short enough for URLs"
    alternatives: "UUID (not reproducible), integer index (fragile on manifest reorder)"
  - id: API-02
    choice: "Thumbnail cache key = SHA256[:16] of absolute path"
    rationale: "Different from image ID intentionally -- thumbnail invalidates if file moves, image ID remains stable"
    alternatives: "Same hash as image ID (would serve stale thumbnails after move)"
  - id: API-03
    choice: "Routers registered before StaticFiles mount"
    rationale: "StaticFiles catch-all intercepts all unmatched routes; API routes must be registered first"
    alternatives: "Route prefixing only (less safe, depends on prefix matching order)"
  - id: API-04
    choice: "project_dir stored on app.state, accessed via request.app.state"
    rationale: "No global state; testable by creating app with different project_dir"
    alternatives: "Global variable (breaks parallel test execution)"
  - id: API-05
    choice: "Top-level klippbok/__main__.py dispatches dataset/video by importing submodule main()"
    rationale: "Keeps submodule CLIs independent; top-level is thin dispatcher only"
    alternatives: "Merged parser (creates coupling between domains)"

metrics:
  duration: ~2min
  completed: "2026-02-28"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 4 Plan 01: FastAPI Backend Shell Summary

**One-liner:** FastAPI app factory with SHA256-ID gallery/thumbnail API and `klippbok serve` CLI using uvicorn.

## What Was Built

The FastAPI backend foundation that the React frontend (Plan 02+) will call. Provides two REST endpoints and a disk-cached thumbnail service, all launchable via `klippbok serve` or `python -m klippbok.api`.

### Files Created

| File | Purpose |
|------|---------|
| `klippbok/api/app.py` | `create_app(project_dir)` factory; registers images router then mounts SPA static |
| `klippbok/api/models.py` | `ImageStatusResponse`, `GalleryResponse` Pydantic response schemas |
| `klippbok/api/thumbnail.py` | `get_thumbnail()` with `300x300` JPEG cache under `.klippbok/thumbnails/` |
| `klippbok/api/routers/images.py` | `GET /images/` gallery and `GET /images/{id}/thumbnail` endpoints |
| `klippbok/api/__main__.py` | `python -m klippbok.api` entry point (argparse: --project-dir, --host, --port) |
| `klippbok/__main__.py` | Top-level `klippbok` CLI dispatcher (serve / dataset / video subcommands) |

### Files Modified

| File | Change |
|------|--------|
| `pyproject.toml` | Added `gui` dependency group (fastapi, uvicorn, sse-starlette); added `[project.scripts]`; added `klippbok[gui]` to `all` |

## API Contract

### GET /api/v1/images/

Returns all images from `.klippbok/manifest.json`:

```json
{
  "total": 3,
  "images": [
    {
      "id": "a1b2c3d4e5f60001",
      "relative_path": "images/photo.jpg",
      "thumbnail_url": "/api/v1/images/a1b2c3d4e5f60001/thumbnail",
      "width": 1024,
      "height": 768,
      "resolution_ok": true,
      "quality_pass": true,
      "bucket": "1024x768",
      "is_near_duplicate": false,
      "duplicate_group_id": null,
      "caption": null
    }
  ]
}
```

### GET /api/v1/images/{id}/thumbnail

Returns `image/jpeg` -- a `300x300` max JPEG thumbnail cached at `.klippbok/thumbnails/{hash}.jpg`.

Returns 404 if image ID not in manifest or file missing on disk.

## Key Design Decisions

**API-01: Image ID = SHA256[:16] of relative_path.** Stable across restarts. Portable -- project can be moved without breaking IDs. Short enough for URLs.

**API-02: Thumbnail cache key = SHA256[:16] of absolute path.** Intentionally different from image ID: thumbnails invalidate if the file moves (correct behavior), while the ID remains stable.

**API-03: Routers must be registered before StaticFiles mount.** The SPA catch-all (`StaticFiles(html=True)`) intercepts all unmatched requests. API routers must be registered first or `/api/v1/...` calls will return `index.html`.

**API-04: project_dir on app.state, not global.** Enables clean testing with `create_app(project_dir=tmp_dir)` without globals bleeding between test runs.

## Deviations from Plan

None -- plan executed exactly as written.

## Verification Results

All four plan verification checks passed:

1. `python -c "from klippbok.api.app import create_app; print('OK')"` -- OK
2. `python -c "import fastapi, uvicorn, sse_starlette; print('Deps OK')"` -- Deps OK
3. `klippbok serve --help` -- shows --project-dir, --host, --port
4. `python -m klippbok.api --help` -- shows same args

## Next Phase Readiness

- Plan 02 (React frontend) can start immediately -- endpoints are stable
- The `klippbok/api/static/` directory is reserved for the React build output
- When `static/` exists, the SPA is automatically served as a catch-all
- `sse-starlette` is installed and ready for Phase 4 real-time progress events
