"""Captions router -- batch generation with SSE progress and single-image PATCH.

Endpoints:
    POST /captions/generate         -- Start batch caption generation, returns op_id.
    GET  /captions/{op_id}/events   -- SSE stream for generation progress.
    PATCH /captions/{image_id}      -- Update a single image caption (inline edit).

Named SSE event types:
    "progress"      -- In-progress update (status="running")
    "done"          -- Generation completed (status="complete")
    "caption_error" -- Generation failed (status="error")
      "caption_error" is used instead of "error" to avoid collision with the
      browser EventSource built-in error event.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from klippbok.api.models import (
    CaptionGenerateRequest,
    CaptionProgress,
    CaptionStarted,
    CaptionUpdateRequest,
    CaptionUpdateResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/captions", tags=["captions"])

# Module-level state for active caption operations.
# These are process-local -- a restart clears all in-flight operations.
_queues: dict[str, asyncio.Queue] = {}
_tasks: dict[str, asyncio.Task] = {}


async def _run_caption_batch(
    body: CaptionGenerateRequest,
    queue: asyncio.Queue,
    op_id: str,
    project_dir: Path,
) -> None:
    """Background coroutine that runs the batch caption generation pipeline.

    Iterates over selected images, calls caption_image_for_project() via
    run_in_executor (ONNX/VLM backends are synchronous/blocking), saves
    each caption, and pushes SSE progress events onto the queue.

    Args:
        body: Caption generation request parameters.
        queue: asyncio.Queue to push CaptionProgress events onto.
        op_id: Operation UUID for event payloads.
        project_dir: Project root directory from app state.
    """
    from klippbok.api.routers.images import _image_id
    from klippbok.services.caption_service import caption_image_for_project, save_caption
    from klippbok.services.project_service import load_manifest

    try:
        # Step 1: Load manifest
        await queue.put(CaptionProgress(
            operation_id=op_id,
            current=0,
            total=0,
            message="Loading project manifest...",
            status="running",
        ))

        manifest = load_manifest(project_dir)
        if not manifest or "images" not in manifest:
            await queue.put(CaptionProgress(
                operation_id=op_id,
                current=0,
                total=0,
                message="No images found in project manifest.",
                status="error",
            ))
            return

        # Step 2: Determine images to process
        all_images = manifest["images"]

        if body.image_ids is not None:
            images_to_process = [
                e for e in all_images
                if _image_id(e.get("path", "")) in body.image_ids
            ]
        else:
            images_to_process = all_images

        # Filter out already-captioned images unless overwrite is set
        if not body.overwrite:
            images_to_process = [
                e for e in images_to_process
                if not e.get("caption")
            ]

        total = len(images_to_process)
        if total == 0:
            await queue.put(CaptionProgress(
                operation_id=op_id,
                current=0,
                total=0,
                message="No images to caption (all already captioned; set overwrite=true to re-caption).",
                status="complete",
            ))
            return

        await queue.put(CaptionProgress(
            operation_id=op_id,
            current=0,
            total=total,
            message=f"Captioning {total} image{'s' if total != 1 else ''}...",
            status="running",
        ))

        # Step 3: Build VLM config if needed for NL captioning
        vlm_config = None
        if body.provider is not None:
            from klippbok.caption.models import CaptionConfig
            vlm_config = CaptionConfig(
                provider=body.provider,  # type: ignore[arg-type]
                api_key=body.api_key or "",
            )

        # Step 4: Process images one by one
        completed = 0
        errors = 0

        for entry in images_to_process:
            relative_path = entry.get("path", "")
            abs_path = project_dir / relative_path
            img_id = _image_id(relative_path)

            try:
                # Prepare manifest for style lookup, injecting style override if requested
                lookup_manifest = dict(manifest)
                if body.style in ("booru", "natural_language"):
                    lookup_manifest = dict(manifest)
                    lookup_manifest["caption_style_override"] = body.style

                # Run caption generation in thread (ONNX/VLM are blocking)
                caption = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda p=abs_path, m=lookup_manifest: caption_image_for_project(
                        p, m, vlm_config, body.general_threshold,
                    ),
                )

                # Save: sidecar + manifest (manifest mutated in place)
                save_caption(abs_path, caption, manifest, img_id)
                completed += 1

                await queue.put(CaptionProgress(
                    operation_id=op_id,
                    current=completed,
                    total=total,
                    message=f"Captioned: {relative_path}",
                    status="running",
                ))

            except Exception as exc:
                errors += 1
                logger.error(
                    "Caption failed for '%s' in operation %s: %s",
                    relative_path, op_id, exc,
                )
                await queue.put(CaptionProgress(
                    operation_id=op_id,
                    current=completed,
                    total=total,
                    message=f"Error captioning {relative_path}: {exc}",
                    status="running",
                ))

        # Step 5: Persist updated manifest (all captions saved in memory above)
        # Write the full manifest dict back -- do NOT use save_image_entries which appends
        try:
            import json
            from datetime import datetime, timezone

            from klippbok.services.project_service import MANIFEST_DIR, MANIFEST_FILE

            manifest["updated"] = datetime.now(timezone.utc).isoformat()
            manifest_path = project_dir / MANIFEST_DIR / MANIFEST_FILE
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("Failed to persist manifest after captioning: %s", exc)

        # Step 6: Emit completion event
        summary_parts = [f"Captioning complete: {completed}/{total} captioned"]
        if errors:
            summary_parts.append(f"{errors} failed")
        await queue.put(CaptionProgress(
            operation_id=op_id,
            current=completed,
            total=total,
            message=". ".join(summary_parts),
            status="complete",
        ))

    except Exception as exc:
        logger.error("Caption operation %s failed: %s", op_id, exc)
        await queue.put(CaptionProgress(
            operation_id=op_id,
            current=0,
            total=0,
            message=f"Caption generation failed: {exc}",
            status="error",
        ))

    finally:
        # Sentinel: signals the SSE generator to stop reading
        await queue.put(None)


@router.post("/generate", response_model=CaptionStarted, status_code=202)
async def start_caption_generation(
    body: CaptionGenerateRequest,
    request: Request,
) -> CaptionStarted:
    """Start a batch caption generation operation in the background.

    Creates an asyncio task that captions the specified images (or all images
    if image_ids is None) using the active model profile's caption style.
    Returns an operation ID for subscribing to SSE progress events.

    Args:
        body: Caption generation parameters.
        request: FastAPI request (used to access app.state.project_dir).

    Returns:
        CaptionStarted with the operation_id for SSE subscription.

    Raises:
        HTTPException 409: If no project directory is selected.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    op_id = str(uuid.uuid4())

    queue: asyncio.Queue = asyncio.Queue()
    _queues[op_id] = queue

    task = asyncio.create_task(
        _run_caption_batch(body, queue, op_id, project_dir),
        name=f"caption-{op_id}",
    )
    _tasks[op_id] = task

    logger.info(
        "Started caption operation %s (style=%s, overwrite=%s, images=%s)",
        op_id, body.style, body.overwrite,
        "all" if body.image_ids is None else len(body.image_ids),
    )
    return CaptionStarted(operation_id=op_id)


@router.get("/{op_id}/events")
async def caption_events(op_id: str) -> EventSourceResponse:
    """Stream SSE progress events for a batch caption generation operation.

    Consumes events from the operation's queue and yields them as named
    Server-Sent Events. The stream closes when the operation completes or fails.

    Named event types:
        "progress"      -- Intermediate progress update
        "done"          -- Generation finished successfully
        "caption_error" -- Generation encountered an error

    Args:
        op_id: Operation ID returned by POST /captions/generate.

    Returns:
        EventSourceResponse streaming progress events.

    Raises:
        HTTPException 404: If op_id is not found.
    """
    if op_id not in _queues:
        raise HTTPException(
            status_code=404,
            detail=f"Caption operation '{op_id}' not found.",
        )

    queue = _queues[op_id]

    async def event_generator():
        try:
            while True:
                event = await queue.get()

                # None sentinel signals end of stream
                if event is None:
                    break

                progress: CaptionProgress = event
                data = progress.model_dump_json()

                if progress.status == "complete":
                    yield ServerSentEvent(data=data, event="done")
                    break
                elif progress.status == "error":
                    yield ServerSentEvent(data=data, event="caption_error")
                    break
                else:
                    yield ServerSentEvent(data=data, event="progress")

        finally:
            # Clean up operation state after stream ends
            _queues.pop(op_id, None)
            task = _tasks.pop(op_id, None)
            if task and not task.done():
                task.cancel()
                logger.debug("Cancelled caption task for operation %s", op_id)

    return EventSourceResponse(event_generator())


@router.patch("/{image_id}", response_model=CaptionUpdateResponse)
async def update_caption(
    image_id: str,
    body: CaptionUpdateRequest,
    request: Request,
) -> CaptionUpdateResponse:
    """Update a single image caption (inline edit).

    Updates both the manifest entry and the sidecar .txt file atomically.
    Used by the inline caption editor in the gallery lightbox.

    Args:
        image_id: SHA256[:16] image ID (from gallery list response).
        body: New caption text.
        request: FastAPI request (used to access app.state.project_dir).

    Returns:
        CaptionUpdateResponse with the saved caption and sidecar status.

    Raises:
        HTTPException 409: If no project directory is selected.
        HTTPException 404: If the image is not found in the manifest.
        HTTPException 500: If the manifest cannot be loaded or saved.
    """
    import json
    from datetime import datetime, timezone

    from klippbok.api.routers.images import _find_entry_by_id
    from klippbok.services.caption_service import save_caption
    from klippbok.services.project_service import MANIFEST_DIR, MANIFEST_FILE, load_manifest

    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    # Load manifest and find the image entry
    try:
        manifest = load_manifest(project_dir)
    except Exception as exc:
        logger.error("Failed to load manifest: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load project manifest") from exc

    if not manifest or "images" not in manifest:
        raise HTTPException(status_code=404, detail="No images in manifest")

    # Locate the image file on disk (raises 404 if not found)
    entry, abs_path = _find_entry_by_id(image_id, project_dir)

    sidecar_written = False
    try:
        # Save: mutates manifest entry in place + writes sidecar .txt
        save_caption(abs_path, body.caption, manifest, image_id)
        sidecar_written = True
    except Exception as exc:
        logger.error("Failed to write sidecar for '%s': %s", abs_path, exc)
        # Don't raise -- we can still update the manifest

    # Persist the updated manifest by writing the full dict back
    # (do NOT use save_image_entries -- that function appends, designed for import batches)
    try:
        manifest["updated"] = datetime.now(timezone.utc).isoformat()
        manifest_path = project_dir / MANIFEST_DIR / MANIFEST_FILE
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        logger.error("Failed to persist manifest after caption update: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Caption saved to sidecar but manifest update failed: {exc}",
        ) from exc

    logger.info("Updated caption for image '%s' in project %s", image_id, project_dir)
    return CaptionUpdateResponse(
        image_id=image_id,
        caption=body.caption,
        sidecar_written=sidecar_written,
    )
