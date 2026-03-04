"""Captions router -- batch generation with SSE progress, single-image PATCH, batch tag ops, scoring, and provider config.

Endpoints:
    POST /captions/generate         -- Start batch caption generation, returns op_id.
    GET  /captions/{op_id}/events   -- SSE stream for generation progress.
    GET  /captions/config           -- Get caption provider configuration (with defaults).
    PUT  /captions/config           -- Save caption provider configuration to global config.
    GET  /captions/models           -- Fetch model list from provider.
    GET  /captions/health           -- Probe provider health.
    POST /captions/batch            -- Batch tag add/remove/replace/prepend_trigger.
    GET  /captions/scores           -- Get quality scores for all captioned images.
    PATCH /captions/{image_id}      -- Update a single image caption (inline edit).

Named SSE event types:
    "progress"      -- In-progress update (status="running")
    "done"          -- Generation completed (status="complete")
    "caption_error" -- Generation failed (status="error")
      "caption_error" is used instead of "error" to avoid collision with the
      browser EventSource built-in error event.

Route registration note:
    /config, /models, /health, /batch, /scores MUST be registered BEFORE the
    /{image_id} PATCH route to prevent path parameter capture (per ROUTE-01).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from klippbok.api.models import (
    CaptionBatchRequest,
    CaptionBatchResponse,
    CaptionGenerateRequest,
    CaptionProgress,
    CaptionProviderConfig,
    CaptionScoreResponse,
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
        if body.provider_preset is not None:
            # provider_preset takes priority -- resolve from global config
            from klippbok.services.caption_service import build_vlm_config_from_global
            from klippbok.services.global_config_service import load_global_config
            global_cfg = load_global_config()
            vlm_config = build_vlm_config_from_global(body.provider_preset, global_cfg, manifest)
        elif body.provider is not None:
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


@router.post("/batch", response_model=CaptionBatchResponse)
async def batch_caption_operation(
    body: CaptionBatchRequest,
    request: Request,
) -> CaptionBatchResponse:
    """Apply a batch tag operation across all (or selected) image captions.

    Supports four operations:
    - ``add_tag``: Append a tag to every caption that doesn't already have it.
    - ``remove_tag``: Remove a tag from every caption that contains it.
    - ``replace_tag``: Replace one tag with another across all captions
      (requires ``replace_with`` field).
    - ``prepend_trigger``: Prepend a trigger word using ``_prepend_anchor``
      logic (skips captions already starting with the trigger).

    All modifications are written to both the manifest and sidecar .txt files.

    Args:
        body: Batch operation parameters.
        request: FastAPI request (used to access app.state.project_dir).

    Returns:
        CaptionBatchResponse with the operation name and count of modified captions.

    Raises:
        HTTPException 409: If no project directory is selected.
        HTTPException 400: If ``replace_tag`` is requested without ``replace_with``.
        HTTPException 500: If the manifest cannot be loaded or saved.
    """
    import json
    from datetime import datetime, timezone

    from klippbok.services.caption_service import (
        batch_add_tag,
        batch_prepend_trigger,
        batch_remove_tag,
        batch_replace_tag,
    )
    from klippbok.services.project_service import MANIFEST_DIR, MANIFEST_FILE, load_manifest

    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    if body.operation == "replace_tag" and body.replace_with is None:
        raise HTTPException(
            status_code=400,
            detail="'replace_with' is required for 'replace_tag' operation",
        )

    try:
        manifest = load_manifest(project_dir)
    except Exception as exc:
        logger.error("Failed to load manifest for batch operation: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load project manifest") from exc

    if not manifest or "images" not in manifest:
        return CaptionBatchResponse(operation=body.operation, modified_count=0)

    if body.operation == "add_tag":
        count = batch_add_tag(body.value, manifest, project_dir, body.image_ids)
    elif body.operation == "remove_tag":
        count = batch_remove_tag(body.value, manifest, project_dir, body.image_ids)
    elif body.operation == "replace_tag":
        count = batch_replace_tag(
            body.value, body.replace_with or "", manifest, project_dir, body.image_ids
        )
    elif body.operation == "prepend_trigger":
        count = batch_prepend_trigger(body.value, manifest, project_dir, body.image_ids)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown operation: {body.operation}")

    # Persist updated manifest to disk
    try:
        manifest["updated"] = datetime.now(timezone.utc).isoformat()
        manifest_path = project_dir / MANIFEST_DIR / MANIFEST_FILE
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        logger.error("Failed to persist manifest after batch operation: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Batch operation applied but manifest save failed: {exc}",
        ) from exc

    logger.info(
        "Batch operation '%s' on project %s: %d captions modified",
        body.operation, project_dir, count,
    )
    return CaptionBatchResponse(operation=body.operation, modified_count=count)


@router.get("/scores", response_model=list[CaptionScoreResponse])
async def get_caption_scores(request: Request) -> list[CaptionScoreResponse]:
    """Get caption quality scores for all captioned images in the project.

    Scores each caption using IMAGE_SCORING_CONFIG — tuned for short booru-style
    tags and brief natural language image captions. Temporal scoring is disabled
    (not relevant for still images).

    Args:
        request: FastAPI request (used to access app.state.project_dir).

    Returns:
        List of CaptionScoreResponse, one per image that has a caption.
        Sorted by overall score, worst first (most needing attention at top).

    Raises:
        HTTPException 409: If no project directory is selected.
        HTTPException 500: If the manifest cannot be loaded.
    """
    import hashlib

    from klippbok.caption.scoring import IMAGE_SCORING_CONFIG, score_caption
    from klippbok.services.project_service import load_manifest

    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    try:
        manifest = load_manifest(project_dir)
    except Exception as exc:
        logger.error("Failed to load manifest for scoring: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load project manifest") from exc

    if not manifest or "images" not in manifest:
        return []

    results: list[CaptionScoreResponse] = []
    for entry in manifest["images"]:
        caption: str | None = entry.get("caption")
        if not caption:
            continue

        relative_path: str = entry.get("path", "")
        image_id = hashlib.sha256(relative_path.encode()).hexdigest()[:16]

        score = score_caption(caption, IMAGE_SCORING_CONFIG)
        results.append(CaptionScoreResponse(
            image_id=image_id,
            caption=caption,
            overall=score.overall,
            length_score=score.length_score,
            specificity_score=score.specificity_score,
            issues=score.issues,
        ))

    # Sort worst-first for easy review
    results.sort(key=lambda r: r.overall)
    return results


@router.get("/config", response_model=CaptionProviderConfig)
async def get_caption_config() -> CaptionProviderConfig:
    """Get the current caption provider configuration.

    Reads from ~/.klippbok/config.json and returns a CaptionProviderConfig
    with defaults for any fields not yet saved.

    Returns:
        CaptionProviderConfig with current settings (defaults when absent).
    """
    from klippbok.services.global_config_service import load_global_config

    cfg = load_global_config()

    # Auto-detect JoyCaption path if not explicitly configured
    joycaption_path = cfg.get("joycaption_path", "")
    if not joycaption_path:
        try:
            from klippbok.caption.joycaption import detect_joycaption

            detected = detect_joycaption()
            if detected is not None:
                joycaption_path = str(detected)
        except Exception:
            pass

    return CaptionProviderConfig(
        provider=cfg.get("provider", "lm_studio"),
        lm_studio_base_url=cfg.get("lm_studio_base_url", "http://localhost:1234/v1"),
        lm_studio_model=cfg.get("lm_studio_model", ""),
        nanogpt_api_key=cfg.get("nanogpt_api_key", ""),
        nanogpt_model=cfg.get("nanogpt_model", ""),
        gemini_api_key=cfg.get("gemini_api_key", ""),
        gemini_model=cfg.get("gemini_model", "gemini-2.5-flash"),
        joycaption_path=joycaption_path,
        custom_prompt=cfg.get("custom_prompt"),
    )


@router.put("/config", response_model=CaptionProviderConfig)
async def save_caption_config(body: CaptionProviderConfig) -> CaptionProviderConfig:
    """Save caption provider configuration to the global config file.

    Writes the provided settings to ~/.klippbok/config.json using atomic write.
    Returns the saved configuration.

    Args:
        body: Caption provider settings to persist.

    Returns:
        The saved CaptionProviderConfig (mirrors the input after save).
    """
    from klippbok.services.global_config_service import load_global_config, save_global_config

    # Load existing config and merge (preserve fields not managed by this endpoint)
    existing = load_global_config()
    existing.update({
        "provider": body.provider,
        "lm_studio_base_url": body.lm_studio_base_url,
        "lm_studio_model": body.lm_studio_model,
        "nanogpt_api_key": body.nanogpt_api_key,
        "nanogpt_model": body.nanogpt_model,
        "gemini_api_key": body.gemini_api_key,
        "gemini_model": body.gemini_model,
        "joycaption_path": body.joycaption_path,
        "custom_prompt": body.custom_prompt,
    })

    save_global_config(existing)
    logger.info("Saved caption provider config: provider=%s", body.provider)
    return body


@router.get("/models")
async def get_caption_models(provider: str = "lm_studio") -> dict:
    """Fetch the available models for a caption provider.

    Returns a list of model IDs for the specified provider. For local providers
    (LM Studio), makes an HTTP request. For API providers, returns a static list.

    Args:
        provider: Provider name: 'lm_studio' | 'nanogpt' | 'gemini' | 'joycaption'.

    Returns:
        Dict with 'models' list and optional 'message' for warnings.
    """
    import requests
    from klippbok.services.global_config_service import load_global_config

    cfg = load_global_config()

    if provider == "lm_studio":
        base_url = cfg.get("lm_studio_base_url", "http://localhost:1234/v1")
        try:
            resp = requests.get(f"{base_url}/models", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            models = [item["id"] for item in data.get("data", [])]
            return {"models": models}
        except requests.exceptions.ConnectionError:
            return {
                "models": [],
                "message": f"Could not connect to LM Studio at {base_url}. Is it running?",
            }
        except Exception as exc:
            logger.warning("Failed to fetch LM Studio models: %s", exc)
            return {"models": [], "message": str(exc)}

    elif provider == "nanogpt":
        api_key = cfg.get("nanogpt_api_key", "")
        if not api_key:
            return {"models": [], "message": "NanoGPT API key not configured."}
        try:
            resp = requests.get(
                "https://nano-gpt.com/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                params={"detailed": "true"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            # Log response shape on first call for debugging
            logger.debug("NanoGPT /models response keys: %s", list(data.keys()) if isinstance(data, dict) else type(data).__name__)
            if isinstance(data, dict) and "data" in data:
                models = [item["id"] for item in data["data"] if isinstance(item, dict)]
            elif isinstance(data, list):
                models = [item["id"] for item in data if isinstance(item, dict)]
            else:
                models = []
            return {"models": models}
        except Exception as exc:
            logger.warning("Failed to fetch NanoGPT models: %s", exc)
            return {"models": [], "message": str(exc)}

    elif provider == "gemini":
        return {
            "models": ["gemini-2.5-flash", "gemini-2.0-flash"],
        }

    elif provider == "joycaption":
        return {
            "models": ["fancyfeast/llama-joycaption-beta-one-hf-llava"],
        }

    else:
        return {"models": [], "message": f"Unknown provider: {provider}"}


@router.get("/health")
async def get_caption_health(provider: str = "lm_studio") -> dict:
    """Probe provider health/connectivity.

    For local providers (LM Studio), makes a lightweight HTTP request.
    For API-based providers, returns healthy immediately (no local check needed).

    Args:
        provider: Provider name: 'lm_studio' | 'nanogpt' | 'gemini' | 'joycaption'.

    Returns:
        Dict with 'healthy' bool and 'message' string.
    """
    import requests
    from klippbok.services.global_config_service import load_global_config

    cfg = load_global_config()

    if provider == "lm_studio":
        base_url = cfg.get("lm_studio_base_url", "http://localhost:1234/v1")
        try:
            resp = requests.get(f"{base_url}/models", timeout=3)
            resp.raise_for_status()
            return {"healthy": True, "message": f"LM Studio is reachable at {base_url}"}
        except requests.exceptions.ConnectionError:
            return {
                "healthy": False,
                "message": f"Cannot connect to LM Studio at {base_url}. Is it running?",
            }
        except Exception as exc:
            return {"healthy": False, "message": str(exc)}
    else:
        # API-based providers (nanogpt, gemini, joycaption) don't need local health checks
        return {"healthy": True, "message": "API-based provider — no local health check needed."}


@router.get("/default-prompt")
async def get_default_prompt(use_case: str | None = None) -> dict:
    """Return the default prompt template for a given use case.

    This lets the frontend show users what prompt will be used when
    custom_prompt is left blank.

    Args:
        use_case: One of 'character', 'style', 'motion', 'object', or None.

    Returns:
        Dict with 'prompt' string.
    """
    from klippbok.caption.prompts import IMAGE_PROMPTS

    template = IMAGE_PROMPTS.get(use_case, IMAGE_PROMPTS[None])
    # Strip template placeholders for display — they'll be filled at generation time
    clean = (
        template
        .replace("{anchor_line}", "")
        .replace("{secondary_line}", "")
        .replace("{style_anchor_line}", "")
        .replace("{subject}", "[trigger word]")
    )
    return {"prompt": clean.strip()}


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
