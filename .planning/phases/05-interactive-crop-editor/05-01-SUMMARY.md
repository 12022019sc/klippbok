---
phase: 05-interactive-crop-editor
plan: 01
subsystem: ui
tags: [react, typescript, zustand, crop, selection, react-router]

# Dependency graph
requires:
  - phase: 04-web-gui-foundation
    provides: GalleryPage, MasonryGrid, ThumbnailCard, NavBar, App router, appStore, GalleryItem type
provides:
  - CropState, CropCoordinates, BucketOption, BucketSize types in frontend/src/types/crop.ts
  - generateBuckets(), snapToNearestBucket(), needsUpscale() bucket math utilities
  - Extended appStore with selectionMode, selectedImageIds, cropStates and all actions
  - Gallery selection mode with smart filter toolbar and Process button
  - /crop and /process routes registered in App.tsx
  - Crop nav link in NavBar
  - SelectionToolbar component with quality/duplicate filter helpers
affects: [05-02-image-crop-editor, 05-03-upscale-pipeline, 05-04-process-page, 06-captioning]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Zustand immutable Set/Map patterns (new Set([...prev, id]), new Map([...prev, [k, v]]))
    - Selection mode toggle: changes click handler behavior without separate component tree

key-files:
  created:
    - frontend/src/types/crop.ts
    - frontend/src/components/Gallery/SelectionToolbar.tsx
    - frontend/src/pages/CropPage.tsx
    - frontend/src/pages/ProcessPage.tsx
  modified:
    - frontend/src/stores/appStore.ts
    - frontend/src/pages/GalleryPage.tsx
    - frontend/src/components/Gallery/MasonryGrid.tsx
    - frontend/src/components/Gallery/ThumbnailCard.tsx
    - frontend/src/components/Layout/NavBar.tsx
    - frontend/src/App.tsx
    - frontend/src/index.css

key-decisions:
  - "05-01 TYPES-01: generateBuckets pixel-budget algorithm mirrors Python generate_buckets with step=64, min=256, max=2x, maxAR=2.0"
  - "05-01 TYPES-02: snapToNearestBucket reduces by minimum absolute AR difference, mirrors Python assign_to_bucket"
  - "05-01 SEL-01: selectionMode toggle clears selectedImageIds on exit to avoid stale selections"
  - "05-01 SEL-02: Selection state rendered via CSS outline on thumbnail-card not a separate overlay element (no DOM nesting issues)"
  - "05-01 SEL-03: SelectionToolbar rendered in GalleryPage regardless of selection mode; toggle button always visible"

patterns-established:
  - "Pattern 1: Zustand Set mutations use new Set([...prev, id]) / next.delete(id) + return new Set for reactivity"
  - "Pattern 2: Zustand Map mutations use new Map([...prev, [k,v]]) for additions, new Map(prev) + delete for removals"
  - "Pattern 3: Selection mode toggle changes handleItemClick behavior inline (no separate component trees for modes)"

requirements-completed: [GUI-05]

# Metrics
duration: 3min
completed: 2026-03-03
---

# Phase 5 Plan 01: Types, Selection Mode, and Route Stubs Summary

**TypeScript crop types with bucket math utilities, Zustand selection store, gallery selection mode with smart filters, /crop and /process routes, and Crop nav item**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-03T18:45:00Z
- **Completed:** 2026-03-03T18:48:07Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments
- Created `frontend/src/types/crop.ts` with CropState, CropCoordinates, BucketOption, BucketSize types and `generateBuckets`, `snapToNearestBucket`, `needsUpscale` pure utility functions that mirror the existing Python bucket math in `klippbok/image/bucket.py`
- Extended Zustand appStore with selection mode state (selectionMode, selectedImageIds Set) and crop state map (cropStates Map), using immutable Set/Map patterns for Zustand reactivity
- Implemented gallery selection mode: toggle button, smart filter helpers (Select All, Deselect All, Select Passing Quality, Select Non-Duplicates), selected count display, Process button navigating to /process
- Added blue border + checkmark badge visual indicator on selected thumbnails via CSS outline and absolute-positioned badge
- Registered /crop and /process routes in App.tsx with stub pages; added Crop nav link to NavBar

## Task Commits

Each task was committed atomically:

1. **Task 1: Create crop types and bucket math utilities** - `ee1c3c9` (feat)
2. **Task 2: Extend store, add selection mode to gallery, wire routes** - `dd3892f` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified
- `frontend/src/types/crop.ts` - CropCoordinates, CropState, BucketSize, BucketOption types; generateBuckets, snapToNearestBucket, needsUpscale utilities
- `frontend/src/stores/appStore.ts` - Extended with selectionMode, selectedImageIds, cropStates and all corresponding actions
- `frontend/src/components/Gallery/SelectionToolbar.tsx` - Selection toggle, smart filters, count display, Process button
- `frontend/src/components/Gallery/MasonryGrid.tsx` - Added selectionMode and selectedIds props, passes to ThumbnailCard
- `frontend/src/components/Gallery/ThumbnailCard.tsx` - Added isSelected/selectionMode props; blue outline + checkmark badge when selected
- `frontend/src/pages/GalleryPage.tsx` - Imports SelectionToolbar; handleItemClick switches between lightbox and selection behavior
- `frontend/src/components/Layout/NavBar.tsx` - Added Crop NavLink between Import and Settings
- `frontend/src/App.tsx` - Imports CropPage/ProcessPage; registers /crop and /process routes
- `frontend/src/pages/CropPage.tsx` - Stub page placeholder
- `frontend/src/pages/ProcessPage.tsx` - Stub page placeholder
- `frontend/src/index.css` - Selection toolbar and thumbnail selection CSS styles

## Decisions Made
- `selectionMode` toggle clears `selectedImageIds` on exit — prevents stale selections when re-entering selection mode
- Selection indicator uses CSS `outline` on thumbnail-card (not a separate overlay div) to avoid DOM nesting and overflow issues
- `SelectionToolbar` always rendered in GalleryPage; the toggle button visible at all times, filter buttons/count/Process only when selectionMode is active

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All Phase 5 foundation types in place: CropState, CropCoordinates, BucketSize, BucketOption
- Bucket math utilities ready for use in CropCard / crop editor components
- Selection store ready: selectedImageIds available for CropPage to consume via useAppStore
- /crop route registered; CropPage stub ready to be replaced with full editor in plan 03
- /process route registered; ProcessPage stub ready for upscale pipeline in plan 04

---
*Phase: 05-interactive-crop-editor*
*Completed: 2026-03-03*
