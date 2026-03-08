"""Dataset curation: multi-signal scoring and diversity-maximizing selection.

Provides automated image selection for LoRA training datasets using:
- Multi-signal image scoring (face, technical, aesthetic, pose, occlusion)
- Diversity-maximizing subset selection via apricot FacilityLocation
- Model-aware preset defaults (SD1.5, SDXL, Flux, Pony)
"""

from klippbok.curation.models import (
    CurationConfig,
    CurationMode,
    CurationResult,
    DiversityMetrics,
    DiversityWeights,
    ImageScore,
    PipelineSummary,
    SignalScores,
)
from klippbok.curation.presets import (
    CHARACTER_WEIGHTS,
    MODEL_TARGET_COUNTS,
    STYLE_WEIGHTS,
    get_target_count_default,
    get_weights,
)

__all__ = [
    "CurationConfig",
    "CurationMode",
    "CurationResult",
    "DiversityMetrics",
    "DiversityWeights",
    "ImageScore",
    "PipelineSummary",
    "SignalScores",
    "CHARACTER_WEIGHTS",
    "MODEL_TARGET_COUNTS",
    "STYLE_WEIGHTS",
    "get_target_count_default",
    "get_weights",
]
