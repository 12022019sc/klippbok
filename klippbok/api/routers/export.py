"""Export router — API endpoints for LoRA trainer export operations.

Endpoints:
    GET  /export/defaults            -- Return default export config from project manifest.
    GET  /export/validate            -- Return pre-flight validation issues.
    POST /export/start               -- Start background export operation.
    GET  /export/{op_id}/events      -- SSE stream for export progress.
    POST /export/{op_id}/cancel      -- Cancel an in-progress export.
    GET  /export/train/status        -- OneTrainer detection + training active status.
    POST /export/train/start         -- Start headless OneTrainer training.
    GET  /export/train/{op_id}/events -- SSE stream for training progress.
    POST /export/train/{op_id}/stop  -- Stop an active training run.
    POST /export/train/launch-gui    -- Launch OneTrainer GUI (detached).
    GET  /export/train/models        -- List model files from configured model directory.

Named SSE event types:
    "export_progress"    -- Export in-progress update
    "export_done"        -- Export complete
    "export_error"       -- Export failed
    "training_progress"  -- Epoch update from OneTrainer
    "training_error"     -- Error event from OneTrainer
    "training_done"      -- Training completed

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
import time
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

# Module-level state for training operations
_train_queues: dict[str, asyncio.Queue] = {}
_train_start_times: dict[str, float] = {}


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


class TrainStartRequest(BaseModel):
    """Request body for starting a OneTrainer headless training operation."""

    preset_path: str
    base_model_path: str | None = None
    lora_rank: int = 64
    lora_alpha: int = 64
    epochs: int = 7
    batch_size: int = 2
    learning_rate: float = 1.0
    resolution: int = 768


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

    # Resolve output_dir against project_dir — frontend sends relative paths
    # like "./export/onetrainer/" which must land inside the project, not the
    # server's CWD.
    output_dir = Path(body.output_path)
    if not output_dir.is_absolute():
        output_dir = project_dir / output_dir

    config = ExportConfig(
        trainer=body.trainer,
        repeats=body.repeats,
        trigger_word=body.trigger_word,
        class_name=body.class_name,
        concept_name=body.concept_name,
        output_dir=output_dir,
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


# ---------------------------------------------------------------------------
# Training endpoints
# ---------------------------------------------------------------------------


@router.get("/train/status")
async def get_train_status() -> dict:
    """Return OneTrainer detection status, training state, and GPU VRAM usage.

    Returns:
        Dict with onetrainer_detected, onetrainer_path, training_active,
        gpu_vram_used_mb, gpu_busy.
    """
    from klippbok.services.global_config_service import load_global_config
    from klippbok.services.gpu_service import get_gpu_vram_used_mb, is_gpu_busy
    from klippbok.services.onetrainer_service import detect_onetrainer, is_training_active

    global_config = load_global_config()
    configured_path = global_config.get("onetrainer", {}).get("onetrainer_path")

    ot_path = detect_onetrainer(configured_path)
    vram_used = get_gpu_vram_used_mb()

    return {
        "onetrainer_detected": ot_path is not None,
        "onetrainer_path": str(ot_path) if ot_path else None,
        "training_active": is_training_active(),
        "gpu_vram_used_mb": vram_used,
        "gpu_busy": is_gpu_busy(),
    }


@router.post("/train/start")
async def start_training(body: TrainStartRequest, request: Request) -> dict:
    """Start a headless OneTrainer training operation.

    Detects OneTrainer, reads the preset from body.preset_path, applies
    overrides (base_model, rank, alpha, epochs, batch_size, lr, resolution),
    writes the modified preset to training_preset_active.json in the same
    directory, then launches the training subprocess.

    Args:
        body: TrainStartRequest with preset_path and training parameters.
        request: FastAPI request (for project_dir).

    Returns:
        {"op_id": str}

    Raises:
        HTTPException 400: If OneTrainer not configured or preset not found.
        HTTPException 409: If no project directory is selected.
    """
    from klippbok.services.global_config_service import load_global_config
    from klippbok.services.onetrainer_service import detect_onetrainer, launch_onetrainer_headless

    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    global_config = load_global_config()
    configured_path = global_config.get("onetrainer", {}).get("onetrainer_path")

    ot_root = detect_onetrainer(configured_path)
    if ot_root is None:
        raise HTTPException(
            status_code=400,
            detail="OneTrainer not configured. Set the install path in Settings.",
        )

    # Resolve preset path against project_dir — frontend sends relative paths
    # like "export/onetrainer/training_preset.json"
    preset_path = Path(body.preset_path)
    if not preset_path.is_absolute():
        preset_path = project_dir / preset_path
    if not preset_path.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"Preset file not found: {body.preset_path}",
        )

    # Read and modify the preset
    try:
        preset_data = _json.loads(preset_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to read preset file: {exc}",
        ) from exc

    # Apply training parameter overrides
    if body.base_model_path:
        preset_data["base_model_name"] = body.base_model_path
    preset_data["network_rank"] = body.lora_rank
    preset_data["network_alpha"] = float(body.lora_alpha)
    preset_data["num_epochs"] = body.epochs
    preset_data["batch_size"] = body.batch_size
    preset_data["learning_rate"] = body.learning_rate
    preset_data["resolution"] = body.resolution

    # Write modified preset next to the original
    active_preset_path = preset_path.parent / "training_preset_active.json"
    active_preset_path.write_text(
        _json.dumps(preset_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    op_id = uuid.uuid4().hex[:8]
    queue: asyncio.Queue = asyncio.Queue()
    _train_queues[op_id] = queue
    _train_start_times[op_id] = time.time()

    loop = asyncio.get_running_loop()
    # launch_onetrainer_headless is synchronous — run in executor to avoid blocking.
    # Pass the running loop explicitly because get_event_loop() returns a wrong
    # loop inside thread pool workers (Python 3.10+ deprecation).
    await loop.run_in_executor(
        None,
        lambda: launch_onetrainer_headless(ot_root, active_preset_path, queue, op_id, loop=loop),
    )

    logger.info("Started OneTrainer training operation %s", op_id)
    return {"op_id": op_id}


@router.get("/train/{op_id}/events")
async def training_events(op_id: str) -> EventSourceResponse:
    """Stream SSE training progress events for a training operation.

    Event types:
    - training_progress: {epoch, total_epochs}
    - training_error: {message, log_snippet}
    - training_done: {lora_path, epochs, duration_seconds}

    Args:
        op_id: Operation ID from start_training.

    Returns:
        EventSourceResponse streaming training progress events.

    Raises:
        HTTPException 404: If op_id is not found.
    """
    if op_id not in _train_queues:
        raise HTTPException(status_code=404, detail=f"Training operation {op_id} not found")

    queue = _train_queues[op_id]
    start_time = _train_start_times.get(op_id, time.time())

    async def _training_sse_generator():
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break

                event_type = event.get("type", "training_progress")
                op = event.get("op_id", op_id)

                if event_type == "training_progress":
                    yield ServerSentEvent(
                        event="training_progress",
                        data=_json.dumps({
                            "op_id": op,
                            "epoch": event.get("epoch", 0),
                            "total_epochs": event.get("total_epochs", 0),
                            "message": event.get("message", ""),
                        }),
                    )
                elif event_type == "training_error":
                    yield ServerSentEvent(
                        event="training_error",
                        data=_json.dumps({
                            "op_id": op,
                            "message": event.get("message", "Training error"),
                            "log_snippet": event.get("message", ""),
                        }),
                    )
                elif event_type == "training_done":
                    duration = time.time() - start_time
                    # Try to find the LoRA output path from the active preset
                    lora_path: str | None = None
                    try:
                        active_preset_candidates = list(
                            Path(".").rglob("training_preset_active.json")
                        )
                        if active_preset_candidates:
                            preset_data = _json.loads(
                                active_preset_candidates[0].read_text(encoding="utf-8")
                            )
                            lora_path = preset_data.get("output_model_destination")
                    except Exception:
                        pass

                    yield ServerSentEvent(
                        event="training_done",
                        data=_json.dumps({
                            "op_id": op,
                            "lora_path": lora_path,
                            "epochs": event.get("total_epochs", 0),
                            "duration_seconds": round(duration, 1),
                            "return_code": event.get("return_code", 0),
                            "message": event.get("message", "Training complete."),
                        }),
                    )
                    break
        finally:
            _train_queues.pop(op_id, None)
            _train_start_times.pop(op_id, None)

    return EventSourceResponse(_training_sse_generator())


@router.post("/train/{op_id}/stop")
async def stop_training(op_id: str) -> dict:
    """Gracefully stop an active OneTrainer training operation.

    Args:
        op_id: Training operation ID to stop.

    Returns:
        {"stopped": True/False}
    """
    from klippbok.services.onetrainer_service import stop_onetrainer

    stopped = stop_onetrainer(op_id)
    if not stopped:
        logger.warning("stop_training: op_id=%s not found in active processes", op_id)
    return {"stopped": stopped}


@router.post("/train/launch-gui")
async def launch_training_gui() -> dict:
    """Launch the OneTrainer GUI (detached, no tracking).

    Returns:
        {"status": "launched"} or {"status": "not_configured"}
    """
    from klippbok.services.global_config_service import load_global_config
    from klippbok.services.onetrainer_service import detect_onetrainer, launch_onetrainer_gui

    global_config = load_global_config()
    configured_path = global_config.get("onetrainer", {}).get("onetrainer_path")

    ot_root = detect_onetrainer(configured_path)
    if ot_root is None:
        raise HTTPException(
            status_code=400,
            detail="OneTrainer not configured. Set the install path in Settings.",
        )

    try:
        launch_onetrainer_gui(ot_root)
        logger.info("Launched OneTrainer GUI (ot_root=%s)", ot_root)
        return {"status": "launched"}
    except Exception as exc:
        logger.error("Failed to launch OneTrainer GUI: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to launch OneTrainer GUI: {exc}",
        ) from exc


@router.get("/train/models")
async def list_training_models() -> list[dict]:
    """List model files (.safetensors, .ckpt) from the configured model directory.

    Scans the model_dir from global config (onetrainer.model_dir) and returns
    files grouped by subfolder.

    Returns:
        List of {"path": str, "name": str, "subfolder": str} dicts.
        Empty list if model_dir not configured or not found.
    """
    from klippbok.services.global_config_service import load_global_config

    global_config = load_global_config()
    model_dir_str = global_config.get("onetrainer", {}).get("model_dir")

    if not model_dir_str:
        return []

    model_dir = Path(model_dir_str)
    if not model_dir.is_dir():
        return []

    models: list[dict] = []
    extensions = {".safetensors", ".ckpt"}

    for file_path in sorted(model_dir.rglob("*")):
        if file_path.suffix.lower() in extensions and file_path.is_file():
            # Subfolder relative to model_dir
            rel = file_path.relative_to(model_dir)
            parts = rel.parts
            subfolder = str(parts[0]) if len(parts) > 1 else ""
            models.append({
                "path": str(file_path),
                "name": file_path.name,
                "subfolder": subfolder,
            })

    return models
