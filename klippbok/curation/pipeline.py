"""Curation pipeline orchestrator: score -> quality floor -> diversity select.

Chains multi-signal scoring from scorer.py, quality floor filtering,
and diversity-maximizing selection from diversity.py into a single pipeline.
Supports auto-detection of reference face via clustering, result persistence,
and re-diversification with pinned/excluded images.

Result persistence:
- CurationResult -> .klippbok/curation_results.json (Pydantic JSON)
- Embeddings -> .klippbok/curation_embeddings.npz (numpy arrays)
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from klippbok.curation.diversity import select_diverse_subset
from klippbok.curation.models import (
    CurationConfig,
    CurationResult,
    ImageScore,
    PipelineSummary,
)
from klippbok.curation.scorer import mark_duplicates, score_images
from klippbok.services.face_service import (
    cluster_face_embeddings,
    compute_face_embeddings,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_results(project_dir: Path, result: CurationResult) -> None:
    """Write CurationResult to .klippbok/curation_results.json.

    Args:
        project_dir: Project root directory.
        result: CurationResult to persist.
    """
    out_dir = project_dir / ".klippbok"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "curation_results.json"
    out_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Saved curation results to %s", out_path)


def load_results(project_dir: Path) -> CurationResult | None:
    """Load CurationResult from .klippbok/curation_results.json.

    Args:
        project_dir: Project root directory.

    Returns:
        CurationResult if file exists, None otherwise.
    """
    path = project_dir / ".klippbok" / "curation_results.json"
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8")
    return CurationResult.model_validate_json(raw)


def save_embeddings(
    project_dir: Path,
    clip: np.ndarray,
    pose: np.ndarray,
    face: np.ndarray,
    image_ids: list[str],
) -> None:
    """Save embedding arrays to .klippbok/curation_embeddings.npz.

    Args:
        project_dir: Project root directory.
        clip: (N, 512) CLIP visual embeddings.
        pose: (N, D) pose angle vectors.
        face: (N, 512) face identity embeddings.
        image_ids: Corresponding image IDs (same order).
    """
    out_dir = project_dir / ".klippbok"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "curation_embeddings.npz"
    np.savez(
        str(out_path),
        clip=clip,
        pose=pose,
        face=face,
        image_ids=np.array(image_ids, dtype=object),
    )
    logger.info("Saved curation embeddings to %s", out_path)


def load_embeddings(project_dir: Path) -> dict[str, np.ndarray] | None:
    """Load embedding arrays from .klippbok/curation_embeddings.npz.

    Args:
        project_dir: Project root directory.

    Returns:
        Dict with keys 'clip', 'pose', 'face', 'image_ids' as numpy arrays.
        Returns None if file doesn't exist.
    """
    path = project_dir / ".klippbok" / "curation_embeddings.npz"
    if not path.exists():
        return None
    data = np.load(str(path), allow_pickle=True)
    return {
        "clip": data["clip"],
        "pose": data["pose"],
        "face": data["face"],
        "image_ids": list(data["image_ids"]),
    }


# ---------------------------------------------------------------------------
# Auto-detect reference face
# ---------------------------------------------------------------------------


def _auto_detect_reference(
    image_paths: list[Path],
    project_dir: Path,
) -> tuple[np.ndarray | None, str | None]:
    """Auto-detect reference face from the largest face cluster.

    Computes face embeddings for all images, clusters them via DBSCAN,
    and returns the centroid of the largest cluster as the reference embedding.

    Args:
        image_paths: All images in the dataset.
        project_dir: Project root directory.

    Returns:
        (centroid_embedding, reference_image_id) from the largest cluster.
        (None, None) if no faces are found.
    """
    embeddings = compute_face_embeddings(image_paths)
    if not embeddings:
        logger.info("No faces detected in dataset; skipping reference auto-detection")
        return None, None

    clusters = cluster_face_embeddings(embeddings)
    if not clusters:
        logger.info("No face clusters formed; skipping reference auto-detection")
        return None, None

    # Find the largest cluster
    largest = max(clusters, key=lambda c: len(c.image_paths))
    logger.info(
        "Auto-detected reference face from cluster %d (%d images)",
        largest.cluster_id,
        len(largest.image_paths),
    )

    # Compute centroid of the cluster
    cluster_embeddings = np.array(
        [embeddings[p] for p in largest.image_paths if p in embeddings],
        dtype=np.float32,
    )
    centroid = cluster_embeddings.mean(axis=0)
    # L2-normalize the centroid
    norm = np.linalg.norm(centroid)
    if norm > 1e-8:
        centroid = centroid / norm

    # Pick the primary reference image ID
    ref_path = largest.primary_reference or largest.image_paths[0]
    ref_id = hashlib.sha256(ref_path.encode()).hexdigest()[:16]

    return centroid, ref_id


def _resolve_reference_embedding(
    config: CurationConfig,
    image_paths: list[Path],
    project_dir: Path,
) -> np.ndarray | None:
    """Resolve the reference face embedding for identity scoring.

    If config.reference_image_id is set, look up that image's face embedding.
    If None and mode is "character", auto-detect from the largest face cluster.

    Args:
        config: Curation configuration (may be mutated to set reference_image_id).
        image_paths: All images in the dataset.
        project_dir: Project root directory.

    Returns:
        Reference face embedding array, or None if not applicable.
    """
    if config.reference_image_id is not None:
        # Look up the specific image's face embedding
        for path in image_paths:
            img_id = hashlib.sha256(str(path).encode()).hexdigest()[:16]
            if img_id == config.reference_image_id:
                embs = compute_face_embeddings([path])
                if embs:
                    return next(iter(embs.values()))
                break
        return None

    if config.mode == "character":
        centroid, ref_id = _auto_detect_reference(image_paths, project_dir)
        if ref_id is not None:
            config.reference_image_id = ref_id
        return centroid

    return None


# ---------------------------------------------------------------------------
# Embedding gathering
# ---------------------------------------------------------------------------


def _gather_embeddings(
    scores: list[ImageScore],
    image_paths: list[Path],
    score_to_path: dict[str, Path],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Gather CLIP, pose, and face embeddings for scored images.

    Args:
        scores: List of scored images.
        image_paths: Original image paths.
        score_to_path: Mapping from image_id to path.

    Returns:
        (clip_embeddings, pose_vectors, face_embeddings) numpy arrays,
        each with shape (N, D) matching the scores list order.
    """
    from klippbok.curation.scorer import _get_clip_embedder, _get_face_app

    n = len(scores)

    # CLIP embeddings
    embedder = _get_clip_embedder()
    paths_for_clip = [score_to_path.get(s.image_id, Path("missing")) for s in scores]
    clip_list = embedder.encode_images(paths_for_clip)
    clip_embs = np.array(clip_list, dtype=np.float32) if clip_list else np.zeros((n, 512), dtype=np.float32)

    # Pose vectors from signal scores
    pose_dim = 20  # fixed dimension for pose vectors
    pose_list = []
    for s in scores:
        pv = s.signals.pose_vector
        if len(pv) < pose_dim:
            pv = pv + [0.0] * (pose_dim - len(pv))
        pose_list.append(pv[:pose_dim])
    pose_embs = np.array(pose_list, dtype=np.float32)

    # Face embeddings
    import cv2
    face_app = _get_face_app()
    face_list = []
    for s in scores:
        path = score_to_path.get(s.image_id)
        emb = np.zeros(512, dtype=np.float32)
        if path and path.exists():
            try:
                img_bgr = cv2.imread(str(path))
                if img_bgr is not None:
                    faces = face_app.get(img_bgr)
                    if faces:
                        best = max(faces, key=lambda f: f.det_score)
                        if hasattr(best, "normed_embedding"):
                            emb = best.normed_embedding.astype(np.float32)
            except Exception:
                pass
        face_list.append(emb)
    face_embs = np.array(face_list, dtype=np.float32)

    return clip_embs, pose_embs, face_embs


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_curation(
    image_paths: list[Path],
    project_dir: Path,
    config: CurationConfig,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> CurationResult:
    """Run the full curation pipeline: score -> quality floor -> diversity select.

    Args:
        image_paths: List of image file paths to evaluate.
        project_dir: Project root directory (for persistence).
        config: Curation configuration.
        progress_callback: Optional callable(stage, current, total) for progress.

    Returns:
        CurationResult with scores, selected IDs, and pipeline summary.
    """
    total = len(image_paths)

    # 1. Resolve reference embedding
    reference_embedding = _resolve_reference_embedding(config, image_paths, project_dir)

    # 2. Score all images
    if progress_callback:
        progress_callback("scoring", 0, total)

    def scoring_progress(current: int, total: int) -> None:
        if progress_callback:
            progress_callback("scoring", current, total)

    all_scores = score_images(image_paths, config.mode, reference_embedding, scoring_progress)

    # 3. Mark duplicates
    mark_duplicates(all_scores, image_paths)

    # Build score-to-path mapping
    score_to_path: dict[str, Path] = {}
    for score, path in zip(all_scores, image_paths):
        score_to_path[score.image_id] = path

    # 4. Quality floor: remove bottom N% by composite score AND duplicates
    composites = np.array([s.composite_score for s in all_scores])
    if len(composites) > 0 and config.quality_floor_pct > 0:
        cutoff = float(np.percentile(composites, config.quality_floor_pct * 100))
    else:
        cutoff = 0.0

    passed_scores = [
        s for s in all_scores
        if s.composite_score >= cutoff and not s.signals.is_duplicate
    ]

    # 5. Gather embeddings for passed images
    if progress_callback:
        progress_callback("selecting", 0, 1)

    clip_embs, pose_embs, face_embs = _gather_embeddings(
        passed_scores, image_paths, score_to_path,
    )

    # 6. Diversity selection
    selected_ids = select_diverse_subset(
        passed_scores,
        config.target_count,
        clip_embs,
        pose_embs,
        face_embs,
        pinned_ids=config.diversity_weights and [],
        excluded_ids=[],
    )

    # 7. Build result
    scores_dict = {s.image_id: s for s in all_scores}
    summary = PipelineSummary(
        total_scanned=total,
        passed_quality=len(passed_scores),
        selected=len(selected_ids),
    )

    result = CurationResult(
        config=config,
        scores=scores_dict,
        selected_ids=selected_ids,
        summary=summary,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # 8. Persist results and embeddings
    save_results(project_dir, result)

    # Save embeddings for rediversify (keyed by passed image IDs)
    passed_ids = [s.image_id for s in passed_scores]
    save_embeddings(project_dir, clip_embs, pose_embs, face_embs, passed_ids)

    if progress_callback:
        progress_callback("done", 1, 1)

    return result


# ---------------------------------------------------------------------------
# Rediversify
# ---------------------------------------------------------------------------


def rediversify(
    project_dir: Path,
    pinned_ids: list[str],
    excluded_ids: list[str],
    target_count: int | None = None,
) -> CurationResult:
    """Re-run diversity selection with new pins/excludes, reusing cached scores.

    Args:
        project_dir: Project root directory.
        pinned_ids: Image IDs to always include.
        excluded_ids: Image IDs to always exclude.
        target_count: Override target count (uses original if None).

    Returns:
        Updated CurationResult with new selection.

    Raises:
        FileNotFoundError: If no previous curation results exist.
    """
    result = load_results(project_dir)
    if result is None:
        raise FileNotFoundError("No curation results found to rediversify")

    emb_data = load_embeddings(project_dir)
    if emb_data is None:
        raise FileNotFoundError("No curation embeddings found for rediversify")

    tc = target_count if target_count is not None else result.config.target_count

    # Rebuild scores list from stored image_ids order in embeddings
    stored_ids = emb_data["image_ids"]
    scores_list = [result.scores[sid] for sid in stored_ids if sid in result.scores]

    # Filter embeddings to match available scores
    available_mask = [sid in result.scores for sid in stored_ids]
    clip_embs = emb_data["clip"][available_mask]
    pose_embs = emb_data["pose"][available_mask]
    face_embs = emb_data["face"][available_mask]

    selected_ids = select_diverse_subset(
        scores_list,
        tc,
        clip_embs,
        pose_embs,
        face_embs,
        pinned_ids=pinned_ids,
        excluded_ids=excluded_ids,
    )

    # Update result
    result.selected_ids = selected_ids
    result.pinned_ids = pinned_ids
    result.excluded_ids = excluded_ids
    result.summary.selected = len(selected_ids)

    save_results(project_dir, result)
    return result
