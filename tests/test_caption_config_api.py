"""Integration tests for caption config API endpoints (Phase 6.1).

Tests verify:
  - GET  /api/v1/captions/config: Returns CaptionProviderConfig with defaults
  - PUT  /api/v1/captions/config: Partial update preserves unset fields
  - GET  /api/v1/captions/models: Lists models for each provider
  - GET  /api/v1/captions/health: Probes provider connectivity
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Patch targets — deferred imports in captions.py mean we patch at the source module
_LOAD_CFG = "klippbok.services.global_config_service.load_global_config"
_SAVE_CFG = "klippbok.services.global_config_service.save_global_config"
_REQUESTS_GET = "requests.get"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """TestClient with no project_dir — config endpoints don't need one."""
    from klippbok.api.app import create_app

    app = create_app(project_dir=None)
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# GET /api/v1/captions/config
# ---------------------------------------------------------------------------


class TestGetConfig:
    def test_returns_defaults_when_no_config_file(self, client: TestClient) -> None:
        """GET /config returns CaptionProviderConfig defaults when global config is empty."""
        with patch(_LOAD_CFG, return_value={}):
            resp = client.get("/api/v1/captions/config")

        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "lm_studio"
        assert data["lm_studio_base_url"] == "http://localhost:1234/v1"
        assert data["nanogpt_api_key"] == ""
        assert data["gemini_model"] == "gemini-2.5-flash"

    def test_returns_stored_values(self, client: TestClient) -> None:
        """GET /config returns values from global config when present."""
        stored = {
            "provider": "nanogpt",
            "nanogpt_api_key": "sk-secret",
            "nanogpt_model": "Gemma-3-27B-it",
        }
        with patch(_LOAD_CFG, return_value=stored):
            resp = client.get("/api/v1/captions/config")

        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "nanogpt"
        assert data["nanogpt_api_key"] == "sk-secret"
        assert data["nanogpt_model"] == "Gemma-3-27B-it"
        # Unstored fields still get defaults
        assert data["lm_studio_base_url"] == "http://localhost:1234/v1"

    def test_auto_detects_joycaption_when_not_configured(self, client: TestClient) -> None:
        """GET /config auto-detects JoyCaption path when not in global config."""
        with (
            patch(_LOAD_CFG, return_value={}),
            patch(
                "klippbok.caption.joycaption.detect_joycaption",
                return_value="/opt/joycaption",
            ),
        ):
            resp = client.get("/api/v1/captions/config")

        assert resp.status_code == 200
        assert resp.json()["joycaption_path"] == "/opt/joycaption"


# ---------------------------------------------------------------------------
# PUT /api/v1/captions/config
# ---------------------------------------------------------------------------


class TestPutConfig:
    def test_saves_partial_update(self, client: TestClient) -> None:
        """PUT /config with partial body only updates sent fields."""
        existing = {"provider": "lm_studio", "nanogpt_api_key": "sk-keep-me"}
        saved = {}

        def mock_save(cfg: dict) -> None:
            saved.update(cfg)

        with (
            patch(_LOAD_CFG, return_value=existing.copy()),
            patch(_SAVE_CFG, side_effect=mock_save),
        ):
            resp = client.put(
                "/api/v1/captions/config",
                json={"provider": "nanogpt", "nanogpt_model": "Gemma-3-27B-it"},
            )

        assert resp.status_code == 200
        # API key must survive partial update
        assert saved["nanogpt_api_key"] == "sk-keep-me"
        assert saved["provider"] == "nanogpt"
        assert saved["nanogpt_model"] == "Gemma-3-27B-it"

    def test_returns_merged_config(self, client: TestClient) -> None:
        """PUT /config returns the full merged config, not just the sent fields."""
        with (
            patch(_LOAD_CFG, return_value={"gemini_api_key": "gk-existing"}),
            patch(_SAVE_CFG),
        ):
            resp = client.put(
                "/api/v1/captions/config",
                json={"provider": "gemini"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "gemini"
        assert data["gemini_api_key"] == "gk-existing"
        # All fields present in response
        assert "lm_studio_base_url" in data
        assert "nanogpt_model" in data


# ---------------------------------------------------------------------------
# GET /api/v1/captions/models
# ---------------------------------------------------------------------------


class TestGetModels:
    def test_gemini_returns_static_list(self, client: TestClient) -> None:
        """GET /models?provider=gemini returns static model list."""
        resp = client.get("/api/v1/captions/models?provider=gemini")
        assert resp.status_code == 200
        data = resp.json()
        assert "gemini-2.5-flash" in data["models"]
        assert "gemini-2.0-flash" in data["models"]

    def test_joycaption_returns_static_list(self, client: TestClient) -> None:
        """GET /models?provider=joycaption returns static model list."""
        resp = client.get("/api/v1/captions/models?provider=joycaption")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["models"]) == 1
        assert "joycaption" in data["models"][0].lower()

    def test_unknown_provider_returns_empty_with_message(self, client: TestClient) -> None:
        """GET /models?provider=unknown returns empty list with error message."""
        resp = client.get("/api/v1/captions/models?provider=unknown_provider")
        assert resp.status_code == 200
        data = resp.json()
        assert data["models"] == []
        assert "Unknown provider" in data["message"]

    def test_lm_studio_connection_error(self, client: TestClient) -> None:
        """GET /models?provider=lm_studio returns graceful error when not running."""
        import requests

        with (
            patch(_LOAD_CFG, return_value={}),
            patch(_REQUESTS_GET, side_effect=requests.exceptions.ConnectionError("refused")),
        ):
            resp = client.get("/api/v1/captions/models?provider=lm_studio")

        assert resp.status_code == 200
        data = resp.json()
        assert data["models"] == []
        assert "Could not connect" in data["message"]

    def test_lm_studio_success(self, client: TestClient) -> None:
        """GET /models?provider=lm_studio returns model list on success."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [{"id": "llava-1.5-13b"}, {"id": "qwen-vl-7b"}]
        }
        mock_resp.raise_for_status = MagicMock()

        with (
            patch(_LOAD_CFG, return_value={}),
            patch(_REQUESTS_GET, return_value=mock_resp),
        ):
            resp = client.get("/api/v1/captions/models?provider=lm_studio")

        assert resp.status_code == 200
        data = resp.json()
        assert data["models"] == ["llava-1.5-13b", "qwen-vl-7b"]

    def test_nanogpt_no_api_key(self, client: TestClient) -> None:
        """GET /models?provider=nanogpt returns message when API key is missing."""
        with patch(_LOAD_CFG, return_value={}):
            resp = client.get("/api/v1/captions/models?provider=nanogpt")

        assert resp.status_code == 200
        data = resp.json()
        assert data["models"] == []
        assert "API key" in data["message"]

    def test_nanogpt_filters_vlm_models(self, client: TestClient) -> None:
        """GET /models?provider=nanogpt returns only vision-capable models."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"id": "Gemma-3-27B-it"},        # VLM (gemma-3 pattern)
                {"id": "gpt-4o"},                  # NOT VLM
                {"id": "qwen25-vl-72b-instruct"},  # VLM (-vl- pattern)
                {"id": "llama-3.1-8b"},            # NOT VLM
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with (
            patch(_LOAD_CFG, return_value={"nanogpt_api_key": "sk-test"}),
            patch(_REQUESTS_GET, return_value=mock_resp),
        ):
            resp = client.get("/api/v1/captions/models?provider=nanogpt")

        assert resp.status_code == 200
        models = resp.json()["models"]
        assert "Gemma-3-27B-it" in models
        assert "qwen25-vl-72b-instruct" in models
        assert "gpt-4o" not in models
        assert "llama-3.1-8b" not in models


# ---------------------------------------------------------------------------
# GET /api/v1/captions/health
# ---------------------------------------------------------------------------


class TestGetHealth:
    def test_lm_studio_healthy(self, client: TestClient) -> None:
        """GET /health?provider=lm_studio returns healthy when reachable."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"id": "model-1"}]}
        mock_resp.raise_for_status = MagicMock()

        with (
            patch(_LOAD_CFG, return_value={}),
            patch(_REQUESTS_GET, return_value=mock_resp),
        ):
            resp = client.get("/api/v1/captions/health?provider=lm_studio")

        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is True
        assert "1 model" in data["message"]

    def test_lm_studio_unreachable(self, client: TestClient) -> None:
        """GET /health?provider=lm_studio returns unhealthy when connection refused."""
        import requests

        with (
            patch(_LOAD_CFG, return_value={}),
            patch(_REQUESTS_GET, side_effect=requests.exceptions.ConnectionError()),
        ):
            resp = client.get("/api/v1/captions/health?provider=lm_studio")

        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is False
        assert "Cannot connect" in data["message"]

    def test_nanogpt_no_key(self, client: TestClient) -> None:
        """GET /health?provider=nanogpt returns unhealthy when no API key."""
        with patch(_LOAD_CFG, return_value={}):
            resp = client.get("/api/v1/captions/health?provider=nanogpt")

        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is False
        assert "API key" in data["message"]

    def test_gemini_no_key(self, client: TestClient) -> None:
        """GET /health?provider=gemini returns unhealthy when no API key."""
        with patch(_LOAD_CFG, return_value={}):
            resp = client.get("/api/v1/captions/health?provider=gemini")

        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is False
        assert "API key" in data["message"]

    def test_joycaption_auto_detect(self, client: TestClient) -> None:
        """GET /health?provider=joycaption auto-detects path when not configured."""
        with (
            patch(_LOAD_CFG, return_value={}),
            patch(
                "klippbok.caption.joycaption.detect_joycaption",
                return_value="/opt/joycaption",
            ),
        ):
            resp = client.get("/api/v1/captions/health?provider=joycaption")

        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is True
        assert "/opt/joycaption" in data["message"]

    def test_joycaption_not_found(self, client: TestClient) -> None:
        """GET /health?provider=joycaption returns unhealthy when not detected."""
        with (
            patch(_LOAD_CFG, return_value={}),
            patch(
                "klippbok.caption.joycaption.detect_joycaption",
                return_value=None,
            ),
        ):
            resp = client.get("/api/v1/captions/health?provider=joycaption")

        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is False

    def test_unknown_provider(self, client: TestClient) -> None:
        """GET /health?provider=unknown returns unhealthy."""
        resp = client.get("/api/v1/captions/health?provider=unknown")
        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is False
        assert "Unknown provider" in data["message"]


# ---------------------------------------------------------------------------
# VLM filter unit test
# ---------------------------------------------------------------------------


class TestNanoGPTVLMFilter:
    """Direct tests for _filter_nanogpt_vlm_models."""

    def test_filters_by_pattern(self) -> None:
        from klippbok.api.routers.captions import _filter_nanogpt_vlm_models

        models = ["Gemma-3-27B-it", "gpt-4o", "phi-4-multimodal-instruct", "llama-3.1-8b"]
        result = _filter_nanogpt_vlm_models(models)
        assert "Gemma-3-27B-it" in result
        assert "phi-4-multimodal-instruct" in result
        assert "gpt-4o" not in result
        assert "llama-3.1-8b" not in result

    def test_filters_explicit_set(self) -> None:
        from klippbok.api.routers.captions import _filter_nanogpt_vlm_models

        models = ["qvq-max", "some-text-model"]
        result = _filter_nanogpt_vlm_models(models)
        assert "qvq-max" in result
        assert "some-text-model" not in result
