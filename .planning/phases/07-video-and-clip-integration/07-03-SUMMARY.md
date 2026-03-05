---
phase: 07-video-and-clip-integration
plan: "03"
subsystem: video-frontend
tags: [video, frontend, react, sse, navigation, tabs]
dependency_graph:
  requires:
    - klippbok/api/routers/video.py (07-01: SSE ingest/extract endpoints)
    - frontend/src/hooks/useUpscaleEvents.ts (SSE hook pattern reference)
    - frontend/src/stores/appStore.ts (Zustand store extension)
  provides:
    - frontend/src/types/video.ts
    - frontend/src/hooks/useIngestEvents.ts
    - frontend/src/hooks/useExtractEvents.ts
    - frontend/src/pages/VideoPage.tsx
    - frontend/src/pages/TriagePage.tsx (stub)
  affects:
    - frontend/src/components/Layout/NavBar.tsx (Video + Triage nav items)
    - frontend/src/App.tsx (video + triage routes)
    - frontend/src/stores/appStore.ts (galleryFilter state)
tech_stack:
  added: []
  patterns:
    - SSE via EventSource named event listeners (ingest_progress/ingest_done/ingest_error)
    - Tab layout with local useState activeTab (no CSS framework)
    - Per-operation SSE hook with reset-on-operationId-change (05-04 PROC-02 pattern)
key_files:
  created:
    - frontend/src/types/video.ts
    - frontend/src/hooks/useIngestEvents.ts
    - frontend/src/hooks/useExtractEvents.ts
    - frontend/src/pages/VideoPage.tsx
    - frontend/src/pages/TriagePage.tsx
  modified:
    - frontend/src/stores/appStore.ts
    - frontend/src/components/Layout/NavBar.tsx
    - frontend/src/App.tsx
decisions:
  - "[07-03 NAV-01]: Process removed from NavBar — reached via CropPage navigation only, not a top-level destination"
  - "[07-03 INGEST-01]: Ingest input mode defaults to Directory Path (not Upload) — large raw footage is typically on disk already per locked decision"
  - "[07-03 TRIAGE-STUB-01]: TriagePage created as minimal stub so /triage route resolves without 404; full implementation in Plan 04"
metrics:
  duration: 258s
  completed_date: "2026-03-05"
  tasks_completed: 2
  files_changed: 8
---

# Phase 7 Plan 3: VideoPage Frontend Summary

VideoPage with three-tab layout (Ingest/Scan/Extract), SSE hooks for ingest and extract progress, and updated navigation including Video and Triage items in the locked nav order.

## What Was Built

**video.ts types** — TypeScript interfaces for all video operations: `IngestConfig`, `IngestProgress`, `ExtractProgress`, `ScanResultItem`, `ScanResult`, `VideoClip`.

**useIngestEvents hook** — SSE hook following the `useUpscaleEvents` pattern. Connects to `/api/v1/video/ingest/{operationId}/events`, handles `ingest_progress`, `ingest_done`, `ingest_error` named events. Resets state on operationId change per [05-04 PROC-02].

**useExtractEvents hook** — Same pattern for frame extraction. Connects to `/api/v1/video/extract/{operationId}/events`, handles `extract_progress`, `extract_done`, `extract_error` events.

**appStore extension** — Added `galleryFilter: 'all' | 'images' | 'videos'` and `setGalleryFilter` action. Flat store shape per [04-02] Zustand flat pattern.

**VideoPage.tsx** — Three-tab layout:
- Ingest tab: toggle between Directory Path and Upload Video input modes, smart defaults (fps=16, resolution=720p displayed), Advanced toggle revealing threshold/max_frames/fps/resolution overrides, Start Ingest button, SSE progress bar with stage label + percentage + count, Cancel button, success message with clip count and quick-navigate to Scan tab
- Scan tab: fetches `/api/v1/video/scan` on tab activation, displays table of clips (filename, resolution, fps, duration, codec, frame count, issues in red), Refresh button, empty state message, auto-invalidates scan cache after ingest completes
- Extract tab: frames_per_clip input (default 1), Extract Frames button, SSE progress bar with cancel, thumbnail grid of extracted clips from `/api/v1/video/clips`

**NavBar.tsx** — Updated to locked order: Gallery > Import > Video > Crop > Caption > Triage > Settings. Process removed (reached via CropPage navigation).

**App.tsx** — Added `/video` and `/triage` routes inside the AppLayout wrapper.

**TriagePage.tsx** — Minimal stub rendering "Triage page — coming soon" so the route resolves.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Notes

The `klippbok/api/static/` directory is gitignored (build output). The frontend was built and deployed to that directory as part of Task 2 execution, but the static files are not tracked in git. This is correct behavior.

The linter added triage state to `appStore.ts` (`triageResults`, `triageThreshold`, `setTriageResults`, `setTriageThreshold`, `clearTriageResults`) alongside the `galleryFilter` additions. This is from Plan 04 work that has already been committed — the linter picked it up from the existing file. The galleryFilter additions from this plan are present and correct.

## Self-Check: PASSED

All created files verified on disk:
- FOUND: frontend/src/types/video.ts
- FOUND: frontend/src/hooks/useIngestEvents.ts
- FOUND: frontend/src/hooks/useExtractEvents.ts
- FOUND: frontend/src/pages/VideoPage.tsx
- FOUND: frontend/src/pages/TriagePage.tsx
- FOUND: frontend/src/components/Layout/NavBar.tsx (modified)
- FOUND: frontend/src/App.tsx (modified)
- FOUND: frontend/src/stores/appStore.ts (modified)

Commits verified:
- fe0f82e: feat(07-03): add video types, SSE hooks, and appStore galleryFilter
- 6f49d7d: feat(07-03): VideoPage with Ingest/Scan/Extract tabs, nav and route wiring
