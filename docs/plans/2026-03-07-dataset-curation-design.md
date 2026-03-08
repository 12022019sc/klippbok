# Dataset Curation Design — Automated Image Selection for LoRA Training

**Date:** 2026-03-07
**Branch:** feat/dataset-prep-gui
**Status:** Approved

---

## Problem

Given a gallery of hundreds of mixed-source images (video frames + standalone photos), automatically select the best ~N images for character LoRA training. The selection must optimize for both individual image quality AND dataset diversity (pose, background, expression variety).

## Requirements

- **Two curation modes:** Character (identity-anchored) and Style (aesthetic-focused)
- **Model-aware presets:** Target count and thresholds vary by model profile (SD1.5, SDXL, Flux, Pony)
- **One-click auto-curate** with guided review UI for adjustments
- **Process ~400 images in under 45 seconds** on RTX 5080
- **Extensible** — new scoring signals can be added without rearchitecting

## Approach: Score then Diversify (Approach B)

Two-phase pipeline:
1. **Phase 1 (Score & Filter):** Multi-signal scoring, drop bottom 30% by quality floor
2. **Phase 2 (Diverse Selection):** Submodular optimization (apricot Facility Location) on concatenated feature embeddings

### Why not simpler (Approach A — rank only)?

Top-N by score alone has no diversity guarantee — could select 40 images of the same pose/angle.

### Why not fuller (Approach C — background segmentation + expression classification)?

CLIP embeddings capture background and expression variety implicitly. Approach C documented as upgrade path below.

---

## Architecture

```
Phase 1: Score & Filter
  All Images
    ├──► InsightFace → face confidence, pose angles, area ratio, embedding
    ├──► pyiqa (TOPIQ-NR) → perceptual quality
    ├──► Aesthetic Predictor V2.5 → aesthetic/composition score
    ├──► OpenCV Laplacian → face-region + whole-image sharpness
    ├──► MediaPipe Pose → normalized joint angle vector (~20-D)
    ├──► CLIP zero-shot → occlusion flags
    └──► pHash → duplicate detection
  → Composite score → Quality floor filter → Survivors

Phase 2: Diverse Subset Selection
  Survivors
    ├──► CLIP embeddings (512-D)
    ├──► Pose vectors (~20-D, from MediaPipe)
    └──► Face embeddings (512-D, from InsightFace)
  → Concatenate + normalize → apricot FacilityLocation → Best N

Phase 3: Review & Adjust (Frontend)
  → Score breakdown per image → Pin/Exclude/Swap → Re-run → Apply
```

## Curation Modes

| Aspect | Character Mode | Style Mode |
|--------|---------------|------------|
| Identity check | Yes — face embedding cosine similarity to reference | No |
| Primary diversity axis | Pose + background variety | Visual + aesthetic variety |
| Default target (SD1.5) | 30-40 images | 50-60 images |
| Default target (SDXL/Flux) | 40-60 images | 60-80 images |
| Phase 1 weight emphasis | Face quality 40%, Technical 25%, Aesthetic 20%, Other 15% | Aesthetic 35%, Technical 30%, Face 20%, Other 15% |

### Model Profile Integration

Curation presets loaded from existing `ModelProfile` system:

```python
class CurationPreset:
    target_count: int
    quality_floor_pct: float        # bottom % to drop (default 0.30)
    min_face_confidence: float      # InsightFace det_score threshold
    min_face_area_ratio: float      # face >= X% of frame
    max_pose_angle: float           # reject beyond this yaw/pitch
    weights: dict[str, float]       # signal weight overrides per mode
```

---

## Backend Module Structure

```
klippbok/curation/
├── __init__.py
├── scorer.py          # Phase 1: Multi-signal image scoring
├── diversity.py       # Phase 2: Diverse subset selection via apricot
├── pipeline.py        # Orchestrator: scoring → filtering → selection
├── presets.py         # Model-aware curation presets
└── models.py          # Pydantic models: CurationConfig, ImageScore, CurationResult
```

### Key Data Models

```python
class CurationMode(str, Enum):
    CHARACTER = "character"
    STYLE = "style"

class ImageScore(BaseModel):
    image_id: str
    face_confidence: float | None
    face_sharpness: float | None
    pose_angles: tuple[float, float, float] | None  # yaw, pitch, roll
    face_area_ratio: float | None
    identity_similarity: float | None  # character mode only
    perceptual_quality: float          # pyiqa TOPIQ-NR
    aesthetic_score: float             # Aesthetic V2.5
    sharpness: float                   # whole-image Laplacian
    is_occluded: bool                  # CLIP zero-shot
    is_duplicate: bool                 # pHash
    composite_score: float             # weighted sum (mode-dependent)
    pose_vector: list[float] | None    # MediaPipe (~20-D)

class CurationConfig(BaseModel):
    mode: CurationMode = CurationMode.CHARACTER
    target_count: int = 40
    quality_floor_pct: float = 0.30
    min_face_confidence: float = 0.5
    min_face_area_ratio: float = 0.05
    max_pose_angle: float = 75.0
    identity_threshold: float = 0.45
    reference_image_id: str | None = None
    diversity_weights: DiversityWeights = DiversityWeights()

class DiversityWeights(BaseModel):
    clip_visual: float = 0.4
    pose: float = 0.3
    face: float = 0.3

class CurationResult(BaseModel):
    selected_ids: list[str]
    scores: dict[str, ImageScore]
    survivors_count: int
    total_count: int
    mode: CurationMode
    config: CurationConfig
```

### Pipeline Entry Point

```python
async def run_curation(
    project_dir: Path,
    config: CurationConfig,
    progress_callback: Callable | None = None,
) -> CurationResult:
    """
    1. Load images from manifest
    2. Score all images (parallel GPU inference)
    3. Filter by quality floor
    4. Build concatenated feature embeddings
    5. Run apricot FacilityLocation selection
    6. Return ranked selection with scores
    """
```

### Scorer (GPU model singleton)

```python
class CurationScorer:
    def __init__(self, device: str = "cuda"):
        self.face_app = ...        # InsightFace (existing singleton)
        self.pyiqa_model = ...     # pyiqa TOPIQ-NR
        self.aesthetic_model = ... # Aesthetic V2.5 SigLIP
        self.clip_model = ...      # existing CLIP ViT-B/32
        self.pose_model = ...      # MediaPipe (existing from autocrop)

    async def score_batch(self, images: list[Path]) -> list[ImageScore]:
        """Score all images. GPU-batched where possible."""
```

### API Endpoints

```
POST /api/v1/curation/start          → operation_id (HTTP 202)
GET  /api/v1/curation/progress/{id}  → SSE stream
GET  /api/v1/curation/result/{id}    → CurationResult JSON
POST /api/v1/curation/rerun          → re-diversify with pins/exclusions
POST /api/v1/curation/apply          → apply selection to gallery
```

---

## Frontend — Review UI

### New Page: `/curate`

**Config Panel:** Mode selector, target count, profile dropdown, reference face picker, start button.

**Progress:** SSE-driven progress bar showing phase and image count.

**Results Summary:** Pipeline funnel (scanned → passed → selected) with diversity metrics.

**Selected Grid:** Masonry grid of selected images with score badges. Each image clickable for score breakdown popover (bar chart of all dimensions).

**Actions per image:**
- **Pin** — lock into selection, re-run won't remove
- **Exclude** — remove from selection AND candidate pool
- **Swap** — replace with an image from the rejected pool

**Rejected Pool:** Collapsed section showing non-selected images, expandable for browsing and swapping.

**Global Actions:**
- **Re-run** — re-run Phase 2 diversity selection respecting pins/exclusions
- **Apply** — set gallery selection to curated set, return to gallery

### State (Zustand)

```typescript
curationConfig: CurationConfig | null
curationResult: CurationResult | null
pinnedIds: Set<string>
excludedIds: Set<string>
```

### Navigation

Gallery toolbar → [Curate] button → `/curate` → configure → run → review → apply → back to Gallery with selection active → proceed to Crop/Process/Caption.

---

## Dependencies

| Package | Size | Purpose | Group |
|---------|------|---------|-------|
| `pyiqa` | ~50MB | TOPIQ-NR perceptual quality | `[curation]` |
| `apricot-select` | ~2MB | Facility Location subset selection | `[curation]` |
| `aesthetic-predictor-v2-5` | ~20MB (+~400MB model) | Aesthetic scoring | `[curation]` |

```toml
[project.optional-dependencies]
curation = [
    "pyiqa>=0.1.12",
    "apricot-select>=0.6.1",
    "aesthetic-predictor-v2-5>=0.1.0",
]
```

### Performance Budget (400 images, RTX 5080)

| Step | Time | Device |
|------|------|--------|
| InsightFace | ~5s | GPU |
| pyiqa TOPIQ-NR | ~8s | GPU |
| Aesthetic V2.5 | ~3s | GPU |
| OpenCV Laplacian | ~1s | CPU |
| MediaPipe Pose | ~8s | CPU |
| CLIP embeddings | ~4s | GPU |
| CLIP zero-shot occlusion | ~1s | GPU |
| pHash dedup | <1s | CPU |
| apricot selection | <1s | CPU |
| **Total** | **~33s** | |

VRAM: ~1.25GB total (InsightFace 300MB + pyiqa 200MB + SigLIP 400MB + CLIP 350MB). Well within RTX 5080's 16GB.

---

## Approach C — Future Upgrade Path

### Upgrade 1: Background Diversity (RMBG-2.0)

- Add `klippbok/curation/background.py`
- RMBG-2.0 via HuggingFace transformers: alpha matte → invert → CLIP embedding of background-only
- Add `background_embedding` (~512-D) to Phase 2 feature vector
- ~350ms/image, adds ~2.5 min for 400 images
- **Trigger:** Same-background images appearing in curated sets despite varied poses

### Upgrade 2: Expression Classification (DeepFace)

- `pip install deepface`
- 7-category emotion classification → 7-D vector in Phase 2
- ~50ms/face, minimal pipeline impact
- **Trigger:** Generated LoRAs defaulting to one expression

### Upgrade 3: Per-Image Radar Chart

- SVG radar chart in score detail popover (no new dependency)
- Axes: Face Quality, Technical, Aesthetic, Sharpness, Identity, Diversity Contribution
- **Trigger:** UI polish pass after core feature validated

### Upgrade 4: Iterative Re-diversification with Constraints

- Pass pinned embeddings as fixed points to apricot `initial_subset`
- Algorithm selects remaining items maximizing diversity relative to pins
- **Trigger:** Verify apricot API supports this natively

### Upgrade Priority

| # | Upgrade | Value | Effort | When |
|---|---------|-------|--------|------|
| 1 | Iterative re-diversification | High | Low | If apricot supports initial_subset |
| 2 | Per-image radar chart | Medium | Low | UI polish pass |
| 3 | Expression classification | Medium | Medium | Same-expression outputs observed |
| 4 | Background segmentation | Medium | Medium | Same-background outputs observed |

---

## Research Sources

### ML Tools (Already Available)
- InsightFace buffalo_l: face detection, 512-D embeddings, pose, confidence (GPU, ctx_id=0)
- CLIP ViT-B/32: 512-D image embeddings, zero-shot classification
- OpenCV: Laplacian variance sharpness
- MediaPipe Pose: 33 3D landmarks (already used for autocrop)
- pHash (imagehash): perceptual deduplication

### ML Tools (New)
- [pyiqa (IQA-PyTorch)](https://github.com/chaofengc/IQA-PyTorch): 40+ IQA metrics, GPU-accelerated
- [apricot](https://github.com/jmschrei/apricot): Submodular optimization, Facility Location
- [Aesthetic Predictor V2.5](https://github.com/discus0434/aesthetic-predictor-v2-5): SigLIP-based aesthetic scoring

### LoRA Dataset Best Practices
- SD1.5 sweet spot: 15-50 images (quality > quantity)
- SDXL/Flux: 40-80 images
- Critical signals: face clarity, pose variety, single subject, varied backgrounds
- Avoid: duplicates, blur, heavy occlusion, extreme angles, mixed identities

### Alternative Tools Evaluated (not selected)
- DensePose: Rich UV mapping but hard Windows install (detectron2), overkill
- OpenPose: C++ build complexity, no advantage over MediaPipe
- DeepFace: Expression classification, deferred to Approach C
- RMBG-2.0: Background segmentation, deferred to Approach C
- FiftyOne: Heavy framework (MongoDB), ideas borrowed not dependency added
- LoRA-Dataset-Automaker: Notebook, not reusable; klippbok already covers its pipeline
