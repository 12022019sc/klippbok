"""Model profile schema and bucket generation for diffusion model targets.

Defines the ModelProfile frozen Pydantic model that captures all model-specific
defaults: base resolution, caption style, bucket parameters, and training
hyperparameter hints. Also provides the pixel-budget bucket generation
algorithm compatible with kohya/sd-scripts, musubi-tuner, and ai-toolkit.

Three sub-models:
  - BucketConfig: parameters for bucket dimension generation
  - TrainingHints: hyperparameter suggestions for export config (Phase 8)
  - ModelProfile: the complete profile combining resolution, style, and hints
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ─── Bucket Configuration ───


class BucketConfig(BaseModel):
    """Parameters for pixel-budget bucket generation.

    Controls how resolution buckets are enumerated for a given model.
    Step size must be a power of 2 (8, 16, 32, 64) to align with VAE
    spatial compression factors.
    """

    model_config = ConfigDict(frozen=True)

    step_size: int = Field(
        default=64,
        description="Pixel step for dimension alignment. Must be a power of 2.",
    )
    min_dimension: int = Field(
        default=256,
        description="Minimum allowed bucket dimension (width or height).",
    )
    max_dimension: int = Field(
        default=1024,
        description="Maximum allowed bucket dimension (width or height).",
    )

    @field_validator("step_size")
    @classmethod
    def validate_step_size_power_of_two(cls, v: int) -> int:
        """Step size must be a power of 2."""
        if v < 1 or (v & (v - 1)) != 0:
            raise ValueError(
                f"step_size must be a power of 2, got {v}. "
                f"Valid values: 8, 16, 32, 64, etc."
            )
        return v


# ─── Training Hints ───


class TrainingHints(BaseModel):
    """Training hyperparameter suggestions for export config generation.

    These are hints for Phase 8 (export) -- they suggest reasonable starting
    points for LoRA training parameters. They are NOT enforced constraints.
    Values are aggregated from kohya wiki, civitai guides, and ai-toolkit docs.
    """

    model_config = ConfigDict(frozen=True)

    learning_rate_range: tuple[float, float] = Field(
        default=(1e-5, 1e-3),
        description="Suggested learning rate range (min, max).",
    )
    network_rank_range: tuple[int, int] = Field(
        default=(4, 128),
        description="Suggested LoRA network rank range (min, max).",
    )
    network_rank_default: int = Field(
        default=32,
        description="Default network rank for this model type.",
    )
    network_alpha_ratio: float = Field(
        default=0.5,
        description="Alpha = rank * ratio. 0.5 for most models, 1.0 for Flux.",
    )


# ─── Model Profile ───


class ModelProfile(BaseModel):
    """A target diffusion model profile defining resolution, caption, and training defaults.

    Frozen Pydantic model -- immutable after construction. Overrides produce
    new profiles via the override system (Phase 2 Plan 2), never mutation.

    Required fields: name, display_name, base_resolution, caption_style.
    Optional: bucket_config, training_hints, description.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Machine-readable profile identifier (e.g., 'sd15').")
    display_name: str = Field(description="Human-readable name (e.g., 'Stable Diffusion 1.5').")
    base_resolution: int = Field(
        description=(
            "Base resolution in pixels. Defines the pixel budget "
            "(base_resolution^2) for bucket generation."
        ),
    )
    caption_style: Literal["booru", "natural_language"] = Field(
        description=(
            "Default captioning style. 'booru' = comma-separated tags "
            "(SD1.5, Pony). 'natural_language' = full sentences (SDXL, Flux)."
        ),
    )
    bucket_config: BucketConfig = Field(
        default_factory=BucketConfig,
        description="Bucket generation parameters.",
    )
    training_hints: TrainingHints = Field(
        default_factory=TrainingHints,
        description="Training hyperparameter suggestions for export.",
    )
    description: str = Field(
        default="",
        description="Human-readable description of this profile.",
    )

    @model_validator(mode="after")
    def validate_base_resolution_alignment(self) -> ModelProfile:
        """base_resolution must be a multiple of bucket_config.step_size."""
        step = self.bucket_config.step_size
        if self.base_resolution % step != 0:
            raise ValueError(
                f"base_resolution ({self.base_resolution}) must be a multiple "
                f"of bucket_config.step_size ({step})."
            )
        return self


# ─── Bucket Generation ───


def generate_buckets(
    base_resolution: int,
    step_size: int = 64,
    min_dimension: int = 256,
    max_dimension: int | None = None,
    max_aspect_ratio: float = 2.0,
) -> list[tuple[int, int]]:
    """Generate valid bucket resolutions within a pixel budget.

    Follows the kohya/sd-scripts algorithm:
    1. Pixel budget = base_resolution^2
    2. For each width from min_dimension to max_dimension (step_size increments):
       a. Compute max valid height = floor(pixel_budget / width) snapped to step_size
       b. Clamp height to [min_dimension, max_dimension]
       c. Check aspect ratio constraint
       d. Add (width, height) and (height, width) if both are valid
    3. Return sorted, deduplicated bucket list

    Args:
        base_resolution: Defines pixel budget (base_resolution^2).
            E.g., 512 for SD1.5 (262,144 px), 1024 for SDXL (1,048,576 px).
        step_size: Dimension alignment step. All bucket dimensions will be
            multiples of this value. Default 64.
        min_dimension: Smallest allowed dimension (width or height).
        max_dimension: Largest allowed dimension. Defaults to 2 * base_resolution.
        max_aspect_ratio: Maximum aspect ratio (long side / short side).
            Default 2.0 covers portrait/landscape up to 1:2.

    Returns:
        Sorted list of (width, height) tuples. Empty list if no valid
        buckets can be generated with the given parameters.
    """
    if max_dimension is None:
        max_dimension = base_resolution * 2

    pixel_budget = base_resolution * base_resolution
    buckets: set[tuple[int, int]] = set()

    w = min_dimension
    while w <= max_dimension:
        # Max height that fits within pixel budget at this width,
        # snapped down to step_size grid
        h = (pixel_budget // w) // step_size * step_size
        h = min(h, max_dimension)

        if h >= min_dimension:
            ratio = max(w, h) / min(w, h)
            if ratio <= max_aspect_ratio:
                buckets.add((w, h))
                if w != h:
                    buckets.add((h, w))

        w += step_size

    return sorted(buckets)
