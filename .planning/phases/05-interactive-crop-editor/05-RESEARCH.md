# Phase 5: Interactive Crop Editor - Research

**Researched:** 2026-03-03
**Domain:** React interactive crop UI, subject detection, subprocess upscaling, Pillow image processing
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Gallery Selection**
- Click-to-select mode: toggle button enables selection mode; clicking thumbnails selects (highlighted border) instead of opening lightbox
- Smart filter helpers: Select All, Deselect All, plus filter-based selection ("Select all passing quality", "Select all non-duplicates") leveraging existing quality/duplicate data
- Single "Process" button appears when >=1 image selected — navigates to wizard-style pipeline page (upscale → crop flow)
- Selected image IDs persist in Zustand store (survive page navigation, lost on browser refresh — session only)

**Upscale Workflow**
- Subprocess integration (like ffmpeg): klippbok calls SeedVR2's venv Python (`batch_upscale.py`) as a subprocess, parses stdout for progress
- Auto-detect SeedVR2 installation at common paths (e.g., C:\GenAI\Tools\SeedVR2) + environment variables; falls back to manual settings page configuration if not found
- Default upscaler: SeedVR2 3B FP8, 2x scale factor, LAB color correction, VAE tiling enabled, model caching enabled
- NMKD-Siax included as an alternative upscaler option (ESRGAN via spandrel, faster but lower quality)
- Minimal UI: upscaler dropdown (SeedVR2 / NMKD-Siax) + scale factor dropdown (2x default). All other settings use optimal defaults
- Simple progress bar: "Upscaling 3/20 images..." with percentage
- Surface OOM or performance issues to user with clear error messages
- VRAM freed when upscaling completes (subprocess termination handles this automatically)
- 3B FP8 is the right model for training data prep

**Crop Editor Entry & Layout**
- Dedicated route: /crop as a top-level page
- "Crop" added as a nav bar item
- Batch grid layout: all selected images in a scrollable grid, each with its own crop rectangle, rotation controls, and zoom slider
- Responsive columns adapting to screen width, maximum 4 columns wide
- Each card shows: filename + original dimensions + quality badge (sharp/blurry) in header
- +/x buttons on each card for include/exclude from dataset
- Excluded images removed from grid immediately

**Crop Interaction**
- Global controls at top: Bucket Size dropdown (512 / 768 / 1024) + "Allow Non-Square" checkbox (checked by default)
- Allow Non-Square unchecked = all crops locked to 1:1 square
- Default drag: crop rectangle locked to current bucket aspect ratio
- CTRL+drag: freeform resize. Behavior on CTRL release: snaps to nearest valid bucket ratio
- Resolution readout: green text + down arrow (downscale OK) or red text + up arrow (upscale quality loss) + aspect ratio badge

**Auto-crop**
- Manual "Auto-crop All" button at top of crop page — not automatic on import
- Full body priority: try to include full body first, only zoom to face if body doesn't fit
- Center crop fallback when no subject detected
- No visual indicator needed for center-crop fallback

**Crop Persistence & Save**
- Crops held in browser state (Zustand) during editing — session only
- "Proceed to Captioning" button saves all crops: server generates actual cropped+resized image files at bucket dimensions
- Original images always preserved
- User can navigate back to crop page to re-crop (non-destructive)

### Claude's Discretion
- Exact crop handle styling and drag behavior implementation details
- NMKD-Siax subprocess integration approach (spandrel or direct realesrgan-ncnn-vulkan)
- Auto-crop subject detection model choice (YOLO, MediaPipe, etc.)
- Exact wizard page layout for the Process flow (upscale → crop transitions)
- Error handling and retry behavior for upscaler subprocess failures

### Deferred Ideas (OUT OF SCOPE)
- Per-image crop memory persisted across sessions (ADV-01)
- Batch auto-crop with review queue (ADV-04)
- Backend crop coordinate persistence to manifest for cross-session recovery
- SeedVR2 7B model option
- Additional upscaler models beyond SeedVR2 and NMKD-Siax
- Phase 6 (Captioning) connection details
- Phase 8 (Export) scope adjustment for pre-cropped images
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CROP-01 | Interactive crop editor with draggable/resizable rectangle overlay on image | react-advanced-cropper 0.20.1 provides full-featured stencil with handles; renders into per-card containers in the batch grid |
| CROP-02 | Crop rectangle snaps to nearest valid training aspect ratio on resize release | RectangleStencil `aspectRatio` prop + `onInteractionEnd` callback from cropper; nearest-AR snap implemented in JS calling existing `assign_to_bucket` logic |
| CROP-03 | CTRL+resize allows freeform resize, snaps to nearest valid bucket ratio on key release | Custom stencil wrapper intercepts keydown/keyup for CTRL state; switches stencil between locked and free aspect ratio modes |
| CROP-04 | Real-time resolution display during crop (green=downscale ok, red=upscale quality loss) | `onChange` callback gives current coordinates; compute scaled dimensions client-side using bucket math; reuse StatusStrip color pattern |
| CROP-05 | Zoom slider for navigating high-resolution source images | `cropperRef.current.zoomImage(factor)` tied to `<input type="range">` slider |
| CROP-06 | Rotation controls (90-degree increments) and horizontal/vertical flip | `cropperRef.current.rotateImage(90)` and `cropperRef.current.flip(h, v)` from advanced-recipes |
| CROP-07 | Auto-crop with subject detection places crop rectangle on detected subject | Backend: MediaPipe Pose Landmarker (preferred) gives full-body bbox; fallback to face detector. Returns crop coordinates; frontend sets stencil position |
| CROP-08 | Auto-crop falls back to center crop when no subject detected | Backend `auto_crop_image()` returns center-crop coordinates when MediaPipe detects no person |
| CROP-09 | User can adjust auto-crop result via interactive crop editor | Natural: stencil starts at auto-crop coordinates; user drags to adjust |
| GUI-05 | Crop editor accessible from gallery (click image → crop tool) | Selection mode in GalleryPage + "Process" button navigates to /crop with selectedImageIds in Zustand |
</phase_requirements>

---

## Summary

Phase 5 has three distinct sub-domains: (1) gallery selection UX, (2) upscale subprocess pipeline, (3) interactive batch crop editor. The signature technical challenge is the bucket-snapping crop interaction — building an interactive cropper where resize operations snap to valid LoRA training aspect ratios.

**react-advanced-cropper 0.20.1** is the verified library for the crop UI. It provides `RectangleStencil` with `aspectRatio` prop, ref methods for rotate/flip/zoom, and `onChange` callbacks for real-time coordinate tracking. The bucket-snapping behavior requires a thin wrapper: hold current bucket AR in state, pass to stencil `aspectRatio` prop, and on CTRL+drag release call `assign_to_bucket` in JS (mirror of the Python logic already in `klippbok/image/bucket.py`).

The **SeedVR2 subprocess** integration is straightforward — `subprocess.Popen` with stdout line-by-line parsing for progress, using the existing SSE pattern from the import router. `batch_upscale.py` already handles the heavy lifting; klippbok wraps it. SeedVR2's debug output includes "Processing file N/total" lines which can be parsed for progress.

**Auto-crop subject detection**: MediaPipe Pose Landmarker is the best fit — it provides 33 full-body landmarks from which a tight bounding box can be derived (min/max of landmark coordinates). It is lightweight (~5MB model), CPU-capable, has no CUDA requirement, and handles the photographic-person content described in the phase spec. YOLO would also work but adds a heavier dependency. MediaPipe face detector is the fallback within MediaPipe when pose returns no detections.

**Primary recommendation:** Use react-advanced-cropper 0.20.1 for the crop UI with RectangleStencil's `aspectRatio` prop dynamically set from the bucket selection; use MediaPipe Pose Landmarker for auto-crop subject detection; wrap SeedVR2 batch_upscale.py as a Popen subprocess with line-parse progress reporting.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| react-advanced-cropper | 0.20.1 | Interactive crop rectangle with handles, zoom, rotate, flip | Only React crop library with full ref API (rotate/flip/zoom), custom stencil support, and aspect ratio range constraint. The STATE.md blocker note cites this library specifically. |
| mediapipe | 0.10.x | Full-body and face subject detection for auto-crop | Lightweight (~5MB pose model), no CUDA required, provides 33 body landmarks for tight bbox derivation. Google-maintained. |
| Pillow (PIL) | already installed | Server-side crop+resize+rotate execution | Already in project deps; `crop()` + `resize(LANCZOS)` + `transpose(ROTATE_90)` covers all needed ops. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sse-starlette | already installed | SSE progress stream for upscale operation | Reuse exact pattern from import_ router |
| asyncio + run_in_executor | stdlib | Run CPU-bound crop-apply and subprocess monitoring off the event loop | Subprocess stdout reading blocks — must use thread executor |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| react-advanced-cropper | react-easy-crop | react-easy-crop has simpler API but no ref methods for zoom/rotate, no custom stencil for AR-snapping behavior |
| react-advanced-cropper | Cropper.js (react-cropper) | Cropper.js last published >2 years ago, no active maintenance |
| MediaPipe Pose | ultralytics YOLO11n | YOLO is excellent but adds `ultralytics` package (heavy). MediaPipe already maps to klippbok's photo-of-people use case with smaller install footprint |
| MediaPipe Pose | OpenCV DNN | Less accurate, harder to extract tight body bbox |

**Installation:**
```bash
# Frontend
npm install react-advanced-cropper

# Backend (new optional dep group)
pip install mediapipe
```

---

## Architecture Patterns

### Recommended Project Structure
```
frontend/src/
├── pages/
│   ├── CropPage.tsx           # Main /crop route — batch grid + global controls
│   └── ProcessPage.tsx        # Wizard page: upscale step → crop step
├── components/
│   └── Crop/
│       ├── CropCard.tsx       # Per-image card: cropper + controls + readout
│       ├── CropReadout.tsx    # Resolution display (green/red + arrow + AR badge)
│       ├── BucketSelector.tsx # Global bucket size dropdown + non-square checkbox
│       └── UpscaleStep.tsx    # Upscale wizard step with progress bar
├── hooks/
│   ├── useUpscaleEvents.ts    # SSE hook for upscale progress (clone of useImportEvents)
│   └── useCropState.ts        # Per-card crop coordinate state management
├── stores/
│   └── appStore.ts            # Extend: selectedImageIds, cropStates map
└── types/
    └── crop.ts                # CropState, BucketSize, CropCoordinates types

klippbok/
├── api/routers/
│   ├── crop.py                # POST /crop/apply — save cropped images
│   └── upscale.py             # POST /upscale/start, GET /upscale/{op_id}/events
├── services/
│   ├── crop_service.py        # apply_crop(), apply_crops_batch()
│   └── upscale_service.py     # start_upscale_subprocess(), detect_seedvr2()
└── image/
    └── autocrop.py            # auto_crop_image() — MediaPipe + center fallback
```

### Pattern 1: Dynamic Bucket Aspect Ratio Snapping

**What:** The cropper `aspectRatio` prop is set from React state. On CTRL keydown, set `isFreeform=true` (pass `undefined` to `aspectRatio`). On CTRL keyup or `onInteractionEnd`, call `snapToNearestBucket()` which mirrors `assign_to_bucket` in JavaScript and updates both the stencil's AR and the displayed readout.

**When to use:** Every resize interaction in CropCard.

**Example:**
```typescript
// Source: react-advanced-cropper docs + bucket.py mirror
const buckets = generateBuckets(bucketSize, allowNonSquare)

function snapToNearestBucket(width: number, height: number): [number, number] {
  const ar = width / height
  return buckets.reduce((best, b) => {
    const diff = Math.abs(b[0] / b[1] - ar)
    const bestDiff = Math.abs(best[0] / best[1] - ar)
    return diff < bestDiff ? b : best
  })
}

// In CropCard:
const [isCtrlHeld, setIsCtrlHeld] = useState(false)
const [lockedAR, setLockedAR] = useState<number>(buckets[0][0] / buckets[0][1])

// Pass to stencil:
<Cropper
  ref={cropperRef}
  src={image.full_url}
  stencilProps={{ aspectRatio: isCtrlHeld ? undefined : lockedAR }}
  onChange={handleChange}
/>

// On CTRL release / interaction end:
function handleInteractionEnd() {
  const coords = cropperRef.current?.getCoordinates()
  if (coords && isCtrlHeld === false) {
    const [bw, bh] = snapToNearestBucket(coords.width, coords.height)
    setLockedAR(bw / bh)
  }
}
```

### Pattern 2: SeedVR2 Subprocess with SSE Progress

**What:** `upscale_service.py` uses `subprocess.Popen` to call `venv/Scripts/python.exe batch_upscale.py`. A background thread reads stdout line by line; matching lines feed an `asyncio.Queue`. SSE router converts the queue to an event stream — exact clone of import_ router pattern.

**When to use:** POST `/api/v1/upscale/start` trigger.

**Example:**
```python
# Source: pattern from klippbok/api/routers/import_.py + SeedVR2 inspection
import subprocess, asyncio, threading

def _stdout_reader(proc: subprocess.Popen, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """Read SeedVR2 stdout in a background thread, push progress to asyncio queue."""
    for line in iter(proc.stdout.readline, ""):
        # SeedVR2 inference_cli.py logs: "Processing file N/M: filename"
        if "Processing file" in line:
            match = re.search(r"Processing file (\d+)/(\d+)", line)
            if match:
                current, total = int(match.group(1)), int(match.group(2))
                asyncio.run_coroutine_threadsafe(
                    queue.put(UpscaleProgress(current=current, total=total)),
                    loop
                )
    asyncio.run_coroutine_threadsafe(queue.put(None), loop)  # sentinel

async def start_upscale(request: UpscaleRequest, queue: asyncio.Queue) -> str:
    seedvr2_python = detect_seedvr2_python()  # C:\GenAI\Tools\SeedVR2\venv\Scripts\python.exe
    cmd = [seedvr2_python, "batch_upscale.py", request.input_dir, "--output", request.output_dir,
           "--preset", "balanced"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, cwd=SEEDVR2_ROOT)
    loop = asyncio.get_event_loop()
    thread = threading.Thread(target=_stdout_reader, args=(proc, queue, loop), daemon=True)
    thread.start()
    return proc
```

### Pattern 3: Server-Side Crop Application

**What:** `POST /api/v1/crop/apply` receives a list of `{image_id, left, top, width, height, rotation, flip_h, flip_v, target_bucket}` items. `crop_service.apply_crop()` opens original with Pillow, applies rotation/flip, crops, resizes to bucket dimensions with LANCZOS, saves alongside original as `{stem}_crop_{bw}x{bh}{ext}`.

**When to use:** User clicks "Proceed to Captioning".

**Example:**
```python
# Source: Pillow docs (pillow.readthedocs.io/en/stable/reference/Image.html)
from PIL import Image
from pathlib import Path

def apply_crop(
    source_path: Path,
    left: int, top: int, width: int, height: int,
    rotation: int,          # 0, 90, 180, 270
    flip_h: bool, flip_v: bool,
    target_width: int, target_height: int,
    output_path: Path,
) -> Path:
    img = Image.open(source_path)

    # Apply rotation (multiples of 90 — use transpose for lossless)
    if rotation == 90:
        img = img.transpose(Image.Transpose.ROTATE_90)
    elif rotation == 180:
        img = img.transpose(Image.Transpose.ROTATE_180)
    elif rotation == 270:
        img = img.transpose(Image.Transpose.ROTATE_270)

    # Apply flip
    if flip_h:
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if flip_v:
        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    # Crop to selection coordinates
    cropped = img.crop((left, top, left + width, top + height))

    # Resize to exact bucket dimensions
    resized = cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)
    resized.save(output_path)
    return output_path
```

### Pattern 4: MediaPipe Auto-Crop

**What:** `klippbok/image/autocrop.py` loads MediaPipe Pose Landmarker, runs inference on the image, derives a bounding box from visible landmarks, pads it, then maps to the nearest valid bucket crop. Falls back to center crop on no detection.

**When to use:** `POST /api/v1/crop/auto` (called from "Auto-crop All" button).

**Example:**
```python
# Source: ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

def auto_crop_image(
    image_path: Path,
    buckets: list[tuple[int, int]],
) -> tuple[int, int, int, int]:
    """Returns (left, top, width, height) crop coordinates."""
    with mp_vision.PoseLandmarker.create_from_options(OPTIONS) as detector:
        mp_image = mp.Image.create_from_file(str(image_path))
        result = detector.detect(mp_image)

    if not result.pose_landmarks:
        # Center crop fallback (CROP-08)
        return _center_crop(mp_image.width, mp_image.height, buckets)

    # Derive bounding box from all visible landmarks
    xs = [lm.x * mp_image.width for lm in result.pose_landmarks[0]]
    ys = [lm.y * mp_image.height for lm in result.pose_landmarks[0]]
    bbox_left, bbox_top = int(min(xs)), int(min(ys))
    bbox_w = int(max(xs)) - bbox_left
    bbox_h = int(max(ys)) - bbox_top

    # Add 10% padding
    pad_x, pad_y = int(bbox_w * 0.10), int(bbox_h * 0.10)
    bbox_left = max(0, bbox_left - pad_x)
    bbox_top = max(0, bbox_top - pad_y)
    bbox_w = min(mp_image.width - bbox_left, bbox_w + 2 * pad_x)
    bbox_h = min(mp_image.height - bbox_top, bbox_h + 2 * pad_y)

    # Assign to nearest bucket ratio, expand to match
    bucket = assign_to_bucket(bbox_w, bbox_h, buckets)
    if bucket is None:
        return _center_crop(mp_image.width, mp_image.height, buckets)

    return _fit_crop_to_bucket(bbox_left, bbox_top, bbox_w, bbox_h,
                               bucket, mp_image.width, mp_image.height)
```

### Anti-Patterns to Avoid

- **One Cropper component for all images:** Each card needs its own `<Cropper>` instance with its own ref. Do not share a single cropper instance across the grid — state will bleed between cards.
- **Applying AR snap inside onChange:** `onChange` fires on every pixel move. Do AR snap only on `onInteractionEnd` (resize released) or CTRL keyup to avoid thrashing state.
- **Blocking the event loop with subprocess:** SeedVR2 runs for minutes. Must use `threading.Thread` for stdout reading + `asyncio.run_coroutine_threadsafe` to push to the queue — never `await proc.communicate()` which would block.
- **Using `subprocess.run()` for upscale:** `subprocess.run()` blocks until completion. Must use `subprocess.Popen()` for streaming stdout progress.
- **Hardcoding SeedVR2 path:** Always auto-detect with fallback to settings; user path is stored in settings, not hardcoded.
- **Generating crops at save time from localStorage coordinates:** Crop coordinates live in Zustand (in-memory JS). The "Proceed to Captioning" click must POST all crop states to the backend in one call — don't rely on persisted client state surviving a reload.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Crop rectangle with handles | Custom SVG drag handles | react-advanced-cropper RectangleStencil | Edge cases: aspect ratio enforcement, diagonal resize, touch support, coordinate clamping to image bounds |
| Aspect ratio snapping math | Custom AR distance function | Mirror `assign_to_bucket` in TypeScript (4 lines) | The Python function is already correct; the JS mirror is trivial, not a rolling-your-own risk |
| Image rotation on server | Custom rotation matrix | `Image.transpose(ROTATE_90)` | Pillow's transpose is lossless for 90-degree steps; custom matrix math introduces floating-point errors |
| Subject detection | OpenCV cascade classifier | MediaPipe Pose Landmarker | MediaPipe is 2024-maintained, handles partial body, gives body + face landmarks in one model |
| Progress streaming | WebSocket | SSE (existing pattern) | SSE is already implemented for import; unidirectional (server → client) is all that's needed |

---

## Common Pitfalls

### Pitfall 1: react-advanced-cropper "beta" — Version Lock Required

**What goes wrong:** The GitHub README states the library is in beta and recommends fixing versions with `~`. Breaking changes between minor versions have occurred.

**Why it happens:** Library is actively developed, API surface still stabilizing.

**How to avoid:** Pin to `"react-advanced-cropper": "~0.20.1"` in package.json, not `^0.20.1`.

**Warning signs:** `aspectRatio` prop type changed between some versions; if TypeScript errors appear on upgrade, check breaking changes first.

### Pitfall 2: CTRL Key State Not Captured in Cropper

**What goes wrong:** The cropper component captures pointer events. CTRL state must be tracked via document-level `keydown`/`keyup` listeners in a `useEffect`, not inside the cropper's event handlers.

**Why it happens:** React synthetic events inside a third-party component may not expose keyboard modifier state reliably.

**How to avoid:**
```typescript
useEffect(() => {
  const handleKeyDown = (e: KeyboardEvent) => { if (e.key === 'Control') setIsCtrlHeld(true) }
  const handleKeyUp = (e: KeyboardEvent) => {
    if (e.key === 'Control') {
      setIsCtrlHeld(false)
      // Trigger snap on CTRL release
      snapCurrentCropToNearestBucket()
    }
  }
  document.addEventListener('keydown', handleKeyDown)
  document.addEventListener('keyup', handleKeyUp)
  return () => {
    document.removeEventListener('keydown', handleKeyDown)
    document.removeEventListener('keyup', handleKeyUp)
  }
}, [])
```

**Warning signs:** CTRL+resize has no effect, or snapping happens during CTRL-held resize.

### Pitfall 3: Crop Coordinates Are Relative to Display Size, Not Source Image

**What goes wrong:** `cropperRef.current.getCoordinates()` returns pixel coordinates relative to the **displayed** image within the cropper container, not the original file's dimensions. Sending these to the backend crops the thumbnail, not the source.

**Why it happens:** react-advanced-cropper scales the display; coordinates are always in the original image's coordinate space. But if the developer reads from the stencil DOM position instead of the ref API, they get display coordinates.

**How to avoid:** Always use `getCoordinates()` from the cropper ref (not DOM measurements). The library documentation confirms these are image-space coordinates.

**Warning signs:** Crops look correct at small sizes but are offset/wrong-sized at original resolution.

### Pitfall 4: SeedVR2 stdout May Not Flush Line-by-Line

**What goes wrong:** Python's stdout buffers when not connected to a terminal. Progress lines may arrive in large batches rather than one-by-one.

**Why it happens:** Python's default stdio buffering.

**How to avoid:** Pass `-u` (unbuffered) flag or `PYTHONUNBUFFERED=1` env var when launching the subprocess:
```python
env = {**os.environ, "PYTHONUNBUFFERED": "1"}
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, env=env, cwd=str(SEEDVR2_ROOT))
```

**Warning signs:** Progress bar doesn't update during upscale, then jumps to 100%.

### Pitfall 5: Multiple CropCard Croppers Fighting for CTRL State

**What goes wrong:** All CropCard components share the same document-level CTRL listener. When CTRL is released, all cards snap simultaneously — this is actually desired behavior per spec. But if `isCtrlHeld` is local component state, each card manages it independently and they may drift.

**Why it happens:** Per-component state vs. shared interaction state.

**How to avoid:** Lift `isCtrlHeld` to CropPage (or a `useCropInteraction` hook), pass down as prop. All cards use the same CTRL state so behavior is consistent.

### Pitfall 6: MediaPipe Model Download at Runtime

**What goes wrong:** MediaPipe's new Tasks API downloads model files on first use (~5MB). This fails on offline systems and delays the first auto-crop call.

**Why it happens:** Default model loading is from network.

**How to avoid:** Bundle the model file with the package. In `autocrop.py`, provide the model path from a vendored location:
```python
MODEL_PATH = Path(__file__).parent / "models" / "pose_landmarker_full.task"
# Download script in setup or provide as optional dep
```

Or use the legacy `mp.solutions.pose` API which bundles the model:
```python
import mediapipe as mp
mp_pose = mp.solutions.pose.Pose(static_image_mode=True, min_detection_confidence=0.5)
```

**Warning signs:** First auto-crop takes 30+ seconds or fails with network error.

### Pitfall 7: React 19 Compatibility with react-advanced-cropper

**What goes wrong:** react-advanced-cropper 0.20.1 was published before React 19 GA. Peer dependency ranges may flag warnings.

**Why it happens:** Library peer deps declare `"react": "^18.0.0"` or similar.

**How to avoid:** The library's core (no deprecated APIs used) works with React 19. Use `--legacy-peer-deps` if npm/pnpm raises conflicts, or use `overrides` in package.json.

**Warning signs:** pnpm install fails with peer dep error.

---

## Code Examples

### Verified: RectangleStencil with Dynamic AspectRatio

```typescript
// Source: https://advanced-cropper.github.io/react-advanced-cropper/docs/components/RectangleStencil/
import { Cropper, RectangleStencil } from 'react-advanced-cropper'
import type { CropperRef, Coordinates } from 'react-advanced-cropper'
import 'react-advanced-cropper/dist/style.css'

interface CropCardProps {
  imageUrl: string
  lockedAR: number          // width/height ratio
  isFreeform: boolean       // true when CTRL held
  onCropChange: (coords: Coordinates) => void
}

export function CropCard({ imageUrl, lockedAR, isFreeform, onCropChange }: CropCardProps) {
  const cropperRef = useRef<CropperRef>(null)

  function handleChange(cropper: CropperRef) {
    const coords = cropper.getCoordinates()
    if (coords) onCropChange(coords)
  }

  return (
    <Cropper
      ref={cropperRef}
      src={imageUrl}
      stencilComponent={RectangleStencil}
      stencilProps={{
        aspectRatio: isFreeform ? undefined : lockedAR,
      }}
      onChange={handleChange}
    />
  )
}

// Zoom, rotate, flip via ref:
cropperRef.current?.zoomImage(1.2)          // zoom in 20%
cropperRef.current?.rotateImage(90)         // 90° clockwise
cropperRef.current?.flip(true, false)       // horizontal flip
```

### Verified: Pillow Crop + Resize at Bucket Dimensions

```python
# Source: https://pillow.readthedocs.io/en/stable/reference/Image.html
from PIL import Image

def apply_crop_to_bucket(
    source_path: Path,
    left: int, top: int, width: int, height: int,
    bucket_w: int, bucket_h: int,
    output_path: Path,
) -> None:
    with Image.open(source_path) as img:
        img = img.convert("RGB")          # Normalize RGBA/CMYK
        cropped = img.crop((left, top, left + width, top + height))
        resized = cropped.resize((bucket_w, bucket_h), Image.Resampling.LANCZOS)
        resized.save(output_path)
```

### Verified: Bucket Generation Mirror in TypeScript

```typescript
// Mirror of klippbok/image/bucket.py assign_to_bucket + config/model_profiles.py generate_buckets
// Source: Derived from existing Python implementation

function generateBuckets(baseResolution: number, allowNonSquare: boolean): [number, number][] {
  const pixelBudget = baseResolution * baseResolution
  const step = 64
  const min = 256
  const max = baseResolution * 2
  const buckets = new Set<string>()
  const result: [number, number][] = []

  for (let w = min; w <= max; w += step) {
    const h = Math.floor(Math.floor(pixelBudget / w) / step) * step
    const clampedH = Math.min(h, max)
    if (clampedH >= min) {
      const ratio = Math.max(w, clampedH) / Math.min(w, clampedH)
      if (ratio <= 2.0) {
        if (allowNonSquare || w === clampedH) {
          const key = `${w}x${clampedH}`
          if (!buckets.has(key)) { buckets.add(key); result.push([w, clampedH]) }
          if (w !== clampedH) {
            const key2 = `${clampedH}x${w}`
            if (!buckets.has(key2)) { buckets.add(key2); result.push([clampedH, w]) }
          }
        }
      }
    }
  }
  return result.sort((a, b) => a[0] - b[0] || a[1] - b[1])
}

function snapToNearestBucket(width: number, height: number, buckets: [number, number][]): [number, number] {
  const ar = width / height
  return buckets.reduce((best, b) => {
    return Math.abs(b[0] / b[1] - ar) < Math.abs(best[0] / best[1] - ar) ? b : best
  })
}
```

### Verified: SeedVR2 Path Detection

```python
# Source: Pattern from klippbok/video/_ffmpeg.py adapted for SeedVR2
import os
from pathlib import Path

SEEDVR2_COMMON_PATHS = [
    Path(r"C:\GenAI\Tools\SeedVR2"),
    Path.home() / "GenAI" / "Tools" / "SeedVR2",
    Path(os.environ.get("SEEDVR2_PATH", "")) if os.environ.get("SEEDVR2_PATH") else None,
]

def detect_seedvr2() -> Path | None:
    """Find SeedVR2 installation. Returns root dir or None."""
    for candidate in filter(None, SEEDVR2_COMMON_PATHS):
        python_exe = candidate / "venv" / "Scripts" / "python.exe"
        script = candidate / "batch_upscale.py"
        if python_exe.is_file() and script.is_file():
            return candidate
    return None
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Cropper.js / react-cropper | react-advanced-cropper | 2022+ | Full ref API, dynamic aspect ratio, active maintenance |
| MediaPipe legacy `mp.solutions.pose` | MediaPipe Tasks API (`PoseLandmarker`) | 2023 | Tasks API is current; legacy still works but deprecated |
| PIL `Image.ANTIALIAS` | `Image.Resampling.LANCZOS` | Pillow 9.1.0 | `ANTIALIAS` was removed in Pillow 10.0; must use `Resampling.LANCZOS` |
| `react-router-dom` | `react-router` (merged) | v7.0 (late 2024) | Already in project; just add new Route |

**Deprecated/outdated:**
- `PIL.Image.ANTIALIAS`: Removed in Pillow 10. Use `Image.Resampling.LANCZOS` (already present in project).
- MediaPipe `mp.solutions.pose`: Functional but deprecated. The Tasks API (`PoseLandmarker`) is preferred for new code; however, legacy API bundles model files which avoids the download-at-runtime pitfall.
- `react-cropper` / Cropper.js: Last npm publish 2+ years ago. Do not use.

---

## Open Questions

1. **SeedVR2 stdout progress line format**
   - What we know: `inference_cli.py` has `debug.log(f"Processing file {idx}/{len(media_files)}", category="generation", force=True)` — line 1656 of inference_cli.py. Called from `batch_upscale.py` which invokes inference_cli.py as a subprocess.
   - What's unclear: The exact text format of `debug.log` output. The `debug` object likely formats as `[category] message`. Needs a test run to capture actual stdout.
   - Recommendation: In Wave 0 or plan 1, capture actual SeedVR2 stdout with `python batch_upscale.py test_image/ --dry-run 2>&1` and grep for progress patterns. Implement flexible regex that matches on "file" + integer + "/" + integer pattern.

2. **NMKD-Siax integration approach**
   - What we know: NMKD-Siax is an ESRGAN model (4x_NMKD-Siax_200k). Can run via spandrel (Python ESRGAN library) or via realesrgan-ncnn-vulkan (external binary).
   - What's unclear: Whether spandrel is already installed in the SeedVR2 venv, or if a separate install is needed.
   - Recommendation: Check `C:\GenAI\Tools\SeedVR2\requirements.txt` for spandrel. If present, use it. Otherwise, realesrgan-ncnn-vulkan binary is the simpler fallback (download from GitHub releases, call as subprocess like ffmpeg). This is Claude's discretion per CONTEXT.md.

3. **react-advanced-cropper React 19 peer dep**
   - What we know: 0.20.1 was published before React 19 GA. Project uses React 19.2.0.
   - What's unclear: Whether pnpm will raise a peer dep error.
   - Recommendation: Plan for `--legacy-peer-deps` or `overrides.react = "^19.0.0"` in package.json. Test install in Wave 0.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.0+ |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/test_image_autocrop.py tests/test_crop_service.py tests/test_upscale_service.py -x` |
| Full suite command | `pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CROP-01 | Crop rectangle renders (smoke) | manual-only | n/a — browser interaction | n/a |
| CROP-02 | `snapToNearestBucket` returns correct bucket for given AR | unit | `pytest tests/test_crop_service.py::test_snap_to_nearest_bucket -x` | ❌ Wave 0 |
| CROP-03 | CTRL+release triggers snap (interaction test) | manual-only | n/a — browser keyboard event | n/a |
| CROP-04 | `needs_upscale()` correctly flags resolution (already tested) | unit | `pytest tests/test_image_bucket.py -x` | ✅ existing |
| CROP-05 | Zoom slider (browser interaction) | manual-only | n/a | n/a |
| CROP-06 | Rotation/flip (browser interaction) | manual-only | n/a | n/a |
| CROP-07 | `auto_crop_image()` returns valid bbox for test image with person | unit | `pytest tests/test_image_autocrop.py::test_auto_crop_detects_person -x` | ❌ Wave 0 |
| CROP-08 | `auto_crop_image()` returns center crop when no person detected | unit | `pytest tests/test_image_autocrop.py::test_auto_crop_center_fallback -x` | ❌ Wave 0 |
| CROP-09 | Auto-crop coordinates are valid within image bounds | unit | `pytest tests/test_image_autocrop.py::test_auto_crop_coords_in_bounds -x` | ❌ Wave 0 |
| GUI-05 | /crop route navigable from gallery | manual-only | n/a — browser navigation | n/a |
| CROP apply | `apply_crop()` produces file at correct dimensions | unit | `pytest tests/test_crop_service.py::test_apply_crop_dimensions -x` | ❌ Wave 0 |
| CROP apply | `apply_crop()` preserves correct pixel content after rotation | unit | `pytest tests/test_crop_service.py::test_apply_crop_rotation -x` | ❌ Wave 0 |
| Upscale | `detect_seedvr2()` finds installation at known path | unit | `pytest tests/test_upscale_service.py::test_detect_seedvr2 -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_image_autocrop.py tests/test_crop_service.py tests/test_upscale_service.py -x`
- **Per wave merge:** `pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_image_autocrop.py` — covers CROP-07, CROP-08, CROP-09
- [ ] `tests/test_crop_service.py` — covers CROP-02 snap math, apply_crop dimensions, apply_crop rotation
- [ ] `tests/test_upscale_service.py` — covers detect_seedvr2 path detection
- [ ] `tests/fixtures/person_sample.jpg` — small test image with a person (for MediaPipe detection tests; use a freely licensed stock photo or generate a synthetic one with ffmpeg)

---

## Sources

### Primary (HIGH confidence)
- react-advanced-cropper GitHub + docs (`advanced-cropper.github.io/react-advanced-cropper`) — component API, RectangleStencil props, ref methods (rotate, flip, zoom)
- Pillow official docs (`pillow.readthedocs.io/en/stable/reference/Image.html`) — crop, resize, transpose ops
- MediaPipe official docs (`ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python`) — Pose Landmarker Python API
- `C:/GenAI/Tools/SeedVR2/batch_upscale.py` — direct inspection of CLI interface and presets
- `C:/GenAI/Tools/SeedVR2/inference_cli.py` — direct inspection of progress log format
- `klippbok/image/bucket.py` — existing Python bucket assignment (mirrored to TS)
- `klippbok/config/model_profiles.py` — existing bucket generation algorithm
- `klippbok/api/routers/import_.py` — SSE pattern to reuse for upscale

### Secondary (MEDIUM confidence)
- npm search result: react-advanced-cropper latest version 0.20.1 (last published ~1 year ago)
- WebSearch: MediaPipe Pose Landmarker for full-body bounding box derivation (multiple sources confirm landmark-to-bbox approach)
- WebSearch: SeedVR2 uses tqdm + progress callbacks internally; stdout includes "Processing file N/M" format from inference_cli.py line 1656

### Tertiary (LOW confidence)
- NMKD-Siax spandrel availability in SeedVR2 venv (not verified; needs direct check of requirements.txt)
- React 19 peer dep compatibility with react-advanced-cropper 0.20.1 (not officially confirmed; low risk based on no known breaking API usage)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — react-advanced-cropper confirmed via official docs + npm; Pillow confirmed via official docs; MediaPipe confirmed via Google AI Edge docs; SeedVR2 interface confirmed via direct file inspection
- Architecture: HIGH — patterns derived from existing codebase (import_ router pattern, bucket.py logic) + verified library APIs
- Pitfalls: HIGH (CTRL key capture, crop coordinate space, subprocess buffering) / MEDIUM (React 19 peer dep, MediaPipe model download)

**Research date:** 2026-03-03
**Valid until:** 2026-04-03 (react-advanced-cropper is slow-moving; MediaPipe stable; Pillow stable)
