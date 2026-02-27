# Requirements: Klippbok v2

**Defined:** 2026-02-27
**Core Value:** Take raw images/video of any size and produce correctly bucketed, captioned, training-ready datasets for any supported diffusion model through an intuitive web interface.

## v1 Requirements

### Image Pipeline

- [ ] **IMG-01**: User can batch import images (PNG, JPG, WEBP, TIFF) via drag-and-drop or file picker
- [ ] **IMG-02**: Corrupt/invalid files are rejected with clear error messages on import
- [ ] **IMG-03**: Each image displays resolution (WxH) with green/red indicator vs target training resolution
- [ ] **IMG-04**: Images are automatically grouped into aspect ratio buckets based on target model
- [ ] **IMG-05**: Bucket distribution is visible (how many images per bucket, flagging imbalanced buckets)
- [ ] **IMG-06**: Near-duplicate images detected via perceptual hashing with visual indicator
- [ ] **IMG-07**: Basic quality filtering: blur detection, exposure assessment with pass/fail per image
- [ ] **IMG-08**: Upscale warning: clear red indicator when source resolution is below target bucket size

### Cropping

- [ ] **CROP-01**: Interactive crop editor with draggable/resizable rectangle overlay on image
- [ ] **CROP-02**: Crop rectangle snaps to nearest valid training aspect ratio on resize release
- [ ] **CROP-03**: CTRL+resize allows freeform resize, snaps to nearest valid bucket ratio on key release
- [ ] **CROP-04**: Real-time resolution display during crop (green=downscale ok, red=upscale quality loss)
- [ ] **CROP-05**: Zoom slider for navigating high-resolution source images
- [ ] **CROP-06**: Rotation controls (90-degree increments) and horizontal/vertical flip
- [ ] **CROP-07**: Auto-crop with subject detection places crop rectangle on detected subject
- [ ] **CROP-08**: Auto-crop falls back to center crop when no subject detected
- [ ] **CROP-09**: User can adjust auto-crop result via interactive crop editor

### Model Configuration

- [ ] **MODL-01**: User can select target model type (SD1.5, SDXL, Flux, custom)
- [ ] **MODL-02**: Selecting model auto-sets resolution presets (SD1.5=512, SDXL/Flux=1024)
- [ ] **MODL-03**: Selecting model auto-sets valid bucket sizes and aspect ratios
- [ ] **MODL-04**: Selecting model auto-sets captioning style default (booru tags for SD1.5, NL for SDXL/Flux)
- [ ] **MODL-05**: User can override any model default (resolution, bucket sizes, caption style)
- [ ] **MODL-06**: Custom model profiles can be created with user-defined resolution and caption settings

### Captioning

- [ ] **CAPT-01**: Booru-style tag generation via WD Tagger v3 (ONNX) for SD1.5 datasets
- [ ] **CAPT-02**: Natural language caption generation via existing VLM backends (Gemini, Replicate, OpenAI-compatible)
- [ ] **CAPT-03**: Caption style automatically selected based on target model (booru for SD1.5, NL for SDXL/Flux)
- [ ] **CAPT-04**: User can override caption style per dataset regardless of model default
- [ ] **CAPT-05**: Manual caption editing: inline text editor per image in gallery view
- [ ] **CAPT-06**: Trigger word injection: auto-prepend configurable trigger token to all captions
- [ ] **CAPT-07**: Batch tag operations: add, remove, or replace tags across all captions at once
- [ ] **CAPT-08**: Caption quality scoring via existing klippbok scoring (length, specificity, issues)

### Web GUI

- [ ] **GUI-01**: FastAPI backend serves React SPA from single `klippbok serve` command
- [ ] **GUI-02**: Image gallery view with thumbnail grid, click to expand/edit
- [ ] **GUI-03**: Gallery shows per-image: thumbnail, resolution, quality status, caption preview
- [ ] **GUI-04**: Inline caption editor alongside image preview in expanded view
- [ ] **GUI-05**: Crop editor accessible from gallery (click image → crop tool)
- [ ] **GUI-06**: Model configuration selector (dropdown/panel) affecting resolution + caption defaults
- [ ] **GUI-07**: Dataset export interface: select trainer format, configure options, download/export
- [ ] **GUI-08**: Video pipeline accessible from GUI (existing ingest, scan, triage workflows)
- [ ] **GUI-09**: Progress indicators for long-running operations (captioning, auto-crop batch, export)

### Export

- [ ] **EXPT-01**: Export dataset as kohya/sd-scripts folder structure (repeats_trigger class/ format)
- [ ] **EXPT-02**: Export dataset as ai-toolkit format (YAML config + flat image directory)
- [ ] **EXPT-03**: Export dataset as OneTrainer format (JSON config + image directory)
- [ ] **EXPT-04**: Export dataset as SimpleTuner format (multidatabackend.json + image directory)
- [ ] **EXPT-05**: Each export includes correctly paired image + .txt caption files
- [ ] **EXPT-06**: Exported images are resized/cropped to target bucket dimensions
- [ ] **EXPT-07**: Export generates trainer-specific config files (TOML for kohya, YAML for ai-toolkit, JSON for OneTrainer)

### Architecture

- [ ] **ARCH-01**: Service layer shared by both CLI and API (no duplicated business logic)
- [ ] **ARCH-02**: New image domain module (`klippbok/image/`) following existing module patterns
- [ ] **ARCH-03**: Unified SamplePair model supporting both image and video targets
- [ ] **ARCH-04**: Image-specific validation (resolution, format, quality) using accumulative ValidationIssue pattern
- [ ] **ARCH-05**: GUI dependencies as optional `[gui]` extra group
- [ ] **ARCH-06**: Server-side thumbnail generation for gallery (browser canvas pixel limits)
- [ ] **ARCH-07**: Existing CLI commands continue to work unchanged
- [ ] **ARCH-08**: Existing CLIP triage extended to work with standalone images

## v2 Requirements

### Advanced Features

- **ADV-01**: Per-image crop memory persisted across sessions (relative coordinates)
- **ADV-02**: Bucket distribution histogram/bar chart visualization
- **ADV-03**: CLIP-based similarity scoring between images (find redundant/outlier images)
- **ADV-04**: Batch auto-crop with review queue (auto-crop all → review/adjust each)
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
| Image upscaling | Actively harmful for training — adds no real detail, introduces artifacts |
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
| IMG-01 | TBD | Pending |
| IMG-02 | TBD | Pending |
| IMG-03 | TBD | Pending |
| IMG-04 | TBD | Pending |
| IMG-05 | TBD | Pending |
| IMG-06 | TBD | Pending |
| IMG-07 | TBD | Pending |
| IMG-08 | TBD | Pending |
| CROP-01 | TBD | Pending |
| CROP-02 | TBD | Pending |
| CROP-03 | TBD | Pending |
| CROP-04 | TBD | Pending |
| CROP-05 | TBD | Pending |
| CROP-06 | TBD | Pending |
| CROP-07 | TBD | Pending |
| CROP-08 | TBD | Pending |
| CROP-09 | TBD | Pending |
| MODL-01 | TBD | Pending |
| MODL-02 | TBD | Pending |
| MODL-03 | TBD | Pending |
| MODL-04 | TBD | Pending |
| MODL-05 | TBD | Pending |
| MODL-06 | TBD | Pending |
| CAPT-01 | TBD | Pending |
| CAPT-02 | TBD | Pending |
| CAPT-03 | TBD | Pending |
| CAPT-04 | TBD | Pending |
| CAPT-05 | TBD | Pending |
| CAPT-06 | TBD | Pending |
| CAPT-07 | TBD | Pending |
| CAPT-08 | TBD | Pending |
| GUI-01 | TBD | Pending |
| GUI-02 | TBD | Pending |
| GUI-03 | TBD | Pending |
| GUI-04 | TBD | Pending |
| GUI-05 | TBD | Pending |
| GUI-06 | TBD | Pending |
| GUI-07 | TBD | Pending |
| GUI-08 | TBD | Pending |
| GUI-09 | TBD | Pending |
| EXPT-01 | TBD | Pending |
| EXPT-02 | TBD | Pending |
| EXPT-03 | TBD | Pending |
| EXPT-04 | TBD | Pending |
| EXPT-05 | TBD | Pending |
| EXPT-06 | TBD | Pending |
| EXPT-07 | TBD | Pending |
| ARCH-01 | TBD | Pending |
| ARCH-02 | TBD | Pending |
| ARCH-03 | TBD | Pending |
| ARCH-04 | TBD | Pending |
| ARCH-05 | TBD | Pending |
| ARCH-06 | TBD | Pending |
| ARCH-07 | TBD | Pending |
| ARCH-08 | TBD | Pending |

**Coverage:**
- v1 requirements: 50 total
- Mapped to phases: 0
- Unmapped: 50 (pending roadmap creation)

---
*Requirements defined: 2026-02-27*
*Last updated: 2026-02-27 after initial definition*
