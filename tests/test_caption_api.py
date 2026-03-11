"""Integration tests for caption API endpoints.

Tests verify:
  - PATCH /api/v1/captions/{image_id}: Updates caption in manifest + sidecar .txt
  - PATCH with invalid image_id: Returns 404
  - GET /api/v1/settings/profiles: Returns available model profiles
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from klippbok.utils.paths import image_id as _image_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path, image_filename: str = "photo.jpg") -> tuple[Path, str]:
    """Create a minimal project directory with manifest and dummy image.

    Returns:
        Tuple of (project_dir, image_id).
    """
    # Create project structure
    klippbok_dir = tmp_path / ".klippbok"
    klippbok_dir.mkdir(parents=True)

    # Create a minimal 1x1 JPEG image so the PATCH endpoint can find it on disk
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    image_path = images_dir / image_filename

    # Write a minimal valid JPEG (smallest possible)
    jpeg_bytes = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
        b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
        b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1e"
        b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
        b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
        b"\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04"
        b"\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa"
        b"\x07\"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br"
        b"\x82\t\n\x16\x17\x18\x19\x1a%&'()*456789:CDEFGHIJSTUVWXYZ"
        b"cdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95"
        b"\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3"
        b"\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca"
        b"\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7"
        b"\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa"
        b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xd4P\x00\x00\x00\x1f\xff\xd9"
    )
    image_path.write_bytes(jpeg_bytes)

    relative_path = f"images/{image_filename}"
    img_id = _image_id(relative_path)

    # Write manifest
    manifest = {
        "version": "1",
        "active_profile": "sdxl",
        "images": [
            {
                "path": relative_path,
                "width": 512,
                "height": 512,
                "caption": None,
                "resolution_ok": True,
                "quality_pass": True,
                "bucket": "512x512",
                "is_near_duplicate": False,
                "duplicate_group_id": None,
            }
        ],
    }
    manifest_path = klippbok_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    return tmp_path, img_id


# ---------------------------------------------------------------------------
# PATCH /api/v1/captions/{image_id}
# ---------------------------------------------------------------------------


class TestUpdateCaption:
    def test_update_caption_success(self, tmp_path: Path) -> None:
        """PATCH with valid image_id updates caption in manifest and writes sidecar."""
        from klippbok.api.app import create_app

        project_dir, img_id = _make_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.patch(
            f"/api/v1/captions/{img_id}",
            json={"caption": "1girl, smile, white background"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["image_id"] == img_id
        assert data["caption"] == "1girl, smile, white background"
        assert data["sidecar_written"] is True

        # Verify manifest updated
        manifest_path = project_dir / ".klippbok" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        images = manifest["images"]
        assert len(images) == 1
        assert images[0]["caption"] == "1girl, smile, white background"

        # Verify sidecar .txt written
        sidecar_path = project_dir / "images" / "photo.txt"
        assert sidecar_path.exists()
        assert sidecar_path.read_text(encoding="utf-8") == "1girl, smile, white background"

    def test_update_caption_not_found(self, tmp_path: Path) -> None:
        """PATCH with invalid image_id returns 404."""
        from klippbok.api.app import create_app

        project_dir, _ = _make_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.patch(
            "/api/v1/captions/deadbeefdeadbeef",
            json={"caption": "should not save"},
        )
        assert resp.status_code == 404

    def test_update_caption_no_project(self) -> None:
        """PATCH without active project returns 409."""
        from klippbok.api.app import create_app

        app = create_app(project_dir=None)
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.patch(
            "/api/v1/captions/anyid",
            json={"caption": "test"},
        )
        assert resp.status_code == 409

    def test_update_caption_overwrites_existing(self, tmp_path: Path) -> None:
        """PATCH can overwrite an existing caption."""
        from klippbok.api.app import create_app

        project_dir, img_id = _make_project(tmp_path)

        # Pre-populate manifest with an existing caption
        manifest_path = project_dir / ".klippbok" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["images"][0]["caption"] = "old caption"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        app = create_app(project_dir=project_dir)
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.patch(
            f"/api/v1/captions/{img_id}",
            json={"caption": "new caption"},
        )
        assert resp.status_code == 200
        assert resp.json()["caption"] == "new caption"

        # Manifest must reflect new caption
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["images"][0]["caption"] == "new caption"


# ---------------------------------------------------------------------------
# GET /api/v1/settings/profiles
# ---------------------------------------------------------------------------


class TestAnchorWord:
    def test_put_anchor_word_persists_to_manifest(self, tmp_path: Path) -> None:
        """PUT /settings/ with anchor_word saves it to the project manifest."""
        from klippbok.api.app import create_app

        project_dir, _ = _make_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.put("/api/v1/settings/", json={"anchor_word": "ohwx person"})
        assert resp.status_code == 200

        # Verify manifest has anchor_word
        manifest_path = project_dir / ".klippbok" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["anchor_word"] == "ohwx person"

    def test_get_settings_returns_anchor_word(self, tmp_path: Path) -> None:
        """GET /settings/ returns anchor_word from manifest."""
        from klippbok.api.app import create_app

        project_dir, _ = _make_project(tmp_path)

        # Pre-populate manifest with anchor_word
        manifest_path = project_dir / ".klippbok" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["anchor_word"] = "sks woman"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        app = create_app(project_dir=project_dir)
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.get("/api/v1/settings/")
        assert resp.status_code == 200
        assert resp.json()["anchor_word"] == "sks woman"

    def test_get_settings_anchor_word_absent(self, tmp_path: Path) -> None:
        """GET /settings/ returns null anchor_word when not in manifest."""
        from klippbok.api.app import create_app

        project_dir, _ = _make_project(tmp_path)
        app = create_app(project_dir=project_dir)
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.get("/api/v1/settings/")
        assert resp.status_code == 200
        assert resp.json()["anchor_word"] is None


class TestListProfiles:
    def test_list_profiles_returns_expected_profiles(self) -> None:
        """GET /api/v1/settings/profiles returns sd15, sdxl, flux, and pony."""
        from klippbok.api.app import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.get("/api/v1/settings/profiles")
        assert resp.status_code == 200
        profiles = resp.json()
        assert isinstance(profiles, list)
        assert len(profiles) >= 4

        names = {p["name"] for p in profiles}
        assert "sd15" in names
        assert "sdxl" in names
        assert "flux" in names
        assert "pony" in names

    def test_list_profiles_schema(self) -> None:
        """Each profile has name, display_name, caption_style, base_resolution."""
        from klippbok.api.app import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.get("/api/v1/settings/profiles")
        assert resp.status_code == 200
        profiles = resp.json()
        assert len(profiles) > 0

        for profile in profiles:
            assert "name" in profile
            assert "display_name" in profile
            assert "caption_style" in profile
            assert "base_resolution" in profile
            assert isinstance(profile["name"], str)
            assert isinstance(profile["display_name"], str)
            assert profile["caption_style"] in ("booru", "natural_language")
            assert isinstance(profile["base_resolution"], int)
            assert profile["base_resolution"] > 0

    def test_list_profiles_no_project_required(self) -> None:
        """Profiles endpoint works even with no active project."""
        from klippbok.api.app import create_app

        app = create_app(project_dir=None)
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.get("/api/v1/settings/profiles")
        assert resp.status_code == 200
        assert len(resp.json()) >= 4
