"""Import router -- start batch imports and stream SSE progress events.

Endpoints:
    POST /import/           -- Start a batch import, returns operation_id.
    GET  /import/{op_id}/events -- Stream SSE progress events for an import.

Named SSE event types:
    "progress"     -- In-progress update (status="running")
    "done"         -- Import completed (status="complete")
    "import_error" -- Import failed (status="error")
      "import_error" is used instead of "error" to avoid collision with the
      browser EventSource built-in error event.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from klippbok.api.models import ImportProgress, ImportRequest, ImportStarted

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/import", tags=["import"])

# Module-level state for active import operations.
# These are process-local -- a restart clears all in-flight operations.
_queues: dict[str, asyncio.Queue] = {}
_tasks: dict[str, asyncio.Task] = {}


async def _run_import(
    request: ImportRequest,
    queue: asyncio.Queue,
    op_id: str,
    project_dir: Path,
) -> None:
    """Background coroutine that runs the batch import pipeline.

    Wraps the synchronous batch_import_images call in a thread executor so
    the async event loop remains responsive during the CPU-bound import work.

    Progress events are pushed onto the queue and consumed by the SSE generator.

    Args:
        request: Import request parameters (directory, recursive).
        queue: asyncio.Queue to push ImportProgress events onto.
        op_id: Operation UUID for event payloads.
        project_dir: Project root directory from app state.
    """
    from klippbok.image.discover import discover_images
    from klippbok.services.image_service import batch_import_images

    try:
        # Step 1: Discover images (fast -- runs in event loop)
        await queue.put(ImportProgress(
            operation_id=op_id,
            current=0,
            total=0,
            message="Discovering images...",
            status="running",
        ))

        import_dir = Path(request.directory)
        discovered = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: discover_images(import_dir, recursive=request.recursive),
        )
        total = len(discovered)

        await queue.put(ImportProgress(
            operation_id=op_id,
            current=0,
            total=total,
            message=f"Importing {total} image{'s' if total != 1 else ''}...",
            status="running",
        ))

        # Step 2: Run the full batch import in a thread (synchronous, CPU-bound)
        report = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: batch_import_images(
                directory=import_dir,
                project_dir=project_dir,
                recursive=request.recursive,
            ),
        )

        # Step 3: Emit completion event
        await queue.put(ImportProgress(
            operation_id=op_id,
            current=report.imported,
            total=report.total_discovered,
            message=(
                f"Import complete: {report.imported} imported, "
                f"{report.skipped_existing} skipped, "
                f"{report.rejected} rejected."
            ),
            status="complete",
        ))

    except Exception as exc:
        logger.error("Import operation %s failed: %s", op_id, exc)
        await queue.put(ImportProgress(
            operation_id=op_id,
            current=0,
            total=0,
            message=f"Import failed: {exc}",
            status="error",
        ))

    finally:
        # Sentinel: signals the SSE generator to stop reading
        await queue.put(None)


@router.post("/", response_model=ImportStarted, status_code=202)
async def start_import(body: ImportRequest, request: Request) -> ImportStarted:
    """Start a batch import operation in the background.

    Creates an asyncio task running the full import pipeline and returns an
    operation ID that the client can use to subscribe to the SSE progress stream.

    Args:
        body: Import parameters (directory and recursive flag).
        request: FastAPI request (used to access app.state.project_dir).

    Returns:
        ImportStarted with the operation_id for SSE subscription.
    """
    project_dir: Path = request.app.state.project_dir
    op_id = str(uuid.uuid4())

    queue: asyncio.Queue = asyncio.Queue()
    _queues[op_id] = queue

    task = asyncio.create_task(
        _run_import(body, queue, op_id, project_dir),
        name=f"import-{op_id}",
    )
    _tasks[op_id] = task

    logger.info("Started import operation %s for directory: %s", op_id, body.directory)
    return ImportStarted(operation_id=op_id)


@router.get("/{op_id}/events")
async def import_events(op_id: str) -> EventSourceResponse:
    """Stream SSE progress events for a batch import operation.

    Consumes events from the operation's queue and yields them as named
    Server-Sent Events. The stream closes when the import completes or fails.

    Named event types:
        "progress"     -- Intermediate progress update
        "done"         -- Import finished successfully
        "import_error" -- Import encountered an error

    Args:
        op_id: Operation ID returned by POST /import/.

    Returns:
        EventSourceResponse streaming progress events.

    Raises:
        HTTPException 404: If op_id is not found (operation does not exist).
    """
    if op_id not in _queues:
        raise HTTPException(
            status_code=404,
            detail=f"Import operation '{op_id}' not found.",
        )

    queue = _queues[op_id]

    async def event_generator():
        try:
            while True:
                event = await queue.get()

                # None sentinel signals end of stream
                if event is None:
                    break

                progress: ImportProgress = event
                data = progress.model_dump_json()

                if progress.status == "complete":
                    yield ServerSentEvent(data=data, event="done")
                    break
                elif progress.status == "error":
                    yield ServerSentEvent(data=data, event="import_error")
                    break
                else:
                    yield ServerSentEvent(data=data, event="progress")

        finally:
            # Clean up operation state after stream ends
            _queues.pop(op_id, None)
            task = _tasks.pop(op_id, None)
            if task and not task.done():
                task.cancel()
                logger.debug("Cancelled import task for operation %s", op_id)

    return EventSourceResponse(event_generator())
