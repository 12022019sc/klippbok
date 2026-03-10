"""Integration tests for the export API router.

Tests cover:
- GET /export/defaults returns default config values
- GET /export/validate returns candidate count and issues list
- POST /export/start returns 200 with op_id
- POST /export/{op_id}/cancel returns cancelled status
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
    """Create a minimal project with manifest and cropped test images."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    klippbok_dir = project_dir / ".klippbok"
    klippbok_dir.mkdir()

    # Create test images
    img1 = project_dir / "crop_photo1.jpg"
    img2 = project_dir / "crop_photo2.jpg"
    img1.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
    img2.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    # Create manifest with crop-source entries
    manifest = {
        "version": "1",
        "created": "2026-01-01T00:00:00Z",
        "updated": "2026-01-01T00:00:00Z",
        "active_profile": "sd15",
        "anchor_word": "mytrigger",
        "images": [
            {
                "path": "crop_photo1.jpg",
                "source": "crop",
                "caption": "A woman smiling",
                "width": 512,
                "height": 512,
            },
            {
                "path": "crop_photo2.jpg",
                "source": "crop",
                "caption": "",
                "width": 512,
                "height": 512,
            },
            {
                "path": "original.jpg",
                "source": "import",
                "caption": "An original photo",
                "width": 1024,
                "height": 768,
            },
        ],
    }
    (klippbok_dir / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    return project_dir


def _setup_empty_project(tmp_path: Path) -> Path:
    """Create a project with no cropped images."""
    project_dir = tmp_path / "empty_project"
    project_dir.mkdir()
    klippbok_dir = project_dir / ".klippbok"
    klippbok_dir.mkdir()

    manifest = {
        "version": "1",
        "created": "2026-01-01T00:00:00Z",
        "updated": "2026-01-01T00:00:00Z",
        "images": [],
    }
    (klippbok_dir / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return project_dir


class TestExportDefaultsEndpoint:
    """Test GET /api/v1/export/defaults."""

    def test_defaults_returns_export_config(self, tmp_path: Path) -> None:
        """GET /export/defaults should return 200 with default export values."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        resp = client.get("/api/v1/export/defaults")
        assert resp.status_code == 200
        data = resp.json()
        assert "trigger_word" in data
        assert "default_repeats" in data
        assert "class_name" in data
        assert "resolution" in data

    def test_defaults_reflect_manifest_anchor_word(self, tmp_path: Path) -> None:
        """Defaults trigger_word should come from manifest anchor_word."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        resp = client.get("/api/v1/export/defaults")
        assert resp.status_code == 200
        data = resp.json()
        assert data["trigger_word"] == "mytrigger"

    def test_defaults_no_project_returns_409(self) -> None:
        """GET /export/defaults with no project dir returns 409."""
        app = create_app(project_dir=None)
        client = TestClient(app)

        resp = client.get("/api/v1/export/defaults")
        assert resp.status_code == 409


class TestExportValidateEndpoint:
    """Test GET /api/v1/export/validate."""

    def test_validate_returns_candidates_and_issues(self, tmp_path: Path) -> None:
        """GET /export/validate returns candidate count and issues list."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        resp = client.get("/api/v1/export/validate")
        assert resp.status_code == 200
        data = resp.json()
        assert "candidates" in data
        assert "issues" in data
        # 2 crop-source images in fixture
        assert data["candidates"] == 2
        # 1 has empty caption
        assert len(data["issues"]) == 1
        assert data["issues"][0]["issue"] == "empty_caption"

    def test_validate_no_project_returns_409(self) -> None:
        """GET /export/validate with no project dir returns 409."""
        app = create_app(project_dir=None)
        client = TestClient(app)

        resp = client.get("/api/v1/export/validate")
        assert resp.status_code == 409

    def test_validate_empty_project_returns_zero_candidates(self, tmp_path: Path) -> None:
        """GET /export/validate with no crop images returns zero candidates."""
        project_dir = _setup_empty_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        resp = client.get("/api/v1/export/validate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["candidates"] == 0
        assert data["issues"] == []


class TestExportStartEndpoint:
    """Test POST /api/v1/export/start."""

    @patch("klippbok.api.routers.export.perform_export")
    def test_start_returns_op_id(
        self, mock_perform: MagicMock, tmp_path: Path
    ) -> None:
        """POST /export/start should return 200 with op_id."""
        project_dir = _setup_project(tmp_path)

        # Mock perform_export to avoid real file operations
        from klippbok.services.export_service import ExportResult
        mock_perform.return_value = ExportResult(
            status="ok",
            image_count=2,
            config_path=project_dir / "kohya_config.toml",
            output_dir=project_dir / "export",
        )

        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        resp = client.post(
            "/api/v1/export/start",
            json={
                "trainer": "kohya",
                "repeats": 5,
                "trigger_word": "sks",
                "class_name": "person",
                "concept_name": "test",
                "output_path": str(tmp_path / "export"),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "op_id" in data
        assert isinstance(data["op_id"], str)
        assert len(data["op_id"]) > 0

    def test_start_no_project_returns_409(self) -> None:
        """POST /export/start with no project dir returns 409."""
        app = create_app(project_dir=None)
        client = TestClient(app)

        resp = client.post(
            "/api/v1/export/start",
            json={
                "trainer": "kohya",
                "repeats": 5,
                "trigger_word": "sks",
                "class_name": "person",
                "concept_name": "test",
                "output_path": "/tmp/export",
            },
        )
        assert resp.status_code == 409

    def test_start_invalid_trainer_returns_422(self, tmp_path: Path) -> None:
        """POST /export/start with invalid trainer returns 422."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        resp = client.post(
            "/api/v1/export/start",
            json={
                "trainer": "unknown_trainer",
                "repeats": 5,
                "trigger_word": "sks",
                "class_name": "person",
                "concept_name": "test",
                "output_path": str(tmp_path / "export"),
            },
        )
        assert resp.status_code == 422


class TestExportCancelEndpoint:
    """Test POST /api/v1/export/{op_id}/cancel."""

    def test_cancel_unknown_op_returns_404(self, tmp_path: Path) -> None:
        """POST /export/{op_id}/cancel with unknown op_id returns 404."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        resp = client.post("/api/v1/export/nonexistent-op/cancel")
        assert resp.status_code == 404


class TestExportRouterRegistration:
    """Test that the export router is properly registered in the app."""

    def test_export_router_registered(self, tmp_path: Path) -> None:
        """Export router endpoints should be accessible after app creation."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        # GET /export/defaults should be reachable (not 404)
        resp = client.get("/api/v1/export/defaults")
        assert resp.status_code != 404

    def test_export_router_before_static_files(self, tmp_path: Path) -> None:
        """Export API endpoints should not be intercepted by SPA static mount."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        # Validate endpoint returns JSON (not index.html), confirming API router priority
        resp = client.get("/api/v1/export/validate")
        assert "application/json" in resp.headers.get("content-type", "")
