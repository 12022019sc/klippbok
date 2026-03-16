"""Tests for klippbok.curation.diversity module.

Uses synthetic embeddings (random numpy arrays with known structure).
"""

from __future__ import annotations

import numpy as np
import pytest

from klippbok.curation.models import ImageScore, SignalScores
from klippbok.curation.diversity import select_diverse_subset


def _make_scores(n: int, seed: int = 42) -> list[ImageScore]:
    """Create n synthetic ImageScore objects with deterministic IDs."""
    rng = np.random.RandomState(seed)
    scores = []
    for i in range(n):
        scores.append(
            ImageScore(
                image_id=f"img_{i:04d}",
                relative_path=f"images/img_{i:04d}.jpg",
                signals=SignalScores(
                    face_confidence=rng.uniform(0.3, 1.0),
                    quality_score=rng.uniform(0.3, 1.0),
                    aesthetic_score=rng.uniform(0.3, 1.0),
                    sharpness_whole=rng.uniform(0.3, 1.0),
                ),
                composite_score=rng.uniform(0.3, 0.9),
                mode="character",
            )
        )
    return scores


def _make_embeddings(n: int, dim: int, seed: int = 42) -> np.ndarray:
    """Create n L2-normalized random embeddings."""
    rng = np.random.RandomState(seed)
    emb = rng.randn(n, dim).astype(np.float32)
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    return emb / np.maximum(norms, 1e-8)


class TestSelectDiverseSubset:
    """Tests for diversity selection via apricot FacilityLocation."""

    def test_select_target_count(self) -> None:
        """Verify exact count returned."""
        n = 20
        target = 8
        scores = _make_scores(n)
        clip_emb = _make_embeddings(n, 512, seed=1)
        pose_emb = _make_embeddings(n, 20, seed=2)
        face_emb = _make_embeddings(n, 512, seed=3)

        result = select_diverse_subset(
            scores=scores,
            target_count=target,
            clip_embeddings=clip_emb,
            pose_vectors=pose_emb,
            face_embeddings=face_emb,
        )

        assert len(result) == target
        # All returned IDs should be valid
        valid_ids = {s.image_id for s in scores}
        assert all(rid in valid_ids for rid in result)

    def test_pinned_ids_included(self) -> None:
        """Verify pinned IDs always in result."""
        n = 20
        target = 8
        scores = _make_scores(n)
        clip_emb = _make_embeddings(n, 512, seed=1)
        pose_emb = _make_embeddings(n, 20, seed=2)
        face_emb = _make_embeddings(n, 512, seed=3)

        pinned = ["img_0003", "img_0015"]

        result = select_diverse_subset(
            scores=scores,
            target_count=target,
            clip_embeddings=clip_emb,
            pose_vectors=pose_emb,
            face_embeddings=face_emb,
            pinned_ids=pinned,
        )

        assert len(result) == target
        for pid in pinned:
            assert pid in result

    def test_excluded_ids_absent(self) -> None:
        """Verify excluded IDs never in result."""
        n = 20
        target = 8
        scores = _make_scores(n)
        clip_emb = _make_embeddings(n, 512, seed=1)
        pose_emb = _make_embeddings(n, 20, seed=2)
        face_emb = _make_embeddings(n, 512, seed=3)

        excluded = ["img_0002", "img_0005", "img_0010"]

        result = select_diverse_subset(
            scores=scores,
            target_count=target,
            clip_embeddings=clip_emb,
            pose_vectors=pose_emb,
            face_embeddings=face_emb,
            excluded_ids=excluded,
        )

        assert len(result) == target
        for eid in excluded:
            assert eid not in result

    def test_rediversify_pins(self) -> None:
        """Pin 2 IDs, exclude 1, verify constraints hold."""
        n = 20
        target = 10
        scores = _make_scores(n)
        clip_emb = _make_embeddings(n, 512, seed=1)
        pose_emb = _make_embeddings(n, 20, seed=2)
        face_emb = _make_embeddings(n, 512, seed=3)

        pinned = ["img_0001", "img_0019"]
        excluded = ["img_0005"]

        result = select_diverse_subset(
            scores=scores,
            target_count=target,
            clip_embeddings=clip_emb,
            pose_vectors=pose_emb,
            face_embeddings=face_emb,
            pinned_ids=pinned,
            excluded_ids=excluded,
        )

        assert len(result) == target
        for pid in pinned:
            assert pid in result
        assert "img_0005" not in result

    def test_quality_weighting_prefers_high_quality(self) -> None:
        """High-quality images should be preferred over low-quality ones with similar diversity."""
        # Create 10 images: 5 high-quality (0.8-0.9), 5 low-quality (0.1-0.2)
        # All have similar random embeddings so diversity is roughly equal
        n = 10
        scores = []
        rng = np.random.RandomState(99)
        for i in range(n):
            quality = 0.85 if i < 5 else 0.15
            scores.append(
                ImageScore(
                    image_id=f"img_{i:04d}",
                    relative_path=f"images/img_{i:04d}.jpg",
                    signals=SignalScores(
                        face_confidence=rng.uniform(0.3, 1.0),
                        quality_score=quality,
                    ),
                    composite_score=quality,
                    mode="character",
                )
            )
        clip_emb = _make_embeddings(n, 512, seed=10)
        pose_emb = _make_embeddings(n, 20, seed=11)
        face_emb = _make_embeddings(n, 512, seed=12)

        result = select_diverse_subset(
            scores=scores,
            target_count=5,
            clip_embeddings=clip_emb,
            pose_vectors=pose_emb,
            face_embeddings=face_emb,
        )

        # Most selected should be high-quality (first 5 images)
        high_quality_selected = sum(1 for rid in result if int(rid.split("_")[1]) < 5)
        assert high_quality_selected >= 3, (
            f"Expected at least 3/5 high-quality images selected, got {high_quality_selected}"
        )

    def test_empty_pool(self) -> None:
        """Edge case with 0 images after exclusion."""
        scores = _make_scores(3)
        clip_emb = _make_embeddings(3, 512, seed=1)
        pose_emb = _make_embeddings(3, 20, seed=2)
        face_emb = _make_embeddings(3, 512, seed=3)

        excluded = ["img_0000", "img_0001", "img_0002"]

        result = select_diverse_subset(
            scores=scores,
            target_count=2,
            clip_embeddings=clip_emb,
            pose_vectors=pose_emb,
            face_embeddings=face_emb,
            excluded_ids=excluded,
        )

        assert result == []
