"""Tests for curation pipeline orchestrator.

Tests pipeline flow: score -> quality floor -> diversity select,
auto-reference face detection, persistence, and rediversify.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from klippbok.curation.models import (
    CurationConfig,
    CurationResult,
    ImageScore,
    PipelineSummary,
    SignalScores,
)


def _make_score(image_id: str, composite: float, is_dup: bool = False) -> ImageScore:
    """Helper to create an ImageScore with a specific composite value."""
    return ImageScore(
        image_id=image_id,
        relative_path=f"images/{image_id}.jpg",
        signals=SignalScores(
            face_confidence=composite,
            quality_score=composite,
            aesthetic_score=composite,
            sharpness_whole=composite,
            is_duplicate=is_dup,
        ),
        composite_score=composite,
        mode="character",
    )


class TestQualityFloor:
    """Quality floor filtering: bottom N% by composite score are removed."""

    def test_quality_floor_removes_bottom_30_pct(self, tmp_path: Path) -> None:
        """10 images with floor=0.3 -> bottom 30% removed -> 7 pass."""
        from klippbok.curation.pipeline import run_curation

        # Create 10 fake image files
        image_paths = []
        for i in range(10):
            p = tmp_path / f"img_{i:02d}.jpg"
            p.write_bytes(b"fake")
            image_paths.append(p)

        # Scores: 0.1, 0.2, 0.3, ..., 1.0
        scores = [_make_score(f"id{i:02d}", (i + 1) * 0.1) for i in range(10)]
        config = CurationConfig(mode="character", target_count=5, quality_floor_pct=0.3)

        # Mock all external dependencies
        with (
            patch("klippbok.curation.pipeline.score_images", return_value=scores),
            patch("klippbok.curation.pipeline.mark_duplicates"),
            patch("klippbok.curation.pipeline.select_diverse_subset",
                  side_effect=lambda scores, tc, clip, pose, face, **kw: [s.image_id for s in scores[:tc]]),
            patch("klippbok.curation.pipeline._resolve_reference_embedding", return_value=None),
            patch("klippbok.curation.pipeline._gather_embeddings",
                  return_value=(np.zeros((10, 512)), np.zeros((10, 20)), np.zeros((10, 512)))),
            patch("klippbok.curation.pipeline.save_results"),
            patch("klippbok.curation.pipeline.save_embeddings"),
        ):
            result = run_curation(image_paths, tmp_path, config)

        # Bottom 30% means images with composite <= 30th percentile are removed
        # 7 should pass quality floor
        assert result.summary.passed_quality == 7
        assert result.summary.total_scanned == 10

    def test_duplicates_removed_before_diversity(self, tmp_path: Path) -> None:
        """Duplicate-flagged images should be excluded from passed_quality count."""
        from klippbok.curation.pipeline import run_curation

        image_paths = []
        for i in range(5):
            p = tmp_path / f"img_{i}.jpg"
            p.write_bytes(b"fake")
            image_paths.append(p)

        # 5 images: 3 normal, 2 duplicates (one high-score dup still excluded)
        scores = [
            _make_score("id0", 0.9),
            _make_score("id1", 0.8),
            _make_score("id2", 0.7),
            _make_score("id3", 0.6, is_dup=True),
            _make_score("id4", 0.5, is_dup=True),
        ]
        config = CurationConfig(mode="character", target_count=3, quality_floor_pct=0.0)

        with (
            patch("klippbok.curation.pipeline.score_images", return_value=scores),
            patch("klippbok.curation.pipeline.mark_duplicates"),
            patch("klippbok.curation.pipeline.select_diverse_subset",
                  side_effect=lambda scores, tc, clip, pose, face, **kw: [s.image_id for s in scores[:tc]]),
            patch("klippbok.curation.pipeline._resolve_reference_embedding", return_value=None),
            patch("klippbok.curation.pipeline._gather_embeddings",
                  return_value=(np.zeros((5, 512)), np.zeros((5, 20)), np.zeros((5, 512)))),
            patch("klippbok.curation.pipeline.save_results"),
            patch("klippbok.curation.pipeline.save_embeddings"),
        ):
            result = run_curation(image_paths, tmp_path, config)

        # Dupes excluded: only 3 pass
        assert result.summary.passed_quality == 3


class TestSummaryStats:
    """Pipeline summary has correct funnel counts."""

    def test_summary_funnel_counts(self, tmp_path: Path) -> None:
        """Summary counts: total_scanned, passed_quality, selected match pipeline flow."""
        from klippbok.curation.pipeline import run_curation

        image_paths = []
        for i in range(10):
            p = tmp_path / f"img_{i}.jpg"
            p.write_bytes(b"fake")
            image_paths.append(p)

        scores = [_make_score(f"id{i}", (i + 1) * 0.1) for i in range(10)]
        config = CurationConfig(mode="character", target_count=4, quality_floor_pct=0.3)

        selected_ids = ["id03", "id04", "id05", "id06"]

        with (
            patch("klippbok.curation.pipeline.score_images", return_value=scores),
            patch("klippbok.curation.pipeline.mark_duplicates"),
            patch("klippbok.curation.pipeline.select_diverse_subset", return_value=selected_ids),
            patch("klippbok.curation.pipeline._resolve_reference_embedding", return_value=None),
            patch("klippbok.curation.pipeline._gather_embeddings",
                  return_value=(np.zeros((10, 512)), np.zeros((10, 20)), np.zeros((10, 512)))),
            patch("klippbok.curation.pipeline.save_results"),
            patch("klippbok.curation.pipeline.save_embeddings"),
        ):
            result = run_curation(image_paths, tmp_path, config)

        assert result.summary.total_scanned == 10
        assert result.summary.passed_quality == 7
        assert result.summary.selected == 4


class TestPersistence:
    """save_results / load_results round-trip."""

    def test_persistence_round_trip(self, tmp_path: Path) -> None:
        """Save then load CurationResult, verify fields preserved."""
        from klippbok.curation.pipeline import load_results, save_results

        result = CurationResult(
            config=CurationConfig(mode="style", target_count=50),
            scores={"abc123": _make_score("abc123", 0.85)},
            selected_ids=["abc123"],
            pinned_ids=[],
            excluded_ids=[],
            summary=PipelineSummary(total_scanned=100, passed_quality=70, selected=50),
            timestamp="2026-03-08T00:00:00Z",
        )

        save_results(tmp_path, result)
        loaded = load_results(tmp_path)

        assert loaded is not None
        assert loaded.config.mode == "style"
        assert loaded.config.target_count == 50
        assert loaded.summary.total_scanned == 100
        assert loaded.summary.passed_quality == 70
        assert loaded.summary.selected == 50
        assert "abc123" in loaded.scores
        assert loaded.scores["abc123"].composite_score == 0.85

    def test_load_results_returns_none_when_missing(self, tmp_path: Path) -> None:
        """load_results returns None if no file exists."""
        from klippbok.curation.pipeline import load_results

        assert load_results(tmp_path) is None

    def test_embeddings_round_trip(self, tmp_path: Path) -> None:
        """save_embeddings / load_embeddings preserves numpy arrays."""
        from klippbok.curation.pipeline import load_embeddings, save_embeddings

        clip = np.random.rand(5, 512).astype(np.float32)
        pose = np.random.rand(5, 20).astype(np.float32)
        face = np.random.rand(5, 512).astype(np.float32)
        ids = ["a", "b", "c", "d", "e"]

        save_embeddings(tmp_path, clip, pose, face, ids)
        loaded = load_embeddings(tmp_path)

        assert loaded is not None
        np.testing.assert_array_almost_equal(loaded["clip"], clip)
        np.testing.assert_array_almost_equal(loaded["pose"], pose)
        np.testing.assert_array_almost_equal(loaded["face"], face)
        assert list(loaded["image_ids"]) == ids


class TestAutoReference:
    """Auto-detect reference face from largest face cluster."""

    def test_auto_reference_picks_largest_cluster(self, tmp_path: Path) -> None:
        """With 2 clusters, auto-detect picks centroid from the largest."""
        from klippbok.curation.pipeline import _auto_detect_reference

        # Mock face_service functions
        emb_a = np.random.rand(512).astype(np.float32)
        emb_b = np.random.rand(512).astype(np.float32)
        emb_c = np.random.rand(512).astype(np.float32)

        embeddings = {
            "img1.jpg": emb_a,
            "img2.jpg": emb_a + 0.01,  # same cluster
            "img3.jpg": emb_a + 0.02,  # same cluster
            "img4.jpg": emb_b,          # different cluster (smaller)
        }

        # Cluster 0 has 3 images, cluster 1 has 1 image
        from klippbok.services.face_service import FaceCluster
        clusters = [
            FaceCluster(cluster_id=0, image_paths=["img1.jpg", "img2.jpg", "img3.jpg"]),
            FaceCluster(cluster_id=1, image_paths=["img4.jpg"]),
        ]

        paths = [tmp_path / f"img{i}.jpg" for i in range(4)]
        for p in paths:
            p.write_bytes(b"fake")

        with (
            patch("klippbok.curation.pipeline.compute_face_embeddings", return_value=embeddings),
            patch("klippbok.curation.pipeline.cluster_face_embeddings", return_value=clusters),
        ):
            centroid, ref_id = _auto_detect_reference(paths, tmp_path)

        # Should return a centroid (non-None) and an image_id from the largest cluster
        assert centroid is not None
        assert ref_id is not None

    def test_auto_reference_returns_none_when_no_faces(self, tmp_path: Path) -> None:
        """Returns (None, None) when no faces detected."""
        from klippbok.curation.pipeline import _auto_detect_reference

        paths = [tmp_path / "img.jpg"]
        paths[0].write_bytes(b"fake")

        with (
            patch("klippbok.curation.pipeline.compute_face_embeddings", return_value={}),
            patch("klippbok.curation.pipeline.cluster_face_embeddings", return_value=[]),
        ):
            centroid, ref_id = _auto_detect_reference(paths, tmp_path)

        assert centroid is None
        assert ref_id is None


class TestRediversify:
    """Re-run diversity selection with new pins/excludes."""

    def test_rediversify_updates_selected_ids(self, tmp_path: Path) -> None:
        """Rediversify loads results, re-runs diversity, updates selection."""
        from klippbok.curation.pipeline import rediversify, save_embeddings, save_results

        # Setup: save existing result and embeddings
        scores_dict = {f"id{i}": _make_score(f"id{i}", (i + 1) * 0.1) for i in range(10)}
        original_result = CurationResult(
            config=CurationConfig(mode="character", target_count=5),
            scores=scores_dict,
            selected_ids=["id5", "id6", "id7", "id8", "id9"],
            summary=PipelineSummary(total_scanned=10, passed_quality=10, selected=5),
            timestamp="2026-03-08T00:00:00Z",
        )
        save_results(tmp_path, original_result)

        clip = np.random.rand(10, 512).astype(np.float32)
        pose = np.random.rand(10, 20).astype(np.float32)
        face = np.random.rand(10, 512).astype(np.float32)
        ids = [f"id{i}" for i in range(10)]
        save_embeddings(tmp_path, clip, pose, face, ids)

        new_selected = ["id0", "id1", "id2", "id3", "id4"]

        with patch("klippbok.curation.pipeline.select_diverse_subset", return_value=new_selected):
            result = rediversify(
                tmp_path,
                pinned_ids=["id0"],
                excluded_ids=["id9"],
                target_count=5,
            )

        assert result.selected_ids == new_selected
        assert result.pinned_ids == ["id0"]
        assert result.excluded_ids == ["id9"]
