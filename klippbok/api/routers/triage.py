"""Triage router — CLIP triage, concept management, face embedding, and health.

Endpoints:
    POST /triage/run/start                     -- Start CLIP triage, returns operation_id.
    GET  /triage/run/{op_id}/events            -- SSE stream for triage progress.
    POST /triage/run/{op_id}/cancel            -- Cancel triage operation.
    GET  /triage/results                       -- Get persisted triage results.
    GET  /triage/concepts                      -- List all concept references.
    POST /triage/concepts/upload               -- Upload image file as concept reference.
    POST /triage/concepts                      -- Add image as concept reference (path-based).
    POST /triage/face/start                    -- Start face embedding, returns operation_id.
    GET  /triage/face/{op_id}/events           -- SSE stream for face embedding progress.
    POST /triage/face/{op_id}/cancel           -- Cancel face embedding operation.
    GET  /triage/face/clusters                 -- Get current face clusters.
    POST /triage/face/clusters/{cluster_id}/name -- Name a face cluster.
    GET  /triage/health                        -- CLIP and InsightFace availability.

Named SSE event types:
    "triage_progress" -- CLIP triage in-progress update
    "triage_error"    -- CLIP triage failed
    "face_progress"   -- Face embedding in-progress update
    "face_error"      -- Face embedding failed

Route registration note:
    Specific routes (/run/start, /face/start, /face/clusters, /health, /results,
    /concepts) MUST be registered BEFORE wildcard path routes to prevent path
    parameter capture. FastAPI registers routes in order — more specific first.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Literal

import tempfile

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from klippbok.services.face_service import (
    FaceCluster,
    check_insightface_available,
    cluster_face_embeddings,
    compute_face_embeddings,
)
from klippbok.services.triage_service import (
    TriageResult,
    add_concept_reference,
    get_triage_results,
    list_concepts,
    run_triage,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/triage", tags=["triage"])

# Module-level state for active operations (process-local)
_triage_tasks: dict[str, asyncio.Task] = {}
_triage_queues: dict[str, asyncio.Queue] = {}
_face_tasks: dict[str, asyncio.Task] = {}
_face_queues: dict[str, asyncio.Queue] = {}

# Module-level face cluster store keyed by project_dir string
_face_clusters: dict[str, list[FaceCluster]] = {}

# CLIP availability check (module-level bool, avoids importing heavy deps on startup)
def check_clip_available_flag() -> bool:
    """Return True if CLIP dependencies (torch+transformers) are available."""
    try:
        from klippbok.triage.embeddings import _CLIP_AVAILABLE
        return _CLIP_AVAILABLE
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------

class TriageRunRequest(BaseModel):
    """Request body for starting a CLIP triage run."""
    threshold: float = 0.70
    item_ids: list[str] | None = None
    """Specific item IDs to triage. None means all items in the project."""
    concepts_dir: str | None = None
    """Override path to concepts directory. Defaults to project/concepts/."""


class AddConceptRequest(BaseModel):
    """Request body for adding an image as a concept reference."""
    image_path: str
    """Absolute or relative path to the source image."""
    category: str
    """Concept category folder (e.g. 'character', 'setting')."""


class FaceRunRequest(BaseModel):
    """Request body for starting face embedding computation."""
    item_ids: list[str] | None = None
    """Specific item IDs to process. None means all images in the project."""


class NameClusterRequest(BaseModel):
    """Request body for naming a face cluster."""
    name: str
    """Human-readable name for the cluster (e.g. 'Alice', 'Main Character')."""
    confirmed: bool = False
    """If True, create concept reference from cluster's primary_reference."""


class ConceptResponse(BaseModel):
    """API representation of a concept reference."""
    name: str
    concept_type: str | None
    image_path: str
    folder_name: str


class HealthResponse(BaseModel):
    """Triage service health status."""
    clip_available: bool
    insightface_available: bool
    clip_model_loaded: bool


# ---------------------------------------------------------------------------
# Helper: resolve item paths from project
# ---------------------------------------------------------------------------

def _resolve_item_paths(project_dir: Path, item_ids: list[str] | None) -> list[Path]:
    """Resolve item paths from the project manifest.

    Args:
        project_dir: Project root directory.
        item_ids: Optional list of item IDs to filter. None = all items.

    Returns:
        List of resolved Path objects for triage items.
    """
    import json as _json

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
# Background coroutine: CLIP triage
# ---------------------------------------------------------------------------

async def _run_triage_bg(
    request: TriageRunRequest,
    queue: asyncio.Queue,
    op_id: str,
    project_dir: Path,
) -> None:
    """Background coroutine that runs the CLIP triage pipeline.

    Runs run_triage in a thread executor (CPU-bound CLIP work).
    Progress callback enqueues events for the SSE generator.
    None sentinel signals end of stream.
    """
    loop = asyncio.get_running_loop()

    try:
        item_paths = await loop.run_in_executor(
            None,
            lambda: _resolve_item_paths(project_dir, request.item_ids),
        )

        concepts_dir = (
            Path(request.concepts_dir)
            if request.concepts_dir
            else project_dir / "concepts"
        )

        output_path = project_dir / ".klippbok" / "triage_manifest.json"

        total = len(item_paths)
        progress_sent = {"count": 0}

        def progress_callback(current: int, total: int) -> None:
            progress_sent["count"] += 1
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {
                    "event": "triage_progress",
                    "data": {
                        "operation_id": op_id,
                        "current": current,
                        "total": total,
                        "message": f"Triaging item {current} of {total}",
                    },
                },
            )

        await queue.put({
            "event": "triage_progress",
            "data": {
                "operation_id": op_id,
                "current": 0,
                "total": total,
                "message": f"Starting triage on {total} items...",
            },
        })

        results = await loop.run_in_executor(
            None,
            lambda: run_triage(
                item_paths=item_paths,
                concepts_dir=concepts_dir,
                threshold=request.threshold,
                output_path=output_path,
                progress_callback=progress_callback,
                project_dir=project_dir,
            ),
        )

        await queue.put({
            "event": "triage_progress",
            "data": {
                "operation_id": op_id,
                "current": total,
                "total": total,
                "message": f"Triage complete: {len(results)} items processed.",
                "status": "complete",
            },
        })

    except Exception as exc:
        logger.error("Triage operation %s failed: %s", op_id, exc)
        await queue.put({
            "event": "triage_error",
            "data": {
                "operation_id": op_id,
                "message": f"Triage failed: {exc}",
            },
        })

    finally:
        await queue.put(None)  # Sentinel


# ---------------------------------------------------------------------------
# Background coroutine: face embedding
# ---------------------------------------------------------------------------

async def _run_face_bg(
    request: FaceRunRequest,
    queue: asyncio.Queue,
    op_id: str,
    project_dir: Path,
) -> None:
    """Background coroutine that runs face embedding + clustering.

    Two-stage progress: embedding phase then clustering phase.
    """
    loop = asyncio.get_running_loop()

    try:
        item_paths = await loop.run_in_executor(
            None,
            lambda: _resolve_item_paths(project_dir, request.item_ids),
        )

        total = len(item_paths)
        start_time = time.monotonic()

        await queue.put({
            "event": "face_progress",
            "data": {
                "operation_id": op_id,
                "current": 0,
                "total": total,
                "eta_seconds": None,
                "message": f"Computing face embeddings for {total} images...",
            },
        })

        def progress_callback(current: int, total: int) -> None:
            elapsed = time.monotonic() - start_time
            eta = (elapsed / current) * (total - current) if current > 0 else None
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {
                    "event": "face_progress",
                    "data": {
                        "operation_id": op_id,
                        "current": current,
                        "total": total,
                        "eta_seconds": round(eta, 1) if eta is not None else None,
                        "message": f"Embedding face {current} of {total}",
                    },
                },
            )

        embeddings = await loop.run_in_executor(
            None,
            lambda: compute_face_embeddings(item_paths, progress_callback=progress_callback),
        )

        await queue.put({
            "event": "face_progress",
            "data": {
                "operation_id": op_id,
                "current": total,
                "total": total,
                "eta_seconds": 0,
                "message": f"Clustering {len(embeddings)} face embeddings...",
            },
        })

        clusters = await loop.run_in_executor(
            None,
            lambda: cluster_face_embeddings(embeddings),
        )

        # Store clusters for retrieval
        _face_clusters[str(project_dir)] = clusters

        await queue.put({
            "event": "face_progress",
            "data": {
                "operation_id": op_id,
                "current": total,
                "total": total,
                "eta_seconds": 0,
                "message": f"Face analysis complete: {len(clusters)} cluster(s) found.",
                "status": "complete",
            },
        })

    except Exception as exc:
        logger.error("Face embedding operation %s failed: %s", op_id, exc)
        await queue.put({
            "event": "face_error",
            "data": {
                "operation_id": op_id,
                "message": f"Face embedding failed: {exc}",
            },
        })

    finally:
        await queue.put(None)  # Sentinel


# ---------------------------------------------------------------------------
# SSE generator helper
# ---------------------------------------------------------------------------

async def _sse_generator(queue: asyncio.Queue, op_id: str, task_dict: dict, queue_dict: dict):
    """Consume events from queue and yield as ServerSentEvents.

    Emits "triage_done"/"face_done" when status is "complete" (the background
    coroutines send this as part of triage_progress/face_progress data).

    Stops when None sentinel is received. Cleans up task/queue dicts on exit.
    """
    import json as _json

    try:
        while True:
            event = await queue.get()
            if event is None:
                break

            event_name = event["event"]
            data = event["data"]

            # When the background task signals completion, emit the
            # correct "done" event that the frontend listens for.
            if data.get("status") == "complete":
                # Derive done event name: triage_progress -> triage_done,
                # face_progress -> face_done
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
# CLIP Triage endpoints
# ---------------------------------------------------------------------------

@router.post("/run/start", status_code=202)
async def start_triage_run(body: TriageRunRequest, request: Request) -> dict:
    """Start a CLIP triage operation in the background.

    Args:
        body: Triage parameters (threshold, item_ids, concepts_dir).
        request: FastAPI request (used for app.state.project_dir).

    Returns:
        {"operation_id": str} for SSE subscription.

    Raises:
        HTTPException 409: If no project directory is selected.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    op_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _triage_queues[op_id] = queue

    task = asyncio.create_task(
        _run_triage_bg(body, queue, op_id, project_dir),
        name=f"triage-{op_id}",
    )
    _triage_tasks[op_id] = task

    logger.info("Started triage operation %s", op_id)
    return {"operation_id": op_id}


@router.get("/run/{op_id}/events")
async def triage_events(op_id: str) -> EventSourceResponse:
    """Stream SSE progress events for a triage operation.

    Args:
        op_id: Operation ID from start_triage_run.

    Returns:
        EventSourceResponse streaming triage progress events.

    Raises:
        HTTPException 404: If op_id is not found.
    """
    if op_id not in _triage_queues:
        raise HTTPException(status_code=404, detail=f"Triage operation {op_id} not found")

    queue = _triage_queues[op_id]
    return EventSourceResponse(
        _sse_generator(queue, op_id, _triage_tasks, _triage_queues)
    )


@router.post("/run/{op_id}/cancel")
async def cancel_triage_run(op_id: str) -> dict:
    """Cancel an in-progress triage operation.

    Args:
        op_id: Operation ID to cancel.

    Returns:
        {"cancelled": True} if cancelled, {"cancelled": False} if already done.

    Raises:
        HTTPException 404: If op_id is not found.
    """
    task = _triage_tasks.pop(op_id, None)
    _triage_queues.pop(op_id, None)

    if task is None:
        raise HTTPException(status_code=404, detail=f"Triage operation {op_id} not found")

    if not task.done():
        task.cancel()
        logger.info("Cancelled triage operation %s", op_id)
        return {"cancelled": True}
    return {"cancelled": False}


@router.get("/results")
async def get_results(request: Request) -> list[dict]:
    """Return persisted triage results from the project manifest.

    Returns:
        List of TriageResult dicts. Empty list if no manifest exists.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        return []

    manifest_path = project_dir / ".klippbok" / "triage_manifest.json"
    results = get_triage_results(manifest_path)
    return [r.model_dump() for r in results]


# ---------------------------------------------------------------------------
# Concept management endpoints
# ---------------------------------------------------------------------------

@router.get("/concepts")
async def get_concepts(request: Request) -> list[dict]:
    """Return all concept references from the project concepts/ directory.

    Returns:
        List of concept reference dicts.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        return []

    concepts_dir = project_dir / "concepts"
    if not concepts_dir.exists():
        return []

    refs = list_concepts(concepts_dir)
    return [
        {
            "name": r.name,
            "concept_type": r.concept_type.value if r.concept_type else None,
            "image_path": str(r.image_path),
            "folder_name": r.folder_name,
        }
        for r in refs
    ]


@router.post("/concepts/upload")
async def upload_concept(
    file: UploadFile,
    request: Request,
    category: str = Form(...),
) -> dict:
    """Upload an image file as a concept reference.

    Saves the uploaded file to concepts/{category}/ and returns the
    newly created ConceptReference. The file is written directly to the
    target location, then passed to add_concept_reference() for consistent
    ConceptReference construction.

    Args:
        file: Uploaded image file.
        category: Concept category folder (e.g. 'character', 'setting').
        request: FastAPI request (for project_dir).

    Returns:
        ConceptResponse dict with name, concept_type, image_path, folder_name.

    Raises:
        HTTPException 409: If no project directory is selected.
        HTTPException 422: If file or category is missing (FastAPI validation).
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    concepts_dir = project_dir / "concepts"

    # Save the upload to a temp file in the project dir, then pass it to
    # add_concept_reference() which handles copying to concepts/{category}/.
    # Using a temp file avoids writing directly to the target location, which
    # would cause a SameFileError in shutil.copy2 (src == dst).
    filename = file.filename or "upload"
    suffix = Path(filename).suffix or ".bin"

    content = await file.read()

    with tempfile.NamedTemporaryFile(
        dir=project_dir, delete=False, suffix=suffix, prefix="_upload_"
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)
        tmp_file.write(content)

    # Rename temp file to match the original filename so add_concept_reference
    # uses the correct stem + extension when constructing the ConceptReference.
    named_tmp = tmp_path.parent / filename
    tmp_path.replace(named_tmp)
    tmp_path = named_tmp

    try:
        ref = add_concept_reference(
            image_path=tmp_path,
            concepts_dir=concepts_dir,
            category=category,
        )
    finally:
        # Clean up the temp source file — add_concept_reference has already
        # copied it to concepts/{category}/
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    return {
        "name": ref.name,
        "concept_type": ref.concept_type.value if ref.concept_type else None,
        "image_path": str(ref.image_path),
        "folder_name": ref.folder_name,
    }


class AddFromGalleryRequest(BaseModel):
    """Request body for adding a gallery image as a concept reference."""
    image_id: str
    """SHA256[:16] image ID from the gallery."""
    category: str = "character"
    """Concept category folder (e.g. 'character', 'setting')."""


@router.post("/concepts/add-from-gallery")
async def add_concept_from_gallery(body: AddFromGalleryRequest, request: Request) -> dict:
    """Add a gallery image as a concept reference.

    Looks up the image's absolute path from the manifest, then copies it
    into concepts/{category}/.

    Args:
        body: AddFromGalleryRequest with image_id and category.
        request: FastAPI request (for project_dir).

    Returns:
        ConceptResponse dict.

    Raises:
        HTTPException 404: If image_id not found in manifest.
        HTTPException 409: If no project directory is selected.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    # Look up image path from manifest
    from klippbok.services.project_service import load_manifest
    import hashlib as _hashlib

    manifest = load_manifest(project_dir)
    if not manifest or "images" not in manifest:
        raise HTTPException(status_code=404, detail="No images in manifest")

    target_entry = None
    for entry in manifest["images"]:
        rel_path = entry.get("path", "")
        entry_id = _hashlib.sha256(rel_path.encode()).hexdigest()[:16]
        if entry_id == body.image_id:
            target_entry = entry
            break

    if target_entry is None:
        raise HTTPException(status_code=404, detail=f"Image '{body.image_id}' not found")

    abs_path = project_dir / target_entry["path"]
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="Image file not found on disk")

    concepts_dir = project_dir / "concepts"
    ref = add_concept_reference(
        image_path=abs_path,
        concepts_dir=concepts_dir,
        category=body.category,
    )

    return {
        "name": ref.name,
        "concept_type": ref.concept_type.value if ref.concept_type else None,
        "image_path": str(ref.image_path),
        "folder_name": ref.folder_name,
    }


@router.post("/concepts")
async def add_concept(body: AddConceptRequest, request: Request) -> dict:
    """Add an image file as a concept reference.

    Copies the image into concepts/{category}/ and returns the
    newly created ConceptReference.

    Args:
        body: AddConceptRequest with image_path and category.
        request: FastAPI request (for project_dir).

    Returns:
        ConceptResponse dict.

    Raises:
        HTTPException 404: If the source image does not exist.
        HTTPException 409: If no project directory is selected.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    image_path = Path(body.image_path)
    if not image_path.is_absolute():
        image_path = project_dir / image_path

    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {image_path}")

    concepts_dir = project_dir / "concepts"
    ref = add_concept_reference(
        image_path=image_path,
        concepts_dir=concepts_dir,
        category=body.category,
    )

    return {
        "name": ref.name,
        "concept_type": ref.concept_type.value if ref.concept_type else None,
        "image_path": str(ref.image_path),
        "folder_name": ref.folder_name,
    }


# ---------------------------------------------------------------------------
# Face embedding endpoints
# ---------------------------------------------------------------------------

@router.post("/face/start", status_code=202)
async def start_face_embedding(body: FaceRunRequest, request: Request) -> dict:
    """Start face embedding computation in the background.

    Args:
        body: FaceRunRequest with optional item_ids to process.
        request: FastAPI request (for project_dir).

    Returns:
        {"operation_id": str} for SSE subscription.

    Raises:
        HTTPException 409: If no project directory is selected.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    op_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _face_queues[op_id] = queue

    task = asyncio.create_task(
        _run_face_bg(body, queue, op_id, project_dir),
        name=f"face-{op_id}",
    )
    _face_tasks[op_id] = task

    logger.info("Started face embedding operation %s", op_id)
    return {"operation_id": op_id}


@router.get("/face/{op_id}/events")
async def face_events(op_id: str) -> EventSourceResponse:
    """Stream SSE progress events for a face embedding operation.

    Args:
        op_id: Operation ID from start_face_embedding.

    Returns:
        EventSourceResponse streaming face progress events.

    Raises:
        HTTPException 404: If op_id is not found.
    """
    if op_id not in _face_queues:
        raise HTTPException(status_code=404, detail=f"Face operation {op_id} not found")

    queue = _face_queues[op_id]
    return EventSourceResponse(
        _sse_generator(queue, op_id, _face_tasks, _face_queues)
    )


@router.post("/face/{op_id}/cancel")
async def cancel_face_embedding(op_id: str) -> dict:
    """Cancel an in-progress face embedding operation.

    Args:
        op_id: Operation ID to cancel.

    Returns:
        {"cancelled": True/False}.

    Raises:
        HTTPException 404: If op_id not found.
    """
    task = _face_tasks.pop(op_id, None)
    _face_queues.pop(op_id, None)

    if task is None:
        raise HTTPException(status_code=404, detail=f"Face operation {op_id} not found")

    if not task.done():
        task.cancel()
        logger.info("Cancelled face operation %s", op_id)
        return {"cancelled": True}
    return {"cancelled": False}


@router.get("/face/clusters")
async def get_face_clusters(request: Request) -> list[dict]:
    """Return current face clusters for the project.

    Clusters are stored in memory after face embedding completes.
    Returns empty list if no clustering has been run.

    Returns:
        List of FaceCluster dicts.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        return []

    clusters = _face_clusters.get(str(project_dir), [])
    return [c.model_dump() for c in clusters]


@router.post("/face/clusters/{cluster_id}/name")
async def name_face_cluster(
    cluster_id: int,
    body: NameClusterRequest,
    request: Request,
) -> dict:
    """Name a face cluster (set suggested_name).

    Optionally creates a concept reference when confirmed=True.

    Args:
        cluster_id: The cluster_id to name.
        body: NameClusterRequest with name and optional confirmed flag.
        request: FastAPI request (for project_dir).

    Returns:
        Updated FaceCluster dict.

    Raises:
        HTTPException 404: If cluster_id not found or no clusters in memory.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    project_key = str(project_dir)
    clusters = _face_clusters.get(project_key, [])

    target = next((c for c in clusters if c.cluster_id == cluster_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

    # Update in place (Pydantic BaseModel — create new instance)
    updated_cluster = FaceCluster(
        cluster_id=target.cluster_id,
        image_paths=target.image_paths,
        suggested_name=body.name,
        primary_reference=target.primary_reference,
    )

    # Replace in list
    idx = next(i for i, c in enumerate(clusters) if c.cluster_id == cluster_id)
    _face_clusters[project_key][idx] = updated_cluster

    if body.confirmed and updated_cluster.primary_reference:
        try:
            concepts_dir = project_dir / "concepts"
            add_concept_reference(
                image_path=Path(updated_cluster.primary_reference),
                concepts_dir=concepts_dir,
                category="character",
            )
        except Exception as exc:
            logger.warning("Failed to create concept reference from cluster: %s", exc)

    return updated_cluster.model_dump()


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

@router.get("/health")
async def triage_health() -> dict:
    """Return availability of CLIP and InsightFace dependencies.

    Returns:
        HealthResponse dict with clip_available, insightface_available,
        and clip_model_loaded flags.
    """
    from klippbok.services.triage_service import _embedder as current_embedder

    clip_available = check_clip_available_flag()
    insightface_available = check_insightface_available()
    clip_model_loaded = current_embedder is not None

    return {
        "clip_available": clip_available,
        "insightface_available": insightface_available,
        "clip_model_loaded": clip_model_loaded,
    }
