"""Diversity-maximizing subset selection using apricot FacilityLocation.

Selects a target number of images that maximize embedding spread across
CLIP visual, pose angle, and face identity dimensions. Supports pinned
IDs (always included) and excluded IDs (never included).
"""

from __future__ import annotations

import logging

import numpy as np

from klippbok.curation.models import ImageScore

logger = logging.getLogger(__name__)


def select_diverse_subset(
    scores: list[ImageScore],
    target_count: int,
    clip_embeddings: np.ndarray,
    pose_vectors: np.ndarray,
    face_embeddings: np.ndarray,
    pinned_ids: list[str] | None = None,
    excluded_ids: list[str] | None = None,
) -> list[str]:
    """Select a diverse subset of images using FacilityLocation.

    Concatenates L2-normalized CLIP, pose, and face embeddings, computes
    a cosine similarity matrix, and uses apricot's greedy FacilityLocation
    to select the most diverse subset.

    Args:
        scores: List of ImageScore objects (parallel to embedding arrays).
        target_count: Desired number of images in the subset.
        clip_embeddings: (N, 512) CLIP visual embeddings.
        pose_vectors: (N, D) pose angle vectors (zero-padded to fixed dim).
        face_embeddings: (N, 512) face identity embeddings.
        pinned_ids: Image IDs always included in the result.
        excluded_ids: Image IDs never included in the result.

    Returns:
        List of selected image IDs (length == target_count when possible).
        Returns empty list if pool is empty after exclusion.
    """
    pinned_ids = pinned_ids or []
    excluded_ids = excluded_ids or []
    excluded_set = set(excluded_ids)
    pinned_set = set(pinned_ids)

    # Build filtered index: map from filtered position to original index
    filtered_indices: list[int] = []
    for i, score in enumerate(scores):
        if score.image_id not in excluded_set:
            filtered_indices.append(i)

    if not filtered_indices:
        return []

    # Separate pinned from selectable pool
    pinned_pool_indices: list[int] = []
    selectable_pool_indices: list[int] = []
    for idx in filtered_indices:
        if scores[idx].image_id in pinned_set:
            pinned_pool_indices.append(idx)
        else:
            selectable_pool_indices.append(idx)

    # Calculate how many to select (excluding pinned)
    adjusted_target = target_count - len(pinned_pool_indices)

    if adjusted_target <= 0:
        # Pinned alone meet or exceed target
        return [scores[i].image_id for i in pinned_pool_indices[:target_count]]

    if not selectable_pool_indices:
        # Only pinned available
        return [scores[i].image_id for i in pinned_pool_indices]

    # Clamp to available pool size
    adjusted_target = min(adjusted_target, len(selectable_pool_indices))

    # Extract and normalize embeddings for selectable pool
    sel_clip = _normalize_block(clip_embeddings[selectable_pool_indices])
    sel_pose = _normalize_block(pose_vectors[selectable_pool_indices])
    sel_face = _normalize_block(face_embeddings[selectable_pool_indices])

    # Concatenate embedding blocks
    combined = np.concatenate([sel_clip, sel_pose, sel_face], axis=1)

    # Compute cosine similarity matrix
    norms = np.linalg.norm(combined, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-8)
    normalized = combined / norms
    sim_matrix = normalized @ normalized.T

    # Clip to non-negative (FacilityLocation requires non-negative similarities)
    sim_matrix = np.clip(sim_matrix, 0.0, None)

    # Run FacilityLocation selection
    try:
        from apricot import FacilityLocationSelection

        selector = FacilityLocationSelection(
            n_samples=adjusted_target,
            metric="precomputed",
            optimizer="lazy",
        )
        selector.fit(sim_matrix)
        selected_pool_positions = list(selector.ranking)
    except ImportError:
        logger.warning("apricot-select not installed, falling back to random selection")
        rng = np.random.RandomState(42)
        selected_pool_positions = rng.choice(
            len(selectable_pool_indices),
            size=adjusted_target,
            replace=False,
        ).tolist()

    # Map back to image IDs
    selected_ids = [scores[pinned_pool_indices[i]].image_id for i in range(len(pinned_pool_indices))]
    for pos in selected_pool_positions:
        orig_idx = selectable_pool_indices[pos]
        selected_ids.append(scores[orig_idx].image_id)

    return selected_ids


def _normalize_block(embeddings: np.ndarray) -> np.ndarray:
    """L2-normalize each row of an embedding matrix.

    Args:
        embeddings: (N, D) embedding matrix.

    Returns:
        (N, D) L2-normalized matrix (rows have unit norm).
    """
    if embeddings.ndim == 1:
        embeddings = embeddings.reshape(1, -1)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-8)
    return embeddings / norms
