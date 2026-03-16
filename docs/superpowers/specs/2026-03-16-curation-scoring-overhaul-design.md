# Curation Scoring Overhaul — Design Spec

**Date:** 2026-03-16
**Status:** Reviewed (v2 — fixes from spec review)
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

**Two composites — raw and ranked:**

The existing per-image `_compute_composite()` call in `score_images()` stays and produces a **raw composite** (`raw_composite_score`). After `rank_normalize()`, a second composite is computed from ranked signals and stored as `composite_score`. This separation is critical because:
- `raw_composite_score` preserves absolute quality information → used by the **hard floor** (Section 2)
- `composite_score` (rank-based) is stable and relative → used for **soft floor**, **diversity selection**, **dedup representative choice**, and **UI display**

Weight presets (`CHARACTER_WEIGHTS`, `STYLE_WEIGHTS`) remain unchanged — applied to both raw and ranked composites.

**Model changes (`ImageScore`):**
```python
ranked_signals: SignalScores = Field(default_factory=SignalScores)
"""Percentile-ranked signal scores (0.0 = worst in dataset, 1.0 = best)."""

raw_composite_score: float = 0.0
"""Composite from raw signals — preserves absolute quality for hard floor."""
```

The existing `composite_score` field is repurposed to hold the rank-based composite. Old serialized results that lack `raw_composite_score` default to 0.0 (backwards-compatible; hard floor won't retroactively exclude them since they were already processed).

**Signal fallback for missing detections:**
- Raw signal stays at 0.0 when InsightFace finds no face
- Rank naturally places it at the bottom without catastrophic cliff — if 5 out of 100 images have no face, they cluster at rank ~0.02 instead of all being exactly 0.0
- CLIP occlusion failures: raw defaults to 0.5, rank places it at median naturally

**Small dataset behavior (n < 5):**
- n=1: all ranks set to 1.0 (single image is trivially best)
- n=2-4: ranks produce coarse quantization (e.g., {0.0, 1.0} for n=2), but the raw composite is still available for absolute quality assessment via the hard floor. The ranked composite is used for relative ordering and diversity, which is less sensitive to quantization at small scales.

### 2. Two-Tier Quality Floor

**Location:** `curation/pipeline.py` (floor logic), `curation/models.py` (new fields), `curation/presets.py` (constant)

**Hard floor — operates on raw composite (absolute quality):**
- Absolute threshold against `raw_composite_score`: `HARD_FLOOR_DEFAULT = 0.15`
- Images below this are always excluded from the diversity pool
- Catches genuinely bad images: corrupt, completely blurry, wrong subject entirely
- Because it uses `raw_composite_score` (not rank-based), it reflects absolute quality — a dataset of 100 excellent images will have zero hard-floor exclusions
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
# Hard floor: absolute exclusion (uses RAW composite, not ranked)
for s in all_scores:
    if s.raw_composite_score < config.hard_floor:
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

**3a. Tighten pHash threshold (curation-scoped):**

Add a `threshold` parameter to `are_near_duplicates()` in `image/dedup.py` (default stays at `PHASH_THRESHOLD = 10` for import validation backwards compat). The curation `mark_duplicates()` passes `threshold=6` explicitly. This limits curation dedup to true near-duplicates (re-encoded, resized, minor crop) without affecting import validation behavior.

```python
# image/dedup.py — add threshold parameter
def are_near_duplicates(hash_hex_a: str, hash_hex_b: str, threshold: int = PHASH_THRESHOLD) -> bool:
```

`mark_duplicates()` in `scorer.py` calls `are_near_duplicates(h_a, h_b, threshold=6)`.

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

**New `mark_duplicates()` logic — union-find rewrite:**

The current `mark_duplicates()` in `scorer.py` has no transitive grouping — it's a simple pairwise comparison with early break. This must be replaced with a proper union-find to ensure transitive closure (if A matches B and B matches C, all three are in one group).

```python
CURATION_PHASH_THRESHOLD: int = 6

def mark_duplicates(scores, image_paths):
    # 1. Compute pHashes for all images (unchanged)

    # 2. Union-find with path compression (NEW — replaces pairwise logic)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]  # path compression
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(n):
        if hashes[i] is None:
            continue
        for j in range(i + 1, n):
            if hashes[j] is None:
                continue
            if are_near_duplicates(hashes[i], hashes[j], threshold=CURATION_PHASH_THRESHOLD):
                union(i, j)

    # 3. Build groups from union-find roots
    groups: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        groups.setdefault(root, []).append(i)

    # 4. For each group with 2+ members:
    #   - Assign dedup_group_id = image_id of root member
    #   - Find member with highest composite_score → dedup_kept = True
    #   - All others: dedup_kept = False, signals.is_duplicate = True
    for root, members in groups.items():
        if len(members) < 2:
            continue
        group_id = scores[root].image_id
        best_idx = max(members, key=lambda i: scores[i].composite_score)
        for i in members:
            scores[i].dedup_group_id = group_id
            if i == best_idx:
                scores[i].dedup_kept = True
            else:
                scores[i].dedup_kept = False
                scores[i].signals.is_duplicate = True  # backwards compat
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
| `curation/models.py` | Add `ranked_signals`, `raw_composite_score`, `floor_status`, `dedup_group_id`, `dedup_kept` to `ImageScore`. Add `hard_floor` to `CurationConfig`. Add `hard_excluded`, `soft_flagged` to `PipelineSummary`. |
| `curation/scorer.py` | Add `rank_normalize()` function. Rewrite `mark_duplicates()` with union-find grouping and representative selection. Existing per-image composite becomes `raw_composite_score`; ranked composite computed after `rank_normalize()`. |
| `curation/presets.py` | Add `HARD_FLOOR_DEFAULT = 0.15`. |
| `curation/pipeline.py` | Call `rank_normalize()` after `score_images()`, recompute `composite_score` from ranked signals. Hard floor checks `raw_composite_score`. Replace single-cutoff floor with two-tier logic. Filter dedup non-representatives from diversity pool. Update `PipelineSummary` counts. |
| `image/dedup.py` | Add `threshold` parameter to `are_near_duplicates()` (default unchanged at 10). |
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
- `are_near_duplicates()` gains an optional `threshold` parameter — existing callers (import validation) are unaffected.
- `raw_composite_score` defaults to 0.0 in old results — hard floor won't retroactively exclude them.
- **Composite scores are not comparable across old/new runs** — old composites were raw-signal-based, new composites are rank-based. This is acceptable because curation results are ephemeral (re-run per session), not cross-session comparable.

## Rediversify Compatibility

`rediversify()` loads cached `ImageScore` objects and re-runs diversity selection. Since `floor_status` and `dedup_kept` are persisted in the JSON, rediversify does NOT need to re-evaluate floor or dedup — it uses the cached values. Only the diversity selection (pin/exclude) is re-run.

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
