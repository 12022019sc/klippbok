"""Integration tests for POST /triage/concepts/upload endpoint.

Tests verify:
  - POST /api/v1/triage/concepts/upload with a valid file + category returns 200
    with concept reference dict (name, concept_type, image_path, folder_name)
  - Uploaded file is physically saved to {project_dir}/concepts/{category}/{filename}
  - POST /api/v1/triage/concepts/upload without a project_dir returns 409
  - POST /api/v1/triage/concepts/upload with missing category returns 422
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Minimal valid PNG bytes (1x1 pixel, RGB)
# ---------------------------------------------------------------------------

def _minimal_png() -> bytes:
    """Return a minimal valid 1x1 PNG in bytes (no Pillow required)."""
    # This is a hard-coded 1x1 red pixel PNG
    return (
        b"\x89PNG\r\n\x1a\n"                    # PNG signature
        b"\x00\x00\x00\rIHDR"                   # IHDR chunk length + type
        b"\x00\x00\x00\x01"                     # width = 1
        b"\x00\x00\x00\x01"                     # height = 1
        b"\x08\x02"                             # bit depth=8, color type=2 (RGB)
        b"\x00\x00\x00"                         # compression, filter, interlace
        b"\x90wS\xde"                           # CRC
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f" # IDAT chunk
        b"\x00\x01\x01\x00\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"      # IEND chunk
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal project directory structure."""
    klippbok_dir = tmp_path / ".klippbok"
    klippbok_dir.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def client(project_dir: Path) -> TestClient:
    """Create a test client with a project directory set."""
    from klippbok.api.app import create_app
    app = create_app(project_dir=project_dir)
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def client_no_project() -> TestClient:
    """Create a test client without any project directory."""
    from klippbok.api.app import create_app
    app = create_app(project_dir=None)
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Test: successful upload
# ---------------------------------------------------------------------------

class TestConceptsUpload:

    def test_upload_returns_200_with_concept_reference(
        self, client: TestClient, project_dir: Path
    ) -> None:
        """POST /triage/concepts/upload returns 200 with concept reference dict."""
        png_bytes = _minimal_png()
        response = client.post(
            "/api/v1/triage/concepts/upload",
            files={"file": ("test_ref.png", io.BytesIO(png_bytes), "image/png")},
            data={"category": "character"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "concept_type" in data
        assert "image_path" in data
        assert "folder_name" in data
        assert data["folder_name"] == "character"
        assert data["name"] == "test_ref"

    def test_upload_saves_file_to_concepts_directory(
        self, client: TestClient, project_dir: Path
    ) -> None:
        """POST /triage/concepts/upload saves the file to concepts/{category}/{filename}."""
        png_bytes = _minimal_png()
        client.post(
            "/api/v1/triage/concepts/upload",
            files={"file": ("uploaded.png", io.BytesIO(png_bytes), "image/png")},
            data={"category": "character"},
        )
        saved_path = project_dir / "concepts" / "character" / "uploaded.png"
        assert saved_path.exists(), f"Expected file at {saved_path} but it does not exist"
        assert saved_path.stat().st_size > 0

    def test_upload_creates_category_directory_if_missing(
        self, client: TestClient, project_dir: Path
    ) -> None:
        """POST /triage/concepts/upload creates the category directory if it doesn't exist."""
        concepts_dir = project_dir / "concepts" / "setting"
        assert not concepts_dir.exists()

        png_bytes = _minimal_png()
        response = client.post(
            "/api/v1/triage/concepts/upload",
            files={"file": ("bg.png", io.BytesIO(png_bytes), "image/png")},
            data={"category": "setting"},
        )
        assert response.status_code == 200
        assert concepts_dir.exists()
        assert (concepts_dir / "bg.png").exists()

    def test_upload_returns_409_when_no_project_dir(
        self, client_no_project: TestClient
    ) -> None:
        """POST /triage/concepts/upload returns 409 if no project_dir is set."""
        png_bytes = _minimal_png()
        response = client_no_project.post(
            "/api/v1/triage/concepts/upload",
            files={"file": ("test.png", io.BytesIO(png_bytes), "image/png")},
            data={"category": "character"},
        )
        assert response.status_code == 409

    def test_upload_returns_422_when_category_missing(
        self, client: TestClient
    ) -> None:
        """POST /triage/concepts/upload returns 422 if category field is absent."""
        png_bytes = _minimal_png()
        response = client.post(
            "/api/v1/triage/concepts/upload",
            files={"file": ("test.png", io.BytesIO(png_bytes), "image/png")},
            # No 'category' data field
        )
        assert response.status_code == 422

    def test_upload_returns_422_when_file_missing(
        self, client: TestClient
    ) -> None:
        """POST /triage/concepts/upload returns 422 if file is absent."""
        response = client.post(
            "/api/v1/triage/concepts/upload",
            data={"category": "character"},
            # No file
        )
        assert response.status_code == 422
