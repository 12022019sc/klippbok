---
phase: 06-captioning-system
plan: 03
subsystem: ui
tags: [react, fastapi, sse, caption, lightbox, pydantic]

requires:
  - phase: 06-02
    provides: caption_service, save_caption, PATCH endpoint stub, captions router
  - phase: 04-web-gui-foundation
    provides: ImageLightbox, SettingsPage, GalleryPage, TanStack Query, Sonner toasts

provides:
  - CaptionPanel inline editor (lightbox footer, PATCH /api/v1/captions/{id})
  - useCaptionEvents SSE hook (batch caption progress)
  - ProfileInfo model + GET /api/v1/settings/profiles endpoint
  - SettingsPage model profile dropdown (GUI-06)
  - GalleryPage Generate Captions button with SSE toast progress
  - 7 integration tests covering PATCH endpoint and profiles API

affects:
  - 06-04 (caption-export, will use same endpoints/patterns)

tech-stack:
  added: []
  patterns:
    - "Full manifest write-back pattern (load -> mutate in-place -> write full dict) for atomic caption updates"
    - "useCaptionEvents SSE hook mirrors useUpscaleEvents pattern exactly"
    - "CaptionPanel read-only/edit mode toggle with inline textarea"
    - "Gallery toolbar for action buttons above the masonry grid"

key-files:
  created:
    - frontend/src/components/Caption/CaptionPanel.tsx
    - frontend/src/hooks/useCaptionEvents.ts
    - tests/test_caption_api.py
  modified:
    - klippbok/api/models.py (ProfileInfo model)
    - klippbok/api/routers/settings.py (GET /profiles endpoint)
    - klippbok/api/routers/captions.py (fix manifest write-back, fix _run_caption_batch)
    - frontend/src/components/Lightbox/ImageLightbox.tsx (CaptionPanel integration)
    - frontend/src/pages/SettingsPage.tsx (profile dropdown)
    - frontend/src/pages/GalleryPage.tsx (Generate Captions button)
    - frontend/src/App.css (CaptionPanel, settings-select, gallery-toolbar styles)

key-decisions:
  - "06-03 MANIFEST-01: update_caption writes full manifest dict back to disk (NOT save_image_entries which appends) — prevents duplicate image entries"
  - "06-03 MANIFEST-02: _run_caption_batch also fixed to write full manifest dict instead of appending"
  - "06-03 CAPS-01: CaptionPanel default read-only mode, Edit button to enter textarea mode"
  - "06-03 CAPS-02: onCaptionSaved mutates item.caption in-place for immediate re-open accuracy, plus invalidates 'images' query for gallery refresh"
  - "06-03 GEN-01: Generate Captions button captions selected images if in selection mode, all images otherwise"

patterns-established:
  - "Manifest write-back: load_manifest -> mutate in place -> json.dumps full dict (NOT save_image_entries for updates)"
  - "CaptionPanel: read-only span + Edit btn, textarea + Save/Cancel in edit mode"

requirements-completed:
  - CAPT-05
  - GUI-04
  - GUI-06

duration: 10min
completed: 2026-03-04
---

# Phase 06 Plan 03: Caption UI and Profile Controls Summary

**Inline caption editor in lightbox (CaptionPanel), model profile dropdown in Settings, Generate Captions button with SSE progress in Gallery, and 7 integration tests**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-03-04T00:15:00Z
- **Completed:** 2026-03-04T00:24:53Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- CaptionPanel component: inline edit/save/cancel for captions in lightbox footer, PATCH /api/v1/captions/{id}
- Settings page model profile dropdown: fetches GET /settings/profiles, PUT on change, shows caption style and base resolution details
- Generate Captions button in gallery with SSE progress toasts via useCaptionEvents hook
- ProfileInfo model + GET /api/v1/settings/profiles endpoint listing all built-in and custom profiles
- Fixed a manifest duplication bug in the PATCH endpoint and batch caption runner

## Task Commits

1. **Task 1: PATCH caption endpoint, settings profiles API, and tests** - `22239a7` (feat)
2. **Task 2: Caption editor UI, settings dropdown, and generate button** - `1f00aa1` (feat)

## Files Created/Modified

- `frontend/src/components/Caption/CaptionPanel.tsx` - Inline caption editor, read-only/edit mode toggle, PATCH save
- `frontend/src/hooks/useCaptionEvents.ts` - SSE hook for batch caption progress (mirrors useUpscaleEvents)
- `tests/test_caption_api.py` - 7 integration tests: PATCH success/not-found/no-project/overwrite + profiles schema/content/no-project
- `klippbok/api/models.py` - ProfileInfo Pydantic model (name, display_name, caption_style, base_resolution)
- `klippbok/api/routers/settings.py` - GET /profiles endpoint (list_available_profiles)
- `klippbok/api/routers/captions.py` - Fixed manifest write-back in update_caption and _run_caption_batch
- `frontend/src/components/Lightbox/ImageLightbox.tsx` - CaptionPanel in slideFooter, onCaptionSaved prop
- `frontend/src/pages/SettingsPage.tsx` - Profile dropdown with live profile details display
- `frontend/src/pages/GalleryPage.tsx` - Generate Captions button, useCaptionEvents SSE progress
- `frontend/src/App.css` - CaptionPanel, settings-select, gallery-toolbar CSS

## Decisions Made

- `save_image_entries` is an additive/append function designed for import batches. For caption updates, we write the full manifest dict back directly using `json.dumps`. This prevents the critical duplication bug found during Task 1 testing.
- `_run_caption_batch` had the same bug — fixed to use the same full write-back approach.
- CaptionPanel defaults to read-only mode; clicking Edit enters textarea mode. Cancel reverts to initialCaption.
- Generate Captions in selection mode sends only selected image IDs; otherwise sends all (no image_ids field).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed manifest duplication bug in update_caption and _run_caption_batch**
- **Found during:** Task 1 (integration test `test_update_caption_success` failed with `assert 2 == 1`)
- **Issue:** Both endpoints called `save_image_entries(project_dir, manifest["images"])` which reads the existing images list and appends the new entries on top, duplicating all image records on every save
- **Fix:** Replaced `save_image_entries` calls with direct `json.dumps(manifest)` write-back to disk. `save_image_entries` is correctly used only for import batches (appending new entries), not for in-place updates
- **Files modified:** `klippbok/api/routers/captions.py`
- **Verification:** All 7 integration tests pass; manifest has 1 entry after PATCH, not 2
- **Committed in:** `22239a7` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Critical correctness fix — without this, every caption save would corrupt the manifest by doubling all image entries. No scope creep.

## Issues Encountered

- `klippbok/api/static/` is gitignored — the deploy step copies files correctly but they are not tracked. This is by design (the build artifacts are regenerated from source).

## Next Phase Readiness

- PATCH endpoint, profiles API, CaptionPanel, useCaptionEvents, and Generate Captions button are all functional
- Ready for Phase 06-04 (caption export / final pipeline integration)
- The manifest write-back pattern is now established and consistent between PATCH and batch generation

---
*Phase: 06-captioning-system*
*Completed: 2026-03-04*
