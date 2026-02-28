"""Tests for model config override system, custom profiles, and profile resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from klippbok.config.model_defaults import BUILTIN_PROFILES, SD15_PROFILE
from klippbok.config.model_profiles import ModelProfile


# ─── Imports under test ───

from klippbok.config.model_config import (
    ModelConfigOverride,
    delete_custom_profile,
    get_profile,
    list_profiles,
    load_model_config,
    reset_override_field,
    resolve_effective_config,
    save_custom_profile,
    save_model_config,
)


# ─── ModelConfigOverride Schema ───


class TestModelConfigOverrideSchema:
    """Tests for the ModelConfigOverride Pydantic model."""

    def test_override_all_fields_optional_except_profile_name(self) -> None:
        """ModelConfigOverride(profile_name='sd15') succeeds with all other fields None."""
        override = ModelConfigOverride(profile_name="sd15")
        assert override.profile_name == "sd15"
        assert override.base_resolution is None
        assert override.caption_style is None

    def test_override_requires_profile_name(self) -> None:
        """Constructing without profile_name raises ValidationError."""
        with pytest.raises(ValidationError):
            ModelConfigOverride()  # type: ignore[call-arg]

    def test_override_caption_style_validated(self) -> None:
        """caption_style='invalid' raises ValidationError."""
        with pytest.raises(ValidationError):
            ModelConfigOverride(profile_name="sd15", caption_style="invalid")


# ─── resolve_effective_config ───


class TestResolveEffectiveConfig:
    """Tests for merging overrides onto base profile."""

    def test_resolve_no_overrides_returns_profile_unchanged(self) -> None:
        """resolve_effective_config(SD15_PROFILE, None) returns SD15_PROFILE values."""
        result = resolve_effective_config(SD15_PROFILE, None)
        assert result.base_resolution == SD15_PROFILE.base_resolution
        assert result.caption_style == SD15_PROFILE.caption_style
        assert result.name == SD15_PROFILE.name

    def test_resolve_base_resolution_override(self) -> None:
        """Override base_resolution=768 on SD15_PROFILE produces profile with base_resolution=768."""
        override = ModelConfigOverride(profile_name="sd15", base_resolution=768)
        result = resolve_effective_config(SD15_PROFILE, override)
        assert result.base_resolution == 768

    def test_resolve_caption_style_override(self) -> None:
        """Override caption_style='natural_language' on SD15_PROFILE changes caption_style."""
        override = ModelConfigOverride(
            profile_name="sd15", caption_style="natural_language"
        )
        result = resolve_effective_config(SD15_PROFILE, override)
        assert result.caption_style == "natural_language"

    def test_resolve_bucket_step_size_override(self) -> None:
        """Override bucket_step_size=32 produces profile with bucket_config.step_size=32."""
        override = ModelConfigOverride(profile_name="sd15", bucket_step_size=32)
        result = resolve_effective_config(SD15_PROFILE, override)
        assert result.bucket_config.step_size == 32

    def test_resolve_bucket_min_dimension_override(self) -> None:
        """Override applies to nested bucket_config."""
        override = ModelConfigOverride(profile_name="sd15", bucket_min_dimension=128)
        result = resolve_effective_config(SD15_PROFILE, override)
        assert result.bucket_config.min_dimension == 128

    def test_resolve_bucket_max_dimension_override(self) -> None:
        """Override applies to nested bucket_config."""
        override = ModelConfigOverride(profile_name="sd15", bucket_max_dimension=2048)
        result = resolve_effective_config(SD15_PROFILE, override)
        assert result.bucket_config.max_dimension == 2048

    def test_resolve_multiple_bucket_overrides_combined(self) -> None:
        """Multiple bucket overrides all apply to the resolved profile."""
        override = ModelConfigOverride(
            profile_name="sd15",
            bucket_step_size=32,
            bucket_min_dimension=128,
            bucket_max_dimension=2048,
        )
        result = resolve_effective_config(SD15_PROFILE, override)
        assert result.bucket_config.step_size == 32
        assert result.bucket_config.min_dimension == 128
        assert result.bucket_config.max_dimension == 2048

    def test_resolve_non_overridden_fields_preserved(self) -> None:
        """Overriding base_resolution does not change caption_style or training_hints."""
        override = ModelConfigOverride(profile_name="sd15", base_resolution=768)
        result = resolve_effective_config(SD15_PROFILE, override)
        assert result.caption_style == SD15_PROFILE.caption_style
        assert result.training_hints == SD15_PROFILE.training_hints

    def test_resolve_training_hint_overrides(self) -> None:
        """learning_rate_range, network_rank_default can be overridden."""
        override = ModelConfigOverride(
            profile_name="sd15",
            network_rank_default=64,
        )
        result = resolve_effective_config(SD15_PROFILE, override)
        assert result.training_hints.network_rank_default == 64

    def test_resolve_validates_result(self) -> None:
        """Overriding base_resolution to 500 with step_size=64 raises ValueError."""
        override = ModelConfigOverride(profile_name="sd15", base_resolution=500)
        with pytest.raises(ValueError):
            resolve_effective_config(SD15_PROFILE, override)


# ─── Per-Project Persistence ───


class TestPerProjectPersistence:
    """Tests for saving/loading overrides to .klippbok/model_config.json."""

    def test_save_and_load_model_config_roundtrip(self, tmp_path: Path) -> None:
        """Save overrides, load them back, values match."""
        override = ModelConfigOverride(profile_name="sd15", base_resolution=768)
        save_model_config(tmp_path, override)
        loaded = load_model_config(tmp_path)
        assert loaded is not None
        assert loaded.profile_name == "sd15"
        assert loaded.base_resolution == 768

    def test_load_model_config_no_file_returns_none(self, tmp_path: Path) -> None:
        """Load from empty directory returns None."""
        result = load_model_config(tmp_path)
        assert result is None

    def test_save_creates_klippbok_directory(self, tmp_path: Path) -> None:
        """.klippbok/ created if missing."""
        override = ModelConfigOverride(profile_name="sd15")
        save_model_config(tmp_path, override)
        assert (tmp_path / ".klippbok").is_dir()

    def test_save_excludes_none_fields(self, tmp_path: Path) -> None:
        """JSON on disk does NOT contain null-valued override fields."""
        override = ModelConfigOverride(profile_name="sd15", base_resolution=768)
        save_model_config(tmp_path, override)
        config_path = tmp_path / ".klippbok" / "model_config.json"
        data = json.loads(config_path.read_text())
        assert "caption_style" not in data
        assert "base_resolution" in data

    def test_reset_override_field(self, tmp_path: Path) -> None:
        """reset_override_field('base_resolution') sets it to None, other overrides preserved."""
        override = ModelConfigOverride(
            profile_name="sd15", base_resolution=768, caption_style="natural_language"
        )
        save_model_config(tmp_path, override)
        result = reset_override_field(tmp_path, "base_resolution")
        assert result.base_resolution is None
        assert result.caption_style == "natural_language"

    def test_reset_override_field_unknown_field_raises(self, tmp_path: Path) -> None:
        """reset_override_field('nonexistent') raises ValueError."""
        override = ModelConfigOverride(profile_name="sd15")
        save_model_config(tmp_path, override)
        with pytest.raises(ValueError):
            reset_override_field(tmp_path, "nonexistent")


# ─── Custom Profile CRUD ───


class TestCustomProfileCRUD:
    """Tests for saving/loading/deleting custom profiles."""

    @pytest.fixture(autouse=True)
    def _use_tmp_profiles_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Redirect custom profiles to tmp_path."""
        self.profiles_dir = tmp_path / "profiles"
        monkeypatch.setattr(
            "klippbok.config.model_config._USER_PROFILES_DIR",
            self.profiles_dir,
        )

    def test_save_custom_profile_creates_file(self) -> None:
        """Saving a custom profile creates a JSON file."""
        profile = ModelProfile(
            name="my_custom",
            display_name="My Custom",
            base_resolution=512,
            caption_style="booru",
        )
        path = save_custom_profile(profile)
        assert path.is_file()
        assert path.name == "my_custom.json"

    def test_save_custom_profile_roundtrip(self) -> None:
        """Save a custom profile and load it back via get_profile."""
        profile = ModelProfile(
            name="roundtrip_test",
            display_name="Roundtrip Test",
            base_resolution=768,
            caption_style="natural_language",
        )
        save_custom_profile(profile)
        loaded = get_profile("roundtrip_test")
        assert loaded.name == "roundtrip_test"
        assert loaded.base_resolution == 768
        assert loaded.caption_style == "natural_language"

    def test_save_custom_profile_adds_based_on_field(self) -> None:
        """When based_on is provided, it's stored in the JSON metadata."""
        profile = ModelProfile(
            name="my_variant",
            display_name="My Variant",
            base_resolution=512,
            caption_style="booru",
        )
        path = save_custom_profile(profile, based_on="sd15")
        data = json.loads(path.read_text())
        assert data.get("based_on") == "sd15"

    def test_delete_custom_profile(self) -> None:
        """Deleting a custom profile removes the file."""
        profile = ModelProfile(
            name="to_delete",
            display_name="To Delete",
            base_resolution=512,
            caption_style="booru",
        )
        save_custom_profile(profile)
        delete_custom_profile("to_delete")
        with pytest.raises(KeyError):
            get_profile("to_delete")

    def test_delete_custom_profile_not_found_raises(self) -> None:
        """Deleting a non-existent custom profile raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            delete_custom_profile("does_not_exist")

    def test_delete_builtin_profile_raises(self) -> None:
        """Attempting to delete a built-in profile raises ValueError."""
        with pytest.raises(ValueError):
            delete_custom_profile("sd15")

    def test_custom_profile_requires_minimum_fields(self) -> None:
        """Custom profiles must have name, base_resolution, and caption_style."""
        with pytest.raises(ValidationError):
            ModelProfile(name="incomplete")  # type: ignore[call-arg]


# ─── get_profile ───


class TestGetProfile:
    """Tests for unified profile lookup."""

    @pytest.fixture(autouse=True)
    def _use_tmp_profiles_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Redirect custom profiles to tmp_path."""
        self.profiles_dir = tmp_path / "profiles"
        monkeypatch.setattr(
            "klippbok.config.model_config._USER_PROFILES_DIR",
            self.profiles_dir,
        )

    def test_get_builtin_profile(self) -> None:
        """get_profile('sd15') returns the built-in SD1.5 profile."""
        profile = get_profile("sd15")
        assert profile.name == "sd15"
        assert profile.display_name == "Stable Diffusion 1.5"

    def test_get_custom_profile(self) -> None:
        """get_profile returns a custom profile from disk."""
        custom = ModelProfile(
            name="my_profile",
            display_name="My Profile",
            base_resolution=512,
            caption_style="booru",
        )
        save_custom_profile(custom)
        result = get_profile("my_profile")
        assert result.name == "my_profile"

    def test_get_nonexistent_profile_raises(self) -> None:
        """get_profile('nonexistent') raises KeyError."""
        with pytest.raises(KeyError):
            get_profile("nonexistent")


# ─── list_profiles ───


class TestListProfiles:
    """Tests for listing all available profiles."""

    @pytest.fixture(autouse=True)
    def _use_tmp_profiles_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Redirect custom profiles to tmp_path."""
        self.profiles_dir = tmp_path / "profiles"
        monkeypatch.setattr(
            "klippbok.config.model_config._USER_PROFILES_DIR",
            self.profiles_dir,
        )

    def test_list_profiles_includes_builtins(self) -> None:
        """list_profiles returns all 4 built-in profiles."""
        profiles = list_profiles()
        names = {p.name for p in profiles}
        assert {"sd15", "sdxl", "flux", "pony"} <= names

    def test_list_profiles_includes_custom(self) -> None:
        """list_profiles includes saved custom profiles."""
        custom = ModelProfile(
            name="custom_one",
            display_name="Custom One",
            base_resolution=512,
            caption_style="booru",
        )
        save_custom_profile(custom)
        profiles = list_profiles()
        names = {p.name for p in profiles}
        assert "custom_one" in names

    def test_list_profiles_no_duplicates(self) -> None:
        """list_profiles does not return duplicate profile names."""
        profiles = list_profiles()
        names = [p.name for p in profiles]
        assert len(names) == len(set(names))


# ─── Full Integration ───


class TestFullIntegration:
    """End-to-end workflow tests."""

    @pytest.fixture(autouse=True)
    def _use_tmp_profiles_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Redirect custom profiles to tmp_path."""
        self.profiles_dir = tmp_path / "profiles"
        monkeypatch.setattr(
            "klippbok.config.model_config._USER_PROFILES_DIR",
            self.profiles_dir,
        )

    def test_full_workflow(self) -> None:
        """Select sd15, override resolution to 768, resolve, verify buckets within 768^2."""
        from klippbok.config.model_profiles import generate_buckets

        profile = get_profile("sd15")
        override = ModelConfigOverride(profile_name="sd15", base_resolution=768)
        effective = resolve_effective_config(profile, override)

        assert effective.base_resolution == 768
        assert effective.caption_style == "booru"  # unchanged

        buckets = generate_buckets(
            effective.base_resolution,
            step_size=effective.bucket_config.step_size,
            min_dimension=effective.bucket_config.min_dimension,
            max_dimension=effective.bucket_config.max_dimension,
        )
        budget = 768 * 768
        assert len(buckets) > 0
        for w, h in buckets:
            assert w * h <= budget, f"Bucket ({w}, {h}) exceeds 768^2 budget"
