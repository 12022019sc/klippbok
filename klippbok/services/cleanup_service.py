"""Cleanup classification service -- ML-powered media filtering for subject relevance.

Uses a layered approach:
1. CLIP text-to-image classification (positive vs negative prompts)
2. InsightFace face detection (only on CLIP-positive items)

The combined score determines keep/review/remove classification.

Key design decisions:
- Reuses _get_or_create_embedder() singleton from triage_service (no model reload)
- Reuses _get_face_app() singleton from face_service (no model reload)
- Text prompts encoded ONCE before the image loop (anti-pattern avoidance)
- Files are NEVER deleted -- always moved to _review/ with audit log
- Separate threshold (0.25) from triage threshold (0.70) per locked decision

Exports: classify_item, classify_items, compute_confidence, confirm_removal,
         CleanupClassification, DEFAULT_CLEANUP_THRESHOLD
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

import cv2
import numpy as np
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_POSITIVE_PROMPTS: list[str] = [
    "photo of a woman",
    "portrait of a woman",
    "selfie of a woman",
    "photo of a person",
    "woman posing",
    "photo of a girl",
]

DEFAULT_NEGATIVE_PROMPTS: list[str] = [
    "screenshot",
    "meme",
    "text graphic",
    "landscape photo",
    "food photo",
    "product photo",
    "logo",
    "infographic",
]

DEFAULT_CLEANUP_THRESHOLD: float = 0.25

VIDEO_EXTENSIONS: set[str] = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

SIDECAR_EXTENSIONS: list[str] = [".txt", ".json", ".jsonl"]

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CleanupClassification(BaseModel):
    """Classification result for a single media item."""
    item_path: str
    item_id: str
    clip_score: float
    has_face: bool
    confidence: float
    label: Literal["keep", "review", "remove"]


# ---------------------------------------------------------------------------
# Score combination
# ---------------------------------------------------------------------------


def compute_confidence(clip_score: float, has_face: bool, clip_threshold: float) -> float:
    """Combine CLIP score and face detection into a single confidence value.

    Normalizes the CLIP score relative to the threshold range (0.10-0.40 maps
    to 0-1), adds a face boost (+0.3), and clamps to [0.0, 1.0].

    Args:
        clip_score: Net CLIP score (max_positive - max_negative).
        has_face: Whether a face was detected by InsightFace.
        clip_threshold: The CLIP threshold used for classification.

    Returns:
        Confidence score in [0.0, 1.0].
    """
    # Normalize CLIP score: map the range [low, high] to [0, 1]
    low = clip_threshold - 0.15
    high = clip_threshold + 0.15
    normalized = (clip_score - low) / (high - low) if high > low else 0.5
    normalized = max(0.0, min(1.0, normalized))

    # Face boost
    face_boost = 0.3 if has_face else 0.0

    confidence = normalized + face_boost
    return max(0.0, min(1.0, confidence))


def _classify_label(confidence: float) -> Literal["keep", "review", "remove"]:
    """Classify based on confidence thresholds.

    Args:
        confidence: Combined confidence score (0.0-1.0).

    Returns:
        "keep" if >= 0.6, "review" if >= 0.3, "remove" otherwise.
    """
    if confidence >= 0.6:
        return "keep"
    elif confidence >= 0.3:
        return "review"
    else:
        return "remove"


# ---------------------------------------------------------------------------
# Single-item classification
# ---------------------------------------------------------------------------


def classify_item(
    image_path: Path,
    embedder: Any,
    positive_embeddings: list[np.ndarray],
    negative_embeddings: list[np.ndarray],
    clip_threshold: float,
    face_app: Any | None,
) -> CleanupClassification:
    """Classify a single image using CLIP scores and optional face detection.

    The layered approach: CLIP first, InsightFace only on CLIP-positive items.

    Args:
        image_path: Path to the image file.
        embedder: CLIPEmbedder instance.
        positive_embeddings: Pre-encoded positive text prompt embeddings.
        negative_embeddings: Pre-encoded negative text prompt embeddings.
        clip_threshold: CLIP score threshold for triggering face detection.
        face_app: InsightFace FaceAnalysis app, or None to skip face detection.

    Returns:
        CleanupClassification with scores, face detection result, and label.
    """
    # Encode the image
    image_emb = embedder.encode_image(image_path)

    # Compute max positive and negative similarity scores
    max_pos = max(
        (float(np.dot(image_emb, p_emb)) for p_emb in positive_embeddings),
        default=0.0,
    )
    max_neg = max(
        (float(np.dot(image_emb, n_emb)) for n_emb in negative_embeddings),
        default=0.0,
    )

    clip_score = max_pos - max_neg

    # Layered approach: only run InsightFace if CLIP score is above threshold
    has_face = False
    if clip_score >= clip_threshold and face_app is not None:
        try:
            cv2_image = cv2.imread(str(image_path))
            if cv2_image is not None:
                faces = face_app.get(cv2_image)
                has_face = len(faces) > 0
        except Exception as exc:
            logger.warning("Face detection failed for %s: %s", image_path, exc)

    confidence = compute_confidence(clip_score, has_face, clip_threshold)
    label = _classify_label(confidence)

    # Compute item ID
    item_id = hashlib.sha256(str(image_path).encode()).hexdigest()[:16]

    return CleanupClassification(
        item_path=str(image_path),
        item_id=item_id,
        clip_score=clip_score,
        has_face=has_face,
        confidence=confidence,
        label=label,
    )


# ---------------------------------------------------------------------------
# Batch classification
# ---------------------------------------------------------------------------


def classify_items(
    item_paths: list[Path],
    project_dir: Path,
    positive_prompts: list[str] | None = None,
    negative_prompts: list[str] | None = None,
    clip_threshold: float = DEFAULT_CLEANUP_THRESHOLD,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[CleanupClassification]:
    """Classify a batch of media items using CLIP + optional InsightFace.

    Text prompts are encoded ONCE before the image loop. The CLIP embedder
    singleton is reused via _get_or_create_embedder(). InsightFace is only
    used if available.

    For video files, frames are sampled and the best score is used.

    Args:
        item_paths: List of image/video paths to classify.
        project_dir: Project root directory.
        positive_prompts: Text prompts for positive matching. Defaults to
            DEFAULT_POSITIVE_PROMPTS.
        negative_prompts: Text prompts for negative matching. Defaults to
            DEFAULT_NEGATIVE_PROMPTS.
        clip_threshold: CLIP score threshold. Default 0.25.
        progress_callback: Optional callable(current, total) per item.

    Returns:
        List of CleanupClassification, one per input path.
    """
    from klippbok.services.triage_service import _get_or_create_embedder
    from klippbok.services.face_service import check_insightface_available, _get_face_app

    pos_prompts = positive_prompts or DEFAULT_POSITIVE_PROMPTS
    neg_prompts = negative_prompts or DEFAULT_NEGATIVE_PROMPTS

    # Get CLIP embedder singleton
    embedder = _get_or_create_embedder()

    # Encode ALL text prompts ONCE (anti-pattern avoidance)
    positive_embeddings = embedder.encode_texts(pos_prompts)
    negative_embeddings = embedder.encode_texts(neg_prompts)

    # Check InsightFace availability
    face_app = None
    if check_insightface_available():
        try:
            face_app = _get_face_app()
        except Exception as exc:
            logger.warning("Failed to initialize InsightFace: %s", exc)

    total = len(item_paths)
    results: list[CleanupClassification] = []

    for i, item_path in enumerate(item_paths, 1):
        item_path = Path(item_path)
        suffix = item_path.suffix.lower()

        if suffix in VIDEO_EXTENSIONS:
            # Video: sample frames, classify each, use best score
            result = _classify_video(
                item_path, embedder, positive_embeddings, negative_embeddings,
                clip_threshold, face_app,
            )
        else:
            # Image: classify directly
            result = classify_item(
                item_path, embedder, positive_embeddings, negative_embeddings,
                clip_threshold, face_app,
            )

        results.append(result)

        if progress_callback is not None:
            progress_callback(i, total)

    return results


# ---------------------------------------------------------------------------
# Video classification (frame sampling)
# ---------------------------------------------------------------------------

# Lazy imports to avoid circular dependencies
sample_clip_frames = None
cleanup_frames = None


def _ensure_sampler_imports():
    """Lazily import frame sampling functions."""
    global sample_clip_frames, cleanup_frames
    if sample_clip_frames is None:
        from klippbok.triage.sampler import sample_clip_frames as _scf, cleanup_frames as _cf
        sample_clip_frames = _scf
        cleanup_frames = _cf


def _classify_video(
    video_path: Path,
    embedder: Any,
    positive_embeddings: list[np.ndarray],
    negative_embeddings: list[np.ndarray],
    clip_threshold: float,
    face_app: Any | None,
    num_frames: int = 3,
) -> CleanupClassification:
    """Classify a video by sampling frames and using the best CLIP score.

    Args:
        video_path: Path to the video file.
        embedder: CLIPEmbedder instance.
        positive_embeddings: Pre-encoded positive prompt embeddings.
        negative_embeddings: Pre-encoded negative prompt embeddings.
        clip_threshold: CLIP threshold.
        face_app: InsightFace app or None.
        num_frames: Number of frames to sample (default 3).

    Returns:
        CleanupClassification using the best frame's score.
    """
    _ensure_sampler_imports()

    try:
        frame_paths = sample_clip_frames(video_path, count=num_frames)
    except Exception as exc:
        logger.warning("Frame sampling failed for %s: %s", video_path, exc)
        frame_paths = []

    if not frame_paths:
        # No frames: treat as low-confidence remove
        item_id = hashlib.sha256(str(video_path).encode()).hexdigest()[:16]
        return CleanupClassification(
            item_path=str(video_path),
            item_id=item_id,
            clip_score=0.0,
            has_face=False,
            confidence=0.0,
            label="remove",
        )

    # Classify each frame
    best_result: CleanupClassification | None = None
    for frame_path in frame_paths:
        result = classify_item(
            frame_path, embedder, positive_embeddings, negative_embeddings,
            clip_threshold, face_app,
        )
        if best_result is None or result.clip_score > best_result.clip_score:
            best_result = result

    # Clean up temp frames
    try:
        cleanup_frames(frame_paths)
    except Exception:
        pass

    # Return best result but with original video path
    item_id = hashlib.sha256(str(video_path).encode()).hexdigest()[:16]
    return CleanupClassification(
        item_path=str(video_path),
        item_id=item_id,
        clip_score=best_result.clip_score,
        has_face=best_result.has_face,
        confidence=best_result.confidence,
        label=best_result.label,
    )


# ---------------------------------------------------------------------------
# Removal / file operations
# ---------------------------------------------------------------------------


def confirm_removal(
    project_dir: Path,
    item_paths: list[str],
) -> dict:
    """Move flagged files and sidecars to _review/ and update manifest.

    Never deletes files -- always moves to _review/ for manual review.
    Writes an audit log to _review/cleanup_log.json.

    Args:
        project_dir: Project root directory.
        item_paths: List of relative paths (from manifest) to move.

    Returns:
        {"moved": int, "review_dir": str} with count and review directory path.
    """
    review_dir = project_dir / "_review"
    review_dir.mkdir(parents=True, exist_ok=True)

    moved_count = 0
    log_entries: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for rel_path in item_paths:
        src = project_dir / rel_path
        if not src.exists():
            logger.warning("File not found for removal: %s", src)
            continue

        # Move primary file
        dest = review_dir / src.name
        shutil.move(str(src), str(dest))
        moved_count += 1

        log_entries.append({
            "source": rel_path,
            "dest": str(dest.relative_to(project_dir)),
            "timestamp": now,
        })

        # Move sidecar files (.txt, .json, .jsonl)
        for ext in SIDECAR_EXTENSIONS:
            sidecar = src.with_suffix(ext)
            if sidecar.exists():
                sidecar_dest = review_dir / sidecar.name
                shutil.move(str(sidecar), str(sidecar_dest))
                log_entries.append({
                    "source": str(sidecar.relative_to(project_dir)),
                    "dest": str(sidecar_dest.relative_to(project_dir)),
                    "timestamp": now,
                })

    # Update manifest: filter out removed paths
    manifest_path = project_dir / ".klippbok" / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        removed_set = set(item_paths)
        manifest["images"] = [
            entry for entry in manifest.get("images", [])
            if entry.get("path") not in removed_set
        ]
        manifest["updated"] = now
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    # Write/append audit log
    log_path = review_dir / "cleanup_log.json"
    existing_log: list[dict] = []
    if log_path.exists():
        try:
            existing_log = json.loads(log_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            pass

    existing_log.extend(log_entries)
    log_path.write_text(
        json.dumps(existing_log, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return {
        "moved": moved_count,
        "review_dir": str(review_dir),
    }
