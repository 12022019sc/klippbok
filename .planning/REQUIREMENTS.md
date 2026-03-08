# Requirements: Klippbok v2

**Defined:** 2026-02-27
**Core Value:** Take raw images/video of any size and produce correctly bucketed, captioned, training-ready datasets for any supported diffusion model through an intuitive web interface.

## v1 Requirements

### Image Pipeline

- [x] **IMG-01**: User can batch import images (PNG, JPG, WEBP, TIFF) via drag-and-drop or file picker
- [x] **IMG-02**: Corrupt/invalid files are rejected with clear error messages on import
- [x] **IMG-03**: Each image displays resolution (WxH) with green/red indicator vs target training resolution
- [x] **IMG-04**: Images are automatically grouped into aspect ratio buckets based on target model
- [x] **IMG-05**: Bucket distribution is visible (how many images per bucket, flagging imbalanced buckets)
- [x] **IMG-06**: Near-duplicate images detected via perceptual hashing with visual indicator
- [x] **IMG-07**: Basic quality filtering: blur detection, exposure assessment with pass/fail per image
- [x] **IMG-08**: Upscale warning: clear red indicator when source resolution is below target bucket size

### Cropping

- [x] **CROP-01**: Interactive crop editor with draggable/resizable rectangle overlay on image
- [x] **CROP-02**: Crop rectangle snaps to nearest valid training aspect ratio on resize release
- [x] **CROP-03**: CTRL+resize allows freeform resize, snaps to nearest valid bucket ratio on key release
- [x] **CROP-04**: Real-time resolution display during crop (green=downscale ok, red=upscale quality loss)
- [x] **CROP-05**: Zoom slider for navigating high-resolution source images
- [x] **CROP-06**: Rotation controls (90-degree increments) and horizontal/vertical flip
- [x] **CROP-07**: Auto-crop with subject detection places crop rectangle on detected subject
- [x] **CROP-08**: Auto-crop falls back to center crop when no subject detected
- [x] **CROP-09**: User can adjust auto-crop result via interactive crop editor

### Model Configuration

- [ ] **MODL-01**: User can select target model type (SD1.5, SDXL, Flux, custom)
- [ ] **MODL-02**: Selecting model auto-sets resolution presets (SD1.5=512, SDXL/Flux=1024)
- [ ] **MODL-03**: Selecting model auto-sets valid bucket sizes and aspect ratios
- [ ] **MODL-04**: Selecting model auto-sets captioning style default (booru tags for SD1.5, NL for SDXL/Flux)
- [ ] **MODL-05**: User can override any model default (resolution, bucket sizes, caption style)
- [ ] **MODL-06**: Custom model profiles can be created with user-defined resolution and caption settings

### Captioning

- [x] **CAPT-01**: Booru-style tag generation via WD Tagger v3 (ONNX) for SD1.5 datasets
- [x] **CAPT-02**: Natural language caption generation via existing VLM backends (Gemini, Replicate, OpenAI-compatible)
- [x] **CAPT-03**: Caption style automatically selected based on target model (booru for SD1.5, NL for SDXL/Flux)
- [x] **CAPT-04**: User can override caption style per dataset regardless of model default
- [x] **CAPT-05**: Manual caption editing: inline text editor per image in gallery view
- [x] **CAPT-06**: Trigger word injection: auto-prepend configurable trigger token to all captions
- [x] **CAPT-07**: Batch tag operations: add, remove, or replace tags across all captions at once
- [x] **CAPT-08**: Caption quality scoring via existing klippbok scoring (length, specificity, issues)

### Web GUI

- [ ] **GUI-01**: FastAPI backend serves React SPA from single `klippbok serve` command
- [ ] **GUI-02**: Image gallery view with thumbnail grid, click to expand/edit
- [ ] **GUI-03**: Gallery shows per-image: thumbnail, resolution, quality status, caption preview
- [x] **GUI-04**: Inline caption editor alongside image preview in expanded view
- [x] **GUI-05**: Crop editor accessible from gallery (click image -> crop tool)
- [x] **GUI-06**: Model configuration selector (dropdown/panel) affecting resolution + caption defaults
- [ ] **GUI-07**: Dataset export interface: select trainer format, configure options, download/export
- [x] **GUI-08**: Video pipeline accessible from GUI (existing ingest, scan, triage workflows)
- [ ] **GUI-09**: Progress indicators for long-running operations (captioning, auto-crop batch, export)

### Cleanup

- [x] **CLEAN-01**: User can trigger a cleanup scan from the GUI that analyzes all imported images and videos
- [x] **CLEAN-02**: ML-based person detection identifies images/videos containing a human subject using CLIP + InsightFace
- [x] **CLEAN-03**: Non-matching media is flagged with clear visual indicator and confidence score in the cleanup review page
- [x] **CLEAN-04**: User can review flagged items and confirm removal -- moved to _review/ subfolder, NOT deleted
- [x] **CLEAN-05**: Cleanup handles large folders (1000+) with progress indication and can be cancelled mid-operation

### Dataset Curation

- [ ] **CUR-01**: Multi-signal image scoring (7 signals: InsightFace, pyiqa TOPIQ-NR, Aesthetic V2.5, OpenCV Laplacian, MediaPipe Pose, CLIP zero-shot, pHash) on GPU/CPU
- [ ] **CUR-02**: Composite score with mode-dependent weights (Character: face 40%, technical 25%, aesthetic 20%, other 15%; Style: aesthetic 35%, technical 30%, face 20%, other 15%)
- [ ] **CUR-03**: Quality floor filtering removes bottom N% of images by composite score (default 30%)
- [ ] **CUR-04**: Diversity-maximizing subset selection via apricot FacilityLocation on concatenated CLIP+Pose+Face embeddings
- [x] **CUR-05**: Two-panel review UI with selected images (top grid, score badges) and rejected pool (collapsible, dimmed)
- [ ] **CUR-06**: Click-to-pin/exclude adjustment with re-diversification respecting constraints
- [ ] **CUR-07**: Score breakdown popover with horizontal bar chart showing each scoring dimension
- [ ] **CUR-08**: Pipeline summary with funnel stats (scanned -> passed quality -> selected) and diversity metrics
- [ ] **CUR-09**: Apply action sets gallery selectedImageIds, enables selection mode, navigates to Gallery
- [ ] **CUR-10**: Curation results persist to .klippbok/curation_results.json, loadable on revisit
- [ ] **CUR-11**: Model-aware target count defaults (SD1.5->40, SDXL->80, Flux->100, Pony->70, Custom->60)
- [ ] **CUR-12**: Auto-detect reference face from largest face cluster (no manual face picker needed)
- [x] **CUR-13**: SSE progress for long-running scoring pipeline with stage and per-item progress
- [x] **CUR-14**: NavBar "Curate" link and SelectionToolbar "Curate" button as entry points

### Export

- [ ] **EXPT-01**: Export dataset as kohya/sd-scripts folder structure (repeats_trigger class/ format)
- [ ] **EXPT-02**: Export dataset as ai-toolkit format (YAML config + flat image directory)
- [ ] **EXPT-03**: Export dataset as OneTrainer format (JSON config + image directory)
- [ ] **EXPT-04**: Export dataset as SimpleTuner format (multidatabackend.json + image directory)
- [ ] **EXPT-05**: Each export includes correctly paired image + .txt caption files
- [ ] **EXPT-06**: Exported images are resized/cropped to target bucket dimensions
- [ ] **EXPT-07**: Export generates trainer-specific config files (TOML for kohya, YAML for ai-toolkit, JSON for OneTrainer)

### Architecture

- [x] **ARCH-01**: Service layer shared by both CLI and API (no duplicated business logic)
- [x] **ARCH-02**: New image domain module (`klippbok/image/`) following existing module patterns
- [x] **ARCH-03**: Unified SamplePair model supporting both image and video targets
- [x] **ARCH-04**: Image-specific validation (resolution, format, quality) using accumulative ValidationIssue pattern
- [x] **ARCH-05**: GUI dependencies as optional `[gui]` extra group
- [ ] **ARCH-06**: Server-side thumbnail generation for gallery (browser canvas pixel limits)
- [x] **ARCH-07**: Existing CLI commands continue to work unchanged
- [x] **ARCH-08**: Existing CLIP triage extended to work with standalone images

## v2 Requirements

### Advanced Features

- **ADV-01**: Per-image crop memory persisted across sessions (relative coordinates)
- **ADV-02**: Bucket distribution histogram/bar chart visualization
- **ADV-03**: CLIP-based similarity scoring between images (find redundant/outlier images)
- **ADV-04**: Batch auto-crop with review queue (auto-crop all -> review/adjust each)
- **ADV-05**: Caption comparison view (side-by-side: auto-generated vs edited)
- **ADV-06**: Resumable pipeline operations (checkpoint after each image processed)
- **ADV-07**: Progress bars with ETA for all batch operations
- **ADV-08**: Structured logging with configurable verbosity

### Additional Model Support

- **MODL-07**: Qwen model profile with appropriate defaults
- **MODL-08**: Custom model profile import/export
- **MODL-09**: Model-specific regularization image support (optional)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Built-in LoRA training | Dataset preparation tool, not a trainer. Export to kohya/ai-toolkit/OneTrainer instead. |
| Image generation (txt2img) | Synthetic data is lower quality than real images for LoRA training |
| Image upscaling | Actively harmful for training -- adds no real detail, introduces artifacts |
| Cloud storage integration | Single-user local tool. Use external sync tools if needed. |
| Multi-user / authentication | Internal tool for single developer. No auth complexity. |
| Real-time collaborative editing | Single user. No WebSocket sync needed. |
| Plugin/extension system | Over-engineering. Keep modular internally, accept PRs for extensibility. |
| Dataset augmentation (flip/jitter) | Handled by trainers (flip_aug, color_aug in kohya config), not prep tools |
| Mobile app | Web GUI is sufficient for desktop workflow |
| Regularization image generation | Increasingly unnecessary for modern LoRA training (especially Flux) |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| IMG-01 | Phase 3 | Pending |
| IMG-02 | Phase 3 | Pending |
| IMG-03 | Phase 3 | Pending |
| IMG-04 | Phase 3 | Pending |
| IMG-05 | Phase 3 | Pending |
| IMG-06 | Phase 3 | Pending |
| IMG-07 | Phase 3 | Pending |
| IMG-08 | Phase 3 | Pending |
| CROP-01 | Phase 5 | Complete |
| CROP-02 | Phase 5 | Complete |
| CROP-03 | Phase 5 | Complete |
| CROP-04 | Phase 5 | Complete |
| CROP-05 | Phase 5 | Complete |
| CROP-06 | Phase 5 | Complete |
| CROP-07 | Phase 5 | Complete |
| CROP-08 | Phase 5 | Complete |
| CROP-09 | Phase 5 | Complete |
| MODL-01 | Phase 2 | Complete |
| MODL-02 | Phase 2 | Complete |
| MODL-03 | Phase 2 | Complete |
| MODL-04 | Phase 2 | Complete |
| MODL-05 | Phase 2 | Complete |
| MODL-06 | Phase 2 | Complete |
| CAPT-01 | Phase 6 | Complete |
| CAPT-02 | Phase 6 | Complete |
| CAPT-03 | Phase 6 | Complete |
| CAPT-04 | Phase 6 | Complete |
| CAPT-05 | Phase 6 | Complete |
| CAPT-06 | Phase 6 | Complete |
| CAPT-07 | Phase 6 | Complete |
| CAPT-08 | Phase 6 | Complete |
| GUI-01 | Phase 4 | Pending |
| GUI-02 | Phase 4 | Pending |
| GUI-03 | Phase 4 | Pending |
| GUI-04 | Phase 6 | Complete |
| GUI-05 | Phase 5 | Complete |
| GUI-06 | Phase 6 | Complete |
| GUI-07 | Phase 8 | Pending |
| GUI-08 | Phase 7 | Complete |
| GUI-09 | Phase 4 | Pending |
| CLEAN-01 | Phase 7.1 | Complete |
| CLEAN-02 | Phase 7.1 | Complete |
| CLEAN-03 | Phase 7.1 | Complete |
| CLEAN-04 | Phase 7.1 | Complete |
| CLEAN-05 | Phase 7.1 | Complete |
| CUR-01 | Phase 7.3 | Pending |
| CUR-02 | Phase 7.3 | Pending |
| CUR-03 | Phase 7.3 | Pending |
| CUR-04 | Phase 7.3 | Pending |
| CUR-05 | Phase 7.3 | Complete |
| CUR-06 | Phase 7.3 | Pending |
| CUR-07 | Phase 7.3 | Pending |
| CUR-08 | Phase 7.3 | Pending |
| CUR-09 | Phase 7.3 | Pending |
| CUR-10 | Phase 7.3 | Pending |
| CUR-11 | Phase 7.3 | Pending |
| CUR-12 | Phase 7.3 | Pending |
| CUR-13 | Phase 7.3 | Complete |
| CUR-14 | Phase 7.3 | Complete |
| EXPT-01 | Phase 8 | Pending |
| EXPT-02 | Phase 8 | Pending |
| EXPT-03 | Phase 8 | Pending |
| EXPT-04 | Phase 8 | Pending |
| EXPT-05 | Phase 8 | Pending |
| EXPT-06 | Phase 8 | Pending |
| EXPT-07 | Phase 8 | Pending |
| ARCH-01 | Phase 1 | Complete |
| ARCH-02 | Phase 1 | Complete |
| ARCH-03 | Phase 1 | Complete |
| ARCH-04 | Phase 1 | Complete |
| ARCH-05 | Phase 1 | Complete |
| ARCH-06 | Phase 4 | Pending |
| ARCH-07 | Phase 1 | Complete |
| ARCH-08 | Phase 7 | Complete |

**Coverage:**
- v1 requirements: 74 total
- Mapped to phases: 74
- Unmapped: 0

---
*Requirements defined: 2026-02-27*
*Last updated: 2026-03-08 after Phase 7.3 planning*
