```
   ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·
  ╭────────────────────────────────────────────────────────────────────╮
  │                                                                    │
  │                      ✂  k l i p p b o k                           │
  │                                                                    │
  │        video & image dataset curation for LoRA training            │
  │                                                                    │
  │    ┌───────┐   ┌───────┐   ┌───────┐   ┌───────┐   ┌───────┐    │
  │    │ scan  │──▶│triage │──▶│caption│──▶│  val  │──▶│ train │    │
  │    └───────┘   └───────┘   └───────┘   └───────┘   └───────┘    │
  │                                                                    │
  │                          alvdansen labs                            │
  │                                                                    │
  ╰────────────────────────────────────────────────────────────────────╯
   ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·
```

**Video and image dataset curation, preparation, and annotation for LoRA training.**

Klippbok is a tool for processing raw video footage and images into training-ready datasets. It features scene detection, CLIP-based triage, multi-provider VLM captioning, interactive cropping with pose detection, AI upscaling, resolution bucketing, and dataset validation. It ships with both a CLI for automated pipelines and a web GUI for interactive dataset preparation.

Works with any trainer (musubi-tuner, ai-toolkit, kohya/sd-scripts) and designed to prep data for finetuning any modern video diffusion model.

Built by [Minta](https://github.com/aramintak) and [Timothy](https://github.com/timm156), distilling three years of professional LoRA finetuning into opinionated tooling. Every default, threshold, and pipeline decision comes from shipping production models for enterprise clients — not guesswork. The same methodology behind [lora-gym](https://github.com/alvdansen/lora-gym) and 50+ published models on [Hugging Face](https://huggingface.co/alvdansen).

---

## What it does

### Video pipeline

| Stage | Tool | What happens |
|-------|------|-------------|
| **Ingest** | `scan`, `ingest`, `normalize` | Scene detection, splitting, fps/resolution normalization |
| **Triage** | `triage` | CLIP-based matching against reference images — find your character in 2 hours of footage |
| **Caption** | `caption`, `score`, `audit` | VLM-generated captions via Gemini, Replicate, or local models |
| **Extract** | `extract` | Reference frame extraction (first frame, best frame) for I2V training |
| **Validate** | `validate`, `organize` | Dataset completeness checks, trainer-specific output formatting |

### Image pipeline (Web GUI)

| Stage | Tool | What happens |
|-------|------|-------------|
| **Import** | Project picker + import | Batch import with metadata probing, blur detection, duplicate detection |
| **Crop** | Interactive crop editor | Per-image crop with auto-crop (MediaPipe pose detection), rotation, flip, bucket snapping |
| **Upscale** | Upscale step | AI upscaling via SeedVR2 or NMKD-Siax with real-time progress |
| **Caption** | Caption editor | Multi-provider captioning, batch tag operations, inline editing, quality scoring |
| **Export** | Validate + organize | Bucket validation, trainer-specific output formatting |

## Why Klippbok exists

Existing training frameworks don't take responsibility for how your data is prepared and there is very little reliable guidance on dataset prep for video models.

A common reality:

- Your source material is a 2-hour movie and you need 150 clips of one character
- Your clips are 1080p/24fps but training needs 720p/16fps with 4n+1 frame counts
- You need captions and you don't know where to start
- You need to know which clips are blurry, which have text overlays, which are duplicates, etc

Klippbok solves arguably the most difficult part of finetuning, preparing the data, so that you can focus on training.

Klippbok is an [Alvdansen Labs](https://huggingface.co/alvdansen) project — an open-source initiative to advance finetuning practices and make production-quality training accessible to everyone.

---

## Quick start

### CLI (video datasets)

```bash
pip install klippbok[all]
```

**Scenario: Character LoRA from raw footage**

```powershell
# Set up a concepts folder with a reference image — any screenshot or photo works
mkdir concepts\character
# Copy a reference image into concepts\character\ (e.g. a screenshot of your character)

# 1. Find every scene containing your character using CLIP visual matching
python -m klippbok.video triage "C:\raw_videos" -s concepts/

# 2. Split only matching scenes into training clips
python -m klippbok.video ingest "C:\raw_videos" -o clips --triage scene_triage_manifest.json

# 3. Caption
python -m klippbok.video caption clips -p gemini -u character -a "Holly Golightly"

# 4. Extract reference frames (for I2V)
python -m klippbok.video extract clips -o clips/references

# 5. Validate
python -m klippbok.dataset validate clips
```

Output: normalized clips (16fps, 720p), `.txt` caption sidecars, `.png` reference frames — ready for any trainer.

### Web GUI (image datasets)

```bash
pip install klippbok[gui]
klippbok serve --port 9000
```

Open `http://localhost:9000` — pick a project directory, import images, crop, caption, and export.

See [docs/PIPELINES.md](docs/PIPELINES.md) for all 6 supported pipelines.

---

## Installation

**Minimal** (config + validation only):
```bash
pip install klippbok
```

**With specific features:**
```bash
pip install klippbok[video]      # + scene detection, normalization (requires ffmpeg)
pip install klippbok[caption]    # + Gemini, Replicate captioning backends
pip install klippbok[triage]     # + CLIP-based triage (torch, transformers)
pip install klippbok[dataset]    # + rich reports, file type detection
pip install klippbok[image]      # + image processing (Pillow, imagehash)
pip install klippbok[crop]       # + auto-crop with MediaPipe pose detection
pip install klippbok[tagger]     # + WD Tagger booru-style tag generation
pip install klippbok[gui]        # + web GUI (FastAPI, React, all image tools)
pip install klippbok[all]        # everything
```

**Requirements:**
- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) on PATH (for video processing)
- API key for cloud captioning (Gemini, Replicate) — or use local models for free

---

## Web GUI

The web GUI is a FastAPI + React application for interactive image dataset preparation.

### Pages

| Page | Description |
|------|-------------|
| **Project Picker** | Browse filesystem, select or create a project directory |
| **Gallery** | Masonry grid of imported images with metadata, selection toolbar |
| **Import** | Batch import with real-time SSE progress (probing, blur detection, dedup) |
| **Crop** | Interactive per-image crop editor with auto-crop, rotation, flip, zoom |
| **Upscale** | AI upscaling with SeedVR2 or NMKD-Siax, progress streaming, cancel support |
| **Caption** | Multi-provider captioning, batch tag ops, inline editing, quality scores |
| **Settings** | Model profile selection (SD1.5, SDXL, Flux, Qwen), provider configuration |

### Running the GUI

```bash
# Install with GUI dependencies
pip install klippbok[gui]

# Start the server
klippbok serve --port 9000

# Or directly:
python -m klippbok.api --port 9000
```

The server serves the React SPA from built static files. No separate dev server needed.

### Supported upscalers

The GUI auto-detects locally installed upscalers:

| Upscaler | Detection | Notes |
|----------|-----------|-------|
| **SeedVR2** | Checks `C:\GenAI\SeedVR2` and `SEEDVR2_PATH` env var | Uses `inference_cli.py` directly |
| **NMKD-Siax** | Checks common install paths and `NMKD_SIAX_PATH` env var | CLI-based upscaling |

---

## Caption providers

| Provider | Flag / Config | Needs | Quality | Notes |
|----------|---------------|-------|---------|-------|
| **Gemini** | `-p gemini` | `GEMINI_API_KEY` | Best | Free tier available |
| **Replicate** | `-p replicate` | `REPLICATE_API_TOKEN` | Best | Pay-per-use |
| **LM Studio** | GUI config | LM Studio running locally | Good | OpenAI-compatible API |
| **NanoGPT** | GUI config | NanoGPT endpoint | Good | OpenAI-compatible API |
| **JoyCaption** | GUI auto-detect | Model files in standard paths | Good | Local, free |
| **Ollama** | `-p openai` | Ollama installed | Good | Free, runs on your GPU |
| **WD Tagger** | GUI / tagger module | ONNX model (auto-downloaded) | N/A | Booru-style tags, not captions |

Local models tend toward verbose captions. Gemini and Replicate produce the short, factual captions that train best. See [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md) for provider setup.

---

## Pipelines

Different training goals need different tools. Klippbok supports 6 pipelines:

| Your situation | Pipeline |
|---------------|----------|
| Raw footage + character reference images | **Triage-first** — find your character, skip everything else |
| Pre-cut clips of a character | **Normalize + caption** — fix specs, add captions |
| Clips selected for visual style | **Style LoRA** — captions describe content, model learns style from pixels |
| Clips selected for motion patterns | **Motion LoRA** — captions focus on movement and camera behavior |
| Existing dataset with wrong specs | **Cleanup** — re-normalize, score captions, validate |
| Raw footage + object/setting references | **Experimental triage** — works but needs manual review |

Full details: [docs/PIPELINES.md](docs/PIPELINES.md)

---

## Command reference

### Video CLI

```
python -m klippbok.video scan <dir>                    # probe clips, report issues
python -m klippbok.video ingest <path> -o <out>        # scene detect + split + normalize
python -m klippbok.video normalize <dir> -o <out>      # fix fps, resolution, frame count
python -m klippbok.video triage <dir> -s <concepts>    # CLIP match against references
python -m klippbok.video caption <dir> -p <provider>   # generate .txt captions
python -m klippbok.video score <dir>                   # check caption quality (local)
python -m klippbok.video extract <dir> -o <out>        # extract reference frames as PNG
python -m klippbok.video audit <dir>                   # compare captions against VLM
```

### Dataset CLI

```
python -m klippbok.dataset validate <dir>              # check dataset completeness
python -m klippbok.dataset organize <dir> -o <out>     # format for specific trainers
```

### Server

```
klippbok serve [--project-dir DIR] [--host HOST] [--port PORT]
```

Full flag reference with examples: [docs/COMMANDS.md](docs/COMMANDS.md)

---

## API reference

All endpoints use the `/api/v1/` prefix. The server runs on port 9000 by default.

| Group | Endpoints | Purpose |
|-------|-----------|---------|
| **Browse** | `GET /browse/roots`, `GET /browse/list`, `POST /browse/mkdir` | Filesystem navigation for project picker |
| **Import** | `POST /import/`, `GET /import/{op_id}/events` | Batch image import with SSE progress |
| **Images** | `GET /images/`, `GET /images/{id}/thumbnail`, `GET /images/{id}/full` | Gallery data and image serving |
| **Crop** | `POST /crop/`, `POST /crop/auto` | Batch crop/rotate/flip and auto-crop with pose detection |
| **Upscale** | `POST /upscale/start`, `GET /upscale/status`, `POST /upscale/{op_id}/cancel`, `GET /upscale/{op_id}/events` | AI upscaling with progress streaming and cancellation |
| **Captions** | `POST /captions/generate`, `GET /captions/{op_id}/events`, `GET /captions/config`, `PUT /captions/config`, `GET /captions/models`, `POST /captions/batch`, `PATCH /captions/{id}` | Caption generation, provider config, batch ops, inline edit |
| **Settings** | `GET /settings/`, `PUT /settings/`, `GET /settings/profiles`, `POST /settings/shutdown` | Project settings and model profile selection |

---

## Visual triage: let a reference image organize your dataset

This is one of Klippbok's most powerful features. Instead of manually scrubbing through hours of footage, you drop a reference image into a folder and Klippbok finds every scene containing that subject.

**How it works:** You create a `concepts/` folder with subfolders named by type. Put one or more reference images in each — a screenshot, a character sheet, a photo. Klippbok uses [CLIP](https://openai.com/research/clip) to compare video frames against your reference images and automatically identifies which scenes match.

```
concepts/
  character/
    luna_ref.jpg              <- just one image is enough
  setting/
    cafe_exterior.png
```

```powershell
python -m klippbok.video triage "C:\raw_videos" -s concepts/
```

That's it. Klippbok probes every video, detects scenes, samples frames from each scene, and matches them against your references. The output is a reviewable manifest where you can verify matches and flip `include: true/false` per scene before splitting.

**Why this matters:** A 2-hour film might produce 1700 clips when fully split. If you're training a character LoRA, maybe 150 of those actually contain your character. Without triage, you'd split everything, caption everything, then manually delete 1500 files. With triage, you skip all of that — only matching scenes get split.

**Auto-detection:** Klippbok automatically adapts to your source material:
- **Short clips (<30s):** Samples a few frames per clip, matches directly -> `triage_manifest.json`
- **Long videos (>=30s):** Detects scenes first, samples 1-2 frames per scene -> `scene_triage_manifest.json`

**Reliability:** Character triage is production-ready — CLIP recognizes human identity across angles, lighting, and distance. Object and setting triage is experimental and benefits from manual manifest review.

---

## Architecture

```
klippbok/
├── api/              # FastAPI web server + React SPA
│   ├── routers/      # REST endpoints (browse, import, images, crop, upscale, captions, settings)
│   ├── models.py     # Request/response Pydantic schemas
│   ├── thumbnail.py  # Thumbnail generation and caching
│   └── static/       # Built React app (served as SPA)
│
├── caption/          # Multi-provider VLM captioning
│   ├── gemini.py     # Google Gemini backend
│   ├── replicate.py  # Replicate backend
│   ├── openai_compat.py  # OpenAI-compatible (LM Studio, Ollama, NanoGPT)
│   ├── joycaption.py # JoyCaption local model
│   ├── wd_tagger.py  # Booru-style tag generation (ONNX)
│   ├── scoring.py    # Caption quality metrics
│   └── prompts.py    # Use-case prompt templates
│
├── config/           # YAML data schema, model profiles, defaults
│   ├── model_profiles.py  # SD1.5, SDXL, Flux, Qwen bucket configs
│   └── loader.py     # YAML config loading
│
├── dataset/          # Dataset discovery, validation, bucketing, organization
│   ├── validate.py   # Comprehensive validation with accumulative issues
│   ├── organize.py   # Trainer-specific output (musubi, ai-toolkit, kohya)
│   └── bucketing.py  # Resolution bucket assignment
│
├── image/            # Image processing tools
│   ├── autocrop.py   # MediaPipe pose detection + center-crop fallback
│   ├── quality.py    # Blur detection
│   ├── dedup.py      # Perceptual hash duplicate detection
│   └── probe.py      # Image metadata extraction
│
├── services/         # Business logic layer
│   ├── image_service.py    # Batch import orchestration
│   ├── caption_service.py  # Caption generation + batch ops
│   ├── crop_service.py     # Crop application
│   ├── upscale_service.py  # Upscaler detection + subprocess management
│   └── global_config_service.py  # Provider config persistence
│
├── triage/           # CLIP-based visual matching
│   ├── embeddings.py # CLIP embedding generation
│   ├── concepts.py   # Concept folder loading
│   └── triage.py     # Matching orchestration
│
└── video/            # Video processing pipeline
    ├── scene.py      # PySceneDetect scene detection
    ├── split.py      # Frame-accurate video splitting
    ├── probe.py      # ffprobe metadata extraction
    └── extract.py    # Reference frame extraction
```

### Frontend

```
frontend/src/
├── pages/            # Route-level components
│   ├── ProjectPickerPage.tsx   # Directory browser + project selection
│   ├── GalleryPage.tsx         # Masonry image grid with selection
│   ├── ImportPage.tsx          # Import with SSE progress
│   ├── CropPage.tsx            # Interactive crop editor
│   ├── CaptionPage.tsx         # Caption editor + batch ops
│   └── SettingsPage.tsx        # Model profiles + provider config
│
├── components/       # Reusable UI components
│   ├── Crop/         # CropCard, BucketSelector, UpscaleStep
│   ├── Caption/      # CaptionPanel, ProviderConfigSection, BatchTagBar
│   ├── Gallery/      # MasonryGrid, ThumbnailCard, SelectionToolbar
│   └── Layout/       # NavBar, AppLayout, ToastProvider
│
├── hooks/            # Custom React hooks (useImages, useImportEvents, useCaptionEvents)
└── store/            # Zustand state (project_dir, selections)
```

**Tech stack:** React 19, TypeScript, Vite, React Router v7, Zustand, TanStack React Query, react-advanced-cropper, sonner

### Key patterns

- **Manifest-driven state** — single `.klippbok/manifest.json` per project tracks all image entries, metadata, captions, and validation issues
- **Pydantic v2 models** for all data validation (backend schemas and API contracts)
- **SSE streaming** for long operations (import, upscale, caption) — real-time progress to the frontend
- **Service layer** separates business logic from API routing — same services used by both CLI and web GUI
- **Accumulative validation** — never fails fast, collects all issues per image/video

---

## Trainer compatibility

Klippbok produces standard formats that work with:

- **musubi-tuner** — generates TOML config via `organize -t musubi`
- **ai-toolkit (ostris)** — generates YAML config via `organize -t aitoolkit`
- **kohya/sd-scripts** — flat layout with `.txt` sidecars (standard format)
- **Any trainer** that reads video/image + caption sidecar pairs

---

## Model profiles

The GUI supports training-specific bucketing for different model architectures:

| Profile | Typical Buckets | Use Case |
|---------|----------------|----------|
| **SD 1.5** | 512px base | Stable Diffusion 1.5 LoRA |
| **SDXL** | 1024px base | Stable Diffusion XL LoRA |
| **Flux** | 512-1024px range | Flux model finetuning |
| **Qwen** | Various | Qwen-based models |
| **Custom** | User-defined | Any resolution/ratio requirements |

Each profile defines valid resolution buckets. Auto-crop and manual crop both snap to the active profile's bucket ratios.

---

## Development

```bash
# Clone and install
git clone https://github.com/alvdansen/klippbok.git
cd klippbok
pip install -e ".[all,dev]"

# Run tests
pytest                    # all tests
pytest -x                 # stop on first failure
pytest -k "pattern"       # matching tests only

# Build frontend
cd frontend
pnpm install
pnpm build
cd ..

# Copy frontend build to server static directory
cp -r frontend/dist/* klippbok/api/static/

# Start the server
python -m klippbok.api --port 9000
```

**Frontend workflow:** The API server serves static files from `klippbok/api/static/`. There is no Vite dev server. After any change to `frontend/src/`, rebuild with `pnpm build` and copy to `klippbok/api/static/`.

---

## Documentation

- [**COMMANDS.md**](docs/COMMANDS.md) — Full command glossary with every flag and option
- [**CAPTIONING.md**](docs/CAPTIONING.md) — Captioning methodology: use-case prompts, anchor words, provider comparison
- [**PIPELINES.md**](docs/PIPELINES.md) — Which pipeline to use for your training scenario
- [**WALKTHROUGH.md**](docs/WALKTHROUGH.md) — Step-by-step tutorial tested on real data

---

## Roadmap

Klippbok is actively developed. Here's what's coming:

**Organization & multi-source handling**
- Smarter reference image routing during organize (I2V references, subject references, style references as separate control signals)
- Multi-source dataset merging — combine clips from different sources with different configs into a single organized output
- Per-concept captioning configs (different anchor words, use-cases, or providers per concept folder)
- Organize from triage output directly — `organize --from-triage manifest.json` without intermediate steps

**Trainer integration**
- Additional trainer config generators (kohya/sd-scripts TOML, SimpleTuner)
- Config validation against trainer requirements (e.g. "musubi needs 4n+1 frames")
- Training-ready archive export (zip with config + data, ready to upload to cloud training)

**Caption improvements**
- Caption refinement pipeline — score, filter, and re-caption low-quality entries automatically
- Multi-pass captioning — generate captions from multiple providers and pick the best
- Caption style transfer — convert verbose captions to prompt-style without re-running VLM

**Triage & quality**
- Multi-concept triage in a single pass with conflict resolution
- Temporal consistency scoring — detect clips where the subject appears/disappears mid-clip
- Scene-level quality scoring (motion blur, shot stability, lighting consistency)

**Data management**
- Dataset versioning — track what changed between iterations
- Deduplication across datasets — find overlapping content between projects
- Dataset splitting for train/val with stratified sampling by concept

---

## Part of the Dimljus ecosystem

Klippbok is the standalone data preparation toolkit from the soon to be released Dimljus Trainer, a video LoRA training framework for diffusion transformer models. Klippbok handles everything before training — Dimljus handles training itself.

You don't need Dimljus to use Klippbok. The output works with any trainer.

---

## License

Apache 2.0
