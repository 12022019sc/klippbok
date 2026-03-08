"""Curation router -- pipeline orchestration with SSE progress streaming.

Endpoints:
    POST /curation/start               -- Start curation pipeline (202 + op_id).
    GET  /curation/{op_id}/events      -- SSE stream for pipeline progress.
    POST /curation/{op_id}/cancel      -- Cancel an in-progress pipeline run.
    GET  /curation/results             -- Load persisted curation results.
    POST /curation/rediversify         -- Re-run diversity with pins/excludes.
    POST /curation/apply               -- Return selected image IDs for gallery.

Named SSE event types:
    "curation_progress" -- Pipeline in-progress update (stage, current, total)
    "curation_done"     -- Pipeline complete (full result JSON)
    "curation_error"    -- Pipeline failed (error message)

Follows the exact SSE pattern from cleanup.py:
- asyncio.Queue per operation_id
- None sentinel signals end of stream
- Background task runs in thread executor (CPU-bound ML)
- Thread-safe progress callback via loop.call_soon_threadsafe
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from klippbok.curation.models import CurationConfig, CurationResult
from klippbok.curation.pipeline import (
    load_results,
    rediversify,
    run_curation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/curation", tags=["curation"])

# Module-level state for active operations (process-local)
_curation_tasks: dict[str, asyncio.Task] = {}
_curation_queues: dict[str, asyncio.Queue] = {}
_curation_results: dict[str, dict] = {}  # op_id -> result dict


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class CurationStartRequest(BaseModel):
    """Request body for starting a curation pipeline run."""

    mode: str = Field(default="character", description="Curation mode: 'character' or 'style'")
    target_count: int | None = Field(default=None, description="Target image count (None = use preset)")
    quality_floor_pct: float = Field(default=0.3, ge=0.0, le=1.0, description="Bottom percentile to discard")
    reference_image_id: str | None = Field(default=None, description="Image ID for reference face")


class RediversifyRequest(BaseModel):
    """Request body for re-running diversity selection."""

    pinned_ids: list[str] = Field(default_factory=list, description="Image IDs to always include")
    excluded_ids: list[str] = Field(default_factory=list, description="Image IDs to always exclude")
    target_count: int | None = Field(default=None, description="Override target count")


# ---------------------------------------------------------------------------
# Helper: resolve image paths from manifest
# ---------------------------------------------------------------------------


def _resolve_image_paths(project_dir: Path) -> list[Path]:
    """Resolve all image paths from the project manifest.

    Args:
        project_dir: Project root directory.

    Returns:
        List of resolved Path objects for images that exist on disk.
    """
    manifest_path = project_dir / ".klippbok" / "manifest.json"
    if not manifest_path.exists():
        return []

    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    images = manifest.get("images", [])

    paths = []
    for entry in images:
        path_str = entry.get("path", "")
        full_path = project_dir / path_str
        if full_path.exists():
            paths.append(full_path)

    return paths


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


async def _run_curation_bg(
    op_id: str,
    project_dir: Path,
    config: CurationConfig,
) -> None:
    """Background coroutine that runs the curation pipeline.

    Runs the CPU/GPU-bound pipeline in a thread executor with
    thread-safe progress callbacks via asyncio.Queue.
    """
    loop = asyncio.get_running_loop()
    queue = _curation_queues[op_id]

    try:
        # Resolve image paths
        image_paths = await loop.run_in_executor(
            None,
            lambda: _resolve_image_paths(project_dir),
        )

        if not image_paths:
            await queue.put({
                "event": "curation_error",
                "data": {
                    "operation_id": op_id,
                    "message": "No images found in project manifest",
                },
            })
            return

        total = len(image_paths)

        await queue.put({
            "event": "curation_progress",
            "data": {
                "operation_id": op_id,
                "stage": "starting",
                "current": 0,
                "total": total,
                "message": f"Starting curation pipeline on {total} images...",
            },
        })

        def progress_callback(stage: str, current: int, total: int) -> None:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {
                    "event": "curation_progress",
                    "data": {
                        "operation_id": op_id,
                        "stage": stage,
                        "current": current,
                        "total": total,
                        "message": f"{stage}: {current}/{total}",
                    },
                },
            )

        result = await loop.run_in_executor(
            None,
            lambda: run_curation(image_paths, project_dir, config, progress_callback),
        )

        result_dict = result.model_dump()
        _curation_results[op_id] = result_dict

        await queue.put({
            "event": "curation_done",
            "data": {
                "operation_id": op_id,
                "current": total,
                "total": total,
                "message": f"Curation complete: {result.summary.selected} images selected from {total}.",
                "status": "complete",
                "result": result_dict,
            },
        })

    except Exception as exc:
        logger.error("Curation operation %s failed: %s", op_id, exc)
        await queue.put({
            "event": "curation_error",
            "data": {
                "operation_id": op_id,
                "message": f"Curation failed: {exc}",
            },
        })

    finally:
        await queue.put(None)


# ---------------------------------------------------------------------------
# SSE generator (mirrors cleanup.py pattern exactly)
# ---------------------------------------------------------------------------


async def _sse_generator(
    queue: asyncio.Queue,
    op_id: str,
    task_dict: dict,
    queue_dict: dict,
):
    """Consume events from queue and yield as ServerSentEvents.

    Emits "curation_done" when status is "complete". Stops on None sentinel.
    Cleans up task/queue dicts on exit.
    """
    try:
        while True:
            event = await queue.get()
            if event is None:
                break

            event_name = event["event"]
            data = event["data"]

            if data.get("status") == "complete":
                done_event = event_name.replace("_progress", "_done")
                yield ServerSentEvent(
                    event=done_event,
                    data=_json.dumps(data),
                )
                break

            yield ServerSentEvent(
                event=event_name,
                data=_json.dumps(data),
            )
    finally:
        queue_dict.pop(op_id, None)
        task = task_dict.pop(op_id, None)
        if task and not task.done():
            task.cancel()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/start", status_code=202)
async def start_curation(body: CurationStartRequest, request: Request) -> dict:
    """Start a curation pipeline run in the background.

    Returns 202 with operation_id. Connect to /curation/{op_id}/events
    for SSE progress streaming.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    # Build CurationConfig
    from klippbok.curation.presets import get_target_count_default

    target = body.target_count if body.target_count is not None else get_target_count_default(None)

    config = CurationConfig(
        mode=body.mode,  # type: ignore[arg-type]
        target_count=target,
        quality_floor_pct=body.quality_floor_pct,
        reference_image_id=body.reference_image_id,
    )

    op_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _curation_queues[op_id] = queue

    task = asyncio.create_task(
        _run_curation_bg(op_id, project_dir, config),
        name=f"curation-{op_id}",
    )
    _curation_tasks[op_id] = task

    logger.info("Started curation operation %s (mode=%s, target=%d)", op_id, body.mode, target)
    return {"operation_id": op_id}


@router.get("/{op_id}/events")
async def curation_events(op_id: str) -> EventSourceResponse:
    """Stream SSE progress events for a curation pipeline operation.

    Args:
        op_id: Operation ID from start_curation.

    Returns:
        EventSourceResponse streaming curation progress events.

    Raises:
        HTTPException 404: If op_id is not found.
    """
    if op_id not in _curation_queues:
        raise HTTPException(status_code=404, detail=f"Curation operation {op_id} not found")

    queue = _curation_queues[op_id]
    return EventSourceResponse(
        _sse_generator(queue, op_id, _curation_tasks, _curation_queues)
    )


@router.post("/{op_id}/cancel")
async def cancel_curation(op_id: str) -> dict:
    """Cancel an in-progress curation operation.

    Args:
        op_id: Operation ID to cancel.

    Returns:
        {"cancelled": True/False}.

    Raises:
        HTTPException 404: If op_id not found.
    """
    task = _curation_tasks.pop(op_id, None)
    _curation_queues.pop(op_id, None)

    if task is None:
        raise HTTPException(status_code=404, detail=f"Curation operation {op_id} not found")

    if not task.done():
        task.cancel()
        logger.info("Cancelled curation operation %s", op_id)
        return {"cancelled": True}
    return {"cancelled": False}


@router.get("/results")
async def get_curation_results(request: Request) -> dict:
    """Load persisted curation results from disk.

    Returns:
        CurationResult as dict, or 404 if no results exist.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    result = load_results(project_dir)
    if result is None:
        raise HTTPException(status_code=404, detail="No curation results found")

    return result.model_dump()


@router.post("/rediversify")
async def rediversify_curation(body: RediversifyRequest, request: Request) -> dict:
    """Re-run diversity selection with new pins/excludes.

    Reuses cached scores and embeddings from the previous pipeline run.

    Returns:
        Updated CurationResult as dict.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    try:
        result = rediversify(
            project_dir,
            pinned_ids=body.pinned_ids,
            excluded_ids=body.excluded_ids,
            target_count=body.target_count,
        )
        return result.model_dump()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/apply")
async def apply_curation(request: Request) -> dict:
    """Return selected image IDs from the last curation run.

    Frontend uses these IDs to set gallery selection state.

    Returns:
        {"selected_ids": list[str]}.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    result = load_results(project_dir)
    if result is None:
        raise HTTPException(status_code=404, detail="No curation results to apply")

    return {"selected_ids": result.selected_ids}
