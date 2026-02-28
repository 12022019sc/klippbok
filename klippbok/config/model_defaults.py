"""Built-in model profile constants for supported diffusion models.

Four profiles ship with Klippbok:
  - SD1.5: 512px base, booru tags, legacy but widely used
  - SDXL: 1024px base, natural language captions
  - Flux: 1024px base, natural language, alpha_ratio=1.0
  - Pony: 1024px base (SDXL-based), booru tags for anime

Each profile is a frozen ModelProfile instance. Use BUILTIN_PROFILES dict
to look up profiles by name.
"""

from __future__ import annotations

from klippbok.config.model_profiles import (
    BucketConfig,
    ModelProfile,
    TrainingHints,
)

SD15_PROFILE = ModelProfile(
    name="sd15",
    display_name="Stable Diffusion 1.5",
    base_resolution=512,
    caption_style="booru",
    bucket_config=BucketConfig(
        step_size=64,
        min_dimension=256,
        max_dimension=1024,
    ),
    training_hints=TrainingHints(
        learning_rate_range=(1e-5, 1e-3),
        network_rank_range=(4, 128),
        network_rank_default=32,
        network_alpha_ratio=0.5,
    ),
    description="SD1.5 — 512px base, booru-style tags, 262K pixel budget",
)

SDXL_PROFILE = ModelProfile(
    name="sdxl",
    display_name="Stable Diffusion XL",
    base_resolution=1024,
    caption_style="natural_language",
    bucket_config=BucketConfig(
        step_size=64,
        min_dimension=512,
        max_dimension=2048,
    ),
    training_hints=TrainingHints(
        learning_rate_range=(5e-6, 5e-4),
        network_rank_range=(8, 128),
        network_rank_default=32,
        network_alpha_ratio=0.5,
    ),
    description="SDXL — 1024px base, natural language captions, 1M pixel budget",
)

FLUX_PROFILE = ModelProfile(
    name="flux",
    display_name="Flux (dev & schnell)",
    base_resolution=1024,
    caption_style="natural_language",
    bucket_config=BucketConfig(
        step_size=64,
        min_dimension=512,
        max_dimension=2048,
    ),
    training_hints=TrainingHints(
        learning_rate_range=(8e-5, 2e-3),
        network_rank_range=(16, 64),
        network_rank_default=32,
        network_alpha_ratio=1.0,
    ),
    description="Flux — 1024px base, natural language captions, covers dev and schnell",
)

PONY_PROFILE = ModelProfile(
    name="pony",
    display_name="Pony Diffusion XL",
    base_resolution=1024,
    caption_style="booru",
    bucket_config=BucketConfig(
        step_size=64,
        min_dimension=512,
        max_dimension=2048,
    ),
    training_hints=TrainingHints(
        learning_rate_range=(5e-6, 5e-4),
        network_rank_range=(8, 128),
        network_rank_default=32,
        network_alpha_ratio=0.5,
    ),
    description="Pony XL — 1024px base, booru-style tags (SDXL-based anime model)",
)

BUILTIN_PROFILES: dict[str, ModelProfile] = {
    p.name: p for p in [SD15_PROFILE, SDXL_PROFILE, FLUX_PROFILE, PONY_PROFILE]
}
"""Lookup dict for built-in model profiles, keyed by profile name."""
