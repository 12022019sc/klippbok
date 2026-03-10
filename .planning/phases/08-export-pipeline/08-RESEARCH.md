# Phase 8: Export Pipeline - Research

**Researched:** 2026-03-10
**Domain:** Multi-trainer dataset export + OneTrainer subprocess integration
**Confidence:** HIGH (heavily grounded in existing codebase patterns)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **Export output**: Local folder only — no ZIP download
- **Output path**: Text input with smart default `./export/{trainer_name}/` relative to project dir; user can edit; overwrite with warning; copy files (no symlinks)
- **Trainer scope**: Three trainers only — kohya/sd-scripts, ai-toolkit, OneTrainer (no SimpleTuner)
- **OneTrainer is primary**: User's main tool; prioritize over others
- **Config format per trainer**: kohya = TOML, ai-toolkit = YAML, OneTrainer = concept JSON + training preset JSON
- **kohya folder**: `{repeats}_{trigger_word} {class_name}/` (e.g., `5_sks person/`)
- **ai-toolkit**: YAML config + flat image directory
- **OneTrainer**: Concept JSON array + training preset JSON based on user's "SD 1.5 Lora Character - Prodigy" preset
- **Extend existing**: `trainers.py` registry pattern (`@register_trainer`) extended with image-specific generators
- **Image selection**: Export only `source: "crop"` images from manifest; originals excluded
- **Images as-is**: Already at bucket dimensions from Phase 5 — no re-processing; keep original filenames
- **Captions**: Read from manifest `caption` field; write new `.txt` files alongside images in export folder
- **Pre-export validation**: Scan for images without captions, empty captions, unpaired files; warning panel with proceed anyway option
- **Empty state**: Guided empty state if no cropped images — "No cropped images found. Go to Crop..." with link
- **Export page**: Dedicated `/export` route; "Export" as last NavBar item; single page not wizard
- **Page sections**: Trainer picker, options, summary preview, Export button; Training section appears only after successful export
- **SSE progress**: Same pattern as import/cleanup/curation
- **Training section**: Appears after successful export only
- **Config options exposed**: Trainer format dropdown, repeats number input, trigger word (pre-filled from anchor_word), class name (default "person"), concept name (default from project folder name), output path
- **OneTrainer launch**: Both headless (`scripts/train.py`) AND GUI (`scripts/train_ui.py`) launch options
- **OneTrainer detection**: Auto-detect at common paths + configurable in Settings; validate via `venv/Scripts/python.exe` + `scripts/train.py`
- **Export works without OneTrainer**: Training buttons disabled with "configure in Settings" message
- **OneTrainer key params exposed**: base model path, LoRA rank/alpha, epochs, batch size, learning rate, resolution
- **Model path**: Scan `D:\reForge\stable-diffusion-webui-reForge\models\Stable-diffusion\` (configurable in Settings); listed per subfolder; default to last-used model
- **LoRA output location**: `{export_dir}/output/{lora_name}.safetensors`
- **TensorBoard**: Embed in iframe on Export page; port 6006 (already configured in user's preset)
- **Graceful stop**: SIGTERM to OneTrainer subprocess
- **Completion**: Success banner with LoRA path, final epoch count, training duration; TensorBoard stays available
- **Error handling**: Parse stderr for OOM, file not found, CUDA errors; show error message + relevant log snippet
- **VRAM conflict**: Disable GPU features (Curate, Cleanup, Triage) during klippbok-launched training with tooltip; check nvidia-smi for GPU usage before any GPU operation
- **Non-GPU features stay available**: Gallery, crop, caption editing remain available during training

### Claude's Discretion

- VRAM threshold for GPU busy warning (based on RTX 5080 16GB)
- Exact TensorBoard iframe sizing and placement
- OneTrainer stdout/stderr parsing patterns for progress and error detection
- Export file naming for config files per trainer
- ai-toolkit image-mode YAML structure details
- Common OneTrainer install path list for auto-detection

### Deferred Ideas (OUT OF SCOPE)

- SimpleTuner export format (multidatabackend.json)
- Auto-copy trained LoRA to reForge models directory after training completes
- Export history / re-export tracking
- kohya/sd-scripts and ai-toolkit launch integration (OneTrainer only has launch support)
- Rich training dashboard with loss graphs inside klippbok (TensorBoard handles this)
- Model scan for non-reForge directories (ComfyUI, A1111)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| EXPT-01 | Export dataset as kohya/sd-scripts folder structure (repeats_trigger class/ format) | Folder naming pattern documented; TOML config generator maps to existing `@register_trainer` pattern |
| EXPT-02 | Export dataset as ai-toolkit format (YAML config + flat image directory) | Existing `aitoolkit` video trainer shows structure; image-mode YAML is simpler (no video fields) |
| EXPT-03 | Export dataset as OneTrainer format (JSON config + image directory) | Concept JSON + preset JSON format documented from CONTEXT specifics |
| EXPT-04 | Export dataset as SimpleTuner format | DEFERRED — out of scope for Phase 8 |
| EXPT-05 | Each export includes correctly paired image + .txt caption files | Manifest `caption` field read; `.txt` files written during export; stem-matched convention |
| EXPT-06 | Exported images resized/cropped to target bucket dimensions | Already done by Phase 5 crop — no re-processing needed; copy-as-is |
| EXPT-07 | Export generates trainer-specific config files (TOML for kohya, YAML for ai-toolkit, JSON for OneTrainer) | Maps to `@register_trainer` image generators; config file naming conventions documented |
| GUI-07 | Dataset export interface: select trainer format, configure options, download/export | Single-page `/export` route; trainer picker + options form + SSE progress; post-export training panel |
</phase_requirements>

---

## Summary

Phase 8 implements a three-trainer export pipeline plus OneTrainer launch integration. The codebase already has all the foundational infrastructure: the `@register_trainer` registry in `trainers.py`, SSE progress pattern from `cleanup.py`/`curation.py`, subprocess management from `upscale_service.py`, global config persistence via `global_config_service.py`, and manifest-based image tracking with `source: "crop"` filtering.

The export service is a new image-domain parallel to the existing video `organize_dataset()` pipeline. It differs in that it reads from the manifest (not a filesystem scan), filters by `source: "crop"`, writes captions from manifest data (not filesystem pairing), and generates three image-specific trainer configs instead of the two video-specific ones.

The OneTrainer launch integration is the most novel piece — it reuses the `upscale_service.py` Popen+threading+SSE pattern, extended with stderr parsing for training errors and a graceful stop mechanism. The TensorBoard iframe is a passthrough HTML element with no server-side implementation needed.

**Primary recommendation:** Build the export service as a pure function library (`export_service.py`) consumed by the new `export` router, following the exact SSE + asyncio.Queue pattern from `cleanup.py`. Extend `trainers.py` with three new image-specific `@register_trainer` functions. Keep OneTrainer process management in `onetrainer_service.py` parallel to `upscale_service.py`.

---

## Standard Stack

### Core (no new dependencies needed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| shutil | stdlib | File copy operations | Already used in `organize.py` |
| json | stdlib | JSON config generation (OneTrainer) | Used throughout project |
| tomllib/tomli_w | stdlib (3.11 read) / third-party write | TOML config generation (kohya) | Need `tomli_w` for writing |
| yaml (PyYAML) | already in venv | YAML config generation (ai-toolkit) | Already used for data schema |
| subprocess | stdlib | OneTrainer process launch | Pattern from `upscale_service.py` |
| asyncio | stdlib | SSE event bus | Pattern from `cleanup.py` |
| threading | stdlib | stdout reader thread | Pattern from `upscale_service.py` |
| sse-starlette | already installed | SSE streaming | Pattern from all existing routers |
| React + TanStack Query + Zustand | existing | Frontend | Project standard |

### TOML Writing Note (HIGH confidence)

Python 3.11 includes `tomllib` for **reading** only. For **writing** TOML, use `tomli_w`:
- Check if it's already in venv: `pip show tomli_w`
- If absent: `pip install tomli_w`
- Alternative: hand-write TOML strings (as the existing musubi generator does) — avoids dependency entirely

The existing `generate_musubi_config` builds TOML as string concatenation, not via a library. **Recommend the same approach for kohya** — it's simpler, more readable, and produces well-commented output with TODO markers.

### Installation (if needed)

```bash
# Only if tomli_w is not already present (check first)
pip install tomli_w
# PyYAML is likely already present (used by data_schema.py)
pip show PyYAML
```

---

## Architecture Patterns

### Recommended File Structure

```
klippbok/
├── api/routers/
│   └── export.py              # NEW: POST /export/start, GET /export/{id}/events,
│                              #      POST /export/{id}/cancel, GET /export/status
│                              #      POST /export/launch-onetrainer
│                              #      POST /export/stop-onetrainer
├── services/
│   ├── export_service.py      # NEW: image export pipeline (manifest read, file copy,
│   │                          #      caption write, validation scan)
│   └── onetrainer_service.py  # NEW: OneTrainer detection, launch, cancel, progress
└── dataset/
    └── trainers.py            # EXTEND: add @register_trainer("kohya"),
                               #         @register_trainer("aitoolkit_image"),
                               #         @register_trainer("onetrainer")
```

```
frontend/src/
├── pages/
│   └── ExportPage.tsx         # NEW: /export route
├── components/Export/
│   ├── TrainerPicker.tsx      # Trainer format selector
│   ├── ExportOptions.tsx      # Form: repeats, trigger word, class, concept name, output path
│   ├── ExportSummary.tsx      # Pre-export validation warnings + image count
│   ├── ExportProgress.tsx     # SSE progress bar (reuse cleanup pattern)
│   └── TrainingPanel.tsx      # Post-export: OneTrainer launch, TensorBoard iframe,
│                              #              stop button, completion banner
└── hooks/
    └── useExportEvents.ts     # SSE hook (mirrors useCleanupEvents pattern)
```

### Pattern 1: Manifest-Filtered Image Export

**What:** Read manifest, filter `source: "crop"`, copy image + write `.txt` caption to export dir.
**When to use:** Core export logic in `export_service.py`.

```python
# Source: klippbok/api/routers/crop.py _register_crop_outputs + cleanup.py pattern
def get_export_candidates(project_dir: Path) -> list[dict]:
    """Return manifest image entries with source='crop'."""
    from klippbok.services.project_service import load_manifest
    manifest = load_manifest(project_dir)
    if not manifest:
        return []
    return [
        entry for entry in manifest.get("images", [])
        if entry.get("source") == "crop"
    ]

def validate_export_candidates(entries: list[dict]) -> list[dict]:
    """Return list of validation issues: missing caption, empty caption."""
    issues = []
    for entry in entries:
        caption = entry.get("caption", "")
        if not caption:
            issues.append({"path": entry["path"], "issue": "missing_caption"})
        elif not caption.strip():
            issues.append({"path": entry["path"], "issue": "empty_caption"})
    return issues
```

### Pattern 2: SSE Export Progress (mirrors cleanup.py exactly)

**What:** asyncio.Queue per op_id, background coroutine, None sentinel.
**When to use:** Export operation spanning potentially 100+ file copies.

```python
# Source: klippbok/api/routers/cleanup.py _run_cleanup_bg pattern
_export_tasks: dict[str, asyncio.Task] = {}
_export_queues: dict[str, asyncio.Queue] = {}

async def _run_export_bg(op_id: str, project_dir: Path, config: ExportConfig) -> None:
    queue = _export_queues[op_id]
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: perform_export(project_dir, config,
                                   progress_cb=lambda c, t: loop.call_soon_threadsafe(
                                       queue.put_nowait,
                                       {"event": "export_progress",
                                        "data": {"current": c, "total": t}},
                                   ))
        )
        await queue.put({"event": "export_done", "data": {"status": "complete", ...}})
    except Exception as exc:
        await queue.put({"event": "export_error", "data": {"message": str(exc)}})
    finally:
        await queue.put(None)
```

### Pattern 3: `@register_trainer` Image Generator

**What:** New trainer functions registered in `trainers.py`.
**When to use:** Each of the three trainer configs.

```python
# Source: klippbok/dataset/trainers.py pattern
# New signature for image trainers (different from video trainers)

@register_trainer("kohya")
def generate_kohya_config(
    entries: list[dict],    # manifest image entries (source="crop")
    output_dir: Path,
    export_config: "ImageExportConfig",  # repeats, trigger_word, class_name, etc.
    dry_run: bool = False,
) -> Path:
    """Generate kohya/sd-scripts dataset TOML.

    Output structure:
        {output_dir}/
            {repeats}_{trigger_word} {class_name}/
                image1.jpg
                image1.txt
            kohya_config.toml
    """
    ...

@register_trainer("onetrainer")
def generate_onetrainer_config(
    entries: list[dict],
    output_dir: Path,
    export_config: "ImageExportConfig",
    dry_run: bool = False,
) -> tuple[Path, Path]:  # concept_json, preset_json
    """Generate OneTrainer concept JSON + training preset JSON."""
    ...
```

**IMPORTANT:** The existing `trainers.py` generators accept `(samples, output_dir, config, layout, dry_run)` for video. Image generators have a different signature. Consider either:
1. Adding new image-specific functions to `trainers.py` with a different registration namespace (e.g., `register_image_trainer`)
2. Or simply implement them as standalone functions in `export_service.py` without the registry

**Recommendation:** Implement as standalone functions in `export_service.py` — the registry is designed for the CLI `organize_dataset()` flow, not the GUI export flow. No registry overhead needed for three hardcoded trainers.

### Pattern 4: OneTrainer Subprocess (mirrors upscale_service.py)

**What:** Popen + background thread + asyncio.Queue for progress.
**When to use:** OneTrainer headless and GUI launch.

```python
# Source: klippbok/services/upscale_service.py start_upscale pattern

_ot_procs: dict[str, subprocess.Popen] = {}

async def launch_onetrainer_headless(
    onetrainer_root: Path,
    preset_path: Path,
    queue: asyncio.Queue,
    op_id: str,
) -> None:
    python_exe = onetrainer_root / "venv" / "Scripts" / "python.exe"
    train_script = onetrainer_root / "scripts" / "train.py"
    cmd = [str(python_exe), str(train_script), "--config-path", str(preset_path)]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        cwd=str(onetrainer_root),
    )
    _ot_procs[op_id] = proc

    loop = asyncio.get_event_loop()
    thread = threading.Thread(
        target=_ot_stdout_reader,
        args=(proc, queue, loop, op_id),
        daemon=True,
    )
    thread.start()

def stop_onetrainer(op_id: str) -> bool:
    proc = _ot_procs.get(op_id)
    if proc is None:
        return False
    proc.terminate()  # SIGTERM — saves backup before exit per OneTrainer behavior
    return True
```

### Pattern 5: OneTrainer Detection (mirrors detect_seedvr2)

**What:** Check common paths + configurable path from global config.

```python
# Source: klippbok/services/upscale_service.py _SEEDVR2_COMMON_PATHS pattern

_ONETRAINER_COMMON_PATHS: list[Path] = [
    Path(r"C:\GenAI\Data\Packages\OneTrainer"),
    Path.home() / "GenAI" / "Data" / "Packages" / "OneTrainer",
    Path(r"C:\OneTrainer"),
    Path.home() / "OneTrainer",
]

def detect_onetrainer(onetrainer_path: str | None = None) -> Path | None:
    """Find OneTrainer installation.

    Checks: configured path from global config > common paths.
    Validates: venv/Scripts/python.exe AND scripts/train.py both present.
    """
    candidates = []
    if onetrainer_path:
        candidates.append(Path(onetrainer_path))
    candidates.extend(_ONETRAINER_COMMON_PATHS)

    for candidate in candidates:
        python = candidate / "venv" / "Scripts" / "python.exe"
        train = candidate / "scripts" / "train.py"
        if python.is_file() and train.is_file():
            return candidate
    return None
```

### Pattern 6: VRAM GPU Busy Check

**What:** Check nvidia-smi before launching GPU operations during training.

```python
# Claude's discretion — recommended implementation

import subprocess

def get_gpu_vram_used_mb() -> int | None:
    """Query nvidia-smi for current VRAM usage in MB. Returns None if unavailable."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return int(result.stdout.strip().split("\n")[0])
    except Exception:
        pass
    return None

VRAM_BUSY_THRESHOLD_MB = 4096  # Claude's discretion: 4GB used = busy
# RTX 5080 has 16GB VRAM. During training, ~8-14GB is used.
# Anything above 4GB usage when no training is running = external training active.
```

### Anti-Patterns to Avoid

- **Don't re-run crop/resize during export**: Images are already at bucket dimensions from Phase 5. Copying as-is is correct.
- **Don't use the video `organize_dataset()` pipeline**: That validates a filesystem, not a manifest. The image export reads the manifest directly.
- **Don't use the existing `trainers.py` registry dispatch for image export**: The `generate_trainer_config` function expects `OrganizedSample` models with video-specific fields. New image generators use a different input shape.
- **Don't symlink**: CONTEXT.md mandates full copies for self-contained export.
- **Don't write captions from filesystem**: Read from manifest `caption` field, not from `.txt` files on disk — the manifest may have edits that differ from disk state.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSE streaming | Custom websocket or polling | `sse-starlette` + existing pattern | Pattern proven across 4 features |
| Subprocess output | Custom pipe reader | Threading pattern from `upscale_service.py` | Handles blocking I/O without event loop starvation |
| Atomic config writes | Raw `open()` | `global_config_service.save_global_config()` | Atomic temp+replace already implemented |
| Manifest reading | JSON parse from scratch | `project_service.load_manifest()` | Handles missing manifest, version checks |
| Progress feedback | Polling endpoint | SSE asyncio.Queue pattern | Already in use across import, cleanup, curation |
| TensorBoard embedding | Reimplement metrics | `<iframe src="http://localhost:6006">` | OneTrainer already starts TB; just embed |
| TOML generation | tomli_w library | String concatenation (like musubi generator) | Simpler, produces commented output, no extra dep |

**Key insight:** Every infrastructure piece (SSE, subprocess, manifest, progress) is already implemented and proven. This phase is primarily about connecting existing pieces in a new configuration and writing three trainer config generators.

---

## Common Pitfalls

### Pitfall 1: Kohya Folder Naming Convention

**What goes wrong:** Using wrong separator or format — kohya expects exactly `{N}_{trigger} {class}/` with underscore between number and trigger, and space between trigger and class.
**Why it happens:** The convention looks like it might use all underscores or all spaces.
**How to avoid:** Folder name is `f"{repeats}_{trigger_word} {class_name}"` — underscore between count and trigger, space between trigger and class. Example: `5_sks person`, `10_natahrie woman`.
**Warning signs:** Training fails with "no training data found" or bucket assignment errors.

### Pitfall 2: Captions Written from Manifest vs Disk

**What goes wrong:** Reading caption `.txt` files from disk rather than from manifest `caption` field — misses inline edits made via the Caption page UI.
**Why it happens:** It seems simpler to pair by filename.
**How to avoid:** Always read `entry["caption"]` from the manifest dict. The manifest is the source of truth for caption state.
**Warning signs:** Exported captions lag behind what user edited in the GUI.

### Pitfall 3: OneTrainer stdout Parser Missing Progress

**What goes wrong:** OneTrainer doesn't emit a consistent "N/M" pattern — it uses Python `tqdm` which produces ANSI escape codes and carriage returns.
**Why it happens:** stdout reader assumes clean line-by-line output like SeedVR2.
**How to avoid:** Use a regex that strips ANSI codes and handles `\r` line endings. Alternatively, parse epoch-level markers from text like `"Epoch X/Y"` which are reliably printed.
**Recommended pattern:**
```python
epoch_pattern = re.compile(r"Epoch\s+(\d+)/(\d+)", re.IGNORECASE)
step_pattern = re.compile(r"(\d+)it\s*\[", re.IGNORECASE)  # tqdm "N it [" format
```

### Pitfall 4: OOM Error Detection

**What goes wrong:** CUDA OOM errors appear on stderr (sometimes stdout) mid-training; must be distinguished from normal training output.
**How to avoid:** Scan for known patterns:
```python
OOM_PATTERNS = ["OutOfMemoryError", "CUDA out of memory", "out of memory", "OOM"]
FILE_NOT_FOUND = ["No such file or directory", "FileNotFoundError"]
CUDA_ERROR = ["CUDA error", "CUDA initialization"]
```

### Pitfall 5: Export Overwrites Without Warning

**What goes wrong:** Silently overwriting existing export folder loses previous export (e.g., a trained LoRA in `{export_dir}/output/`).
**Why it happens:** `shutil.copy2` overwrites by default.
**How to avoid:** Pre-export validation checks if output dir is non-empty and shows a warning panel ("Folder not empty — existing files will be overwritten, including any trained LoRAs"). User explicitly confirms before proceeding.

### Pitfall 6: OneTrainer Preset JSON Paths

**What goes wrong:** The preset JSON references absolute paths (`concept_file_name`, `model.path`, `output_dir`) that differ between export runs.
**Why it happens:** Presets are designed to be reused; paths are embedded.
**How to avoid:** Generate a fresh preset JSON for each export run using the user's "SD 1.5 Lora Character - Prodigy" preset as a **template** — read the template, substitute paths, write a new `training_preset.json` in the export dir.

### Pitfall 7: Windows Path Separators in Config Files

**What goes wrong:** Backslashes in TOML/YAML/JSON config paths cause failures in OneTrainer (Python on Windows handles both, but the YAML parser may not).
**Why it happens:** `Path` objects on Windows use backslashes.
**How to avoid:** Use `path.as_posix()` or `str(path).replace("\\", "/")` when writing paths to config files. The existing `_to_forward_slash()` helper in `trainers.py` does this.

---

## Trainer Config Format Details

### kohya/sd-scripts TOML

**Folder structure:**
```
{export_dir}/
    {repeats}_{trigger_word} {class_name}/   # e.g. "5_sks person"
        image1.jpg
        image1.txt
        ...
    kohya_config.toml
```

**TOML content:**
```toml
# kohya/sd-scripts dataset config
# Generated by klippbok export

[general]
shuffle_caption = false
caption_extension = ".txt"
keep_tokens = 1

[[datasets]]
resolution = 512
batch_size = 1
num_repeats = 5  # or per user input

  [[datasets.subsets]]
  image_dir = "./5_sks person"
  class_tokens = "sks person"
```

**Key notes:**
- The `class_tokens` should match the folder name stem (after `{repeats}_`).
- `resolution` = the active model profile's `base_resolution` (512 for SD1.5).
- Training TOML separates dataset config from network config — only dataset TOML generated here; network TOML is separate (user provides).

### ai-toolkit YAML (image mode)

**Folder structure:**
```
{export_dir}/
    images/           # flat directory of images + .txt files
        image1.jpg
        image1.txt
        ...
    aitoolkit_config.yaml
```

**YAML dataset section (image mode, not video):**
```yaml
datasets:
  - folder_path: "./images"
    caption_ext: "txt"
    resolution: [512, 512]   # or [1024, 1024] for SDXL
```

Note: `is_video: true` is NOT included (that was the video generator). For images, omit the `is_video` field entirely.

### OneTrainer Format

**Folder structure:**
```
{export_dir}/
    images/
        image1.jpg
        image1.txt
        ...
    concept.json
    training_preset.json
    output/
        {lora_name}.safetensors    # written by OneTrainer during training
```

**concept.json (array of one concept):**
```json
[
  {
    "name": "natahrie",
    "uuid": "{generated-uuid}",
    "description": "",
    "type": "STANDARD",
    "path": "C:/path/to/export/images",
    "prompt_source": "sample",
    "include_subdirectories": false,
    "image_variations": [
      {
        "resolution": 512,
        "aspect_ratio_bucketing": true,
        "target_frames": 1,
        "image_augmentation_crop_jitter": 0.0
      }
    ],
    "text_variations": [
      {
        "prompt": "",
        "probability": 1.0,
        "noised_probability": 0.0
      }
    ],
    "balancing": "REPEATS",
    "repeats": 5,
    "samples_to_train": 0,
    "loss_weight": 1.0,
    "ignore_concept": false,
    "sample_skipping": false
  }
]
```

**training_preset.json:** Based on user's "SD 1.5 Lora Character - Prodigy" template — read from `{onetrainer_root}/training_presets/SD 1.5 Lora Character - Prodigy.json` (if OneTrainer is installed), substitute:
- `concept_file_name` → absolute path to generated `concept.json`
- `output_model_destination` → `{export_dir}/output/{lora_name}.safetensors`
- `base_model_name` → user-selected model path
- `lora_rank` / `lora_alpha` → user input
- `epochs` → user input
- `batch_size` → user input
- `learning_rate` → user input

If OneTrainer is not installed, use a hardcoded template with the user's known preset values (LoRA rank 64, 7 epochs, batch 2, Prodigy optimizer).

---

## Code Examples

### Manifest Image Filtering

```python
# Source: klippbok/api/routers/crop.py _register_crop_outputs pattern
# and klippbok/services/project_service.py load_manifest

def get_export_candidates(project_dir: Path) -> list[dict]:
    """Return manifest image entries eligible for export (source='crop')."""
    from klippbok.services.project_service import load_manifest
    manifest = load_manifest(project_dir)
    if not manifest:
        return []
    return [
        entry for entry in manifest.get("images", [])
        if entry.get("source") == "crop"
    ]
```

### Global Config Extension for OneTrainer Path

```python
# Source: klippbok/services/global_config_service.py pattern

def get_onetrainer_config() -> dict:
    """Load OneTrainer-specific config from global config."""
    config = load_global_config()
    return config.get("onetrainer", {})

def save_onetrainer_config(onetrainer_path: str | None, model_dir: str | None,
                           last_used_model: str | None) -> None:
    """Persist OneTrainer paths to global config."""
    config = load_global_config()
    ot = config.setdefault("onetrainer", {})
    if onetrainer_path is not None:
        ot["install_path"] = onetrainer_path
    if model_dir is not None:
        ot["model_dir"] = model_dir
    if last_used_model is not None:
        ot["last_used_model"] = last_used_model
    save_global_config(config)
```

### Export Config Defaults from Active Profile

```python
# Source: klippbok/config/model_profiles.py ModelProfile + manifest active_profile

def get_export_defaults(project_dir: Path) -> dict:
    """Get sensible export defaults from active model profile."""
    from klippbok.config.model_config import get_profile
    from klippbok.services.project_service import load_manifest

    manifest = load_manifest(project_dir)
    active_profile = manifest.get("active_profile", "sd15") if manifest else "sd15"
    anchor_word = manifest.get("anchor_word", "") if manifest else ""
    profile = get_profile(active_profile)

    return {
        "resolution": profile.base_resolution,
        "default_repeats": 5,  # sensible default
        "trigger_word": anchor_word,
        "class_name": "person",
        "concept_name": project_dir.name,  # folder name as concept name
    }
```

### Settings Router Extension for OneTrainer Path

```python
# Source: klippbok/api/routers/settings.py pattern
# Add GET/PUT endpoints for tool paths:

@router.get("/tools")
def get_tool_settings() -> dict:
    """Return configured external tool paths."""
    config = load_global_config()
    return {
        "onetrainer_path": config.get("onetrainer", {}).get("install_path"),
        "model_dir": config.get("onetrainer", {}).get("model_dir"),
    }

@router.put("/tools")
def update_tool_settings(body: ToolSettingsUpdate) -> dict:
    """Update external tool paths in global config."""
    ...
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Video-only trainer configs (musubi, aitoolkit-video) | Image-specific trainer configs (kohya, aitoolkit-image, onetrainer) | Phase 8 | Need new generators; existing ones are video-only |
| Filesystem-based sample discovery (validate_all) | Manifest-based image discovery | Phase 4 onward | Export reads manifest directly, not filesystem |
| Process page for upscale only | Export page as pipeline terminus | Phase 8 | New dedicated export destination in nav flow |

**Deprecated/outdated:**
- The video `generate_trainer_config()` dispatch: not applicable for image export — uses `OrganizedSample` which has video-specific `frame_count` etc. Don't route through it.

---

## Open Questions

1. **OneTrainer preset template when OneTrainer not installed**
   - What we know: User's preset is at `{onetrainer_root}/training_presets/SD 1.5 Lora Character - Prodigy.json`
   - What's unclear: The exact JSON structure of that file (not yet read)
   - Recommendation: When planning, include a Wave 0 task to read and document the actual preset JSON structure. For the implementation, hardcode the known values (rank 64, 7 epochs, batch 2, Prodigy optimizer) as the fallback template.

2. **ai-toolkit image-mode YAML resolution format**
   - What we know: Video mode uses `resolution: [W, H]`; image mode likely uses `resolution: [N, N]` or a single int
   - What's unclear: Whether image mode accepts non-square resolutions (important for bucketed exports)
   - Recommendation: Use `[base_resolution, base_resolution]` as square (simplest and most compatible). The images are already bucketed to the correct AR; ai-toolkit applies its own bucketing during training.

3. **Kohya TOML: dataset config vs network config split**
   - What we know: kohya uses separate files for dataset and network config
   - What's unclear: Whether we should generate both or just the dataset TOML
   - Recommendation: Generate only the dataset TOML (what describes the training data). Add TODO comments for network params (learning rate, optimizer, etc.). This matches the existing musubi generator pattern.

4. **nvidia-smi availability on Windows**
   - What we know: User has RTX 5080; CUDA is available (from MEMORY.md)
   - What's unclear: Whether `nvidia-smi` is on PATH or requires full path
   - Recommendation: Try `nvidia-smi` first, fall back to `C:\Windows\System32\nvidia-smi.exe`, then skip VRAM check gracefully if unavailable.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (existing, no new install needed) |
| Config file | `pytest.ini` or pyproject.toml (check existing) |
| Quick run command | `pytest tests/test_export_service.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXPT-01 | kohya folder structure created correctly (`5_sks person/`) | unit | `pytest tests/test_export_service.py::test_kohya_folder_structure -x` | ❌ Wave 0 |
| EXPT-01 | kohya TOML config written with correct content | unit | `pytest tests/test_export_service.py::test_kohya_toml_content -x` | ❌ Wave 0 |
| EXPT-02 | ai-toolkit YAML generated with image dataset section | unit | `pytest tests/test_export_service.py::test_aitoolkit_yaml_image_mode -x` | ❌ Wave 0 |
| EXPT-03 | OneTrainer concept JSON has correct structure | unit | `pytest tests/test_export_service.py::test_onetrainer_concept_json -x` | ❌ Wave 0 |
| EXPT-03 | OneTrainer preset JSON references correct paths | unit | `pytest tests/test_export_service.py::test_onetrainer_preset_paths -x` | ❌ Wave 0 |
| EXPT-05 | Caption `.txt` files written from manifest data | unit | `pytest tests/test_export_service.py::test_caption_txt_written -x` | ❌ Wave 0 |
| EXPT-05 | Image + caption files are stem-matched | unit | `pytest tests/test_export_service.py::test_stem_matching -x` | ❌ Wave 0 |
| EXPT-06 | Only `source: "crop"` entries exported | unit | `pytest tests/test_export_service.py::test_crop_only_filter -x` | ❌ Wave 0 |
| EXPT-07 | Config files generated at expected paths | unit | `pytest tests/test_export_service.py::test_config_file_paths -x` | ❌ Wave 0 |
| GUI-07 | Export API: POST /export/start returns op_id | integration | `pytest tests/test_export_api.py::test_start_export -x` | ❌ Wave 0 |
| GUI-07 | Export validation scan returns issues correctly | unit | `pytest tests/test_export_service.py::test_validation_scan -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_export_service.py tests/test_export_api.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_export_service.py` — covers EXPT-01 through EXPT-07 (manifest filtering, file copy, caption write, config generation)
- [ ] `tests/test_export_api.py` — covers GUI-07 (SSE start, events, cancel endpoints)
- [ ] `tests/test_onetrainer_service.py` — covers OneTrainer detection and process management

*(No framework install needed — pytest already present)*

---

## Sources

### Primary (HIGH confidence)

- `klippbok/api/routers/cleanup.py` — SSE pattern with asyncio.Queue, background task, None sentinel
- `klippbok/api/routers/crop.py` — `source: "crop"` manifest field; `_register_crop_outputs` pattern
- `klippbok/services/upscale_service.py` — subprocess + threading + asyncio.Queue pattern for external process
- `klippbok/services/global_config_service.py` — atomic config persistence pattern
- `klippbok/services/project_service.py` — `load_manifest()`, manifest structure, `images` key
- `klippbok/dataset/trainers.py` — `@register_trainer`, TOML/YAML generation pattern
- `klippbok/config/model_profiles.py` — `ModelProfile`, `TrainingHints`, `base_resolution`
- `klippbok/api/routers/settings.py` — Settings router extension pattern
- `.planning/phases/08-export-pipeline/08-CONTEXT.md` — All locked decisions
- `frontend/src/components/Layout/NavBar.tsx` — NavLink pattern for adding nav items

### Secondary (MEDIUM confidence)

- kohya-ss GitHub README: `{N}_{trigger_word} {class_name}/` folder naming convention (verified from community knowledge + context)
- OneTrainer concept JSON structure: documented in CONTEXT.md specifics section from user's direct experience

### Tertiary (LOW confidence — validate during implementation)

- ai-toolkit image-mode YAML resolution field format (verify against ai-toolkit source or README before implementation)
- OneTrainer stdout/stderr output format for progress parsing (verify against OneTrainer source or run a test training)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all dependencies already in venv; no new installs required
- Architecture: HIGH — every pattern directly mirrors existing proven implementations
- Trainer config formats: HIGH (kohya/OneTrainer) / MEDIUM (ai-toolkit image mode)
- OneTrainer subprocess: HIGH — mirrors upscale_service.py exactly
- Pitfalls: HIGH — derived from actual codebase analysis

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (stable domain; trainer format specs rarely change)
