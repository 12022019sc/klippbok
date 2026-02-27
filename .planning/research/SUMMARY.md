# Project Research Summary

**Project:** klippbok — Image Dataset Preparation, Cropping, Tagging, and Web GUI
**Domain:** LoRA training dataset curation (image pipeline + interactive web GUI extending existing video tool)
**Researched:** 2026-02-27
**Confidence:** HIGH

## Executive Summary

Klippbok is being extended from a video-focused LoRA dataset tool into a full image+video dataset preparation platform with an interactive web GUI. The domain is well-understood: the community has settled on clear workflows (import images, crop to aspect-ratio buckets, generate model-appropriate captions, export in trainer format), and multiple reference implementations exist (Birme, BooruDatasetTagManager, malcolmrey's HF Space). The recommended approach is to build a FastAPI+React SPA that exposes the existing klippbok pipeline via a service layer, adding a new `klippbok/image/` domain module for image-specific operations. The project's existing Pydantic models, YAML config patterns, caption backends, and bucketing logic are directly reusable — the work is integration and UI, not greenfield.

The signature differentiating feature is the interactive crop editor with snap-to-bucket-ratio behavior. No existing standalone web tool does this well. This feature must be built early (Phase 2) and must be correct from the start: bucket-aware previews, client-side Canvas rendering for zero-latency feedback, and server-side Pillow for actual pixel operations. A second key differentiator is model-aware captioning: SD1.5 requires booru-style comma-separated tags (WD Tagger v3 via ONNX), while SDXL/Flux require natural language captions (existing Gemini/OpenAI backends). The tool must treat these as fundamentally different systems, not a formatting toggle.

The critical architectural risk is bolting GUI state onto a stateless CLI pipeline. The solution is a formal service layer (`services/`) that both the CLI and API share, backed by a `project.json` manifest as the single source of truth. A second major risk is silent error swallowing: the existing codebase has 15+ bare `except Exception` blocks that are harmless in a CLI (log and continue) but catastrophic in a GUI (silent data loss with no user feedback). Error handling refactoring must happen before GUI integration. All original images must be preserved immutably — crops stored as coordinates, never overwriting originals.

## Key Findings

### Recommended Stack

The backend extends the existing Python codebase with FastAPI (already decided, Pydantic-native) served by uvicorn, SQLAlchemy 2.0 with aiosqlite for async database access (though the architecture research recommends JSON manifest files over SQLite for project state — these serve different purposes), and onnxruntime for WD Tagger v3 ONNX inference. All image operations use Pillow — OpenCV is explicitly excluded due to BGR color space bugs and dependency weight. The frontend is a Vite+React+TypeScript SPA using react-advanced-cropper (chosen over react-easy-crop for custom stencil and programmatic bucket-ratio support), TanStack Query for server state, and Zustand for client state. The full React build is served as static files from FastAPI in production — single process, single port, `pip install klippbok[gui]` and `klippbok serve` starts everything.

**Core technologies:**
- FastAPI >= 0.133 + uvicorn: Web API and ASGI server — async, Pydantic-native, matches existing codebase
- Pillow >= 12.1: All image I/O, crop, resize, thumbnail generation — already a project dependency
- onnxruntime >= 1.24: WD Tagger v3 ONNX inference — lighter than PyTorch for inference-only
- SQLAlchemy 2.0 + aiosqlite: Async ORM for any structured data needs — standard FastAPI pattern
- react-advanced-cropper >= 0.20: Snap-to-bucket interactive crop — only React cropper with custom stencil support
- TanStack Query v5: Server state caching and invalidation — de facto React standard
- Vite 7.3 + React 18 + TypeScript 5: Frontend build stack — standard 2026 SPA

### Expected Features

**Must have (table stakes):**
- Batch image import (PNG, JPG, WEBP, TIFF) with drag-and-drop
- Image gallery with resolution display and green/red quality indicators
- Aspect ratio bucketing preview — klippbok's existing logic is reusable
- Model-aware resolution presets (SD1.5 = 512px, SDXL/Flux = 1024px)
- Basic quality filtering and duplicate detection — both already built in klippbok
- Center crop and interactive crop with snap-to-bucket-ratio
- Caption file generation (.txt per image, same stem)
- Manual caption editing inline in gallery view
- Model-aware captioning: booru tags for SD1.5, natural language for SDXL/Flux
- Trigger word injection
- Batch export as trainer-ready folder (kohya format minimum)

**Should have (differentiators):**
- Auto-crop with subject detection (YOLO-based, with human fallback and always user-confirmable)
- Batch tag operations (add/remove/replace across selection)
- Bucket distribution visualization with imbalance warnings
- Per-image crop memory (stored as relative coordinates in manifest)
- CLIP-based similarity triage (already built for video, low-effort wire-up)
- Multi-trainer export (ai-toolkit second, OneTrainer and SimpleTuner stretch)
- Caption scoring/quality audit (already built in klippbok.caption.scoring)
- Rotation and flip controls in crop editor

**Defer to v2+:**
- Auto-crop with subject detection for non-human subjects (complex, needs multiple detection strategies)
- Florence-2 local NL captioning (Gemini/OpenAI covers the case; Florence-2 as optional later)
- Full danbooru tag autocomplete with alias resolution (curated ~10K subset for MVP)
- Real-time collaborative features (out of scope: single-user tool)
- Built-in training, image generation, upscaling (explicit anti-features)

### Architecture Approach

The architecture extracts a service layer (`services/`) that both the existing CLI and the new API share. No business logic lives in the API routes or CLI — both are thin dispatchers. A new `klippbok/image/` domain module handles all image-specific operations (load, crop, resize, validate, autocrop) using Pillow, following existing frozen Pydantic model conventions. Project state lives in a `project.json` manifest file per workspace, not in-process memory or a separate database. The crop preview renders entirely in the browser via HTML5 Canvas (client-side); the server only processes final crop parameters. Long-running batch operations use Server-Sent Events (SSE) for progress — simpler than WebSocket for unidirectional server-to-client updates.

**Major components:**
1. `klippbok/image/` (NEW) — Image loading, crop, resize, validation, autocrop; pure Pillow, no HTTP
2. `klippbok/services/` (NEW) — Orchestrates domain modules for use cases; testable without HTTP
3. `klippbok/api/` (NEW) — FastAPI routes and SSE; thin HTTP dispatch layer only
4. `klippbok/web/` (NEW) — Built React SPA static files served by FastAPI
5. Existing modules (`config/`, `caption/`, `dataset/`, `triage/`) — Extended, not replaced

### Critical Pitfalls

1. **Wrong resolution targets per model** — Define per-model resolution config from day one. SD1.5: 512px base, SDXL/Flux: 1024px base. Never use global constants. Unit test each model type produces correct bucket dimensions.

2. **GUI state vs. CLI state mismatch** — Implement the `project.json` manifest as single source of truth before building any frontend. Never shell out to CLI commands from the API. Never store state in FastAPI process memory.

3. **Silent error swallowing in existing pipeline** — Audit and categorize all 15+ bare `except Exception` blocks before GUI integration. Implement structured result objects with `success`, `warnings`, and `errors` fields. Every processing function must surface failures, not swallow them.

4. **Tag/caption format confusion** — Implement tag mode and caption mode as fundamentally separate systems. Tag mode: danbooru vocabulary, underscores, comma-separated, ordered by category. Caption mode: freeform NL with VLM assistance. Single text field that "supports both" produces output that works for neither model.

5. **Canvas memory on large images** — Never load full-resolution images into browser Canvas. Always generate server-side thumbnails (max 1024px) for the crop UI. Full-resolution processing stays server-side via Pillow. Use `useRef` for crop canvas, not React state, to avoid re-render jank on every drag event.

## Implications for Roadmap

Based on research, the build order is dictated by dependencies. Each layer must be solid before the next layer can be built. Five phases are suggested.

### Phase 1: Image Domain Module + Config Extension

**Rationale:** Everything else — services, API, frontend — depends on having working image operations and a correct config schema. This is pure Python with no web concerns: easiest to test in isolation, and getting bucket/resolution logic wrong here propagates everywhere. Config schema must be model-aware from day one to avoid Pitfall 1.

**Delivers:** `klippbok/image/` module (models, loader, crop, resize, buckets, validate); `ImageConfig` in config schema with per-model resolution targets; full pytest coverage before any service layer.

**Addresses features:** Aspect ratio bucketing, resolution display, basic quality filtering, duplicate detection (wire to existing klippbok modules), format validation.

**Avoids:** Wrong resolution targets (config schema forces model-aware definition); upscale-as-a-feature (flag as warning, never silently upscale).

**Research flag:** Standard patterns. Pillow image operations and Pydantic models are well-documented. No deeper research needed.

### Phase 2: Service Layer + Error Handling Refactor

**Rationale:** The service layer is the architectural keystone. Building it before the API ensures no business logic bleeds into routes. The error handling refactor must happen in this phase — not after — because the GUI will inherit every silent failure if it is left for later. The project.json manifest design happens here.

**Delivers:** `klippbok/services/` (ImageService, ProjectService, CaptionService); project manifest schema; structured error/warning result objects replacing bare except blocks; services tested without HTTP.

**Addresses features:** Per-image crop memory (manifest design), session resumption, GUI state persistence.

**Avoids:** GUI state vs. CLI mismatch (manifest is single source of truth, established before any frontend exists); silent error swallowing (refactored in this phase before GUI integration).

**Research flag:** Standard patterns. Service layer extraction is a well-documented pattern. Error handling audit is mechanical (grep + categorize).

### Phase 3: API Layer + WD Tagger Integration

**Rationale:** With a working service layer, the API is thin wiring. WD Tagger (ONNX) is included in this phase because it is a backend concern: model download, ONNX Runtime singleton at startup, batch inference with thresholding. The booru tag system must be designed as a separate code path from NL captioning here, before the frontend enforces the distinction.

**Delivers:** FastAPI app with all routes (`/api/v1/images`, `/api/v1/projects`, `/api/v1/captions`, `/api/v1/jobs`); SSE progress streaming; WD Tagger v3 ONNX integration; booru vs. NL caption mode implemented as separate systems.

**Addresses features:** Model-aware captioning defaults, trigger word injection, auto-tagging for SD1.5, NL captioning via existing Gemini/OpenAI backends, batch operation progress reporting.

**Avoids:** Tag/caption format confusion (designed as separate systems in this phase); CLIP model per-request loading (singleton pattern enforced at API startup).

**Research flag:** Needs attention. SSE streaming patterns and ONNX Runtime batch inference have specific implementation details. WD Tagger preprocessing (448x448 resize, normalization) must match model expectations exactly. Recommend verifying against the wdv3-batch-vit-tagger reference implementation.

### Phase 4: React Frontend — Gallery + Crop Editor

**Rationale:** The crop editor is the hardest, most valuable UI component. Building it last (after stable API) means it can be iterated freely. The Canvas-based crop editor is the signature feature — it must be built correctly from the start, not retrofitted. Gallery virtualization must be in scope from the start (not added at 500 images).

**Delivers:** Vite+React+TypeScript frontend; virtualized image gallery with thumbnails; Canvas-based interactive crop editor with snap-to-bucket-ratio; resolution quality indicators; caption editor panel; model/preset selector.

**Addresses features:** Interactive crop (the key differentiator), image gallery, manual caption editing, bucket distribution visualization, resolution display.

**Avoids:** Canvas memory crashes (thumbnail-only in gallery, full-res crop via `useRef` not React state); server-side crop preview (client-side Canvas only, server handles final crop).

**Research flag:** Needs attention. react-advanced-cropper custom stencil implementation for bucket-ratio snapping is not heavily documented. Canvas-based crop rendering for precise pixel feedback requires care. Plan for a spike on the crop component before committing to the full gallery.

### Phase 5: Export + Advanced Features

**Rationale:** Export (kohya format first, ai-toolkit second) is the final deliverable of the tool. Advanced features — batch tag operations, CLIP similarity triage, auto-crop with subject detection, multi-trainer export — are built on a stable foundation. These are lower-risk but require the full stack to be working.

**Delivers:** Kohya/sd-scripts trainer-ready folder export; TOML config generation; batch tag operations; CLIP similarity triage (wired from existing klippbok.triage); auto-crop with subject detection (YOLO-based, always user-confirmable); optional ai-toolkit export.

**Addresses features:** Batch export, multi-trainer export, batch tag operations, auto-crop, CLIP triage, caption scoring/audit.

**Avoids:** Auto-crop subject detection failure (multiple detection strategies: face, saliency, center-crop fallback; never final without user confirmation); export without dry-run (show bucket distribution preview before export).

**Research flag:** Auto-crop subject detection needs research. YOLO model selection for anime vs. photo vs. object subjects, and integration with the crop suggestion flow, has sparse documentation for this specific use case.

### Phase Ordering Rationale

- **Domain module first** enforces correct foundation: bucketing, resolution, and crop logic must be right before UI touches them.
- **Service layer before API** prevents business logic from leaking into routes, a common mistake when building quickly.
- **Error handling refactor in Phase 2** (not Phase 4) means the frontend inherits structured error results from day one.
- **Frontend last** allows the API to stabilize before UI is built against it, avoiding repeated interface churn.
- **Export in Phase 5** is intentional: a partial dataset (some images cropped, some captioned) has zero value; only a complete, exported dataset is useful. Export is the final gate.

### Research Flags

Phases needing deeper research during planning:

- **Phase 3 (API + WD Tagger):** WD Tagger v3 ONNX preprocessing must exactly match the model's expected normalization. Verify against SmilingWolf's model card and the wdv3-batch-vit-tagger reference implementation before implementing.
- **Phase 4 (Crop Editor):** react-advanced-cropper custom stencil for bucket-ratio snapping is the highest-risk UI implementation. Plan a 1-2 day spike to validate the approach before committing to the full gallery.
- **Phase 5 (Auto-Crop):** YOLO-based subject detection for mixed content (photo, anime, object) needs a clear fallback hierarchy and "always user-confirmable" design constraint enforced from the start.

Phases with standard, well-documented patterns:

- **Phase 1 (Image Module):** Pillow image operations, Pydantic models, pytest — all standard.
- **Phase 2 (Service Layer):** Service layer extraction is mechanical; error handling audit is a grep exercise.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All core library versions verified on PyPI and npm as of Feb 2026. One low-confidence item: Zustand version number — verify before adding to package.json. |
| Features | MEDIUM | Table stakes well-established by community tools and training guides. Differentiators based on gap analysis of existing tools (Birme, BDTM, SD Tag Editor) — confident in the gaps, less certain about exact UX priority ordering. |
| Architecture | HIGH | Based on direct codebase analysis of existing klippbok modules + well-documented FastAPI/React patterns. Service layer and manifest design are verified patterns. |
| Pitfalls | HIGH | Pitfalls sourced from codebase review, community training guides, and official documentation. The silent-error-swallowing pitfall was directly observed in the existing codebase (15+ instances). |

**Overall confidence:** HIGH

### Gaps to Address

- **Zustand version:** Training data suggests >= 5.0 but verify current stable version on npm before adding to package.json.
- **react-advanced-cropper bucket-ratio snapping:** The library supports custom stencils and programmatic aspect ratio control, but the exact implementation pattern for snap-to-nearest-bucket is not documented in the library's examples. Requires a spike.
- **WD Tagger v3 normalization:** The model card specifies 448x448 input, RGB, normalized to [0,1], but the exact channel ordering and normalization formula should be verified against the reference implementation before trusting output tags.
- **Auto-crop strategy for anime:** Anime-specific face/subject detection (lbpcascade_animeface, etc.) is available but not evaluated for quality. This needs a small evaluation pass before committing to a detection library.
- **Architecture recommends JSON manifests; STACK.md recommends SQLite:** These are not in conflict (SQLite for structured queries if needed, manifest for project state), but the boundary between what lives where should be decided explicitly in Phase 2 before both are implemented.

## Sources

### Primary (HIGH confidence)
- Existing klippbok codebase analysis (direct code reading, Feb 2026)
- [Pillow 12.1.1 on PyPI](https://pypi.org/project/Pillow/) — version and API
- [FastAPI 0.133.1 on PyPI](https://pypi.org/project/fastapi/) — version and docs
- [onnxruntime 1.24.2 on PyPI](https://pypi.org/project/onnxruntime/) — version
- [SmilingWolf/wd-eva02-large-tagger-v3 on HuggingFace](https://huggingface.co/SmilingWolf/wd-eva02-large-tagger-v3) — model card and ONNX requirements
- [kohya_ss folder structure docs](https://github.com/bmaltais/kohya_ss/blob/master/docs/image_folder_structure.md) — export format
- [malcolmrey/dataset-preparation HF Space](https://huggingface.co/spaces/malcolmrey/dataset-preparation) — interactive crop reference implementation
- [FastAPI Static Files, Background Tasks, UploadFile docs](https://fastapi.tiangolo.com) — API patterns
- [react-advanced-cropper docs](https://advanced-cropper.github.io/react-advanced-cropper/) — custom stencils, aspect ratio constraints

### Secondary (MEDIUM confidence)
- [Civitai: Detailed Flux Training Guide](https://civitai.com/articles/7777/detailed-flux-training-guide-dataset-preparation) — bucketing, captioning, quality criteria
- [Civitai: Captioning for LoRA Training](https://civitai.com/articles/25066/captioning-for-lora-training-joycaption-wd14-ideas) — captioning strategy comparison
- [Civitai: Automated Anime Character Dataset](https://civitai.com/articles/218/automated-anime-character-dataset-for-character-loras) — auto-tagging thresholds
- [Sable Confusion: How Are Images Assigned to Buckets](https://medium.com/@sableconfusion/lora-training-practice-in-kohya-ss-how-are-images-assigned-to-buckets-19b2a3e97c6c) — bucket algorithm
- [NovelAI Aspect Ratio Bucketing reference implementation](https://github.com/NovelAI/novelai-aspect-ratio-bucketing)
- [DEV.to: Building a React Image Cropper](https://dev.to/mjoycemilburn/building-a-react-image-cropper-a-whole-world-of-unexpected-problems-300i) — canvas/state pitfalls
- [klippbok image/SD1.5 support analysis](../docs/image-sd15-support-analysis.md) — image-ready components

### Tertiary (LOW confidence)
- [LoraTag](https://loratag.ai/) — commercial tool reference (feature landscape only)
- [Apatero: LoRA Training Best Practices 2025](https://apatero.com/blog/lora-training-best-practices-flux-stable-diffusion-2025) — general practices

---
*Research completed: 2026-02-27*
*Ready for roadmap: yes*
