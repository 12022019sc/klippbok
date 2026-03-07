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
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from klippbok.api.thumbnail import generate_video_thumbnail
from klippbok.services.image_service import batch_import_images
from klippbok.services.project_service import load_manifest, remove_image_entries
from klippbok.services.video_service import (
    extract_frames,
    ingest_video,
    scan_project_videos,
)
from klippbok.video.extract import extract_reference_image
from klippbok.video.extract_models import ExtractionConfig, ExtractionStrategy
from klippbok.video.probe import probe_video
from klippbok.video.scene import detect_scenes
from klippbok.video.split import split_video_at_scenes
from klippbok.config.data_schema import VideoConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video", tags=["video"])

# Module-level state for active operations (process-local, reset on restart)
_ingest_queues: dict[str, asyncio.Queue] = {}
_ingest_tasks: dict[str, asyncio.Task] = {}
_extract_queues: dict[str, asyncio.Queue] = {}
_extract_tasks: dict[str, asyncio.Task] = {}
_process_queues: dict[str, asyncio.Queue] = {}
_process_tasks: dict[str, asyncio.Task] = {}
_process_results: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    """Parameters for a video ingest operation."""
    video_path: str | None = None
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
    message: str = ""
    status: str = "running"


class ProcessRequest(BaseModel):
    """Parameters for a video process operation."""
    video_paths: list[str] | None = None
    """Relative paths of specific videos to process. None = all videos."""
    frames_per_clip: int = 1
    """Number of reference frames to extract per clip."""
    scene_threshold: float = 27.0
    """Scene detection threshold for long videos."""
    long_video_threshold: float = 30.0
    """Duration threshold in seconds -- videos >= this get scene detection."""


class ProcessStarted(BaseModel):
    """Response for a started process operation."""
    operation_id: str


class ProcessProgressEvent(BaseModel):
    """SSE data payload for process progress events."""
    operation_id: str
    stage: str  # "Probing videos", "Scene detection", "Splitting clips", "Extracting frames", "Complete"
    current: int
    total: int
    message: str = ""
    status: str = "running"
    extracted_frames: list[dict] | None = None
    processed_video_paths: list[str] | None = None
    skipped_videos: list[dict] | None = None  # [{path, reason}]


class ProcessConfirmRequest(BaseModel):
    """Request body for confirming video processing (import frames + remove videos)."""
    video_paths: list[str]
    frame_paths: list[str] | None = None
    """If provided, only import these specific frames. None = import all from refs/."""


class ProcessDiscardRequest(BaseModel):
    """Request body for discarding extracted frames."""
    frame_paths: list[str]
    remove_videos: bool = False
    """If true, also remove video entries from manifest."""
    video_paths: list[str] | None = None
    """Video paths to remove (required if remove_videos=True)."""


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

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


async def _run_ingest(
    request: IngestRequest,
    queue: asyncio.Queue,
    op_id: str,
    project_dir: Path,
) -> None:
    """Background coroutine that runs the video ingest pipeline.

    Runs ingest_video in a thread executor so the async event loop stays
    responsive. Progress events are pushed onto the queue.

    Supports two modes:
    - video_path: Ingest a single video file.
    - directory_path: Glob a directory for video files and ingest each.

    Args:
        request: Ingest parameters.
        queue: asyncio.Queue to push progress events onto.
        op_id: Operation UUID for event payloads.
        project_dir: Project root directory from app state.
    """
    from klippbok.config.data_schema import VideoConfig

    # Capture the running loop before entering executor threads
    loop = asyncio.get_running_loop()

    try:
        # Build VideoConfig from request params
        config = VideoConfig(
            fps=request.fps,
            resolution=request.resolution,
            frame_count="auto",
            max_frames=request.max_frames,
        )

        # Resolve video file(s) to ingest
        if request.video_path:
            video_files = [Path(request.video_path)]
        elif request.directory_path:
            dir_path = Path(request.directory_path)
            if not dir_path.is_dir():
                raise FileNotFoundError(f"Directory not found: {dir_path}")
            video_files = sorted(
                p for p in dir_path.iterdir()
                if p.is_file() and p.suffix.lower() in _VIDEO_EXTENSIONS
            )
            if not video_files:
                raise FileNotFoundError(f"No video files found in: {dir_path}")
        else:
            raise ValueError("Either video_path or directory_path is required")

        total_files = len(video_files)
        all_clips = []

        for file_idx, video_path in enumerate(video_files):
            # Emit per-file progress
            await queue.put(IngestProgressEvent(
                operation_id=op_id,
                stage=f"Ingesting file {file_idx + 1}/{total_files}",
                current=file_idx,
                total=total_files,
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
                asyncio.run_coroutine_threadsafe(queue.put(event), loop)

            # Run ingest in thread (CPU-bound + subprocess calls)
            clips = await loop.run_in_executor(
                None,
                lambda vp=video_path: ingest_video(
                    video_path=vp,
                    output_dir=project_dir,
                    config=config,
                    threshold=request.threshold,
                    progress_callback=progress_callback,
                ),
            )
            all_clips.extend(clips)

        # Emit completion event
        await queue.put(IngestProgressEvent(
            operation_id=op_id,
            stage="Complete",
            current=len(all_clips),
            total=len(all_clips),
            message=f"Ingest complete: {len(all_clips)} clips from {total_files} file(s)",
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
    loop = asyncio.get_running_loop()

    try:
        clips_dir = project_dir
        output_dir = project_dir / "refs"

        await queue.put(ExtractProgressEvent(
            operation_id=op_id,
            stage="Starting extraction",
            current=0,
            total=1,
            message="Scanning clips directory...",
            status="running",
        ))

        extracted = await loop.run_in_executor(
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
            message=f"Extraction complete: {len(extracted)} reference frames",
            status="complete",
        ))

    except Exception as exc:
        logger.error("Extract operation %s failed: %s", op_id, exc)
        await queue.put(ExtractProgressEvent(
            operation_id=op_id,
            stage="Error",
            current=0,
            total=0,
            message=f"Extraction failed: {exc}",
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
    if not body.video_path and not body.directory_path:
        raise HTTPException(status_code=422, detail="Either video_path or directory_path is required")

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
        report = await asyncio.get_running_loop().run_in_executor(
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
# Process: background runner (extract frames → import → remove videos)
# ---------------------------------------------------------------------------

_VIDEO_MEDIA_TYPE = "video"


async def _run_process(
    request: ProcessRequest,
    queue: asyncio.Queue,
    op_id: str,
    project_dir: Path,
) -> None:
    """Background coroutine: multi-stage video process pipeline.

    Pipeline stages:
    1. Probing videos -- get duration to decide routing
    2. Scene detection -- for long videos (>= long_video_threshold)
    3. Splitting clips -- split long videos at scene boundaries
    4. Extracting frames -- extract reference image per clip/video
    5. Complete -- report results

    Short videos (<threshold) skip stages 2-3 and extract directly.
    Failed videos are auto-skipped with error details preserved.
    """
    loop = asyncio.get_running_loop()

    try:
        # Step 1: Collect video entries from manifest
        manifest = load_manifest(project_dir)
        if not manifest or "images" not in manifest:
            await queue.put(ProcessProgressEvent(
                operation_id=op_id,
                stage="Complete",
                current=0,
                total=0,
                message="No images in manifest -- nothing to process.",
                status="complete",
                extracted_frames=[],
                processed_video_paths=[],
            ))
            _process_results[op_id] = {"extracted_frames": [], "processed_video_paths": []}
            return

        all_images: list[dict] = manifest["images"]
        video_entries = [
            e for e in all_images
            if e.get("type") == _VIDEO_MEDIA_TYPE
        ]

        # Filter to specific paths if requested
        if request.video_paths is not None:
            filter_set = set(request.video_paths)
            video_entries = [e for e in video_entries if e.get("path") in filter_set]

        if not video_entries:
            await queue.put(ProcessProgressEvent(
                operation_id=op_id,
                stage="Complete",
                current=0,
                total=0,
                message="No video entries found to process.",
                status="complete",
                extracted_frames=[],
                processed_video_paths=[],
            ))
            _process_results[op_id] = {"extracted_frames": [], "processed_video_paths": []}
            return

        total = len(video_entries)
        refs_dir = project_dir / "refs"
        refs_dir.mkdir(parents=True, exist_ok=True)

        # Temp processing dir for clean cancel support
        temp_dir = refs_dir / f".processing-{op_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        extracted_frames: list[dict] = []
        processed_video_paths: list[str] = []
        skipped_videos: list[dict] = []

        # Store temp_dir early so cancel can clean up
        _process_results[op_id] = {"temp_dir": str(temp_dir)}

        threshold = request.long_video_threshold

        for idx, entry in enumerate(video_entries):
            rel_path = entry.get("path", "")
            abs_path = project_dir / rel_path

            try:
                # Stage 1: Probing videos
                await queue.put(ProcessProgressEvent(
                    operation_id=op_id,
                    stage="Probing videos",
                    current=idx,
                    total=total,
                    message=f"Probing: {Path(rel_path).name}",
                    status="running",
                ))

                metadata = await loop.run_in_executor(
                    None,
                    lambda p=abs_path: probe_video(p),
                )
                duration = metadata.duration

                # Determine extraction targets (clips to extract frames from)
                extraction_targets: list[tuple[Path, str]] = []  # (abs_path, stem)

                if duration >= threshold:
                    # Long video: scene detect + split
                    await queue.put(ProcessProgressEvent(
                        operation_id=op_id,
                        stage="Scene detection",
                        current=idx,
                        total=total,
                        message=f"Detecting scenes: {Path(rel_path).name}",
                        status="running",
                    ))

                    scenes = await loop.run_in_executor(
                        None,
                        lambda p=abs_path, t=request.scene_threshold: detect_scenes(p, threshold=t),
                    )

                    if scenes:
                        await queue.put(ProcessProgressEvent(
                            operation_id=op_id,
                            stage="Splitting clips",
                            current=idx,
                            total=total,
                            message=f"Splitting: {Path(rel_path).name} ({len(scenes)} scenes)",
                            status="running",
                        ))

                        config = VideoConfig()
                        clips = await loop.run_in_executor(
                            None,
                            lambda p=abs_path, s=scenes, d=temp_dir, c=config: split_video_at_scenes(p, s, d, c),
                        )

                        for clip in clips:
                            clip_stem = Path(clip.output).stem
                            extraction_targets.append((Path(clip.output), clip_stem))
                    else:
                        # No scenes found in long video -- treat as single clip
                        stem = Path(rel_path).stem
                        extraction_targets.append((abs_path, stem))
                else:
                    # Short video: extract directly
                    stem = Path(rel_path).stem
                    extraction_targets.append((abs_path, stem))

                # Stage 4: Extract frames
                await queue.put(ProcessProgressEvent(
                    operation_id=op_id,
                    stage="Extracting frames",
                    current=idx,
                    total=total,
                    message=f"Extracting frames: {Path(rel_path).name}",
                    status="running",
                ))

                # Use best_frame strategy with top-5 candidates for user review
                extraction_config = ExtractionConfig(
                    strategy=ExtractionStrategy.BEST_FRAME,
                    sample_count=10,
                    overwrite=True,
                    keep_top_n=7,
                )

                for source_path, stem in extraction_targets:
                    output_path = temp_dir / f"{stem}.png"
                    try:
                        result = await loop.run_in_executor(
                            None,
                            lambda sp=source_path, op=output_path, cfg=extraction_config: extract_reference_image(sp, op, cfg),
                        )
                        if result.success or result.skipped:
                            # Move winner frame from temp to refs/
                            final_path = refs_dir / f"{stem}.png"
                            if output_path.exists():
                                shutil.move(str(output_path), str(final_path))

                            # Move candidates dir from temp to refs/
                            frame_candidates: list[dict] | None = None
                            temp_cand_dir = temp_dir / f"{stem}_candidates"
                            if temp_cand_dir.exists():
                                final_cand_dir = refs_dir / f"{stem}_candidates"
                                if final_cand_dir.exists():
                                    shutil.rmtree(str(final_cand_dir))
                                shutil.move(str(temp_cand_dir), str(final_cand_dir))
                                # Rebuild candidate paths relative to project
                                frame_candidates = []
                                for cand_file in sorted(final_cand_dir.glob("rank_*.png")):
                                    rel = f"refs/{stem}_candidates/{cand_file.name}"
                                    # Parse score from filename: rank_1_score_0.841.png
                                    parts = cand_file.stem.split("_")
                                    rank = int(parts[1]) if len(parts) >= 2 else 0
                                    score = float(parts[3]) if len(parts) >= 4 else 0.0
                                    frame_candidates.append({
                                        "path": rel,
                                        "score": score,
                                        "rank": rank,
                                    })

                            frame_rel = f"refs/{stem}.png"
                            frame_entry: dict = {
                                "video_path": rel_path,
                                "frame_path": frame_rel,
                            }
                            if frame_candidates:
                                frame_entry["candidates"] = frame_candidates
                            extracted_frames.append(frame_entry)
                        else:
                            logger.warning(
                                "Frame extraction failed for %s: %s", stem, result.error
                            )
                    except Exception as exc:
                        logger.error("Frame extraction error for %s: %s", stem, exc)

                processed_video_paths.append(rel_path)

            except Exception as exc:
                logger.error("Processing failed for %s: %s", rel_path, exc)
                skipped_videos.append({
                    "path": rel_path,
                    "reason": str(exc),
                })
                continue

        # Clean up temp dir (clips and any remaining temp frames)
        if temp_dir.exists():
            shutil.rmtree(str(temp_dir), ignore_errors=True)

        # Store results for retrieval via GET endpoint
        _process_results[op_id] = {
            "extracted_frames": extracted_frames,
            "processed_video_paths": processed_video_paths,
            "skipped_videos": skipped_videos,
        }

        await queue.put(ProcessProgressEvent(
            operation_id=op_id,
            stage="Complete",
            current=total,
            total=total,
            message=(
                f"Extraction complete: {len(extracted_frames)} frames extracted "
                f"from {len(processed_video_paths)} videos."
                + (f" {len(skipped_videos)} skipped." if skipped_videos else "")
            ),
            status="complete",
            extracted_frames=extracted_frames,
            processed_video_paths=processed_video_paths,
            skipped_videos=skipped_videos if skipped_videos else None,
        ))

    except Exception as exc:
        logger.error("Process operation %s failed: %s", op_id, exc)
        await queue.put(ProcessProgressEvent(
            operation_id=op_id,
            stage="Error",
            current=0,
            total=0,
            message=f"Processing failed: {exc}",
            status="error",
        ))

    finally:
        await queue.put(None)


def _cleanup_candidate_dirs(refs_dir: Path) -> None:
    """Remove all *_candidates/ directories under refs/."""
    if not refs_dir.exists():
        return
    for d in refs_dir.iterdir():
        if d.is_dir() and d.name.endswith("_candidates"):
            shutil.rmtree(str(d), ignore_errors=True)


# ---------------------------------------------------------------------------
# Process endpoints
# ---------------------------------------------------------------------------

@router.post("/process/start", response_model=ProcessStarted, status_code=200)
async def start_process(body: ProcessRequest, request: Request) -> ProcessStarted:
    """Start a video processing operation (extract + import + remove)."""
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    op_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _process_queues[op_id] = queue

    task = asyncio.create_task(
        _run_process(body, queue, op_id, project_dir),
        name=f"process-{op_id}",
    )
    _process_tasks[op_id] = task

    logger.info("Started process operation %s", op_id)
    return ProcessStarted(operation_id=op_id)


@router.get("/process/{op_id}/events")
async def process_events(op_id: str) -> EventSourceResponse:
    """Stream SSE progress events for a video process operation."""
    if op_id not in _process_queues:
        raise HTTPException(
            status_code=404,
            detail=f"Process operation '{op_id}' not found.",
        )

    queue = _process_queues[op_id]

    async def event_generator():
        try:
            while True:
                event = await queue.get()

                if event is None:
                    break

                progress: ProcessProgressEvent = event
                data = progress.model_dump_json()

                if progress.status == "complete":
                    yield ServerSentEvent(data=data, event="process_done")
                    break
                elif progress.status == "error":
                    yield ServerSentEvent(data=data, event="process_error")
                    break
                else:
                    yield ServerSentEvent(data=data, event="process_progress")

        finally:
            _process_queues.pop(op_id, None)
            task = _process_tasks.pop(op_id, None)
            if task and not task.done():
                task.cancel()
                logger.debug("Cancelled process task for operation %s", op_id)

    return EventSourceResponse(event_generator())


@router.post("/process/{op_id}/cancel")
async def cancel_process(op_id: str, request: Request) -> dict:
    """Cancel a running process operation and clean up temp files."""
    task = _process_tasks.pop(op_id, None)
    _process_queues.pop(op_id, None)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Process operation '{op_id}' not found.",
        )

    if not task.done():
        task.cancel()
        logger.info("Cancelled process operation %s", op_id)

    # Clean up temp processing directory and candidate dirs
    results = _process_results.get(op_id)
    if results:
        if "temp_dir" in results:
            temp_dir = Path(results["temp_dir"])
            if temp_dir.exists():
                shutil.rmtree(str(temp_dir), ignore_errors=True)
                logger.info("Cleaned up temp dir for operation %s: %s", op_id, temp_dir)
        # Clean up any candidate dirs that were already moved to refs/
        project_dir = request.app.state.project_dir
        if project_dir:
            _cleanup_candidate_dirs(Path(project_dir) / "refs")
    _process_results.pop(op_id, None)

    return {"cancelled": True}


@router.post("/process/confirm")
async def confirm_process(body: ProcessConfirmRequest, request: Request) -> dict:
    """Confirm video processing: import extracted frames and remove video entries.

    If body.frame_paths is provided, only those specific frames are imported
    (copied to a temp dir, then batch_import_images runs on that dir).
    If frame_paths is None, imports all frames from refs/.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    refs_dir = project_dir / "refs"
    if not refs_dir.exists():
        raise HTTPException(status_code=404, detail="No refs/ directory found")

    loop = asyncio.get_running_loop()

    if body.frame_paths is not None:
        # Selective import: copy only specified frames to a temp dir
        import tempfile
        temp_import_dir = Path(tempfile.mkdtemp(prefix="klippbok-confirm-"))
        try:
            for fp in body.frame_paths:
                src = project_dir / fp
                if src.exists():
                    shutil.copy2(str(src), str(temp_import_dir / src.name))

            report = await loop.run_in_executor(
                None,
                lambda d=temp_import_dir: batch_import_images(d, project_dir),
            )
        finally:
            shutil.rmtree(str(temp_import_dir), ignore_errors=True)
    else:
        report = await loop.run_in_executor(
            None,
            lambda: batch_import_images(refs_dir, project_dir),
        )

    removed = 0
    if body.video_paths:
        removed = await loop.run_in_executor(
            None,
            lambda: remove_image_entries(project_dir, set(body.video_paths)),
        )

    # Clean up candidate dirs after import
    _cleanup_candidate_dirs(project_dir / "refs")

    return {"imported": report.imported, "removed": removed}


@router.post("/process/discard")
async def discard_process(body: ProcessDiscardRequest, request: Request) -> dict:
    """Discard extracted frames by deleting specific files from refs/.

    If remove_videos=True and video_paths provided, also removes video
    entries from the manifest.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    deleted = 0
    for frame_path in body.frame_paths:
        abs_path = project_dir / frame_path
        if abs_path.exists() and abs_path.is_file():
            abs_path.unlink()
            deleted += 1

    # Also delete candidate dirs for discarded frames
    refs_dir = project_dir / "refs"
    for frame_path in body.frame_paths:
        stem = Path(frame_path).stem
        cand_dir = refs_dir / f"{stem}_candidates"
        if cand_dir.exists() and cand_dir.is_dir():
            shutil.rmtree(str(cand_dir), ignore_errors=True)

    videos_removed = 0
    if body.remove_videos and body.video_paths:
        loop = asyncio.get_running_loop()
        videos_removed = await loop.run_in_executor(
            None,
            lambda: remove_image_entries(project_dir, set(body.video_paths)),
        )

    return {"deleted": deleted, "videos_removed": videos_removed}


@router.get("/process/results/{op_id}")
async def get_process_results(op_id: str) -> dict:
    """Retrieve stored extraction results for a completed process operation."""
    results = _process_results.get(op_id)
    if results is None:
        raise HTTPException(
            status_code=404,
            detail=f"Process results for '{op_id}' not found.",
        )
    return results


@router.get("/process/frame")
async def serve_process_frame(path: str, request: Request) -> FileResponse:
    """Serve an extracted frame file for review thumbnails."""
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    abs_path = project_dir / path
    if not abs_path.exists() or not abs_path.is_file():
        raise HTTPException(status_code=404, detail=f"Frame not found: {path}")

    return FileResponse(str(abs_path), media_type="image/png")


# ---------------------------------------------------------------------------
# Clips endpoint
# ---------------------------------------------------------------------------

def _clip_id_from_relative(relative_path: str) -> str:
    """Generate clip ID from relative path: SHA256[:16] of relative path string."""
    return hashlib.sha256(relative_path.encode()).hexdigest()[:16]


# Module-level cache: clip_id -> absolute Path, populated by list_clips/scan
_clip_path_cache: dict[str, Path] = {}


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
        report = await asyncio.get_running_loop().run_in_executor(
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
            thumb_path = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda p=meta.path: generate_video_thumbnail(p, cache_dir),
            )
            thumbnail_url = f"/api/v1/video/clips/{clip_id}/thumbnail"
        except Exception as exc:
            logger.warning("Failed to generate thumbnail for %s: %s", meta.path.name, exc)
            thumbnail_url = ""

        # Populate clip path cache for thumbnail lookups
        _clip_path_cache[clip_id] = meta.path

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

    # Look up clip path from cache (populated by list_clips)
    clip_path = _clip_path_cache.get(clip_id)

    if clip_path is None:
        # Cache miss — do a full scan to populate
        try:
            report = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: scan_project_videos(project_dir),
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Scan failed: {exc}")

        for clip_validation in report.clips:
            meta = clip_validation.metadata
            try:
                relative_path = str(meta.path.relative_to(project_dir))
            except ValueError:
                relative_path = meta.path.name
            cid = _clip_id_from_relative(relative_path)
            _clip_path_cache[cid] = meta.path
            if cid == clip_id:
                clip_path = meta.path

    if clip_path is None:
        raise HTTPException(status_code=404, detail=f"Clip '{clip_id}' not found")

    # Generate/return thumbnail
    try:
        thumb_path = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: generate_video_thumbnail(clip_path, cache_dir),
        )
    except Exception as exc:
        logger.error("Thumbnail generation failed for clip %s: %s", clip_id, exc)
        raise HTTPException(status_code=500, detail=f"Thumbnail generation failed: {exc}")

    return FileResponse(str(thumb_path), media_type="image/jpeg")
