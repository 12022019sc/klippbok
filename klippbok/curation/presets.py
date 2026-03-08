"""Model-aware curation presets and weight configurations.

Target counts are locked context decisions from 07.3-RESEARCH.md:
- SD 1.5: 20-50 images (default 40)
- SDXL: 50-100 images (default 80)
- Flux: 80-150 images (default 100)
- Pony: 40-100 images (default 70)
- Custom/unknown: 60 images (conservative default)
"""

from __future__ import annotations

from klippbok.curation.models import CurationMode

MODEL_TARGET_COUNTS: dict[str, int] = {
    "sd15": 40,
    "sdxl": 80,
    "flux": 100,
    "pony": 70,
}
"""Default target image counts per model architecture."""

CHARACTER_WEIGHTS: dict[str, float] = {
    "face": 0.40,
    "technical": 0.25,
    "aesthetic": 0.20,
    "other": 0.15,
}
"""Composite score weights for character-focused curation."""

STYLE_WEIGHTS: dict[str, float] = {
    "aesthetic": 0.35,
    "technical": 0.30,
    "face": 0.20,
    "other": 0.15,
}
"""Composite score weights for style-focused curation."""

_DEFAULT_TARGET_COUNT: int = 60
"""Fallback target count for unknown/custom model architectures."""


def get_target_count_default(model_name: str | None) -> int:
    """Return the default target image count for a model architecture.

    Case-insensitive lookup. Returns 60 for unknown/None models.

    Args:
        model_name: Model architecture name (e.g., "sd15", "SDXL", "flux").

    Returns:
        Recommended target image count for the model.
    """
    if model_name is None:
        return _DEFAULT_TARGET_COUNT
    return MODEL_TARGET_COUNTS.get(model_name.lower(), _DEFAULT_TARGET_COUNT)


def get_weights(mode: CurationMode) -> dict[str, float]:
    """Return composite score weights for the given curation mode.

    Args:
        mode: "character" or "style".

    Returns:
        Dict mapping weight category to float weight.
    """
    if mode == "character":
        return CHARACTER_WEIGHTS.copy()
    return STYLE_WEIGHTS.copy()
