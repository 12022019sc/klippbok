"""Tests for face_service — InsightFace face embedding and DBSCAN clustering.

All tests mock insightface and sklearn to avoid requiring them in CI.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# check_insightface_available
# ---------------------------------------------------------------------------

class TestCheckInsightfaceAvailable:
    def test_returns_false_when_insightface_not_installed(self):
        """check_insightface_available returns False when insightface is not importable."""
        from klippbok.services.face_service import check_insightface_available

        with patch("klippbok.services.face_service._INSIGHTFACE_AVAILABLE", False):
            result = check_insightface_available()

        assert result is False

    def test_returns_true_when_insightface_installed(self):
        """check_insightface_available returns True when insightface is importable."""
        from klippbok.services.face_service import check_insightface_available

        with patch("klippbok.services.face_service._INSIGHTFACE_AVAILABLE", True):
            result = check_insightface_available()

        assert result is True


# ---------------------------------------------------------------------------
# compute_face_embeddings
# ---------------------------------------------------------------------------

class TestComputeFaceEmbeddings:
    def test_returns_dict_of_path_to_embedding(self, tmp_path):
        """compute_face_embeddings returns {path_str: embedding_array} for detected faces."""
        from klippbok.services.face_service import compute_face_embeddings

        img1 = tmp_path / "face1.jpg"
        img2 = tmp_path / "face2.jpg"
        img1.write_bytes(b"FAKE1")
        img2.write_bytes(b"FAKE2")

        mock_face = MagicMock()
        mock_face.det_score = 0.95
        mock_face.normed_embedding = np.ones(512, dtype=np.float32)

        with (
            patch("klippbok.services.face_service._INSIGHTFACE_AVAILABLE", True),
            patch("klippbok.services.face_service._get_face_app") as mock_get_app,
            patch("cv2.imread") as mock_imread,
        ):
            mock_app = MagicMock()
            mock_app.get.return_value = [mock_face]
            mock_get_app.return_value = mock_app
            mock_imread.return_value = np.zeros((100, 100, 3), dtype=np.uint8)

            result = compute_face_embeddings([img1, img2])

        assert isinstance(result, dict)
        assert len(result) == 2
        assert str(img1) in result
        assert str(img2) in result
        assert result[str(img1)].shape == (512,)

    def test_skips_images_with_no_detected_face(self, tmp_path):
        """compute_face_embeddings omits images where no face is detected."""
        from klippbok.services.face_service import compute_face_embeddings

        img_no_face = tmp_path / "landscape.jpg"
        img_no_face.write_bytes(b"FAKE")

        with (
            patch("klippbok.services.face_service._INSIGHTFACE_AVAILABLE", True),
            patch("klippbok.services.face_service._get_face_app") as mock_get_app,
            patch("cv2.imread") as mock_imread,
        ):
            mock_app = MagicMock()
            mock_app.get.return_value = []  # No faces detected
            mock_get_app.return_value = mock_app
            mock_imread.return_value = np.zeros((100, 100, 3), dtype=np.uint8)

            result = compute_face_embeddings([img_no_face])

        assert result == {}

    def test_calls_progress_callback_with_current_and_total(self, tmp_path):
        """compute_face_embeddings calls progress_callback(current, total) per image."""
        from klippbok.services.face_service import compute_face_embeddings

        images = []
        for i in range(3):
            img = tmp_path / f"face{i}.jpg"
            img.write_bytes(b"FAKE")
            images.append(img)

        mock_face = MagicMock()
        mock_face.det_score = 0.95
        mock_face.normed_embedding = np.ones(512, dtype=np.float32)

        calls = []

        with (
            patch("klippbok.services.face_service._INSIGHTFACE_AVAILABLE", True),
            patch("klippbok.services.face_service._get_face_app") as mock_get_app,
            patch("cv2.imread") as mock_imread,
        ):
            mock_app = MagicMock()
            mock_app.get.return_value = [mock_face]
            mock_get_app.return_value = mock_app
            mock_imread.return_value = np.zeros((100, 100, 3), dtype=np.uint8)

            compute_face_embeddings(
                images,
                progress_callback=lambda c, t: calls.append((c, t)),
            )

        assert len(calls) == 3
        assert all(t == 3 for _, t in calls)
        assert [c for c, _ in calls] == [1, 2, 3]

    def test_selects_face_with_highest_det_score(self, tmp_path):
        """compute_face_embeddings picks the face with highest detection score."""
        from klippbok.services.face_service import compute_face_embeddings

        img = tmp_path / "two_faces.jpg"
        img.write_bytes(b"FAKE")

        face_low = MagicMock()
        face_low.det_score = 0.60
        face_low.normed_embedding = np.array([1.0] + [0.0] * 511, dtype=np.float32)

        face_high = MagicMock()
        face_high.det_score = 0.95
        face_high.normed_embedding = np.array([0.0, 1.0] + [0.0] * 510, dtype=np.float32)

        with (
            patch("klippbok.services.face_service._INSIGHTFACE_AVAILABLE", True),
            patch("klippbok.services.face_service._get_face_app") as mock_get_app,
            patch("cv2.imread") as mock_imread,
        ):
            mock_app = MagicMock()
            mock_app.get.return_value = [face_low, face_high]
            mock_get_app.return_value = mock_app
            mock_imread.return_value = np.zeros((100, 100, 3), dtype=np.uint8)

            result = compute_face_embeddings([img])

        # Should select face_high's embedding (second element = 1.0)
        assert result[str(img)][1] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# cluster_face_embeddings
# ---------------------------------------------------------------------------

class TestClusterFaceEmbeddings:
    def test_groups_similar_embeddings_using_dbscan(self):
        """cluster_face_embeddings groups similar embeddings into FaceClusters."""
        from klippbok.services.face_service import cluster_face_embeddings, FaceCluster

        # Create two groups of similar embeddings
        emb_a = np.array([1.0] + [0.0] * 511, dtype=np.float32)
        emb_b = np.array([0.99, 0.14] + [0.0] * 510, dtype=np.float32)
        emb_b = emb_b / np.linalg.norm(emb_b)
        emb_c = np.array([0.0, 1.0] + [0.0] * 510, dtype=np.float32)
        emb_d = np.array([0.14, 0.99] + [0.0] * 510, dtype=np.float32)
        emb_d = emb_d / np.linalg.norm(emb_d)

        embeddings = {
            "/path/img1.jpg": emb_a,
            "/path/img2.jpg": emb_b,
            "/path/img3.jpg": emb_c,
            "/path/img4.jpg": emb_d,
        }

        with patch("klippbok.services.face_service.DBSCAN") as mock_dbscan_cls:
            mock_dbscan = MagicMock()
            # Simulate two clusters: 0 and 1
            mock_dbscan.fit_predict.return_value = np.array([0, 0, 1, 1])
            mock_dbscan_cls.return_value = mock_dbscan

            clusters = cluster_face_embeddings(embeddings)

        assert isinstance(clusters, list)
        assert len(clusters) == 2
        for cluster in clusters:
            assert isinstance(cluster, FaceCluster)
            assert len(cluster.image_paths) == 2

    def test_returns_empty_list_for_no_embeddings(self):
        """cluster_face_embeddings returns empty list when no embeddings given."""
        from klippbok.services.face_service import cluster_face_embeddings

        result = cluster_face_embeddings({})
        assert result == []

    def test_excludes_noise_points(self):
        """cluster_face_embeddings excludes DBSCAN noise points (label=-1)."""
        from klippbok.services.face_service import cluster_face_embeddings

        emb = np.array([1.0] + [0.0] * 511, dtype=np.float32)
        embeddings = {
            "/img1.jpg": emb,
            "/img2.jpg": emb,
            "/noise.jpg": emb,
        }

        with patch("klippbok.services.face_service.DBSCAN") as mock_dbscan_cls:
            mock_dbscan = MagicMock()
            # img1, img2 in cluster 0; noise is -1
            mock_dbscan.fit_predict.return_value = np.array([0, 0, -1])
            mock_dbscan_cls.return_value = mock_dbscan

            clusters = cluster_face_embeddings(embeddings)

        assert len(clusters) == 1
        assert "/noise.jpg" not in clusters[0].image_paths


# ---------------------------------------------------------------------------
# select_best_reference
# ---------------------------------------------------------------------------

class TestSelectBestReference:
    def test_picks_highest_resolution_image_from_cluster(self, tmp_path):
        """select_best_reference picks the image with the highest pixel count."""
        from klippbok.services.face_service import select_best_reference, FaceCluster

        small_img = tmp_path / "small.jpg"
        large_img = tmp_path / "large.jpg"
        small_img.write_bytes(b"FAKE_SMALL")
        large_img.write_bytes(b"FAKE_LARGE")

        cluster = FaceCluster(
            cluster_id=0,
            image_paths=[str(small_img), str(large_img)],
        )

        with patch("klippbok.services.face_service.Image") as mock_image_module:
            mock_small = MagicMock()
            mock_small.size = (100, 100)  # 10,000 pixels
            mock_large = MagicMock()
            mock_large.size = (1920, 1080)  # 2,073,600 pixels

            mock_image_module.open.side_effect = [mock_small, mock_large]

            result = select_best_reference(cluster)

        assert result == str(large_img)
