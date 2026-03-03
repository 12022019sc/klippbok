---
phase: 05-interactive-crop-editor
plan: "04"
subsystem: ui
tags: [react, typescript, sse, eventsource, process-wizard, upscale, crop-save]

requires:
  - phase: 05-02
    provides: "POST /api/v1/upscale/start, GET /api/v1/upscale/{op_id}/events, GET /api/v1/upscale/status, POST /api/v1/crop/"
  - phase: 05-03
    provides: "CropPage, CropCard, BucketSelector, react-advanced-cropper integration"

provides:
  - "useUpscaleEvents SSE hook -- subscribes to /api/v1/upscale/{op_id}/events with progress/done/upscale_error events"
  - "UpscaleStep component -- upscaler detection status, selection dropdowns, progress bar, skip button"
  - "ProcessPage wizard -- step indicator (Upscale -> Crop -> Save), navigates to /crop on complete/skip"
  - "CropPage Proceed to Captioning -- POSTs all included crop states to /api/v1/crop/, saves images to .klippbok/crops/"
  - "Full pipeline: Gallery select -> /process (upscale) -> /crop (edit) -> save -> gallery"

affects:
  - 06-captioning
  - 07-video-clip

tech-stack:
  added: []
  patterns:
    - "useUpscaleEvents mirrors useImportEvents pattern -- same SSE 3-event shape (progress/done/error)"
    - "ProcessPage as upscale entry point only -- navigate('/crop') for step 2 keeps pages cleanly separated"
    - "Wizard step indicator with circle states (active/done/pending) reused pattern"

key-files:
  created:
    - frontend/src/hooks/useUpscaleEvents.ts
    - frontend/src/components/Crop/UpscaleStep.tsx
    - frontend/src/pages/ProcessPage.tsx
  modified:
    - frontend/src/pages/CropPage.tsx
    - frontend/src/index.css

key-decisions:
  - "05-04 PROC-01: ProcessPage is upscale entry only -- navigate('/crop') on complete/skip, no inline crop embedding"
  - "05-04 PROC-02: useUpscaleEvents resets state on operationId change -- prevents stale progress across retries"
  - "05-04 PROC-03: CropPage Proceed to Captioning uses /api/v1/crop/ (trailing slash) -- matches FastAPI router prefix"
  - "05-04 UPS-03: Cancel upscale button calls /api/v1/upscale/{op_id}/cancel -- graceful subprocess termination"

patterns-established:
  - "SSE hook pattern: useEffect with EventSource, addEventListener for named events, cleanup on unmount/operationId change"
  - "Wizard page pattern: separate page for each step, navigate() to transition between steps"

requirements-completed: [CROP-04, CROP-05]

duration: ~8min
completed: 2026-03-03
---

# Phase 5 Plan 04: Process Wizard and Crop Save Action Summary

**ProcessPage upscale wizard with SeedVR2/NMKD-Siax detection + SSE progress, UpscaleStep component, useUpscaleEvents hook, and CropPage "Proceed to Captioning" save action completing the full select->upscale->crop->save pipeline**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-03T19:07:47Z
- **Completed:** 2026-03-03T19:15:00Z
- **Tasks:** 2 of 3 (Task 3 is checkpoint:human-verify, awaiting user)
- **Files modified:** 5

## Accomplishments

- ProcessPage wizard with 3-step indicator (Upscale -> Crop -> Save), renders UpscaleStep and navigates to /crop on complete or skip
- useUpscaleEvents SSE hook mirrors useImportEvents pattern -- connects to /api/v1/upscale/{op_id}/events, parses progress/done/upscale_error named events
- UpscaleStep component with on-mount status fetch (SeedVR2 / NMKD-Siax availability), upscaler dropdown, scale factor selector, real-time progress bar, cancel button, and skip button
- CropPage "Proceed to Captioning" button -- collects all included crop states, POSTs to /api/v1/crop/, shows success/error toast, navigates to gallery on success
- Frontend built and deployed to klippbok/api/static/

## Task Commits

1. **Task 1: UpscaleStep component and useUpscaleEvents SSE hook** - `50ad2f3` (feat)
2. **Task 2: ProcessPage wizard and crop save action** - `58f6420` (feat)
3. **Task 3: Verify complete crop editor pipeline** - checkpoint:human-verify (pending)

## Files Created/Modified

- `frontend/src/hooks/useUpscaleEvents.ts` - SSE hook for upscale progress (current/total/message/status/isComplete/error)
- `frontend/src/components/Crop/UpscaleStep.tsx` - Step 1 of wizard: upscaler detection, controls, progress bar, skip
- `frontend/src/pages/ProcessPage.tsx` - Wizard entry page with step indicator, renders UpscaleStep
- `frontend/src/pages/CropPage.tsx` - Added handleProceedToCaptioning (POST /api/v1/crop/), proceed button row
- `frontend/src/index.css` - Added .upscale-step, .upscaler-status, .upscale-controls, .process-page, .process-steps, .proceed-button CSS

## Decisions Made

- ProcessPage is the upscale entry point only -- navigate('/crop') for step 2 keeps pages cleanly separated (no inline embedding)
- useUpscaleEvents resets state on operationId change to prevent stale progress showing across retries
- Proceed to Captioning uses /api/v1/crop/ with trailing slash to match FastAPI router prefix
- Cancel upscale added as deviation Rule 2 (missing critical) -- graceful subprocess termination via POST /api/v1/upscale/{op_id}/cancel

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added Cancel Upscale button**
- **Found during:** Task 1 (UpscaleStep component)
- **Issue:** Plan did not specify a cancel button for in-progress upscale operations. Without it, users have no way to stop a long-running upscale other than killing the server.
- **Fix:** Added handleCancel function calling POST /api/v1/upscale/{op_id}/cancel, with isCancelling state and Cancel Upscale button visible during progress
- **Files modified:** frontend/src/components/Crop/UpscaleStep.tsx, frontend/src/index.css
- **Verification:** TypeScript compiles, button renders during progress state
- **Committed in:** 50ad2f3 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Cancel button is essential for UX correctness -- upscale can take minutes per image. No scope creep.

## Issues Encountered

None -- both tasks executed cleanly. TypeScript compiled without errors on first attempt.

## User Setup Required

**External services require manual configuration.** SeedVR2 and NMKD-Siax upscalers are optional:
- Set `SEEDVR2_PATH` env var if SeedVR2 not at default `C:\GenAI\Tools\SeedVR2`
- NMKD-Siax requires `realesrgan-ncnn-vulkan` on PATH
- Both show detection status on the Process page if unavailable

## Next Phase Readiness

- Full crop pipeline complete: Gallery (select) -> Process (upscale) -> Crop (edit) -> Save (generate files)
- .klippbok/crops/ directory populated with bucket-resized output images after save
- Phase 6 (Captioning) can consume images from .klippbok/crops/ -- pipeline handoff point established
- Awaiting: human end-to-end verification of complete pipeline (Task 3 checkpoint)

---
*Phase: 05-interactive-crop-editor*
*Completed: 2026-03-03*

## Self-Check: PASSED

- FOUND: frontend/src/hooks/useUpscaleEvents.ts
- FOUND: frontend/src/components/Crop/UpscaleStep.tsx
- FOUND: frontend/src/pages/ProcessPage.tsx
- FOUND: frontend/src/pages/CropPage.tsx
- FOUND: .planning/phases/05-interactive-crop-editor/05-04-SUMMARY.md
- FOUND commit: 50ad2f3 (Task 1)
- FOUND commit: 58f6420 (Task 2)
