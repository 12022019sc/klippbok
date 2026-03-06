"""Integration tests for the cleanup API router.

Tests cover:
- POST /cleanup/start returns operation_id
- POST /cleanup/confirm moves files and returns count
- GET /cleanup/results/{op_id} returns stored classification results
- POST /cleanup/{op_id}/cancel returns cancelled status
- Router registration in app
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from klippbok.api.app import create_app


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal project with manifest and test images."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    klippbok_dir = project_dir / ".klippbok"
    klippbok_dir.mkdir()

    # Create test images
    img1 = project_dir / "photo1.jpg"
    img2 = project_dir / "photo2.jpg"
    img1.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
    img2.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    # Create sidecar
    (project_dir / "photo1.txt").write_text("caption text")

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
    (klippbok_dir / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    return project_dir


class TestCleanupStartEndpoint:
    """Test POST /api/v1/cleanup/start."""

    @patch("klippbok.services.face_service.check_insightface_available", return_value=False)
    @patch("klippbok.services.triage_service._get_or_create_embedder")
    def test_start_returns_operation_id(
        self, mock_embedder_fn, mock_insightface, tmp_path: Path
    ):
        """POST /cleanup/start should return 200 with operation_id."""
        project_dir = _setup_project(tmp_path)

        embedder = MagicMock()
        import numpy as np
        emb = np.array([0.1, 0.0, 0.0], dtype=np.float32)
        embedder.encode_image.return_value = emb
        embedder.encode_texts.return_value = [emb]
        mock_embedder_fn.return_value = embedder

        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        resp = client.post("/api/v1/cleanup/start", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "operation_id" in data
        assert isinstance(data["operation_id"], str)
        assert len(data["operation_id"]) > 0


class TestCleanupConfirmEndpoint:
    """Test POST /api/v1/cleanup/confirm."""

    def test_confirm_moves_files(self, tmp_path: Path):
        """POST /cleanup/confirm should move files and return moved count."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        resp = client.post(
            "/api/v1/cleanup/confirm",
            json={"item_paths": ["photo1.jpg"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["moved"] == 1
        assert "_review" in data["review_dir"]

        # Verify file was moved
        assert (project_dir / "_review" / "photo1.jpg").exists()
        assert not (project_dir / "photo1.jpg").exists()

        # Verify sidecar was moved
        assert (project_dir / "_review" / "photo1.txt").exists()

    def test_confirm_updates_manifest(self, tmp_path: Path):
        """POST /cleanup/confirm should remove entries from manifest."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        client.post(
            "/api/v1/cleanup/confirm",
            json={"item_paths": ["photo1.jpg"]},
        )

        manifest = json.loads(
            (project_dir / ".klippbok" / "manifest.json").read_text(encoding="utf-8")
        )
        paths = [e["path"] for e in manifest["images"]]
        assert "photo1.jpg" not in paths
        assert "photo2.jpg" in paths


class TestCleanupResultsEndpoint:
    """Test GET /api/v1/cleanup/results/{op_id}."""

    def test_results_returns_stored_classifications(self, tmp_path: Path):
        """GET /cleanup/results/{op_id} should return results from memory store."""
        from klippbok.api.routers.cleanup import _cleanup_results

        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        # Pre-populate results
        op_id = "test-op-123"
        _cleanup_results[op_id] = [
            {
                "item_path": "photo1.jpg",
                "item_id": "abc123",
                "clip_score": 0.35,
                "has_face": True,
                "confidence": 0.8,
                "label": "keep",
            }
        ]

        resp = client.get(f"/api/v1/cleanup/results/{op_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["label"] == "keep"

        # Clean up
        _cleanup_results.pop(op_id, None)

    def test_results_returns_404_for_unknown_op(self, tmp_path: Path):
        """GET /cleanup/results/{unknown} should return 404."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        resp = client.get("/api/v1/cleanup/results/nonexistent")
        assert resp.status_code == 404


class TestCleanupCancelEndpoint:
    """Test POST /api/v1/cleanup/{op_id}/cancel."""

    def test_cancel_unknown_op_returns_404(self, tmp_path: Path):
        """POST /cleanup/{op_id}/cancel should return 404 for unknown op."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        resp = client.post("/api/v1/cleanup/nonexistent/cancel")
        assert resp.status_code == 404


class TestCleanupRouterRegistration:
    """Test that cleanup router is registered in the app."""

    def test_cleanup_routes_exist(self, tmp_path: Path):
        """App should have cleanup routes registered."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)

        route_paths = [r.path for r in app.routes]
        assert any("/cleanup" in r for r in route_paths), (
            f"cleanup routes not found in {route_paths}"
        )
