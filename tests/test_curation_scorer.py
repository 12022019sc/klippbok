"""Tests for klippbok.curation.scorer module.

All ML model singletons are mocked to return deterministic values.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from klippbok.curation.models import ImageScore, SignalScores
from klippbok.curation.scorer import mark_duplicates, normalize_score, rank_normalize, score_image


class TestNormalizeScore:
    """Tests for linear normalization to [0, 1]."""

    @pytest.mark.parametrize(
        "value,low,high,expected",
        [
            (5.0, 0.0, 10.0, 0.5),
            (0.0, 0.0, 10.0, 0.0),
            (10.0, 0.0, 10.0, 1.0),
            (-5.0, 0.0, 10.0, 0.0),   # below low -> clamp to 0
            (15.0, 0.0, 10.0, 1.0),   # above high -> clamp to 1
            (75.0, 50.0, 100.0, 0.5),
            (3.0, 3.0, 8.0, 0.0),     # at low boundary
            (8.0, 3.0, 8.0, 1.0),     # at high boundary
        ],
        ids=[
            "midrange", "at-low", "at-high",
            "below-low", "above-high",
            "custom-range", "low-boundary", "high-boundary",
        ],
    )
    def test_normalize(
        self, value: float, low: float, high: float, expected: float
    ) -> None:
        result = normalize_score(value, low, high)
        assert abs(result - expected) < 1e-6


class TestScoreImage:
    """Tests for score_image with mocked ML backends."""

    @pytest.fixture()
    def mock_ml_models(self, tmp_path: Path):
        """Set up mocked ML singletons that return deterministic values."""
        # Create a test image file
        from PIL import Image

        img_path = tmp_path / "test.jpg"
        img = Image.new("RGB", (512, 512), color=(128, 128, 128))
        img.save(img_path)

        # Mock cv2.imread to return a numpy array
        mock_cv2_img = np.full((512, 512, 3), 128, dtype=np.uint8)

        # Mock InsightFace face result
        mock_face = MagicMock()
        mock_face.det_score = 0.95
        mock_face.bbox = np.array([100, 100, 300, 300])  # x1,y1,x2,y2
        mock_face.pose = np.array([5.0, -3.0, 1.0])  # yaw, pitch, roll
        mock_face.normed_embedding = np.random.RandomState(42).randn(512).astype(np.float32)
        mock_face.normed_embedding /= np.linalg.norm(mock_face.normed_embedding)

        mock_face_app = MagicMock()
        mock_face_app.get.return_value = [mock_face]

        # Mock pyiqa model
        mock_pyiqa = MagicMock()
        mock_pyiqa.return_value = MagicMock(item=MagicMock(return_value=0.72))

        # Mock aesthetic model
        mock_aesthetic_model = MagicMock()
        mock_aesthetic_output = MagicMock()
        mock_aesthetic_output.logits = MagicMock()
        mock_aesthetic_output.logits.__getitem__ = MagicMock(
            return_value=MagicMock(item=MagicMock(return_value=6.5))
        )
        mock_aesthetic_model.return_value = mock_aesthetic_output

        mock_aesthetic_preproc = MagicMock()
        mock_aesthetic_preproc.return_value = {"pixel_values": MagicMock(to=MagicMock(return_value=MagicMock()))}

        # Mock CLIP embedder
        mock_embedder = MagicMock()
        mock_embedder.encode_image.return_value = np.ones(512, dtype=np.float32) / np.sqrt(512)
        mock_embedder.encode_text.return_value = np.ones(512, dtype=np.float32) / np.sqrt(512)

        mock_cv2 = MagicMock()
        mock_cv2.imread.return_value = mock_cv2_img
        mock_cv2.Laplacian.return_value = np.random.RandomState(42).randn(512, 512).astype(np.float64) * 30
        mock_cv2.cvtColor.return_value = np.full((512, 512), 128, dtype=np.uint8)
        mock_cv2.COLOR_BGR2GRAY = 6

        patches = [
            patch("klippbok.curation.scorer._get_face_app", return_value=mock_face_app),
            patch("klippbok.curation.scorer._get_pyiqa_model", return_value=mock_pyiqa),
            patch("klippbok.curation.scorer._get_aesthetic_model", return_value=(mock_aesthetic_model, mock_aesthetic_preproc)),
            patch("klippbok.curation.scorer._get_clip_embedder", return_value=mock_embedder),
            patch("klippbok.curation.scorer.cv2", mock_cv2),
        ]

        started = [p.start() for p in patches]

        yield img_path

        for p in patches:
            p.stop()

    def test_score_image_returns_all_signals(self, mock_ml_models: Path) -> None:
        """Verify ImageScore has non-default values for each signal."""
        result = score_image(mock_ml_models, mode="character")

        assert isinstance(result, ImageScore)
        assert result.image_id != ""
        assert result.relative_path != ""
        assert result.mode == "character"

        s = result.signals
        # Face signals should be populated (face was detected)
        assert s.face_confidence > 0.0
        assert s.face_area_ratio > 0.0
        # Technical/aesthetic signals
        assert s.quality_score >= 0.0
        assert s.aesthetic_score >= 0.0
        assert s.sharpness_whole >= 0.0

    def test_mode_weights(self, mock_ml_models: Path) -> None:
        """Score same image in Character and Style mode, verify different composites."""
        char_score = score_image(mock_ml_models, mode="character")
        style_score = score_image(mock_ml_models, mode="style")

        assert char_score.composite_score != style_score.composite_score
        assert char_score.mode == "character"
        assert style_score.mode == "style"

    def test_score_breakdown(self, mock_ml_models: Path) -> None:
        """Verify all signal fields are float in [0, 1]."""
        result = score_image(mock_ml_models, mode="character")
        s = result.signals

        for field_name in [
            "face_confidence", "face_area_ratio", "identity_similarity",
            "quality_score", "aesthetic_score", "sharpness_whole",
            "sharpness_face", "occlusion_score",
        ]:
            val = getattr(s, field_name)
            assert isinstance(val, float), f"{field_name} is not float"
            assert 0.0 <= val <= 1.0, f"{field_name}={val} not in [0,1]"

    def test_no_face_handling(self, tmp_path: Path) -> None:
        """Mock InsightFace returning empty faces list, verify face scores are 0.0."""
        from PIL import Image

        img_path = tmp_path / "noface.jpg"
        img = Image.new("RGB", (256, 256), color=(200, 200, 200))
        img.save(img_path)

        mock_face_app = MagicMock()
        mock_face_app.get.return_value = []  # no faces

        mock_pyiqa = MagicMock()
        mock_pyiqa.return_value = MagicMock(item=MagicMock(return_value=0.5))

        mock_aesthetic_model = MagicMock()
        mock_aesthetic_output = MagicMock()
        mock_aesthetic_output.logits = MagicMock()
        mock_aesthetic_output.logits.__getitem__ = MagicMock(
            return_value=MagicMock(item=MagicMock(return_value=5.0))
        )
        mock_aesthetic_model.return_value = mock_aesthetic_output
        mock_aesthetic_preproc = MagicMock()
        mock_aesthetic_preproc.return_value = {"pixel_values": MagicMock(to=MagicMock(return_value=MagicMock()))}

        mock_embedder = MagicMock()
        mock_embedder.encode_image.return_value = np.ones(512, dtype=np.float32) / np.sqrt(512)
        mock_embedder.encode_text.return_value = np.ones(512, dtype=np.float32) / np.sqrt(512)

        with (
            patch("klippbok.curation.scorer._get_face_app", return_value=mock_face_app),
            patch("klippbok.curation.scorer._get_pyiqa_model", return_value=mock_pyiqa),
            patch("klippbok.curation.scorer._get_aesthetic_model", return_value=(mock_aesthetic_model, mock_aesthetic_preproc)),
            patch("klippbok.curation.scorer._get_clip_embedder", return_value=mock_embedder),
            patch("klippbok.curation.scorer.cv2") as mock_cv2,
        ):
            mock_cv2.imread.return_value = np.full((256, 256, 3), 200, dtype=np.uint8)
            mock_cv2.Laplacian.return_value = np.random.RandomState(1).randn(256, 256) * 20

            result = score_image(img_path, mode="character")

        assert result.signals.face_confidence == 0.0
        assert result.signals.face_area_ratio == 0.0
        assert result.signals.identity_similarity == 0.0
        assert result.signals.sharpness_face == 0.0


class TestSharpnessNormalization:
    """Verify sharpness normalization uses correct range (10-500)."""

    def test_laplacian_30_produces_nonzero_score(self) -> None:
        """A Laplacian variance of 30 (slightly blurry) should not be zero."""
        result = normalize_score(30.0, 10.0, 500.0)
        assert result > 0.0
        assert result == pytest.approx((30.0 - 10.0) / (500.0 - 10.0))

    def test_laplacian_250_produces_midrange_score(self) -> None:
        """A Laplacian variance of 250 (normal frame) should score ~0.49."""
        result = normalize_score(250.0, 10.0, 500.0)
        assert 0.4 < result < 0.6

    def test_laplacian_500_plus_scores_one(self) -> None:
        """A Laplacian variance >= 500 should score 1.0."""
        assert normalize_score(500.0, 10.0, 500.0) == pytest.approx(1.0)
        assert normalize_score(1000.0, 10.0, 500.0) == pytest.approx(1.0)

    def test_laplacian_below_10_scores_zero(self) -> None:
        """A Laplacian variance below 10 (extremely blurry) should score 0.0."""
        assert normalize_score(5.0, 10.0, 500.0) == pytest.approx(0.0)


class TestRankNormalize:
    """Tests for percentile rank normalization."""

    def _make_score(self, **signal_kwargs: float) -> ImageScore:
        """Helper: create ImageScore with specific signal values."""
        signals = SignalScores(**signal_kwargs)
        return ImageScore(
            image_id="test",
            relative_path="test.jpg",
            signals=signals,
            composite_score=0.5,
            mode="character",
        )

    def test_single_image_gets_max_rank(self) -> None:
        """Single image should get rank 1.0 on all dimensions."""
        scores = [self._make_score(face_confidence=0.3, quality_score=0.7)]
        rank_normalize(scores)
        assert scores[0].ranked_signals.face_confidence == pytest.approx(1.0)
        assert scores[0].ranked_signals.quality_score == pytest.approx(1.0)

    def test_two_images_rank_ordering(self) -> None:
        """Higher raw value should get higher rank."""
        scores = [
            self._make_score(quality_score=0.2),
            self._make_score(quality_score=0.8),
        ]
        scores[0].image_id = "a"
        scores[1].image_id = "b"
        rank_normalize(scores)
        assert scores[0].ranked_signals.quality_score == pytest.approx(0.0)
        assert scores[1].ranked_signals.quality_score == pytest.approx(1.0)

    def test_ties_get_averaged_rank(self) -> None:
        """Tied values should get the same (averaged) rank."""
        scores = [
            self._make_score(aesthetic_score=0.5),
            self._make_score(aesthetic_score=0.5),
            self._make_score(aesthetic_score=0.9),
        ]
        for i, s in enumerate(scores):
            s.image_id = str(i)
        rank_normalize(scores)
        # Two tied at 0.5 share rank positions 1 and 2 → avg rank 1.5
        # Normalized: (1.5 - 1) / (3 - 1) = 0.25
        assert scores[0].ranked_signals.aesthetic_score == pytest.approx(0.25)
        assert scores[1].ranked_signals.aesthetic_score == pytest.approx(0.25)
        assert scores[2].ranked_signals.aesthetic_score == pytest.approx(1.0)

    def test_face_area_ratio_copied_not_ranked(self) -> None:
        """face_area_ratio should be copied as-is, not rank-normalized."""
        scores = [
            self._make_score(face_area_ratio=0.1),
            self._make_score(face_area_ratio=0.4),
        ]
        scores[0].image_id = "a"
        scores[1].image_id = "b"
        rank_normalize(scores)
        assert scores[0].ranked_signals.face_area_ratio == pytest.approx(0.1)
        assert scores[1].ranked_signals.face_area_ratio == pytest.approx(0.4)

    def test_five_images_uniform_distribution(self) -> None:
        """Five distinct values should produce evenly spaced ranks."""
        scores = [self._make_score(sharpness_whole=v) for v in [0.1, 0.3, 0.5, 0.7, 0.9]]
        for i, s in enumerate(scores):
            s.image_id = str(i)
        rank_normalize(scores)
        expected = [0.0, 0.25, 0.5, 0.75, 1.0]
        for s, exp in zip(scores, expected):
            assert s.ranked_signals.sharpness_whole == pytest.approx(exp)


class TestMarkDuplicatesGroups:
    """Tests for union-find dedup grouping."""

    def _make_score(self, image_id: str, composite: float) -> ImageScore:
        return ImageScore(
            image_id=image_id,
            relative_path=f"{image_id}.jpg",
            composite_score=composite,
            mode="character",
        )

    @patch("klippbok.curation.scorer.compute_phash")
    @patch("klippbok.curation.scorer.are_near_duplicates")
    def test_group_assignment(self, mock_dup, mock_hash, tmp_path):
        """Matching images should share a dedup_group_id."""
        scores = [self._make_score("a", 0.8), self._make_score("b", 0.6)]
        paths = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
        for p in paths:
            p.touch()
        mock_hash.side_effect = ["hash_a", "hash_b"]
        mock_dup.return_value = True

        mark_duplicates(scores, paths)

        assert scores[0].dedup_group_id is not None
        assert scores[0].dedup_group_id == scores[1].dedup_group_id

    @patch("klippbok.curation.scorer.compute_phash")
    @patch("klippbok.curation.scorer.are_near_duplicates")
    def test_highest_composite_kept(self, mock_dup, mock_hash, tmp_path):
        """Highest composite in group should be dedup_kept=True."""
        scores = [self._make_score("a", 0.8), self._make_score("b", 0.6)]
        paths = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
        for p in paths:
            p.touch()
        mock_hash.side_effect = ["hash_a", "hash_b"]
        mock_dup.return_value = True

        mark_duplicates(scores, paths)

        assert scores[0].dedup_kept is True   # higher composite
        assert scores[1].dedup_kept is False   # lower composite

    @patch("klippbok.curation.scorer.compute_phash")
    @patch("klippbok.curation.scorer.are_near_duplicates")
    def test_backwards_compat_is_duplicate(self, mock_dup, mock_hash, tmp_path):
        """Non-kept images should have signals.is_duplicate=True."""
        scores = [self._make_score("a", 0.8), self._make_score("b", 0.6)]
        paths = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
        for p in paths:
            p.touch()
        mock_hash.side_effect = ["hash_a", "hash_b"]
        mock_dup.return_value = True

        mark_duplicates(scores, paths)

        assert scores[0].signals.is_duplicate is False
        assert scores[1].signals.is_duplicate is True

    @patch("klippbok.curation.scorer.compute_phash")
    @patch("klippbok.curation.scorer.are_near_duplicates")
    def test_transitive_grouping(self, mock_dup, mock_hash, tmp_path):
        """A-B match + B-C match should group all three (transitive closure)."""
        scores = [
            self._make_score("a", 0.5),
            self._make_score("b", 0.9),
            self._make_score("c", 0.3),
        ]
        paths = [tmp_path / f"{x}.jpg" for x in "abc"]
        for p in paths:
            p.touch()
        mock_hash.side_effect = ["h1", "h2", "h3"]

        def dup_check(h1, h2, threshold=10):
            pair = frozenset([h1, h2])
            return pair in [frozenset(["h1", "h2"]), frozenset(["h2", "h3"])]
        mock_dup.side_effect = dup_check

        mark_duplicates(scores, paths)

        assert scores[0].dedup_group_id == scores[1].dedup_group_id == scores[2].dedup_group_id
        assert scores[1].dedup_kept is True
        assert scores[0].dedup_kept is False
        assert scores[2].dedup_kept is False

    @patch("klippbok.curation.scorer.compute_phash")
    @patch("klippbok.curation.scorer.are_near_duplicates")
    def test_unique_images_no_group(self, mock_dup, mock_hash, tmp_path):
        """Non-matching images should have no group."""
        scores = [self._make_score("a", 0.8), self._make_score("b", 0.6)]
        paths = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
        for p in paths:
            p.touch()
        mock_hash.side_effect = ["hash_a", "hash_b"]
        mock_dup.return_value = False

        mark_duplicates(scores, paths)

        assert scores[0].dedup_group_id is None
        assert scores[1].dedup_group_id is None
        assert scores[0].dedup_kept is True
        assert scores[1].dedup_kept is True
