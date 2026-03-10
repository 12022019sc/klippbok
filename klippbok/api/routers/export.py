"""Export router — API endpoints for LoRA trainer export operations.

Endpoints:
    GET  /export/defaults            -- Return default export config from project manifest.
    GET  /export/validate            -- Return pre-flight validation issues.
    POST /export/start               -- Start background export operation.
    GET  /export/{op_id}/events      -- SSE stream for export progress.
    POST /export/{op_id}/cancel      -- Cancel an in-progress export.

Named SSE event types:
    "export_progress" -- Export in-progress update
    "export_done"     -- Export complete
    "export_error"    -- Export failed

Follows the SSE pattern from cleanup.py exactly:
- asyncio.Queue per operation_id
- None sentinel signals end of stream
- Background task runs in thread executor (CPU-bound file I/O)
- Thread-safe progress callback via loop.call_soon_threadsafe
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from klippbok.services.export_service import (
    ExportConfig,
    get_export_candidates,
    get_export_defaults,
    perform_export,
    validate_export_candidates,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export", tags=["export"])

# Module-level state for active operations (process-local)
_export_tasks: dict[str, asyncio.Task] = {}
_export_queues: dict[str, asyncio.Queue] = {}


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class ExportStartRequest(BaseModel):
    """Request body for starting an export operation."""

    trainer: Literal["kohya", "aitoolkit", "onetrainer"] = "kohya"
    repeats: int = 5
    trigger_word: str = "sks"
    class_name: str = "person"
    concept_name: str = ""
    output_path: str


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


async def _run_export_bg(
    op_id: str,
    project_dir: Path,
    config: ExportConfig,
) -> None:
    """Background coroutine that runs the export pipeline.

    Dispatches to perform_export() in a thread executor (file I/O).
    Puts SSE events on the queue for the SSE generator to consume.
    """
    loop = asyncio.get_running_loop()
    queue = _export_queues[op_id]

    try:
        # Initial progress event
        await queue.put({
            "event": "export_progress",
            "data": {
                "operation_id": op_id,
                "current": 0,
                "total": 0,
                "message": f"Starting {config.trainer} export...",
            },
        })

        def progress_callback(current: int, total: int) -> None:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {
                    "event": "export_progress",
                    "data": {
                        "operation_id": op_id,
                        "current": current,
                        "total": total,
                        "message": f"Exporting file {current} of {total}",
                    },
                },
            )

        result = await loop.run_in_executor(
            None,
            lambda: perform_export(project_dir, config, progress_callback),
        )

        await queue.put({
            "event": "export_done",
            "data": {
                "operation_id": op_id,
                "current": result.image_count,
                "total": result.image_count,
                "message": f"Export complete: {result.image_count} images exported.",
                "status": "complete",
                "image_count": result.image_count,
                "config_path": str(result.config_path),
                "output_dir": str(result.output_dir),
            },
        })

    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        logger.error("Export operation %s failed: %s\n%s", op_id, exc, tb)
        await queue.put({
            "event": "export_error",
            "data": {
                "operation_id": op_id,
                "message": f"Export failed: {exc}",
                "traceback": tb,
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

    Emits "export_done" when status is "complete". Stops on None sentinel.
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
                yield ServerSentEvent(
                    event=event_name,
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


@router.get("/defaults")
async def export_defaults(request: Request) -> dict:
    """Return default export configuration from project manifest.

    Args:
        request: FastAPI request (for project_dir).

    Returns:
        Dict with resolution, default_repeats, trigger_word, class_name, concept_name.

    Raises:
        HTTPException 409: If no project directory selected.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    return get_export_defaults(project_dir)


@router.get("/validate")
async def export_validate(request: Request) -> dict:
    """Return pre-flight validation issues for export candidates.

    Returns candidate count (source='crop' images) and list of validation issues
    (missing/empty captions).

    Args:
        request: FastAPI request (for project_dir).

    Returns:
        Dict: {"candidates": int, "issues": [{"path": str, "issue": str}]}.

    Raises:
        HTTPException 409: If no project directory selected.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    candidates = get_export_candidates(project_dir)
    issues = validate_export_candidates(candidates)

    return {
        "candidates": len(candidates),
        "issues": issues,
    }


@router.post("/start")
async def start_export(body: ExportStartRequest, request: Request) -> dict:
    """Start a background export operation.

    Creates op_id, asyncio.Queue, and background task. The task calls
    perform_export() in a thread executor and pushes SSE events to the queue.

    Args:
        body: ExportStartRequest with trainer, repeats, trigger_word, etc.
        request: FastAPI request (for project_dir).

    Returns:
        {"op_id": str}

    Raises:
        HTTPException 409: If no project directory selected.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    config = ExportConfig(
        trainer=body.trainer,
        repeats=body.repeats,
        trigger_word=body.trigger_word,
        class_name=body.class_name,
        concept_name=body.concept_name,
        output_dir=Path(body.output_path),
    )

    op_id = uuid.uuid4().hex[:8]
    queue: asyncio.Queue = asyncio.Queue()
    _export_queues[op_id] = queue

    task = asyncio.create_task(
        _run_export_bg(op_id, project_dir, config),
        name=f"export-{op_id}",
    )
    _export_tasks[op_id] = task

    logger.info("Started export operation %s (trainer=%s)", op_id, body.trainer)
    return {"op_id": op_id}


@router.get("/{op_id}/events")
async def export_events(op_id: str) -> EventSourceResponse:
    """Stream SSE progress events for an export operation.

    Args:
        op_id: Operation ID from start_export.

    Returns:
        EventSourceResponse streaming export progress events.

    Raises:
        HTTPException 404: If op_id is not found.
    """
    if op_id not in _export_queues:
        raise HTTPException(status_code=404, detail=f"Export operation {op_id} not found")

    queue = _export_queues[op_id]
    return EventSourceResponse(
        _sse_generator(queue, op_id, _export_tasks, _export_queues)
    )


@router.post("/{op_id}/cancel")
async def cancel_export(op_id: str) -> dict:
    """Cancel an in-progress export operation.

    Args:
        op_id: Operation ID to cancel.

    Returns:
        {"cancelled": True/False}

    Raises:
        HTTPException 404: If op_id not found.
    """
    task = _export_tasks.pop(op_id, None)
    _export_queues.pop(op_id, None)

    if task is None:
        raise HTTPException(status_code=404, detail=f"Export operation {op_id} not found")

    if not task.done():
        task.cancel()
        logger.info("Cancelled export operation %s", op_id)
        return {"cancelled": True}
    return {"cancelled": False}
