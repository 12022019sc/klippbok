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
    load_model_config,
    reset_override_field,
    resolve_effective_config,
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
