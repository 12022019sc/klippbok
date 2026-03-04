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


# ---------------------------------------------------------------------------
# Batch operations -- helpers
# ---------------------------------------------------------------------------


def _make_manifest_with_images(
    tmp_path: Path,
    entries: list[tuple[str, str | None]],
) -> tuple[dict, Path]:
    """Build a manifest with multiple image entries and create dummy files.

    Args:
        tmp_path: Pytest temporary directory.
        entries: List of (relative_path, caption_or_None) tuples.

    Returns:
        (manifest_dict, project_dir) where project_dir == tmp_path.
    """
    images = []
    for rel_path, caption in entries:
        # Create the dummy image file on disk
        abs_path = tmp_path / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(b"fake-image")
        images.append({"path": rel_path, "caption": caption})

    manifest: dict = {
        "version": "1",
        "active_profile": "sd15",
        "images": images,
    }
    return manifest, tmp_path


# ---------------------------------------------------------------------------
# batch_add_tag tests
# ---------------------------------------------------------------------------


class TestBatchAddTag:
    """Tests for batch_add_tag() adding a tag to all/selected captions."""

    def test_batch_add_tag(self, tmp_path: Path) -> None:
        """Adds tag to all captions; each caption ends with ', blue_eyes'."""
        from klippbok.services.caption_service import batch_add_tag

        manifest, project_dir = _make_manifest_with_images(tmp_path, [
            ("img/a.jpg", "1girl, solo"),
            ("img/b.jpg", "1boy, outdoors"),
        ])
        count = batch_add_tag("blue_eyes", manifest, project_dir)

        assert count == 2
        assert manifest["images"][0]["caption"] == "1girl, solo, blue_eyes"
        assert manifest["images"][1]["caption"] == "1boy, outdoors, blue_eyes"

    def test_batch_add_tag_already_present(self, tmp_path: Path) -> None:
        """Tag already present in caption is NOT duplicated."""
        from klippbok.services.caption_service import batch_add_tag

        manifest, project_dir = _make_manifest_with_images(tmp_path, [
            ("img/a.jpg", "1girl, blue_eyes, solo"),
            ("img/b.jpg", "1boy, brown_eyes"),
        ])
        count = batch_add_tag("blue_eyes", manifest, project_dir)

        # Only b.jpg should be modified
        assert count == 1
        assert manifest["images"][0]["caption"] == "1girl, blue_eyes, solo"
        assert manifest["images"][1]["caption"] == "1boy, brown_eyes, blue_eyes"

    def test_batch_add_tag_writes_sidecar(self, tmp_path: Path) -> None:
        """batch_add_tag writes sidecar .txt files for each modified image."""
        from klippbok.services.caption_service import batch_add_tag

        manifest, project_dir = _make_manifest_with_images(tmp_path, [
            ("img/a.jpg", "1girl, solo"),
        ])
        batch_add_tag("blue_eyes", manifest, project_dir)

        sidecar = tmp_path / "img" / "a.txt"
        assert sidecar.exists(), "Sidecar .txt should be written by batch_add_tag"
        assert sidecar.read_text(encoding="utf-8") == "1girl, solo, blue_eyes"


# ---------------------------------------------------------------------------
# batch_remove_tag tests
# ---------------------------------------------------------------------------


class TestBatchRemoveTag:
    """Tests for batch_remove_tag() removing a tag from all/selected captions."""

    def test_batch_remove_tag(self, tmp_path: Path) -> None:
        """Removes tag from all captions; tag is gone, no trailing commas."""
        from klippbok.services.caption_service import batch_remove_tag

        manifest, project_dir = _make_manifest_with_images(tmp_path, [
            ("img/a.jpg", "1girl, solo, blue_eyes"),
            ("img/b.jpg", "1boy, solo, outdoors"),
        ])
        count = batch_remove_tag("solo", manifest, project_dir)

        assert count == 2
        assert manifest["images"][0]["caption"] == "1girl, blue_eyes"
        assert manifest["images"][1]["caption"] == "1boy, outdoors"

    def test_batch_remove_tag_writes_sidecar(self, tmp_path: Path) -> None:
        """batch_remove_tag writes sidecar .txt files for each modified image."""
        from klippbok.services.caption_service import batch_remove_tag

        manifest, project_dir = _make_manifest_with_images(tmp_path, [
            ("img/a.jpg", "1girl, solo"),
        ])
        batch_remove_tag("solo", manifest, project_dir)

        sidecar = tmp_path / "img" / "a.txt"
        assert sidecar.exists()
        assert sidecar.read_text(encoding="utf-8") == "1girl"


# ---------------------------------------------------------------------------
# batch_replace_tag tests
# ---------------------------------------------------------------------------


class TestBatchReplaceTag:
    """Tests for batch_replace_tag() replacing one tag with another."""

    def test_batch_replace_tag(self, tmp_path: Path) -> None:
        """Replaces old_tag with new_tag across all captions."""
        from klippbok.services.caption_service import batch_replace_tag

        manifest, project_dir = _make_manifest_with_images(tmp_path, [
            ("img/a.jpg", "1girl, solo, blue_hair"),
            ("img/b.jpg", "1girl, outdoors"),
        ])
        count = batch_replace_tag("1girl", "1boy", manifest, project_dir)

        assert count == 2
        assert manifest["images"][0]["caption"] == "1boy, solo, blue_hair"
        assert manifest["images"][1]["caption"] == "1boy, outdoors"

    def test_batch_replace_tag_not_found(self, tmp_path: Path) -> None:
        """Replacing a non-existent tag is a no-op (no error, count=0)."""
        from klippbok.services.caption_service import batch_replace_tag

        manifest, project_dir = _make_manifest_with_images(tmp_path, [
            ("img/a.jpg", "1girl, solo"),
        ])
        count = batch_replace_tag("nonexistent_tag", "something", manifest, project_dir)

        assert count == 0
        assert manifest["images"][0]["caption"] == "1girl, solo"

    def test_batch_replace_tag_writes_sidecar(self, tmp_path: Path) -> None:
        """batch_replace_tag writes sidecar .txt files for modified images."""
        from klippbok.services.caption_service import batch_replace_tag

        manifest, project_dir = _make_manifest_with_images(tmp_path, [
            ("img/a.jpg", "1girl, solo"),
        ])
        batch_replace_tag("1girl", "1boy", manifest, project_dir)

        sidecar = tmp_path / "img" / "a.txt"
        assert sidecar.exists()
        assert sidecar.read_text(encoding="utf-8") == "1boy, solo"


# ---------------------------------------------------------------------------
# batch_prepend_trigger tests
# ---------------------------------------------------------------------------


class TestBatchPrependTrigger:
    """Tests for batch_prepend_trigger() prepending a trigger word to all captions."""

    def test_batch_prepend_trigger(self, tmp_path: Path) -> None:
        """Prepends trigger to all captions -> 'ohwx, rest of caption'."""
        from klippbok.services.caption_service import batch_prepend_trigger

        manifest, project_dir = _make_manifest_with_images(tmp_path, [
            ("img/a.jpg", "1girl, solo"),
            ("img/b.jpg", "1boy, outdoors"),
        ])
        count = batch_prepend_trigger("ohwx", manifest, project_dir)

        assert count == 2
        assert manifest["images"][0]["caption"] == "ohwx, 1girl, solo"
        assert manifest["images"][1]["caption"] == "ohwx, 1boy, outdoors"

    def test_batch_prepend_trigger_already_present(self, tmp_path: Path) -> None:
        """Captions already starting with trigger are unchanged."""
        from klippbok.services.caption_service import batch_prepend_trigger

        manifest, project_dir = _make_manifest_with_images(tmp_path, [
            ("img/a.jpg", "ohwx, 1girl, solo"),
            ("img/b.jpg", "1boy, outdoors"),
        ])
        count = batch_prepend_trigger("ohwx", manifest, project_dir)

        # Only b.jpg modified
        assert count == 1
        assert manifest["images"][0]["caption"] == "ohwx, 1girl, solo"
        assert manifest["images"][1]["caption"] == "ohwx, 1boy, outdoors"

    def test_batch_prepend_trigger_writes_sidecar(self, tmp_path: Path) -> None:
        """batch_prepend_trigger writes sidecar .txt files for modified images."""
        from klippbok.services.caption_service import batch_prepend_trigger

        manifest, project_dir = _make_manifest_with_images(tmp_path, [
            ("img/a.jpg", "1girl, solo"),
        ])
        batch_prepend_trigger("ohwx", manifest, project_dir)

        sidecar = tmp_path / "img" / "a.txt"
        assert sidecar.exists()
        assert sidecar.read_text(encoding="utf-8") == "ohwx, 1girl, solo"
