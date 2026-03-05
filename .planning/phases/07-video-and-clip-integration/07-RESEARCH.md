# Phase 7: Video and CLIP Integration - Research

**Researched:** 2026-03-05
**Domain:** Video pipeline GUI exposure, CLIP image triage, InsightFace face clustering, SSE-backed async operations
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **Video workflow scope:** Four CLI commands get GUI exposure — ingest, scan, triage, extract. Caption, score, audit, normalize stay CLI-only.
- **Gallery unification:** Video clips appear in the unified gallery alongside images (not a separate gallery).
- **Video captioning:** Accessible from the existing CaptionPage — backend already supports video captioning, GUI passes clip paths.
- **Ingest config defaults:** Smart defaults (16fps, 720p, auto frames) with an Advanced toggle for threshold, max-frames, resolution.
- **Ingest input:** Both video upload and directory picker supported (upload for small files, directory for large raw footage).
- **Concepts gallery:** Extracted reference frames viewable/manageable in a concepts gallery on the Triage page.
- **Video page:** New nav item. Single page with top tabs: Ingest, Scan, Extract.
- **Triage page:** New nav item. Separate dedicated page for CLIP matching (works with both video clips and images).
- **Nav order:** Gallery > Import > Video > Crop > Caption > Triage > Settings.
- **Gallery filter controls:** All | Images | Videos toggle.
- **Video clip thumbnails:** Play button overlay (centered, semi-transparent) + duration badge (corner, e.g. "3.2s").
- **Lightbox video:** Clicking a video clip in gallery shows video playback with `<video>` element and play controls.
- **Scan tab:** Project-wide auto-scan results. Also shown as per-clip metadata badges on gallery thumbnails (fps, frame count, duration, validation).
- **Image triage UX (ARCH-08):** Concept references added via dedicated 'Add to Concepts' action on gallery images. Additional references uploadable on Triage page concepts gallery panel.
- **Triage result display:** Score overlay on gallery items (similarity badge + color: green=match, yellow=borderline, grey=no match) + results summary panel on Triage page.
- **Threshold:** Adjustable slider (0.5–1.0, default 0.70) with borderline range (threshold-0.1 to threshold = yellow/review zone).
- **Triage results persistence:** Persisted to triage_manifest.json (survives refresh, available for filtered ingest).
- **Auto-subject identification:** Face embeddings via InsightFace for automatic subject identification. Targets character LoRA workflow.
- **Suggested Subjects panel:** On Triage page. User names clusters and confirms — confirmed clusters become concept references.
- **Auto-picks highest-quality image** from each cluster as primary reference; user can swap.
- **Filtered ingest pipeline:** Claude's Discretion on whether triage→filtered ingest runs as connected pipeline or triage produces manifest and user triggers ingest separately.
- **Progress/cancellation:** Video ingest: stage-aware progress bar with SSE. Face embeddings: progress with ETA per image. CLIP triage: simple 0–100% progress bar. All three are cancelable — graceful termination, keeps results produced so far.

### Claude's Discretion

- Video clip thumbnail generation strategy (first frame extraction, caching)
- InsightFace model selection and dependency management (optional `[triage]` extra)
- Face embedding clustering algorithm (DBSCAN, agglomerative, etc.) and similarity threshold
- SSE event naming for video operations (following existing patterns)
- API router organization for video endpoints
- Whether to reuse the existing `triage_manifest.json` format or extend it for GUI-specific fields
- Whether triage→filtered ingest runs as connected pipeline or triage produces manifest first

### Deferred Ideas (OUT OF SCOPE)

None — all discussed items included in phase scope per user decision.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| GUI-08 | Video pipeline accessible from GUI (existing ingest, scan, triage workflows) | Video API routers wrapping klippbok.video.__main__ business logic; SSE for ingest/scan/triage progress; VideoPage with Ingest/Scan/Extract tabs |
| ARCH-08 | Existing CLIP triage extended to work with standalone images | CLIPEmbedder.encode_image() already accepts any image path; triage_service wraps triage_clips() but accepts image paths from project manifest; concepts gallery panel for reference images |
</phase_requirements>

## Summary

Phase 7 is primarily a GUI integration phase — the backend business logic already exists in mature, well-tested form. The `klippbok/triage/` and `klippbok/video/` modules are complete and functional. The work is to expose these via API endpoints, wire them to SSE progress streams, and build the React pages (VideoPage with tabs, TriagePage).

The InsightFace integration is the only genuinely new backend feature. Everything else is plumbing: extract service functions from CLI command handlers (`cmd_ingest`, `cmd_scan`, `cmd_extract`, `cmd_triage` in `klippbok/video/__main__.py`), expose them through FastAPI routers, and connect them via SSE-backed async operations following the exact same pattern established by import, upscale, and caption routers.

The frontend has two new pages plus extensions to GalleryPage, ThumbnailCard, and ImageLightbox. The `GalleryItem` type already has `media_type`, `video_url`, and `full_url` fields — the gallery infrastructure is video-ready. The lightbox already handles video playback (existing `<video>` branch at line 48 of ImageLightbox.tsx).

**Primary recommendation:** Service-extract first (pull business logic from CLI command handlers into `klippbok/services/video_service.py` and `klippbok/services/triage_service.py`), then build API routers, then build React pages. InsightFace should be the final backend piece, kept strictly behind optional dependency guard.

## Standard Stack

### Core (Backend)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| klippbok.triage.embeddings | existing | CLIPEmbedder class | Already written and tested; no new dependency |
| klippbok.triage.triage | existing | triage_clips(), triage_videos() | Orchestrators ready for service wrapping |
| klippbok.video.probe | existing | probe_video(), probe_directory() | Used by scan command |
| klippbok.video.validate | existing | validate_directory(), format_scan_report() | Used by scan command |
| klippbok.video.split | existing | split_video_at_scenes(), split_video_segments() | Used by ingest command |
| klippbok.video.scene | existing | detect_scenes() | Used by ingest command |
| klippbok.video.extract | existing | extract_directory(), extract_from_selections() | Used by extract command |
| insightface | latest compatible with Python 3.11 | Face detection + embedding | Purpose-built for identity matching; more reliable than CLIP for individual people |
| sse-starlette | >=3.2.0 (already installed) | Server-Sent Events | Existing pattern in project |
| fastapi | >=0.100 (already installed) | API routers | Existing |

### Core (Frontend)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React Router v7 | already installed | /video and /triage routes | Existing routing infrastructure |
| Zustand | already installed | Store extensions for triage state | Existing flat store pattern |
| TanStack Query | already installed | Triage results, scan results | Existing data fetching |
| yet-another-react-lightbox | already installed | Video playback in lightbox | Already has video branch code |

### InsightFace Dependency Management
| Approach | Notes |
|----------|-------|
| Optional `[triage]` extra (extend existing) | Add `insightface` and `onnxruntime` (if not already in `[triage]`) to pyproject.toml |
| Runtime guard | Mirror `check_clip_available()` pattern with `check_insightface_available()` |
| Model | buffalo_l — most accurate InsightFace model; auto-downloads on first use to `~/.insightface/` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| InsightFace | DeepFace | InsightFace is more performant for pure embedding extraction; DeepFace is easier to install but slower |
| InsightFace | CLIP for face clustering | CLIP cannot reliably distinguish individual people — InsightFace uses ArcFace-trained identity embeddings |
| DBSCAN clustering | Agglomerative clustering | DBSCAN chosen: no need to specify cluster count, handles noise automatically, common for face clustering |

### Installation
```bash
# InsightFace
pip install insightface onnxruntime

# Already installed (no action needed)
# torch, transformers, sse-starlette, fastapi
```

## Architecture Patterns

### Recommended Project Structure (New Files)
```
klippbok/
├── services/
│   ├── video_service.py         # Ingest/scan/extract service functions (extracted from __main__)
│   └── triage_service.py        # CLIP triage + face embedding service functions
├── api/
│   └── routers/
│       ├── video.py             # /api/v1/video/* endpoints (ingest, scan, extract)
│       └── triage.py            # /api/v1/triage/* endpoints (run, concepts, face)
frontend/src/
├── pages/
│   ├── VideoPage.tsx            # Ingest/Scan/Extract tabs
│   └── TriagePage.tsx           # CLIP matching + face clusters
├── hooks/
│   ├── useIngestEvents.ts       # SSE for video ingest
│   ├── useTriageEvents.ts       # SSE for CLIP triage
│   └── useFaceEvents.ts         # SSE for face embedding computation
└── types/
    └── triage.ts                # TriageResult, ConceptRef, FaceCluster types
```

### Pattern 1: Service Extraction from CLI Handlers

The CLI command handlers in `klippbok/video/__main__.py` contain the business logic as `_ingest_single_video()`, `cmd_scan()`, etc. These must be extracted to a service module. The CLI becomes a thin wrapper calling the service.

```python
# klippbok/services/video_service.py
from klippbok.video.probe import probe_directory
from klippbok.video.validate import validate_directory

def scan_project_videos(
    project_dir: Path,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> ScanReport:
    """Probe and validate all video clips in the project clips directory."""
    clips_dir = project_dir / "clips"  # or wherever clips live
    metadata_list = probe_directory(clips_dir)
    report = validate_directory(clips_dir, video_config, metadata_list=metadata_list)
    return report
```

### Pattern 2: SSE-Backed Async Operations (Established Pattern)

All existing long-running operations (import, upscale, caption) use this identical pattern. Video ingest and CLIP triage MUST follow it.

```python
# klippbok/api/routers/video.py
import asyncio
import uuid
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

router = APIRouter(prefix="/video", tags=["video"])
_queues: dict[str, asyncio.Queue] = {}
_tasks: dict[str, asyncio.Task] = {}

@router.post("/ingest/start")
async def start_ingest(request: IngestRequest, req: Request) -> IngestStarted:
    op_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _queues[op_id] = queue
    task = asyncio.create_task(_run_ingest(request, queue, op_id, project_dir))
    _tasks[op_id] = task
    return IngestStarted(operation_id=op_id)

@router.get("/ingest/{op_id}/events")
async def ingest_events(op_id: str) -> EventSourceResponse:
    async def generator():
        queue = _queues.get(op_id)
        while True:
            event = await queue.get()
            if event is None:  # sentinel
                break
            yield ServerSentEvent(
                data=event.model_dump_json(),
                event="ingest_progress",
            )
    return EventSourceResponse(generator())

@router.post("/ingest/{op_id}/cancel")
async def cancel_ingest(op_id: str) -> dict:
    task = _tasks.get(op_id)
    if task and not task.done():
        task.cancel()
    return {"cancelled": True}
```

### Pattern 3: SSE Event Naming Convention

Following `[04-04 IMP-01]` and `[05-02 UPS-01]` decisions — named events avoid collision with the browser EventSource built-in error event:

| Operation | SSE Event Name | Sentinel Signal |
|-----------|---------------|-----------------|
| Import | `import_progress`, `import_error` | `None` in queue |
| Upscale | `upscale_progress`, `upscale_error` | `None` in queue |
| Caption | `caption_progress`, `caption_error` | `None` in queue |
| Video Ingest | `ingest_progress`, `ingest_error` | `None` in queue |
| CLIP Triage | `triage_progress`, `triage_error` | `None` in queue |
| Face Embedding | `face_progress`, `face_error` | `None` in queue |

### Pattern 4: InsightFace Face Clustering Pipeline

```python
# klippbok/services/triage_service.py
import numpy as np

def compute_face_embeddings(
    image_paths: list[Path],
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, np.ndarray]:
    """Compute InsightFace identity embeddings for all images with detected faces.

    Returns mapping of image_path_str -> 512-dim embedding.
    Images with no detected face are excluded.
    """
    import insightface

    app = insightface.app.FaceAnalysis(name="buffalo_l")
    app.prepare(ctx_id=0)  # 0 = GPU if available, else CPU

    embeddings = {}
    for i, path in enumerate(image_paths):
        if progress_callback:
            progress_callback(i, len(image_paths))
        img = cv2.imread(str(path))
        if img is None:
            continue
        faces = app.get(img)
        if faces:
            # Use the largest/most confident face
            face = max(faces, key=lambda f: f.det_score)
            embeddings[str(path)] = face.normed_embedding
    return embeddings


def cluster_face_embeddings(
    embeddings: dict[str, np.ndarray],
    eps: float = 0.4,
    min_samples: int = 2,
) -> list[FaceCluster]:
    """Cluster face embeddings using DBSCAN.

    eps: maximum cosine distance for two faces to be in same cluster.
    DBSCAN eps in cosine space ~0.4 corresponds to ~similarity 0.6.
    Images that don't fit any cluster are labeled as noise (-1).
    """
    from sklearn.cluster import DBSCAN

    paths = list(embeddings.keys())
    vectors = np.array(list(embeddings.values()))

    # DBSCAN with cosine metric
    clustering = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine')
    labels = clustering.fit_predict(vectors)

    clusters: dict[int, list[str]] = {}
    for path, label in zip(paths, labels):
        if label == -1:
            continue  # noise point - no cluster
        clusters.setdefault(label, []).append(path)

    return [FaceCluster(image_paths=v) for v in clusters.values()]
```

### Pattern 5: Video Clip Thumbnail Generation

First frame extraction via ffmpeg, cached by SHA256[:16] of clip path (matching existing thumbnail cache key pattern from `[04-01 API-02]`):

```python
# In klippbok/api/thumbnail.py (extend existing)
def generate_video_thumbnail(video_path: Path, cache_dir: Path) -> Path:
    """Extract first frame of a video clip and cache as JPEG thumbnail."""
    import subprocess

    cache_key = hashlib.sha256(str(video_path.resolve()).encode()).hexdigest()[:16]
    thumb_path = cache_dir / f"{cache_key}.jpg"

    if thumb_path.exists():
        return thumb_path

    cache_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-i", str(video_path),
        "-vframes", "1",        # extract exactly 1 frame
        "-q:v", "3",            # JPEG quality
        str(thumb_path),
    ], capture_output=True, check=True)

    return thumb_path
```

### Pattern 6: Gallery Filter State (Zustand Extension)

Extend the existing flat Zustand store with gallery filter state:

```typescript
// appStore.ts additions
interface AppState {
  // ... existing fields ...

  // gallery filter
  galleryFilter: 'all' | 'images' | 'videos'
  setGalleryFilter: (filter: 'all' | 'images' | 'videos') => void

  // triage state
  triageResults: Map<string, TriageScore>  // image_id -> score
  setTriageResults: (results: Map<string, TriageScore>) => void
  clearTriageResults: () => void
}
```

### Pattern 7: Triage Score Overlay on ThumbnailCard

The ThumbnailCard receives `item: GalleryItem`. Triage scores are kept in the Zustand store, not in GalleryItem (scores are volatile, not persisted in manifest until run completes). ThumbnailCard reads from the store directly:

```tsx
// ThumbnailCard extension
const triageScore = useAppStore((s) => s.triageResults.get(item.id))

// Score badge: green (>=threshold), yellow (>=threshold-0.1), none
const triageBadgeColor = triageScore
  ? triageScore.score >= threshold ? 'green'
    : triageScore.score >= threshold - 0.1 ? 'yellow'
    : 'grey'
  : null
```

### Anti-Patterns to Avoid

- **Duplicating business logic between CLI and API:** The CLI command handlers contain business logic mixed with argparse wiring. Extract service functions BEFORE writing routers. Never copy-paste logic.
- **Blocking the async event loop with CLIP/InsightFace:** Both are CPU/GPU-bound. Always wrap in `asyncio.get_event_loop().run_in_executor(None, lambda: ...)` — exact same approach as `batch_import_images` in `import_.py`.
- **Loading CLIP model per request:** CLIPEmbedder loads a ~600MB model. Cache it on `app.state.clip_embedder` or use module-level singleton — do NOT instantiate per API call.
- **Hard-coding clips directory path:** The project structure lets users choose where clips live. Pass the path from the GUI; don't assume a fixed `clips/` subfolder.
- **Registering catch-all routes before specific ones:** Follows `[04-01 API-03]` — routers registered before StaticFiles mount. Within a router, specific paths before parameterized ones.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Face identity embeddings | Custom CNN face embedding | insightface with buffalo_l model | ArcFace-trained, battle-tested, handles occlusion/lighting variation |
| Face clustering | K-means with manual k | DBSCAN from sklearn | DBSCAN finds cluster count automatically; handles noise; standard for face clustering |
| Scene detection | Frame differencing in Python | klippbok.video.scene.detect_scenes() | Already wraps scenedetect library with tuned defaults |
| CLIP embeddings | PyTorch CLIP from scratch | klippbok.triage.embeddings.CLIPEmbedder | Already written, tested, handles batching and normalization |
| Video metadata | ffprobe subprocess manually | klippbok.video.probe.probe_video() | Already handles all edge cases (VFR, missing nb_frames, SAR normalization) |
| Video thumbnail | OpenCV first frame | ffmpeg via subprocess (one command) | Already a dependency via scenedetect; reliable for all containers |
| SSE progress events | WebSockets or polling | sse-starlette (existing) | Already installed and in use; simpler than WebSockets for one-way streams |

**Key insight:** The entire backend pipeline — video probing, scene detection, splitting, CLIP embedding, triage matching — is already implemented. Phase 7's backend work is 80% plumbing (service extraction + API routing) and 20% new code (InsightFace, triage_service.py, video_service.py).

## Common Pitfalls

### Pitfall 1: CLIP Model Loaded Multiple Times
**What goes wrong:** Each triage API call instantiates a new CLIPEmbedder, causing 5–10 second delays and 600MB memory spikes.
**Why it happens:** CLIPEmbedder is instantiated inside the request handler without caching.
**How to avoid:** Cache on `app.state.clip_embedder = None` in `create_app()`. Lazy-initialize on first triage request. The embedder is stateless after loading.
**Warning signs:** First triage request takes 10+ seconds every time.

### Pitfall 2: InsightFace Model Not Found
**What goes wrong:** `insightface.app.FaceAnalysis(name="buffalo_l")` tries to download ~500MB model on first use. On a restricted network this hangs indefinitely.
**Why it happens:** InsightFace auto-downloads to `~/.insightface/` by default.
**How to avoid:** Call `app.prepare(ctx_id=-1)` (CPU mode) with a timeout wrapper. Expose a health check endpoint that tells the GUI if the model is downloaded. Show download progress in the UI if model is missing.
**Warning signs:** Face computation hangs without progress.

### Pitfall 3: Video Thumbnail Generation Blocks Event Loop
**What goes wrong:** ffmpeg thumbnail extraction (subprocess) blocks the FastAPI async event loop, causing other requests to time out.
**Why it happens:** `subprocess.run()` is synchronous.
**How to avoid:** Use `asyncio.get_event_loop().run_in_executor(None, lambda: subprocess.run(...))` for thumbnail generation in async endpoints.
**Warning signs:** Gallery loads freeze when thumbnails are being generated.

### Pitfall 4: triage_manifest.json Format Mismatch
**What goes wrong:** Existing `triage_manifest.json` format (from `_write_manifest()` in `triage.py`) doesn't have GUI-specific fields like `triage_score` per image. Reading it from the GUI fails.
**Why it happens:** The manifest was designed for CLI consumption (filtered ingest), not GUI display.
**How to avoid:** Extend the manifest format with optional GUI fields rather than replacing it. The `include` field and `matches` array are needed by filtered ingest; GUI adds `triage_score` as supplementary data.
**Warning signs:** GUI can't display triage results after page refresh.

### Pitfall 5: Cancellation Leaves Temp Files
**What goes wrong:** Canceling CLIP triage mid-run leaves temp frame images in system temp directory.
**Why it happens:** `sample_clip_frames()` creates temp files; `cleanup_frames()` is called at the end of the loop. Cancellation via `task.cancel()` raises `CancelledError` before cleanup.
**How to avoid:** Wrap the ingest/triage loop body in a `try/finally` that calls `cleanup_frames()`. Track all temp paths created and clean up in the finally block even on cancellation.
**Warning signs:** System temp directory fills with frame PNG files after cancelled operations.

### Pitfall 6: InsightFace opencv-python Conflict
**What goes wrong:** insightface requires `opencv-python` (or `opencv-python-headless`). The project may already have opencv via `scenedetect[opencv]`. Version conflicts cause import errors.
**Why it happens:** `scenedetect[opencv]` pulls in `opencv-python`; insightface may want a specific version.
**How to avoid:** Check `pip show opencv-python` before adding insightface. Use `insightface` with `onnxruntime` (not torch backend) to minimize dependency conflicts. `opencv-python-headless` preferred on servers.
**Warning signs:** `ImportError: cannot import name 'cv2'` or OpenCV version mismatch at import time.

### Pitfall 7: Gallery Filter Not Applied on Backend vs Frontend
**What goes wrong:** Gallery filter (All/Images/Videos) toggles that only exist in frontend state get out of sync with the data from `/api/v1/images/`.
**Why it happens:** The images endpoint returns all items; filtering is client-side. If a new navigation event triggers a re-fetch, the filter state gets reset.
**How to avoid:** Store gallery filter in Zustand (survives navigation within session). Filter is applied in the `useImages` hook via `.filter()` on the fetched data, not as a query param.

## Code Examples

Verified patterns from existing codebase:

### SSE Queue Pattern (from import_.py)
```python
# Source: klippbok/api/routers/import_.py
_queues: dict[str, asyncio.Queue] = {}
_tasks: dict[str, asyncio.Task] = {}

# Start operation:
op_id = str(uuid.uuid4())
queue: asyncio.Queue = asyncio.Queue()
_queues[op_id] = queue
task = asyncio.create_task(_run_import(request, queue, op_id, project_dir))
_tasks[op_id] = task

# Signal end of stream:
await queue.put(None)  # sentinel

# SSE generator:
async def _event_generator(queue):
    while True:
        event = await queue.get()
        if event is None:
            break
        yield ServerSentEvent(data=event.model_dump_json(), event="ingest_progress")
```

### Run CPU-Bound Work in Executor (from import_.py)
```python
# Source: klippbok/api/routers/import_.py
# Pattern [04-04 IMP-03]: run synchronous/CPU-bound code in executor
result = await asyncio.get_event_loop().run_in_executor(
    None,
    lambda: some_synchronous_function(args),
)
```

### SHA256 Item ID Pattern (from images.py)
```python
# Source: klippbok/api/routers/images.py [04-01 API-01]
import hashlib
def _image_id(relative_path: str) -> str:
    return hashlib.sha256(relative_path.encode()).hexdigest()[:16]
```

### CLIPEmbedder Usage (from triage/embeddings.py)
```python
# Source: klippbok/triage/embeddings.py
embedder = CLIPEmbedder(model_name="openai/clip-vit-base-patch32")  # loads ~600MB

# Single image
embedding = embedder.encode_image(Path("reference.jpg"))  # returns (512,) ndarray

# Batch images (more efficient)
embeddings = embedder.encode_images([Path("img1.jpg"), Path("img2.jpg")])

# Cosine similarity (embeddings are L2-normalized, so dot product = cosine sim)
score = CLIPEmbedder.similarity(emb1, emb2)  # float 0.0-1.0

# Best match across multiple frames
best_score, best_idx = CLIPEmbedder.best_match_score(frame_embeddings, ref_embedding)
```

### triage_clips() Signature (from triage/triage.py)
```python
# Source: klippbok/triage/triage.py
report = triage_clips(
    clips_dir="path/to/clips",
    concepts_dir="path/to/concepts",
    threshold=0.70,
    frames_per_clip=5,
    model_name="openai/clip-vit-base-patch32",
    output_path="path/to/triage_manifest.json",  # optional
)
# Returns TriageReport (short clips) or VideoTriageReport (long videos)
```

### discover_concepts() Usage (from triage/concepts.py)
```python
# Source: klippbok/triage/concepts.py
# Expects concepts/  structure:
#   concepts/character/holly.jpg
#   concepts/style/vintage.png
concepts = discover_concepts(concepts_dir)
# Returns list[ConceptReference] with name, concept_type, image_path, folder_name
```

### probe_video() for Scan Results (from video/probe.py)
```python
# Source: klippbok/video/probe.py
from klippbok.video.probe import probe_video, probe_directory

meta = probe_video(path)
# VideoMetadata: width, height, fps, frame_count, duration, codec, has_audio, ...

metadata_list = probe_directory(directory)
# list[VideoMetadata] sorted by filename, skips unreadable files with warning
```

### NavBar Pattern for New Nav Items (from frontend/src/components/Layout/NavBar.tsx)
```tsx
// Source: frontend/src/components/Layout/NavBar.tsx
// New items follow NavLink pattern with isActive className function
<NavLink to="/video" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
  Video
</NavLink>
<NavLink to="/triage" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
  Triage
</NavLink>
```

### Zustand Flat Store Extension (from stores/appStore.ts)
```typescript
// Source: frontend/src/stores/appStore.ts
// Extend AppState interface and add to create() call
// Keep flat (no nested objects per [04-02] decision)
galleryFilter: 'all' as 'all' | 'images' | 'videos',
setGalleryFilter: (filter) => set({ galleryFilter: filter }),
triageResults: new Map<string, TriageScore>(),
setTriageResults: (results) => set({ triageResults: results }),
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| CLIP-only for person matching | CLIP for scene/style + InsightFace for identity | InsightFace 0.7+ / 2023 | Identity-critical workflows (character LoRA) get reliable person matching |
| Manual concept folder management | GUI "Add to Concepts" contextual action | Phase 7 | Concepts accumulate naturally during normal gallery workflow |
| triage → CLI ingest (two separate commands) | triage → GUI-triggered filtered ingest option | Phase 7 | Keeps results in context for user review before ingest |

**Deprecated/outdated:**
- `triage_videos()` called directly from GUI: keep using `triage_clips()` which auto-detects short vs long video mode — single entry point handles both cases.

## Open Questions

1. **InsightFace on Windows with CPU-only**
   - What we know: InsightFace supports CPU via onnxruntime. Buffalo_l model is ~500MB download.
   - What's unclear: Whether `ctx_id=-1` (CPU mode) works cleanly on Windows 11 with Python 3.11 without CUDA. The user's system does not have CUDA confirmed.
   - Recommendation: Default to `ctx_id=-1` (CPU). Add health check endpoint that tests InsightFace import and returns GPU availability. Do not assume GPU.

2. **Filtered ingest as connected pipeline or separate trigger**
   - What we know: Claude's Discretion. The triage manifest format already has `include: true/false` per scene.
   - What's unclear: Whether GUI value of connecting triage → ingest outweighs the complexity of managing a two-step async operation.
   - Recommendation: Keep them separate for Phase 7. Triage writes the manifest, shows results. User reviews, then clicks "Run Filtered Ingest" button on the Triage page which triggers the ingest router. This mirrors how the CLI works and avoids managing a compound async operation.

3. **Concepts directory location relative to project**
   - What we know: CLI expects a `concepts/` dir. Project manifest lives in `.klippbok/manifest.json`.
   - What's unclear: Whether concepts should live at `{project_dir}/concepts/` or be user-specified per triage run.
   - Recommendation: Default to `{project_dir}/concepts/`. Show the path in the Triage page UI. Allow override per-run via a path input.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing, configured in pyproject.toml) |
| Config file | `pyproject.toml` [tool.pytest.ini_options] testpaths = ["tests"] |
| Quick run command | `pytest tests/test_triage_models.py tests/test_video_probe.py -x` |
| Full suite command | `pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GUI-08 | Video ingest API starts and returns operation_id | integration | `pytest tests/test_video_api.py::test_ingest_start -x` | Wave 0 |
| GUI-08 | Scan API returns video metadata list | integration | `pytest tests/test_video_api.py::test_scan -x` | Wave 0 |
| GUI-08 | Extract API starts and returns operation_id | integration | `pytest tests/test_video_api.py::test_extract_start -x` | Wave 0 |
| GUI-08 | Cancel ingest operation terminates gracefully | integration | `pytest tests/test_video_api.py::test_ingest_cancel -x` | Wave 0 |
| ARCH-08 | CLIP triage accepts image paths (not just clip paths) | unit | `pytest tests/test_triage_service.py::test_triage_images -x` | Wave 0 |
| ARCH-08 | Triage results persist to triage_manifest.json | unit | `pytest tests/test_triage_service.py::test_triage_manifest_write -x` | Wave 0 |
| ARCH-08 | Face embedding returns dict of path->embedding | unit | `pytest tests/test_face_service.py::test_face_embeddings -x` | Wave 0 |
| ARCH-08 | DBSCAN clustering groups similar faces | unit | `pytest tests/test_face_service.py::test_face_clustering -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x -k "not test_video_api"` (skip API integration tests that need a running server)
- **Per wave merge:** `pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_video_api.py` — covers GUI-08 API integration (ingest, scan, extract endpoints)
- [ ] `tests/test_triage_service.py` — covers ARCH-08 image-mode triage and manifest writing
- [ ] `tests/test_face_service.py` — covers InsightFace embedding and DBSCAN clustering (with mocked insightface for CI)
- [ ] `tests/test_video_service.py` — covers extracted video service functions

*(All existing test files in `tests/` cover prior phases and remain unaffected)*

## Sources

### Primary (HIGH confidence)
- Direct code inspection: `klippbok/triage/embeddings.py` — CLIPEmbedder API surface verified
- Direct code inspection: `klippbok/triage/triage.py` — triage_clips() / triage_videos() signatures and manifest format verified
- Direct code inspection: `klippbok/video/__main__.py` — CLI command handler patterns for service extraction
- Direct code inspection: `klippbok/api/routers/import_.py` — SSE pattern to replicate
- Direct code inspection: `klippbok/api/app.py` — router registration order requirement
- Direct code inspection: `frontend/src/stores/appStore.ts` — Zustand flat store pattern
- Direct code inspection: `frontend/src/types/image.ts` — GalleryItem already has media_type, video_url fields
- Direct code inspection: `pyproject.toml` — dependency groups, confirmed torch/transformers in `[triage]`, onnxruntime in `[triage]`

### Secondary (MEDIUM confidence)
- InsightFace buffalo_l model: standard recommendation from InsightFace docs for ArcFace-based identity recognition
- DBSCAN for face clustering: established pattern in the face recognition community; sklearn implementation is standard

### Tertiary (LOW confidence)
- InsightFace Windows/CPU compatibility specifics: based on project README and known community usage patterns; should be verified with a test install before committing to it

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — all backend libraries are already in the codebase and tested; InsightFace is well-known
- Architecture: HIGH — patterns are directly derived from existing code; service extraction approach matches existing `services/` module structure
- Pitfalls: HIGH for CLIP/SSE pitfalls (verified from code); MEDIUM for InsightFace-specific issues (common knowledge, unverified on this specific Windows setup)

**Research date:** 2026-03-05
**Valid until:** 2026-04-05 (stable libraries, 30-day validity)
