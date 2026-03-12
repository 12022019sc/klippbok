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
            preset_path=None,
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


# ---------------------------------------------------------------------------
# Training endpoint tests (08-04)
# ---------------------------------------------------------------------------


class TestTrainStatusEndpoint:
    """Test GET /api/v1/export/train/status (gap 08-04-01)."""

    @patch("klippbok.api.routers.export.is_gpu_busy", create=True)
    @patch("klippbok.api.routers.export.get_gpu_vram_used_mb", create=True)
    @patch("klippbok.api.routers.export.is_training_active", create=True)
    @patch("klippbok.api.routers.export.detect_onetrainer", create=True)
    @patch("klippbok.api.routers.export.load_global_config", create=True)
    def test_train_status_returns_expected_fields(
        self,
        mock_load_config: MagicMock,
        mock_detect: MagicMock,
        mock_is_active: MagicMock,
        mock_vram: MagicMock,
        mock_busy: MagicMock,
        tmp_path: Path,
    ) -> None:
        """GET /export/train/status returns onetrainer_detected, training_active, gpu fields."""
        mock_load_config.return_value = {}
        mock_detect.return_value = None
        mock_is_active.return_value = False
        mock_vram.return_value = 512
        mock_busy.return_value = False

        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        with (
            patch(
                "klippbok.services.global_config_service.load_global_config",
                return_value={},
            ),
            patch(
                "klippbok.services.onetrainer_service.detect_onetrainer",
                return_value=None,
            ),
            patch(
                "klippbok.services.onetrainer_service.is_training_active",
                return_value=False,
            ),
            patch(
                "klippbok.services.gpu_service.get_gpu_vram_used_mb",
                return_value=512,
            ),
            patch(
                "klippbok.services.gpu_service.is_gpu_busy",
                return_value=False,
            ),
        ):
            resp = client.get("/api/v1/export/train/status")

        assert resp.status_code == 200
        data = resp.json()
        assert "onetrainer_detected" in data
        assert "training_active" in data
        assert "gpu_vram_used_mb" in data
        assert "gpu_busy" in data

    def test_train_status_onetrainer_not_detected(self, tmp_path: Path) -> None:
        """GET /export/train/status with no OneTrainer install returns onetrainer_detected=False."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        with (
            patch(
                "klippbok.services.global_config_service.load_global_config",
                return_value={},
            ),
            patch(
                "klippbok.services.onetrainer_service.detect_onetrainer",
                return_value=None,
            ),
            patch(
                "klippbok.services.onetrainer_service.is_training_active",
                return_value=False,
            ),
            patch(
                "klippbok.services.gpu_service.get_gpu_vram_used_mb",
                return_value=None,
            ),
            patch(
                "klippbok.services.gpu_service.is_gpu_busy",
                return_value=False,
            ),
        ):
            resp = client.get("/api/v1/export/train/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["onetrainer_detected"] is False
        assert data["onetrainer_path"] is None
        assert data["training_active"] is False

    def test_train_status_with_active_training_and_gpu_busy(self, tmp_path: Path) -> None:
        """GET /export/train/status reflects training_active and gpu_busy when GPU is loaded."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        with (
            patch(
                "klippbok.services.global_config_service.load_global_config",
                return_value={},
            ),
            patch(
                "klippbok.services.onetrainer_service.detect_onetrainer",
                return_value=None,
            ),
            patch(
                "klippbok.services.onetrainer_service.is_training_active",
                return_value=True,
            ),
            patch(
                "klippbok.services.gpu_service.get_gpu_vram_used_mb",
                return_value=10240,
            ),
            patch(
                "klippbok.services.gpu_service.is_gpu_busy",
                return_value=True,
            ),
        ):
            resp = client.get("/api/v1/export/train/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["training_active"] is True
        assert data["gpu_busy"] is True
        assert data["gpu_vram_used_mb"] == 10240


class TestTrainStopEndpoint:
    """Test POST /api/v1/export/train/{op_id}/stop (gap 08-04-02)."""

    def test_stop_known_op_returns_stopped_true(self, tmp_path: Path) -> None:
        """POST /export/train/{op_id}/stop returns stopped=True when op exists."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        with patch(
            "klippbok.services.onetrainer_service.stop_onetrainer",
            return_value=True,
        ):
            resp = client.post("/api/v1/export/train/abc12345/stop")

        assert resp.status_code == 200
        data = resp.json()
        assert data["stopped"] is True

    def test_stop_unknown_op_returns_stopped_false(self, tmp_path: Path) -> None:
        """POST /export/train/{op_id}/stop returns stopped=False when op not found."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        with patch(
            "klippbok.services.onetrainer_service.stop_onetrainer",
            return_value=False,
        ):
            resp = client.post("/api/v1/export/train/nonexistent/stop")

        assert resp.status_code == 200
        data = resp.json()
        assert data["stopped"] is False


class TestTrainLaunchGuiEndpoint:
    """Test POST /api/v1/export/train/launch-gui (gap 08-04-03)."""

    def test_launch_gui_returns_launched_when_onetrainer_detected(
        self, tmp_path: Path
    ) -> None:
        """POST /export/train/launch-gui returns status=launched when OneTrainer is found."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        fake_ot_root = tmp_path / "OneTrainer"

        with (
            patch(
                "klippbok.services.global_config_service.load_global_config",
                return_value={},
            ),
            patch(
                "klippbok.services.onetrainer_service.detect_onetrainer",
                return_value=fake_ot_root,
            ),
            patch(
                "klippbok.services.onetrainer_service.launch_onetrainer_gui",
                return_value=None,
            ),
        ):
            resp = client.post("/api/v1/export/train/launch-gui")

        assert resp.status_code == 200
        assert resp.json()["status"] == "launched"

    def test_launch_gui_forwards_preset_path(
        self, tmp_path: Path
    ) -> None:
        """POST /export/train/launch-gui forwards preset_path to launch_onetrainer_gui."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        fake_ot_root = tmp_path / "OneTrainer"
        mock_launch = MagicMock(return_value=None)

        with (
            patch(
                "klippbok.services.global_config_service.load_global_config",
                return_value={},
            ),
            patch(
                "klippbok.services.onetrainer_service.detect_onetrainer",
                return_value=fake_ot_root,
            ),
            patch(
                "klippbok.services.onetrainer_service.launch_onetrainer_gui",
                mock_launch,
            ),
        ):
            resp = client.post(
                "/api/v1/export/train/launch-gui",
                json={"preset_path": "/some/preset.json"},
            )

        assert resp.status_code == 200
        mock_launch.assert_called_once_with(fake_ot_root, preset_path=Path("/some/preset.json"))

    def test_launch_gui_returns_400_when_onetrainer_not_configured(
        self, tmp_path: Path
    ) -> None:
        """POST /export/train/launch-gui returns 400 when OneTrainer is not found."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        with (
            patch(
                "klippbok.services.global_config_service.load_global_config",
                return_value={},
            ),
            patch(
                "klippbok.services.onetrainer_service.detect_onetrainer",
                return_value=None,
            ),
        ):
            resp = client.post("/api/v1/export/train/launch-gui")

        assert resp.status_code == 400
        assert "not configured" in resp.json()["detail"].lower()


class TestTrainModelsEndpoint:
    """Test GET /api/v1/export/train/models (gap 08-04-04)."""

    def test_models_returns_empty_list_when_model_dir_not_configured(
        self, tmp_path: Path
    ) -> None:
        """GET /export/train/models returns [] when no model_dir in global config."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        with patch(
            "klippbok.services.global_config_service.load_global_config",
            return_value={},
        ):
            resp = client.get("/api/v1/export/train/models")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_models_returns_safetensors_files_grouped_by_subfolder(
        self, tmp_path: Path
    ) -> None:
        """GET /export/train/models returns model files with name and subfolder."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        # Create a temp model dir with .safetensors and .ckpt files
        model_dir = tmp_path / "models"
        (model_dir / "sd15").mkdir(parents=True)
        (model_dir / "sdxl").mkdir(parents=True)
        (model_dir / "sd15" / "v1-5-pruned.safetensors").write_bytes(b"\x00" * 16)
        (model_dir / "sdxl" / "base.ckpt").write_bytes(b"\x00" * 16)
        (model_dir / "flat_model.safetensors").write_bytes(b"\x00" * 16)

        with patch(
            "klippbok.services.global_config_service.load_global_config",
            return_value={"onetrainer": {"model_dir": str(model_dir)}},
        ):
            resp = client.get("/api/v1/export/train/models")

        assert resp.status_code == 200
        models = resp.json()
        assert len(models) == 3

        names = {m["name"] for m in models}
        assert "v1-5-pruned.safetensors" in names
        assert "base.ckpt" in names
        assert "flat_model.safetensors" in names

        subfolders = {m["name"]: m["subfolder"] for m in models}
        assert subfolders["v1-5-pruned.safetensors"] == "sd15"
        assert subfolders["base.ckpt"] == "sdxl"
        assert subfolders["flat_model.safetensors"] == ""

    def test_models_returns_empty_list_when_model_dir_missing(
        self, tmp_path: Path
    ) -> None:
        """GET /export/train/models returns [] when model_dir path does not exist on disk."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        with patch(
            "klippbok.services.global_config_service.load_global_config",
            return_value={
                "onetrainer": {"model_dir": str(tmp_path / "nonexistent_models")}
            },
        ):
            resp = client.get("/api/v1/export/train/models")

        assert resp.status_code == 200
        assert resp.json() == []


class TestSettingsToolsGetEndpoint:
    """Test GET /api/v1/settings/tools (gap 08-04-05)."""

    def test_get_tools_returns_none_values_when_not_configured(
        self, tmp_path: Path
    ) -> None:
        """GET /settings/tools returns onetrainer_path=null and model_dir=null when absent."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        with patch(
            "klippbok.services.global_config_service.load_global_config",
            return_value={},
        ):
            resp = client.get("/api/v1/settings/tools")

        assert resp.status_code == 200
        data = resp.json()
        assert "onetrainer_path" in data
        assert "model_dir" in data
        assert data["onetrainer_path"] is None
        assert data["model_dir"] is None

    def test_get_tools_returns_configured_paths(self, tmp_path: Path) -> None:
        """GET /settings/tools returns configured paths from global config."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        with patch(
            "klippbok.services.global_config_service.load_global_config",
            return_value={
                "onetrainer": {
                    "onetrainer_path": "/some/onetrainer/path",
                    "model_dir": "/some/models/dir",
                }
            },
        ):
            resp = client.get("/api/v1/settings/tools")

        assert resp.status_code == 200
        data = resp.json()
        assert data["onetrainer_path"] == "/some/onetrainer/path"
        assert data["model_dir"] == "/some/models/dir"


class TestSettingsToolsPutEndpoint:
    """Test PUT /api/v1/settings/tools (gap 08-04-06)."""

    def test_put_tools_saves_valid_paths(self, tmp_path: Path) -> None:
        """PUT /settings/tools saves paths that exist on disk and returns updated values."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        # Create real directories for path-existence validation
        ot_path = tmp_path / "OneTrainer"
        ot_path.mkdir()
        model_dir = tmp_path / "models"
        model_dir.mkdir()

        saved_config: dict = {}

        def fake_save(config: dict) -> None:
            saved_config.update(config)

        with (
            patch(
                "klippbok.services.global_config_service.load_global_config",
                return_value={},
            ),
            patch(
                "klippbok.services.global_config_service.save_global_config",
                side_effect=fake_save,
            ),
        ):
            resp = client.put(
                "/api/v1/settings/tools",
                json={
                    "onetrainer_path": str(ot_path),
                    "model_dir": str(model_dir),
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["onetrainer_path"] == str(ot_path)
        assert data["model_dir"] == str(model_dir)
        # Verify the config was saved
        assert saved_config.get("onetrainer", {}).get("onetrainer_path") == str(ot_path)
        assert saved_config.get("onetrainer", {}).get("model_dir") == str(model_dir)

    def test_put_tools_returns_400_when_onetrainer_path_does_not_exist(
        self, tmp_path: Path
    ) -> None:
        """PUT /settings/tools returns 400 when onetrainer_path does not exist."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        with patch(
            "klippbok.services.global_config_service.load_global_config",
            return_value={},
        ):
            resp = client.put(
                "/api/v1/settings/tools",
                json={"onetrainer_path": str(tmp_path / "nonexistent_dir")},
            )

        assert resp.status_code == 400
        assert "does not exist" in resp.json()["detail"].lower()

    def test_put_tools_returns_400_when_model_dir_does_not_exist(
        self, tmp_path: Path
    ) -> None:
        """PUT /settings/tools returns 400 when model_dir does not exist."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        with patch(
            "klippbok.services.global_config_service.load_global_config",
            return_value={},
        ):
            resp = client.put(
                "/api/v1/settings/tools",
                json={"model_dir": str(tmp_path / "nonexistent_models")},
            )

        assert resp.status_code == 400
        assert "does not exist" in resp.json()["detail"].lower()

    def test_put_tools_with_null_values_does_not_overwrite_existing(
        self, tmp_path: Path
    ) -> None:
        """PUT /settings/tools with null fields leaves existing config values unchanged."""
        project_dir = _setup_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app)

        existing = {
            "onetrainer": {
                "onetrainer_path": "/existing/path",
                "model_dir": "/existing/models",
            }
        }
        saved_config: dict = {}

        def fake_save(config: dict) -> None:
            saved_config.update(config)

        with (
            patch(
                "klippbok.services.global_config_service.load_global_config",
                return_value=existing,
            ),
            patch(
                "klippbok.services.global_config_service.save_global_config",
                side_effect=fake_save,
            ),
        ):
            # Send nulls — neither path should be updated
            resp = client.put(
                "/api/v1/settings/tools",
                json={"onetrainer_path": None, "model_dir": None},
            )

        assert resp.status_code == 200
        data = resp.json()
        # Existing values should be preserved
        assert data["onetrainer_path"] == "/existing/path"
        assert data["model_dir"] == "/existing/models"
