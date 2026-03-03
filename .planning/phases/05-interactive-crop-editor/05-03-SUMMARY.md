---
phase: 05-interactive-crop-editor
plan: 03
subsystem: ui
tags: [react, typescript, react-advanced-cropper, crop, bucket-snapping, zustand]

# Dependency graph
requires:
  - phase: 05-interactive-crop-editor/05-01
    provides: CropState, CropCoordinates, BucketSize types, generateBuckets, snapToNearestBucket, needsUpscale utilities, appStore cropStates/selectedImageIds, /crop route stub
  - phase: 05-interactive-crop-editor/05-02
    provides: POST /api/v1/crop/auto endpoint returning AutoCropResult[]
  - phase: 04-web-gui-foundation
    provides: GalleryItem type, useImages hook, dark theme CSS, appStore pattern
provides:
  - CropPage: full batch crop editor with sticky global controls bar and responsive grid
  - CropCard: per-image crop card with react-advanced-cropper, dynamic bucket AR, rotation/flip/zoom
  - CropReadout: green/red resolution indicator (up/down arrow) with GCD-computed AR badge
  - BucketSelector: bucket size dropdown (512/768/1024) + Allow Non-Square checkbox
  - CTRL key state lifted to CropPage level (shared across all cards)
  - Auto-crop All button calling POST /api/v1/crop/auto and updating card positions
  - CSS styles for all crop editor components in index.css
affects: [05-04-process-page, 06-captioning]

# Tech tracking
tech-stack:
  added:
    - react-advanced-cropper ~0.20.1 (pinned with ~ per RESEARCH Pitfall 1; installed with --legacy-peer-deps for React 19 compatibility)
  patterns:
    - CTRL state lifted to page level: isCtrlHeld prop passed down to all CropCards from CropPage keydown/keyup listeners
    - Bucket AR snap on CTRL release: useEffect watches isCtrlHeld, calls snapToNearestBucket on false transition
    - Each CropCard has its own Cropper ref instance (anti-pattern: never share a single cropper across cards)
    - Default center crop initialization: on first load, compute center crop at first bucket AR for images without existing CropState

key-files:
  created:
    - frontend/src/components/Crop/CropCard.tsx
    - frontend/src/components/Crop/CropReadout.tsx
    - frontend/src/components/Crop/BucketSelector.tsx
  modified:
    - frontend/src/pages/CropPage.tsx (replaced stub with full implementation)
    - frontend/src/index.css (added all crop editor CSS classes)
    - frontend/package.json (added react-advanced-cropper ~0.20.1)

key-decisions:
  - "05-03 CTRL-01: isCtrlHeld lifted to CropPage level -- passed as prop to all CropCards -- all cards snap simultaneously on CTRL release (desired batch behavior)"
  - "05-03 AR-01: Bucket AR snap triggered in useEffect watching isCtrlHeld transition to false -- avoids per-pixel-move thrashing (only snaps on CTRL release, not during drag)"
  - "05-03 INIT-01: Default center crop initialized at first bucket AR in CropPage useEffect for images without existing CropState -- non-destructive on re-render"
  - "05-03 PKG-01: react-advanced-cropper installed with --legacy-peer-deps for React 19 compatibility; library core does not use deprecated React APIs"

patterns-established:
  - "Pattern: Each CropCard has its own cropperRef (useRef<CropperRef>) -- never share a single Cropper instance across grid cards"
  - "Pattern: Page-level document event listeners for modifier keys (CTRL) with cleanup on unmount -- cropper component does not expose keyboard modifier state"
  - "Pattern: Crop state propagation via onCropChange callback up to CropPage which writes to appStore.cropStates Map"

requirements-completed: [CROP-01, CROP-02, CROP-03, CROP-04, CROP-05, CROP-06, CROP-09]

# Metrics
duration: 8min
completed: 2026-03-03
---

# Phase 5 Plan 03: Interactive Crop Editor UI Summary

**react-advanced-cropper batch grid with dynamic bucket-AR snapping, CTRL freeform mode, per-card rotation/flip/zoom, green/red resolution readout, and auto-crop All integration**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-03T18:58:50Z
- **Completed:** 2026-03-03T19:07:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Installed `react-advanced-cropper@~0.20.1` with React 19 compatibility (`--legacy-peer-deps`); pinned with `~` per RESEARCH Pitfall 1 to avoid API instability
- `CropCard`: per-image interactive crop card with `Cropper+RectangleStencil`, dynamic `aspectRatio` prop (locked to bucket AR by default, `undefined` when CTRL held for freeform), rotation CW/CCW (`rotateImage(±90)`), flip H/V (`flipImage`), zoom slider (`zoomImage`), include/exclude footer buttons
- `CropReadout`: resolution display with green (#22c55e) + down-arrow for downscale OK, red (#ef4444) + up-arrow for upscale risk, GCD-computed AR badge (e.g. "1:1", "3:4")
- `BucketSelector`: global bucket size dropdown (512/768/1024, default 1024) + Allow Non-Square checkbox (checked by default)
- `CropPage`: replaced stub -- sticky controls bar, responsive CSS grid (`auto-fill minmax(320px, 1fr)`, max 4 columns), CTRL state from document-level listeners, center crop initialization, Auto-crop All calling `POST /api/v1/crop/auto`, empty state with Gallery link

## Task Commits

Each task was committed atomically:

1. **Task 1: Install react-advanced-cropper, build CropCard and CropReadout** - `6396cd7` (feat)
2. **Task 2: CropPage with batch grid, CTRL state, and auto-crop integration** - `7f9da45` (feat)

## Files Created/Modified
- `frontend/src/components/Crop/CropCard.tsx` - Per-image crop card: react-advanced-cropper Cropper with RectangleStencil, dynamic AR, rotate/flip/zoom controls, include/exclude footer
- `frontend/src/components/Crop/CropReadout.tsx` - Resolution indicator: green/red text, up/down arrow, GCD-based AR badge
- `frontend/src/components/Crop/BucketSelector.tsx` - Bucket size dropdown + Allow Non-Square checkbox
- `frontend/src/pages/CropPage.tsx` - Full batch crop editor: replaced stub -- sticky controls, responsive grid, CTRL state, auto-crop, empty state
- `frontend/src/index.css` - All crop editor CSS: crop-card, crop-card-header, crop-readout, crop-controls, crop-card-footer, crop-page-controls, crop-grid, bucket-selector
- `frontend/package.json` - Added react-advanced-cropper ~0.20.1

## Decisions Made
- `isCtrlHeld` is a single boolean lifted to CropPage and passed as prop -- all cards share the same CTRL state so CTRL release causes all cards to snap simultaneously (batch behavior matches spec)
- Bucket AR snap uses `useEffect` watching `isCtrlHeld` (not `onChange`) -- snap only fires on CTRL release, not on every pixel drag (avoids thrashing)
- Default center crop computed at page level in `useEffect` -- only initializes images that don't yet have a `CropState` in the store (non-destructive on re-render)
- `--legacy-peer-deps` used for installation since react-advanced-cropper 0.20.1 declares peer dep on React ^18; library works fine with React 19.2.0

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. react-advanced-cropper installed cleanly with `--legacy-peer-deps`. TypeScript compiles with 0 errors. All key links from plan frontmatter verified.

## User Setup Required

None - no external service configuration required. react-advanced-cropper is a pure frontend dependency installed from npm.

## Next Phase Readiness
- CropPage is fully functional -- all CROP-01 through CROP-09 requirements satisfied
- BucketSelector + CropCard component API ready for any future Plan 04 extensions
- Auto-crop integration complete: POST /api/v1/crop/auto wired, response updates all CropCard positions via appStore.cropStates
- ProcessPage stub (/process route) is the next target for plan 04 (upscale wizard + proceed to captioning)

---
*Phase: 05-interactive-crop-editor*
*Completed: 2026-03-03*

## Self-Check: PASSED

- FOUND: frontend/src/components/Crop/CropCard.tsx
- FOUND: frontend/src/components/Crop/CropReadout.tsx
- FOUND: frontend/src/components/Crop/BucketSelector.tsx
- FOUND: frontend/src/pages/CropPage.tsx
- FOUND: .planning/phases/05-interactive-crop-editor/05-03-SUMMARY.md
- FOUND: commit 6396cd7 (Task 1)
- FOUND: commit 7f9da45 (Task 2)
- TypeScript: 0 errors (`npx tsc --noEmit` clean)
