# Technology Stack

**Project:** klippbok -- Image Dataset Preparation, Cropping, Tagging, and Web GUI
**Researched:** 2026-02-27
**Scope:** Stack additions for image pipeline, booru tagging, multi-model support, and FastAPI+React web GUI. Does NOT cover existing video processing stack.

---

## Recommended Stack

### Backend -- Python (extending existing codebase)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| FastAPI | >=0.133 | Web API framework | Already decided. Async, Pydantic-native, matches existing Pydantic v2 models. Official full-stack template exists. | HIGH |
| uvicorn | >=0.34 | ASGI server | Standard FastAPI production server. Single-user tool, no need for gunicorn. | HIGH |
| python-multipart | >=0.0.20 | File upload parsing | Required by FastAPI for `UploadFile` -- image upload is core functionality. | HIGH |
| Pillow | >=12.1 | Image load/crop/resize/save | Already a dependency (in `triage` extras). Handles all needed image ops: crop, resize with Lanczos, format conversion, EXIF reading. No need for OpenCV for this use case. | HIGH |
| SQLite + aiosqlite | >=0.20 | Async database | Single-user internal tool -- SQLite is the right choice. No server process, single-file DB, zero config. aiosqlite for async FastAPI compatibility. | HIGH |
| SQLAlchemy | >=2.0 | ORM / database layer | Async support via `AsyncSession`, works with SQLite, Pydantic v2 integration patterns well-documented. Use 2.0-style with mapped_column. | HIGH |
| onnxruntime | >=1.24 | WD tagger inference | Required for WD Tagger v3 ONNX models. Lighter than full PyTorch for inference-only. Supports batch inference (batch dim no longer fixed to 1). | HIGH |
| websockets | >=14.0 | Real-time progress updates | FastAPI WebSocket support for long-running ops (batch tagging, batch crop). Better UX than polling. | MEDIUM |

### Booru Tagging -- WD Tagger v3 (SmilingWolf)

| Technology | Version/Variant | Purpose | Why | Confidence |
|------------|----------------|---------|-----|------------|
| wd-eva02-large-tagger-v3 | v1.0 (ONNX) | Primary booru tag model | Best accuracy among v3 variants (EVA02-Large architecture). ONNX format for fast inference without full PyTorch. Trained on Danbooru dataset up to 2024-02-28. | HIGH |
| wd-vit-tagger-v3 | v1.0 (ONNX) | Lightweight fallback | Smaller/faster than EVA02-Large. Good for users with limited VRAM/RAM. Same tag vocabulary. | MEDIUM |

**Tag inference approach:** Use ONNX Runtime directly, NOT timm or transformers. Rationale:
- ONNX models are provided by SmilingWolf on HuggingFace
- No torch dependency needed for inference (lighter install)
- Batch inference supported (batch dim is dynamic)
- onnxruntime-gpu available for CUDA acceleration if needed
- Reference: [wdv3-batch-vit-tagger](https://github.com/Ketengan-Diffusion/wdv3-batch-vit-tagger) for ONNX batch pattern

**Input preprocessing:** Resize to 448x448 (model input size), RGB, normalize to [0,1]. Use Pillow for this -- no OpenCV needed.

**Output format:** CSV of `(tag_name, confidence)` pairs. Filter by threshold (default 0.35 for general, 0.85 for character tags). Output as comma-separated booru tag string for SD1.5 compatibility.

### Natural Language Captioning (for SDXL/Flux)

| Technology | Purpose | Why | Confidence |
|------------|---------|-----|------------|
| Existing caption module (Gemini/OpenAI) | NL captions | Already built in klippbok. Gemini and OpenAI APIs for natural language captions. Reuse for image captioning. | HIGH |
| Florence-2 (microsoft/Florence-2-large) | Local NL captions | 0.77B param model, runs on CPU. MIT license. No API cost. Generates detailed natural language captions suitable for SDXL/Flux. Requires transformers + accelerate. | MEDIUM |

**Recommendation:** Start with existing Gemini/OpenAI caption module (already built). Add Florence-2 as optional local alternative later. Florence-2 requires `transformers>=4.30` and `accelerate` -- both already compatible with the existing triage dependency group.

### Image Processing Pipeline

| Technology | Purpose | Why | Confidence |
|------------|---------|-----|------------|
| Pillow (PIL) | All image operations | Crop, resize, format conversion, EXIF orientation, thumbnail generation. Lanczos resampling for high-quality downscaling. Already a project dependency. | HIGH |

**Do NOT use OpenCV for image operations in this project.** Rationale:
- OpenCV uses BGR by default -- constant source of bugs when mixing with Pillow/web display
- OpenCV is massive (100MB+) for operations Pillow handles fine
- Pillow's `Image.LANCZOS` resampling is high quality for dataset prep
- The project already depends on Pillow via `triage` extras
- OpenCV's advantage (real-time video, complex CV) is irrelevant here

### Frontend -- React + TypeScript

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Vite | >=7.3 | Build tool + dev server | Standard for React SPAs in 2026. Fast HMR, TypeScript out of the box. `npm create vite@latest -- --template react-ts`. | HIGH |
| React | >=18 | UI framework | Already decided. SPA for internal tool -- no SSR needed, no Next.js overhead. | HIGH |
| TypeScript | >=5.0 | Type safety | Required by project standards. | HIGH |
| react-advanced-cropper | >=0.20 | Interactive image cropping | Best React cropper for this use case: custom aspect ratio constraints (critical for bucket presets), custom stencils, programmatic control via ref, zoom/rotate. More flexible than react-easy-crop for preset-driven workflows. | HIGH |
| @tanstack/react-query | >=5.90 | Server state management | Caching, invalidation, optimistic updates for dataset state. De facto standard for React API integration. | HIGH |
| Zustand | >=5.0 | Client state management | Lightweight, no boilerplate. Good for UI state (selected images, crop settings, active model config). Simpler than Redux for a single-user tool. | MEDIUM |

### Frontend -- Supporting Libraries

| Library | Purpose | Why | Confidence |
|---------|---------|-----|------------|
| react-virtuoso or @tanstack/react-virtual | Virtualized image grid | Dataset browsers can have 1000+ images. Must virtualize to avoid DOM explosion. | HIGH |
| react-dropzone | File upload UX | Drag-and-drop image import. Well-maintained, accessible. | MEDIUM |
| tailwindcss | Styling | Utility-first, fast iteration for internal tools. No design system overhead. | MEDIUM |

### Database Schema (SQLite)

Single-user tool -- SQLite is sufficient and preferred. No migration framework needed initially (use raw SQL schema or Alembic if complexity grows).

| Entity | Purpose |
|--------|---------|
| `projects` | Named collections of images targeting a specific model |
| `images` | Source images with metadata (path, dimensions, format, import date) |
| `crops` | Crop definitions per image (x, y, w, h, target_bucket) |
| `tags` | Booru tags per image (tag, confidence, source: auto/manual) |
| `captions` | NL captions per image (text, source: gemini/openai/florence/manual) |
| `model_configs` | Target model presets (SD1.5, SDXL, Flux with bucket definitions) |

### Multi-Model Bucket Definitions

| Model | Base Resolution | Bucket Step | Caption Style |
|-------|----------------|-------------|---------------|
| SD1.5 | 512x512 | 64px | Booru tags (comma-separated) |
| SDXL | 1024x1024 | 64px | Natural language |
| Flux | 1024x1024 | 64px | Natural language |

Bucket algorithm: For each image, find the bucket whose aspect ratio is closest to the image's native aspect ratio, where `bucket_width + bucket_height <= 2 * base_resolution` and each dimension is a multiple of `bucket_step`. This matches Kohya/sd-scripts bucketing behavior.

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not Alternative |
|----------|-------------|-------------|---------------------|
| Image processing | Pillow | OpenCV (cv2) | BGR color space bugs, massive dependency, overkill for crop/resize. No advantage for static image dataset work. |
| Booru tagger | WD Tagger v3 (ONNX) | DeepDanbooru | Outdated, superseded by WD Tagger v3. Less accurate, fewer tags. |
| Booru tagger runtime | onnxruntime | timm (PyTorch) | ONNX is lighter (no torch needed for inference), faster cold start, batch-flexible. Torch only needed if fine-tuning. |
| NL captioning | Gemini API (existing) | Florence-2 local | Florence-2 is good but API models produce better captions. Add Florence-2 as optional later. |
| React cropper | react-advanced-cropper | react-easy-crop | react-easy-crop lacks custom stencils and programmatic aspect ratio presets. react-advanced-cropper supports exact bucket constraints. |
| React cropper | react-advanced-cropper | react-image-crop | react-image-crop is simpler but lacks zoom, rotate, and stencil customization needed for precise dataset cropping. |
| Database | SQLite | PostgreSQL | Single-user internal tool. PostgreSQL adds operational complexity (server process, connection management) with zero benefit. |
| State management | Zustand | Redux Toolkit | Redux is overkill for single-user internal tool. Zustand is simpler, less boilerplate. |
| Build tool | Vite | Next.js | Internal tool SPA, no SEO needed, no SSR needed. Vite is lighter, faster, simpler. |
| ORM | SQLAlchemy 2.0 | Tortoise ORM | SQLAlchemy is the standard, better async support, larger ecosystem. Tortoise is niche. |

---

## Installation

### Backend (Python)

```bash
# Add to pyproject.toml [project.optional-dependencies]
# New dependency group: "web"
pip install fastapi>=0.133 uvicorn>=0.34 python-multipart>=0.0.20
pip install sqlalchemy>=2.0 aiosqlite>=0.20
pip install onnxruntime>=1.24  # or onnxruntime-gpu for CUDA

# Already available via existing extras:
# Pillow (via triage), pydantic (core), pyyaml (core)
```

### Frontend (React/TypeScript)

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend

# Core
npm install @tanstack/react-query react-advanced-cropper zustand

# UI/UX
npm install react-dropzone react-virtuoso tailwindcss @tailwindcss/vite

# Dev
npm install -D @types/react @types/react-dom
```

### WD Tagger Model Download

```bash
# Download ONNX model from HuggingFace (one-time)
# wd-eva02-large-tagger-v3: ~300MB ONNX file
huggingface-cli download SmilingWolf/wd-eva02-large-tagger-v3 \
  model.onnx selected_tags.csv --local-dir models/wd-eva02-large-v3
```

---

## Dependency Groups (pyproject.toml additions)

```toml
[project.optional-dependencies]
web = [
    "fastapi>=0.133",
    "uvicorn>=0.34",
    "python-multipart>=0.0.20",
    "sqlalchemy>=2.0",
    "aiosqlite>=0.20",
    "websockets>=14.0",
]
tagging = [
    "onnxruntime>=1.24",
    "Pillow>=12.0",
    "numpy>=1.24",
]
# GPU acceleration (optional)
tagging-gpu = [
    "onnxruntime-gpu>=1.24",
    "Pillow>=12.0",
    "numpy>=1.24",
]
```

---

## Key Integration Points with Existing Codebase

| Existing Module | Integration | Notes |
|----------------|-------------|-------|
| `klippbok/config/` | Extend YAML schema for image datasets + model configs | Add image-specific fields to `klippbok_data.yaml` |
| `klippbok/caption/` | Reuse for NL captioning of images (already supports Gemini, OpenAI) | May need minor adaptation for image vs video input |
| `klippbok/dataset/` | Extend bucketing logic for image-specific aspect ratio buckets | Existing validation patterns reusable |
| `klippbok/triage/` | Embedding logic could help with dataset diversity analysis | Already has Pillow + torch + transformers |

---

## Sources

### Verified (HIGH confidence)
- [Pillow 12.1.1 on PyPI](https://pypi.org/project/Pillow/) -- latest version confirmed Feb 2026
- [FastAPI 0.133.1 on PyPI](https://pypi.org/project/fastapi/) -- latest version confirmed Feb 2026
- [onnxruntime 1.24.2 on PyPI](https://pypi.org/project/onnxruntime/) -- latest version confirmed Feb 2026
- [SmilingWolf/wd-eva02-large-tagger-v3 on HuggingFace](https://huggingface.co/SmilingWolf/wd-eva02-large-tagger-v3) -- model card with ONNX requirements
- [SmilingWolf/wd-vit-tagger-v3 on HuggingFace](https://huggingface.co/SmilingWolf/wd-vit-tagger-v3) -- model card
- [react-advanced-cropper docs](https://advanced-cropper.github.io/react-advanced-cropper/) -- custom stencils, aspect ratio constraints
- [FastAPI Request Files docs](https://fastapi.tiangolo.com/tutorial/request-files/) -- UploadFile pattern
- [Kohya bucketing discussion](https://github.com/bmaltais/kohya_ss/discussions/1516) -- bucket algorithm reference

### Multiple sources agree (MEDIUM confidence)
- Vite 7.3.x as current stable -- [vite.dev/releases](https://vite.dev/releases), multiple 2026 articles
- TanStack Query v5.90+ -- [npm](https://www.npmjs.com/package/@tanstack/react-query)
- react-advanced-cropper 0.20.x -- [npm](https://www.npmjs.com/package/react-advanced-cropper)
- Florence-2 for local NL captioning -- [HuggingFace](https://huggingface.co/microsoft/Florence-2-large), multiple tutorials
- SQLite + aiosqlite for single-user FastAPI -- [FastAPI docs](https://fastapi.tiangolo.com/tutorial/sql-databases/), community best practices

### Unverified / LOW confidence
- Zustand >=5.0 version number -- based on training data, verify before adding to package.json
- websockets >=14.0 version -- verify current version on npm/PyPI before installing
- react-virtuoso vs @tanstack/react-virtual -- both viable, do a quick comparison during implementation
