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
from klippbok.curation.scorer import _compute_composite, mark_duplicates, rank_normalize, score_images
from klippbok.services.face_service import (
    cluster_face_embeddings,
    compute_face_embeddings,
)
from klippbok.utils.paths import image_id, to_manifest_path

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
    ref_id = image_id(to_manifest_path(Path(ref_path), project_dir))

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
            img_id = image_id(to_manifest_path(path, project_dir))
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

    # Unload CLIP from GPU before face pass — must delete local ref too
    import gc
    import torch
    try:
        embedder._model.cpu()
    except Exception:
        pass
    del embedder
    from klippbok.curation import scorer as _scorer
    _scorer._clip_embedder = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # Face embeddings (with explicit memory cleanup per image)
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
                    del faces
                del img_bgr
            except Exception:
                pass
        face_list.append(emb)
    face_embs = np.array(face_list, dtype=np.float32)

    # Clean up face_app — no longer needed after embedding extraction
    del face_app
    _scorer._face_app = None
    try:
        from klippbok.services import face_service as _fs
        _fs._face_app = None
    except Exception:
        pass
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return clip_embs, pose_embs, face_embs


# ---------------------------------------------------------------------------
# Quality floor
# ---------------------------------------------------------------------------


def _apply_quality_floor(
    scores: list[ImageScore],
    config: CurationConfig,
) -> None:
    """Apply two-tier quality floor to scored images in-place.

    Hard floor: excludes images with raw_composite_score below config.hard_floor.
    Soft floor: flags images below the quality_floor_pct percentile of ranked
    composite scores (among non-hard-excluded images).

    Args:
        scores: List of ImageScore objects. Modified in-place.
        config: Curation configuration with hard_floor and quality_floor_pct.
    """
    # Hard floor: absolute exclusion based on raw composite
    for s in scores:
        if s.raw_composite_score < config.hard_floor:
            s.floor_status = "hard_floor"

    # Soft floor: advisory flag based on ranked composite percentile
    remaining = [s for s in scores if s.floor_status != "hard_floor"]
    if remaining and config.quality_floor_pct > 0:
        composites = np.array([s.composite_score for s in remaining])
        soft_cutoff = float(np.percentile(composites, config.quality_floor_pct * 100))
        for s in remaining:
            if s.composite_score < soft_cutoff:
                s.floor_status = "soft_floor"


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

    import gc
    import torch

    def _flush_gpu() -> None:
        """Force garbage collection and free GPU cache between heavy phases."""
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # 1. Resolve reference embedding
    reference_embedding = _resolve_reference_embedding(config, image_paths, project_dir)
    # Free face_service singleton loaded during auto-detection — scoring
    # creates its own lightweight InsightFace with only detection+recognition.
    try:
        from klippbok.services import face_service as _fs
        _fs._face_app = None
    except Exception:
        pass
    _flush_gpu()

    # 2. Score all images
    #    score_images reports progress as (step, total_steps) where
    #    total_steps = N_images * 5 phases.  Translate back to image scale
    #    so the frontend shows e.g. "scoring: 120/343" not "scoring: 600/1715".
    _NUM_SCORING_PHASES = 5
    if progress_callback:
        progress_callback("scoring", 0, total)

    def scoring_progress(current: int, _total_steps: int) -> None:
        if progress_callback:
            # Convert phase-level ticks to image-level progress
            image_progress = min(current // _NUM_SCORING_PHASES, total)
            progress_callback("scoring", image_progress, total)

    all_scores = score_images(image_paths, config.mode, reference_embedding, scoring_progress, project_dir=project_dir)

    _flush_gpu()

    # 3. Mark duplicates (union-find grouping)
    mark_duplicates(all_scores, image_paths)

    # 3b. Rank-normalize signals and recompute composite
    rank_normalize(all_scores)
    for s in all_scores:
        s.raw_composite_score = s.composite_score  # preserve raw
        s.composite_score = _compute_composite(s.ranked_signals, config.mode)

    # Build score-to-path mapping
    score_to_path: dict[str, Path] = {}
    for score, path in zip(all_scores, image_paths):
        score_to_path[score.image_id] = path

    # 4. Two-tier quality floor
    _apply_quality_floor(all_scores, config)

    # 4b. Character-mode gates: reject images without a usable face or wrong person.
    #     Uses raw signal values (pre-rank) so gates are absolute, not relative.
    identity_gated = 0
    if config.mode == "character":
        for s in all_scores:
            if s.floor_status == "hard_floor":
                continue  # already excluded
            if s.signals.face_confidence < config.face_confidence_threshold:
                s.floor_status = "hard_floor"
                identity_gated += 1
            elif s.signals.identity_similarity < config.identity_threshold:
                s.floor_status = "hard_floor"
                identity_gated += 1
        if identity_gated:
            logger.info(
                "Character gates excluded %d images (low face confidence or wrong identity)",
                identity_gated,
            )

    # 5. Build pool: exclude hard floor and dedup non-representatives
    passed_scores = [
        s for s in all_scores
        if s.floor_status != "hard_floor" and s.dedup_kept
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
        hard_excluded=sum(1 for s in all_scores if s.floor_status == "hard_floor"),
        soft_flagged=sum(1 for s in all_scores if s.floor_status == "soft_floor"),
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

    # Guard: drop pinned IDs not present in embeddings (hard-floor excluded
    # or dedup non-representatives don't have cached embeddings)
    stored_id_set = set(stored_ids)
    dropped_pins = [pid for pid in pinned_ids if pid not in stored_id_set]
    if dropped_pins:
        logger.warning(
            "Dropping %d pinned IDs not in embeddings (hard-floor or dedup non-rep): %s",
            len(dropped_pins), dropped_pins[:5],
        )
    valid_pinned = [pid for pid in pinned_ids if pid in stored_id_set]

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
        pinned_ids=valid_pinned,
        excluded_ids=excluded_ids,
    )

    # Update result
    result.selected_ids = selected_ids
    result.pinned_ids = pinned_ids
    result.excluded_ids = excluded_ids
    result.summary.selected = len(selected_ids)

    save_results(project_dir, result)
    return result
