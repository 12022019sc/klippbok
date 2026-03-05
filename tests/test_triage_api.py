"""Tests for the triage API router.

Tests verify:
  - POST /api/v1/triage/run/start returns operation_id
  - POST /api/v1/triage/run/{op_id}/cancel returns cancelled=true
  - GET  /api/v1/triage/results returns persisted triage results
  - GET  /api/v1/triage/concepts returns list of concept references
  - POST /api/v1/triage/concepts adds image as concept reference
  - POST /api/v1/triage/face/start returns operation_id
  - POST /api/v1/triage/face/{op_id}/cancel returns cancelled=true
  - GET  /api/v1/triage/face/clusters returns face clusters
  - POST /api/v1/triage/face/clusters/{cluster_id}/name names a cluster
  - GET  /api/v1/triage/health returns CLIP and InsightFace availability

All service calls are mocked to avoid heavy CLIP/InsightFace dependencies in CI.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# App factory fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal project directory structure."""
    klippbok_dir = tmp_path / ".klippbok"
    klippbok_dir.mkdir(parents=True)
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    concepts_dir = tmp_path / "concepts"
    concepts_dir.mkdir()
    char_dir = concepts_dir / "character"
    char_dir.mkdir()
    ref_img = char_dir / "alice.jpg"
    ref_img.write_bytes(b"FAKE_REF")
    return tmp_path


@pytest.fixture
def client(project_dir: Path) -> TestClient:
    """Create a test client with a project directory set."""
    from klippbok.api.app import create_app
    app = create_app(project_dir=project_dir)
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Triage run endpoints
# ---------------------------------------------------------------------------

class TestTriageRunStart:
    def test_returns_operation_id(self, client: TestClient, project_dir: Path):
        """POST /triage/run/start returns 202 with operation_id."""
        with (
            patch("klippbok.api.routers.triage.run_triage") as mock_run,
            patch("klippbok.api.routers.triage._resolve_item_paths") as mock_resolve,
        ):
            mock_resolve.return_value = []
            mock_run.return_value = []

            response = client.post("/api/v1/triage/run/start", json={
                "threshold": 0.70,
            })

        assert response.status_code == 202
        data = response.json()
        assert "operation_id" in data
        assert isinstance(data["operation_id"], str)
        assert len(data["operation_id"]) > 0

    def test_returns_409_when_no_project_dir(self):
        """POST /triage/run/start returns 409 when no project directory set."""
        from klippbok.api.app import create_app
        app = create_app(project_dir=None)
        no_project_client = TestClient(app, raise_server_exceptions=False)

        response = no_project_client.post("/api/v1/triage/run/start", json={})
        assert response.status_code == 409


class TestTriageRunCancel:
    def test_cancel_returns_cancelled_true(self, client: TestClient, project_dir: Path):
        """POST /triage/run/{op_id}/cancel returns {cancelled: true}."""
        import asyncio
        from klippbok.api.routers import triage as triage_router

        # Register a fake task
        op_id = "test-op-cancel"
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_task.cancel.return_value = True
        triage_router._triage_tasks[op_id] = mock_task

        response = client.post(f"/api/v1/triage/run/{op_id}/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data["cancelled"] is True

        # Cleanup
        del triage_router._triage_tasks[op_id]

    def test_cancel_returns_404_for_unknown_op_id(self, client: TestClient):
        """POST /triage/run/nonexistent/cancel returns 404."""
        response = client.post("/api/v1/triage/run/nonexistent/cancel")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Triage results endpoint
# ---------------------------------------------------------------------------

class TestTriageResults:
    def test_returns_empty_list_when_no_manifest(self, client: TestClient, project_dir: Path):
        """GET /triage/results returns empty list when no manifest exists."""
        response = client.get("/api/v1/triage/results")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data == []

    def test_returns_persisted_results(self, client: TestClient, project_dir: Path):
        """GET /triage/results returns results from triage_manifest.json."""
        manifest_data = {
            "results": [
                {
                    "item_path": str(project_dir / "images" / "photo.jpg"),
                    "item_id": "abc123",
                    "best_score": 0.85,
                    "matches": [{"concept_name": "alice", "score": 0.85}],
                    "classification": "match",
                }
            ]
        }
        manifest_path = project_dir / ".klippbok" / "triage_manifest.json"
        manifest_path.write_text(json.dumps(manifest_data))

        response = client.get("/api/v1/triage/results")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["best_score"] == 0.85
        assert data[0]["classification"] == "match"


# ---------------------------------------------------------------------------
# Concept management endpoints
# ---------------------------------------------------------------------------

class TestTriageConcepts:
    def test_get_concepts_returns_list(self, client: TestClient, project_dir: Path):
        """GET /triage/concepts returns list of concept references."""
        response = client.get("/api/v1/triage/concepts")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have 'alice' from the fixture
        assert len(data) >= 1
        names = [r["name"] for r in data]
        assert "alice" in names

    def test_post_concepts_adds_image(self, client: TestClient, project_dir: Path):
        """POST /triage/concepts adds an image as concept reference."""
        # Create a fake source image (simulate an image already in project)
        source_img = project_dir / "images" / "new_ref.jpg"
        source_img.write_bytes(b"FAKE_IMG")

        with patch("klippbok.api.routers.triage.add_concept_reference") as mock_add:
            from klippbok.triage.models import ConceptReference, ConceptType
            mock_add.return_value = ConceptReference(
                name="new_ref",
                concept_type=ConceptType.CHARACTER,
                image_path=project_dir / "concepts" / "character" / "new_ref.jpg",
                folder_name="character",
            )

            response = client.post("/api/v1/triage/concepts", json={
                "image_path": str(source_img),
                "category": "character",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "new_ref"
        assert data["folder_name"] == "character"


# ---------------------------------------------------------------------------
# Face embedding endpoints
# ---------------------------------------------------------------------------

class TestTriageFaceStart:
    def test_returns_operation_id(self, client: TestClient, project_dir: Path):
        """POST /triage/face/start returns 202 with operation_id."""
        with patch("klippbok.api.routers.triage.compute_face_embeddings") as mock_compute:
            mock_compute.return_value = {}

            response = client.post("/api/v1/triage/face/start", json={})

        assert response.status_code == 202
        data = response.json()
        assert "operation_id" in data

    def test_returns_409_when_no_project_dir(self):
        """POST /triage/face/start returns 409 when no project directory set."""
        from klippbok.api.app import create_app
        app = create_app(project_dir=None)
        no_project_client = TestClient(app, raise_server_exceptions=False)

        response = no_project_client.post("/api/v1/triage/face/start", json={})
        assert response.status_code == 409


class TestTriageFaceCancel:
    def test_cancel_returns_cancelled_true(self, client: TestClient):
        """POST /triage/face/{op_id}/cancel returns {cancelled: true}."""
        from klippbok.api.routers import triage as triage_router

        op_id = "face-cancel-op"
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_task.cancel.return_value = True
        triage_router._face_tasks[op_id] = mock_task

        response = client.post(f"/api/v1/triage/face/{op_id}/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data["cancelled"] is True

        del triage_router._face_tasks[op_id]

    def test_cancel_returns_404_for_unknown_op(self, client: TestClient):
        """POST /triage/face/nonexistent/cancel returns 404."""
        response = client.post("/api/v1/triage/face/nonexistent/cancel")
        assert response.status_code == 404


class TestTriageFaceClusters:
    def test_returns_current_clusters(self, client: TestClient, project_dir: Path):
        """GET /triage/face/clusters returns stored face clusters for project."""
        from klippbok.api.routers import triage as triage_router
        from klippbok.services.face_service import FaceCluster

        project_key = str(project_dir)
        triage_router._face_clusters[project_key] = [
            FaceCluster(
                cluster_id=0,
                image_paths=[str(project_dir / "images" / "face1.jpg")],
                suggested_name="alice",
            )
        ]

        response = client.get("/api/v1/triage/face/clusters")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["cluster_id"] == 0
        assert data[0]["suggested_name"] == "alice"

        del triage_router._face_clusters[project_key]

    def test_returns_empty_when_no_clusters(self, client: TestClient):
        """GET /triage/face/clusters returns empty list when no clustering done."""
        response = client.get("/api/v1/triage/face/clusters")
        assert response.status_code == 200
        assert response.json() == []


class TestTriageFaceClusterName:
    def test_names_a_cluster(self, client: TestClient, project_dir: Path):
        """POST /triage/face/clusters/{id}/name sets cluster suggested_name."""
        from klippbok.api.routers import triage as triage_router
        from klippbok.services.face_service import FaceCluster

        project_key = str(project_dir)
        triage_router._face_clusters[project_key] = [
            FaceCluster(cluster_id=0, image_paths=["img1.jpg"])
        ]

        response = client.post(
            "/api/v1/triage/face/clusters/0/name",
            json={"name": "bob"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["suggested_name"] == "bob"
        assert data["cluster_id"] == 0

        del triage_router._face_clusters[project_key]

    def test_returns_404_for_unknown_cluster_id(self, client: TestClient, project_dir: Path):
        """POST /triage/face/clusters/99/name returns 404 when cluster not found."""
        response = client.post(
            "/api/v1/triage/face/clusters/99/name",
            json={"name": "nobody"},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestTriageHealth:
    def test_returns_availability_flags(self, client: TestClient):
        """GET /triage/health returns clip_available and insightface_available flags."""
        with (
            patch("klippbok.api.routers.triage.check_clip_available_flag") as mock_clip,
            patch("klippbok.api.routers.triage.check_insightface_available") as mock_face,
        ):
            mock_clip.return_value = True
            mock_face.return_value = False

            response = client.get("/api/v1/triage/health")

        assert response.status_code == 200
        data = response.json()
        assert "clip_available" in data
        assert "insightface_available" in data
        assert isinstance(data["clip_available"], bool)
        assert isinstance(data["insightface_available"], bool)
