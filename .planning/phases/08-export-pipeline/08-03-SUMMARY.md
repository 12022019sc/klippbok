---
phase: 08-export-pipeline
plan: "03"
subsystem: export-api-and-gui
tags: [export, api, frontend, sse, fastapi, react, typescript]
dependency_graph:
  requires: ["08-01"]
  provides: ["export-api-router", "export-page-frontend"]
  affects: ["klippbok/api/app.py", "frontend/src/App.tsx", "frontend/src/components/Layout/NavBar.tsx"]
tech_stack:
  added: []
  patterns: ["asyncio.Queue SSE pattern", "EventSource hook", "TDD red-green"]
key_files:
  created:
    - klippbok/api/routers/export.py
    - tests/test_export_api.py
    - frontend/src/pages/ExportPage.tsx
    - frontend/src/components/Export/TrainerPicker.tsx
    - frontend/src/components/Export/ExportOptions.tsx
    - frontend/src/components/Export/ExportSummary.tsx
    - frontend/src/components/Export/ExportProgress.tsx
    - frontend/src/hooks/useExportEvents.ts
  modified:
    - klippbok/api/app.py
    - frontend/src/App.tsx
    - frontend/src/components/Layout/NavBar.tsx
    - frontend/src/App.css
decisions:
  - "EXPT-SSE-01: Export router uses asyncio.Queue per op_id with None sentinel, mirrors cleanup.py pattern exactly"
  - "EXPT-OPID-01: op_id uses uuid4().hex[:8] (8-char hex) — consistent with plan spec"
  - "EXPT-NAV-01: Export NavLink inserted between Triage and Settings — pipeline endpoint position"
  - "EXPT-OT-RECOMMENDED: OneTrainer set as default selected trainer and badged Recommended"
metrics:
  duration: 418
  completed_date: "2026-03-10"
  tasks_completed: 2
  files_created: 8
  files_modified: 4
---

# Phase 8 Plan 3: Export API and Frontend Summary

**One-liner:** Export API router with asyncio SSE progress and ExportPage frontend (trainer picker, options form, caption validation warnings, SSE progress bar).

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Export API router with SSE progress + integration tests | aa7baad (test), 546e920 (feat) | export.py, app.py, test_export_api.py |
| 2 | ExportPage frontend with trainer picker, options, validation, SSE progress | 44c40e2 | ExportPage.tsx, 4 Export/ components, useExportEvents.ts, App.tsx, NavBar.tsx, App.css |

## What Was Built

### Export API Router (`klippbok/api/routers/export.py`)

Five endpoints following the cleanup.py SSE pattern exactly:

- `GET /api/v1/export/defaults` — returns model-aware defaults (trigger_word from manifest anchor_word, resolution from active_profile)
- `GET /api/v1/export/validate` — returns `{candidates: N, issues: [...]}` pre-flight check for missing/empty captions
- `POST /api/v1/export/start` — creates op_id (uuid4 hex[:8]), asyncio.Queue, background task; returns `{op_id}`
- `GET /api/v1/export/{op_id}/events` — SSE stream (export_progress, export_done, export_error events)
- `POST /api/v1/export/{op_id}/cancel` — graceful task cancellation

The background task (`_run_export_bg`) runs `perform_export()` in `run_in_executor` with a thread-safe progress callback via `loop.call_soon_threadsafe`.

### Integration Tests (`tests/test_export_api.py`)

12 tests covering all endpoints: TDD red-green cycle. Tests mock `perform_export` for the start endpoint to avoid real file I/O. Validates: defaults reflect manifest anchor_word, validate counts only crop-source entries, start returns op_id, cancel 404s on unknown op, router registered (not 404, returns JSON not index.html).

### Frontend ExportPage (`frontend/src/pages/ExportPage.tsx`)

Single-page layout (not wizard) with four sections:

1. **TrainerPicker** — three cards: kohya/sd-scripts, ai-toolkit, OneTrainer (highlighted as Recommended). Default selection: OneTrainer.
2. **ExportOptions** — form with repeats, trigger word, class name, concept name (shown for onetrainer/aitoolkit), output path. Output path default updates when trainer changes.
3. **ExportSummary** — shows candidate count (cropped images only), caption issues warning panel with issue list + "Proceed anyway" / "Go fix captions" link to /caption, empty state guides to /crop.
4. **ExportProgress** — shown during/after export: SSE progress bar with current/total, success banner with image count + output dir + config path, error display.

Fetches `/api/v1/export/defaults` on mount to pre-fill trigger_word from project anchor_word. Fetches `/api/v1/export/validate` to drive summary. Export button disabled when: no candidates, validating, exporting, or issues exist and user hasn't clicked "Proceed anyway".

### `useExportEvents` Hook (`frontend/src/hooks/useExportEvents.ts`)

EventSource to `/api/v1/export/{opId}/events`. Handles export_progress (updates current/total), export_done (sets result with image_count, config_path, output_dir), export_error (sets error string). Returns `{progress, result, error, isExporting}`.

### App Registration

- Router registered in `klippbok/api/app.py` before StaticFiles mount (API-03 convention), export tasks cancelled in lifespan shutdown.
- Route `/export` added to `App.tsx`.
- Export NavLink added to NavBar between Triage and Settings.
- CSS added to App.css for all export components.

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check

### Files Created/Modified

- `klippbok/api/routers/export.py` — FOUND
- `tests/test_export_api.py` — FOUND
- `frontend/src/pages/ExportPage.tsx` — FOUND
- `frontend/src/components/Export/TrainerPicker.tsx` — FOUND
- `frontend/src/components/Export/ExportOptions.tsx` — FOUND
- `frontend/src/components/Export/ExportSummary.tsx` — FOUND
- `frontend/src/components/Export/ExportProgress.tsx` — FOUND
- `frontend/src/hooks/useExportEvents.ts` — FOUND

### Test Results

- `pytest tests/test_export_api.py -q`: 12 passed
- `python -c "from klippbok.api.routers.export import router"`: OK
- `npx tsc --noEmit`: 0 errors

## Self-Check: PASSED
