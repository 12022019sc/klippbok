"""Tests for ModelProfile schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from klippbok.config.model_defaults import (
    BUILTIN_PROFILES,
    FLUX_PROFILE,
    PONY_PROFILE,
    SD15_PROFILE,
    SDXL_PROFILE,
)
from klippbok.config.model_profiles import (
    BucketConfig,
    ModelProfile,
    TrainingHints,
    generate_buckets,
)


class TestModelProfileSchema:
    """Tests for the ModelProfile Pydantic model."""

    def test_model_profile_is_frozen(self) -> None:
        """Constructing a ModelProfile and attempting attribute assignment raises."""
        profile = ModelProfile(
            name="test",
            display_name="Test",
            base_resolution=512,
            caption_style="booru",
        )
        with pytest.raises(ValidationError):
            profile.name = "changed"

    def test_model_profile_requires_name_base_resolution_caption_style(self) -> None:
        """Construction without required fields raises ValidationError."""
        with pytest.raises(ValidationError):
            ModelProfile()  # type: ignore[call-arg]

        with pytest.raises(ValidationError):
            ModelProfile(name="test")  # type: ignore[call-arg]

        with pytest.raises(ValidationError):
            ModelProfile(name="test", base_resolution=512)  # type: ignore[call-arg]

    def test_model_profile_valid_caption_styles(self) -> None:
        """'booru' and 'natural_language' accepted; 'invalid' rejected."""
        for style in ("booru", "natural_language"):
            p = ModelProfile(
                name="test",
                display_name="Test",
                base_resolution=512,
                caption_style=style,
            )
            assert p.caption_style == style

        with pytest.raises(ValidationError):
            ModelProfile(
                name="test",
                display_name="Test",
                base_resolution=512,
                caption_style="invalid",
            )

    def test_model_profile_construction_with_all_fields(self) -> None:
        """Full construction with all fields works."""
        profile = ModelProfile(
            name="test",
            display_name="Test Model",
            base_resolution=1024,
            caption_style="natural_language",
            bucket_config=BucketConfig(step_size=64, min_dimension=512, max_dimension=2048),
            training_hints=TrainingHints(network_rank_default=16),
            description="A test profile",
        )
        assert profile.name == "test"
        assert profile.base_resolution == 1024
        assert profile.bucket_config.step_size == 64
        assert profile.training_hints.network_rank_default == 16


class TestBucketConfig:
    """Tests for BucketConfig defaults and validation."""

    def test_bucket_config_defaults(self) -> None:
        """BucketConfig() has step_size=64, min_dimension=256, max_dimension=1024."""
        bc = BucketConfig()
        assert bc.step_size == 64
        assert bc.min_dimension == 256
        assert bc.max_dimension == 1024

    def test_bucket_config_step_size_must_be_power_of_two(self) -> None:
        """step_size=7 raises validation error; 8, 16, 32, 64 accepted."""
        with pytest.raises(ValidationError):
            BucketConfig(step_size=7)

        for size in (8, 16, 32, 64):
            bc = BucketConfig(step_size=size)
            assert bc.step_size == size


class TestTrainingHints:
    """Tests for TrainingHints defaults."""

    def test_training_hints_defaults(self) -> None:
        """TrainingHints() has reasonable defaults."""
        th = TrainingHints()
        assert th.network_rank_default == 32
        assert th.network_alpha_ratio == 0.5
        assert th.learning_rate_range == (1e-5, 1e-3)
        assert th.network_rank_range == (4, 128)


class TestBaseResolutionValidation:
    """Tests for base_resolution alignment with step_size."""

    def test_base_resolution_must_be_multiple_of_step_size(self) -> None:
        """base_resolution=500 with step_size=64 raises validation error."""
        with pytest.raises(ValidationError):
            ModelProfile(
                name="test",
                display_name="Test",
                base_resolution=500,
                caption_style="booru",
                bucket_config=BucketConfig(step_size=64),
            )

    def test_base_resolution_aligned_with_step_size(self) -> None:
        """base_resolution=512 with step_size=64 is accepted."""
        p = ModelProfile(
            name="test",
            display_name="Test",
            base_resolution=512,
            caption_style="booru",
            bucket_config=BucketConfig(step_size=64),
        )
        assert p.base_resolution == 512


class TestBuiltinProfiles:
    """Tests for built-in model profile constants."""

    def test_builtin_profiles_count(self) -> None:
        """BUILTIN_PROFILES has exactly 4 entries."""
        assert len(BUILTIN_PROFILES) == 4

    def test_sd15_profile_values(self) -> None:
        """SD15_PROFILE has correct resolution and caption style."""
        assert SD15_PROFILE.base_resolution == 512
        assert SD15_PROFILE.caption_style == "booru"
        assert SD15_PROFILE.name == "sd15"

    def test_sdxl_profile_values(self) -> None:
        """SDXL_PROFILE has correct resolution and caption style."""
        assert SDXL_PROFILE.base_resolution == 1024
        assert SDXL_PROFILE.caption_style == "natural_language"
        assert SDXL_PROFILE.name == "sdxl"

    def test_flux_alpha_ratio(self) -> None:
        """FLUX_PROFILE has network_alpha_ratio == 1.0."""
        assert FLUX_PROFILE.training_hints.network_alpha_ratio == 1.0

    def test_pony_caption_style(self) -> None:
        """PONY_PROFILE has caption_style == 'booru'."""
        assert PONY_PROFILE.caption_style == "booru"

    def test_all_builtin_buckets_generate_successfully(self) -> None:
        """Each built-in profile generates a non-empty bucket list."""
        for name, profile in BUILTIN_PROFILES.items():
            buckets = generate_buckets(
                profile.base_resolution,
                step_size=profile.bucket_config.step_size,
                min_dimension=profile.bucket_config.min_dimension,
                max_dimension=profile.bucket_config.max_dimension,
            )
            assert len(buckets) > 0, f"Profile '{name}' generated no buckets"

    def test_sd15_buckets_within_budget(self) -> None:
        """All SD1.5 buckets have w*h <= 512*512."""
        buckets = generate_buckets(
            SD15_PROFILE.base_resolution,
            step_size=SD15_PROFILE.bucket_config.step_size,
            min_dimension=SD15_PROFILE.bucket_config.min_dimension,
            max_dimension=SD15_PROFILE.bucket_config.max_dimension,
        )
        budget = 512 * 512
        for w, h in buckets:
            assert w * h <= budget, f"SD1.5 bucket ({w}, {h}) exceeds budget"

    def test_public_api_importable(self) -> None:
        """Public API is importable from klippbok.config."""
        from klippbok.config import (  # noqa: F401
            BUILTIN_PROFILES as bp,
            BucketConfig as bc,
            ModelProfile as mp,
            TrainingHints as th,
            generate_buckets as gb,
        )
        assert len(bp) == 4
