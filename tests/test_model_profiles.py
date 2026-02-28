"""Tests for ModelProfile schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from klippbok.config.model_profiles import (
    BucketConfig,
    ModelProfile,
    TrainingHints,
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
