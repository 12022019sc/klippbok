"""Upscale router -- start upscale operations and stream SSE progress events.

Endpoints:
    POST /upscale/start               -- Start a batch upscale, returns operation_id.
    GET  /upscale/{op_id}/events      -- Stream SSE progress events for an upscale.
    GET  /upscale/status              -- Return availability of upscaler tools.

Named SSE event types:
    "progress"      -- In-progress update (status="running")
    "done"          -- Upscale completed (status="complete")
    "upscale_error" -- Upscale failed (status="error")
      "upscale_error" is used instead of "error" to avoid collision with the
      browser EventSource built-in error event.

Pattern: Follows import_ router exactly (asyncio.Queue per operation, background
asyncio task, SSE generator consuming from queue, None sentinel to end stream).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from klippbok.api.models import UpscaleProgress, UpscaleRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upscale", tags=["upscale"])

# Module-level state for active upscale operations.
# These are process-local -- a restart clears all in-flight operations.
_queues: dict[str, asyncio.Queue] = {}
_tasks: dict[str, asyncio.Task] = {}


@router.post("/start", status_code=202)
async def start_upscale_operation(body: UpscaleRequest, request: Request) -> dict:
    """Start a batch upscale operation in the background.

    Creates an asyncio task that runs the upscaler subprocess and streams
    progress via SSE. Returns an operation_id for the client to subscribe to.

    Args:
        body: Upscale parameters (image_ids, upscaler, scale_factor).
        request: FastAPI request (used for app.state.project_dir).

    Returns:
        {"operation_id": str} for SSE subscription.

    Raises:
        HTTPException 409: If no project directory is selected.
    """
    from klippbok.services.upscale_service import detect_seedvr2
    from klippbok.api.routers.images import _image_id

    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    op_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _queues[op_id] = queue

    # Resolve image paths from manifest
    from klippbok.services.project_service import load_manifest

    try:
        manifest = load_manifest(project_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load manifest: {exc}") from exc

    id_to_path: dict[str, Path] = {}
    if manifest and "images" in manifest:
        for entry in manifest["images"]:
            relative_path = entry.get("path", "")
            img_id = _image_id(relative_path)
            abs_path = project_dir / relative_path
            if abs_path.exists():
                id_to_path[img_id] = abs_path

    image_paths = [id_to_path[img_id] for img_id in body.image_ids if img_id in id_to_path]
    if not image_paths:
        raise HTTPException(status_code=400, detail="No valid image paths found for provided image_ids")

    output_dir = project_dir / ".klippbok" / "upscaled"

    async def _run_upscale():
        from klippbok.services.upscale_service import start_upscale
        await start_upscale(
            image_paths=image_paths,
            output_dir=output_dir,
            upscaler=body.upscaler,
            scale_factor=body.scale_factor,
            queue=queue,
            op_id=op_id,
            project_dir=project_dir,
        )

    task = asyncio.create_task(_run_upscale(), name=f"upscale-{op_id}")
    _tasks[op_id] = task

    logger.info(
        "Started upscale operation %s (%s x%d, %d images)",
        op_id, body.upscaler, body.scale_factor, len(image_paths),
    )

    return {"operation_id": op_id}


@router.get("/status")
async def upscale_status() -> dict:
    """Return availability of installed upscaler tools.

    Returns:
        JSON with seedvr2_available, nmkd_siax_available, and their paths.
    """
    from klippbok.services.upscale_service import detect_nmkd_siax, detect_seedvr2

    seedvr2_path = detect_seedvr2()
    nmkd_path = detect_nmkd_siax()

    return {
        "seedvr2_available": seedvr2_path is not None,
        "nmkd_siax_available": nmkd_path is not None,
        "seedvr2_path": str(seedvr2_path) if seedvr2_path else None,
        "nmkd_siax_path": str(nmkd_path) if nmkd_path else None,
    }


@router.post("/{op_id}/cancel")
async def cancel_upscale_operation(op_id: str) -> dict:
    """Cancel a running upscale operation by killing its subprocess.

    Args:
        op_id: Operation ID returned by POST /upscale/start.

    Returns:
        {"cancelled": bool} indicating if the process was found and killed.
    """
    from klippbok.services.upscale_service import cancel_upscale

    killed = cancel_upscale(op_id)
    if not killed:
        logger.debug("Cancel requested for %s but no running process found", op_id)
    return {"cancelled": killed}


@router.post("/{op_id}/apply")
async def apply_upscaled(op_id: str, request: Request) -> dict:
    """Replace original images with their upscaled versions and update the manifest.

    Reads the name-mapping stored during the upscale operation to copy each
    upscaled file back over the original, then re-imports the affected entries
    so the manifest reflects the new dimensions.

    Args:
        op_id: Operation ID from POST /upscale/start.
        request: FastAPI request (for app.state.project_dir).

    Returns:
        {"replaced": int} count of files successfully replaced.
    """
    import shutil

    from klippbok.services.upscale_service import get_mapping, clear_mapping

    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    mapping = get_mapping(op_id)
    if mapping is None:
        raise HTTPException(status_code=404, detail=f"No mapping found for operation '{op_id}'")

    output_dir = project_dir / ".klippbok" / "upscaled"
    replaced = 0

    for staged_name, original_path in mapping.items():
        upscaled_path = output_dir / staged_name
        if not upscaled_path.exists():
            # Upscaler may change the extension (e.g. SeedVR2 outputs .png)
            # Look for a file with the same stem but any image extension
            stem = Path(staged_name).stem
            candidates = list(output_dir.glob(f"{stem}.*"))
            if candidates:
                upscaled_path = candidates[0]
                logger.info(
                    "Upscaler changed extension: expected %s, found %s",
                    staged_name, upscaled_path.name,
                )
            else:
                logger.warning("Upscaled file not found: %s (no extension variants either)", upscaled_path)
                continue
        if not original_path.exists():
            logger.warning("Original file no longer exists: %s", original_path)
            continue
        shutil.copy2(str(upscaled_path), str(original_path))
        replaced += 1
        logger.debug("Replaced %s with upscaled version", original_path)

    # Clean up upscaled output dir and mapping
    if output_dir.exists():
        shutil.rmtree(str(output_dir), ignore_errors=True)
    clear_mapping(op_id)

    # Re-import the replaced images so manifest gets updated dimensions.
    # We load the manifest directly and update matching entries.
    re_evaluated = 0
    if replaced > 0:
        loop = asyncio.get_running_loop()
        # Build set of relative paths that were replaced.
        # Normalize to forward slashes to match manifest path format.
        replaced_rel_paths = set()
        project_resolved = project_dir.resolve()
        for original_path in mapping.values():
            try:
                rel = original_path.resolve().relative_to(project_resolved)
                replaced_rel_paths.add(rel.as_posix())
            except ValueError:
                logger.warning(
                    "Could not relativize %s to %s", original_path, project_resolved
                )

        logger.info(
            "Apply upscale: %d files replaced, re-evaluating quality for: %s",
            replaced, replaced_rel_paths,
        )

        def _update_manifest_entries() -> int:
            from klippbok.services.project_service import load_manifest
            from klippbok.services.image_service import probe_image
            from klippbok.image.quality import BLUR_THRESHOLD, compute_blur_score
            from klippbok.api.routers.images import _image_id
            from PIL import Image
            import json

            manifest = load_manifest(project_dir)
            if not manifest or "images" not in manifest:
                logger.warning("No manifest or no images section found")
                return 0

            changed = False
            updated = 0
            for entry in manifest["images"]:
                rel_path = entry.get("path", "")
                # Normalize manifest path to forward slashes for comparison
                rel_path_normalized = rel_path.replace("\\", "/")
                if rel_path_normalized not in replaced_rel_paths:
                    continue
                abs_path = project_dir / rel_path
                if not abs_path.exists():
                    logger.warning("File not found for re-evaluation: %s", abs_path)
                    continue
                try:
                    # Re-probe dimensions
                    meta = probe_image(abs_path)
                    entry["width"] = meta.width
                    entry["height"] = meta.height

                    # Re-evaluate blur score
                    with Image.open(abs_path) as pil_img:
                        new_blur = compute_blur_score(pil_img)
                    entry["blur_score"] = new_blur

                    # Update issues: remove stale blur/upscale warnings, add new if needed
                    old_issues = [
                        i for i in entry.get("issues", [])
                        if i.get("code") not in ("IMAGE_BLUR_DETECTED", "IMAGE_UPSCALE_REQUIRED")
                    ]
                    if new_blur < BLUR_THRESHOLD:
                        old_issues.append({
                            "code": "IMAGE_BLUR_DETECTED",
                            "severity": "warning",
                            "message": (
                                f"Image appears blurry (Laplacian variance={new_blur:.1f} "
                                f"< threshold {BLUR_THRESHOLD})."
                            ),
                        })
                    entry["issues"] = old_issues
                    entry["status"] = "valid"

                    # Delete stale thumbnail so gallery fetches fresh
                    img_id = _image_id(rel_path)
                    thumb_path = project_dir / ".klippbok" / "thumbnails" / f"{img_id}.jpg"
                    if thumb_path.exists():
                        thumb_path.unlink()

                    changed = True
                    updated += 1
                    logger.info(
                        "Re-evaluated %s: %dx%d, blur=%.1f (threshold=%.1f)",
                        rel_path, meta.width, meta.height, new_blur, BLUR_THRESHOLD,
                    )
                except Exception as exc:
                    logger.warning("Failed to re-evaluate %s: %s", abs_path, exc)

            if changed:
                from klippbok.services.project_service import MANIFEST_DIR, MANIFEST_FILE
                manifest_path = project_dir / MANIFEST_DIR / MANIFEST_FILE
                manifest_path.write_text(
                    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                logger.info("Manifest updated with %d re-evaluated entries", updated)

            return updated

        try:
            re_evaluated = await loop.run_in_executor(None, _update_manifest_entries)
        except Exception as exc:
            logger.error("Failed to re-evaluate quality after upscale: %s", exc, exc_info=True)

    return {"replaced": replaced, "re_evaluated": re_evaluated}


@router.get("/{op_id}/events")
async def upscale_events(op_id: str) -> EventSourceResponse:
    """Stream SSE progress events for a batch upscale operation.

    Consumes events from the operation's queue and yields them as named
    Server-Sent Events. The stream closes when upscaling completes or fails.

    Named event types:
        "progress"     -- Intermediate progress update
        "done"         -- Upscale finished successfully
        "upscale_error" -- Upscale encountered an error

    Args:
        op_id: Operation ID returned by POST /upscale/start.

    Returns:
        EventSourceResponse streaming progress events.

    Raises:
        HTTPException 404: If op_id is not found.
    """
    if op_id not in _queues:
        raise HTTPException(
            status_code=404,
            detail=f"Upscale operation '{op_id}' not found.",
        )

    queue = _queues[op_id]

    async def event_generator():
        try:
            while True:
                event = await queue.get()

                # None sentinel signals end of stream
                if event is None:
                    break

                progress: UpscaleProgress = event
                data = progress.model_dump_json()

                if progress.status == "complete":
                    yield ServerSentEvent(data=data, event="done")
                    break
                elif progress.status == "error":
                    yield ServerSentEvent(data=data, event="upscale_error")
                    break
                else:
                    yield ServerSentEvent(data=data, event="progress")

        finally:
            # Clean up operation state after stream ends
            _queues.pop(op_id, None)
            task = _tasks.pop(op_id, None)
            if task and not task.done():
                task.cancel()
                logger.debug("Cancelled upscale task for operation %s", op_id)

    return EventSourceResponse(event_generator())
