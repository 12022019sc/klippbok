# Phase 4: Web GUI Foundation - Research

**Researched:** 2026-02-28
**Domain:** FastAPI + React SPA (Vite + TypeScript), SSE streaming, masonry gallery, server-side thumbnails
**Confidence:** HIGH (core stack), MEDIUM (React library versions)

## Summary

Phase 4 builds a FastAPI backend serving a React SPA on a single port, with an image gallery featuring masonry layout, virtual scrolling, per-image status overlays, and SSE-powered live updates during batch import. The standard pattern is well-established: FastAPI serves the React build via StaticFiles with `html=True` for SPA routing fallback. The React frontend is scaffolded with Vite + TypeScript + React Router v7. Zustand manages global UI state; TanStack Query handles data fetching; `masonic` provides virtualized masonry; `yet-another-react-lightbox` handles click-to-expand; `sonner` handles toast notifications.

Server-side thumbnail generation is mandatory (ARCH-06) because browser canvas has pixel-count limits (~16.7MP) and large datasets render full-resolution images without it. Pillow's `thumbnail()` method + a disk cache under `.klippbok/thumbnails/` is the correct approach. The thumbnail endpoint returns a JPEG response directly from the cache file.

For SSE (live gallery updates during import), the standard pattern is: background task writes progress to an `asyncio.Queue`; an SSE endpoint consumes the queue via `StreamingResponse` with `media_type="text/event-stream"`. The `sse-starlette` library (v3.2.0) wraps this cleanly and handles client disconnect detection.

**Primary recommendation:** Vite+React+TypeScript (front) + FastAPI 0.134+ + uvicorn (back) + `masonic` for gallery + `sse-starlette` for live updates + Pillow disk-cache thumbnails.

---

## Standard Stack

### Python Backend
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | >=0.100 (latest 0.134) | REST API + SPA hosting + SSE | Already in ecosystem; StaticFiles + StreamingResponse handles all three needs |
| uvicorn[standard] | >=0.20 | ASGI server for `klippbok serve` | FastAPI's official recommended server; `standard` extras include watchfiles for dev |
| sse-starlette | >=3.2.0 | SSE endpoint abstraction | Handles W3C-compliant SSE, client disconnect, multi-loop; eliminates boilerplate |
| Pillow | >=9.0 (already in `image` dep group) | Thumbnail generation | Already a dependency; `thumbnail()` preserves aspect ratio correctly |
| python-multipart | >=0.0.5 | Required by FastAPI for form data | Needed if any file upload routes added |

### JavaScript Frontend
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| react | ^19.x | UI framework | Current major; Vite template targets this |
| react-dom | ^19.x | DOM rendering | Paired with react |
| typescript | ^5.x | Type safety | Project standard; catches API contract mismatches early |
| vite | ^6.x | Build tool + dev server | Industry standard; instant HMR; `npm create vite@latest -- --template react-ts` |
| react-router | ^7.x | Client-side routing | v7 consolidates react-router-dom; import from `react-router` only |
| zustand | ^5.x | Global UI state (toasts, selected image, import status) | Minimal boilerplate; no providers needed; excellent for small-medium apps |
| @tanstack/react-query | ^5.x | API data fetching + cache invalidation | Standard for async server state; integrates with SSE via queryClient.invalidateQueries |
| masonic | ^4.1.0 | Virtualized masonry grid | Only masonry library with built-in virtualization; renders tens of thousands of cells |
| yet-another-react-lightbox | ^3.29.1 | Lightbox overlay for click-to-expand | Actively maintained; render prop API for custom metadata panel; React 19 compatible |
| sonner | ^1.x | Toast notifications | Adopted by shadcn/ui; <5KB; persistent toast API matches spec requirement |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| axios or fetch | built-in fetch | API calls | Use `fetch` directly or wrap in query functions; no axios needed |
| @types/react | ^19.x | TypeScript types for React | Always include with React + TypeScript |
| eslint + prettier | latest | Code quality | Standard Vite scaffold includes these |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| masonic | react-masonry-css | react-masonry-css has NO virtualization; will lag at 1000+ images |
| masonic | MUI Masonry | MUI adds entire component library as dep; overkill |
| yet-another-react-lightbox | react-image-lightbox | react-image-lightbox not maintained; last release 2021 |
| sonner | react-hot-toast | Both are fine; sonner has better persistent toast API |
| sse-starlette | raw StreamingResponse | sse-starlette handles disconnect detection and proper cleanup automatically |
| asyncio.Queue | FastAPI BackgroundTasks | BackgroundTasks cannot share asyncio queue with SSE endpoint; need asyncio.Queue directly |

**Python dependencies installation:**
```bash
pip install "fastapi[standard]>=0.100" "sse-starlette>=3.2.0" uvicorn
```

**Frontend scaffold:**
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install react-router @tanstack/react-query zustand masonic yet-another-react-lightbox sonner
```

---

## Architecture Patterns

### Recommended Project Structure

```
klippbok/
├── api/                    # New: FastAPI application
│   ├── __init__.py
│   ├── app.py              # FastAPI app factory, mounts SPA, registers routers
│   ├── routers/
│   │   ├── images.py       # GET /api/v1/images, GET /api/v1/images/{id}/thumbnail
│   │   ├── import_.py      # POST /api/v1/import, GET /api/v1/import/events (SSE)
│   │   └── settings.py     # GET/PUT /api/v1/settings
│   └── models.py           # Pydantic response schemas (ImageResponse, ImportEvent)
├── __main_serve__.py       # Entry point for `klippbok serve`
└── [existing modules...]

frontend/                   # Vite React SPA (built to frontend/dist/)
├── src/
│   ├── components/
│   │   ├── Gallery/
│   │   │   ├── MasonryGrid.tsx     # masonic wrapper
│   │   │   ├── ThumbnailCard.tsx   # single card with status overlay
│   │   │   └── StatusStrip.tsx     # bottom overlay bar
│   │   ├── Lightbox/
│   │   │   └── ImageLightbox.tsx   # yet-another-react-lightbox + metadata panel
│   │   └── Layout/
│   │       ├── NavBar.tsx
│   │       └── ToastProvider.tsx
│   ├── hooks/
│   │   ├── useImages.ts            # TanStack Query: GET /api/v1/images
│   │   └── useImportEvents.ts      # EventSource hook feeding Zustand
│   ├── stores/
│   │   └── appStore.ts             # Zustand: importStatus, selectedImage, toasts
│   ├── pages/
│   │   ├── GalleryPage.tsx
│   │   ├── ImportPage.tsx
│   │   └── SettingsPage.tsx
│   └── App.tsx                     # React Router routes
├── dist/                           # Built output copied to klippbok/api/static/
└── vite.config.ts
```

### Pattern 1: FastAPI Serves React SPA (Single Port)

**What:** FastAPI's `StaticFiles(html=True)` serves the React build. API routes are prefixed `/api/v1/`. The `html=True` flag makes any unmatched path return `index.html`, enabling React Router's client-side routing.

**Critical:** API routes MUST be registered before mounting StaticFiles, or StaticFiles will intercept API calls.

```python
# Source: https://fastapi.tiangolo.com/tutorial/static-files/
# Pattern: API-first, then SPA catch-all

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from klippbok.api.routers import images, import_, settings

app = FastAPI(title="klippbok")

# 1. Register API routers FIRST
app.include_router(images.router, prefix="/api/v1")
app.include_router(import_.router, prefix="/api/v1")
app.include_router(settings.router, prefix="/api/v1")

# 2. Mount SPA LAST — catches everything not matched above
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="spa")
```

### Pattern 2: SSE Live Updates via asyncio.Queue

**What:** A batch import operation runs as an `asyncio.Task`. It writes progress events to a per-request `asyncio.Queue`. An SSE endpoint reads from the queue and yields formatted events. Client uses native `EventSource`.

**Why asyncio.Queue, not BackgroundTasks:** FastAPI's `BackgroundTasks` runs after the response is sent and cannot share state with a streaming response. An `asyncio.Task` runs concurrently with the SSE stream and can push to a shared queue.

```python
# Source: https://github.com/sysid/sse-starlette + asyncio patterns
import asyncio
from sse_starlette.sse import EventSourceResponse
from fastapi import APIRouter

router = APIRouter()

# Module-level queue registry keyed by operation ID
_queues: dict[str, asyncio.Queue] = {}

@router.post("/import")
async def start_import(request: ImportRequest) -> ImportStarted:
    op_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _queues[op_id] = queue

    # Fire-and-forget: task runs concurrently
    asyncio.create_task(_run_import(request, queue, op_id))

    return ImportStarted(operation_id=op_id)

@router.get("/import/{op_id}/events")
async def import_events(op_id: str):
    queue = _queues.get(op_id)
    if not queue:
        raise HTTPException(404)

    async def event_generator():
        while True:
            event = await queue.get()
            if event is None:  # sentinel: done
                yield {"event": "done", "data": "{}"}
                break
            yield {"event": "progress", "data": event.model_dump_json()}

    return EventSourceResponse(event_generator())
```

### Pattern 3: Virtualized Masonry Gallery

**What:** `masonic`'s `<Masonry>` component renders only visible cells. Each cell receives an `index` and `data` prop. Heights are variable (masonry respects actual aspect ratios). Cell widths are uniform (masonic controls column width); height is derived from aspect ratio.

```typescript
// Source: https://github.com/jaredLunde/masonic
import { Masonry } from "masonic";
import { ThumbnailCard } from "./ThumbnailCard";

interface GalleryItem {
  id: string;
  thumbnailUrl: string;
  width: number;
  height: number;
  resolution: string;
  qualityPass: boolean;
  bucket: string;
  isDuplicate: boolean;
  duplicateGroupId?: string;
}

function MasonryGrid({ items }: { items: GalleryItem[] }) {
  const renderCard = ({ index, data, width }: { index: number; data: GalleryItem; width: number }) => {
    const height = Math.round(width * (data.height / data.width));
    return <ThumbnailCard item={data} width={width} height={height} />;
  };

  return (
    <Masonry
      items={items}
      render={renderCard}
      columnGutter={8}
      columnWidth={220}
      overscanBy={2}
    />
  );
}
```

### Pattern 4: Thumbnail Endpoint with Disk Cache

**What:** FastAPI endpoint generates a 300px-wide JPEG thumbnail using Pillow on first request, caches to `.klippbok/thumbnails/{hash}.jpg`, returns from cache on subsequent requests.

**Why not stream full images:** Browser displays full-resolution images only in lightbox; gallery uses cached thumbnails. Eliminates re-encoding on every request.

```python
# Source: Pillow docs (https://pillow.readthedocs.io/en/stable/reference/Image.html)
import hashlib
from pathlib import Path
from PIL import Image
from fastapi import APIRouter
from fastapi.responses import FileResponse

THUMB_SIZE = (300, 300)  # max dimensions; aspect ratio preserved by thumbnail()

def get_thumbnail(image_path: Path, cache_dir: Path) -> Path:
    """Return path to thumbnail, generating if needed."""
    cache_key = hashlib.sha256(str(image_path).encode()).hexdigest()[:16]
    thumb_path = cache_dir / f"{cache_key}.jpg"

    if not thumb_path.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(image_path) as img:
            img = img.convert("RGB")  # strip alpha for JPEG
            img.thumbnail(THUMB_SIZE, Image.LANCZOS)
            img.save(thumb_path, "JPEG", quality=85, optimize=True)

    return thumb_path

@router.get("/images/{image_id}/thumbnail")
async def serve_thumbnail(image_id: str):
    # resolve image_id to path from manifest
    ...
    thumb = get_thumbnail(image_path, THUMB_CACHE_DIR)
    return FileResponse(thumb, media_type="image/jpeg")
```

### Pattern 5: Lightbox with Metadata Panel

**What:** `yet-another-react-lightbox` via `render.slideFooter` for metadata overlay.

```typescript
// Source: https://yet-another-react-lightbox.com/documentation
import Lightbox from "yet-another-react-lightbox";

<Lightbox
  open={isOpen}
  close={() => setOpen(false)}
  slides={slides}
  render={{
    slideFooter: ({ slide }) => (
      <div className="metadata-panel">
        <span>{(slide as GalleryItem).resolution}</span>
        <span>{(slide as GalleryItem).bucket}</span>
        <span>{(slide as GalleryItem).caption}</span>
      </div>
    ),
  }}
/>
```

### Anti-Patterns to Avoid

- **Mounting StaticFiles before API routes:** StaticFiles with `html=True` will swallow all unmatched paths including `/api/v1/...`. Always register routers first.
- **Using FastAPI BackgroundTasks for SSE progress:** BackgroundTasks run after the response is fully sent; they cannot communicate with an ongoing SSE stream. Use `asyncio.create_task()` + `asyncio.Queue`.
- **Serving full-resolution images in the gallery grid:** With 1000+ images this is a browser memory and bandwidth disaster. Always serve thumbnails in the grid; full images only in lightbox.
- **Not virtualizing the masonry grid:** CSS-only masonry libraries (react-masonry-css) render all DOM nodes. At 500+ images this causes severe performance degradation. Use `masonic` which only renders visible items.
- **Using `img.thumbnail()` on RGBA images saved as JPEG:** JPEG does not support alpha. Always `img.convert("RGB")` before saving as JPEG.
- **Caching thumbnails in-memory only:** Application restart loses all thumbnails. Cache to disk under `.klippbok/thumbnails/`.
- **React Router v6 patterns in v7:** In v7, import from `react-router` not `react-router-dom`; the packages were merged.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Masonry with virtualization | Custom CSS columns or grid | `masonic` | Virtualizing variable-height items requires interval-tree layout math; masonic already has this |
| SSE endpoint lifecycle | Raw `StreamingResponse` generator | `sse-starlette` | Client disconnect detection, proper cleanup, and asyncio loop management are error-prone |
| Lightbox with keyboard/touch nav | Custom modal with image | `yet-another-react-lightbox` | Keyboard nav, preloading, pinch-zoom, focus trapping are non-trivial |
| Toast notification system | Custom state + DOM portal | `sonner` | Z-index management, animation, queue management, accessibility (aria-live) |
| SPA routing fallback | Custom catch-all route | `StaticFiles(html=True)` | Built into Starlette; handles edge cases around asset vs page requests |
| Thumbnail aspect-ratio resize | Custom PIL resize logic | `img.thumbnail(size, LANCZOS)` | `thumbnail()` correctly constrains both dimensions while preserving ratio; `resize()` does not |

**Key insight:** Every "hand-rolled" item here has subtle correctness requirements. The masonry height calculation alone requires an interval tree for O(log n) position lookups. Use the library.

---

## Common Pitfalls

### Pitfall 1: StaticFiles Swallows API Routes

**What goes wrong:** If `StaticFiles` is mounted before API routers, all `/api/v1/...` requests return 404 or `index.html` because StaticFiles handles them first.
**Why it happens:** FastAPI route matching is first-match; a root mount catches everything.
**How to avoid:** Always `app.include_router(...)` ALL API routers before `app.mount("/", StaticFiles(...))`.
**Warning signs:** API calls in browser return HTML instead of JSON; 404 on all API routes.

### Pitfall 2: BackgroundTasks Cannot Feed SSE Stream

**What goes wrong:** Developer uses `background_tasks.add_task(run_import, queue)` expecting it to push to an active SSE connection. The SSE stream never receives events.
**Why it happens:** BackgroundTasks run AFTER the response is fully sent. An SSE response streams indefinitely — BackgroundTasks never fire while SSE is active.
**How to avoid:** Use `asyncio.create_task(run_import(queue))` inside the route handler. The task runs concurrently with the SSE response.
**Warning signs:** SSE stream opens but never receives any events; import completes silently.

### Pitfall 3: Thumbnail JPEG Save with Alpha Channel

**What goes wrong:** `PIL.UnidentifiedImageError` or garbled thumbnail when saving a PNG with alpha as JPEG.
**Why it happens:** JPEG format does not support alpha channel. Pillow raises an error or produces incorrect output.
**How to avoid:** Always `img = img.convert("RGB")` before `img.save(..., "JPEG")`.
**Warning signs:** Error on first PNG thumbnail request; WebP images with transparency also affected.

### Pitfall 4: masonic `columnWidth` vs Actual Cell Height

**What goes wrong:** All thumbnails render as squares because the cell render function uses a fixed height instead of calculating from aspect ratio.
**Why it happens:** masonic passes `width` (the cell width) to the render function; height is the developer's responsibility.
**How to avoid:** In the render function: `const height = Math.round(width * (item.height / item.width))`. Return a div with explicit height.
**Warning signs:** Gallery looks like a uniform grid instead of masonry; portrait images appear cropped.

### Pitfall 5: SSE Connection Multiplying on React StrictMode

**What goes wrong:** In development with React StrictMode, `useEffect` runs twice, creating two EventSource connections per component mount. Server sees duplicate connections; events may arrive doubled.
**Why it happens:** React StrictMode intentionally double-invokes effects in development to catch side effects.
**How to avoid:** In the EventSource hook, return a cleanup function that calls `eventSource.close()`. React will close the first connection before opening the second.
**Warning signs:** Duplicate toast notifications during import; server logs show two SSE connections per client.

### Pitfall 6: Vite Dev Server CORS Blocking API Calls

**What goes wrong:** During development, the React dev server runs on :5173 and the FastAPI server on :8000. All API calls fail with CORS errors.
**Why it happens:** Browser same-origin policy blocks cross-origin requests without CORS headers.
**How to avoid:** Configure Vite's `proxy` in `vite.config.ts` to forward `/api/v1` to `http://localhost:8000`. Do NOT add CORS middleware to FastAPI for production (SPA is served from same origin).

```typescript
// vite.config.ts
export default defineConfig({
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
```
**Warning signs:** Network tab shows CORS error on `/api/v1/images`; works in production but not dev.

### Pitfall 7: Thumbnail Cache Path Collisions

**What goes wrong:** Two images with the same filename in different directories get the same thumbnail cache key.
**Why it happens:** If cache key is based on filename only (not full path), collisions occur.
**How to avoid:** Hash the FULL absolute path: `hashlib.sha256(str(abs_path).encode()).hexdigest()[:16]`.
**Warning signs:** Wrong thumbnail shown for images with same filename in different folders.

---

## Code Examples

### FastAPI App Factory with SPA Mount

```python
# Source: https://fastapi.tiangolo.com/tutorial/static-files/
# klippbok/api/app.py

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

def create_app() -> FastAPI:
    app = FastAPI(title="klippbok API", version="0.1.0")

    from klippbok.api.routers import images, import_, settings
    app.include_router(images.router, prefix="/api/v1", tags=["images"])
    app.include_router(import_.router, prefix="/api/v1", tags=["import"])
    app.include_router(settings.router, prefix="/api/v1", tags=["settings"])

    # SPA static files MUST be mounted AFTER all API routers
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="spa")

    return app
```

### `klippbok serve` Entry Point

```python
# Source: uvicorn documentation
# klippbok/__main_serve__.py

import uvicorn
from klippbok.api.app import create_app

def main():
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)

if __name__ == "__main__":
    main()
```

### Image List API Response Model

```python
# klippbok/api/models.py

from pydantic import BaseModel

class ImageStatusResponse(BaseModel):
    id: str                  # stable ID (e.g. sha256 of relative path)
    relative_path: str       # for display
    thumbnail_url: str       # /api/v1/images/{id}/thumbnail
    width: int
    height: int
    resolution_ok: bool      # True = downscale only (green), False = upscale needed (red)
    quality_pass: bool       # blur detection pass/fail
    bucket: str | None       # e.g. "3:4", "1:1"
    is_near_duplicate: bool
    duplicate_group_id: str | None  # shared among duplicates in same cluster
    caption: str | None      # None in gallery; populated in lightbox from manifest

class GalleryResponse(BaseModel):
    total: int
    images: list[ImageStatusResponse]
```

### EventSource Hook (React)

```typescript
// Source: MDN EventSource API + React hooks pattern
// frontend/src/hooks/useImportEvents.ts

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAppStore } from "../stores/appStore";

export function useImportEvents(operationId: string | null) {
  const queryClient = useQueryClient();
  const addToast = useAppStore((s) => s.addToast);
  const setImportProgress = useAppStore((s) => s.setImportProgress);

  useEffect(() => {
    if (!operationId) return;

    const es = new EventSource(`/api/v1/import/${operationId}/events`);

    es.addEventListener("progress", (e) => {
      const data = JSON.parse(e.data);
      setImportProgress(data);
      // Invalidate gallery query so new images appear
      queryClient.invalidateQueries({ queryKey: ["images"] });
    });

    es.addEventListener("done", () => {
      es.close();
      addToast({ message: "Import complete", type: "success" });
    });

    es.onerror = () => {
      es.close();
      addToast({ message: "Import stream disconnected", type: "error" });
    };

    return () => es.close(); // cleanup for StrictMode
  }, [operationId]);
}
```

### Duplicate Group Color Assignment

```typescript
// frontend/src/utils/duplicateColors.ts
// Assign a stable color to each duplicate group for border rendering

const DUPLICATE_COLORS = [
  "#ef4444", "#f97316", "#eab308", "#22c55e",
  "#06b6d4", "#8b5cf6", "#ec4899",
];

const groupColorCache = new Map<string, string>();
let colorIndex = 0;

export function getDuplicateGroupColor(groupId: string): string {
  if (!groupColorCache.has(groupId)) {
    groupColorCache.set(groupId, DUPLICATE_COLORS[colorIndex % DUPLICATE_COLORS.length]);
    colorIndex++;
  }
  return groupColorCache.get(groupId)!;
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| react-router-dom (separate package) | react-router (merged) | v7, late 2024 | Import from `react-router`; `react-router-dom` still works as alias |
| Redux for global state | Zustand for small apps | 2022-2023 | Less boilerplate; no provider wrapping; better DX |
| Polling for live updates | SSE (EventSource) | Established; common 2024+ | Lower overhead than WebSocket for one-way server push |
| WebSocket for progress | SSE | N/A | SSE is simpler; auto-reconnect built in; works over HTTP/1.1 |
| CSS-only masonry | masonic (virtualized) | Needed at 500+ images | Required for large datasets; CSS masonry has no virtualization |
| Create React App | Vite | 2022-2023 | CRA deprecated; Vite is the standard scaffold |

**Deprecated/outdated:**
- `react-router-dom`: Still works as alias in v7 but install `react-router` going forward
- `create-react-app` (`react-scripts`): Officially deprecated; use `npm create vite@latest`
- `react-image-lightbox`: Last published 2021; unmaintained; use `yet-another-react-lightbox`
- `react-virtualized`: Largely superseded by `react-window` and `masonic` for specific use cases

---

## Open Questions

1. **Build output location for SPA**
   - What we know: FastAPI needs to serve the built frontend; the natural location is `klippbok/api/static/`
   - What's unclear: Should the build step be manual (developer runs `npm run build` then copies) or automated (pyproject.toml script calls npm)? Or does the `klippbok serve` command detect a missing build and print instructions?
   - Recommendation: For Phase 4, require manual build and document it. Add `frontend/dist/` copy to `klippbok/api/static/` as a dev workflow step. Full automation is Phase 8 scope.

2. **Image ID stability across manifest updates**
   - What we know: The API needs a stable `id` to serve thumbnails at `/api/v1/images/{id}/thumbnail`
   - What's unclear: Should the ID be the SHA256 of the relative path, or a UUID generated at import time?
   - Recommendation: Use SHA256 of the relative path (deterministic, no state needed). This means IDs are stable across restarts without storing them in the manifest.

3. **SSE connection cleanup on server shutdown**
   - What we know: `sse-starlette` handles client disconnect; asyncio.Queue cleanup is not automatic
   - What's unclear: If the server is shut down mid-import, orphaned tasks and queues may linger
   - Recommendation: Track active tasks in a module-level dict; register a FastAPI `lifespan` handler that cancels all tasks on shutdown.

4. **Project directory selection**
   - What we know: Phase 4 spec says "single project at a time — switch by loading a different folder"
   - What's unclear: How does `klippbok serve` know which project directory to open? CLI arg? Current directory? Settings page selection?
   - Recommendation: Accept optional `--project-dir` CLI argument; default to current working directory. This matches how most ML tools work.

---

## Sources

### Primary (HIGH confidence)
- FastAPI official docs (https://fastapi.tiangolo.com/tutorial/static-files/) — StaticFiles, SPA routing, html=True pattern
- FastAPI official docs (https://fastapi.tiangolo.com/tutorial/background-tasks/) — BackgroundTasks limitations, asyncio task recommendation
- Pillow official docs (https://pillow.readthedocs.io/en/stable/reference/Image.html) — thumbnail() method, LANCZOS filter
- yet-another-react-lightbox docs (https://yet-another-react-lightbox.com/documentation) — render prop API for slideFooter
- sse-starlette GitHub (https://github.com/sysid/sse-starlette) — EventSourceResponse, v3.2.0

### Secondary (MEDIUM confidence)
- WebSearch: masonic v4.1.0 on npm — confirmed latest version, virtualization support, hook APIs
- WebSearch: yet-another-react-lightbox v3.29.1 — confirmed latest version, active maintenance (published 12 days ago)
- WebSearch: FastAPI v0.134 current — confirmed from PyPI release notes
- WebSearch: sse-starlette v3.2.0 — confirmed from PyPI
- WebSearch: React Router v7 — v6→v7 non-breaking, import from `react-router`
- WebSearch: sonner vs react-hot-toast 2025 comparison — sonner recommended for modern apps

### Tertiary (LOW confidence)
- WebSearch: duplicate group colored borders technique — no specific prior art found; implementation is custom CSS (straightforward)
- WebSearch: asyncio.Queue + SSE pattern — confirmed as community standard but not in official FastAPI docs

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all library versions verified via npm/PyPI searches and official docs
- Architecture: HIGH — FastAPI StaticFiles + SSE patterns verified against official docs
- Pitfalls: MEDIUM — most verified against official docs; SSE/StrictMode pitfall is community knowledge verified by multiple sources
- React library versions: MEDIUM — confirmed via npm search results (not Context7 fetch)

**Research date:** 2026-02-28
**Valid until:** 2026-03-28 (stable ecosystem; React/FastAPI major versions move slowly)
