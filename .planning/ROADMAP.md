# Roadmap: Klippbok v2

## Overview

Klippbok v2 extends the existing video-only LoRA dataset tool into a unified image+video preparation platform with an interactive web GUI. The roadmap builds from architectural foundation through domain modules, web interface, and export -- each phase delivers a coherent, testable capability. The critical path runs through image processing, model-aware configuration, the interactive crop editor (the signature differentiator), and multi-trainer export.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Architecture Foundation** - Service layer, image domain module, unified models, and dependency structure
- [x] **Phase 2: Model Configuration** - Model profiles with resolution presets, bucket sizes, and caption style defaults
- [x] **Phase 3: Image Import and Quality** - Batch image import with validation, bucketing, quality filtering, and duplicate detection
- [x] **Phase 4: Web GUI Foundation** - FastAPI+React shell, image gallery, thumbnails, and progress indicators
- [x] **Phase 5: Interactive Crop Editor** - Canvas-based crop tool with snap-to-bucket, zoom, rotation, and auto-crop (completed 2026-03-03)
- [x] **Phase 6: Captioning System** - Booru tag generation, NL captioning, model-aware defaults, manual editing, and batch operations (completed 2026-03-04)
- [x] **Phase 6.1: Caption Provider Configuration** - Dedicated captioning page with provider config, model picker, API key management, and caption workspace (INSERTED) (completed 2026-03-04)
- [x] **Phase 6.2: Captioning Enhancement: JoyCaption Integration Planning** - Caption modes, context-only modes, post-processing pipeline, token budgets, trigger word injection (INSERTED) (completed 2026-03-05)
- [x] **Phase 7: Video and CLIP Integration** - Existing video pipeline accessible from GUI, CLIP triage extended to standalone images (completed 2026-03-05)
- [ ] **Phase 8: Export Pipeline** - Multi-trainer export with format-specific config generation and dataset download

## Phase Details

### Phase 1: Architecture Foundation
**Goal**: Developers can build image features and API routes on top of a shared service layer, unified data models, and correct dependency structure -- without breaking existing CLI workflows
**Depends on**: Nothing (first phase)
**Requirements**: ARCH-01, ARCH-02, ARCH-03, ARCH-04, ARCH-05, ARCH-07
**Success Criteria** (what must be TRUE):
  1. A service layer exists that both CLI commands and future API routes can call without duplicating business logic
  2. An image domain module (`klippbok/image/`) exists following the same patterns as existing modules (frozen Pydantic models, accumulative validation)
  3. A unified SamplePair model can represent both image and video targets with type discrimination
  4. Image-specific validation produces structured ValidationIssue results (resolution, format, quality) without failing fast
  5. Existing CLI commands (`klippbok dataset`, `klippbok video`) continue to work identically after changes
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md -- Service layer extraction (dataset_service, project_service) and CLI refactor
- [x] 01-02-PLAN.md -- Image domain module (models, probe, validate, discover) and IssueCode extension
- [x] 01-03-PLAN.md -- Unified SamplePair with type discriminator, discovery target_type, dependency groups

### Phase 2: Model Configuration
**Goal**: Users can select a target model (SD1.5, SDXL, Flux, custom) and get correct resolution presets, bucket sizes, and captioning defaults automatically -- with full override capability
**Depends on**: Phase 1
**Requirements**: MODL-01, MODL-02, MODL-03, MODL-04, MODL-05, MODL-06
**Success Criteria** (what must be TRUE):
  1. Selecting SD1.5 sets base resolution to 512px, valid buckets within 262,144 pixel budget, and booru-style caption default
  2. Selecting SDXL or Flux sets base resolution to 1024px with appropriate buckets and natural language caption default
  3. User can override any model default (resolution, bucket sizes, caption style) and the override persists
  4. User can create a custom model profile with arbitrary resolution and caption settings
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md -- Model profile schema and built-in presets
- [x] 02-02-PLAN.md -- Override system and custom profile creation

### Phase 3: Image Import and Quality
**Goal**: Users can batch-import images and immediately see which ones are training-ready, which need attention, and how they distribute across resolution buckets
**Depends on**: Phase 1, Phase 2
**Requirements**: IMG-01, IMG-02, IMG-03, IMG-04, IMG-05, IMG-06, IMG-07, IMG-08
**Success Criteria** (what must be TRUE):
  1. User can import a folder of mixed images (PNG, JPG, WEBP, TIFF) and corrupt/invalid files are rejected with clear error messages
  2. Each imported image displays its resolution with a green/red indicator relative to the target training resolution
  3. Images are automatically grouped into aspect ratio buckets based on the selected model, with bucket distribution visible (count per bucket, imbalance flags)
  4. Near-duplicate images are detected via perceptual hashing and flagged with a visual indicator
  5. Basic quality issues (blur, exposure) are detected with pass/fail per image, and upscale-required images show a clear red warning
**Plans**: 3 plans

Plans:
- [x] 03-01-PLAN.md -- TIFF format support, new IssueCode values, and import result models
- [x] 03-02-PLAN.md -- Bucket assignment and blur detection modules
- [x] 03-03-PLAN.md -- Perceptual hash dedup and full batch import pipeline

### Phase 4: Web GUI Foundation
**Goal**: Users can launch the web interface with a single command and browse their imported images in a responsive gallery with per-image status at a glance
**Depends on**: Phase 1, Phase 3
**Requirements**: GUI-01, GUI-02, GUI-03, GUI-09, ARCH-06
**Success Criteria** (what must be TRUE):
  1. Running `klippbok serve` starts a FastAPI backend serving a React SPA on a single port
  2. Image gallery displays a thumbnail grid with click-to-expand behavior
  3. Each thumbnail shows resolution, quality status (pass/fail), and a caption preview
  4. Long-running operations (import, batch processing) display progress indicators
  5. Server generates thumbnails for gallery display (not relying on browser canvas for full-resolution images)
**Plans**: 5 plans

Plans:
- [x] 04-01-PLAN.md -- FastAPI backend shell, API models, images router, thumbnail service, CLI serve command
- [x] 04-02-PLAN.md -- React SPA scaffold with Vite, app shell, routing, zustand, TanStack Query
- [x] 04-03-PLAN.md -- Gallery page with masonry grid, status overlays, duplicate borders, lightbox
- [x] 04-04-PLAN.md -- Import router with SSE progress, settings router, import/settings pages, toast system
- [x] 04-05-PLAN.md -- Build pipeline, SPA deployment to static dir, end-to-end verification

### Phase 5: Interactive Crop Editor
**Goal**: Users can precisely crop any image to a valid training bucket ratio using an interactive editor with gallery selection, optional AI upscaling, and batch crop editing with snap-to-bucket behavior -- the signature feature that no existing tool does well
**Depends on**: Phase 4
**Requirements**: CROP-01, CROP-02, CROP-03, CROP-04, CROP-05, CROP-06, CROP-07, CROP-08, CROP-09, GUI-05
**Success Criteria** (what must be TRUE):
  1. User can click an image in the gallery to open a crop editor with a draggable/resizable rectangle overlay
  2. Releasing a resize snaps the crop rectangle to the nearest valid training aspect ratio; CTRL+resize allows freeform, snapping on key release
  3. Real-time resolution display during crop shows green (downscale OK) or red (upscale quality loss)
  4. Zoom slider and rotation/flip controls (90-degree increments, H/V flip) work on high-resolution source images
  5. Auto-crop places the crop rectangle on the detected subject (falling back to center crop), and the user can adjust the result interactively
**Plans**: 4 plans

Plans:
- [ ] 05-01-PLAN.md -- Types, Zustand store extension, gallery selection mode, route wiring
- [ ] 05-02-PLAN.md -- Backend crop service, auto-crop (MediaPipe), upscale service, API routers
- [ ] 05-03-PLAN.md -- Batch crop editor UI with react-advanced-cropper, bucket snapping, zoom/rotate/flip
- [ ] 05-04-PLAN.md -- Process wizard (upscale step), crop save action, end-to-end verification

### Phase 6: Captioning System
**Goal**: Users can generate, edit, and manage captions for every image in their dataset -- with the correct format automatically selected based on target model
**Depends on**: Phase 2, Phase 4
**Requirements**: CAPT-01, CAPT-02, CAPT-03, CAPT-04, CAPT-05, CAPT-06, CAPT-07, CAPT-08, GUI-04, GUI-06
**Success Criteria** (what must be TRUE):
  1. SD1.5 datasets get booru-style tags generated via WD Tagger v3 (ONNX); SDXL/Flux datasets get natural language captions via existing VLM backends
  2. Caption style is automatically selected based on model but user can override per dataset
  3. User can view and edit captions inline alongside the image preview in the gallery
  4. A configurable trigger word is auto-prepended to all captions, and batch tag operations (add/remove/replace) work across the entire dataset
  5. Caption quality scoring (length, specificity, issues) runs on all captions with results visible per image
**Plans**: 4 plans

Plans:
- [ ] 06-01-PLAN.md -- WD Tagger v3 ONNX backend and [tagger] dependency group
- [ ] 06-02-PLAN.md -- Caption service with model-aware routing, NL captioning, API router
- [ ] 06-03-PLAN.md -- Caption editor UI, PATCH endpoint, settings profile dropdown, generate button
- [ ] 06-04-PLAN.md -- Trigger words, batch tag operations, and caption quality scoring

### Phase 06.1: Caption Provider Configuration (INSERTED)

**Goal:** Users can configure caption providers (LM Studio, NanoGPT, Gemini, JoyCaption), manage API keys, pick models, and generate/edit captions from a dedicated Captioning page with a split-view workspace
**Requirements**: CPROV-01, CPROV-02, CPROV-03, CPROV-04, CPROV-05, CPROV-06
**Depends on:** Phase 6
**Success Criteria** (what must be TRUE):
  1. Global config (~/.klippbok/config.json) stores provider preferences and API keys across projects
  2. Four named providers (LM Studio, NanoGPT, Gemini, JoyCaption) resolve to correct backend configs
  3. Model picker fetches available models from LM Studio and NanoGPT endpoints
  4. Caption generation accepts a provider preset and resolves config server-side
  5. Dedicated CaptionPage with collapsible provider config, thumbnail strip, batch tag ops, and caption editor
  6. Generate Captions moved from GalleryPage to CaptionPage; nav reflects pipeline workflow
**Plans:** 2/2 plans complete

Plans:
- [ ] 06.1-01-PLAN.md -- Backend: global config service, JoyCaption detection, provider routing, API endpoints
- [ ] 06.1-02-PLAN.md -- Frontend: CaptionPage UI, provider config panel, NavBar update, GalleryPage cleanup

### Phase 06.2: Captioning Enhancement: JoyCaption Integration Planning (INSERTED)

**Goal:** Enhance the captioning system with JoyCaption-inspired caption modes, context-only modes for character LoRA training, a multi-stage post-processing pipeline, model-aware token budgets, and trigger word/subject tag injection — applying to all providers and models
**Requirements**: CENH-01, CENH-02, CENH-03, CENH-04, CENH-05, CENH-06, CENH-07, CENH-08, CENH-09, CENH-10
**Depends on:** Phase 6, Phase 6.1
**Success Criteria** (what must be TRUE):
  1. 5 caption modes (Booru Tags, Context Only Tags, Context Only Natural, Descriptive, Straightforward) available across all providers
  2. Context Only modes filter appearance tags (hair, eyes, body type) for character LoRA training
  3. Post-processing pipelines (VLM artifact stripping, token budget trimming) produce clean output
  4. Model-aware token budgets (SD1.5=75, SDXL=150, Flux=225) enforced with smart trimming
  5. Mode dropdown and max-tokens field visible in CaptionPage config section
  6. Over-budget warning indicator visible per image
**Plans:** 4/4 plans complete

Plans:
- [ ] 06.2-01-PLAN.md -- Caption mode types, model updates, prompts rewrite, post-processing pipeline
- [ ] 06.2-02-PLAN.md -- Service routing, router updates, JoyCaption runner mode parameterization
- [ ] 06.2-03-PLAN.md -- Frontend: mode dropdown, max-tokens field, over-budget warning

### Phase 7: Video and CLIP Integration
**Goal**: Users can access existing video pipeline workflows and CLIP-based triage from the web GUI, unifying image and video dataset preparation in one interface
**Depends on**: Phase 4
**Requirements**: GUI-08, ARCH-08
**Success Criteria** (what must be TRUE):
  1. Existing video ingest, scan, and triage workflows are accessible and operable from the web GUI
  2. CLIP-based triage (embedding similarity matching) works with standalone images, not just video frames
**Plans**: 5 plans

Plans:
- [ ] 07-01-PLAN.md -- Video service extraction, video API router with SSE, video thumbnail generation
- [ ] 07-02-PLAN.md -- Triage service (CLIP for images), face embedding service (InsightFace), triage API router
- [ ] 07-03-PLAN.md -- VideoPage with Ingest/Scan/Extract tabs, SSE hooks, NavBar and routing updates
- [ ] 07-04-PLAN.md -- TriagePage with CLIP triage UI, concepts gallery, face clusters, gallery video extensions
- [ ] 07-05-PLAN.md -- Gap closure: POST /triage/concepts/upload file upload endpoint

### Phase 8: Export Pipeline
**Goal**: Users can export their cropped, captioned dataset in the format required by their chosen trainer -- ready to train with no manual file manipulation
**Depends on**: Phase 5, Phase 6
**Requirements**: EXPT-01, EXPT-02, EXPT-03, EXPT-04, EXPT-05, EXPT-06, EXPT-07, GUI-07
**Success Criteria** (what must be TRUE):
  1. User can export as kohya/sd-scripts folder structure (repeats_trigger class/ format) with TOML config
  2. User can export as ai-toolkit format (YAML config + flat image directory)
  3. User can export as OneTrainer format (JSON config + image directory) and SimpleTuner format (multidatabackend.json)
  4. Every export includes correctly paired image + .txt caption files, with images resized/cropped to target bucket dimensions
  5. Export interface in GUI lets user select trainer format, configure options, and download/export the result
**Plans**: TBD

Plans:
- [ ] 08-01: Kohya/sd-scripts export with TOML config generation
- [ ] 08-02: ai-toolkit and OneTrainer export formats
- [ ] 08-03: SimpleTuner export and export UI integration

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 6.1 -> 6.2 -> 7 -> 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Architecture Foundation | 3/3 | Complete | 2026-02-27 |
| 2. Model Configuration | 2/2 | Complete | 2026-02-28 |
| 3. Image Import and Quality | 3/3 | Complete | 2026-02-28 |
| 4. Web GUI Foundation | 5/5 | Complete | 2026-02-28 |
| 5. Interactive Crop Editor | 4/4 | Complete   | 2026-03-03 |
| 6. Captioning System | 4/4 | Complete   | 2026-03-04 |
| 6.1 Caption Provider Config | 2/2 | Complete   | 2026-03-04 |
| 6.2 Caption Enhancement: JoyCaption | 3/3 | Complete   | 2026-03-05 |
| 7. Video and CLIP Integration | 4/5 | Gap closure | 2026-03-05 |
| 8. Export Pipeline | 0/3 | Not started | - |
