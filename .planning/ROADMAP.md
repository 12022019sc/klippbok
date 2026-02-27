# Roadmap: Klippbok v2

## Overview

Klippbok v2 extends the existing video-only LoRA dataset tool into a unified image+video preparation platform with an interactive web GUI. The roadmap builds from architectural foundation through domain modules, web interface, and export -- each phase delivers a coherent, testable capability. The critical path runs through image processing, model-aware configuration, the interactive crop editor (the signature differentiator), and multi-trainer export.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Architecture Foundation** - Service layer, image domain module, unified models, and dependency structure
- [ ] **Phase 2: Model Configuration** - Model profiles with resolution presets, bucket sizes, and caption style defaults
- [ ] **Phase 3: Image Import and Quality** - Batch image import with validation, bucketing, quality filtering, and duplicate detection
- [ ] **Phase 4: Web GUI Foundation** - FastAPI+React shell, image gallery, thumbnails, and progress indicators
- [ ] **Phase 5: Interactive Crop Editor** - Canvas-based crop tool with snap-to-bucket, zoom, rotation, and auto-crop
- [ ] **Phase 6: Captioning System** - Booru tag generation, NL captioning, model-aware defaults, manual editing, and batch operations
- [ ] **Phase 7: Video and CLIP Integration** - Existing video pipeline accessible from GUI, CLIP triage extended to standalone images
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
- [ ] 01-01-PLAN.md -- Service layer extraction (dataset_service, project_service) and CLI refactor
- [ ] 01-02-PLAN.md -- Image domain module (models, probe, validate, discover) and IssueCode extension
- [ ] 01-03-PLAN.md -- Unified SamplePair with type discriminator, discovery target_type, dependency groups

### Phase 2: Model Configuration
**Goal**: Users can select a target model (SD1.5, SDXL, Flux, custom) and get correct resolution presets, bucket sizes, and captioning defaults automatically -- with full override capability
**Depends on**: Phase 1
**Requirements**: MODL-01, MODL-02, MODL-03, MODL-04, MODL-05, MODL-06
**Success Criteria** (what must be TRUE):
  1. Selecting SD1.5 sets base resolution to 512px, valid buckets within 262,144 pixel budget, and booru-style caption default
  2. Selecting SDXL or Flux sets base resolution to 1024px with appropriate buckets and natural language caption default
  3. User can override any model default (resolution, bucket sizes, caption style) and the override persists
  4. User can create a custom model profile with arbitrary resolution and caption settings
**Plans**: TBD

Plans:
- [ ] 02-01: Model profile schema and built-in presets
- [ ] 02-02: Override system and custom profile creation

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
**Plans**: TBD

Plans:
- [ ] 03-01: Image loader with format validation and error handling
- [ ] 03-02: Resolution analysis and model-aware bucketing
- [ ] 03-03: Quality filtering, duplicate detection, and upscale warnings

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
**Plans**: TBD

Plans:
- [ ] 04-01: FastAPI application shell and React SPA scaffold
- [ ] 04-02: Image gallery with thumbnails and status display
- [ ] 04-03: Progress indicator system (SSE streaming)

### Phase 5: Interactive Crop Editor
**Goal**: Users can precisely crop any image to a valid training bucket ratio using an interactive editor -- the signature feature that no existing tool does well
**Depends on**: Phase 4
**Requirements**: CROP-01, CROP-02, CROP-03, CROP-04, CROP-05, CROP-06, CROP-07, CROP-08, CROP-09, GUI-05
**Success Criteria** (what must be TRUE):
  1. User can click an image in the gallery to open a crop editor with a draggable/resizable rectangle overlay
  2. Releasing a resize snaps the crop rectangle to the nearest valid training aspect ratio; CTRL+resize allows freeform, snapping on key release
  3. Real-time resolution display during crop shows green (downscale OK) or red (upscale quality loss)
  4. Zoom slider and rotation/flip controls (90-degree increments, H/V flip) work on high-resolution source images
  5. Auto-crop places the crop rectangle on the detected subject (falling back to center crop), and the user can adjust the result interactively
**Plans**: TBD

Plans:
- [ ] 05-01: Canvas-based crop editor with drag/resize
- [ ] 05-02: Bucket-ratio snapping and resolution indicators
- [ ] 05-03: Zoom, rotation, and flip controls
- [ ] 05-04: Auto-crop with subject detection and center-crop fallback

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
**Plans**: TBD

Plans:
- [ ] 06-01: WD Tagger v3 ONNX integration for booru tags
- [ ] 06-02: NL captioning via existing backends with model-aware selection
- [ ] 06-03: Caption editor UI with inline editing
- [ ] 06-04: Trigger words, batch tag operations, and quality scoring

### Phase 7: Video and CLIP Integration
**Goal**: Users can access existing video pipeline workflows and CLIP-based triage from the web GUI, unifying image and video dataset preparation in one interface
**Depends on**: Phase 4
**Requirements**: GUI-08, ARCH-08
**Success Criteria** (what must be TRUE):
  1. Existing video ingest, scan, and triage workflows are accessible and operable from the web GUI
  2. CLIP-based triage (embedding similarity matching) works with standalone images, not just video frames
**Plans**: TBD

Plans:
- [ ] 07-01: Video pipeline GUI integration
- [ ] 07-02: CLIP triage extension for standalone images

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
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Architecture Foundation | 0/3 | Not started | - |
| 2. Model Configuration | 0/2 | Not started | - |
| 3. Image Import and Quality | 0/3 | Not started | - |
| 4. Web GUI Foundation | 0/3 | Not started | - |
| 5. Interactive Crop Editor | 0/4 | Not started | - |
| 6. Captioning System | 0/4 | Not started | - |
| 7. Video and CLIP Integration | 0/2 | Not started | - |
| 8. Export Pipeline | 0/3 | Not started | - |
