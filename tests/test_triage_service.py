"""Tests for triage_service — CLIP triage for standalone images and clips.

All tests mock CLIPEmbedder and discover_concepts to avoid requiring
torch/transformers in CI.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def concepts_dir(tmp_path: Path) -> Path:
    """Create a minimal concepts directory with one character folder."""
    char_dir = tmp_path / "concepts" / "character"
    char_dir.mkdir(parents=True)
    # Create a dummy reference image
    ref_img = char_dir / "alice.jpg"
    ref_img.write_bytes(b"FAKE_JPEG")
    return tmp_path / "concepts"


@pytest.fixture
def image_dir(tmp_path: Path) -> Path:
    """Create a directory with two fake images."""
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    (img_dir / "photo1.jpg").write_bytes(b"FAKE1")
    (img_dir / "photo2.jpg").write_bytes(b"FAKE2")
    return img_dir


@pytest.fixture
def mock_embedder():
    """A mock CLIPEmbedder that returns deterministic embeddings."""
    embedder = MagicMock()
    # Return normalized embedding of all 0.5
    emb = np.array([0.5] * 512, dtype=np.float32)
    emb = emb / np.linalg.norm(emb)
    embedder.encode_image.return_value = emb
    embedder.similarity.side_effect = lambda a, b: float(np.dot(a, b))
    return embedder


@pytest.fixture
def mock_concept_ref(concepts_dir):
    """A mock ConceptReference for 'alice'."""
    from klippbok.triage.models import ConceptReference, ConceptType
    return ConceptReference(
        name="alice",
        concept_type=ConceptType.CHARACTER,
        image_path=concepts_dir / "character" / "alice.jpg",
        folder_name="character",
    )


# ---------------------------------------------------------------------------
# run_triage — CLIP similarity scoring for image paths
# ---------------------------------------------------------------------------

class TestRunTriage:
    def test_run_triage_with_image_paths_returns_triage_results(
        self, tmp_path, concepts_dir, mock_concept_ref
    ):
        """run_triage returns a list of TriageResult for each image path."""
        from klippbok.services.triage_service import run_triage, TriageResult

        img1 = tmp_path / "photo1.jpg"
        img1.write_bytes(b"FAKE")

        emb = np.ones(512, dtype=np.float32)
        emb = emb / np.linalg.norm(emb)

        with (
            patch("klippbok.services.triage_service._get_or_create_embedder") as mock_get_emb,
            patch("klippbok.services.triage_service.discover_concepts") as mock_discover,
        ):
            mock_embedder = MagicMock()
            mock_embedder.encode_image.return_value = emb
            mock_get_emb.return_value = mock_embedder
            mock_discover.return_value = [mock_concept_ref]

            results = run_triage(
                item_paths=[img1],
                concepts_dir=concepts_dir,
                threshold=0.70,
            )

        assert isinstance(results, list)
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, TriageResult)
        assert result.item_path == str(img1)
        assert isinstance(result.best_score, float)
        assert isinstance(result.matches, list)
        assert result.classification in ("match", "borderline", "no_match")

    def test_run_triage_computes_similarity_scores(
        self, tmp_path, concepts_dir, mock_concept_ref
    ):
        """Triage score equals cosine similarity between image and reference embeddings."""
        from klippbok.services.triage_service import run_triage

        img1 = tmp_path / "photo1.jpg"
        img1.write_bytes(b"FAKE")

        # Use identical embeddings -> similarity = 1.0
        emb = np.ones(512, dtype=np.float32)
        emb = emb / np.linalg.norm(emb)

        with (
            patch("klippbok.services.triage_service._get_or_create_embedder") as mock_get_emb,
            patch("klippbok.services.triage_service.discover_concepts") as mock_discover,
        ):
            mock_emb_obj = MagicMock()
            mock_emb_obj.encode_image.return_value = emb
            mock_get_emb.return_value = mock_emb_obj
            mock_discover.return_value = [mock_concept_ref]

            results = run_triage(
                item_paths=[img1],
                concepts_dir=concepts_dir,
                threshold=0.70,
            )

        assert len(results) == 1
        assert results[0].best_score == pytest.approx(1.0, abs=0.01)
        assert len(results[0].matches) == 1
        assert results[0].matches[0].concept_name == "alice"

    def test_run_triage_classifies_match(self, tmp_path, concepts_dir, mock_concept_ref):
        """Items with score >= threshold are classified as 'match'."""
        from klippbok.services.triage_service import run_triage

        img = tmp_path / "photo.jpg"
        img.write_bytes(b"FAKE")

        emb = np.ones(512, dtype=np.float32)
        emb = emb / np.linalg.norm(emb)

        with (
            patch("klippbok.services.triage_service._get_or_create_embedder") as mock_get_emb,
            patch("klippbok.services.triage_service.discover_concepts") as mock_discover,
        ):
            mock_emb_obj = MagicMock()
            mock_emb_obj.encode_image.return_value = emb
            mock_get_emb.return_value = mock_emb_obj
            mock_discover.return_value = [mock_concept_ref]

            results = run_triage(item_paths=[img], concepts_dir=concepts_dir, threshold=0.70)

        assert results[0].classification == "match"

    def test_run_triage_classifies_no_match(self, tmp_path, concepts_dir, mock_concept_ref):
        """Items with score < threshold - 0.1 are classified as 'no_match'."""
        from klippbok.services.triage_service import run_triage

        img = tmp_path / "photo.jpg"
        img.write_bytes(b"FAKE")

        # Item embedding far from reference
        item_emb = np.zeros(512, dtype=np.float32)
        item_emb[0] = 1.0  # points in x direction

        ref_emb = np.zeros(512, dtype=np.float32)
        ref_emb[1] = 1.0  # points in y direction -> similarity = 0.0

        with (
            patch("klippbok.services.triage_service._get_or_create_embedder") as mock_get_emb,
            patch("klippbok.services.triage_service.discover_concepts") as mock_discover,
        ):
            mock_emb_obj = MagicMock()
            # encode_image: first call for reference, second for item
            mock_emb_obj.encode_image.side_effect = [ref_emb, item_emb]
            mock_get_emb.return_value = mock_emb_obj
            mock_discover.return_value = [mock_concept_ref]

            results = run_triage(item_paths=[img], concepts_dir=concepts_dir, threshold=0.70)

        assert results[0].classification == "no_match"

    def test_run_triage_classifies_borderline(self, tmp_path, concepts_dir, mock_concept_ref):
        """Items with score in (threshold-0.1, threshold) are 'borderline'."""
        from klippbok.services.triage_service import run_triage

        img = tmp_path / "photo.jpg"
        img.write_bytes(b"FAKE")

        # Craft embeddings to produce ~0.65 similarity with threshold 0.70
        # borderline range = (0.60, 0.70)
        # cos(theta) = 0.65 -> theta = arccos(0.65)
        import math
        angle = math.acos(0.65)
        item_emb = np.array([math.cos(angle), math.sin(angle)] + [0.0] * 510, dtype=np.float32)
        item_emb = item_emb / np.linalg.norm(item_emb)
        ref_emb = np.array([1.0] + [0.0] * 511, dtype=np.float32)

        with (
            patch("klippbok.services.triage_service._get_or_create_embedder") as mock_get_emb,
            patch("klippbok.services.triage_service.discover_concepts") as mock_discover,
        ):
            mock_emb_obj = MagicMock()
            mock_emb_obj.encode_image.side_effect = [ref_emb, item_emb]
            mock_get_emb.return_value = mock_emb_obj
            mock_discover.return_value = [mock_concept_ref]

            results = run_triage(item_paths=[img], concepts_dir=concepts_dir, threshold=0.70)

        assert results[0].classification == "borderline"

    def test_run_triage_persists_results_when_output_path_given(
        self, tmp_path, concepts_dir, mock_concept_ref
    ):
        """run_triage writes triage_manifest.json when output_path provided."""
        from klippbok.services.triage_service import run_triage

        img = tmp_path / "photo.jpg"
        img.write_bytes(b"FAKE")
        output_path = tmp_path / "triage_manifest.json"

        emb = np.ones(512, dtype=np.float32)
        emb = emb / np.linalg.norm(emb)

        with (
            patch("klippbok.services.triage_service._get_or_create_embedder") as mock_get_emb,
            patch("klippbok.services.triage_service.discover_concepts") as mock_discover,
        ):
            mock_emb_obj = MagicMock()
            mock_emb_obj.encode_image.return_value = emb
            mock_get_emb.return_value = mock_emb_obj
            mock_discover.return_value = [mock_concept_ref]

            run_triage(
                item_paths=[img],
                concepts_dir=concepts_dir,
                output_path=output_path,
            )

        assert output_path.exists()
        manifest = json.loads(output_path.read_text())
        assert "results" in manifest
        assert len(manifest["results"]) == 1

    def test_run_triage_calls_progress_callback(
        self, tmp_path, concepts_dir, mock_concept_ref
    ):
        """run_triage calls progress_callback(current, total) for each item."""
        from klippbok.services.triage_service import run_triage

        images = []
        for i in range(3):
            img = tmp_path / f"photo{i}.jpg"
            img.write_bytes(b"FAKE")
            images.append(img)

        emb = np.ones(512, dtype=np.float32)
        emb = emb / np.linalg.norm(emb)
        calls = []

        with (
            patch("klippbok.services.triage_service._get_or_create_embedder") as mock_get_emb,
            patch("klippbok.services.triage_service.discover_concepts") as mock_discover,
        ):
            mock_emb_obj = MagicMock()
            mock_emb_obj.encode_image.return_value = emb
            mock_get_emb.return_value = mock_emb_obj
            mock_discover.return_value = [mock_concept_ref]

            run_triage(
                item_paths=images,
                concepts_dir=concepts_dir,
                progress_callback=lambda c, t: calls.append((c, t)),
            )

        assert len(calls) == 3
        totals = [t for _, t in calls]
        assert all(t == 3 for t in totals)
        currents = [c for c, _ in calls]
        assert currents == [1, 2, 3]


# ---------------------------------------------------------------------------
# get_triage_results
# ---------------------------------------------------------------------------

class TestGetTriageResults:
    def test_loads_persisted_results(self, tmp_path):
        """get_triage_results loads and returns TriageResult list from JSON."""
        from klippbok.services.triage_service import get_triage_results, TriageResult

        manifest_data = {
            "results": [
                {
                    "item_path": str(tmp_path / "photo.jpg"),
                    "item_id": "abc123",
                    "best_score": 0.85,
                    "matches": [
                        {"concept_name": "alice", "score": 0.85}
                    ],
                    "classification": "match",
                }
            ]
        }
        manifest = tmp_path / "triage_manifest.json"
        manifest.write_text(json.dumps(manifest_data))

        results = get_triage_results(manifest)
        assert len(results) == 1
        assert isinstance(results[0], TriageResult)
        assert results[0].best_score == 0.85
        assert results[0].classification == "match"


# ---------------------------------------------------------------------------
# add_concept_reference
# ---------------------------------------------------------------------------

class TestAddConceptReference:
    def test_copies_image_to_concepts_folder(self, tmp_path):
        """add_concept_reference copies image to concepts/{category}/ folder."""
        from klippbok.services.triage_service import add_concept_reference

        source = tmp_path / "holly.jpg"
        source.write_bytes(b"FAKE_IMAGE_DATA")
        concepts_dir = tmp_path / "concepts"

        result = add_concept_reference(
            image_path=source,
            concepts_dir=concepts_dir,
            category="character",
        )

        dest = concepts_dir / "character" / "holly.jpg"
        assert dest.exists()
        assert dest.read_bytes() == b"FAKE_IMAGE_DATA"

    def test_returns_concept_reference(self, tmp_path):
        """add_concept_reference returns a ConceptReference with correct fields."""
        from klippbok.services.triage_service import add_concept_reference
        from klippbok.triage.models import ConceptReference

        source = tmp_path / "oak_forest.png"
        source.write_bytes(b"FAKE")
        concepts_dir = tmp_path / "concepts"

        result = add_concept_reference(
            image_path=source,
            concepts_dir=concepts_dir,
            category="setting",
        )

        assert isinstance(result, ConceptReference)
        assert result.name == "oak_forest"
        assert result.folder_name == "setting"


# ---------------------------------------------------------------------------
# list_concepts
# ---------------------------------------------------------------------------

class TestListConcepts:
    def test_returns_all_discovered_concept_references(self, concepts_dir):
        """list_concepts returns all ConceptReferences from the folder structure."""
        from klippbok.services.triage_service import list_concepts
        from klippbok.triage.models import ConceptReference

        results = list_concepts(concepts_dir)
        assert isinstance(results, list)
        assert len(results) >= 1
        assert all(isinstance(r, ConceptReference) for r in results)
        names = [r.name for r in results]
        assert "alice" in names
