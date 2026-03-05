"""Unit tests for caption_service routing and persistence.

Tests verify:
  - get_caption_style_for_project: routes based on model profile (legacy)
  - get_caption_style_for_project: caption_style_override in manifest overrides profile (legacy)
  - get_caption_mode_for_project: routes based on global config or profile
  - _resolve_token_budget: resolution chain vlm_config > profile > default
  - caption_image_for_project: routes by caption_mode (booru_tags→WD Tagger, VLM→pipeline)
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


class TestGetCaptionModeForProject:
    """Tests for get_caption_mode_for_project mode routing."""

    def test_global_config_mode_takes_priority(self) -> None:
        """Global config caption_mode overrides profile default."""
        from klippbok.services.caption_service import get_caption_mode_for_project

        manifest = _manifest(active_profile="sd15")
        global_config = {"caption_mode": "descriptive"}
        mode = get_caption_mode_for_project(manifest, global_config)
        assert mode == "descriptive"

    def test_sd15_profile_maps_to_booru_tags(self) -> None:
        """SD1.5 profile (booru caption_style) maps to booru_tags mode."""
        from klippbok.services.caption_service import get_caption_mode_for_project

        manifest = _manifest(active_profile="sd15")
        mode = get_caption_mode_for_project(manifest, global_config=None)
        assert mode == "booru_tags"

    def test_sdxl_profile_maps_to_descriptive(self) -> None:
        """SDXL profile (natural_language caption_style) maps to descriptive mode."""
        from klippbok.services.caption_service import get_caption_mode_for_project

        manifest = _manifest(active_profile="sdxl")
        mode = get_caption_mode_for_project(manifest, global_config=None)
        assert mode == "descriptive"

    def test_unknown_profile_defaults_to_context_only_tags(self) -> None:
        """Unknown profile falls back to context_only_tags (safe default)."""
        from klippbok.services.caption_service import get_caption_mode_for_project

        manifest = _manifest(active_profile="nonexistent_profile_xyzzy")
        mode = get_caption_mode_for_project(manifest, global_config=None)
        assert mode == "context_only_tags"

    def test_empty_global_config_falls_back_to_profile(self) -> None:
        """Empty global config falls back to profile lookup."""
        from klippbok.services.caption_service import get_caption_mode_for_project

        manifest = _manifest(active_profile="sd15")
        mode = get_caption_mode_for_project(manifest, global_config={})
        assert mode == "booru_tags"

    def test_caption_style_override_in_manifest_ignored(self) -> None:
        """caption_style_override in manifest is intentionally ignored (mode is global)."""
        from klippbok.services.caption_service import get_caption_mode_for_project

        # SD1.5 profile → booru_tags; manifest override should be ignored
        manifest = _manifest(active_profile="sd15", caption_style_override="natural_language")
        mode = get_caption_mode_for_project(manifest, global_config=None)
        assert mode == "booru_tags", (
            "caption_style_override must be ignored; mode comes from profile only"
        )


class TestResolveTokenBudget:
    """Tests for _resolve_token_budget helper."""

    def test_vlm_config_max_tokens_overrides_profile(self) -> None:
        """vlm_config.max_tokens takes priority over profile default."""
        from klippbok.caption.models import CaptionConfig
        from klippbok.services.caption_service import _resolve_token_budget

        config = CaptionConfig(provider="gemini", api_key="k", max_tokens=300)
        manifest = _manifest(active_profile="sd15")  # sd15 default is 75
        assert _resolve_token_budget(config, manifest) == 300

    def test_profile_default_used_when_no_max_tokens(self) -> None:
        """Profile default_token_budget is used when vlm_config.max_tokens is None."""
        from klippbok.caption.models import CaptionConfig
        from klippbok.services.caption_service import _resolve_token_budget

        config = CaptionConfig(provider="gemini", api_key="k", max_tokens=None)
        manifest = _manifest(active_profile="sd15")  # sd15 default is 75
        assert _resolve_token_budget(config, manifest) == 75

    def test_fallback_when_no_vlm_config(self) -> None:
        """Returns profile default when vlm_config is None."""
        from klippbok.services.caption_service import _resolve_token_budget

        manifest = _manifest(active_profile="sdxl")  # sdxl default is 150
        assert _resolve_token_budget(None, manifest) == 150

    def test_safe_default_for_unknown_profile(self) -> None:
        """Returns 150 (SDXL default) when profile cannot be resolved."""
        from klippbok.services.caption_service import _resolve_token_budget

        manifest = _manifest(active_profile="nonexistent_xyzzy")
        assert _resolve_token_budget(None, manifest) == 150


class TestCaptionImageForProject:
    """Tests for caption_image_for_project routing to correct backend."""

    def test_vlm_caption_calls_backend_and_pipeline(self, tmp_path: Path) -> None:
        """VLM path calls _create_backend, caption_image, and apply_vlm_pipeline."""
        from klippbok.caption.models import CaptionConfig
        from klippbok.services.caption_service import caption_image_for_project

        image_path = tmp_path / "photo.jpg"
        image_path.write_bytes(b"fake-image")

        manifest = _manifest(active_profile="sdxl")
        vlm_config = CaptionConfig(
            provider="gemini",
            api_key="test_key",
            caption_mode="descriptive",
        )

        mock_backend = MagicMock()
        mock_backend.caption_image.return_value = "a woman in a red dress"

        with patch("klippbok.caption.captioner._create_backend", return_value=mock_backend), \
             patch("klippbok.caption.pipeline.apply_vlm_pipeline", return_value="post-processed caption") as mock_pipeline:
            result = caption_image_for_project(image_path, manifest, vlm_config)

        assert result == "post-processed caption", f"Got '{result}'"
        mock_backend.caption_image.assert_called_once()
        mock_pipeline.assert_called_once()

    def test_booru_tags_without_vlm_routes_to_wd_tagger(self, tmp_path: Path) -> None:
        """booru_tags without VLM config routes to WD Tagger (raw tags)."""
        from klippbok.services.caption_service import caption_image_for_project

        image_path = tmp_path / "photo.jpg"
        image_path.write_bytes(b"fake-image")

        manifest = _manifest(active_profile="sd15")

        with patch("klippbok.caption.wd_tagger.tag_image_booru", return_value=(["1girl", "solo"], ["char_name"])):
            result = caption_image_for_project(
                image_path, manifest, vlm_config=None, caption_mode="booru_tags"
            )

        # char_tags first + general_tags joined (no filtering)
        assert result == "char_name, 1girl, solo", f"Expected 'char_name, 1girl, solo', got '{result}'"

    def test_context_only_tags_without_vlm_applies_appearance_filter(self, tmp_path: Path) -> None:
        """context_only_tags without VLM routes to WD Tagger + appearance filter."""
        from klippbok.services.caption_service import caption_image_for_project

        image_path = tmp_path / "photo.jpg"
        image_path.write_bytes(b"fake-image")

        manifest = _manifest(active_profile="sdxl")

        # Tags include an appearance tag (blue eyes) which should be filtered
        with patch("klippbok.caption.wd_tagger.tag_image_booru", return_value=(["outdoors", "blue eyes", "solo"], [])):
            result = caption_image_for_project(
                image_path, manifest, vlm_config=None, caption_mode="context_only_tags"
            )

        # "blue eyes" is in DEFAULT_APPEARANCE_BLACKLIST and should be filtered
        assert "blue eyes" not in result, f"Appearance tag should be filtered, got '{result}'"
        assert "outdoors" in result, f"Non-appearance tags should be preserved, got '{result}'"

    def test_vlm_config_caption_mode_overrides_parameter(self, tmp_path: Path) -> None:
        """vlm_config.caption_mode takes precedence over the caption_mode parameter."""
        from klippbok.caption.models import CaptionConfig
        from klippbok.services.caption_service import caption_image_for_project

        image_path = tmp_path / "photo.jpg"
        image_path.write_bytes(b"fake-image")

        manifest = _manifest(active_profile="sdxl")
        vlm_config = CaptionConfig(
            provider="gemini",
            api_key="test_key",
            caption_mode="straightforward",  # Mode set on config
        )

        mock_backend = MagicMock()
        mock_backend.caption_image.return_value = "raw caption"

        captured_pipeline_args = []

        def capture_pipeline(caption, anchor_word, token_budget, caption_mode):
            captured_pipeline_args.append(caption_mode)
            return "processed"

        with patch("klippbok.caption.captioner._create_backend", return_value=mock_backend), \
             patch("klippbok.caption.pipeline.apply_vlm_pipeline", side_effect=capture_pipeline):
            caption_image_for_project(
                image_path, manifest, vlm_config, caption_mode="booru_tags"  # param says booru_tags
            )

        # Pipeline must be called with vlm_config.caption_mode ("straightforward"), not the parameter
        assert captured_pipeline_args[0] == "straightforward", (
            f"Expected 'straightforward' from vlm_config, got '{captured_pipeline_args[0]}'"
        )


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
