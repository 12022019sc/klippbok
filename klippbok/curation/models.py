"""Pydantic v2 data models for the curation pipeline.

Defines scoring, configuration, and result models used across
the scorer, diversity selector, and API layer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CurationMode = Literal["character", "style"]


class SignalScores(BaseModel):
    """Individual signal scores for a single image.

    All float fields are normalized to [0, 1]. Higher = better.
    """

    face_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    """InsightFace detection confidence for the best face."""

    face_area_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    """Ratio of face bounding box area to total image area."""

    identity_similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    """Cosine similarity of face embedding to reference identity."""

    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    """pyiqa TOPIQ-NR perceptual quality score (normalized)."""

    aesthetic_score: float = Field(default=0.0, ge=0.0, le=1.0)
    """Aesthetic Predictor V2.5 score (normalized from [1,10])."""

    sharpness_whole: float = Field(default=0.0, ge=0.0, le=1.0)
    """Whole-image Laplacian sharpness (normalized)."""

    sharpness_face: float = Field(default=0.0, ge=0.0, le=1.0)
    """Face-region Laplacian sharpness (normalized)."""

    occlusion_score: float = Field(default=0.0, ge=0.0, le=1.0)
    """CLIP zero-shot occlusion detection (0=occluded, 1=clear)."""

    face_count: int = Field(default=0, ge=0)
    """Number of faces detected by InsightFace."""

    is_grayscale: bool = False
    """Whether the image is grayscale / black-and-white."""

    pose_vector: list[float] = Field(default_factory=list)
    """Pose joint angles (~20-D), each normalized to [0, 1]."""

    is_duplicate: bool = False
    """Whether this image is a near-duplicate (pHash)."""


class ImageScore(BaseModel):
    """Complete scoring result for a single image."""

    image_id: str
    """SHA256[:16] of relative path."""

    relative_path: str
    """Path relative to project directory."""

    signals: SignalScores = Field(default_factory=SignalScores)
    """Breakdown of all signal dimensions."""

    composite_score: float = 0.0
    """Weighted composite score (depends on CurationMode)."""

    mode: CurationMode = "character"
    """Mode used to compute composite_score."""

    raw_composite_score: float = 0.0
    """Composite from raw signals — preserves absolute quality for hard floor."""

    ranked_signals: SignalScores = Field(default_factory=SignalScores)
    """Percentile-ranked signal scores (0.0 = worst in dataset, 1.0 = best)."""

    floor_status: Literal["passed", "soft_floor", "hard_floor"] = "passed"
    """Quality floor classification."""

    dedup_group_id: str | None = None
    """Duplicate group key (None = unique image, string = group ID)."""

    dedup_kept: bool = True
    """Whether this image is the representative of its dedup group."""


class DiversityWeights(BaseModel):
    """Weights for embedding concatenation in diversity selection."""

    clip: float = Field(default=0.4, ge=0.0, le=1.0)
    """Weight for CLIP visual embeddings."""

    pose: float = Field(default=0.3, ge=0.0, le=1.0)
    """Weight for pose angle embeddings."""

    face: float = Field(default=0.3, ge=0.0, le=1.0)
    """Weight for face identity embeddings."""


class CurationConfig(BaseModel):
    """Configuration for a curation run."""

    mode: CurationMode = "character"
    """Scoring mode: character (face-weighted) or style (aesthetic-weighted)."""

    target_count: int = Field(default=60, ge=1)
    """Desired number of images in the curated subset."""

    quality_floor_pct: float = Field(default=0.3, ge=0.0, le=1.0)
    """Bottom percentile to discard before diversity selection."""

    face_confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    """Minimum face detection confidence to count as a valid face."""

    pose_angle_limit: float = Field(default=45.0, ge=0.0, le=180.0)
    """Maximum pose yaw/pitch angle (degrees) to accept."""

    identity_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    """Minimum identity similarity to reference embedding."""

    hard_floor: float = Field(default=0.15, ge=0.0, le=1.0)
    """Absolute raw composite threshold — images below are always excluded."""

    reference_image_id: str | None = None
    """Image ID of the identity reference (for character mode)."""

    diversity_weights: DiversityWeights | None = None
    """Custom weights for diversity embedding concatenation."""


class DiversityMetrics(BaseModel):
    """Metrics describing the diversity of the selected subset."""

    pose_variety: float = 0.0
    """Standard deviation of pose angles across selected images."""

    unique_backgrounds: int = 0
    """Estimated number of distinct backgrounds (CLIP clustering)."""

    expression_spread: float = 0.0
    """Spread of facial expression embeddings."""


class PipelineSummary(BaseModel):
    """High-level summary of a curation pipeline run."""

    total_scanned: int = 0
    """Total images evaluated."""

    passed_quality: int = 0
    """Images passing the quality floor."""

    selected: int = 0
    """Images selected for the final subset."""

    hard_excluded: int = 0
    """Images below hard quality floor."""

    soft_flagged: int = 0
    """Images below soft quality floor (still eligible for selection)."""

    diversity_metrics: DiversityMetrics | None = None
    """Diversity statistics for the selected subset."""


class CurationResult(BaseModel):
    """Complete output of a curation pipeline run."""

    config: CurationConfig
    """Configuration used for this run."""

    scores: dict[str, ImageScore] = Field(default_factory=dict)
    """All scored images, keyed by image_id."""

    selected_ids: list[str] = Field(default_factory=list)
    """Image IDs in the curated subset."""

    pinned_ids: list[str] = Field(default_factory=list)
    """Image IDs manually pinned (always included)."""

    excluded_ids: list[str] = Field(default_factory=list)
    """Image IDs manually excluded (never included)."""

    summary: PipelineSummary = Field(default_factory=PipelineSummary)
    """Pipeline run summary statistics."""

    timestamp: str = ""
    """ISO 8601 timestamp of the run."""
