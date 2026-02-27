# Architecture Patterns

**Domain:** Image+video LoRA dataset preparation tool with web GUI
**Researched:** 2026-02-27
**Overall confidence:** HIGH (based on codebase analysis + established FastAPI/React patterns)

## Recommended Architecture

### The Core Insight: Service Layer Extraction

The existing klippbok codebase already has the right abstractions -- module functions like `organize_dataset()`, `validate_all()`, `caption_clips()`, `probe_video()` are clean, well-typed Python functions with Pydantic models in and out. The CLI is already a thin wrapper over these.

**The architecture is NOT "add a web layer on top of CLI."**
**The architecture IS "extract a service layer that both CLI and API consume."**

```
                +-------------------+     +-------------------+
                |   CLI (__main__)  |     |  FastAPI (api/)   |
                +--------+----------+     +--------+----------+
                         |                         |
                         v                         v
                +------------------------------------------+
                |           Service Layer (services/)       |
                |  ImageService, ProjectService, JobService |
                +------------------------------------------+
                         |
                         v
                +------------------------------------------+
                |        Domain Modules (existing)          |
                |  config/ video/ caption/ dataset/ triage/ |
                +------------------------------------------+
                         |
                         v
                +------------------------------------------+
                |     Image Module (NEW: klippbok/image/)   |
                |  load, crop, resize, validate, autocrop   |
                +------------------------------------------+
```

The key principle: **no business logic in the API layer or CLI layer.** Both are thin dispatchers to the same service functions.

### Component Architecture

```
klippbok/
  config/          # (existing) YAML schema, defaults, loader
  video/           # (existing) probe, scene, split, extract, validate
  caption/         # (existing) VLM backends, prompts, scoring
  dataset/         # (existing) discover, validate, organize, bucketing
  triage/          # (existing) CLIP embeddings, concept matching
  image/           # (NEW) Image loading, cropping, resizing, quality
  services/        # (NEW) Service layer -- orchestrates domain modules
  api/             # (NEW) FastAPI routes, WebSocket handlers
  web/             # (NEW) Built React static files (served by FastAPI)
```

## Component Boundaries

| Component | Responsibility | Communicates With | New/Existing |
|-----------|---------------|-------------------|--------------|
| `config/` | YAML config loading, Pydantic schema, defaults | All modules read config | Existing (extend) |
| `video/` | ffprobe, scene detection, splitting, frame extraction | `config/`, filesystem | Existing |
| `caption/` | VLM backends, prompt templates, scoring | `config/`, external APIs | Existing (extend) |
| `dataset/` | File pairing, validation, organize, bucketing | `config/`, `video/` | Existing (extend) |
| `triage/` | CLIP embeddings, concept matching | `config/`, `video/`, torch | Existing |
| `image/` | Image I/O, crop, resize, validate, autocrop | `config/`, Pillow | **NEW** |
| `services/` | Orchestrates domain modules for use cases | All domain modules | **NEW** |
| `api/` | HTTP/WebSocket endpoints, request validation | `services/` only | **NEW** |
| `web/` | React SPA static build output | `api/` via HTTP | **NEW** |

### Boundary Rules

1. **`api/` never imports from domain modules directly** -- always goes through `services/`.
2. **`services/` never handles HTTP concerns** (no Request/Response objects, no UploadFile).
3. **Domain modules remain CLI-friendly** -- they take `Path` objects and Pydantic models, never FastAPI types.
4. **`image/` follows existing module patterns** -- frozen Pydantic models, accumulative validation, pure functions.

## Data Flow

### Image Import Flow

```
[Browser: File Upload]
    |
    v
[api/routes/images.py: POST /api/v1/images/upload]
    - Accepts UploadFile, saves to project workspace
    - Returns image_id (stem-based, matching existing convention)
    |
    v
[services/image_service.py: import_image()]
    - Calls image.load() to read and validate
    - Generates thumbnail for gallery view
    - Returns ImageInfo Pydantic model
    |
    v
[image/loader.py: load_image()]
    - Pillow.Image.open()
    - Extract metadata (dimensions, format, color space)
    - Validate format support
    - Return ImageMetadata (frozen Pydantic model)
```

### Interactive Crop Flow (the most latency-sensitive path)

```
[Browser: React Crop Editor]
    - User drags crop rectangle on canvas
    - Canvas renders crop overlay locally (no server round-trip for preview)
    - Crop region = {x, y, width, height, rotation}
    |
    v (on "Apply Crop" or batch export)
[api/routes/images.py: POST /api/v1/images/{id}/crop]
    - Accepts CropRequest (Pydantic model via request body)
    - Delegates to service
    |
    v
[services/image_service.py: apply_crop()]
    - Validates crop against bucket constraints
    - Calls image.crop() for actual pixel manipulation
    - Returns CropResult with quality indicators
    |
    v
[image/crop.py: crop_image()]
    - Pillow crop + resize to target bucket
    - Calculate if upscaling required (quality warning)
    - Return cropped image + CropResult model
```

**Critical design choice:** The crop preview happens entirely in the browser via Canvas API. The server only processes the final crop parameters. This avoids latency for the interactive editing experience while keeping image manipulation server-side (where Pillow lives).

### Auto-Crop Flow

```
[Browser: Click "Auto Crop" button]
    |
    v
[api/routes/images.py: POST /api/v1/images/{id}/autocrop]
    |
    v
[services/image_service.py: auto_crop()]
    - Calls image.detect_subject() for subject bounding box
    - Calls image.compute_best_crop() for optimal bucket fit
    - Returns suggested CropRegion (user can adjust before applying)
    |
    v
[image/autocrop.py: detect_subject() + compute_best_crop()]
    - Subject detection via OpenCV (face/person cascade or saliency)
    - Bucket fitting: given subject bbox + target buckets, find
      the crop rectangle that maximizes subject inclusion while
      matching a bucket aspect ratio
    - Returns CropSuggestion with quality indicators
```

### Caption Flow (image-specific)

```
[Browser: Caption Editor panel]
    |
    v
[api/routes/captions.py: POST /api/v1/images/{id}/caption]
    - Accepts CaptionRequest (provider, style: "booru" | "natural")
    |
    v
[services/caption_service.py: caption_image()]
    - If style == "booru": use booru tagger (new provider)
    - If style == "natural": use existing VLM backends
    - Calls caption module functions
    |
    v
[caption/captioner.py + caption/booru.py (NEW)]
    - Existing VLMBackend.caption_image() for natural language
    - New BooruTagger for danbooru-style tags
```

### Project/Session State Flow

```
[Browser: Project Gallery View]
    |
    v
[api/routes/projects.py: GET /api/v1/project/samples]
    |
    v
[services/project_service.py: list_samples()]
    - Reads project workspace directory
    - Returns list of SampleInfo models
    |
    v
[Project workspace on disk]
    workspace/
      originals/     # uploaded source images (never modified)
      crops/         # cropped output images
      captions/      # .txt sidecar files
      thumbnails/    # gallery thumbnails (auto-generated)
      project.json   # project state manifest
```

**State management:** The project manifest (`project.json`) tracks per-image state: original path, crop parameters, caption text, quality flags. This is the image-pipeline equivalent of the existing `klippbok_manifest.json` pattern. The manifest is the single source of truth -- the React UI reads/writes it via the API.

## Patterns to Follow

### Pattern 1: Service Layer Functions

Every API endpoint delegates to a service function. Service functions are plain Python, testable without HTTP.

```python
# services/image_service.py
from klippbok.image.loader import load_image, ImageMetadata
from klippbok.image.crop import crop_image, CropResult
from klippbok.image.models import CropRegion, BucketConfig

async def import_image(
    source_path: Path,
    workspace: Path,
) -> ImageMetadata:
    """Import an image into the project workspace."""
    metadata = load_image(source_path)
    # Copy original to workspace/originals/
    dest = workspace / "originals" / source_path.name
    shutil.copy2(source_path, dest)
    return metadata

def apply_crop(
    image_path: Path,
    region: CropRegion,
    target_bucket: BucketConfig,
    output_path: Path,
) -> CropResult:
    """Crop and resize image to target bucket."""
    return crop_image(image_path, region, target_bucket, output_path)
```

```python
# api/routes/images.py
from fastapi import APIRouter, UploadFile
from klippbok.services.image_service import import_image, apply_crop

router = APIRouter(prefix="/api/v1/images")

@router.post("/upload")
async def upload_image(file: UploadFile) -> ImageResponse:
    saved_path = await _save_upload(file)
    metadata = await import_image(saved_path, get_workspace())
    return ImageResponse.from_metadata(metadata)
```

### Pattern 2: Pydantic Models at Every Boundary

Follow the existing codebase convention -- frozen Pydantic models for all data transfer.

```python
# image/models.py
from pydantic import BaseModel, ConfigDict

class ImageMetadata(BaseModel):
    """Facts about a loaded image. Frozen -- represents state, not mutation."""
    model_config = ConfigDict(frozen=True)

    path: Path
    width: int
    height: int
    format: str  # "JPEG", "PNG", "WEBP"
    file_size: int
    color_mode: str  # "RGB", "RGBA", "L"

class CropRegion(BaseModel):
    """A crop rectangle with optional rotation."""
    model_config = ConfigDict(frozen=True)

    x: int
    y: int
    width: int
    height: int
    rotation: float = 0.0

class CropResult(BaseModel):
    """Result of applying a crop."""
    model_config = ConfigDict(frozen=True)

    output_path: Path
    output_width: int
    output_height: int
    bucket_key: str  # e.g., "512x768"
    required_upscale: bool  # True = quality warning
    scale_factor: float  # <1.0 = downscale, >1.0 = upscale
```

### Pattern 3: FastAPI Serves React SPA in Production

In production mode, FastAPI serves the built React app as static files. During development, Vite dev server proxies API requests to FastAPI.

```python
# api/app.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

app = FastAPI(title="Klippbok")

# API routes first (higher priority)
app.include_router(images_router)
app.include_router(captions_router)
app.include_router(projects_router)

# Serve React SPA for all non-API routes
web_dir = Path(__file__).parent.parent / "web" / "dist"
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="spa")
```

This means a single `pip install klippbok[gui]` and `klippbok serve` starts everything. No separate Node process needed in production.

### Pattern 4: SSE for Job Progress

For long-running operations (batch auto-crop, batch caption), use Server-Sent Events (SSE) rather than WebSocket. SSE is simpler, unidirectional (server to client), and works over standard HTTP.

```python
# api/routes/jobs.py
from fastapi.responses import StreamingResponse

@router.post("/api/v1/jobs/batch-caption")
async def start_batch_caption(request: BatchCaptionRequest):
    job_id = create_job(request)
    background_tasks.add_task(run_batch_caption, job_id, request)
    return {"job_id": job_id}

@router.get("/api/v1/jobs/{job_id}/progress")
async def job_progress(job_id: str):
    async def event_stream():
        async for update in watch_job(job_id):
            yield f"data: {update.model_dump_json()}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

### Pattern 5: Workspace-per-Project

Each project gets a workspace directory on disk. This follows the existing manifest-driven pattern but scoped to a project.

```
~/.klippbok/projects/my-sd15-dataset/
  originals/          # Source images (untouched)
  crops/              # Cropped images (named by stem)
  captions/           # .txt sidecar files
  thumbnails/         # Auto-generated for gallery
  project.json        # Project manifest (single source of truth)
```

The API never writes to arbitrary filesystem locations. All I/O is scoped to the workspace. This is critical for safety -- the GUI should not be able to modify files outside the workspace.

## Anti-Patterns to Avoid

### Anti-Pattern 1: API Routes Calling Domain Functions Directly

**What:** `api/routes/images.py` imports from `klippbok.image.crop` directly, bypassing services.
**Why bad:** Creates two code paths (CLI goes through services, API goes direct). Business logic leaks into the web layer. Testing requires HTTP setup for what should be unit-testable logic.
**Instead:** Always go through `services/`. The API layer only handles HTTP concerns (parsing UploadFile, returning responses).

### Anti-Pattern 2: Storing State in FastAPI Process Memory

**What:** Using in-memory dicts or global state to track project data.
**Why bad:** Lost on restart. Can't be read by CLI. Creates inconsistency between GUI and CLI views.
**Instead:** Use the project manifest (`project.json`) as the single source of truth. Both CLI and API read/write the same file. Use file-locking for concurrent access (unlikely in single-user but good practice).

### Anti-Pattern 3: Server-Side Crop Preview

**What:** Sending crop parameters to the server on every mouse movement, getting back a preview image.
**Why bad:** Horrible latency for interactive editing. Network round-trip per frame makes the crop editor feel laggy.
**Instead:** Canvas-based client-side preview. The server only processes the final crop on "Apply." The browser renders the crop overlay, rotation, and zoom purely in JavaScript.

### Anti-Pattern 4: Celery/Redis for Background Tasks

**What:** Adding Celery + Redis + message broker infrastructure for background jobs.
**Why bad:** Massive infrastructure overhead for a single-user local tool. Klippbok is not a web service -- it runs on one machine for one person.
**Instead:** Use FastAPI's built-in `BackgroundTasks` for simple fire-and-forget operations. For jobs that need progress tracking, use `asyncio.Queue` with SSE streaming. If a job is truly CPU-heavy (batch image processing), use `concurrent.futures.ProcessPoolExecutor` within the FastAPI process.

### Anti-Pattern 5: Separate Database for Project State

**What:** Adding SQLite or PostgreSQL to store project state.
**Why bad:** Overkill for single-user. Existing klippbok uses JSON manifests and the filesystem. Adding a DB creates two sources of truth, migration headaches, and cognitive overhead.
**Instead:** JSON manifest files (project.json) on disk. The filesystem IS the database. Images are files, captions are .txt sidecars, state is a JSON manifest. This is the pattern that already works in klippbok.

## React Frontend Architecture

### Component Hierarchy

```
App
  ProjectView
    Toolbar (model selector, export button)
    ImageGallery
      GalleryItem (thumbnail + status indicators)
    ImageEditor (shown when image selected)
      CropCanvas (HTML5 Canvas for interactive cropping)
        CropOverlay (draggable rectangle with handles)
        BucketSnap (snap-to-ratio guides)
        QualityIndicator (green/red resolution text)
      CropControls (rotation slider, zoom, aspect lock)
      CaptionPanel
        CaptionEditor (text area with tag mode / prose mode)
        CaptionActions (generate, regenerate, edit)
    StatusBar (job progress, validation summary)
```

### Key Frontend Patterns

1. **Canvas for crop, not DOM elements** -- crop editing uses HTML5 Canvas for performance and pixel-accurate rendering.
2. **Optimistic updates** -- when user applies a crop, immediately update the gallery thumbnail while the server processes.
3. **Debounced saves** -- caption edits auto-save with 500ms debounce, not on every keystroke.
4. **React Query (TanStack Query)** for server state -- handles caching, invalidation, and background refetching of project data.

## Suggested Build Order (Dependencies)

The build order is dictated by what depends on what. Each layer must be solid before the next can be built.

### Phase 1: Image Domain Module (`image/`)

**Build first because:** Everything else depends on having image loading, cropping, and validation working. This is pure Python with Pillow, no web concerns.

- `image/models.py` -- ImageMetadata, CropRegion, CropResult, BucketConfig
- `image/loader.py` -- Load image, extract metadata, validate format
- `image/crop.py` -- Crop + resize to bucket, upscale detection
- `image/buckets.py` -- Bucket definitions per model (SD1.5: 512-based, SDXL: 1024-based)
- `image/validate.py` -- Image-specific validation (resolution, format, quality)

**No service layer, no API, no frontend needed.** Test with pytest, use from CLI.

### Phase 2: Service Layer (`services/`)

**Build second because:** Wraps domain logic into use-case functions that both CLI and API will consume.

- `services/image_service.py` -- import, crop, autocrop, validate
- `services/project_service.py` -- create project, list samples, get/update sample state
- `services/caption_service.py` -- generate caption (delegates to existing caption module)

### Phase 3: API Layer (`api/`)

**Build third because:** Exposes services over HTTP. Requires services to be working.

- `api/app.py` -- FastAPI app factory, middleware, CORS
- `api/routes/images.py` -- Upload, crop, autocrop endpoints
- `api/routes/projects.py` -- Project CRUD, sample listing
- `api/routes/captions.py` -- Caption generation, editing
- `api/routes/jobs.py` -- Background job status, SSE progress

### Phase 4: React Frontend (`web/`)

**Build last because:** Consumes the API. Requires API endpoints to be stable.

- Crop editor (Canvas-based, the hardest UI component)
- Image gallery with thumbnails
- Caption editor panel
- Configuration panel (model selection, bucket sizes)
- Export/download functionality

### Cross-Cutting: Config Extension

At each phase, extend `config/data_schema.py` with image-specific config:

```python
class ImageConfig(BaseModel):
    """Image processing configuration (parallel to VideoConfig)."""
    target_model: Literal["sd15", "sdxl", "flux"] = "sd15"
    max_bucket_resolution: int = 512  # SD1.5 default
    upscale_policy: Literal["never", "warn", "allow"] = "warn"
    output_format: Literal["png", "jpg", "webp"] = "png"
    output_quality: int = 95  # JPEG/WebP quality
```

## How GUI Layer Sits on Top of Existing Pipeline

The GUI does NOT replace the pipeline. It provides an interactive frontend for the **same operations** the CLI performs.

| Existing CLI Command | GUI Equivalent |
|---------------------|----------------|
| `python -m klippbok.video ingest` | Not in GUI initially (video pipeline stays CLI-first) |
| `python -m klippbok.dataset validate` | Project view shows validation status per sample |
| `python -m klippbok.dataset organize` | "Export" button in toolbar |
| `python -m klippbok.video caption` | Caption panel with generate/edit per image |
| (no CLI equivalent) | Interactive crop editor |
| (no CLI equivalent) | Auto-crop with subject detection |
| (no CLI equivalent) | Drag-and-drop image upload |

The GUI adds capabilities that don't make sense in CLI (interactive cropping), while the CLI retains capabilities that don't make sense in GUI (batch video ingest of 100GB footage).

Both use the same:
- Service layer functions
- Pydantic models
- Config schema
- Manifest format
- File conventions (stem-matched .txt sidecars)

## Scalability Considerations

| Concern | At 10 images | At 100 images | At 1000 images |
|---------|-------------|---------------|----------------|
| Gallery load | Instant, inline thumbnails | Paginate, lazy-load thumbs | Virtual scrolling, on-demand thumb generation |
| Crop processing | Synchronous, instant response | Synchronous, <1s each | Batch with progress bar, ProcessPoolExecutor |
| Caption generation | Synchronous per-image | Background task with SSE | Background task with SSE, rate limiting |
| Disk usage | Negligible | ~500MB with originals | 5-10GB, need cleanup/archive |
| Export | ZIP in-memory | ZIP streamed | ZIP streamed with progress |

For a single-user local tool, 1000 images is the realistic upper bound. The architecture handles this without any distributed systems.

## Sources

- Existing klippbok codebase analysis (HIGH confidence -- direct code reading)
- [FastAPI Static Files documentation](https://fastapi.tiangolo.com/tutorial/static-files/) (HIGH confidence)
- [FastAPI Background Tasks documentation](https://fastapi.tiangolo.com/tutorial/background-tasks/) (HIGH confidence)
- [FastAPI UploadFile documentation](https://fastapi.tiangolo.com/reference/uploadfile/) (HIGH confidence)
- [React Advanced Cropper](https://advanced-cropper.github.io/react-advanced-cropper/) (MEDIUM confidence -- library option for crop UI)
- [FastAPI and React integration patterns](https://www.joshfinnie.com/blog/fastapi-and-react-in-2025/) (MEDIUM confidence)
- [Background task processing patterns in FastAPI](https://oneuptime.com/blog/post/2026-01-25-background-task-processing-fastapi/view) (MEDIUM confidence)
- [SSE for real-time updates in FastAPI](https://mahdijafaridev.medium.com/implementing-server-sent-events-sse-with-fastapi-real-time-updates-made-simple-6492f8bfc154) (MEDIUM confidence)

---

*Architecture research: 2026-02-27*
