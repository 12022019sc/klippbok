---
phase: 06-captioning-system
verified: 2026-03-03T00:00:00Z
status: passed
score: 10/10 must-haves verified
re_verification: false
gaps: []
human_verification:
  - test: "Open lightbox on an image, click Edit in caption footer, type a caption, click Save"
    expected: "Caption persists in manifest and sidecar .txt; gallery thumbnail updates; re-opening lightbox shows new caption"
    why_human: "React state mutation + query invalidation + file I/O chain requires live server interaction"
  - test: "Open Settings page, change Model Profile dropdown from sdxl to sd15"
    expected: "Toast 'Profile updated to SD 1.5', profile details update immediately below dropdown, caption style shows 'booru'"
    why_human: "Live DOM rendering, toast display, and profile details panel require visual confirmation"
  - test: "Click Generate Captions in gallery with a project that has images"
    expected: "Progress toasts appear and update as images are processed; gallery thumbnails show captions after completion"
    why_human: "SSE stream + ONNX download + progress toast lifecycle requires a running server with the [tagger] deps installed"
---

# Phase 6: Captioning System Verification Report

**Phase Goal:** Users can generate, edit, and manage captions for every image in their dataset — with the correct format automatically selected based on target model
**Verified:** 2026-03-03
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | WD Tagger v3 ONNX model can be loaded from HuggingFace Hub cache | VERIFIED | `klippbok/caption/wd_tagger.py` L84-97: `hf_hub_download` for model.onnx + selected_tags.csv, `InferenceSession` created, target size extracted from input shape |
| 2 | An image file produces a sorted list of booru-style tags above the threshold | VERIFIED | `tag_image_booru()` L100-152: filters general/char by thresholds, sorts descending, escapes parentheses; 20 tests pass |
| 3 | RGBA images are composited onto white background before inference | VERIFIED | `prepare_image()` L39-42: `Image.new("RGBA", ..., (255,255,255))` + `alpha_composite` + `convert("RGB")` |
| 4 | Image is padded to square, resized to model target size, converted to BGR NHWC float32 | VERIFIED | `prepare_image()` L44-58: square pad, BICUBIC resize, `[:,:,::-1]` BGR flip, `expand_dims` for batch dim |
| 5 | SD1.5 profile routes to booru-style captioning; SDXL/Flux routes to NL captioning | VERIFIED | `get_caption_style_for_project()` in `caption_service.py` L38-70: reads `get_profile().caption_style`; 16+ tests confirm routing |
| 6 | caption_style_override in manifest overrides profile default | VERIFIED | `caption_service.py` L56-58: override checked first before profile fallback; test class `TestCaptionStyleOverride` confirms |
| 7 | POST /api/v1/captions/generate starts batch captioning with SSE progress | VERIFIED | `captions.py` L232-273: `@router.post("/generate")` creates asyncio task + returns `CaptionStarted`; SSE stream at `/{op_id}/events` |
| 8 | Caption is saved to both manifest and sidecar .txt file | VERIFIED | `save_caption()` L133-171: `write_text` sidecar + manifest entry mutation; PATCH endpoint writes full manifest back to disk |
| 9 | User can edit a caption inline in the lightbox footer | VERIFIED | `CaptionPanel.tsx` L1-99: full read-only/edit mode implementation; `PATCH /api/v1/captions/{imageId}` on save; integrated into `ImageLightbox.tsx` L99-103 |
| 10 | Batch trigger word, add/remove/replace tag operations work across all or selected images | VERIFIED | `caption_service.py` L179-376: `batch_add_tag`, `batch_remove_tag`, `batch_replace_tag`, `batch_prepend_trigger`; POST `/batch` endpoint routes all four; 548-line test file with dedicated test classes |

**Score:** 10/10 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `klippbok/caption/wd_tagger.py` | WD Tagger v3 ONNX inference | VERIFIED | 153 lines; exports `tag_image_booru`, `prepare_image`, `_get_tagger` |
| `pyproject.toml` | [tagger] dependency group | VERIFIED | Lines 56-60: `tagger = ["klippbok[image]", "onnxruntime>=1.17.0", "huggingface_hub>=0.20", "pandas>=1.0"]`; also in `[all]` group |
| `tests/test_wd_tagger.py` | Unit tests for preprocessing and tag filtering | VERIFIED | 357 lines, 20 tests (8 preprocessing, 11 tag filtering, 1 import error), all passing |
| `klippbok/services/caption_service.py` | Caption orchestrator with model-aware routing | VERIFIED | 377 lines; exports `get_caption_style_for_project`, `caption_image_for_project`, `save_caption`, `batch_add_tag`, `batch_remove_tag`, `batch_replace_tag`, `batch_prepend_trigger` |
| `klippbok/api/routers/captions.py` | Caption API endpoints | VERIFIED | 571 lines; 5 endpoints: POST /generate, GET /{op_id}/events, POST /batch, GET /scores, PATCH /{image_id} |
| `klippbok/api/models.py` | Caption request/response models | VERIFIED | Contains `CaptionGenerateRequest`, `CaptionStarted`, `CaptionProgress`, `CaptionUpdateRequest`, `CaptionUpdateResponse`, `CaptionBatchRequest`, `CaptionBatchResponse`, `CaptionScoreResponse`, `ProfileInfo` |
| `tests/test_caption_service.py` | Unit tests for caption routing and service | VERIFIED | 548 lines; covers routing, overrides, NL backend, save, and all four batch operations |
| `frontend/src/components/Caption/CaptionPanel.tsx` | Inline caption editor component | VERIFIED | 99 lines; read-only/edit mode toggle, PATCH save, toast feedback |
| `frontend/src/hooks/useCaptionEvents.ts` | SSE hook for batch caption progress | VERIFIED | 135 lines; handles "progress", "done", "caption_error" named events; mirrors useUpscaleEvents pattern |
| `frontend/src/pages/SettingsPage.tsx` | Model profile dropdown | VERIFIED | Contains `<select>` at L147; fetches `/api/v1/settings/profiles`; PUT on change with toast |
| `tests/test_caption_api.py` | Integration tests for PATCH endpoint | VERIFIED | 239 lines; 7 tests covering PATCH success/404/no-project/overwrite + profiles schema/content/no-project |
| `klippbok/caption/scoring.py` | IMAGE_SCORING_CONFIG | VERIFIED | Lines 74-83: `IMAGE_SCORING_CONFIG = ScoringConfig(min_good_length=20, ..., weight_temporal=0.0, ...)` |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `wd_tagger.py` | `huggingface_hub` | `hf_hub_download` for model.onnx + selected_tags.csv | WIRED | L84-85: `hf_hub_download(MODEL_REPO, LABEL_FILENAME)` and `hf_hub_download(MODEL_REPO, MODEL_FILENAME)` |
| `wd_tagger.py` | `onnxruntime` | `InferenceSession` for ONNX model execution | WIRED | L93: `model = rt.InferenceSession(model_path)` |
| `caption_service.py` | `klippbok/config/model_config.py` | `get_profile()` for caption_style lookup | WIRED | L53: `from klippbok.config.model_config import get_profile`; called at L63 |
| `caption_service.py` | `klippbok/caption/captioner.py` | `_create_backend()` for NL VLM backends | WIRED | L121: `from klippbok.caption.captioner import _create_backend`; called at L124 |
| `captions.py` | `caption_service.py` | `caption_image_for_project` for generation | WIRED | L68: `from klippbok.services.caption_service import caption_image_for_project, save_caption`; used at L157, L163 |
| `app.py` | `captions.py` | router registration | WIRED | L38: `from klippbok.api.routers.captions import router as captions_router`; L90: `app.include_router(captions_router, prefix="/api/v1")` |
| `CaptionPanel.tsx` | `/api/v1/captions/{image_id}` | `fetch` PATCH for saving edits | WIRED | L36-39: `fetch(\`/api/v1/captions/${imageId}\`, { method: 'PATCH', ... })` |
| `SettingsPage.tsx` | `/api/v1/settings/` | `fetch` PUT for profile change | WIRED | L59-63: `fetch('/api/v1/settings/', { method: 'PUT', ... body: JSON.stringify({ active_profile: ... }) })` |
| `ImageLightbox.tsx` | `CaptionPanel.tsx` | CaptionPanel rendered in slideFooter | WIRED | L4: import; L99-103: `<CaptionPanel imageId={item.id} initialCaption={item.caption ?? null} onSaved={...} />` |
| `captions.py` | `scoring.py` | `score_caption` with `IMAGE_SCORING_CONFIG` | WIRED | L452: `from klippbok.caption.scoring import IMAGE_SCORING_CONFIG, score_caption`; used at L477 |
| `captions.py` | `caption_service.py` | `batch_add_tag`, `batch_prepend_trigger` for batch endpoint | WIRED | L369-373: imports all four batch functions; POST /batch routes to them at L396-405 |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CAPT-01 | 06-01 | Booru-style tag generation via WD Tagger v3 (ONNX) for SD1.5 datasets | SATISFIED | `wd_tagger.py` — full ONNX inference pipeline; `tag_image_booru()` and `prepare_image()` verified |
| CAPT-02 | 06-02 | Natural language caption generation via existing VLM backends | SATISFIED | `caption_service.py` — `caption_image_for_project()` calls `_create_backend()` and `backend.caption_image()` for NL path |
| CAPT-03 | 06-02 | Caption style automatically selected based on target model | SATISFIED | `get_caption_style_for_project()` reads `get_profile(active_profile).caption_style`; sd15/pony → booru, sdxl/flux → NL |
| CAPT-04 | 06-02 | User can override caption style per dataset | SATISFIED | `caption_service.py` L56-58: `caption_style_override` in manifest takes priority over profile |
| CAPT-05 | 06-03 | Manual caption editing: inline text editor per image in gallery view | SATISFIED | `CaptionPanel.tsx` renders in lightbox slideFooter; PATCH endpoint saves to manifest + sidecar |
| CAPT-06 | 06-04 | Trigger word injection: auto-prepend configurable trigger token | SATISFIED | `batch_prepend_trigger()` reuses `_prepend_anchor()`; POST /batch with `operation="prepend_trigger"` |
| CAPT-07 | 06-04 | Batch tag operations: add, remove, replace across all captions | SATISFIED | `batch_add_tag`, `batch_remove_tag`, `batch_replace_tag` all implemented; POST /batch endpoint routes all three |
| CAPT-08 | 06-04 | Caption quality scoring via existing klippbok scoring | SATISFIED | `IMAGE_SCORING_CONFIG` in `scoring.py`; GET /scores returns per-image scores sorted worst-first |
| GUI-04 | 06-03 | Inline caption editor alongside image preview in expanded view | SATISFIED | `CaptionPanel.tsx` in lightbox footer with edit/save/cancel controls |
| GUI-06 | 06-03 | Model configuration selector affecting resolution + caption defaults | SATISFIED | `SettingsPage.tsx` profile `<select>` dropdown; GET /settings/profiles; PUT on change; shows caption_style + base_resolution details |

**All 10 required requirements (CAPT-01 through CAPT-08, GUI-04, GUI-06) are SATISFIED.**

---

## Anti-Patterns Found

No blockers or significant anti-patterns detected.

| File | Pattern | Severity | Notes |
|------|---------|----------|-------|
| `captions.py` L155 | `asyncio.get_event_loop().run_in_executor()` | Info | Technically deprecated in favor of `asyncio.get_running_loop()` in Python 3.10+, but functionally correct and matching existing patterns in other routers |

---

## Human Verification Required

### 1. Inline caption edit flow

**Test:** Open the gallery, click an image to open lightbox, click "Edit" in the caption footer, type a new caption, click "Save"
**Expected:** Caption saves successfully (toast appears), closing and reopening the lightbox shows the new caption, the sidecar .txt file is written in the project directory
**Why human:** React state mutation + TanStack Query invalidation + file I/O chain requires a running server with a real project loaded

### 2. Model profile dropdown behavior

**Test:** Navigate to Settings page, change the Model Profile dropdown (e.g., from SD XL to SD 1.5)
**Expected:** Toast "Profile updated to SD 1.5", caption style display updates to "booru", base resolution updates to 512px
**Why human:** Visual DOM rendering, toast display timing, and profile details panel appearance require live browser interaction

### 3. Generate Captions with WD Tagger (booru path)

**Test:** Set profile to SD 1.5, navigate to Gallery, click "Generate Captions"
**Expected:** Progress toasts appear with image filenames as they are processed; gallery thumbnails show captions after completion; sidecar .txt files appear in the project directory
**Why human:** Requires [tagger] deps installed, ONNX model download from HuggingFace Hub (~380MB), live SSE stream, and a project with real images

---

## Test Results

| Test File | Tests | Status |
|-----------|-------|--------|
| `tests/test_wd_tagger.py` | 20 passed | All green |
| `tests/test_caption_service.py` | 16 core + batch tests | All green (54 total across API + service) |
| `tests/test_caption_api.py` | 7 integration tests | All green |
| `tests/test_caption_scoring.py` | 43 passed | All green |
| Full test suite | 1211 passed, 4 skipped | No regressions |

---

## Summary

Phase 6 goal is fully achieved. All 10 observable truths are verified against the actual codebase:

1. **WD Tagger backend** (`wd_tagger.py`): Complete ONNX pipeline with correct RGBA composite, square pad, BICUBIC resize, BGR channel order, NHWC batch dimension, and lru_cache lazy-loading. Dependencies isolated in `[tagger]` optional group.

2. **Caption service** (`caption_service.py`): Model-aware routing from profile system, caption_style_override support, NL VLM backend delegation, atomic sidecar+manifest persistence, and all four batch tag operations.

3. **API layer** (`captions.py`): Five endpoints — POST /generate with SSE progress (asyncio.Queue pattern), GET /{op_id}/events stream, PATCH /{image_id} inline edit, POST /batch for tag operations, GET /scores with IMAGE_SCORING_CONFIG. All registered in `app.py` before static file mount.

4. **Frontend** (`CaptionPanel.tsx`, `useCaptionEvents.ts`, `SettingsPage.tsx`, `GalleryPage.tsx`): Inline caption editor in lightbox footer, SSE progress hook for batch generation, profile dropdown with live detail display, and Generate Captions button with selection-mode support.

5. **Scoring** (`scoring.py`): `IMAGE_SCORING_CONFIG` preset with `weight_temporal=0.0` and short-caption length thresholds, integrated into GET /scores endpoint.

The three human verification items are interactive UI behaviors that cannot be confirmed programmatically but have solid code-level evidence supporting them.

---

_Verified: 2026-03-03_
_Verifier: Claude (gsd-verifier)_
