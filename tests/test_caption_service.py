"""Unit tests for caption_service routing and persistence.

Tests verify:
  - get_caption_style_for_project: routes based on model profile
  - get_caption_style_for_project: caption_style_override in manifest overrides profile
  - caption_image_for_project: NL style calls _create_backend and caption_image
  - save_caption: writes sidecar .txt and updates manifest entry
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _manifest(active_profile: str = "sdxl", **extra: object) -> dict:
    """Build a minimal manifest dict for tests."""
    data: dict = {
        "version": "1",
        "active_profile": active_profile,
        "images": [],
    }
    data.update(extra)
    return data


def _manifest_with_image(
    active_profile: str = "sdxl",
    image_path: str = "images/photo.jpg",
    **extra: object,
) -> dict:
    """Build a manifest with a single image entry."""
    import hashlib

    image_id = hashlib.sha256(image_path.encode()).hexdigest()[:16]
    data: dict = {
        "version": "1",
        "active_profile": active_profile,
        "images": [
            {
                "path": image_path,
                "width": 512,
                "height": 512,
                "caption": None,
            }
        ],
    }
    data.update(extra)
    return data, image_id


# ---------------------------------------------------------------------------
# get_caption_style_for_project — routing tests
# ---------------------------------------------------------------------------


class TestGetCaptionStyleForProject:
    """Tests for model-aware caption style routing."""

    def test_caption_routing_sd15(self) -> None:
        """SD1.5 profile routes to 'booru'."""
        from klippbok.services.caption_service import get_caption_style_for_project

        manifest = _manifest(active_profile="sd15")
        style = get_caption_style_for_project(manifest)
        assert style == "booru", f"SD1.5 should route to booru, got '{style}'"

    def test_caption_routing_sdxl(self) -> None:
        """SDXL profile routes to 'natural_language'."""
        from klippbok.services.caption_service import get_caption_style_for_project

        manifest = _manifest(active_profile="sdxl")
        style = get_caption_style_for_project(manifest)
        assert style == "natural_language", f"SDXL should route to natural_language, got '{style}'"

    def test_caption_routing_flux(self) -> None:
        """Flux profile routes to 'natural_language'."""
        from klippbok.services.caption_service import get_caption_style_for_project

        manifest = _manifest(active_profile="flux")
        style = get_caption_style_for_project(manifest)
        assert style == "natural_language", f"Flux should route to natural_language, got '{style}'"

    def test_caption_routing_pony(self) -> None:
        """Pony profile routes to 'booru'."""
        from klippbok.services.caption_service import get_caption_style_for_project

        manifest = _manifest(active_profile="pony")
        style = get_caption_style_for_project(manifest)
        assert style == "booru", f"Pony should route to booru, got '{style}'"

    def test_default_profile_fallback(self) -> None:
        """Manifest without active_profile defaults to sdxl (natural_language)."""
        from klippbok.services.caption_service import get_caption_style_for_project

        manifest = {"version": "1", "images": []}  # no active_profile key
        style = get_caption_style_for_project(manifest)
        assert style == "natural_language", (
            f"Missing active_profile should default to sdxl (natural_language), got '{style}'"
        )

    def test_unknown_profile_fallback(self) -> None:
        """Unknown profile name falls back to 'natural_language' (safe default)."""
        from klippbok.services.caption_service import get_caption_style_for_project

        manifest = _manifest(active_profile="does_not_exist_xyzzy")
        style = get_caption_style_for_project(manifest)
        assert style == "natural_language", (
            f"Unknown profile should default to natural_language, got '{style}'"
        )


# ---------------------------------------------------------------------------
# get_caption_style_for_project — override tests
# ---------------------------------------------------------------------------


class TestCaptionStyleOverride:
    """Tests for caption_style_override taking precedence over profile."""

    def test_style_override_booru(self) -> None:
        """caption_style_override='booru' overrides SDXL (natural_language) profile."""
        from klippbok.services.caption_service import get_caption_style_for_project

        manifest = _manifest(
            active_profile="sdxl",
            caption_style_override="booru",
        )
        style = get_caption_style_for_project(manifest)
        assert style == "booru", (
            f"caption_style_override='booru' should override sdxl default, got '{style}'"
        )

    def test_style_override_nl(self) -> None:
        """caption_style_override='natural_language' overrides SD1.5 (booru) profile."""
        from klippbok.services.caption_service import get_caption_style_for_project

        manifest = _manifest(
            active_profile="sd15",
            caption_style_override="natural_language",
        )
        style = get_caption_style_for_project(manifest)
        assert style == "natural_language", (
            f"caption_style_override='natural_language' should override sd15 default, got '{style}'"
        )

    def test_style_override_invalid_ignored(self) -> None:
        """Invalid caption_style_override value is ignored; falls back to profile."""
        from klippbok.services.caption_service import get_caption_style_for_project

        manifest = _manifest(
            active_profile="sd15",
            caption_style_override="invalid_value",
        )
        style = get_caption_style_for_project(manifest)
        assert style == "booru", (
            f"Invalid override should be ignored, sd15 profile is 'booru', got '{style}'"
        )


# ---------------------------------------------------------------------------
# caption_image_for_project — NL backend test
# ---------------------------------------------------------------------------


class TestCaptionImageForProject:
    """Tests for caption_image_for_project routing to correct backend."""

    def test_nl_caption_calls_backend(self, tmp_path: Path) -> None:
        """NL caption style calls _create_backend and backend.caption_image."""
        from klippbok.caption.models import CaptionConfig
        from klippbok.services.caption_service import caption_image_for_project

        # Create a dummy image file on disk
        image_path = tmp_path / "photo.jpg"
        image_path.write_bytes(b"fake-image")

        manifest = _manifest(active_profile="sdxl")
        vlm_config = CaptionConfig(provider="gemini", api_key="test_key")

        mock_backend = MagicMock()
        mock_backend.caption_image.return_value = "a woman in a red dress"

        with patch("klippbok.services.caption_service.get_caption_style_for_project", return_value="natural_language"), \
             patch("klippbok.caption.captioner._create_backend", return_value=mock_backend):
            result = caption_image_for_project(image_path, manifest, vlm_config)

        assert result == "a woman in a red dress", f"Got '{result}'"
        mock_backend.caption_image.assert_called_once()

    def test_nl_caption_requires_vlm_config(self, tmp_path: Path) -> None:
        """NL captioning raises ValueError if vlm_config is None."""
        from klippbok.services.caption_service import caption_image_for_project

        image_path = tmp_path / "photo.jpg"
        image_path.write_bytes(b"fake-image")

        manifest = _manifest(active_profile="sdxl")

        with patch("klippbok.services.caption_service.get_caption_style_for_project", return_value="natural_language"):
            with pytest.raises(ValueError, match="vlm_config is required"):
                caption_image_for_project(image_path, manifest, vlm_config=None)

    def test_booru_caption_calls_tag_image_booru(self, tmp_path: Path) -> None:
        """Booru caption style calls tag_image_booru and joins tags with chars first."""
        from klippbok.services.caption_service import caption_image_for_project

        image_path = tmp_path / "photo.jpg"
        image_path.write_bytes(b"fake-image")

        manifest = _manifest(active_profile="sd15")

        # Patch both the style routing and the WD tagger at its module location.
        # tag_image_booru is lazy-imported inside caption_image_for_project, so
        # patching the module attribute is the correct approach.
        with patch("klippbok.services.caption_service.get_caption_style_for_project", return_value="booru"), \
             patch("klippbok.caption.wd_tagger.tag_image_booru", return_value=(["1girl", "solo"], ["char_name"])):
            result = caption_image_for_project(image_path, manifest, vlm_config=None)

        # char_tags first + general_tags joined
        assert result == "char_name, 1girl, solo", f"Expected 'char_name, 1girl, solo', got '{result}'"


# ---------------------------------------------------------------------------
# save_caption — sidecar and manifest tests
# ---------------------------------------------------------------------------


class TestSaveCaption:
    """Tests for save_caption writing sidecar .txt and updating manifest."""

    def test_save_caption_writes_sidecar(self, tmp_path: Path) -> None:
        """save_caption writes a .txt sidecar file alongside the image."""
        from klippbok.services.caption_service import save_caption

        image_path = tmp_path / "photo.jpg"
        image_path.write_bytes(b"fake-image")

        import hashlib
        image_id = hashlib.sha256("images/photo.jpg".encode()).hexdigest()[:16]

        manifest = {
            "version": "1",
            "images": [{"path": "images/photo.jpg", "caption": None}],
        }

        save_caption(image_path, "1girl, solo", manifest, image_id)

        sidecar = tmp_path / "photo.txt"
        assert sidecar.exists(), "Sidecar .txt file should be created by save_caption"
        assert sidecar.read_text(encoding="utf-8") == "1girl, solo", (
            f"Sidecar content mismatch: got '{sidecar.read_text()}'"
        )

    def test_save_caption_updates_manifest_entry(self, tmp_path: Path) -> None:
        """save_caption updates the caption field in the matching manifest entry."""
        from klippbok.services.caption_service import save_caption

        image_path = tmp_path / "photo.jpg"
        image_path.write_bytes(b"fake-image")

        import hashlib
        image_id = hashlib.sha256("images/photo.jpg".encode()).hexdigest()[:16]

        manifest = {
            "version": "1",
            "images": [{"path": "images/photo.jpg", "caption": None}],
        }

        save_caption(image_path, "wide shot, woman walks", manifest, image_id)

        # Manifest entry should be updated in place
        entry = manifest["images"][0]
        assert entry["caption"] == "wide shot, woman walks", (
            f"Manifest entry caption should be updated, got '{entry['caption']}'"
        )

    def test_save_caption_only_updates_matching_entry(self, tmp_path: Path) -> None:
        """save_caption only updates the entry with matching image_id; others are untouched."""
        from klippbok.services.caption_service import save_caption

        image_path = tmp_path / "photo.jpg"
        image_path.write_bytes(b"fake-image")

        import hashlib
        target_id = hashlib.sha256("images/photo.jpg".encode()).hexdigest()[:16]

        manifest = {
            "version": "1",
            "images": [
                {"path": "images/photo.jpg", "caption": None},
                {"path": "images/other.jpg", "caption": "existing caption"},
            ],
        }

        save_caption(image_path, "new caption", manifest, target_id)

        assert manifest["images"][0]["caption"] == "new caption"
        assert manifest["images"][1]["caption"] == "existing caption", (
            "Other manifest entries must not be modified"
        )

    def test_save_caption_overwrites_existing_caption(self, tmp_path: Path) -> None:
        """save_caption replaces an existing caption with the new value."""
        from klippbok.services.caption_service import save_caption

        image_path = tmp_path / "photo.jpg"
        image_path.write_bytes(b"fake-image")

        import hashlib
        image_id = hashlib.sha256("images/photo.jpg".encode()).hexdigest()[:16]

        manifest = {
            "version": "1",
            "images": [{"path": "images/photo.jpg", "caption": "old caption"}],
        }

        save_caption(image_path, "new caption", manifest, image_id)

        assert manifest["images"][0]["caption"] == "new caption"
        sidecar = tmp_path / "photo.txt"
        assert sidecar.read_text(encoding="utf-8") == "new caption"
