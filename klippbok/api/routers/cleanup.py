"""Cleanup router -- ML-powered media classification and removal.

Endpoints:
    POST /cleanup/start                  -- Start background cleanup scan.
    GET  /cleanup/{op_id}/events         -- SSE stream for cleanup progress.
    POST /cleanup/{op_id}/cancel         -- Cancel an in-progress scan.
    POST /cleanup/confirm                -- Move flagged files to _review/.
    GET  /cleanup/results/{op_id}        -- Get classification results.

Named SSE event types:
    "cleanup_progress" -- Scan in-progress update
    "cleanup_done"     -- Scan complete
    "cleanup_error"    -- Scan failed

Follows the exact SSE pattern from triage.py:
- asyncio.Queue per operation_id
- None sentinel signals end of stream
- Background task runs in thread executor (CPU-bound)
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

from klippbok.services.cleanup_service import (
    classify_items,
    classify_items_by_reference,
    confirm_removal,
    generate_prompts_from_description,
    DEFAULT_REFERENCE_THRESHOLD,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cleanup", tags=["cleanup"])

# Module-level state for active operations (process-local)
_cleanup_tasks: dict[str, asyncio.Task] = {}
_cleanup_queues: dict[str, asyncio.Queue] = {}
_cleanup_results: dict[str, list[dict]] = {}  # op_id -> classification results


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class CleanupStartRequest(BaseModel):
    """Request body for starting a cleanup scan."""
    mode: Literal["text", "reference"] = "text"
    subject_description: str | None = None
    reference_image_ids: list[str] | None = None
    clip_threshold: float | None = None  # None = use mode default


class ConfirmRemovalRequest(BaseModel):
    """Request body for confirming file removal."""
    item_paths: list[str]


# ---------------------------------------------------------------------------
# Helper: resolve item paths from manifest
# ---------------------------------------------------------------------------


def _resolve_item_paths(project_dir: Path) -> list[Path]:
    """Resolve all image/video paths from the project manifest.

    Args:
        project_dir: Project root directory.

    Returns:
        List of resolved Path objects.
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


def _resolve_image_ids_to_paths(
    project_dir: Path, image_ids: list[str],
) -> list[Path]:
    """Resolve gallery image IDs to file paths via the manifest.

    Args:
        project_dir: Project root directory.
        image_ids: List of SHA256[:16] image IDs.

    Returns:
        List of resolved Path objects.

    Raises:
        HTTPException 400: If any image ID cannot be resolved.
    """
    import hashlib

    manifest_path = project_dir / ".klippbok" / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=400, detail="No manifest found")

    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    images = manifest.get("images", [])

    # Build id -> path lookup
    id_to_path: dict[str, Path] = {}
    for entry in images:
        rel = entry.get("path", "")
        img_id = hashlib.sha256(rel.encode()).hexdigest()[:16]
        id_to_path[img_id] = project_dir / rel

    paths = []
    for img_id in image_ids:
        if img_id not in id_to_path:
            raise HTTPException(
                status_code=400,
                detail=f"Image ID {img_id} not found in manifest",
            )
        path = id_to_path[img_id]
        if not path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Image file not found for ID {img_id}",
            )
        paths.append(path)

    return paths


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


async def _run_cleanup_bg(
    op_id: str,
    project_dir: Path,
    mode: str,
    positive_prompts: list[str] | None,
    negative_prompts: list[str] | None,
    clip_threshold: float,
    reference_paths: list[Path] | None,
) -> None:
    """Background coroutine that runs the cleanup classification pipeline.

    Routes to text-based or reference-based classification depending on mode.
    """
    loop = asyncio.get_running_loop()
    queue = _cleanup_queues[op_id]

    try:
        item_paths = await loop.run_in_executor(
            None,
            lambda: _resolve_item_paths(project_dir),
        )

        total = len(item_paths)

        mode_label = "by reference images" if mode == "reference" else "by text description"
        await queue.put({
            "event": "cleanup_progress",
            "data": {
                "operation_id": op_id,
                "current": 0,
                "total": total,
                "message": f"Starting cleanup scan {mode_label} on {total} items...",
            },
        })

        def progress_callback(current: int, total: int) -> None:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {
                    "event": "cleanup_progress",
                    "data": {
                        "operation_id": op_id,
                        "current": current,
                        "total": total,
                        "message": f"Classifying item {current} of {total}",
                    },
                },
            )

        if mode == "reference" and reference_paths:
            results = await loop.run_in_executor(
                None,
                lambda: classify_items_by_reference(
                    item_paths=item_paths,
                    project_dir=project_dir,
                    reference_paths=reference_paths,
                    clip_threshold=clip_threshold,
                    progress_callback=progress_callback,
                ),
            )
        else:
            results = await loop.run_in_executor(
                None,
                lambda: classify_items(
                    item_paths=item_paths,
                    project_dir=project_dir,
                    positive_prompts=positive_prompts,
                    negative_prompts=negative_prompts,
                    clip_threshold=clip_threshold,
                    progress_callback=progress_callback,
                ),
            )

        result_dicts = [r.model_dump() for r in results]
        _cleanup_results[op_id] = result_dicts

        await queue.put({
            "event": "cleanup_done",
            "data": {
                "operation_id": op_id,
                "current": total,
                "total": total,
                "message": f"Cleanup complete: {len(results)} items classified.",
                "status": "complete",
                "results": result_dicts,
            },
        })

    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        logger.error("Cleanup operation %s failed: %s\n%s", op_id, exc, tb)
        await queue.put({
            "event": "cleanup_error",
            "data": {
                "operation_id": op_id,
                "message": f"Cleanup failed: {exc}",
                "traceback": tb,
            },
        })

    finally:
        await queue.put(None)


# ---------------------------------------------------------------------------
# SSE generator (mirrors triage.py pattern exactly)
# ---------------------------------------------------------------------------


async def _sse_generator(
    queue: asyncio.Queue,
    op_id: str,
    task_dict: dict,
    queue_dict: dict,
):
    """Consume events from queue and yield as ServerSentEvents.

    Emits "cleanup_done" when status is "complete". Stops on None sentinel.
    Cleans up task/queue dicts on exit.
    """
    try:
        while True:
            event = await queue.get()
            if event is None:
                break

            event_name = event["event"]
            data = event["data"]

            # When background task signals completion, emit done event
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
        # Clean up module-level state
        queue_dict.pop(op_id, None)
        task = task_dict.pop(op_id, None)
        if task and not task.done():
            task.cancel()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/start")
async def start_cleanup(body: CleanupStartRequest, request: Request) -> dict:
    """Start a cleanup classification scan in the background.

    Supports two modes:
    - "text": User provides a subject description, CLIP text-to-image matching.
    - "reference": User provides gallery image IDs, CLIP image-to-image matching.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    # Validate mode-specific fields
    positive_prompts = None
    negative_prompts = None
    reference_paths = None

    if body.mode == "text":
        if not body.subject_description:
            raise HTTPException(
                status_code=400,
                detail="subject_description is required for text mode",
            )
        positive_prompts, negative_prompts = generate_prompts_from_description(
            body.subject_description,
        )
        threshold = body.clip_threshold if body.clip_threshold is not None else 0.25
    elif body.mode == "reference":
        if not body.reference_image_ids or len(body.reference_image_ids) == 0:
            raise HTTPException(
                status_code=400,
                detail="reference_image_ids is required for reference mode (1-3 images)",
            )
        if len(body.reference_image_ids) > 3:
            raise HTTPException(
                status_code=400,
                detail="Maximum 3 reference images allowed",
            )
        reference_paths = _resolve_image_ids_to_paths(
            project_dir, body.reference_image_ids,
        )
        threshold = body.clip_threshold if body.clip_threshold is not None else DEFAULT_REFERENCE_THRESHOLD
    else:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {body.mode}")

    op_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _cleanup_queues[op_id] = queue

    task = asyncio.create_task(
        _run_cleanup_bg(
            op_id, project_dir,
            mode=body.mode,
            positive_prompts=positive_prompts,
            negative_prompts=negative_prompts,
            clip_threshold=threshold,
            reference_paths=reference_paths,
        ),
        name=f"cleanup-{op_id}",
    )
    _cleanup_tasks[op_id] = task

    logger.info("Started cleanup operation %s (mode=%s)", op_id, body.mode)
    return {"operation_id": op_id}


@router.get("/{op_id}/events")
async def cleanup_events(op_id: str) -> EventSourceResponse:
    """Stream SSE progress events for a cleanup operation.

    Args:
        op_id: Operation ID from start_cleanup.

    Returns:
        EventSourceResponse streaming cleanup progress events.

    Raises:
        HTTPException 404: If op_id is not found.
    """
    if op_id not in _cleanup_queues:
        raise HTTPException(status_code=404, detail=f"Cleanup operation {op_id} not found")

    queue = _cleanup_queues[op_id]
    return EventSourceResponse(
        _sse_generator(queue, op_id, _cleanup_tasks, _cleanup_queues)
    )


@router.post("/{op_id}/cancel")
async def cancel_cleanup(op_id: str) -> dict:
    """Cancel an in-progress cleanup operation.

    Args:
        op_id: Operation ID to cancel.

    Returns:
        {"cancelled": True/False}.

    Raises:
        HTTPException 404: If op_id not found.
    """
    task = _cleanup_tasks.pop(op_id, None)
    _cleanup_queues.pop(op_id, None)

    if task is None:
        raise HTTPException(status_code=404, detail=f"Cleanup operation {op_id} not found")

    if not task.done():
        task.cancel()
        logger.info("Cancelled cleanup operation %s", op_id)
        return {"cancelled": True}
    return {"cancelled": False}


@router.post("/confirm")
async def confirm_cleanup(body: ConfirmRemovalRequest, request: Request) -> dict:
    """Move flagged files to _review/ directory.

    Args:
        body: ConfirmRemovalRequest with list of item_paths.
        request: FastAPI request (for project_dir).

    Returns:
        {"moved": int, "review_dir": str}.

    Raises:
        HTTPException 409: If no project directory selected.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    result = confirm_removal(project_dir, body.item_paths)
    return result


@router.get("/results/{op_id}")
async def get_cleanup_results(op_id: str) -> list[dict]:
    """Return stored classification results for a cleanup operation.

    Args:
        op_id: Operation ID.

    Returns:
        List of classification result dicts.

    Raises:
        HTTPException 404: If op_id results not found.
    """
    if op_id not in _cleanup_results:
        raise HTTPException(status_code=404, detail=f"Results for operation {op_id} not found")

    return _cleanup_results[op_id]
