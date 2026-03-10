# Phase 8: Export Pipeline - Context

**Gathered:** 2026-03-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Export cropped, captioned image datasets in trainer-specific formats (kohya/sd-scripts, ai-toolkit, OneTrainer) — ready to train with no manual file manipulation. Includes OneTrainer launch integration with headless training, GUI launch, TensorBoard embedding, and training lifecycle management.

</domain>

<decisions>
## Implementation Decisions

### Export Output Destination
- Local folder only — no ZIP download
- Text input with smart default (e.g., `./export/{trainer_name}/`) relative to project dir, user can edit
- Overwrite existing folder with warning ("Folder not empty — existing files will be overwritten") but allow it
- Copy files (full copies of images + captions) — self-contained, no symlinks

### Trainer Format Scope
- Three trainers: kohya/sd-scripts, ai-toolkit, OneTrainer (no SimpleTuner)
- OneTrainer is the primary/priority trainer — user's main tool
- Each trainer generates dataset definition + training template with sensible defaults and TODO markers
- kohya: `repeats_trigger class/` folder structure (e.g., `5_sks person/`) with TOML config
- ai-toolkit: YAML config with flat image directory
- OneTrainer: concept JSON (dataset definition) + training preset JSON based on user's "SD 1.5 Lora Character - Prodigy" preset as template
- Existing `trainers.py` registry pattern (`@register_trainer`) extended with image-specific generators

### Image Preparation During Export
- Export only cropped images (`source: "crop"` in manifest) — uncropped originals excluded
- Copy images as-is — already at bucket dimensions from Phase 5, no re-processing
- Keep original filenames (no sequential renaming) — preserves traceability
- Stem-matched `.txt` caption files alongside images — universal trainer convention
- Captions read from manifest and written as new `.txt` files in export folder

### Pre-Export Validation
- Scan for issues before export: images without captions, images with empty captions, unpaired files
- Warning panel with option to proceed anyway or go fix the issues
- Guided empty state if no cropped images found: "No cropped images found. Go to Crop to prepare your images first." with link to /crop

### Export UI & Page Layout
- Dedicated `/export` page with NavBar "Export" link as last item (pipeline endpoint)
- Single page with sections (not wizard): trainer picker, options, summary preview, Export button
- Training section appears only after successful export (hidden before)
- SSE progress bar during export (same pattern as import/cleanup/curation)
- After export: summary + trainer-specific next steps guide

### Export Page Config Options
- Trainer format dropdown (kohya/sd-scripts, ai-toolkit, OneTrainer)
- Repeats number input (default from model profile)
- Trigger word text input (pre-filled from caption config anchor_word, editable)
- Class name text input (default "person", editable) — for kohya folder naming
- Concept name text input (default from project folder name) — for OneTrainer
- Output path text input with smart default

### OneTrainer Launch Integration
- Both headless training (subprocess) AND OneTrainer GUI launch options
- Headless: launch `scripts/train.py` via OneTrainer's venv Python with generated config
- GUI: launch `scripts/train_ui.py` with preset pre-loaded
- OneTrainer install auto-detected at common paths (C:\GenAI\Data\Packages\OneTrainer\, etc) + configurable in Settings
- Validates by checking `venv/Scripts/python.exe` + `scripts/train.py`
- Export works without OneTrainer — training buttons disabled with "configure in Settings" message

### OneTrainer Config Customization
- Key params exposed: base model path, LoRA rank/alpha, epochs, batch size, learning rate, resolution
- Everything else uses Prodigy preset defaults
- Model path: scan `D:\reForge\stable-diffusion-webui-reForge\models\Stable-diffusion\` (configurable in Settings)
- Models listed per subfolder (by model type), default to last-used model
- LoRA output saved inside export folder: `{export_dir}/output/{lora_name}.safetensors`

### TensorBoard Integration
- Embed TensorBoard in an iframe on the Export/Training page
- OneTrainer starts TensorBoard on port 6006 (already configured in preset)
- Live training metrics without reimplementing anything

### Training Lifecycle Management
- Graceful stop button: SIGTERM to OneTrainer subprocess (saves backup before exit)
- Completion: success banner showing LoRA path, final epoch count, training duration
- TensorBoard iframe stays available after completion for reviewing metrics
- Error handling: parse stderr for known patterns (OOM, file not found, CUDA), show clear error message with relevant log snippet

### VRAM Conflict Handling
- Disable GPU features (Curate, Cleanup, Triage) during klippbok-launched training with tooltip: "GPU in use for training"
- Check nvidia-smi for GPU usage before any GPU operation (catches externally-launched training too)
- VRAM threshold: Claude's discretion based on RTX 5080 specs
- Non-GPU features (gallery, crop, caption editing) stay available during training

### Claude's Discretion
- VRAM threshold for GPU busy warning (based on RTX 5080 16GB)
- Exact TensorBoard iframe sizing and placement
- OneTrainer stdout/stderr parsing patterns for progress and error detection
- Export file naming for config files per trainer
- ai-toolkit image-mode YAML structure details
- Common OneTrainer install path list for auto-detection

</decisions>

<specifics>
## Specific Ideas

- User's OneTrainer install: `C:\GenAI\Data\Packages\OneTrainer\` with venv at `venv/Scripts/python.exe`
- User's preferred preset: `training_presets/SD 1.5 Lora Character - Prodigy.json` (Prodigy Plus Schedule Free optimizer, LoRA rank 64, 7 epochs, batch 2, resolution 768)
- OneTrainer concept file format: JSON array of concepts with `path`, `name`, `type: "STANDARD"`, `text.prompt_source: "sample"`, `balancing` (repeats), augmentation settings
- Training preset references concept file via `concept_file_name` field
- Model directory: `D:\reForge\stable-diffusion-webui-reForge\models\Stable-diffusion\` with subfolders by model type
- OneTrainer train entry: `scripts/train.py --config-path <preset.json>`
- OneTrainer GUI entry: `scripts/train_ui.py`
- TensorBoard enabled on port 6006 in user's preset
- User's prior LoRA training: SD1.5 character LoRAs (Yana Haidukevich, Kenzi, Laurine) with 50-68 images, booru tags, 512-768px

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `klippbok/dataset/trainers.py`: Trainer registry with `@register_trainer` decorator — extend for image trainers (currently has musubi + aitoolkit for video)
- `klippbok/dataset/organize.py`: `organize_dataset()` pipeline (validate, filter, copy, generate configs) with `OrganizedSample` and `OrganizeResult` models
- `klippbok/dataset/models.py`: `SamplePair`, `OrganizedSample`, `OrganizeLayout` — reusable for image export
- `klippbok/services/upscale_service.py`: Subprocess + SSE pattern for external tool integration — reuse for OneTrainer launch
- `klippbok/config/model_profiles.py`: `ModelProfile` with `base_resolution`, `caption_style` — informs export defaults
- `klippbok/config/model_defaults.py`: 4 built-in profiles (SD1.5=512, SDXL=1024, Flux=1024, Pony=1024)
- `klippbok/services/global_config_service.py`: Global config at `~/.klippbok/config.json` — store OneTrainer path, model dir, last-used settings

### Established Patterns
- SSE for long-running operations (import, cleanup, curation) — reuse for export progress
- Settings page for tool path configuration (SeedVR2 pattern)
- Subprocess integration via venv Python (SeedVR2 upscaler in upscale_service.py)
- Plain CSS (App.css) — no Tailwind
- Zustand for client state, TanStack Query for server data
- Manifest-driven image tracking with `source: "crop"` flag for cropped images

### Integration Points
- App.tsx routes: add `/export` route within AppLayout
- AppLayout NavBar: add "Export" as last nav item
- Backend: new `export` router + `export_service.py` + extended `trainers.py`
- Settings router: extend for OneTrainer path and model directory configuration
- Global config: persist OneTrainer path, model dir, last-used model, export settings
- Manifest: filter images by `source: "crop"` for export candidates

</code_context>

<deferred>
## Deferred Ideas

- SimpleTuner export format (multidatabackend.json) — not included in Phase 8, can be added later via `@register_trainer("simpletuner")`
- Auto-copy trained LoRA to reForge models directory after training completes
- Export history / re-export tracking
- kohya/sd-scripts and ai-toolkit launch integration (only OneTrainer has launch support in Phase 8)
- Rich training dashboard with loss graphs inside klippbok (TensorBoard handles this)
- Model scan for non-reForge directories (ComfyUI, A1111)

</deferred>

---

*Phase: 08-export-pipeline*
*Context gathered: 2026-03-10*
