# Dataset Curation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automated image curation pipeline that scores gallery images on multiple ML dimensions, then selects a maximally diverse subset for LoRA training.

**Architecture:** Two-phase pipeline (Score & Filter → Diverse Subset Selection) with SSE progress streaming, model-aware presets, and a review UI for guided adjustments. Backend in `klippbok/curation/`, API router at `/api/v1/curation/`, frontend page at `/curate`.

**Tech Stack:** InsightFace, pyiqa (TOPIQ-NR), aesthetic-predictor-v2-5, apricot-select, CLIP (transformers), MediaPipe, FastAPI + SSE, React + Zustand + React Query.

**Design doc:** `docs/plans/2026-03-07-dataset-curation-design.md`

---

## Task 1: Add Optional Dependency Group

**Files:**
- Modify: `pyproject.toml` (optional-dependencies section, ~line 33)

**Step 1: Add the `curation` group**

In `pyproject.toml`, add after the `crop` group and before `gui`:

```toml
curation = [
    "klippbok[image,triage,crop]",
    "pyiqa>=0.1.12",
    "apricot-select>=0.6.1",
    "aesthetic-predictor-v2-5>=0.1.0",
]
```

Update the `all` group to include `curation`:
```toml
all = [
    "klippbok[video,caption,dataset,image,triage,tagger,crop,curation,gui]",
]
```

**Step 2: Install**

Run: `cd C:/Dev/Projects/klippbok-main && .venv/Scripts/pip.exe install -e ".[curation]"`

Verify: `.venv/Scripts/python.exe -c "import pyiqa; import apricot; print('OK')"`

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add curation optional dependency group (pyiqa, apricot, aesthetic-predictor)"
```

---

## Task 2: Curation Data Models

**Files:**
- Create: `klippbok/curation/__init__.py`
- Create: `klippbok/curation/models.py`
- Test: `tests/test_curation_models.py`

**Step 1: Write the failing test**

```python
# tests/test_curation_models.py
"""Tests for curation data models."""
import pytest
from klippbok.curation.models import (
    CurationMode,
    CurationConfig,
    DiversityWeights,
    ImageScore,
    CurationResult,
)


def test_curation_mode_enum():
    assert CurationMode.CHARACTER == "character"
    assert CurationMode.STYLE == "style"


def test_curation_config_defaults():
    cfg = CurationConfig()
    assert cfg.mode == CurationMode.CHARACTER
    assert cfg.target_count == 40
    assert cfg.quality_floor_pct == 0.30
    assert cfg.min_face_confidence == 0.5
    assert cfg.min_face_area_ratio == 0.05
    assert cfg.max_pose_angle == 75.0
    assert cfg.identity_threshold == 0.45
    assert cfg.reference_image_id is None
    assert isinstance(cfg.diversity_weights, DiversityWeights)


def test_curation_config_style_mode():
    cfg = CurationConfig(mode=CurationMode.STYLE, target_count=60)
    assert cfg.mode == CurationMode.STYLE
    assert cfg.target_count == 60


def test_diversity_weights_defaults():
    w = DiversityWeights()
    assert w.clip_visual == 0.4
    assert w.pose == 0.3
    assert w.face == 0.3


def test_diversity_weights_sum_validation():
    """Weights don't need to sum to 1.0 — they're relative."""
    w = DiversityWeights(clip_visual=0.6, pose=0.2, face=0.2)
    assert w.clip_visual == 0.6


def test_image_score_minimal():
    score = ImageScore(
        image_id="abc123",
        perceptual_quality=0.75,
        aesthetic_score=0.80,
        sharpness=150.0,
        is_occluded=False,
        is_duplicate=False,
        composite_score=0.78,
    )
    assert score.image_id == "abc123"
    assert score.face_confidence is None
    assert score.pose_vector is None


def test_image_score_full():
    score = ImageScore(
        image_id="abc123",
        face_confidence=0.95,
        face_sharpness=200.0,
        pose_angles=(10.0, 5.0, -3.0),
        face_area_ratio=0.15,
        identity_similarity=0.88,
        perceptual_quality=0.85,
        aesthetic_score=0.72,
        sharpness=300.0,
        is_occluded=False,
        is_duplicate=False,
        composite_score=0.82,
        pose_vector=[0.1] * 20,
    )
    assert score.face_confidence == 0.95
    assert len(score.pose_vector) == 20


def test_curation_result():
    result = CurationResult(
        selected_ids=["a", "b", "c"],
        scores={},
        survivors_count=100,
        total_count=400,
        mode=CurationMode.CHARACTER,
        config=CurationConfig(),
    )
    assert len(result.selected_ids) == 3
    assert result.survivors_count == 100
```

**Step 2: Run test to verify it fails**

Run: `cd C:/Dev/Projects/klippbok-main && .venv/Scripts/python.exe -m pytest tests/test_curation_models.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'klippbok.curation'`

**Step 3: Write the implementation**

```python
# klippbok/curation/__init__.py
"""Automated dataset curation for LoRA training."""
```

```python
# klippbok/curation/models.py
"""Pydantic models for the curation pipeline."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class CurationMode(str, Enum):
    """Curation strategy."""

    CHARACTER = "character"
    STYLE = "style"


class DiversityWeights(BaseModel):
    """Relative weights for the Phase 2 diversity feature space."""

    clip_visual: float = 0.4
    pose: float = 0.3
    face: float = 0.3


class CurationConfig(BaseModel):
    """User-configurable curation parameters."""

    mode: CurationMode = CurationMode.CHARACTER
    target_count: int = 40
    quality_floor_pct: float = 0.30
    min_face_confidence: float = 0.5
    min_face_area_ratio: float = 0.05
    max_pose_angle: float = 75.0
    identity_threshold: float = 0.45
    reference_image_id: str | None = None
    diversity_weights: DiversityWeights = DiversityWeights()


class ImageScore(BaseModel):
    """Per-image scoring breakdown."""

    image_id: str
    face_confidence: float | None = None
    face_sharpness: float | None = None
    pose_angles: tuple[float, float, float] | None = None
    face_area_ratio: float | None = None
    identity_similarity: float | None = None
    perceptual_quality: float
    aesthetic_score: float
    sharpness: float
    is_occluded: bool
    is_duplicate: bool
    composite_score: float
    pose_vector: list[float] | None = None


class CurationResult(BaseModel):
    """Returned to frontend after pipeline completes."""

    selected_ids: list[str]
    scores: dict[str, ImageScore]
    survivors_count: int
    total_count: int
    mode: CurationMode
    config: CurationConfig
```

**Step 4: Run tests**

Run: `cd C:/Dev/Projects/klippbok-main && .venv/Scripts/python.exe -m pytest tests/test_curation_models.py -v`

Expected: All PASS

**Step 5: Commit**

```bash
git add klippbok/curation/__init__.py klippbok/curation/models.py tests/test_curation_models.py
git commit -m "feat(curation): add data models for curation pipeline"
```

---

## Task 3: Model-Aware Curation Presets

**Files:**
- Create: `klippbok/curation/presets.py`
- Test: `tests/test_curation_presets.py`

**Context:** The existing model profile system lives in `klippbok/config/model_profiles.py` with profiles like `SD1.5_PROFILE`, `SDXL_PROFILE`, `FLUX_PROFILE`, `PONY_PROFILE` in `klippbok/config/model_defaults.py`. Each has a `name` field (e.g., `"sd15"`, `"sdxl"`).

**Step 1: Write the failing test**

```python
# tests/test_curation_presets.py
"""Tests for model-aware curation presets."""
import pytest
from klippbok.curation.models import CurationConfig, CurationMode
from klippbok.curation.presets import (
    get_preset,
    get_preset_for_profile,
    PRESET_REGISTRY,
)


def test_sd15_character_preset():
    cfg = get_preset("sd15", CurationMode.CHARACTER)
    assert cfg.target_count == 35
    assert cfg.mode == CurationMode.CHARACTER
    assert cfg.quality_floor_pct >= 0.25


def test_sd15_style_preset():
    cfg = get_preset("sd15", CurationMode.STYLE)
    assert cfg.target_count == 50
    assert cfg.mode == CurationMode.STYLE


def test_sdxl_character_preset():
    cfg = get_preset("sdxl", CurationMode.CHARACTER)
    assert cfg.target_count >= 40


def test_flux_character_preset():
    cfg = get_preset("flux", CurationMode.CHARACTER)
    assert cfg.target_count >= 40


def test_unknown_profile_returns_sdxl_defaults():
    cfg = get_preset("unknown_model", CurationMode.CHARACTER)
    sdxl = get_preset("sdxl", CurationMode.CHARACTER)
    assert cfg.target_count == sdxl.target_count


def test_preset_registry_has_all_profiles():
    for name in ("sd15", "sdxl", "flux", "pony"):
        assert name in PRESET_REGISTRY


def test_get_preset_for_profile():
    """Integration with ModelProfile objects."""
    from klippbok.config.model_defaults import SD1_5_PROFILE
    cfg = get_preset_for_profile(SD1_5_PROFILE, CurationMode.CHARACTER)
    assert cfg.target_count == 35
```

**Step 2: Run test to verify it fails**

Run: `cd C:/Dev/Projects/klippbok-main && .venv/Scripts/python.exe -m pytest tests/test_curation_presets.py -v`

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the implementation**

```python
# klippbok/curation/presets.py
"""Model-aware curation presets.

Maps model profile names to sensible curation defaults.
SD1.5 trains at 512px with smaller datasets; SDXL/Flux benefit from more images.
"""
from __future__ import annotations

from klippbok.curation.models import CurationConfig, CurationMode, DiversityWeights


def _character_weights() -> DiversityWeights:
    return DiversityWeights(clip_visual=0.3, pose=0.4, face=0.3)


def _style_weights() -> DiversityWeights:
    return DiversityWeights(clip_visual=0.5, pose=0.2, face=0.3)


# ── SD1.5 ───────────────────────────────────────────
_SD15_CHARACTER = CurationConfig(
    mode=CurationMode.CHARACTER,
    target_count=35,
    quality_floor_pct=0.30,
    min_face_confidence=0.5,
    min_face_area_ratio=0.06,
    max_pose_angle=70.0,
    identity_threshold=0.45,
    diversity_weights=_character_weights(),
)

_SD15_STYLE = CurationConfig(
    mode=CurationMode.STYLE,
    target_count=50,
    quality_floor_pct=0.25,
    min_face_confidence=0.3,
    min_face_area_ratio=0.03,
    max_pose_angle=85.0,
    diversity_weights=_style_weights(),
)

# ── SDXL ────────────────────────────────────────────
_SDXL_CHARACTER = CurationConfig(
    mode=CurationMode.CHARACTER,
    target_count=50,
    quality_floor_pct=0.30,
    min_face_confidence=0.5,
    min_face_area_ratio=0.05,
    max_pose_angle=75.0,
    identity_threshold=0.45,
    diversity_weights=_character_weights(),
)

_SDXL_STYLE = CurationConfig(
    mode=CurationMode.STYLE,
    target_count=65,
    quality_floor_pct=0.25,
    min_face_confidence=0.3,
    min_face_area_ratio=0.03,
    max_pose_angle=85.0,
    diversity_weights=_style_weights(),
)

# ── Flux ────────────────────────────────────────────
_FLUX_CHARACTER = CurationConfig(
    mode=CurationMode.CHARACTER,
    target_count=55,
    quality_floor_pct=0.28,
    min_face_confidence=0.5,
    min_face_area_ratio=0.05,
    max_pose_angle=75.0,
    identity_threshold=0.45,
    diversity_weights=_character_weights(),
)

_FLUX_STYLE = CurationConfig(
    mode=CurationMode.STYLE,
    target_count=70,
    quality_floor_pct=0.22,
    min_face_confidence=0.3,
    min_face_area_ratio=0.03,
    max_pose_angle=85.0,
    diversity_weights=_style_weights(),
)

# ── Pony (SDXL-based, anime-focused) ───────────────
_PONY_CHARACTER = CurationConfig(
    mode=CurationMode.CHARACTER,
    target_count=50,
    quality_floor_pct=0.30,
    min_face_confidence=0.4,
    min_face_area_ratio=0.05,
    max_pose_angle=80.0,
    identity_threshold=0.40,
    diversity_weights=_character_weights(),
)

_PONY_STYLE = CurationConfig(
    mode=CurationMode.STYLE,
    target_count=65,
    quality_floor_pct=0.25,
    min_face_confidence=0.25,
    min_face_area_ratio=0.03,
    max_pose_angle=90.0,
    diversity_weights=_style_weights(),
)

# ── Registry ────────────────────────────────────────
PRESET_REGISTRY: dict[str, dict[CurationMode, CurationConfig]] = {
    "sd15": {CurationMode.CHARACTER: _SD15_CHARACTER, CurationMode.STYLE: _SD15_STYLE},
    "sdxl": {CurationMode.CHARACTER: _SDXL_CHARACTER, CurationMode.STYLE: _SDXL_STYLE},
    "flux": {CurationMode.CHARACTER: _FLUX_CHARACTER, CurationMode.STYLE: _FLUX_STYLE},
    "pony": {CurationMode.CHARACTER: _PONY_CHARACTER, CurationMode.STYLE: _PONY_STYLE},
}

_DEFAULT_PROFILE = "sdxl"


def get_preset(profile_name: str, mode: CurationMode) -> CurationConfig:
    """Get curation preset for a model profile name and mode.

    Falls back to SDXL defaults for unknown profiles.
    Returns a copy so callers can modify without affecting registry.
    """
    modes = PRESET_REGISTRY.get(profile_name, PRESET_REGISTRY[_DEFAULT_PROFILE])
    return modes[mode].model_copy()


def get_preset_for_profile(profile: object, mode: CurationMode) -> CurationConfig:
    """Get curation preset from a ModelProfile object.

    Reads the `name` attribute from the profile.
    """
    name = getattr(profile, "name", _DEFAULT_PROFILE)
    return get_preset(name, mode)
```

**Step 4: Run tests**

Run: `cd C:/Dev/Projects/klippbok-main && .venv/Scripts/python.exe -m pytest tests/test_curation_presets.py -v`

Expected: All PASS

**Step 5: Commit**

```bash
git add klippbok/curation/presets.py tests/test_curation_presets.py
git commit -m "feat(curation): add model-aware curation presets (SD1.5, SDXL, Flux, Pony)"
```

---

## Task 4: Image Scorer — Multi-Signal Scoring Engine

**Files:**
- Create: `klippbok/curation/scorer.py`
- Test: `tests/test_curation_scorer.py`

**Context:** This is the Phase 1 engine. It loads ML models once (GPU singletons) and scores images in batches. Follows the patterns from `face_service.py` (lazy singleton) and `embeddings.py` (optional dep check).

**Step 1: Write the failing test**

```python
# tests/test_curation_scorer.py
"""Tests for multi-signal image scorer.

Uses synthetic data where possible to avoid GPU/model dependency in CI.
"""
import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from klippbok.curation.models import CurationMode, CurationConfig, ImageScore
from klippbok.curation.scorer import (
    compute_composite_score,
    _check_curation_deps,
)


def test_composite_score_character_mode():
    """Character mode weights face quality heavily."""
    score = compute_composite_score(
        mode=CurationMode.CHARACTER,
        face_confidence=0.95,
        face_sharpness=0.90,
        face_area_ratio=0.15,
        pose_frontality=0.80,
        perceptual_quality=0.75,
        aesthetic_score=0.70,
        sharpness=0.85,
        is_occluded=False,
        is_duplicate=False,
        identity_similarity=0.90,
    )
    assert 0.0 <= score <= 1.0
    assert score > 0.7  # Good image should score high


def test_composite_score_style_mode():
    """Style mode weights aesthetics heavily."""
    score = compute_composite_score(
        mode=CurationMode.STYLE,
        face_confidence=None,
        face_sharpness=None,
        face_area_ratio=None,
        pose_frontality=None,
        perceptual_quality=0.90,
        aesthetic_score=0.95,
        sharpness=0.85,
        is_occluded=False,
        is_duplicate=False,
        identity_similarity=None,
    )
    assert 0.0 <= score <= 1.0
    assert score > 0.7


def test_composite_score_duplicate_penalty():
    """Duplicates get zeroed out."""
    score = compute_composite_score(
        mode=CurationMode.CHARACTER,
        face_confidence=0.95,
        face_sharpness=0.90,
        face_area_ratio=0.15,
        pose_frontality=0.80,
        perceptual_quality=0.85,
        aesthetic_score=0.80,
        sharpness=0.85,
        is_occluded=False,
        is_duplicate=True,
        identity_similarity=0.90,
    )
    assert score == 0.0


def test_composite_score_occluded_penalty():
    """Occluded faces get heavy penalty."""
    clean = compute_composite_score(
        mode=CurationMode.CHARACTER,
        face_confidence=0.95,
        face_sharpness=0.90,
        face_area_ratio=0.15,
        pose_frontality=0.80,
        perceptual_quality=0.85,
        aesthetic_score=0.80,
        sharpness=0.85,
        is_occluded=False,
        is_duplicate=False,
        identity_similarity=0.90,
    )
    occluded = compute_composite_score(
        mode=CurationMode.CHARACTER,
        face_confidence=0.95,
        face_sharpness=0.90,
        face_area_ratio=0.15,
        pose_frontality=0.80,
        perceptual_quality=0.85,
        aesthetic_score=0.80,
        sharpness=0.85,
        is_occluded=True,
        is_duplicate=False,
        identity_similarity=0.90,
    )
    assert occluded < clean * 0.7  # At least 30% penalty


def test_composite_score_no_face_character_mode():
    """No face in character mode = low score."""
    score = compute_composite_score(
        mode=CurationMode.CHARACTER,
        face_confidence=None,
        face_sharpness=None,
        face_area_ratio=None,
        pose_frontality=None,
        perceptual_quality=0.85,
        aesthetic_score=0.80,
        sharpness=0.85,
        is_occluded=False,
        is_duplicate=False,
        identity_similarity=None,
    )
    assert score < 0.5  # Penalized for missing face


def test_composite_score_no_face_style_mode():
    """No face in style mode is acceptable."""
    score = compute_composite_score(
        mode=CurationMode.STYLE,
        face_confidence=None,
        face_sharpness=None,
        face_area_ratio=None,
        pose_frontality=None,
        perceptual_quality=0.85,
        aesthetic_score=0.80,
        sharpness=0.85,
        is_occluded=False,
        is_duplicate=False,
        identity_similarity=None,
    )
    assert score > 0.6  # Still acceptable


def test_check_curation_deps():
    """Verify dependency check doesn't raise when deps installed."""
    # This will pass if curation deps are installed, skip otherwise
    try:
        _check_curation_deps()
    except ImportError:
        pytest.skip("Curation dependencies not installed")
```

**Step 2: Run test to verify it fails**

Run: `cd C:/Dev/Projects/klippbok-main && .venv/Scripts/python.exe -m pytest tests/test_curation_scorer.py -v`

Expected: FAIL — `ImportError`

**Step 3: Write the implementation**

```python
# klippbok/curation/scorer.py
"""Phase 1: Multi-signal image scoring engine.

Loads ML models once (GPU singletons) and scores images in batches.
Each signal is extracted independently, then combined into a weighted
composite score that depends on the curation mode.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from klippbok.curation.models import CurationConfig, CurationMode, ImageScore

logger = logging.getLogger(__name__)

# ── Optional dependency checks ──────────────────────

_CURATION_AVAILABLE = False
_IMPORT_ERROR = ""

try:
    import pyiqa
    import torch
    from transformers import CLIPModel, CLIPProcessor

    _CURATION_AVAILABLE = True
except ImportError as e:
    _IMPORT_ERROR = str(e)


def _check_curation_deps() -> None:
    """Raise helpful ImportError if curation deps missing."""
    if not _CURATION_AVAILABLE:
        raise ImportError(
            f"Curation requires pyiqa, torch, and transformers.\n"
            f"Install with: pip install -e '.[curation]'\n"
            f"Missing: {_IMPORT_ERROR}"
        )


# ── Composite score computation ─────────────────────

# Character mode weights (face-heavy)
_CHAR_WEIGHTS = {
    "face_confidence": 0.10,
    "face_sharpness": 0.15,
    "face_area": 0.05,
    "pose_frontality": 0.10,
    "identity": 0.10,
    "perceptual": 0.20,
    "aesthetic": 0.15,
    "sharpness": 0.15,
}

# Style mode weights (aesthetic-heavy)
_STYLE_WEIGHTS = {
    "perceptual": 0.30,
    "aesthetic": 0.30,
    "sharpness": 0.20,
    "face_confidence": 0.05,
    "face_sharpness": 0.05,
    "face_area": 0.03,
    "pose_frontality": 0.02,
    "identity": 0.0,
    # Remaining 5% from face signals when present
}

_NO_FACE_PENALTY_CHARACTER = 0.4  # Multiply score by this if no face in character mode
_NO_FACE_PENALTY_STYLE = 1.0  # No penalty in style mode
_OCCLUSION_PENALTY = 0.5  # Multiply by this if occluded


def compute_composite_score(
    *,
    mode: CurationMode,
    face_confidence: float | None,
    face_sharpness: float | None,
    face_area_ratio: float | None,
    pose_frontality: float | None,
    perceptual_quality: float,
    aesthetic_score: float,
    sharpness: float,
    is_occluded: bool,
    is_duplicate: bool,
    identity_similarity: float | None,
) -> float:
    """Compute weighted composite score for a single image.

    Returns 0.0 for duplicates. Applies penalties for occlusion
    and missing face (in character mode).
    """
    if is_duplicate:
        return 0.0

    weights = _CHAR_WEIGHTS if mode == CurationMode.CHARACTER else _STYLE_WEIGHTS
    has_face = face_confidence is not None

    # Build signal dict with defaults for missing values
    signals = {
        "face_confidence": face_confidence or 0.0,
        "face_sharpness": face_sharpness or 0.0,
        "face_area": min((face_area_ratio or 0.0) / 0.25, 1.0),  # Normalize: 25% area = 1.0
        "pose_frontality": pose_frontality or 0.0,
        "identity": identity_similarity or 0.0,
        "perceptual": perceptual_quality,
        "aesthetic": aesthetic_score,
        "sharpness": min(sharpness / 500.0, 1.0),  # Normalize: 500 Laplacian var = 1.0
    }

    # Weighted sum
    score = sum(signals[k] * weights[k] for k in weights)

    # Normalize by total weight (in case weights don't sum to 1.0)
    total_weight = sum(weights.values())
    if total_weight > 0:
        score /= total_weight

    # Penalties
    if not has_face:
        penalty = (
            _NO_FACE_PENALTY_CHARACTER
            if mode == CurationMode.CHARACTER
            else _NO_FACE_PENALTY_STYLE
        )
        score *= penalty

    if is_occluded:
        score *= _OCCLUSION_PENALTY

    return max(0.0, min(1.0, score))


# ── GPU Model Manager ───────────────────────────────

class CurationScorer:
    """Loads ML models once, scores images in batches.

    Models are loaded lazily on first call to score_all().
    All GPU models share the same CUDA device.
    """

    def __init__(self, device: str | None = None):
        _check_curation_deps()
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self._face_app = None
        self._pyiqa_model = None
        self._aesthetic_model = None
        self._aesthetic_processor = None
        self._clip_model = None
        self._clip_processor = None
        self._pose_detector = None
        logger.info("CurationScorer initialized (device=%s)", device)

    def _ensure_face_app(self):
        if self._face_app is None:
            from klippbok.services.face_service import _get_face_app

            self._face_app = _get_face_app()
        return self._face_app

    def _ensure_pyiqa(self):
        if self._pyiqa_model is None:
            self._pyiqa_model = pyiqa.create_metric(
                "topiq_nr", device=self.device
            )
        return self._pyiqa_model

    def _ensure_aesthetic(self):
        if self._aesthetic_model is None:
            try:
                from aesthetic_predictor_v2_5 import convert_v2_5_from_siglip

                self._aesthetic_model, self._aesthetic_processor = (
                    convert_v2_5_from_siglip(
                        low_cpu_mem_usage=True,
                        trust_remote_code=True,
                    )
                )
                self._aesthetic_model = self._aesthetic_model.to(self.device)
                self._aesthetic_model.eval()
            except Exception as e:
                logger.warning("Aesthetic predictor unavailable: %s", e)
                self._aesthetic_model = None
        return self._aesthetic_model

    def _ensure_clip(self):
        if self._clip_model is None:
            model_name = "openai/clip-vit-base-patch32"
            self._clip_processor = CLIPProcessor.from_pretrained(model_name)
            self._clip_model = CLIPModel.from_pretrained(model_name).to(self.device)
            self._clip_model.eval()
        return self._clip_model

    def _detect_face(self, img_bgr: np.ndarray) -> dict | None:
        """Run InsightFace, return best face or None."""
        face_app = self._ensure_face_app()
        faces = face_app.get(img_bgr)
        if not faces:
            return None
        best = max(faces, key=lambda f: f.det_score)
        bbox = best.bbox.astype(int)
        h, w = img_bgr.shape[:2]
        face_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        frame_area = h * w

        # Face region sharpness
        x1, y1, x2, y2 = max(0, bbox[0]), max(0, bbox[1]), min(w, bbox[2]), min(h, bbox[3])
        face_crop = img_bgr[y1:y2, x1:x2]
        if face_crop.size > 0:
            gray_face = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
            face_sharp = cv2.Laplacian(gray_face, cv2.CV_64F).var()
        else:
            face_sharp = 0.0

        # Pose frontality: 1.0 = perfectly frontal, 0.0 = extreme angle
        yaw, pitch, roll = 0.0, 0.0, 0.0
        if hasattr(best, "pose") and best.pose is not None:
            yaw, pitch, roll = float(best.pose[1]), float(best.pose[0]), float(best.pose[2])
        frontality = max(0.0, 1.0 - (abs(yaw) + abs(pitch)) / 180.0)

        return {
            "confidence": float(best.det_score),
            "face_sharpness": float(face_sharp),
            "face_area_ratio": face_area / frame_area if frame_area > 0 else 0.0,
            "pose_angles": (yaw, pitch, roll),
            "frontality": frontality,
            "embedding": best.normed_embedding if hasattr(best, "normed_embedding") else None,
        }

    def _score_quality(self, img_path: Path) -> float:
        """Score perceptual quality via pyiqa TOPIQ-NR. Returns 0-1."""
        model = self._ensure_pyiqa()
        try:
            score = model(str(img_path)).item()
            return max(0.0, min(1.0, score))
        except Exception as e:
            logger.warning("pyiqa scoring failed for %s: %s", img_path, e)
            return 0.5  # Neutral fallback

    def _score_aesthetic(self, img_path: Path) -> float:
        """Score aesthetic quality via V2.5. Returns 0-1 (normalized from 1-10)."""
        model = self._ensure_aesthetic()
        if model is None:
            return 0.5  # Fallback if unavailable
        try:
            from PIL import Image as PILImage

            image = PILImage.open(img_path).convert("RGB")
            inputs = self._aesthetic_processor(images=image, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            with torch.no_grad():
                score = model(**inputs).logits.squeeze().item()
            # Normalize 1-10 scale to 0-1
            return max(0.0, min(1.0, (score - 1.0) / 9.0))
        except Exception as e:
            logger.warning("Aesthetic scoring failed for %s: %s", img_path, e)
            return 0.5

    def _check_occlusion(self, img_path: Path) -> bool:
        """Use CLIP zero-shot to detect face occlusion. Returns True if occluded."""
        clip = self._ensure_clip()
        try:
            from PIL import Image as PILImage

            image = PILImage.open(img_path).convert("RGB")
            prompts = [
                "a clear unobstructed face",
                "a face partially covered by hand or object",
                "a person wearing sunglasses or mask",
            ]
            inputs = self._clip_processor(
                text=prompts, images=image, return_tensors="pt", padding=True
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            with torch.no_grad():
                outputs = clip(**inputs)
            logits = outputs.logits_per_image.softmax(dim=1)[0]
            # Occluded if either occlusion prompt scores higher than clear face
            return bool(logits[0] < max(logits[1], logits[2]))
        except Exception as e:
            logger.warning("Occlusion check failed for %s: %s", img_path, e)
            return False

    def _extract_pose_vector(self, img_path: Path) -> list[float] | None:
        """Extract normalized pose vector via MediaPipe. Returns ~20-D or None."""
        try:
            import mediapipe as mp

            if self._pose_detector is None:
                from klippbok.image.autocrop import _ensure_model

                model_path = _ensure_model()
                options = mp.tasks.vision.PoseLandmarkerOptions(
                    base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
                    num_poses=1,
                )
                self._pose_detector = mp.tasks.vision.PoseLandmarker.create_from_options(
                    options
                )

            mp_image = mp.Image.create_from_file(str(img_path))
            result = self._pose_detector.detect(mp_image)
            if not result.pose_landmarks:
                return None

            landmarks = result.pose_landmarks[0]
            # Extract key joint angles as a compact vector
            # Use 10 key landmarks: nose, shoulders, elbows, wrists, hips, knees
            key_indices = [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26]
            vector = []
            for idx in key_indices:
                if idx < len(landmarks):
                    lm = landmarks[idx]
                    vector.extend([lm.x, lm.y])
                else:
                    vector.extend([0.0, 0.0])
            return vector
        except Exception as e:
            logger.warning("Pose extraction failed for %s: %s", img_path, e)
            return None

    def _get_clip_embedding(self, img_path: Path) -> np.ndarray | None:
        """Get CLIP image embedding (512-D). Used for Phase 2 diversity."""
        clip = self._ensure_clip()
        try:
            from PIL import Image as PILImage

            image = PILImage.open(img_path).convert("RGB")
            inputs = self._clip_processor(images=image, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            with torch.no_grad():
                emb = clip.get_image_features(**inputs)
            emb = emb / emb.norm(dim=-1, keepdim=True)
            return emb.cpu().numpy().flatten()
        except Exception as e:
            logger.warning("CLIP embedding failed for %s: %s", img_path, e)
            return None

    def score_image(
        self,
        img_path: Path,
        image_id: str,
        config: CurationConfig,
        reference_embedding: np.ndarray | None = None,
        is_duplicate: bool = False,
    ) -> tuple[ImageScore, dict[str, np.ndarray | None]]:
        """Score a single image on all dimensions.

        Returns (ImageScore, embeddings_dict) where embeddings_dict
        contains the raw embeddings for Phase 2 diversity selection.
        """
        # Read image for OpenCV operations
        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            logger.warning("Could not read image: %s", img_path)
            return self._empty_score(image_id, is_duplicate), {}

        # Whole-image sharpness
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        # Face detection
        face_data = self._detect_face(img_bgr)

        # Identity similarity (character mode only)
        identity_sim = None
        if (
            config.mode == CurationMode.CHARACTER
            and reference_embedding is not None
            and face_data
            and face_data["embedding"] is not None
        ):
            cos_sim = np.dot(reference_embedding, face_data["embedding"])
            identity_sim = float(cos_sim)

        # Perceptual quality
        perceptual = self._score_quality(img_path)

        # Aesthetic score
        aesthetic = self._score_aesthetic(img_path)

        # Occlusion check (only if face detected)
        is_occluded = False
        if face_data and face_data["confidence"] > 0.3:
            is_occluded = self._check_occlusion(img_path)

        # Pose vector
        pose_vector = self._extract_pose_vector(img_path)

        # CLIP embedding (for Phase 2)
        clip_emb = self._get_clip_embedding(img_path)

        # Compute composite
        composite = compute_composite_score(
            mode=config.mode,
            face_confidence=face_data["confidence"] if face_data else None,
            face_sharpness=face_data["face_sharpness"] if face_data else None,
            face_area_ratio=face_data["face_area_ratio"] if face_data else None,
            pose_frontality=face_data["frontality"] if face_data else None,
            perceptual_quality=perceptual,
            aesthetic_score=aesthetic,
            sharpness=sharpness,
            is_occluded=is_occluded,
            is_duplicate=is_duplicate,
            identity_similarity=identity_sim,
        )

        score = ImageScore(
            image_id=image_id,
            face_confidence=face_data["confidence"] if face_data else None,
            face_sharpness=face_data["face_sharpness"] if face_data else None,
            pose_angles=face_data["pose_angles"] if face_data else None,
            face_area_ratio=face_data["face_area_ratio"] if face_data else None,
            identity_similarity=identity_sim,
            perceptual_quality=perceptual,
            aesthetic_score=aesthetic,
            sharpness=sharpness,
            is_occluded=is_occluded,
            is_duplicate=is_duplicate,
            composite_score=composite,
            pose_vector=pose_vector,
        )

        embeddings = {
            "clip": clip_emb,
            "face": face_data["embedding"] if face_data and face_data["embedding"] is not None else None,
            "pose": np.array(pose_vector) if pose_vector else None,
        }

        return score, embeddings

    def _empty_score(self, image_id: str, is_duplicate: bool) -> ImageScore:
        return ImageScore(
            image_id=image_id,
            perceptual_quality=0.0,
            aesthetic_score=0.0,
            sharpness=0.0,
            is_occluded=False,
            is_duplicate=is_duplicate,
            composite_score=0.0,
        )
```

**Step 4: Run tests**

Run: `cd C:/Dev/Projects/klippbok-main && .venv/Scripts/python.exe -m pytest tests/test_curation_scorer.py -v`

Expected: All PASS (the `compute_composite_score` tests are pure math — no GPU needed)

**Step 5: Commit**

```bash
git add klippbok/curation/scorer.py tests/test_curation_scorer.py
git commit -m "feat(curation): add multi-signal image scorer with composite scoring"
```

---

## Task 5: Diversity Selector — apricot Facility Location

**Files:**
- Create: `klippbok/curation/diversity.py`
- Test: `tests/test_curation_diversity.py`

**Step 1: Write the failing test**

```python
# tests/test_curation_diversity.py
"""Tests for diverse subset selection via apricot."""
import numpy as np
import pytest

from klippbok.curation.diversity import select_diverse_subset, build_feature_matrix
from klippbok.curation.models import DiversityWeights


def test_select_diverse_subset_basic():
    """Select 3 from 10 random embeddings."""
    rng = np.random.RandomState(42)
    embeddings = {f"img_{i}": rng.randn(64) for i in range(10)}
    quality_scores = {f"img_{i}": 0.5 + rng.rand() * 0.5 for i in range(10)}

    selected = select_diverse_subset(
        embeddings=embeddings,
        quality_scores=quality_scores,
        target_count=3,
    )
    assert len(selected) == 3
    assert all(s in embeddings for s in selected)
    assert len(set(selected)) == 3  # No duplicates


def test_select_diverse_subset_target_exceeds_pool():
    """If target > pool size, return all."""
    embeddings = {f"img_{i}": np.random.randn(64) for i in range(5)}
    quality_scores = {f"img_{i}": 0.8 for i in range(5)}

    selected = select_diverse_subset(
        embeddings=embeddings,
        quality_scores=quality_scores,
        target_count=10,
    )
    assert len(selected) == 5


def test_select_diverse_subset_respects_pinned():
    """Pinned IDs must appear in output."""
    rng = np.random.RandomState(42)
    embeddings = {f"img_{i}": rng.randn(64) for i in range(20)}
    quality_scores = {f"img_{i}": 0.7 for i in range(20)}

    selected = select_diverse_subset(
        embeddings=embeddings,
        quality_scores=quality_scores,
        target_count=5,
        pinned_ids={"img_0", "img_19"},
    )
    assert len(selected) == 5
    assert "img_0" in selected
    assert "img_19" in selected


def test_select_diverse_subset_respects_excluded():
    """Excluded IDs must not appear in output."""
    rng = np.random.RandomState(42)
    embeddings = {f"img_{i}": rng.randn(64) for i in range(20)}
    quality_scores = {f"img_{i}": 0.7 for i in range(20)}

    selected = select_diverse_subset(
        embeddings=embeddings,
        quality_scores=quality_scores,
        target_count=5,
        excluded_ids={"img_0", "img_1", "img_2"},
    )
    assert len(selected) == 5
    assert "img_0" not in selected
    assert "img_1" not in selected
    assert "img_2" not in selected


def test_select_prefers_higher_quality():
    """Given two identical embeddings, prefer the higher-quality one."""
    emb = np.random.randn(64)
    embeddings = {
        "high_quality": emb.copy(),
        "low_quality": emb.copy() + 1e-8,  # Near-identical
    }
    quality_scores = {"high_quality": 0.95, "low_quality": 0.10}

    selected = select_diverse_subset(
        embeddings=embeddings,
        quality_scores=quality_scores,
        target_count=1,
    )
    assert selected == ["high_quality"]


def test_build_feature_matrix():
    """Build concatenated feature matrix from per-signal embeddings."""
    image_ids = ["a", "b", "c"]
    clip_embs = {"a": np.ones(4), "b": np.zeros(4), "c": np.ones(4) * 0.5}
    pose_embs = {"a": np.array([1.0, 0.0]), "b": np.array([0.0, 1.0]), "c": None}
    face_embs = {"a": np.ones(4), "b": None, "c": np.ones(4) * 0.3}

    weights = DiversityWeights(clip_visual=0.5, pose=0.3, face=0.2)
    matrix, valid_ids = build_feature_matrix(
        image_ids=image_ids,
        clip_embeddings=clip_embs,
        pose_vectors=pose_embs,
        face_embeddings=face_embs,
        weights=weights,
    )
    assert matrix.shape[0] == 3  # All images included
    assert matrix.shape[1] == 10  # 4 + 2 + 4
    assert valid_ids == ["a", "b", "c"]
```

**Step 2: Run test to verify it fails**

Run: `cd C:/Dev/Projects/klippbok-main && .venv/Scripts/python.exe -m pytest tests/test_curation_diversity.py -v`

Expected: FAIL — `ImportError`

**Step 3: Write the implementation**

```python
# klippbok/curation/diversity.py
"""Phase 2: Diverse subset selection using submodular optimization.

Uses apricot's FacilityLocation function to select a maximally diverse
subset from a pool of scored images. The feature space is a weighted
concatenation of CLIP, pose, and face embeddings.
"""
from __future__ import annotations

import logging

import numpy as np

from klippbok.curation.models import DiversityWeights

logger = logging.getLogger(__name__)


def build_feature_matrix(
    *,
    image_ids: list[str],
    clip_embeddings: dict[str, np.ndarray | None],
    pose_vectors: dict[str, np.ndarray | None],
    face_embeddings: dict[str, np.ndarray | None],
    weights: DiversityWeights,
) -> tuple[np.ndarray, list[str]]:
    """Build a concatenated, weighted feature matrix for diversity selection.

    Missing embeddings are zero-filled. Each signal is L2-normalized
    independently before weighting to prevent one signal from dominating
    due to magnitude differences.

    Returns (feature_matrix, valid_image_ids).
    """
    # Determine dimensions from first non-None embedding in each signal
    clip_dim = _infer_dim(clip_embeddings, default=512)
    pose_dim = _infer_dim(pose_vectors, default=22)
    face_dim = _infer_dim(face_embeddings, default=512)

    rows = []
    valid_ids = []

    for img_id in image_ids:
        clip_vec = _get_or_zero(clip_embeddings, img_id, clip_dim)
        pose_vec = _get_or_zero(pose_vectors, img_id, pose_dim)
        face_vec = _get_or_zero(face_embeddings, img_id, face_dim)

        # L2 normalize each signal independently
        clip_normed = _l2_normalize(clip_vec) * weights.clip_visual
        pose_normed = _l2_normalize(pose_vec) * weights.pose
        face_normed = _l2_normalize(face_vec) * weights.face

        rows.append(np.concatenate([clip_normed, pose_normed, face_normed]))
        valid_ids.append(img_id)

    return np.array(rows, dtype=np.float64), valid_ids


def select_diverse_subset(
    *,
    embeddings: dict[str, np.ndarray],
    quality_scores: dict[str, float],
    target_count: int,
    quality_weight: float = 0.15,
    pinned_ids: set[str] | None = None,
    excluded_ids: set[str] | None = None,
) -> list[str]:
    """Select a maximally diverse subset using Facility Location.

    Args:
        embeddings: Pre-built feature vectors per image (from build_feature_matrix).
        quality_scores: Composite scores per image (0-1).
        target_count: Number of images to select.
        quality_weight: How much to prefer higher-quality images (0 = pure diversity).
        pinned_ids: Images that must be in the output.
        excluded_ids: Images that must not be in the output.

    Returns:
        List of selected image IDs, ordered by selection round.
    """
    pinned_ids = pinned_ids or set()
    excluded_ids = excluded_ids or set()

    # Filter out excluded
    pool_ids = [k for k in embeddings if k not in excluded_ids]
    if not pool_ids:
        return []

    # Cap target to pool size
    effective_target = min(target_count, len(pool_ids))
    if effective_target <= 0:
        return []

    # If pool is smaller than or equal to target, return all (pinned first)
    if len(pool_ids) <= effective_target:
        pinned_first = [p for p in pool_ids if p in pinned_ids]
        rest = [p for p in pool_ids if p not in pinned_ids]
        return pinned_first + rest

    # Build matrix for pool
    pool_matrix = np.array([embeddings[k] for k in pool_ids], dtype=np.float64)

    # Quality-weight the similarity: scale each row by quality score
    # This makes higher-quality images "attract" more facility assignment
    scales = np.array(
        [1.0 + quality_weight * quality_scores.get(k, 0.5) for k in pool_ids]
    )
    weighted_matrix = pool_matrix * scales[:, np.newaxis]

    # Determine how many slots we need to fill via apricot
    n_pinned_in_pool = len([p for p in pinned_ids if p in set(pool_ids)])
    n_to_select = effective_target

    try:
        from apricot import FacilityLocationSelection

        selector = FacilityLocationSelection(
            n_samples=n_to_select,
            metric="cosine",
            optimizer="lazy",
            verbose=False,
        )
        selector.fit(weighted_matrix)
        selected_indices = list(selector.ranking)
        selected_ids = [pool_ids[i] for i in selected_indices]
    except ImportError:
        logger.warning(
            "apricot not installed, falling back to quality-ranked selection"
        )
        ranked = sorted(pool_ids, key=lambda k: quality_scores.get(k, 0.0), reverse=True)
        selected_ids = ranked[:effective_target]

    # Ensure pinned IDs are included (swap out lowest-diversity items if needed)
    selected_set = set(selected_ids)
    for pid in pinned_ids:
        if pid in excluded_ids:
            continue
        if pid not in selected_set and pid in set(pool_ids):
            # Replace the last selected item with the pinned one
            for i in range(len(selected_ids) - 1, -1, -1):
                if selected_ids[i] not in pinned_ids:
                    selected_ids[i] = pid
                    selected_set.discard(selected_ids[i])
                    selected_set.add(pid)
                    break

    return selected_ids


def _infer_dim(embs: dict[str, np.ndarray | None], default: int) -> int:
    """Get dimension from first non-None value."""
    for v in embs.values():
        if v is not None:
            return len(v)
    return default


def _get_or_zero(
    embs: dict[str, np.ndarray | None], key: str, dim: int
) -> np.ndarray:
    """Get embedding or return zero vector."""
    val = embs.get(key)
    if val is not None:
        return val.astype(np.float64)
    return np.zeros(dim, dtype=np.float64)


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    """L2 normalize, returning zeros if norm is zero."""
    norm = np.linalg.norm(vec)
    if norm < 1e-10:
        return vec
    return vec / norm
```

**Step 4: Run tests**

Run: `cd C:/Dev/Projects/klippbok-main && .venv/Scripts/python.exe -m pytest tests/test_curation_diversity.py -v`

Expected: All PASS

**Step 5: Commit**

```bash
git add klippbok/curation/diversity.py tests/test_curation_diversity.py
git commit -m "feat(curation): add diversity selector using apricot Facility Location"
```

---

## Task 6: Pipeline Orchestrator

**Files:**
- Create: `klippbok/curation/pipeline.py`
- Test: `tests/test_curation_pipeline.py`

**Step 1: Write the failing test**

```python
# tests/test_curation_pipeline.py
"""Tests for the curation pipeline orchestrator.

Uses mocks for GPU-heavy operations.
"""
import numpy as np
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path

from klippbok.curation.models import (
    CurationConfig,
    CurationMode,
    CurationResult,
    ImageScore,
)
from klippbok.curation.pipeline import (
    _filter_by_quality_floor,
    _find_reference_embedding,
)


def _make_score(image_id: str, composite: float, **kwargs) -> ImageScore:
    return ImageScore(
        image_id=image_id,
        perceptual_quality=kwargs.get("perceptual_quality", 0.5),
        aesthetic_score=kwargs.get("aesthetic_score", 0.5),
        sharpness=kwargs.get("sharpness", 100.0),
        is_occluded=kwargs.get("is_occluded", False),
        is_duplicate=kwargs.get("is_duplicate", False),
        composite_score=composite,
        **{k: v for k, v in kwargs.items()
           if k not in ("perceptual_quality", "aesthetic_score", "sharpness", "is_occluded", "is_duplicate")},
    )


def test_filter_by_quality_floor():
    """Drop bottom 30%."""
    scores = {
        "a": _make_score("a", 0.90),
        "b": _make_score("b", 0.10),
        "c": _make_score("c", 0.50),
        "d": _make_score("d", 0.70),
        "e": _make_score("e", 0.30),
        "f": _make_score("f", 0.80),
        "g": _make_score("g", 0.20),
        "h": _make_score("h", 0.60),
        "i": _make_score("i", 0.40),
        "j": _make_score("j", 0.85),
    }
    survivors = _filter_by_quality_floor(scores, floor_pct=0.30)
    assert len(survivors) == 7  # Drop bottom 3
    assert "b" not in survivors  # 0.10 dropped
    assert "g" not in survivors  # 0.20 dropped
    assert "e" not in survivors  # 0.30 dropped
    assert "a" in survivors  # 0.90 kept


def test_filter_by_quality_floor_zero():
    """Floor of 0 keeps all."""
    scores = {
        "a": _make_score("a", 0.90),
        "b": _make_score("b", 0.10),
    }
    survivors = _filter_by_quality_floor(scores, floor_pct=0.0)
    assert len(survivors) == 2


def test_find_reference_embedding_auto():
    """Auto-detect picks the face embedding from the image with highest face confidence."""
    embeddings = {
        "a": {"face": np.ones(512) * 0.5},
        "b": {"face": np.ones(512) * 0.8},
        "c": {"face": None},
    }
    scores = {
        "a": _make_score("a", 0.7, face_confidence=0.80),
        "b": _make_score("b", 0.9, face_confidence=0.95),
        "c": _make_score("c", 0.5),
    }
    ref = _find_reference_embedding(None, scores, embeddings)
    assert ref is not None
    assert np.allclose(ref, np.ones(512) * 0.8)


def test_find_reference_embedding_specified():
    """Use the specified reference image."""
    embeddings = {
        "a": {"face": np.ones(512) * 0.5},
        "b": {"face": np.ones(512) * 0.8},
    }
    scores = {
        "a": _make_score("a", 0.7, face_confidence=0.80),
        "b": _make_score("b", 0.9, face_confidence=0.95),
    }
    ref = _find_reference_embedding("a", scores, embeddings)
    assert ref is not None
    assert np.allclose(ref, np.ones(512) * 0.5)
```

**Step 2: Run test to verify it fails**

Run: `cd C:/Dev/Projects/klippbok-main && .venv/Scripts/python.exe -m pytest tests/test_curation_pipeline.py -v`

Expected: FAIL

**Step 3: Write the implementation**

```python
# klippbok/curation/pipeline.py
"""Curation pipeline orchestrator.

Chains Phase 1 (scoring) → filtering → Phase 2 (diversity selection).
Designed to run as a background task with SSE progress streaming.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import numpy as np

from klippbok.curation.models import (
    CurationConfig,
    CurationMode,
    CurationResult,
    ImageScore,
)

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, str], None]  # (current, total, message)


def _filter_by_quality_floor(
    scores: dict[str, ImageScore],
    floor_pct: float,
) -> dict[str, ImageScore]:
    """Remove the bottom floor_pct of images by composite score.

    E.g., floor_pct=0.30 drops the lowest 30%.
    """
    if floor_pct <= 0.0 or not scores:
        return dict(scores)

    sorted_ids = sorted(scores, key=lambda k: scores[k].composite_score)
    n_to_drop = int(len(sorted_ids) * floor_pct)
    drop_ids = set(sorted_ids[:n_to_drop])
    return {k: v for k, v in scores.items() if k not in drop_ids}


def _find_reference_embedding(
    reference_id: str | None,
    scores: dict[str, ImageScore],
    embeddings: dict[str, dict[str, np.ndarray | None]],
) -> np.ndarray | None:
    """Find the face embedding to use as identity anchor.

    If reference_id is specified, use that image's face embedding.
    Otherwise, pick the image with the highest face confidence.
    """
    if reference_id and reference_id in embeddings:
        emb = embeddings[reference_id].get("face")
        if emb is not None:
            return emb

    # Auto-detect: highest face confidence with a valid embedding
    best_id = None
    best_conf = -1.0
    for img_id, score in scores.items():
        if (
            score.face_confidence is not None
            and score.face_confidence > best_conf
            and img_id in embeddings
            and embeddings[img_id].get("face") is not None
        ):
            best_conf = score.face_confidence
            best_id = img_id

    if best_id:
        return embeddings[best_id].get("face")
    return None


async def run_curation(
    project_dir: Path,
    config: CurationConfig,
    progress: ProgressCallback | None = None,
    pinned_ids: set[str] | None = None,
    excluded_ids: set[str] | None = None,
) -> CurationResult:
    """Main entry point. Orchestrates the full curation pipeline.

    1. Load images from manifest
    2. Score all images (Phase 1)
    3. Filter by quality floor
    4. Find reference face embedding (character mode)
    5. Build diversity feature matrix (Phase 2)
    6. Select diverse subset via apricot
    7. Return result
    """
    import asyncio
    from klippbok.curation.scorer import CurationScorer
    from klippbok.curation.diversity import build_feature_matrix, select_diverse_subset

    pinned_ids = pinned_ids or set()
    excluded_ids = excluded_ids or set()

    def _progress(current: int, total: int, msg: str) -> None:
        if progress:
            progress(current, total, msg)

    # 1. Load images from manifest
    _progress(0, 1, "Loading image manifest...")
    image_paths, image_ids, duplicate_ids = await asyncio.to_thread(
        _load_images_from_manifest, project_dir
    )
    total = len(image_paths)
    if total == 0:
        return CurationResult(
            selected_ids=[],
            scores={},
            survivors_count=0,
            total_count=0,
            mode=config.mode,
            config=config,
        )

    _progress(0, total, f"Scoring {total} images...")

    # 2. Score all images
    scorer = CurationScorer()

    # First pass: detect reference face (character mode, no identity scoring yet)
    all_scores: dict[str, ImageScore] = {}
    all_embeddings: dict[str, dict[str, np.ndarray | None]] = {}

    # Score each image
    loop = asyncio.get_event_loop()
    for i, (img_path, img_id) in enumerate(zip(image_paths, image_ids)):
        is_dup = img_id in duplicate_ids
        score, embs = await loop.run_in_executor(
            None,
            scorer.score_image,
            img_path,
            img_id,
            config,
            None,  # No reference yet for first pass
            is_dup,
        )
        all_scores[img_id] = score
        all_embeddings[img_id] = embs
        _progress(i + 1, total, f"Scored {i + 1}/{total}")

    # 3. Find reference embedding and re-score identity (character mode)
    if config.mode == CurationMode.CHARACTER:
        ref_emb = _find_reference_embedding(
            config.reference_image_id, all_scores, all_embeddings
        )
        if ref_emb is not None:
            _progress(total, total, "Computing identity similarity...")
            for img_id, score in all_scores.items():
                face_emb = all_embeddings.get(img_id, {}).get("face")
                if face_emb is not None:
                    sim = float(np.dot(ref_emb, face_emb))
                    score.identity_similarity = sim
                    # Recompute composite with identity
                    from klippbok.curation.scorer import compute_composite_score

                    score.composite_score = compute_composite_score(
                        mode=config.mode,
                        face_confidence=score.face_confidence,
                        face_sharpness=score.face_sharpness,
                        face_area_ratio=score.face_area_ratio,
                        pose_frontality=score.pose_angles[0] if score.pose_angles else None,
                        perceptual_quality=score.perceptual_quality,
                        aesthetic_score=score.aesthetic_score,
                        sharpness=score.sharpness,
                        is_occluded=score.is_occluded,
                        is_duplicate=score.is_duplicate,
                        identity_similarity=sim,
                    )

    # 4. Filter by quality floor
    _progress(total, total, "Filtering by quality floor...")
    survivors = _filter_by_quality_floor(all_scores, config.quality_floor_pct)

    # Filter by face constraints (character mode)
    if config.mode == CurationMode.CHARACTER:
        survivors = {
            k: v for k, v in survivors.items()
            if (
                v.face_confidence is not None
                and v.face_confidence >= config.min_face_confidence
                and (v.face_area_ratio or 0) >= config.min_face_area_ratio
                and (
                    v.identity_similarity is None
                    or v.identity_similarity >= config.identity_threshold
                )
            )
            or k in pinned_ids
        }

    survivors_count = len(survivors)

    # 5. Build feature matrix
    _progress(total, total, "Building diversity features...")
    survivor_ids = list(survivors.keys())

    clip_embs = {k: all_embeddings.get(k, {}).get("clip") for k in survivor_ids}
    pose_embs = {k: all_embeddings.get(k, {}).get("pose") for k in survivor_ids}
    face_embs = {k: all_embeddings.get(k, {}).get("face") for k in survivor_ids}

    feature_matrix, valid_ids = build_feature_matrix(
        image_ids=survivor_ids,
        clip_embeddings=clip_embs,
        pose_vectors=pose_embs,
        face_embeddings=face_embs,
        weights=config.diversity_weights,
    )

    # Convert to per-image embedding dict for select_diverse_subset
    emb_dict = {valid_ids[i]: feature_matrix[i] for i in range(len(valid_ids))}
    quality_dict = {k: survivors[k].composite_score for k in valid_ids}

    # 6. Select diverse subset
    _progress(total, total, "Selecting diverse subset...")
    selected = select_diverse_subset(
        embeddings=emb_dict,
        quality_scores=quality_dict,
        target_count=config.target_count,
        pinned_ids=pinned_ids,
        excluded_ids=excluded_ids,
    )

    _progress(total, total, "Curation complete!")

    return CurationResult(
        selected_ids=selected,
        scores=all_scores,
        survivors_count=survivors_count,
        total_count=total,
        mode=config.mode,
        config=config,
    )


def _load_images_from_manifest(
    project_dir: Path,
) -> tuple[list[Path], list[str], set[str]]:
    """Load image paths and IDs from the project manifest.

    Returns (paths, ids, duplicate_ids).
    """
    import json

    manifest_path = project_dir / ".klippbok" / "manifest.json"
    if not manifest_path.exists():
        return [], [], set()

    with open(manifest_path) as f:
        manifest = json.load(f)

    images = manifest.get("images", {})
    paths = []
    ids = []
    duplicate_ids = set()

    for rel_path, meta in images.items():
        full_path = project_dir / rel_path
        if not full_path.exists():
            continue

        import hashlib

        image_id = hashlib.sha256(rel_path.encode()).hexdigest()[:16]
        paths.append(full_path)
        ids.append(image_id)

        if meta.get("is_near_duplicate", False):
            duplicate_ids.add(image_id)

    return paths, ids, duplicate_ids
```

**Step 4: Run tests**

Run: `cd C:/Dev/Projects/klippbok-main && .venv/Scripts/python.exe -m pytest tests/test_curation_pipeline.py -v`

Expected: All PASS

**Step 5: Commit**

```bash
git add klippbok/curation/pipeline.py tests/test_curation_pipeline.py
git commit -m "feat(curation): add pipeline orchestrator (score → filter → diversify)"
```

---

## Task 7: API Router with SSE Progress

**Files:**
- Create: `klippbok/api/routers/curation.py`
- Modify: `klippbok/api/app.py` (~line 40 for import, ~line 105 for registration)
- Modify: `klippbok/api/models.py` (add curation request/response models)
- Test: `tests/test_curation_api.py`

**Context:** Follow the SSE pattern from `klippbok/api/routers/cleanup.py`: module-level dicts for tasks/queues/results, background coroutine with `loop.call_soon_threadsafe()`, SSE generator with None sentinel.

**Step 1: Write the API router**

```python
# klippbok/api/routers/curation.py
"""Curation API endpoints with SSE progress streaming.

Follows the same pattern as cleanup.py:
- POST /start → operation_id
- GET /progress/{op_id} → SSE stream
- GET /result/{op_id} → CurationResult JSON
- POST /rerun → re-diversify with pins/exclusions
- POST /apply → apply selection to gallery
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from klippbok.curation.models import (
    CurationConfig,
    CurationMode,
    CurationResult,
    DiversityWeights,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/curation", tags=["curation"])

# ── Module-level state ──────────────────────────────
_curation_tasks: dict[str, asyncio.Task] = {}
_curation_queues: dict[str, asyncio.Queue] = {}
_curation_results: dict[str, CurationResult] = {}

# ── Request models ──────────────────────────────────


class CurationStartRequest(BaseModel):
    mode: CurationMode = CurationMode.CHARACTER
    target_count: int | None = None  # None = use preset default
    quality_floor_pct: float | None = None
    reference_image_id: str | None = None
    diversity_weights: DiversityWeights | None = None


class CurationRerunRequest(BaseModel):
    operation_id: str
    pinned_ids: list[str] = []
    excluded_ids: list[str] = []
    target_count: int | None = None


class CurationApplyRequest(BaseModel):
    operation_id: str


# ── Background task ─────────────────────────────────


async def _run_curation_bg(
    project_dir: str,
    config: CurationConfig,
    queue: asyncio.Queue,
    pinned_ids: set[str] | None = None,
    excluded_ids: set[str] | None = None,
) -> None:
    """Background curation task. Sends progress events to queue."""
    from pathlib import Path
    from klippbok.curation.pipeline import run_curation

    loop = asyncio.get_event_loop()

    def progress_cb(current: int, total: int, message: str) -> None:
        event = {
            "event": "curation_progress",
            "current": current,
            "total": total,
            "message": message,
        }
        loop.call_soon_threadsafe(queue.put_nowait, event)

    try:
        result = await run_curation(
            project_dir=Path(project_dir),
            config=config,
            progress=progress_cb,
            pinned_ids=pinned_ids,
            excluded_ids=excluded_ids,
        )

        # Store result for later retrieval
        # Find op_id from queue (stored in task name)
        op_id = asyncio.current_task().get_name().replace("curation-", "")
        _curation_results[op_id] = result

        done_event = {
            "event": "curation_done",
            "selected_count": len(result.selected_ids),
            "survivors_count": result.survivors_count,
            "total_count": result.total_count,
        }
        queue.put_nowait(done_event)

    except Exception as e:
        logger.exception("Curation failed: %s", e)
        queue.put_nowait({
            "event": "curation_error",
            "error": str(e),
        })
    finally:
        queue.put_nowait(None)  # Sentinel


# ── SSE generator ───────────────────────────────────


async def _sse_generator(
    queue: asyncio.Queue,
    op_id: str,
) -> Any:
    """Yield SSE events from the curation queue."""
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield ServerSentEvent(
                event=event["event"],
                data=json.dumps(event),
            )
    finally:
        _curation_tasks.pop(op_id, None)
        _curation_queues.pop(op_id, None)


# ── Endpoints ───────────────────────────────────────


@router.post("/start")
async def start_curation(req: CurationStartRequest, request: Request):
    """Start a curation pipeline run. Returns operation_id."""
    project_dir = request.app.state.project_dir
    if not project_dir:
        raise HTTPException(status_code=400, detail="No project directory set")

    # Build config from request + preset defaults
    from klippbok.curation.presets import get_preset

    # Load active profile from manifest
    profile_name = _get_active_profile(project_dir)
    preset = get_preset(profile_name, req.mode)

    # Override preset with request values
    config = preset.model_copy(
        update={
            k: v
            for k, v in {
                "target_count": req.target_count,
                "quality_floor_pct": req.quality_floor_pct,
                "reference_image_id": req.reference_image_id,
                "diversity_weights": req.diversity_weights,
            }.items()
            if v is not None
        }
    )

    op_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _curation_queues[op_id] = queue

    task = asyncio.create_task(
        _run_curation_bg(str(project_dir), config, queue),
        name=f"curation-{op_id}",
    )
    _curation_tasks[op_id] = task

    return {"operation_id": op_id}


@router.get("/progress/{op_id}")
async def curation_progress(op_id: str):
    """SSE stream of curation progress events."""
    queue = _curation_queues.get(op_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Operation not found")

    return EventSourceResponse(_sse_generator(queue, op_id))


@router.get("/result/{op_id}")
async def get_curation_result(op_id: str):
    """Get the curation result after pipeline completes."""
    result = _curation_results.get(op_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found (still running?)")

    return result.model_dump()


@router.post("/rerun")
async def rerun_curation(req: CurationRerunRequest, request: Request):
    """Re-run diversity selection with updated pins/exclusions."""
    project_dir = request.app.state.project_dir
    if not project_dir:
        raise HTTPException(status_code=400, detail="No project directory set")

    prev_result = _curation_results.get(req.operation_id)
    if not prev_result:
        raise HTTPException(status_code=404, detail="Previous result not found")

    # Re-use the previous config, optionally updating target_count
    config = prev_result.config.model_copy()
    if req.target_count is not None:
        config.target_count = req.target_count

    op_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _curation_queues[op_id] = queue

    task = asyncio.create_task(
        _run_curation_bg(
            str(project_dir),
            config,
            queue,
            pinned_ids=set(req.pinned_ids),
            excluded_ids=set(req.excluded_ids),
        ),
        name=f"curation-{op_id}",
    )
    _curation_tasks[op_id] = task

    return {"operation_id": op_id}


@router.post("/apply")
async def apply_curation(req: CurationApplyRequest):
    """Mark curation as applied. Frontend uses the selected_ids to set gallery selection."""
    result = _curation_results.get(req.operation_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    return {
        "applied": True,
        "selected_ids": result.selected_ids,
        "count": len(result.selected_ids),
    }


# ── Helpers ─────────────────────────────────────────


def _get_active_profile(project_dir: str) -> str:
    """Read active model profile from manifest."""
    import json
    from pathlib import Path

    manifest_path = Path(project_dir) / ".klippbok" / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
        return manifest.get("active_profile", "sdxl")
    return "sdxl"
```

**Step 2: Register the router in app.py**

In `klippbok/api/app.py`, add the import alongside other router imports (~line 40):

```python
from klippbok.api.routers.curation import router as curation_router
```

And register it alongside other routers (~line 105):

```python
app.include_router(curation_router, prefix="/api/v1")
```

Also add `_curation_tasks` to the lifespan cleanup (~line 70):

```python
from klippbok.api.routers.curation import _curation_tasks as curation_tasks
# In the shutdown section:
for task in curation_tasks.values():
    if not task.done():
        task.cancel()
```

**Step 3: Run tests**

Run: `cd C:/Dev/Projects/klippbok-main && .venv/Scripts/python.exe -m pytest tests/test_curation_api.py -v`

(Write a basic smoke test that imports the router and checks routes exist)

**Step 4: Commit**

```bash
git add klippbok/api/routers/curation.py klippbok/api/app.py tests/test_curation_api.py
git commit -m "feat(curation): add API router with SSE progress streaming"
```

---

## Task 8: Frontend Types and API Hook

**Files:**
- Create: `frontend/src/types/curation.ts`
- Create: `frontend/src/hooks/useCuration.ts`

**Step 1: Add TypeScript types**

```typescript
// frontend/src/types/curation.ts
export type CurationMode = 'character' | 'style'

export interface DiversityWeights {
  clip_visual: number
  pose: number
  face: number
}

export interface CurationConfig {
  mode: CurationMode
  target_count: number
  quality_floor_pct: number
  min_face_confidence: number
  min_face_area_ratio: number
  max_pose_angle: number
  identity_threshold: number
  reference_image_id: string | null
  diversity_weights: DiversityWeights
}

export interface ImageScore {
  image_id: string
  face_confidence: number | null
  face_sharpness: number | null
  pose_angles: [number, number, number] | null
  face_area_ratio: number | null
  identity_similarity: number | null
  perceptual_quality: number
  aesthetic_score: number
  sharpness: number
  is_occluded: boolean
  is_duplicate: boolean
  composite_score: number
  pose_vector: number[] | null
}

export interface CurationResult {
  selected_ids: string[]
  scores: Record<string, ImageScore>
  survivors_count: number
  total_count: number
  mode: CurationMode
  config: CurationConfig
}

export interface CurationStartRequest {
  mode: CurationMode
  target_count?: number
  quality_floor_pct?: number
  reference_image_id?: string | null
  diversity_weights?: DiversityWeights
}

export interface CurationProgress {
  event: string
  current: number
  total: number
  message: string
}
```

**Step 2: Add the curation hook**

```typescript
// frontend/src/hooks/useCuration.ts
import { useState, useCallback, useRef } from 'react'
import type {
  CurationStartRequest,
  CurationResult,
  CurationProgress,
} from '../types/curation'

interface UseCurationReturn {
  isRunning: boolean
  progress: CurationProgress | null
  result: CurationResult | null
  error: string | null
  operationId: string | null
  startCuration: (req: CurationStartRequest) => Promise<void>
  rerun: (pinnedIds: string[], excludedIds: string[], targetCount?: number) => Promise<void>
  applyCuration: () => Promise<string[]>
  reset: () => void
}

export function useCuration(): UseCurationReturn {
  const [isRunning, setIsRunning] = useState(false)
  const [progress, setProgress] = useState<CurationProgress | null>(null)
  const [result, setResult] = useState<CurationResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [operationId, setOperationId] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  const cleanup = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }, [])

  const listenForProgress = useCallback(
    (opId: string) => {
      cleanup()
      const es = new EventSource(`/api/v1/curation/progress/${opId}`)
      eventSourceRef.current = es

      es.addEventListener('curation_progress', (e) => {
        setProgress(JSON.parse(e.data))
      })

      es.addEventListener('curation_done', async (e) => {
        es.close()
        // Fetch full result
        const res = await fetch(`/api/v1/curation/result/${opId}`)
        if (res.ok) {
          const data = await res.json()
          setResult(data)
        }
        setIsRunning(false)
      })

      es.addEventListener('curation_error', (e) => {
        const data = JSON.parse(e.data)
        setError(data.error)
        setIsRunning(false)
        es.close()
      })

      es.onerror = () => {
        setError('Connection lost')
        setIsRunning(false)
        es.close()
      }
    },
    [cleanup],
  )

  const startCuration = useCallback(
    async (req: CurationStartRequest) => {
      setIsRunning(true)
      setError(null)
      setResult(null)
      setProgress(null)

      const res = await fetch('/api/v1/curation/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      })

      if (!res.ok) {
        const msg = await res.text()
        setError(`Failed to start: ${msg}`)
        setIsRunning(false)
        return
      }

      const { operation_id } = await res.json()
      setOperationId(operation_id)
      listenForProgress(operation_id)
    },
    [listenForProgress],
  )

  const rerun = useCallback(
    async (pinnedIds: string[], excludedIds: string[], targetCount?: number) => {
      if (!operationId) return

      setIsRunning(true)
      setError(null)
      setProgress(null)

      const res = await fetch('/api/v1/curation/rerun', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          operation_id: operationId,
          pinned_ids: pinnedIds,
          excluded_ids: excludedIds,
          target_count: targetCount,
        }),
      })

      if (!res.ok) {
        const msg = await res.text()
        setError(`Re-run failed: ${msg}`)
        setIsRunning(false)
        return
      }

      const { operation_id: newOpId } = await res.json()
      setOperationId(newOpId)
      listenForProgress(newOpId)
    },
    [operationId, listenForProgress],
  )

  const applyCuration = useCallback(async () => {
    if (!operationId) return []

    const res = await fetch('/api/v1/curation/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ operation_id: operationId }),
    })

    if (!res.ok) return []
    const data = await res.json()
    return data.selected_ids as string[]
  }, [operationId])

  const reset = useCallback(() => {
    cleanup()
    setIsRunning(false)
    setProgress(null)
    setResult(null)
    setError(null)
    setOperationId(null)
  }, [cleanup])

  return {
    isRunning,
    progress,
    result,
    error,
    operationId,
    startCuration,
    rerun,
    applyCuration,
    reset,
  }
}
```

**Step 3: Commit**

```bash
git add frontend/src/types/curation.ts frontend/src/hooks/useCuration.ts
git commit -m "feat(curation): add frontend types and useCuration hook"
```

---

## Task 9: Curation Page — Config Panel + Progress

**Files:**
- Create: `frontend/src/pages/CuratePage.tsx`
- Modify: `frontend/src/App.tsx` (add route)

**Step 1: Create the page component**

```typescript
// frontend/src/pages/CuratePage.tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCuration } from '../hooks/useCuration'
import { useImages } from '../hooks/useImages'
import useAppStore from '../stores/appStore'
import type { CurationMode, CurationStartRequest } from '../types/curation'

export default function CuratePage() {
  const navigate = useNavigate()
  const { data } = useImages()
  const selectByFilter = useAppStore((s) => s.selectByFilter)
  const {
    isRunning,
    progress,
    result,
    error,
    startCuration,
    rerun,
    applyCuration,
    reset,
  } = useCuration()

  // Config state
  const [mode, setMode] = useState<CurationMode>('character')
  const [targetCount, setTargetCount] = useState<number | undefined>(undefined)
  const [pinnedIds, setPinnedIds] = useState<Set<string>>(new Set())
  const [excludedIds, setExcludedIds] = useState<Set<string>>(new Set())

  const handleStart = () => {
    const req: CurationStartRequest = {
      mode,
      target_count: targetCount || undefined,
    }
    startCuration(req)
  }

  const handleRerun = () => {
    rerun(Array.from(pinnedIds), Array.from(excludedIds), targetCount)
  }

  const handleApply = async () => {
    const ids = await applyCuration()
    if (ids.length > 0) {
      selectByFilter(ids)
      navigate('/')
    }
  }

  const togglePin = (id: string) => {
    setPinnedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
        // Remove from excluded if pinned
        setExcludedIds((ex) => {
          const n = new Set(ex)
          n.delete(id)
          return n
        })
      }
      return next
    })
  }

  const toggleExclude = (id: string) => {
    setExcludedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
        // Remove from pinned if excluded
        setPinnedIds((p) => {
          const n = new Set(p)
          n.delete(id)
          return n
        })
      }
      return next
    })
  }

  const totalImages = data?.images?.length ?? 0

  return (
    <div className="curate-page">
      <div className="curate-header">
        <h1>Curate Dataset</h1>
        {result && (
          <span className="curate-summary">
            {result.total_count} scanned → {result.survivors_count} passed →{' '}
            {result.selected_ids.length} selected
          </span>
        )}
      </div>

      {/* Config Panel */}
      {!result && !isRunning && (
        <div className="curate-config">
          <div className="curate-config-row">
            <label>
              Mode
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as CurationMode)}
              >
                <option value="character">Character</option>
                <option value="style">Style / Aesthetic</option>
              </select>
            </label>

            <label>
              Target count
              <input
                type="number"
                min={5}
                max={200}
                placeholder="Auto (from profile)"
                value={targetCount ?? ''}
                onChange={(e) =>
                  setTargetCount(e.target.value ? Number(e.target.value) : undefined)
                }
              />
            </label>
          </div>

          <button
            className="curate-start-btn"
            onClick={handleStart}
            disabled={totalImages === 0}
          >
            Start Curation ({totalImages} images)
          </button>
        </div>
      )}

      {/* Progress */}
      {isRunning && progress && (
        <div className="curate-progress">
          <div className="curate-progress-bar">
            <div
              className="curate-progress-fill"
              style={{
                width: `${
                  progress.total > 0
                    ? (progress.current / progress.total) * 100
                    : 0
                }%`,
              }}
            />
          </div>
          <span className="curate-progress-text">{progress.message}</span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="curate-error">
          <span>{error}</span>
          <button onClick={reset}>Retry</button>
        </div>
      )}

      {/* Results Grid */}
      {result && (
        <div className="curate-results">
          <div className="curate-results-grid">
            {result.selected_ids
              .filter((id) => !excludedIds.has(id))
              .map((id) => {
                const score = result.scores[id]
                const isPinned = pinnedIds.has(id)
                return (
                  <div
                    key={id}
                    className={`curate-card ${isPinned ? 'curate-card--pinned' : ''}`}
                  >
                    <img
                      src={`/api/v1/images/${id}/thumbnail`}
                      alt=""
                      loading="lazy"
                    />
                    <div className="curate-card-score">
                      {(score?.composite_score ?? 0).toFixed(2)}
                    </div>
                    {isPinned && <div className="curate-card-pin">pinned</div>}
                    <div className="curate-card-actions">
                      <button
                        onClick={() => togglePin(id)}
                        title={isPinned ? 'Unpin' : 'Pin'}
                      >
                        {isPinned ? 'Unpin' : 'Pin'}
                      </button>
                      <button onClick={() => toggleExclude(id)} title="Exclude">
                        Exclude
                      </button>
                    </div>
                  </div>
                )
              })}
          </div>

          <div className="curate-actions">
            <button onClick={handleRerun} disabled={isRunning}>
              Re-run Selection
            </button>
            <button className="curate-apply-btn" onClick={handleApply}>
              Apply Selection ({result.selected_ids.length - excludedIds.size})
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
```

**Step 2: Add route in App.tsx**

Add import at top:
```typescript
import CuratePage from './pages/CuratePage'
```

Add route inside `<Routes>`:
```typescript
<Route path="/curate" element={<CuratePage />} />
```

**Step 3: Add CSS**

Add styles to `frontend/src/App.css` for `.curate-page`, `.curate-config`, `.curate-progress`, `.curate-results-grid`, `.curate-card`, etc. Follow existing patterns from `.cleanup-page` and `.crop-page`.

**Step 4: Add Curate button to SelectionToolbar**

In `frontend/src/components/Gallery/SelectionToolbar.tsx`, add a "Curate" navigation button:

```typescript
function handleCurate() {
  navigate('/curate')
}

// In the JSX, add before the existing buttons:
<button onClick={handleCurate}>Curate Dataset</button>
```

**Step 5: Build and verify**

Run: `cd C:/Dev/Projects/klippbok-main/frontend && npx vite build`
Then: `cd C:/Dev/Projects/klippbok-main && rm -rf klippbok/api/static/* && cp -r frontend/dist/* klippbok/api/static/`

**Step 6: Commit**

```bash
git add frontend/src/pages/CuratePage.tsx frontend/src/App.tsx frontend/src/App.css frontend/src/components/Gallery/SelectionToolbar.tsx
git commit -m "feat(curation): add CuratePage with config panel, progress, and results grid"
```

---

## Task 10: Score Detail Popover

**Files:**
- Create: `frontend/src/components/Curation/ScorePopover.tsx`
- Modify: `frontend/src/pages/CuratePage.tsx` (integrate popover)

**Step 1: Create the popover component**

```typescript
// frontend/src/components/Curation/ScorePopover.tsx
import type { ImageScore } from '../../types/curation'

interface ScorePopoverProps {
  score: ImageScore
  onPin: () => void
  onExclude: () => void
  onClose: () => void
  isPinned: boolean
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? '#22c55e' : pct >= 60 ? '#eab308' : '#ef4444'
  return (
    <div className="score-bar-row">
      <span className="score-bar-label">{label}</span>
      <div className="score-bar-track">
        <div
          className="score-bar-fill"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="score-bar-value">{value.toFixed(2)}</span>
    </div>
  )
}

export default function ScorePopover({
  score,
  onPin,
  onExclude,
  onClose,
  isPinned,
}: ScorePopoverProps) {
  return (
    <div className="score-popover" onClick={(e) => e.stopPropagation()}>
      <button className="score-popover-close" onClick={onClose}>
        x
      </button>
      <h3>Score Breakdown</h3>

      {score.face_confidence != null && (
        <ScoreBar label="Face quality" value={score.face_confidence} />
      )}
      <ScoreBar label="Perceptual (IQA)" value={score.perceptual_quality} />
      <ScoreBar label="Aesthetic" value={score.aesthetic_score} />
      <ScoreBar
        label="Sharpness"
        value={Math.min(score.sharpness / 500, 1.0)}
      />
      {score.identity_similarity != null && (
        <ScoreBar label="Identity match" value={score.identity_similarity} />
      )}
      {score.face_area_ratio != null && (
        <ScoreBar
          label="Face prominence"
          value={Math.min(score.face_area_ratio / 0.25, 1.0)}
        />
      )}

      {score.pose_angles && (
        <div className="score-pose-info">
          Pose: {Math.abs(score.pose_angles[0]).toFixed(0)} yaw,{' '}
          {Math.abs(score.pose_angles[1]).toFixed(0)} pitch
        </div>
      )}

      {score.is_occluded && (
        <div className="score-warning">Occlusion detected</div>
      )}

      <div className="score-popover-actions">
        <button onClick={onPin}>{isPinned ? 'Unpin' : 'Pin'}</button>
        <button onClick={onExclude}>Exclude</button>
      </div>
    </div>
  )
}
```

**Step 2: Integrate into CuratePage** — add click handler on curate-card that opens ScorePopover.

**Step 3: Add CSS for `.score-popover`, `.score-bar-row`, `.score-bar-track`, `.score-bar-fill`.

**Step 4: Build, copy, commit**

```bash
git add frontend/src/components/Curation/ScorePopover.tsx frontend/src/pages/CuratePage.tsx frontend/src/App.css
git commit -m "feat(curation): add score breakdown popover for selected images"
```

---

## Task 11: Rejected Pool + Swap UI

**Files:**
- Modify: `frontend/src/pages/CuratePage.tsx` (add rejected pool section)

**Step 1: Add rejected pool section**

Below the results grid, add a collapsible section showing non-selected images. Each rejected image has a "Swap in" button. When clicked, it replaces the most recently excluded image (or the lowest-scoring non-pinned image).

**Step 2: Build, copy, commit**

```bash
git commit -m "feat(curation): add rejected pool and swap functionality"
```

---

## Task 12: Integration Test — Full Pipeline

**Files:**
- Create: `tests/test_curation_integration.py`

**Step 1: Write integration test**

```python
# tests/test_curation_integration.py
"""Integration test for the full curation pipeline.

Requires GPU + curation deps. Skip in CI.
"""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from klippbok.curation.models import CurationConfig, CurationMode, CurationResult
from klippbok.curation.pipeline import _filter_by_quality_floor, _find_reference_embedding


@pytest.mark.skipif(
    not Path("C:/GenAI/Training/Instagram/natahrie/temp/test").exists(),
    reason="Test project dir not available",
)
class TestCurationIntegration:
    """Full pipeline integration tests against real test data."""

    @pytest.fixture
    def project_dir(self):
        return Path("C:/GenAI/Training/Instagram/natahrie/temp/test")

    @pytest.mark.asyncio
    async def test_full_pipeline_character_mode(self, project_dir):
        from klippbok.curation.pipeline import run_curation

        config = CurationConfig(
            mode=CurationMode.CHARACTER,
            target_count=10,
            quality_floor_pct=0.20,
        )
        result = await run_curation(project_dir, config)
        assert isinstance(result, CurationResult)
        assert len(result.selected_ids) <= 10
        assert result.total_count > 0
        assert result.survivors_count <= result.total_count
```

**Step 2: Run**

Run: `cd C:/Dev/Projects/klippbok-main && .venv/Scripts/python.exe -m pytest tests/test_curation_integration.py -v --timeout=120`

**Step 3: Commit**

```bash
git add tests/test_curation_integration.py
git commit -m "test(curation): add integration test for full pipeline"
```

---

## Task 13: Final Wiring + Manual Verification

**Step 1: Rebuild frontend**

```bash
cd C:/Dev/Projects/klippbok-main/frontend && npx vite build
cd C:/Dev/Projects/klippbok-main && rm -rf klippbok/api/static/* && cp -r frontend/dist/* klippbok/api/static/
```

**Step 2: Restart server**

```bash
.venv/Scripts/python.exe -m klippbok.api --port 9000
```

**Step 3: Manual verification checklist**

1. Navigate to gallery → "Curate Dataset" button visible in toolbar
2. Click Curate → config panel shows (mode, target count)
3. Select "Character" mode, start curation
4. Progress bar animates through scoring phase
5. Results grid shows selected images with score badges
6. Click image → score breakdown popover appears
7. Pin an image → pinned badge appears
8. Exclude an image → removed from grid
9. Re-run → new selection respects pins/exclusions
10. Apply → returns to gallery with curated set selected

**Step 4: Final commit**

```bash
git commit -m "feat(curation): complete dataset curation pipeline with review UI"
```
