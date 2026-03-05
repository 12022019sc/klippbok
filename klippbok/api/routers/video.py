"""Video router -- ingest, scan, extract, and clip management endpoints.

Follows the SSE pattern established in import_.py:
    POST /video/ingest/start        -- Start ingest, return operation_id
    GET  /video/ingest/{op_id}/events  -- Stream SSE progress events
    POST /video/ingest/{op_id}/cancel  -- Cancel ingest task

    GET  /video/scan                -- Synchronous: scan clips directory
    POST /video/extract/start       -- Start extraction, return operation_id
    GET  /video/extract/{op_id}/events -- SSE progress events
    POST /video/extract/{op_id}/cancel  -- Cancel extraction task

    GET  /video/clips               -- List video clips with metadata + thumbnail URLs
    GET  /video/clips/{clip_id}/thumbnail -- Serve cached video thumbnail JPEG

Named SSE event types:
    "ingest_progress"  -- In-progress ingest stage update
    "ingest_done"      -- Ingest completed successfully
    "ingest_error"     -- Ingest failed (avoids EventSource 'error' collision)
    "extract_progress" -- In-progress extraction stage update
    "extract_done"     -- Extraction completed
    "extract_error"    -- Extraction failed
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from klippbok.api.thumbnail import generate_video_thumbnail
from klippbok.services.video_service import (
    extract_frames,
    ingest_video,
    scan_project_videos,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video", tags=["video"])

# Module-level state for active operations (process-local, reset on restart)
_ingest_queues: dict[str, asyncio.Queue] = {}
_ingest_tasks: dict[str, asyncio.Task] = {}
_extract_queues: dict[str, asyncio.Queue] = {}
_extract_tasks: dict[str, asyncio.Task] = {}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    """Parameters for a video ingest operation."""
    video_path: str
    """Path to the video file (or directory) to ingest."""
    directory_path: str | None = None
    """Alternative: scan a directory of videos (mutually exclusive with video_path)."""
    fps: int = 16
    """Target frame rate (Wan training default: 16)."""
    resolution: int = 720
    """Target resolution in pixels (height)."""
    threshold: float = 27.0
    """Scene detection threshold."""
    max_frames: int | None = None
    """Maximum frames per output clip. None = unlimited."""


class IngestStarted(BaseModel):
    """Response for a started ingest operation."""
    operation_id: str


class ExtractRequest(BaseModel):
    """Parameters for a frame extraction operation."""
    frames_per_clip: int = 1
    """Number of reference frames to extract per clip."""


class ExtractStarted(BaseModel):
    """Response for a started extraction operation."""
    operation_id: str


class IngestProgressEvent(BaseModel):
    """SSE data payload for ingest progress events."""
    operation_id: str
    stage: str
    current: int
    total: int
    message: str
    status: str = "running"


class ExtractProgressEvent(BaseModel):
    """SSE data payload for extract progress events."""
    operation_id: str
    stage: str
    current: int
    total: int
    status: str = "running"


class VideoClipItem(BaseModel):
    """A video clip item returned by GET /video/clips."""
    id: str
    """SHA256[:16] of relative_path."""
    relative_path: str
    """Path relative to project_dir."""
    thumbnail_url: str
    """URL path for the clip thumbnail."""
    duration: float
    fps: float
    width: int
    height: int
    frame_count: int


class ScanResultItem(BaseModel):
    """One clip's metadata from GET /video/scan."""
    filename: str
    width: int
    height: int
    fps: float
    duration: float
    codec: str
    frame_count: int
    issues: list[str]


# ---------------------------------------------------------------------------
# Ingest: background runner
# ---------------------------------------------------------------------------

async def _run_ingest(
    request: IngestRequest,
    queue: asyncio.Queue,
    op_id: str,
    project_dir: Path,
) -> None:
    """Background coroutine that runs the video ingest pipeline.

    Runs ingest_video in a thread executor so the async event loop stays
    responsive. Progress events are pushed onto the queue.

    Args:
        request: Ingest parameters.
        queue: asyncio.Queue to push progress events onto.
        op_id: Operation UUID for event payloads.
        project_dir: Project root directory from app state.
    """
    from klippbok.config.data_schema import VideoConfig

    try:
        video_path = Path(request.video_path)

        # Build VideoConfig from request params
        config = VideoConfig(
            fps=request.fps,
            resolution=request.resolution,
            frame_count="auto",
            max_frames=request.max_frames,
        )

        # Emit initial progress
        await queue.put(IngestProgressEvent(
            operation_id=op_id,
            stage="Starting ingest",
            current=0,
            total=1,
            message=f"Ingesting: {video_path.name}",
            status="running",
        ))

        def progress_callback(stage: str, current: int, total: int) -> None:
            """Bridge sync progress callback to async queue."""
            event = IngestProgressEvent(
                operation_id=op_id,
                stage=stage,
                current=current,
                total=total,
                message=stage,
                status="running",
            )
            # Schedule the put coroutine on the running event loop
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(queue.put(event), loop)

        # Run ingest in thread (CPU-bound + subprocess calls)
        clips = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: ingest_video(
                video_path=video_path,
                output_dir=project_dir,
                config=config,
                threshold=request.threshold,
                progress_callback=progress_callback,
            ),
        )

        # Emit completion event
        await queue.put(IngestProgressEvent(
            operation_id=op_id,
            stage="Complete",
            current=len(clips),
            total=len(clips),
            message=f"Ingest complete: {len(clips)} clips produced",
            status="complete",
        ))

    except Exception as exc:
        logger.error("Ingest operation %s failed: %s", op_id, exc)
        await queue.put(IngestProgressEvent(
            operation_id=op_id,
            stage="Error",
            current=0,
            total=0,
            message=f"Ingest failed: {exc}",
            status="error",
        ))

    finally:
        # None sentinel signals SSE generator to stop reading
        await queue.put(None)


# ---------------------------------------------------------------------------
# Extract: background runner
# ---------------------------------------------------------------------------

async def _run_extract(
    request: ExtractRequest,
    queue: asyncio.Queue,
    op_id: str,
    project_dir: Path,
) -> None:
    """Background coroutine that runs the frame extraction pipeline."""
    try:
        clips_dir = project_dir / "clips"
        output_dir = project_dir / "refs"

        await queue.put(ExtractProgressEvent(
            operation_id=op_id,
            stage="Starting extraction",
            current=0,
            total=1,
            status="running",
        ))

        extracted = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: extract_frames(
                clips_dir=clips_dir,
                output_dir=output_dir,
                frames_per_clip=request.frames_per_clip,
            ),
        )

        await queue.put(ExtractProgressEvent(
            operation_id=op_id,
            stage="Complete",
            current=len(extracted),
            total=len(extracted),
            status="complete",
        ))

    except Exception as exc:
        logger.error("Extract operation %s failed: %s", op_id, exc)
        await queue.put(ExtractProgressEvent(
            operation_id=op_id,
            stage="Error",
            current=0,
            total=0,
            status="error",
        ))

    finally:
        await queue.put(None)


# ---------------------------------------------------------------------------
# Ingest endpoints
# ---------------------------------------------------------------------------

@router.post("/ingest/start", response_model=IngestStarted, status_code=200)
async def start_ingest(body: IngestRequest, request: Request) -> IngestStarted:
    """Start a video ingest operation in the background.

    Returns an operation_id the client uses to subscribe to SSE progress.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    op_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _ingest_queues[op_id] = queue

    task = asyncio.create_task(
        _run_ingest(body, queue, op_id, project_dir),
        name=f"ingest-{op_id}",
    )
    _ingest_tasks[op_id] = task

    logger.info("Started ingest operation %s for: %s", op_id, body.video_path)
    return IngestStarted(operation_id=op_id)


@router.get("/ingest/{op_id}/events")
async def ingest_events(op_id: str) -> EventSourceResponse:
    """Stream SSE progress events for a video ingest operation."""
    if op_id not in _ingest_queues:
        raise HTTPException(
            status_code=404,
            detail=f"Ingest operation '{op_id}' not found.",
        )

    queue = _ingest_queues[op_id]

    async def event_generator():
        try:
            while True:
                event = await queue.get()

                if event is None:
                    break

                progress: IngestProgressEvent = event
                data = progress.model_dump_json()

                if progress.status == "complete":
                    yield ServerSentEvent(data=data, event="ingest_done")
                    break
                elif progress.status == "error":
                    yield ServerSentEvent(data=data, event="ingest_error")
                    break
                else:
                    yield ServerSentEvent(data=data, event="ingest_progress")

        finally:
            _ingest_queues.pop(op_id, None)
            task = _ingest_tasks.pop(op_id, None)
            if task and not task.done():
                task.cancel()
                logger.debug("Cancelled ingest task for operation %s", op_id)

    return EventSourceResponse(event_generator())


@router.post("/ingest/{op_id}/cancel")
async def cancel_ingest(op_id: str) -> dict:
    """Cancel a running ingest operation."""
    task = _ingest_tasks.pop(op_id, None)
    _ingest_queues.pop(op_id, None)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ingest operation '{op_id}' not found.",
        )

    if not task.done():
        task.cancel()
        logger.info("Cancelled ingest operation %s", op_id)

    return {"cancelled": True}


# ---------------------------------------------------------------------------
# Scan endpoint
# ---------------------------------------------------------------------------

@router.get("/scan")
async def scan_clips(request: Request) -> list[ScanResultItem]:
    """Scan the project directory for video clips and return metadata.

    Synchronous scan — probes all video files and validates them.
    Returns a list of clip metadata dicts.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    try:
        report = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: scan_project_videos(project_dir),
        )
    except Exception as exc:
        logger.error("Scan failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Scan failed: {exc}")

    results: list[ScanResultItem] = []
    for clip_validation in report.clips:
        meta = clip_validation.metadata
        issues = [issue.message for issue in clip_validation.issues]
        results.append(ScanResultItem(
            filename=meta.path.name,
            width=meta.width,
            height=meta.height,
            fps=meta.fps,
            duration=meta.duration,
            codec=meta.codec,
            frame_count=meta.frame_count,
            issues=issues,
        ))

    return results


# ---------------------------------------------------------------------------
# Extract endpoints
# ---------------------------------------------------------------------------

@router.post("/extract/start", response_model=ExtractStarted, status_code=200)
async def start_extract(body: ExtractRequest, request: Request) -> ExtractStarted:
    """Start a reference frame extraction operation in the background."""
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    op_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _extract_queues[op_id] = queue

    task = asyncio.create_task(
        _run_extract(body, queue, op_id, project_dir),
        name=f"extract-{op_id}",
    )
    _extract_tasks[op_id] = task

    logger.info("Started extraction operation %s", op_id)
    return ExtractStarted(operation_id=op_id)


@router.get("/extract/{op_id}/events")
async def extract_events(op_id: str) -> EventSourceResponse:
    """Stream SSE progress events for a frame extraction operation."""
    if op_id not in _extract_queues:
        raise HTTPException(
            status_code=404,
            detail=f"Extract operation '{op_id}' not found.",
        )

    queue = _extract_queues[op_id]

    async def event_generator():
        try:
            while True:
                event = await queue.get()

                if event is None:
                    break

                progress: ExtractProgressEvent = event
                data = progress.model_dump_json()

                if progress.status == "complete":
                    yield ServerSentEvent(data=data, event="extract_done")
                    break
                elif progress.status == "error":
                    yield ServerSentEvent(data=data, event="extract_error")
                    break
                else:
                    yield ServerSentEvent(data=data, event="extract_progress")

        finally:
            _extract_queues.pop(op_id, None)
            task = _extract_tasks.pop(op_id, None)
            if task and not task.done():
                task.cancel()
                logger.debug("Cancelled extract task for operation %s", op_id)

    return EventSourceResponse(event_generator())


@router.post("/extract/{op_id}/cancel")
async def cancel_extract(op_id: str) -> dict:
    """Cancel a running extraction operation."""
    task = _extract_tasks.pop(op_id, None)
    _extract_queues.pop(op_id, None)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Extract operation '{op_id}' not found.",
        )

    if not task.done():
        task.cancel()
        logger.info("Cancelled extract operation %s", op_id)

    return {"cancelled": True}


# ---------------------------------------------------------------------------
# Clips endpoint
# ---------------------------------------------------------------------------

def _clip_id_from_relative(relative_path: str) -> str:
    """Generate clip ID from relative path: SHA256[:16] of relative path string."""
    return hashlib.sha256(relative_path.encode()).hexdigest()[:16]


@router.get("/clips", response_model=list[VideoClipItem])
async def list_clips(request: Request) -> list[VideoClipItem]:
    """List video clips in the project with metadata and thumbnail URLs.

    Scans the project directory, probes each clip, generates/caches thumbnails,
    and returns a structured list of clip items.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    try:
        report = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: scan_project_videos(project_dir),
        )
    except Exception as exc:
        logger.error("List clips failed during scan: %s", exc)
        raise HTTPException(status_code=500, detail=f"Scan failed: {exc}")

    cache_dir = project_dir / ".klippbok" / "thumbnails"
    items: list[VideoClipItem] = []

    for clip_validation in report.clips:
        meta = clip_validation.metadata
        try:
            relative_path = str(meta.path.relative_to(project_dir))
        except ValueError:
            relative_path = meta.path.name

        clip_id = _clip_id_from_relative(relative_path)

        # Generate/cache thumbnail (non-blocking wrapper)
        try:
            thumb_path = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda p=meta.path: generate_video_thumbnail(p, cache_dir),
            )
            thumbnail_url = f"/api/v1/video/clips/{clip_id}/thumbnail"
        except Exception as exc:
            logger.warning("Failed to generate thumbnail for %s: %s", meta.path.name, exc)
            thumbnail_url = ""

        items.append(VideoClipItem(
            id=clip_id,
            relative_path=relative_path,
            thumbnail_url=thumbnail_url,
            duration=meta.duration,
            fps=meta.fps,
            width=meta.width,
            height=meta.height,
            frame_count=meta.frame_count,
        ))

    return items


@router.get("/clips/{clip_id}/thumbnail")
async def get_clip_thumbnail(clip_id: str, request: Request) -> FileResponse:
    """Serve the cached JPEG thumbnail for a video clip.

    Looks up the clip by ID (SHA256[:16] of relative path), then serves
    the cached thumbnail file.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    cache_dir = project_dir / ".klippbok" / "thumbnails"

    # Resolve clip from project scan
    try:
        report = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: scan_project_videos(project_dir),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scan failed: {exc}")

    # Find the clip with matching ID
    target_meta = None
    for clip_validation in report.clips:
        meta = clip_validation.metadata
        try:
            relative_path = str(meta.path.relative_to(project_dir))
        except ValueError:
            relative_path = meta.path.name
        if _clip_id_from_relative(relative_path) == clip_id:
            target_meta = meta
            break

    if target_meta is None:
        raise HTTPException(status_code=404, detail=f"Clip '{clip_id}' not found")

    # Generate/return thumbnail
    try:
        thumb_path = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: generate_video_thumbnail(target_meta.path, cache_dir),
        )
    except Exception as exc:
        logger.error("Thumbnail generation failed for clip %s: %s", clip_id, exc)
        raise HTTPException(status_code=500, detail=f"Thumbnail generation failed: {exc}")

    return FileResponse(str(thumb_path), media_type="image/jpeg")
