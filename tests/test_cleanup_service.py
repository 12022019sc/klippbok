"""Unit tests for the cleanup classification service.

Tests cover:
- compute_confidence: score combination logic (pure math, no mocks)
- _classify_label: threshold-based labeling
- classify_item: single-item classification with mocked CLIP + InsightFace
- classify_items: batch classification with progress callback
- confirm_removal: file move to _review/ with sidecars and audit log
- video classification: frame sampling with best score
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from klippbok.services.cleanup_service import (
    CleanupClassification,
    compute_confidence,
    _classify_label,
    classify_item,
    classify_items,
    confirm_removal,
    DEFAULT_CLEANUP_THRESHOLD,
    generate_prompts_from_description,
    classify_item_by_reference,
    DEFAULT_REFERENCE_THRESHOLD,
)


# ---------------------------------------------------------------------------
# compute_confidence tests (pure logic, no mocks)
# ---------------------------------------------------------------------------

class TestComputeConfidence:
    """Test score combination logic."""

    def test_high_clip_with_face_returns_high_confidence(self):
        """CLIP score=0.30, has_face=True, threshold=0.25 -> confidence >= 0.6."""
        result = compute_confidence(0.30, True, 0.25)
        assert result >= 0.6, f"Expected >= 0.6, got {result}"

    def test_low_clip_no_face_returns_low_confidence(self):
        """CLIP score=0.10, has_face=False, threshold=0.25 -> confidence < 0.3."""
        result = compute_confidence(0.10, False, 0.25)
        assert result < 0.3, f"Expected < 0.3, got {result}"

    def test_face_boost_pushes_confidence_up(self):
        """Face detection should boost confidence by ~0.3."""
        no_face = compute_confidence(0.25, False, 0.25)
        with_face = compute_confidence(0.25, True, 0.25)
        assert with_face > no_face
        assert with_face - no_face >= 0.2  # Face boost is significant

    def test_confidence_clamped_to_0_1(self):
        """Confidence should never exceed 1.0 or go below 0.0."""
        high = compute_confidence(0.50, True, 0.10)
        assert 0.0 <= high <= 1.0

        low = compute_confidence(0.0, False, 0.40)
        assert 0.0 <= low <= 1.0

    def test_medium_clip_no_face_returns_review_range(self):
        """Medium CLIP score without face should land in review range."""
        result = compute_confidence(0.25, False, 0.25)
        # Should be in the middle-ish range
        assert 0.2 <= result <= 0.7


# ---------------------------------------------------------------------------
# _classify_label tests
# ---------------------------------------------------------------------------

class TestClassifyLabel:
    """Test threshold-based labeling."""

    def test_high_confidence_returns_keep(self):
        assert _classify_label(0.6) == "keep"
        assert _classify_label(0.8) == "keep"
        assert _classify_label(1.0) == "keep"

    def test_medium_confidence_returns_review(self):
        assert _classify_label(0.3) == "review"
        assert _classify_label(0.5) == "review"
        assert _classify_label(0.59) == "review"

    def test_low_confidence_returns_remove(self):
        assert _classify_label(0.0) == "remove"
        assert _classify_label(0.1) == "remove"
        assert _classify_label(0.29) == "remove"


# ---------------------------------------------------------------------------
# classify_item tests (mocked CLIP + InsightFace)
# ---------------------------------------------------------------------------

class TestClassifyItem:
    """Test single-item classification with mocked embedder."""

    def _make_mock_embedder(self, image_pos_score: float = 0.30, image_neg_score: float = 0.05):
        """Create a mock CLIPEmbedder with predictable similarity scores."""
        embedder = MagicMock()
        # encode_image returns a unit vector
        image_emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        embedder.encode_image.return_value = image_emb

        # Positive embeddings: high similarity
        pos_emb = np.array([image_pos_score, 0.0, 0.0], dtype=np.float32)
        # Negative embeddings: low similarity
        neg_emb = np.array([image_neg_score, 0.0, 0.0], dtype=np.float32)

        return embedder, [pos_emb], [neg_emb]

    def test_high_clip_with_face_returns_keep(self, tmp_path: Path):
        """High CLIP + face detected -> label=keep, confidence >= 0.6."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        embedder, pos_embs, neg_embs = self._make_mock_embedder(0.35, 0.05)

        # Mock face_app that detects a face
        face_app = MagicMock()
        face_app.get.return_value = [MagicMock(det_score=0.9)]

        with patch("klippbok.services.cleanup_service.cv2") as mock_cv2:
            mock_cv2.imread.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
            result = classify_item(
                image_path=img,
                embedder=embedder,
                positive_embeddings=pos_embs,
                negative_embeddings=neg_embs,
                clip_threshold=0.25,
                face_app=face_app,
                project_dir=tmp_path,
            )

        assert result.label == "keep"
        assert result.confidence >= 0.6
        assert result.has_face is True
        # item_id should be SHA256 of relative path ("test.jpg")
        import hashlib
        expected_id = hashlib.sha256("test.jpg".encode()).hexdigest()[:16]
        assert result.item_id == expected_id

    def test_low_clip_skips_insightface_returns_remove(self, tmp_path: Path):
        """Low CLIP score -> skip InsightFace, label=remove."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        embedder, pos_embs, neg_embs = self._make_mock_embedder(0.10, 0.05)

        face_app = MagicMock()

        result = classify_item(
            image_path=img,
            embedder=embedder,
            positive_embeddings=pos_embs,
            negative_embeddings=neg_embs,
            clip_threshold=0.25,
            face_app=face_app,
            project_dir=tmp_path,
        )

        assert result.label == "remove"
        assert result.has_face is False
        # InsightFace should NOT have been called
        face_app.get.assert_not_called()

    def test_medium_clip_no_face_returns_review(self, tmp_path: Path):
        """Medium CLIP + no face -> label=review."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        embedder, pos_embs, neg_embs = self._make_mock_embedder(0.28, 0.05)

        face_app = MagicMock()
        face_app.get.return_value = []  # No faces detected

        with patch("klippbok.services.cleanup_service.cv2") as mock_cv2:
            mock_cv2.imread.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
            result = classify_item(
                image_path=img,
                embedder=embedder,
                positive_embeddings=pos_embs,
                negative_embeddings=neg_embs,
                clip_threshold=0.25,
                face_app=face_app,
                project_dir=tmp_path,
            )

        assert result.label == "review"
        assert result.has_face is False


# ---------------------------------------------------------------------------
# classify_items tests (batch with progress callback)
# ---------------------------------------------------------------------------

class TestClassifyItems:
    """Test batch classification with mocked dependencies."""

    @patch("klippbok.services.face_service.check_insightface_available", return_value=False)
    @patch("klippbok.services.triage_service._get_or_create_embedder")
    def test_classify_items_calls_progress_callback(
        self, mock_embedder_fn, mock_insightface, tmp_path: Path
    ):
        """classify_items should call progress_callback(current, total) per item."""
        # Create test images
        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.jpg"
        img1.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        img2.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        # Mock embedder
        embedder = MagicMock()
        emb = np.array([0.1, 0.0, 0.0], dtype=np.float32)
        embedder.encode_image.return_value = emb
        embedder.encode_text.return_value = emb
        embedder.encode_texts.return_value = [emb]
        mock_embedder_fn.return_value = embedder

        progress_calls = []
        def progress_cb(current, total):
            progress_calls.append((current, total))

        results = classify_items(
            item_paths=[img1, img2],
            project_dir=tmp_path,
            positive_prompts=["person"],
            negative_prompts=["landscape"],
            clip_threshold=0.25,
            progress_callback=progress_cb,
        )

        assert len(results) == 2
        assert len(progress_calls) == 2
        assert progress_calls[0] == (1, 2)
        assert progress_calls[1] == (2, 2)

    @patch("klippbok.services.face_service.check_insightface_available", return_value=False)
    @patch("klippbok.services.triage_service._get_or_create_embedder")
    def test_classify_items_encodes_prompts_once(
        self, mock_embedder_fn, mock_insightface, tmp_path: Path
    ):
        """Text prompts should be encoded ONCE, not per image."""
        img1 = tmp_path / "a.jpg"
        img1.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        embedder = MagicMock()
        emb = np.array([0.1, 0.0, 0.0], dtype=np.float32)
        embedder.encode_image.return_value = emb
        embedder.encode_texts.return_value = [emb]
        mock_embedder_fn.return_value = embedder

        classify_items(
            item_paths=[img1],
            project_dir=tmp_path,
            positive_prompts=["person", "portrait"],
            negative_prompts=["landscape"],
            clip_threshold=0.25,
        )

        # encode_texts called exactly twice: once for positive, once for negative
        assert embedder.encode_texts.call_count == 2


# ---------------------------------------------------------------------------
# Video classification tests
# ---------------------------------------------------------------------------

class TestVideoClassification:
    """Test video classification with frame sampling."""

    @patch("klippbok.services.face_service.check_insightface_available", return_value=False)
    @patch("klippbok.services.triage_service._get_or_create_embedder")
    def test_video_samples_frames_uses_best_score(
        self, mock_embedder_fn, mock_insightface, tmp_path: Path
    ):
        """Video files should sample frames and use the best CLIP score."""
        import klippbok.services.cleanup_service as cs

        video = tmp_path / "clip.mp4"
        video.write_bytes(b"\x00" * 100)

        # Create fake frame files
        frame1 = tmp_path / "frame1.jpg"
        frame2 = tmp_path / "frame2.jpg"
        frame3 = tmp_path / "frame3.jpg"
        for f in [frame1, frame2, frame3]:
            f.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        # Patch the module-level lazy-loaded sampler functions
        mock_sample = MagicMock(return_value=[frame1, frame2, frame3])
        mock_cleanup = MagicMock()
        cs.sample_clip_frames = mock_sample
        cs.cleanup_frames = mock_cleanup

        embedder = MagicMock()
        # Different scores per frame
        embs = [
            np.array([0.10, 0.0, 0.0], dtype=np.float32),
            np.array([0.35, 0.0, 0.0], dtype=np.float32),  # Best
            np.array([0.20, 0.0, 0.0], dtype=np.float32),
        ]
        embedder.encode_image.side_effect = embs
        pos_emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        neg_emb = np.array([0.05, 0.0, 0.0], dtype=np.float32)
        embedder.encode_texts.side_effect = [[pos_emb], [neg_emb]]
        mock_embedder_fn.return_value = embedder

        results = classify_items(
            item_paths=[video],
            project_dir=tmp_path,
            positive_prompts=["person"],
            negative_prompts=["meme"],
            clip_threshold=0.25,
        )

        assert len(results) == 1
        # Best frame score should be 0.35 - 0.05 = 0.30, which is above threshold
        assert results[0].clip_score > 0.2
        mock_sample.assert_called_once()
        mock_cleanup.assert_called_once()

        # Reset module-level state
        cs.sample_clip_frames = None
        cs.cleanup_frames = None


# ---------------------------------------------------------------------------
# confirm_removal tests
# ---------------------------------------------------------------------------

class TestConfirmRemoval:
    """Test file move to _review/ with sidecars and audit log."""

    def _setup_project(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create a minimal project with manifest and images."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        klippbok_dir = project_dir / ".klippbok"
        klippbok_dir.mkdir()

        # Create images
        img = project_dir / "photo1.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        # Create sidecar .txt
        sidecar = project_dir / "photo1.txt"
        sidecar.write_text("a woman standing outdoors")

        # Create manifest
        manifest = {
            "version": "1",
            "created": "2026-01-01T00:00:00Z",
            "updated": "2026-01-01T00:00:00Z",
            "images": [
                {"path": "photo1.jpg", "width": 512, "height": 512},
                {"path": "photo2.jpg", "width": 768, "height": 512},
            ],
        }
        (klippbok_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        return project_dir, img

    def test_moves_files_to_review(self, tmp_path: Path):
        """confirm_removal should move files to _review/ directory."""
        project_dir, img = self._setup_project(tmp_path)

        result = confirm_removal(project_dir, ["photo1.jpg"])

        assert result["moved"] == 1
        review_dir = project_dir / "_review"
        assert review_dir.exists()
        assert (review_dir / "photo1.jpg").exists()
        assert not img.exists()

    def test_moves_sidecars(self, tmp_path: Path):
        """confirm_removal should move .txt and .json sidecars."""
        project_dir, _ = self._setup_project(tmp_path)

        # Also create .json sidecar
        (project_dir / "photo1.json").write_text("{}")

        result = confirm_removal(project_dir, ["photo1.jpg"])

        review_dir = project_dir / "_review"
        assert (review_dir / "photo1.txt").exists()
        assert (review_dir / "photo1.json").exists()
        assert not (project_dir / "photo1.txt").exists()
        assert not (project_dir / "photo1.json").exists()

    def test_updates_manifest(self, tmp_path: Path):
        """confirm_removal should remove entries from manifest images list."""
        project_dir, _ = self._setup_project(tmp_path)

        confirm_removal(project_dir, ["photo1.jpg"])

        manifest = json.loads(
            (project_dir / ".klippbok" / "manifest.json").read_text(encoding="utf-8")
        )
        paths = [e["path"] for e in manifest["images"]]
        assert "photo1.jpg" not in paths
        assert "photo2.jpg" in paths

    def test_writes_audit_log(self, tmp_path: Path):
        """confirm_removal should write cleanup_log.json in _review/."""
        project_dir, _ = self._setup_project(tmp_path)

        confirm_removal(project_dir, ["photo1.jpg"])

        log_path = project_dir / "_review" / "cleanup_log.json"
        assert log_path.exists()
        log_data = json.loads(log_path.read_text(encoding="utf-8"))
        assert len(log_data) >= 1
        assert log_data[0]["source"] == "photo1.jpg"
        assert "timestamp" in log_data[0]

    def test_returns_correct_counts(self, tmp_path: Path):
        """confirm_removal should return moved count and review dir path."""
        project_dir, _ = self._setup_project(tmp_path)

        result = confirm_removal(project_dir, ["photo1.jpg"])

        assert result["moved"] == 1
        assert "_review" in result["review_dir"]


# ---------------------------------------------------------------------------
# generate_prompts_from_description tests
# ---------------------------------------------------------------------------

class TestGeneratePrompts:
    """Test prompt generation from subject description."""

    def test_generates_positive_prompts_from_description(self):
        pos, neg = generate_prompts_from_description("woman with dark hair")
        assert len(pos) >= 3
        assert any("woman with dark hair" in p for p in pos)
        # Negative prompts should be the defaults
        assert "screenshot" in neg

    def test_empty_description_raises(self):
        with pytest.raises(ValueError, match="empty"):
            generate_prompts_from_description("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            generate_prompts_from_description("   ")


# ---------------------------------------------------------------------------
# classify_item_by_reference tests
# ---------------------------------------------------------------------------

class TestClassifyItemByReference:
    """Test single-item reference-based classification."""

    def test_high_similarity_returns_keep(self, tmp_path: Path):
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        embedder = MagicMock()
        # Image embedding very similar to reference
        image_emb = np.array([0.9, 0.1, 0.0], dtype=np.float32)
        image_emb = image_emb / np.linalg.norm(image_emb)
        embedder.encode_image.return_value = image_emb

        ref_emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        ref_emb = ref_emb / np.linalg.norm(ref_emb)

        result = classify_item_by_reference(
            image_path=img,
            embedder=embedder,
            reference_embeddings=[ref_emb],
            clip_threshold=DEFAULT_REFERENCE_THRESHOLD,
            face_app=None,
            project_dir=tmp_path,
        )

        assert result.label == "keep"
        assert result.clip_score > 0.8

    def test_low_similarity_returns_remove(self, tmp_path: Path):
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        embedder = MagicMock()
        # Image embedding orthogonal to reference
        image_emb = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        embedder.encode_image.return_value = image_emb

        ref_emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        result = classify_item_by_reference(
            image_path=img,
            embedder=embedder,
            reference_embeddings=[ref_emb],
            clip_threshold=DEFAULT_REFERENCE_THRESHOLD,
            face_app=None,
            project_dir=tmp_path,
        )

        assert result.label == "remove"
        assert result.clip_score < 0.2

    def test_multiple_references_uses_max(self, tmp_path: Path):
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        embedder = MagicMock()
        image_emb = np.array([0.9, 0.1, 0.0], dtype=np.float32)
        image_emb = image_emb / np.linalg.norm(image_emb)
        embedder.encode_image.return_value = image_emb

        # Two references: one similar, one orthogonal
        ref1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        ref1 = ref1 / np.linalg.norm(ref1)
        ref2 = np.array([0.0, 0.0, 1.0], dtype=np.float32)

        result = classify_item_by_reference(
            image_path=img,
            embedder=embedder,
            reference_embeddings=[ref1, ref2],
            clip_threshold=DEFAULT_REFERENCE_THRESHOLD,
            face_app=None,
            project_dir=tmp_path,
        )

        # Should use max similarity (against ref1)
        assert result.clip_score > 0.8
