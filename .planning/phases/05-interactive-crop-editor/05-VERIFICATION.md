---
phase: 05-interactive-crop-editor
verified: 2026-03-03T20:00:00Z
status: passed
score: 10/10 truths verified
gaps:
  - truth: "auto_crop_image() detects a person in a photo and returns crop coordinates covering the body"
    status: resolved
    reason: "Tests updated to unpack 5 values (added detection_type). All 1152 tests pass. Commit 60f36c7."
human_verification:
  - test: "Interactive crop editor end-to-end"
    expected: "Crop rectangle snaps to bucket AR on resize release; CTRL+resize allows freeform; resolution readout color changes between green and red correctly; zoom slider, rotation, and flip controls respond correctly; Auto-crop All updates crop positions in all cards; Proceed to Captioning generates files in .klippbok/crops/"
    why_human: "Visual and interactive behavior (drag/resize, CTRL modifier key, real-time readout changes) cannot be verified programmatically"
---

# Phase 5: Interactive Crop Editor — Verification Report

**Phase Goal:** Build the interactive crop editor — the signature feature. Batch grid of crop cards with bucket-ratio snapping, upscale integration, and save-to-disk.
**Verified:** 2026-03-03T20:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can toggle selection mode in the gallery | VERIFIED | `SelectionToolbar.tsx` renders toggle button wired to `toggleSelectionMode()` in appStore; always visible |
| 2 | User can click thumbnails to select/deselect when selection mode is active | VERIFIED | `GalleryPage.tsx` switches `handleItemClick` to call `toggleImageSelection(item.id)` in selection mode; ThumbnailCard receives `isSelected`/`selectionMode` props |
| 3 | Smart filter helpers work (Select All, Deselect All, quality, duplicates) | VERIFIED | `SelectionToolbar.tsx` implements all 4 filter functions using `selectAll`, `deselectAll`, `selectByFilter` from appStore |
| 4 | Process button appears when >=1 image selected and navigates to /process | VERIFIED | `SelectionToolbar.tsx` line 68: `{selectedCount >= 1 && <button ... onClick={handleProcess}>}` where `handleProcess` calls `navigate('/process')` |
| 5 | Crop nav item in navbar; /crop and /process routes registered | VERIFIED | `NavBar.tsx` has Crop NavLink; `App.tsx` has `<Route path="/crop" element={<CropPage />} />` and `<Route path="/process" element={<ProcessPage />} />` |
| 6 | User sees scrollable grid of crop cards for all selected images | VERIFIED | `CropPage.tsx` renders `<div className="crop-grid">` with CropCard per selected image; responsive grid via CSS |
| 7 | Each card has react-advanced-cropper with bucket-ratio snapping and CTRL freeform | VERIFIED | `CropCard.tsx` imports `Cropper, RectangleStencil` from `react-advanced-cropper`; `stencilProps.aspectRatio` is `undefined` when `isCtrlHeld` (freeform) and `lockedAR` when not; `snapToBucket()` fires on CTRL release |
| 8 | Resolution readout shows green/red with arrow and AR badge; zoom/rotate/flip controls work per card | VERIFIED | `CropReadout.tsx` uses `needsUpscale()` to set color `#ef4444` (red) or `#22c55e` (green) with up/down arrow; `CropCard.tsx` has zoom slider (`cropperRef.zoomImage`), rotate CW/CCW (`rotateImage`), flip H/V (`flipImage`) |
| 9 | Auto-crop All calls backend and positions crop rectangles; user can adjust afterward | VERIFIED | `CropPage.tsx` `handleAutoCropAll()` POSTs to `/api/v1/crop/auto`; response updates `cropStates` in store; `autocropVersion` bump remounts CropCard with updated `initialCropState` so user can continue adjusting |
| 10 | auto_crop_image detects person, returns crop coordinates; center-crop fallback | FAILED | `auto_crop_image()` returns 5 values `(left, top, width, height, detection_type)`; `test_image_autocrop.py` unpacks only 4. Tests fail with `ValueError: too many values to unpack`. The function implementation is correct — the tests are stale. |

**Score: 9/10 truths verified**

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `frontend/src/types/crop.ts` | CropState, CropCoordinates, BucketSize types; generateBuckets, snapToNearestBucket, needsUpscale utilities | VERIFIED | 99 lines; all 3 functions and 4 types exported; substantive implementation with pixel-budget algorithm |
| `frontend/src/stores/appStore.ts` | Extended store with selectedImageIds Set and cropStates Map | VERIFIED | selectionMode, selectedImageIds, cropStates with all actions (toggleSelectionMode, toggleImageSelection, selectAll, deselectAll, selectByFilter, setCropState, removeCropState, clearCropStates) |
| `frontend/src/components/Gallery/SelectionToolbar.tsx` | Selection mode controls, smart filters, Process button | VERIFIED | 79 lines; all controls present and wired to store; navigates to /process |
| `frontend/src/App.tsx` | Routes for /crop and /process | VERIFIED | CropPage and ProcessPage imported; both routes registered inside AppLayout Route |
| `frontend/src/pages/CropPage.tsx` | Batch crop grid page with global controls and CTRL state management | VERIFIED | 330 lines; CTRL keydown/keyup listeners; BucketSelector; crop grid; handleAutoCropAll; handleProceedToCaptioning |
| `frontend/src/components/Crop/CropCard.tsx` | Per-image crop card with react-advanced-cropper, controls, readout | VERIFIED | 280 lines; Cropper with dynamic AR; rotate/flip/zoom; CropReadout; include/exclude buttons |
| `frontend/src/components/Crop/CropReadout.tsx` | Resolution display: green/red text, up/down arrow, AR badge | VERIFIED | Uses needsUpscale(); gcd-based AR formatting; correct colors |
| `frontend/src/components/Crop/BucketSelector.tsx` | Global bucket size dropdown + Allow Non-Square checkbox | VERIFIED | Select with 512/768/1024 options; checkbox for non-square |
| `klippbok/image/autocrop.py` | auto_crop_image() with MediaPipe PoseLandmarker and center-crop fallback | VERIFIED | Full implementation with PoseLandmarker Tasks API; _center_crop; _fit_crop_to_bucket; model discovery and download |
| `klippbok/services/crop_service.py` | apply_crop() Pillow-based crop+rotate+flip+resize; apply_crops_batch() | VERIFIED | Correct processing order (rotate → flip → crop → resize); LANCZOS resampling; RGB conversion |
| `klippbok/services/upscale_service.py` | detect_seedvr2(), detect_nmkd_siax(), start_upscale() | VERIFIED | Path detection with Windows/Linux venv support; PYTHONUNBUFFERED subprocess; threading stdout reader; cancel_upscale() |
| `klippbok/api/routers/crop.py` | POST /crop/apply, POST /crop/auto endpoints | VERIFIED | Both endpoints registered; path resolution from manifest; run_in_executor for CPU-bound work |
| `klippbok/api/routers/upscale.py` | POST /upscale/start, GET /upscale/{op_id}/events, GET /upscale/status | VERIFIED | SSE pattern matches import_ router; named events (progress/done/upscale_error); POST /{op_id}/cancel also added |
| `frontend/src/pages/ProcessPage.tsx` | Wizard-style page with step indicator and UpscaleStep | VERIFIED | StepIndicator component; renders UpscaleStep; navigates to /crop on complete/skip |
| `frontend/src/components/Crop/UpscaleStep.tsx` | Upscaler dropdown, scale factor, progress bar, skip button | VERIFIED | Fetches /upscale/status on mount; availability badges; start/cancel buttons; SSE progress bar; skip always visible |
| `frontend/src/hooks/useUpscaleEvents.ts` | SSE hook for upscale progress | VERIFIED | EventSource to /api/v1/upscale/{operationId}/events; listens for progress/done/upscale_error; cleanup on unmount |
| `tests/test_crop_service.py` | Tests for apply_crop dimensions, rotation, flip, RGB conversion | VERIFIED | 4 tests; all pass (9 passed in crop+upscale run) |
| `tests/test_image_autocrop.py` | Tests for auto_crop detection and center-crop fallback | PARTIAL STUB | 8 tests defined; 6 pass (pure-Python tests); 2 fail because tests unpack 4 values from auto_crop_image which now returns 5 |
| `tests/test_upscale_service.py` | Tests for detect_seedvr2 path detection | VERIFIED | 5 tests; all pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `frontend/src/pages/GalleryPage.tsx` | `frontend/src/stores/appStore.ts` | `useAppStore selectedImageIds` | WIRED | GalleryPage imports useAppStore and reads selectedImageIds for selection mode behavior |
| `frontend/src/components/Gallery/SelectionToolbar.tsx` | `/process` | `react-router navigate` | WIRED | `navigate('/process')` in handleProcess confirmed |
| `frontend/src/pages/CropPage.tsx` | `frontend/src/stores/appStore.ts` | `useAppStore selectedImageIds, cropStates` | WIRED | CropPage reads selectedImageIds and cropStates from store via useAppStore |
| `frontend/src/components/Crop/CropCard.tsx` | `react-advanced-cropper` | `Cropper, RectangleStencil` | WIRED | `import { Cropper, RectangleStencil } from 'react-advanced-cropper'` confirmed; `react-advanced-cropper@~0.20.1` in package.json |
| `frontend/src/components/Crop/CropCard.tsx` | `frontend/src/types/crop.ts` | `snapToNearestBucket` | WIRED | `import { snapToNearestBucket } from '../../types/crop'` and called in snapToBucket() and handleChange() |
| `frontend/src/pages/CropPage.tsx` | `/api/v1/crop/auto` | `fetch POST for auto-crop` | WIRED | `fetch('/api/v1/crop/auto', { method: 'POST', ... })` in handleAutoCropAll() |
| `frontend/src/pages/ProcessPage.tsx` | `/api/v1/upscale/start` | `fetch POST to start upscale` | WIRED | UpscaleStep.tsx handles start; ProcessPage passes selectedIds via prop |
| `frontend/src/pages/CropPage.tsx` | `/api/v1/crop/` | `fetch POST to save crops` | WIRED | `fetch('/api/v1/crop/', { method: 'POST', ... })` in handleProceedToCaptioning() |
| `frontend/src/hooks/useUpscaleEvents.ts` | `/api/v1/upscale/{op_id}/events` | `EventSource SSE subscription` | WIRED | `new EventSource('/api/v1/upscale/${operationId}/events')` confirmed |
| `klippbok/api/routers/crop.py` | `klippbok/services/crop_service.py` | `from klippbok.services.crop_service import` | WIRED | `from klippbok.services.crop_service import apply_crop` in apply_crops endpoint |
| `klippbok/api/routers/crop.py` | `klippbok/image/autocrop.py` | `from klippbok.image.autocrop import` | WIRED | `from klippbok.image.autocrop import _center_crop, auto_crop_image` in auto_crop endpoint |
| `klippbok/api/routers/upscale.py` | `klippbok/services/upscale_service.py` | `from klippbok.services.upscale_service import` | WIRED | `from klippbok.services.upscale_service import start_upscale` and `detect_seedvr2, detect_nmkd_siax` confirmed |
| `klippbok/api/app.py` | `klippbok/api/routers/crop.py` | `app.include_router` | WIRED | `app.include_router(crop_router, prefix="/api/v1")` at line 82; routes confirmed: `/api/v1/crop/`, `/api/v1/crop/auto` |
| `klippbok/api/app.py` | `klippbok/api/routers/upscale.py` | `app.include_router` | WIRED | `app.include_router(upscale_router, prefix="/api/v1")` at line 83; routes confirmed: `/api/v1/upscale/start`, `/api/v1/upscale/{op_id}/events`, etc. |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| CROP-01 | 05-03 | Interactive crop editor with draggable/resizable rectangle overlay | SATISFIED | CropCard.tsx uses react-advanced-cropper Cropper+RectangleStencil |
| CROP-02 | 05-03 | Crop rectangle snaps to nearest valid training AR on resize release | SATISFIED | snapToBucket() called in useEffect on isCtrlHeld change; snapToNearestBucket() updates lockedAR and stencilProps.aspectRatio |
| CROP-03 | 05-03 | CTRL+resize allows freeform, snaps to nearest valid bucket on key release | SATISFIED | isCtrlHeld lifted to CropPage; stencilProps.aspectRatio is undefined when CTRL held; snapToBucket fires when CTRL released |
| CROP-04 | 05-03, 05-04 | Real-time resolution display (green=downscale, red=upscale) | SATISFIED | CropReadout.tsx renders colored resolution text with arrows using needsUpscale() |
| CROP-05 | 05-03, 05-04 | Zoom slider for navigating high-resolution source images | SATISFIED | CropCard.tsx has range input mapped to cropperRef.zoomImage(factor) |
| CROP-06 | 05-03 | Rotation controls (90-degree) and H/V flip | SATISFIED | handleRotateCW/CCW call rotateImage(90)/rotateImage(-90); handleFlipH/V call flipImage() |
| CROP-07 | 05-02 | Auto-crop with subject detection places crop on detected subject | SATISFIED | auto_crop_image() uses MediaPipe PoseLandmarker Tasks API; backend returns pose-detected coords |
| CROP-08 | 05-02 | Auto-crop falls back to center crop when no subject detected | SATISFIED | _center_crop() called when result.pose_landmarks is empty or detection fails |
| CROP-09 | 05-03 | User can adjust auto-crop result via interactive crop editor | SATISFIED | Auto-crop sets initialCropState via store; CropCard remounts with updated coordinates but user can drag/resize freely |
| GUI-05 | 05-01 | Crop editor accessible from gallery | SATISFIED | SelectionToolbar Process button navigates to /process which leads to /crop; Crop link in NavBar for direct access |

All 10 Phase 5 requirements (CROP-01 through CROP-09, GUI-05) are satisfied at the implementation level.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/test_image_autocrop.py` | 159, 196 | Stale test: unpacks 4 values from function that returns 5 | BLOCKER | `test_auto_crop_center_fallback` and `test_auto_crop_coords_in_bounds` fail with `ValueError: too many values to unpack`. The implementation is correct (returns detection_type as 5th value); only the tests are wrong. |

---

### Human Verification Required

#### 1. Interactive Crop Rectangle Behavior

**Test:** Navigate to Gallery, enter Select Mode, select 2-3 images, click Process, skip upscaling, arrive at /crop. Drag and resize the crop rectangle on a card.
**Expected:** Rectangle is draggable; on resize release (without CTRL), the rectangle snaps to a bucket aspect ratio (visible as a proportional jump). Hold CTRL while resizing — rectangle can be any proportion. Release CTRL — rectangle snaps to nearest bucket.
**Why human:** Drag-and-resize behavior, snap timing, and CTRL modifier are interactive events that cannot be verified by reading code.

#### 2. Resolution Readout Color Accuracy

**Test:** On the crop page, adjust a crop rectangle so the crop region is smaller than the target bucket (e.g., crop 400x400 on a 500x500 image targeting 1024x1024).
**Expected:** Resolution readout shows red text with up-arrow and the bucket dimensions (upscale required). Resize to cover the full image at a downscale bucket — readout turns green with down-arrow.
**Why human:** Color response depends on needsUpscale() logic applied to live crop coordinates from the cropper instance.

#### 3. Upscale SSE Progress

**Test:** If SeedVR2 or NMKD-Siax is available, start an upscale from the Process page.
**Expected:** Progress bar advances in real time showing N/M images; on completion the UI auto-advances to /crop.
**Why human:** Requires external upscaler installation and real subprocess execution; SSE streaming behavior cannot be verified statically.

#### 4. Proceed to Captioning File Output

**Test:** After cropping, click "Proceed to Captioning". Check `.klippbok/crops/` in the project directory.
**Expected:** Cropped images appear in `.klippbok/crops/` at exact target bucket dimensions (e.g., 1024x768). Toast message confirms save count.
**Why human:** File system output requires a real project directory and running server.

---

### Gaps Summary

**One gap is blocking the test suite.** Two tests in `tests/test_image_autocrop.py` fail because they unpack `auto_crop_image()` as returning 4 values while the actual function returns 5 (added `detection_type` as the 5th return value). This is a test/implementation mismatch — the implementation is correct (the API router correctly uses the 5-tuple), but the tests were written to the old 4-value contract and were not updated when the return signature was expanded.

The fix is a one-line change per test: replace `left, top, width, height = auto_crop_image(...)` with `left, top, width, height, _detection_type = auto_crop_image(...)`.

All other phase 5 artifacts are fully implemented, substantive (not stubs), and correctly wired. The interactive crop editor, batch grid, bucket snapping, upscale pipeline, and save-to-disk action are all present and connected.

---

*Verified: 2026-03-03*
*Verifier: Claude (gsd-verifier)*
