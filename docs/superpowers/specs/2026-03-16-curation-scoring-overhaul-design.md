# Curation Scoring Overhaul — Design Spec

**Date:** 2026-03-16
**Status:** Draft
**Scope:** `klippbok/curation/` module — scorer, pipeline, models, presets

## Problem Statement

The curation pipeline produces unstable composite scores and false exclusions in character mode:

1. **Unstable scores (D):** Nearly identical images get wildly different composite scores because raw signal values are scale-sensitive. InsightFace returning 0.0 vs 0.95 for similar images causes ~0.13 composite swing (40% face weight * 0.33 average contribution).
2. **False exclusions (C):** Good images are incorrectly discarded by two mechanisms:
   - Percentile-based quality floor (`quality_floor_pct=0.3`) always discards the bottom 30% regardless of actual quality.
   - pHash dedup (`PHASH_THRESHOLD=10`) is loose enough to flag similar-but-different images, then auto-discards the lower-scored one — which may be the wrong choice given noisy composites.

## Solution Overview

Three changes that work together:

1. **Rank-based composite scoring** — convert raw signals to percentile ranks before weighting, eliminating scale sensitivity.
2. **Two-tier quality floor** — hard floor (absolute minimum, auto-exclude) + soft floor (advisory, diversity selector may still pick).
3. **Dedup groups with representative selection** — tighter pHash threshold, group duplicates instead of auto-discarding, let the highest-scored representative enter the diversity pool.

## Detailed Design

### 1. Rank-Based Composite Scoring

**Location:** `curation/scorer.py` (new function), `curation/models.py` (new field)

After `score_images()` produces raw `SignalScores` for all images, a new `rank_normalize()` function converts each signal dimension to its percentile rank (0.0–1.0) across the dataset.

**Signals ranked:**
- `face_confidence`
- `identity_similarity`
- `quality_score`
- `aesthetic_score`
- `sharpness_whole`
- `sharpness_face`
- `occlusion_score`

**Not ranked:** `face_area_ratio` (already normalized to a meaningful 0–1 range), `pose_vector` (multi-dimensional, used only by diversity selector).

**Algorithm:**
```python
def rank_normalize(scores: list[ImageScore]) -> None:
    """Convert raw signal values to percentile ranks in-place.

    For each signal dimension, sort all values, assign percentile
    rank (0.0 = worst, 1.0 = best), store in ranked_signals.
    Ties get averaged rank.
    """
    from scipy.stats import rankdata

    n = len(scores)
    if n < 2:
        # Single image gets rank 1.0 on all dimensions
        for s in scores:
            s.ranked_signals = s.signals.model_copy()
        return

    signal_names = [
        "face_confidence", "identity_similarity", "quality_score",
        "aesthetic_score", "sharpness_whole", "sharpness_face",
        "occlusion_score",
    ]

    # Extract raw values per signal
    for name in signal_names:
        raw_values = [getattr(s.signals, name) for s in scores]
        ranks = rankdata(raw_values, method="average")
        # Normalize to [0, 1]: (rank - 1) / (n - 1)
        for i, s in enumerate(scores):
            normalized_rank = (ranks[i] - 1) / (n - 1)
            setattr(s.ranked_signals, name, normalized_rank)

    # face_area_ratio: copy as-is (already meaningful scale)
    for s in scores:
        s.ranked_signals.face_area_ratio = s.signals.face_area_ratio
```

**Composite computation** now uses `ranked_signals` instead of raw `signals`. The existing `_compute_composite()` function is called with ranked values. Weight presets (`CHARACTER_WEIGHTS`, `STYLE_WEIGHTS`) remain unchanged.

**Model changes (`ImageScore`):**
```python
ranked_signals: SignalScores = Field(default_factory=SignalScores)
"""Percentile-ranked signal scores (0.0 = worst in dataset, 1.0 = best)."""
```

**Signal fallback for missing detections:**
- Raw signal stays at 0.0 when InsightFace finds no face
- Rank naturally places it at the bottom without catastrophic cliff — if 5 out of 100 images have no face, they cluster at rank ~0.02 instead of all being exactly 0.0
- CLIP occlusion failures: raw defaults to 0.5, rank places it at median naturally

### 2. Two-Tier Quality Floor

**Location:** `curation/pipeline.py` (floor logic), `curation/models.py` (new fields), `curation/presets.py` (constant)

**Hard floor:**
- Absolute composite threshold: `HARD_FLOOR_DEFAULT = 0.15`
- Images below this are always excluded from the diversity pool
- Catches genuinely bad images: corrupt, completely blurry, wrong subject entirely
- Stored in `CurationConfig.hard_floor` (default 0.15)

**Soft floor:**
- The existing `quality_floor_pct` parameter (default 0.3)
- Images below the soft cutoff are **flagged** but remain in the diversity pool
- The diversity selector can still pick them if they provide unique coverage

**Floor status field (`ImageScore`):**
```python
floor_status: Literal["passed", "soft_floor", "hard_floor"] = "passed"
```

**Pipeline logic:**
```python
# Hard floor: absolute exclusion
for s in all_scores:
    if s.composite_score < config.hard_floor:
        s.floor_status = "hard_floor"

# Soft floor: advisory flag
remaining = [s for s in all_scores if s.floor_status != "hard_floor"]
if remaining and config.quality_floor_pct > 0:
    composites = [s.composite_score for s in remaining]
    soft_cutoff = np.percentile(composites, config.quality_floor_pct * 100)
    for s in remaining:
        if s.composite_score < soft_cutoff:
            s.floor_status = "soft_floor"

# Pool for diversity selection: everything except hard_floor and dedup non-reps
pool = [s for s in all_scores if s.floor_status != "hard_floor" and s.dedup_kept]
```

**Summary additions (`PipelineSummary`):**
```python
hard_excluded: int = 0
"""Images below hard quality floor."""

soft_flagged: int = 0
"""Images below soft quality floor (still eligible for selection)."""
```

### 3. Dedup Groups with Representative Selection

**Location:** `curation/scorer.py` (mark_duplicates), `curation/models.py` (new fields)

**3a. Tighten pHash threshold:**

Change `PHASH_THRESHOLD` from 10 to 6 in `image/dedup.py`. This matches the dHash threshold in `dataset/quality.py` and limits dedup to true near-duplicates (re-encoded, resized, minor crop) rather than "similar angle, same person."

Note: `mark_duplicates()` in `scorer.py` imports `are_near_duplicates` from `image_service.py` which delegates to `image/dedup.py`. The threshold change propagates automatically.

**3b. Group instead of auto-discard:**

Current `mark_duplicates()` sets `is_duplicate = True` on the lower-scored image. New behavior: assign both images to a `dedup_group_id` and mark the higher-scored one as `dedup_kept = True`.

**Model changes (`ImageScore`):**
```python
dedup_group_id: str | None = None
"""Duplicate group key (None = unique image, string = group ID)."""

dedup_kept: bool = True
"""Whether this image is the representative of its dedup group."""
```

**Backwards compatibility for `is_duplicate`:**

Add a computed property on `SignalScores` (or move to `ImageScore`):
```python
@property
def is_duplicate(self) -> bool:
    """Backwards-compatible: True if in a dedup group and not kept."""
    return self.dedup_group_id is not None and not self.dedup_kept
```

Wait — `is_duplicate` currently lives on `SignalScores` as a plain `bool` field. We need to:
1. Keep `is_duplicate` on `SignalScores` for serialization compatibility
2. Add `dedup_group_id` and `dedup_kept` to `ImageScore`
3. In `mark_duplicates()`, set all three: `dedup_group_id`, `dedup_kept`, and `signals.is_duplicate` (for backwards compat)

**New `mark_duplicates()` logic:**
```python
def mark_duplicates(scores, image_paths):
    # Compute pHashes (unchanged)
    # Union-find grouping (unchanged, uses tightened threshold)

    # For each group:
    #   - Assign dedup_group_id = image_id of first member
    #   - Find member with highest composite_score → dedup_kept = True
    #   - All others: dedup_kept = False, signals.is_duplicate = True
```

**3c. Pipeline integration:**

In `pipeline.py`, after `mark_duplicates()`:
```python
# Only group representatives enter the diversity pool
pool = [s for s in all_scores if s.floor_status != "hard_floor" and s.dedup_kept]
```

Non-representatives are tracked in the result for UI display but excluded from diversity selection.

## Files Modified

| File | Changes |
|------|---------|
| `curation/models.py` | Add `ranked_signals` field to `ImageScore`. Add `floor_status`, `dedup_group_id`, `dedup_kept` to `ImageScore`. Add `hard_floor` to `CurationConfig`. Add `hard_excluded`, `soft_flagged` to `PipelineSummary`. |
| `curation/scorer.py` | Add `rank_normalize()` function. Change `mark_duplicates()` to build groups with representative selection. |
| `curation/presets.py` | Add `HARD_FLOOR_DEFAULT = 0.15`. |
| `curation/pipeline.py` | Call `rank_normalize()` after `score_images()`. Replace single-cutoff floor with two-tier logic. Filter dedup non-representatives from diversity pool. Update `PipelineSummary` counts. |
| `image/dedup.py` | Change `PHASH_THRESHOLD` from 10 to 6. |
| `api/routers/curation.py` | Pass `hard_floor` from config to pipeline (minor wiring). |

## Files NOT Modified

| File | Reason |
|------|--------|
| `curation/diversity.py` | Receives a pre-filtered pool — no changes needed. |
| `curation/presets.py` weights | Weight presets stay the same — rank normalization makes them stable. |
| `api/routers/curation.py` endpoints | No new endpoints, no changed signatures. |
| `triage/` module | Not part of the curation pipeline flow. |

## Backwards Compatibility

- New fields on `ImageScore` all have defaults — loading old `curation_results.json` works.
- `quality_floor_pct` still exists and functions as the soft floor.
- `signals.is_duplicate` still set for any code reading it.
- API response shape gains new fields but no fields removed.

## Testing Strategy

1. **Unit: `rank_normalize()`** — verify percentile ranks with known inputs, ties, single-image edge case.
2. **Unit: `mark_duplicates()`** — verify group assignment, representative selection, backwards-compat `is_duplicate`.
3. **Unit: two-tier floor** — verify hard floor excludes, soft floor flags but doesn't exclude, empty dataset edge case.
4. **Integration: full pipeline** — run `run_curation()` on a small test dataset, verify scores are stable across re-runs, verify no false exclusions of high-quality images.
5. **Regression: existing tests** — `tests/test_curation*.py` must pass with new behavior.

## Success Criteria

1. **Scoring stability:** Two images that a human would rate similarly should have composite scores within 0.05 of each other.
2. **No false exclusions:** In a dataset of all-good images, zero images should be hard-floor excluded.
3. **Dedup accuracy:** Only true near-duplicates (re-encoded, resized) are grouped — different poses/angles of the same person are NOT grouped.
4. **Existing tests pass** with updated assertions where needed.
