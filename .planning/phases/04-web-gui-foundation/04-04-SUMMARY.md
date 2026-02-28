---
phase: 04-web-gui-foundation
plan: 04
subsystem: api, ui
tags: [fastapi, sse, eventsource, asyncio, react, zustand, sonner, tanstack-query]

# Dependency graph
requires:
  - phase: 04-01
    provides: FastAPI app factory, images router, sse-starlette installed
  - phase: 04-02
    provides: React SPA scaffold, Zustand appStore with importOperationId/importProgress, TanStack Query

provides:
  - POST /api/v1/import/ starts batch import background asyncio task, returns operation_id
  - GET /api/v1/import/{op_id}/events SSE stream with named events (progress, done, import_error)
  - GET /api/v1/settings/ reads project_dir and active_profile from manifest
  - PUT /api/v1/settings/ stub that returns updated settings (Phase 4)
  - useImportEvents hook consuming SSE with addEventListener per named event type
  - ImportPage with directory input, recursive toggle, progress bar
  - SettingsPage reading project settings via TanStack Query
  - ToastProvider (sonner) at app root; persistent import toast in AppLayout

affects:
  - 04-05 (gallery page enhancements may trigger imports)
  - 05-crop-editor (crop flow triggers re-import or update)
  - 06-captioning (caption workflow may use import pipeline)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - asyncio.Queue per operation for SSE event bus (producer/consumer decoupling)
    - Module-level _queues/_tasks dicts for in-flight import state (process-local)
    - lifespan context manager for graceful asyncio task cancellation on shutdown
    - Named SSE events via ServerSentEvent(data, event=...) from sse-starlette
    - addEventListener on EventSource for each named event type (not onmessage)
    - Stable toast ID "import-progress" for in-place toast.loading() updates
    - useEffect in AppLayout drives persistent cross-page toast from zustand store

key-files:
  created:
    - klippbok/api/routers/import_.py
    - klippbok/api/routers/settings.py
    - frontend/src/hooks/useImportEvents.ts
    - frontend/src/components/Layout/ToastProvider.tsx
  modified:
    - klippbok/api/models.py
    - klippbok/api/app.py
    - frontend/src/main.tsx
    - frontend/src/pages/ImportPage.tsx
    - frontend/src/pages/SettingsPage.tsx
    - frontend/src/components/Layout/AppLayout.tsx
    - frontend/src/App.css

key-decisions:
  - "import_error SSE event name used (not 'error') to avoid collision with EventSource built-in error handling"
  - "asyncio.Queue per operation_id as SSE event bus -- decouples background task from SSE stream"
  - "_run_import uses run_in_executor for batch_import_images (synchronous CPU-bound) to keep event loop responsive"
  - "lifespan context manager cancels all _tasks on app shutdown to prevent resource leaks"
  - "Stable toast ID 'import-progress' allows AppLayout to update existing toast in-place across page navigations"
  - "Settings PUT is a stub in Phase 4 -- returns updated settings without persisting"

patterns-established:
  - "SSE router pattern: asyncio.Queue producer/consumer with named event types via ServerSentEvent"
  - "Persistent cross-page toast: useEffect in AppLayout reads zustand importOperationId/importProgress"
  - "useImportEvents uses addEventListener not onmessage -- required for named event type routing"

# Metrics
duration: 3min
completed: 2026-02-28
---

# Phase 4 Plan 04: Import API, SSE streaming, settings page, and toast notifications Summary

**Batch import triggered via POST /api/v1/import with asyncio background task; progress streamed as named SSE events (progress/done/import_error); import page, settings page, sonner toast system, and persistent cross-page import progress toast.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-02-28T17:14:57Z
- **Completed:** 2026-02-28T17:18:14Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments

- Import router: POST /api/v1/import starts asyncio background task wrapping synchronous batch_import_images in run_in_executor; GET /api/v1/import/{op_id}/events streams named SSE events via sse-starlette ServerSentEvent
- Settings router: GET reads project_dir + active_profile from manifest, PUT is a Phase 4 stub
- useImportEvents hook uses addEventListener for "progress", "done", "import_error" named events; updates zustand, toasts on done/error, invalidates images query
- ImportPage: directory text input, recursive checkbox, Start Import button with disabled state, inline progress bar showing current/total/message
- SettingsPage: TanStack Query fetch of /api/v1/settings, displays project_dir (monospace) and active_profile or "None selected"
- Persistent import toast in AppLayout using stable toast ID "import-progress" visible across all pages

## Task Commits

1. **Task 1: Import router with SSE progress and settings router** - `4e95c9a` (feat)
2. **Task 2: Import page, settings page, SSE hook, and toast notifications** - `991dc6e` (feat)

## Files Created/Modified

- `klippbok/api/routers/import_.py` - POST /api/v1/import, GET /api/v1/import/{op_id}/events with named SSE events
- `klippbok/api/routers/settings.py` - GET/PUT /api/v1/settings
- `klippbok/api/models.py` - Added ImportRequest, ImportStarted, ImportProgress, SettingsResponse, SettingsUpdate
- `klippbok/api/app.py` - Registered import_ and settings routers; added lifespan for task cancellation
- `frontend/src/hooks/useImportEvents.ts` - EventSource SSE hook with addEventListener per named event
- `frontend/src/components/Layout/ToastProvider.tsx` - Sonner Toaster at app root
- `frontend/src/pages/ImportPage.tsx` - Directory input, recursive toggle, progress display
- `frontend/src/pages/SettingsPage.tsx` - TanStack Query settings fetch and display
- `frontend/src/components/Layout/AppLayout.tsx` - Persistent import toast via zustand store
- `frontend/src/main.tsx` - Added ToastProvider to render tree
- `frontend/src/App.css` - Import form, progress bar, settings panel CSS

## Decisions Made

- **import_error event name**: Used "import_error" not "error" to avoid collision with EventSource's built-in `onerror` -- the browser's "error" event fires on network failures, not custom data events
- **asyncio.Queue per operation**: Each import gets its own Queue to decouple the background task (producer) from the SSE stream (consumer); sentinel None signals end of stream
- **run_in_executor for batch_import_images**: batch_import_images is synchronous/CPU-bound; running it directly in the async event loop would block all requests
- **lifespan context manager**: Cancels all in-flight _tasks on shutdown to prevent asyncio resource leaks when the server exits
- **Stable toast ID**: Using toast.loading(..., { id: 'import-progress' }) allows AppLayout to update the same toast in-place as the user navigates pages -- new toasts would stack
- **Settings PUT stub**: Profile persistence requires reading/writing the project manifest which is a separate concern; stubbed for Phase 4 correctness

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Import flow end-to-end is complete: POST start -> SSE stream -> zustand state -> toast notification -> query invalidation
- Settings page ready for profile selection UI in Phase 6 (just needs PUT to persist)
- Phase 4 Plan 05 (gallery enhancements) can proceed independently
- Blocker noted from research: react-advanced-cropper custom stencil spike needed before Phase 5

---
*Phase: 04-web-gui-foundation*
*Completed: 2026-02-28*
