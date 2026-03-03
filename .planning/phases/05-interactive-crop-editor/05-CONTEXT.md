# Phase 5: Interactive Crop Editor - Context

**Gathered:** 2026-03-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver a complete image processing pipeline step: gallery image selection, optional AI upscaling, and interactive batch crop editing with snap-to-bucket behavior. This is the signature feature — no existing tool does bucket-aware cropping well. The crop page follows the malcolmrey/dataset-preparation Gradio Space as the primary UX reference.

**Expanded scope** (decided during discussion): Phase 5 now includes three capabilities:
1. Gallery image selection (click-to-select mode with smart filters)
2. Upscale workflow (SeedVR2 + NMKD-Siax via subprocess)
3. Interactive crop editor (batch grid with bucket snapping)

**Overall pipeline flow:** Import → Gallery (review/select) → Upscale (optional) → Crop → Caption

</domain>

<decisions>
## Implementation Decisions

### Gallery Selection
- Click-to-select mode: toggle button enables selection mode; clicking thumbnails selects (highlighted border) instead of opening lightbox
- Smart filter helpers: Select All, Deselect All, plus filter-based selection ("Select all passing quality", "Select all non-duplicates") leveraging existing quality/duplicate data
- Single "Process" button appears when >=1 image selected — navigates to wizard-style pipeline page (upscale → crop flow)
- Selected image IDs persist in Zustand store (survive page navigation, lost on browser refresh — session only)

### Upscale Workflow
- Subprocess integration (like ffmpeg): klippbok calls SeedVR2's venv Python (`batch_upscale.py`) as a subprocess, parses stdout for progress
- Auto-detect SeedVR2 installation at common paths (e.g., C:\GenAI\Tools\SeedVR2) + environment variables; falls back to manual settings page configuration if not found
- Default upscaler: SeedVR2 3B FP8, 2x scale factor, LAB color correction, VAE tiling enabled, model caching enabled
- NMKD-Siax included as an alternative upscaler option (ESRGAN via spandrel, faster but lower quality)
- Minimal UI: upscaler dropdown (SeedVR2 / NMKD-Siax) + scale factor dropdown (2x default). All other settings use optimal defaults
- Simple progress bar: "Upscaling 3/20 images..." with percentage
- Surface OOM or performance issues to user with clear error messages
- VRAM freed when upscaling completes (subprocess termination handles this automatically)
- 3B FP8 is the right model for training data prep — 7B's quality advantage is lost when images get downscaled to 512-1024px bucket dimensions

### Crop Editor Entry & Layout
- Dedicated route: /crop as a top-level page (not replacing the lightbox)
- "Crop" added as a nav bar item alongside Gallery / Import / Settings
- Batch grid layout (like malcolmrey): all selected images displayed in a scrollable grid, each with its own crop rectangle, rotation controls, and zoom slider
- Responsive columns adapting to screen width, maximum 4 columns wide
- Each card shows: filename + original dimensions + quality badge (sharp/blurry) in header
- +/x buttons on each card for include/exclude from dataset
- Excluded images removed from grid immediately (can be re-added from gallery)

### Crop Interaction
- Global controls at top: Bucket Size dropdown (512 / 768 / 1024) + "Allow Non-Square" checkbox (checked by default)
- Allow Non-Square unchecked = all crops locked to 1:1 square. Checked = full bucket list available (5-13 ratios depending on bucket size)
- Default drag: crop rectangle locked to current bucket aspect ratio. Resizing scales proportionally
- CTRL+drag: freeform resize. Resolution readout updates dynamically. Behavior on CTRL release matches malcolmrey tool (researcher to verify exact behavior)
- Resolution readout below each card: match malcolmrey exactly — green text + down arrow (downscale OK) or red text + up arrow (upscale quality loss) + aspect ratio badge on right (e.g., "1:1", "3:5")
- Rotation/flip controls + zoom slider below resolution readout: match malcolmrey layout (rotation icons left, zoom slider right)

### Auto-crop
- Target content: primarily photos of people (face/body detection well-suited)
- Manual "Auto-crop All" button at top of crop page — not automatic on import
- Full body priority: try to include full body first, only zoom to face if body doesn't fit in any valid bucket ratio
- Center crop fallback when no subject detected (CROP-08)
- No visual indicator needed for center-crop fallback — user will see and adjust manually

### Crop Persistence & Save
- Crops held in browser state (Zustand) during editing — session only, lost on browser close
- "Proceed to Captioning" button saves all crops: server generates actual cropped+resized image files at bucket dimensions
- Original images always preserved — cropped versions generated alongside
- User can navigate back to crop page to re-crop if needed (non-destructive pipeline)

### Claude's Discretion
- Exact crop handle styling and drag behavior implementation details
- NMKD-Siax subprocess integration approach (spandrel or direct realesrgan-ncnn-vulkan)
- Auto-crop subject detection model choice (YOLO, MediaPipe, etc. — researcher to evaluate)
- Exact wizard page layout for the Process flow (upscale → crop transitions)
- Error handling and retry behavior for upscaler subprocess failures

</decisions>

<specifics>
## Specific Ideas

- malcolmrey/dataset-preparation Gradio Space is the primary UX reference — match the look and feel of the crop card layout, resolution readout, rotation controls, and zoom slider
- Reference screenshots saved in repo root: `dataset-prep-info.png`, `dataset-prep-with-image.png`
- SeedVR2 tool exists at `C:\GenAI\Tools\SeedVR2` with its own isolated venv — subprocess integration should call `venv/Scripts/python.exe batch_upscale.py`
- SeedVR2 test run showed: 905x1096 → 2160x2614 in ~8.7s, peak 6.52GB VRAM with 3B FP8, LAB color correction, VAE tiling
- LAB color correction is the best/most accurate choice for photographic content — preserves upscaler's enhanced luminance detail while matching original color profile
- User has RTX 5080 16GB VRAM — all presets viable, 3B FP8 is the sweet spot for training data
- Preferred upscalers: SeedVR2 (diffusion-based, higher quality) and 4x_NMKD-Siax_200k (ESRGAN, faster)

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `klippbok/image/bucket.py`: `assign_to_bucket()` and `needs_upscale()` — core bucket assignment logic by nearest aspect ratio
- `klippbok/config/model_profiles.py`: `generate_buckets()` produces valid bucket dimensions from base resolution + step size. Buckets: 512→5, 768→9, 1024→13 valid ratios
- `klippbok/config/model_profiles.py`: `ModelProfile`, `BucketConfig` — frozen Pydantic models for model configuration
- `frontend/src/types/image.ts`: `GalleryItem` type with id, width, height, bucket, resolution_ok, quality_pass, is_near_duplicate fields
- `frontend/src/components/Lightbox/ImageLightbox.tsx`: existing lightbox (stays for non-edit viewing)
- `frontend/src/components/Gallery/StatusStrip.tsx`: resolution/quality/bucket display pattern
- `frontend/src/hooks/useImages.ts`: TanStack Query hook for gallery data
- `frontend/src/hooks/useImportEvents.ts`: SSE progress pattern (reusable for upscale progress)
- `frontend/src/stores/appStore.ts`: Zustand flat store pattern — extend for selection state and crop state

### Established Patterns
- Plain CSS (App.css + index.css) — no Tailwind or CSS modules
- Zustand for client state, TanStack Query for server data
- React Router v7 layout routing with AppLayout wrapper
- SSE for long-running operation progress (import pattern reusable for upscale)
- FastAPI app factory with routers registered before StaticFiles mount
- SHA256[:16] of relative_path as stable image ID

### Integration Points
- App.tsx routes: add `/crop` route within AppLayout
- AppLayout nav bar: add "Crop" nav item
- GalleryPage: add selection mode toggle + "Process" button
- Backend: new routers for crop operations (save crop, apply crops) and upscale operations (start upscale, SSE progress)
- Settings router: extend for SeedVR2/NMKD-Siax path configuration
- Subprocess pattern: similar to ffmpeg calls in `klippbok/video/_ffmpeg.py`

</code_context>

<deferred>
## Deferred Ideas

### Roadmap & Requirements Updates Needed
- **REQUIREMENTS.md**: Remove "Image upscaling" from Out of Scope table — it's now confirmed in-scope (SeedVR2 + NMKD-Siax)
- **ROADMAP.md Phase 5 description**: Update to reflect expanded scope (gallery selection + upscaling + crop editor)
- **Phase 6 (Captioning)**: Receives pre-cropped images from Phase 5's "Proceed to Captioning" handoff. Caption UI should display cropped images, not originals. Phase 6 planning must account for this pipeline connection.
- **Phase 8 (Export)**: EXPT-06 ("Exported images are resized/cropped to target bucket dimensions") may need scope adjustment — if images are already cropped to bucket dimensions in Phase 5, export may just package them rather than re-cropping.
- **Nav bar evolution**: Phase 5 adds "Crop". Phase 6 may add "Caption". Consider whether the pipeline wizard approach (Process button) should eventually unify all steps.

### Future Enhancements
- ADV-01: Per-image crop memory persisted across sessions (currently session-only by decision)
- ADV-04: Batch auto-crop with review queue (auto-crop all → review/adjust each) — partially covered by "Auto-crop All" button
- Backend crop coordinate persistence to manifest for cross-session recovery
- SeedVR2 7B model option for non-training use cases (wallpapers, prints)
- Additional upscaler models beyond SeedVR2 and NMKD-Siax

</deferred>

---

*Phase: 05-interactive-crop-editor*
*Context gathered: 2026-03-03*
