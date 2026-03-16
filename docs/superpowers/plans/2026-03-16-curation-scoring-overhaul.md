# Curation Scoring Overhaul Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix unstable composite scores and false exclusions in character-mode curation by adding rank-based scoring, two-tier quality floor, and dedup group representative selection.

**Architecture:** Raw ML signals are scored per-image (unchanged), then rank-normalized across the dataset to produce stable percentile-based composites. A raw composite is preserved for the absolute hard floor. Dedup uses union-find grouping with a tighter threshold, selecting the best representative per group instead of auto-discarding.

**Tech Stack:** Python 3.11, Pydantic v2, scipy.stats.rankdata, numpy, pytest

**Spec:** `docs/superpowers/specs/2026-03-16-curation-scoring-overhaul-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `klippbok/curation/models.py` | Modify | Add `ranked_signals`, `raw_composite_score`, `floor_status`, `dedup_group_id`, `dedup_kept` to `ImageScore`. Add `hard_floor` to `CurationConfig`. Add `hard_excluded`, `soft_flagged` to `PipelineSummary`. |
| `klippbok/curation/presets.py` | Modify | Add `HARD_FLOOR_DEFAULT` and `CURATION_PHASH_THRESHOLD` constants. |
| `klippbok/curation/scorer.py` | Modify | Add `rank_normalize()`. Rewrite `mark_duplicates()` with union-find. |
| `klippbok/curation/pipeline.py` | Modify | Wire rank normalization, two-tier floor, dedup pool filtering. |
| `klippbok/image/dedup.py` | Modify | Add `threshold` parameter to `are_near_duplicates()`. |
| `tests/test_curation_scorer.py` | Modify | Add tests for `rank_normalize()` and new `mark_duplicates()`. |
| `tests/test_curation_pipeline.py` | Modify | Add tests for two-tier floor and dedup pool filtering. |
| `tests/test_dedup.py` | Modify | Add test for `threshold` parameter on `are_near_duplicates()`. |

---

## Chunk 1: Model Changes + Constants

### Task 1: Add new fields to `ImageScore`

**Files:**
- Modify: `klippbok/curation/models.py`
- Test: `tests/test_curation_scorer.py`

- [ ] **Step 1: Add fields to `ImageScore` in `models.py`**

Add these fields after the existing `mode` field:

```python
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
```

Update the `Literal` import at the top of `models.py` — it already imports `Literal` for `CurationMode`.

- [ ] **Step 2: Add `hard_floor` to `CurationConfig`**

Add after `identity_threshold`:

```python
hard_floor: float = Field(default=0.15, ge=0.0, le=1.0)
"""Absolute raw composite threshold — images below are always excluded."""
```

- [ ] **Step 3: Add summary fields to `PipelineSummary`**

Add after `selected`:

```python
hard_excluded: int = 0
"""Images below hard quality floor."""

soft_flagged: int = 0
"""Images below soft quality floor (still eligible for selection)."""
```

- [ ] **Step 4: Verify imports and run existing tests**

Run: `pytest tests/test_curation_scorer.py tests/test_curation_pipeline.py tests/test_curation_api.py -x -q`
Expected: All existing tests PASS (new fields have defaults, so backwards-compatible).

- [ ] **Step 5: Commit**

```bash
git add klippbok/curation/models.py
git commit -m "feat(curation): add ranked_signals, floor_status, dedup fields to ImageScore"
```

### Task 2: Add constants to presets

**Files:**
- Modify: `klippbok/curation/presets.py`

- [ ] **Step 1: Add constants**

Add at module level:

```python
HARD_FLOOR_DEFAULT: float = 0.15
"""Absolute raw composite threshold for hard quality floor.
Images below this are always excluded regardless of dataset quality."""

CURATION_PHASH_THRESHOLD: int = 6
"""pHash Hamming distance threshold for curation dedup.
Tighter than import validation (10) to catch only true near-duplicates."""
```

- [ ] **Step 2: Commit**

```bash
git add klippbok/curation/presets.py
git commit -m "feat(curation): add HARD_FLOOR_DEFAULT and CURATION_PHASH_THRESHOLD constants"
```

### Task 3: Add `threshold` parameter to `are_near_duplicates()`

**Files:**
- Modify: `klippbok/image/dedup.py`
- Test: `tests/test_dedup.py` (if exists, else `tests/test_curation_scorer.py`)

- [ ] **Step 1: Write failing test**

Find or create the dedup test file. Add:

```python
def test_are_near_duplicates_custom_threshold():
    """Custom threshold parameter narrows match window."""
    from klippbok.image.dedup import are_near_duplicates
    import imagehash
    # Two hashes with Hamming distance 8
    h1 = "0" * 16  # 64-bit hash as hex
    h2 = "ff00000000000000"  # differs in 8 bits
    # Default threshold (10) should match
    assert are_near_duplicates(h1, h2) is True
    # Tight threshold (6) should NOT match
    assert are_near_duplicates(h1, h2, threshold=6) is False
    # Exact match always works
    assert are_near_duplicates(h1, h1, threshold=1) is True
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/test_dedup.py::test_are_near_duplicates_custom_threshold -v` (or equivalent path)
Expected: FAIL — `threshold` parameter not accepted.

- [ ] **Step 3: Add `threshold` parameter**

In `klippbok/image/dedup.py`, change `are_near_duplicates()`:

```python
def are_near_duplicates(hash_hex_a: str, hash_hex_b: str, threshold: int = PHASH_THRESHOLD) -> bool:
```

Body unchanged — it already uses a comparison. Just replace the hardcoded `PHASH_THRESHOLD` reference (already used via `<=`) with the parameter. Actually, checking the current code at line 56: `return bool((ha - hb) <= PHASH_THRESHOLD)` — change to `return bool((ha - hb) <= threshold)`.

- [ ] **Step 4: Run test, verify it passes**

Run: `pytest tests/test_dedup.py::test_are_near_duplicates_custom_threshold -v`
Expected: PASS

- [ ] **Step 5: Run all dedup tests to check no regression**

Run: `pytest tests/ -k "dedup" -x -q`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add klippbok/image/dedup.py tests/test_dedup.py
git commit -m "feat(dedup): add threshold parameter to are_near_duplicates()"
```

---

## Chunk 2: Rank Normalization

### Task 4: Implement `rank_normalize()`

**Files:**
- Modify: `klippbok/curation/scorer.py`
- Test: `tests/test_curation_scorer.py`

- [ ] **Step 1: Write failing tests for `rank_normalize()`**

Add to `tests/test_curation_scorer.py`:

```python
from klippbok.curation.scorer import rank_normalize


class TestRankNormalize:
    """Tests for percentile rank normalization."""

    def _make_score(self, **signal_kwargs) -> ImageScore:
        """Helper: create ImageScore with specific signal values."""
        signals = SignalScores(**signal_kwargs)
        return ImageScore(
            image_id="test",
            relative_path="test.jpg",
            signals=signals,
            composite_score=0.5,
            mode="character",
        )

    def test_single_image_gets_max_rank(self) -> None:
        """Single image should get rank 1.0 on all dimensions."""
        scores = [self._make_score(face_confidence=0.3, quality_score=0.7)]
        rank_normalize(scores)
        assert scores[0].ranked_signals.face_confidence == pytest.approx(1.0)
        assert scores[0].ranked_signals.quality_score == pytest.approx(1.0)

    def test_two_images_rank_ordering(self) -> None:
        """Higher raw value should get higher rank."""
        scores = [
            self._make_score(quality_score=0.2),
            self._make_score(quality_score=0.8),
        ]
        # Give unique image_ids
        scores[0].image_id = "a"
        scores[1].image_id = "b"
        rank_normalize(scores)
        assert scores[0].ranked_signals.quality_score == pytest.approx(0.0)
        assert scores[1].ranked_signals.quality_score == pytest.approx(1.0)

    def test_ties_get_averaged_rank(self) -> None:
        """Tied values should get the same (averaged) rank."""
        scores = [
            self._make_score(aesthetic_score=0.5),
            self._make_score(aesthetic_score=0.5),
            self._make_score(aesthetic_score=0.9),
        ]
        for i, s in enumerate(scores):
            s.image_id = str(i)
        rank_normalize(scores)
        # Two tied at 0.5 share rank positions 1 and 2 → avg rank 1.5
        # Normalized: (1.5 - 1) / (3 - 1) = 0.25
        assert scores[0].ranked_signals.aesthetic_score == pytest.approx(0.25)
        assert scores[1].ranked_signals.aesthetic_score == pytest.approx(0.25)
        assert scores[2].ranked_signals.aesthetic_score == pytest.approx(1.0)

    def test_face_area_ratio_copied_not_ranked(self) -> None:
        """face_area_ratio should be copied as-is, not rank-normalized."""
        scores = [
            self._make_score(face_area_ratio=0.1),
            self._make_score(face_area_ratio=0.4),
        ]
        scores[0].image_id = "a"
        scores[1].image_id = "b"
        rank_normalize(scores)
        assert scores[0].ranked_signals.face_area_ratio == pytest.approx(0.1)
        assert scores[1].ranked_signals.face_area_ratio == pytest.approx(0.4)

    def test_five_images_uniform_distribution(self) -> None:
        """Five distinct values should produce evenly spaced ranks."""
        scores = [self._make_score(sharpness_whole=v) for v in [0.1, 0.3, 0.5, 0.7, 0.9]]
        for i, s in enumerate(scores):
            s.image_id = str(i)
        rank_normalize(scores)
        expected = [0.0, 0.25, 0.5, 0.75, 1.0]
        for s, exp in zip(scores, expected):
            assert s.ranked_signals.sharpness_whole == pytest.approx(exp)
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/test_curation_scorer.py::TestRankNormalize -v`
Expected: FAIL — `rank_normalize` not importable.

- [ ] **Step 3: Implement `rank_normalize()` in `scorer.py`**

Add after the existing `normalize_score()` function:

```python
def rank_normalize(scores: list[ImageScore]) -> None:
    """Convert raw signal values to percentile ranks in-place.

    For each signal dimension, compute the percentile rank across all
    images. Ties get averaged rank. Results stored in ranked_signals.

    Args:
        scores: List of ImageScore objects. Modified in-place.
    """
    from scipy.stats import rankdata

    n = len(scores)
    if n == 0:
        return

    if n == 1:
        scores[0].ranked_signals = scores[0].signals.model_copy()
        # Single image is trivially best on all dimensions
        for name in _RANKED_SIGNAL_NAMES:
            setattr(scores[0].ranked_signals, name, 1.0)
        scores[0].ranked_signals.face_area_ratio = scores[0].signals.face_area_ratio
        return

    for name in _RANKED_SIGNAL_NAMES:
        raw_values = [getattr(s.signals, name) for s in scores]
        ranks = rankdata(raw_values, method="average")
        for i, s in enumerate(scores):
            if not hasattr(s, '_ranked_initialized') or not s._ranked_initialized:
                s.ranked_signals = s.signals.model_copy()
            normalized_rank = (ranks[i] - 1) / (n - 1)
            setattr(s.ranked_signals, name, normalized_rank)

    # face_area_ratio: copy as-is (meaningful physical ratio)
    for s in scores:
        s.ranked_signals.face_area_ratio = s.signals.face_area_ratio


_RANKED_SIGNAL_NAMES: list[str] = [
    "face_confidence",
    "identity_similarity",
    "quality_score",
    "aesthetic_score",
    "sharpness_whole",
    "sharpness_face",
    "occlusion_score",
]
"""Signal dimensions that get percentile rank normalization."""
```

Note: The `_ranked_initialized` check is clunky. Simpler approach: initialize `ranked_signals` via `model_copy()` once before the signal loop:

```python
    # Initialize ranked_signals from raw signals
    for s in scores:
        s.ranked_signals = s.signals.model_copy()

    for name in _RANKED_SIGNAL_NAMES:
        raw_values = [getattr(s.signals, name) for s in scores]
        ranks = rankdata(raw_values, method="average")
        for i, s in enumerate(scores):
            normalized_rank = (ranks[i] - 1) / (n - 1)
            setattr(s.ranked_signals, name, normalized_rank)

    # face_area_ratio: copy as-is (already set by model_copy, but explicit)
    for s in scores:
        s.ranked_signals.face_area_ratio = s.signals.face_area_ratio
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/test_curation_scorer.py::TestRankNormalize -v`
Expected: All PASS

- [ ] **Step 5: Run full scorer test suite for regression**

Run: `pytest tests/test_curation_scorer.py -x -q`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add klippbok/curation/scorer.py tests/test_curation_scorer.py
git commit -m "feat(curation): add rank_normalize() for percentile-based scoring"
```

---

## Chunk 3: Union-Find Dedup Groups

### Task 5: Rewrite `mark_duplicates()` with union-find

**Files:**
- Modify: `klippbok/curation/scorer.py`
- Test: `tests/test_curation_scorer.py`

- [ ] **Step 1: Write failing tests for new `mark_duplicates()` behavior**

Add to `tests/test_curation_scorer.py`:

```python
from klippbok.curation.scorer import mark_duplicates


class TestMarkDuplicatesGroups:
    """Tests for union-find dedup grouping."""

    def _make_score(self, image_id: str, composite: float) -> ImageScore:
        return ImageScore(
            image_id=image_id,
            relative_path=f"{image_id}.jpg",
            composite_score=composite,
            mode="character",
        )

    @patch("klippbok.curation.scorer.compute_phash")
    @patch("klippbok.curation.scorer.are_near_duplicates")
    def test_group_assignment(self, mock_dup, mock_hash, tmp_path):
        """Matching images should share a dedup_group_id."""
        scores = [self._make_score("a", 0.8), self._make_score("b", 0.6)]
        paths = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
        for p in paths:
            p.touch()
        mock_hash.side_effect = ["hash_a", "hash_b"]
        mock_dup.return_value = True  # a and b are duplicates

        mark_duplicates(scores, paths)

        assert scores[0].dedup_group_id is not None
        assert scores[0].dedup_group_id == scores[1].dedup_group_id

    @patch("klippbok.curation.scorer.compute_phash")
    @patch("klippbok.curation.scorer.are_near_duplicates")
    def test_highest_composite_kept(self, mock_dup, mock_hash, tmp_path):
        """Highest composite in group should be dedup_kept=True."""
        scores = [self._make_score("a", 0.8), self._make_score("b", 0.6)]
        paths = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
        for p in paths:
            p.touch()
        mock_hash.side_effect = ["hash_a", "hash_b"]
        mock_dup.return_value = True

        mark_duplicates(scores, paths)

        assert scores[0].dedup_kept is True   # higher composite
        assert scores[1].dedup_kept is False   # lower composite

    @patch("klippbok.curation.scorer.compute_phash")
    @patch("klippbok.curation.scorer.are_near_duplicates")
    def test_backwards_compat_is_duplicate(self, mock_dup, mock_hash, tmp_path):
        """Non-kept images should have signals.is_duplicate=True."""
        scores = [self._make_score("a", 0.8), self._make_score("b", 0.6)]
        paths = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
        for p in paths:
            p.touch()
        mock_hash.side_effect = ["hash_a", "hash_b"]
        mock_dup.return_value = True

        mark_duplicates(scores, paths)

        assert scores[0].signals.is_duplicate is False
        assert scores[1].signals.is_duplicate is True

    @patch("klippbok.curation.scorer.compute_phash")
    @patch("klippbok.curation.scorer.are_near_duplicates")
    def test_transitive_grouping(self, mock_dup, mock_hash, tmp_path):
        """A-B match + B-C match should group all three (transitive closure)."""
        scores = [
            self._make_score("a", 0.5),
            self._make_score("b", 0.9),
            self._make_score("c", 0.3),
        ]
        paths = [tmp_path / f"{x}.jpg" for x in "abc"]
        for p in paths:
            p.touch()
        mock_hash.side_effect = ["h1", "h2", "h3"]
        # A-B match, B-C match, A-C no match
        def dup_check(h1, h2, threshold=10):
            pair = frozenset([h1, h2])
            return pair in [frozenset(["h1", "h2"]), frozenset(["h2", "h3"])]
        mock_dup.side_effect = dup_check

        mark_duplicates(scores, paths)

        # All three should share same group
        assert scores[0].dedup_group_id == scores[1].dedup_group_id == scores[2].dedup_group_id
        # B has highest composite → kept
        assert scores[1].dedup_kept is True
        assert scores[0].dedup_kept is False
        assert scores[2].dedup_kept is False

    @patch("klippbok.curation.scorer.compute_phash")
    @patch("klippbok.curation.scorer.are_near_duplicates")
    def test_unique_images_no_group(self, mock_dup, mock_hash, tmp_path):
        """Non-matching images should have no group."""
        scores = [self._make_score("a", 0.8), self._make_score("b", 0.6)]
        paths = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
        for p in paths:
            p.touch()
        mock_hash.side_effect = ["hash_a", "hash_b"]
        mock_dup.return_value = False  # not duplicates

        mark_duplicates(scores, paths)

        assert scores[0].dedup_group_id is None
        assert scores[1].dedup_group_id is None
        assert scores[0].dedup_kept is True
        assert scores[1].dedup_kept is True
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/test_curation_scorer.py::TestMarkDuplicatesGroups -v`
Expected: FAIL — new fields not set by current `mark_duplicates()`.

- [ ] **Step 3: Rewrite `mark_duplicates()` with union-find**

Replace the existing `mark_duplicates()` function in `klippbok/curation/scorer.py`:

```python
def mark_duplicates(
    scores: list[ImageScore],
    image_paths: list[Path],
) -> None:
    """Group near-duplicate images using pHash + union-find.

    For each duplicate group, the highest-composite-score image is
    kept as the representative. Others get dedup_kept=False and
    signals.is_duplicate=True (backwards compat).

    Uses CURATION_PHASH_THRESHOLD (6) — tighter than import validation (10).

    Args:
        scores: List of ImageScore objects (must match image_paths order).
        image_paths: Corresponding image file paths.
    """
    from klippbok.curation.presets import CURATION_PHASH_THRESHOLD
    from klippbok.services.image_service import are_near_duplicates, compute_phash

    n = len(scores)
    if n != len(image_paths):
        raise ValueError("scores and image_paths must have the same length")

    # Compute all pHashes
    hashes: list[str | None] = []
    for path in image_paths:
        try:
            h = compute_phash(path)
            hashes.append(h)
        except Exception:
            hashes.append(None)

    # Union-find with path compression
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

    # Pairwise comparison
    for i in range(n):
        if hashes[i] is None:
            continue
        for j in range(i + 1, n):
            if hashes[j] is None:
                continue
            if are_near_duplicates(hashes[i], hashes[j], threshold=CURATION_PHASH_THRESHOLD):
                union(i, j)

    # Build groups from union-find roots
    groups: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        groups.setdefault(root, []).append(i)

    # Assign group IDs and select representatives
    for root, members in groups.items():
        if len(members) < 2:
            continue  # unique image, no group assignment needed
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

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/test_curation_scorer.py::TestMarkDuplicatesGroups -v`
Expected: All PASS

- [ ] **Step 5: Run full scorer test suite for regression**

Run: `pytest tests/test_curation_scorer.py -x -q`
Expected: All PASS (existing `mark_duplicates` tests may need assertion updates if they check `is_duplicate` behavior — update to also verify `dedup_group_id` and `dedup_kept`).

- [ ] **Step 6: Commit**

```bash
git add klippbok/curation/scorer.py tests/test_curation_scorer.py
git commit -m "feat(curation): rewrite mark_duplicates() with union-find grouping"
```

---

## Chunk 4: Pipeline Integration — Two-Tier Floor + Rank Wiring

### Task 6: Wire rank normalization and two-tier floor into pipeline

**Files:**
- Modify: `klippbok/curation/pipeline.py`
- Test: `tests/test_curation_pipeline.py`

- [ ] **Step 1: Write failing tests for two-tier floor**

Add to `tests/test_curation_pipeline.py`:

```python
class TestTwoTierFloor:
    """Tests for hard floor + soft floor logic."""

    def _make_score(self, image_id: str, raw_composite: float, ranked_composite: float) -> ImageScore:
        return ImageScore(
            image_id=image_id,
            relative_path=f"{image_id}.jpg",
            raw_composite_score=raw_composite,
            composite_score=ranked_composite,
            mode="character",
        )

    def test_hard_floor_excludes_low_raw_composite(self):
        """Images with raw composite below hard floor get floor_status='hard_floor'."""
        from klippbok.curation.pipeline import _apply_quality_floor
        from klippbok.curation.models import CurationConfig

        scores = [
            self._make_score("good", 0.6, 0.8),
            self._make_score("bad", 0.1, 0.2),   # below 0.15 hard floor
        ]
        config = CurationConfig(hard_floor=0.15, quality_floor_pct=0.0)
        _apply_quality_floor(scores, config)

        assert scores[0].floor_status == "passed"
        assert scores[1].floor_status == "hard_floor"

    def test_soft_floor_flags_but_doesnt_exclude(self):
        """Soft floor flags images but leaves floor_status != 'hard_floor'."""
        from klippbok.curation.pipeline import _apply_quality_floor
        from klippbok.curation.models import CurationConfig

        scores = [
            self._make_score("top", 0.9, 0.9),
            self._make_score("mid", 0.5, 0.5),
            self._make_score("low", 0.3, 0.1),  # raw 0.3 above hard floor, ranked 0.1
        ]
        config = CurationConfig(hard_floor=0.15, quality_floor_pct=0.5)
        _apply_quality_floor(scores, config)

        assert scores[0].floor_status == "passed"
        # One of mid/low will be below the 50th percentile soft cutoff
        soft_count = sum(1 for s in scores if s.floor_status == "soft_floor")
        hard_count = sum(1 for s in scores if s.floor_status == "hard_floor")
        assert hard_count == 0  # none below raw 0.15
        assert soft_count >= 1  # at least one below soft cutoff

    def test_all_good_images_no_hard_exclusion(self):
        """In a high-quality dataset, zero images should be hard-excluded."""
        from klippbok.curation.pipeline import _apply_quality_floor
        from klippbok.curation.models import CurationConfig

        scores = [self._make_score(str(i), 0.5 + i * 0.05, 0.5 + i * 0.05) for i in range(10)]
        config = CurationConfig(hard_floor=0.15)
        _apply_quality_floor(scores, config)

        assert all(s.floor_status != "hard_floor" for s in scores)
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/test_curation_pipeline.py::TestTwoTierFloor -v`
Expected: FAIL — `_apply_quality_floor` not importable.

- [ ] **Step 3: Implement `_apply_quality_floor()` in `pipeline.py`**

Add as a new helper function:

```python
def _apply_quality_floor(
    scores: list[ImageScore],
    config: CurationConfig,
) -> None:
    """Apply two-tier quality floor to scored images in-place.

    Hard floor: excludes images with raw_composite_score below config.hard_floor.
    Soft floor: flags images below the quality_floor_pct percentile of ranked
    composite scores (among non-hard-excluded images).

    Args:
        scores: List of ImageScore objects. Modified in-place.
        config: Curation configuration with hard_floor and quality_floor_pct.
    """
    # Hard floor: absolute exclusion based on raw composite
    for s in scores:
        if s.raw_composite_score < config.hard_floor:
            s.floor_status = "hard_floor"

    # Soft floor: advisory flag based on ranked composite percentile
    remaining = [s for s in scores if s.floor_status != "hard_floor"]
    if remaining and config.quality_floor_pct > 0:
        composites = np.array([s.composite_score for s in remaining])
        soft_cutoff = float(np.percentile(composites, config.quality_floor_pct * 100))
        for s in remaining:
            if s.composite_score < soft_cutoff:
                s.floor_status = "soft_floor"
```

- [ ] **Step 4: Wire into `run_curation()`**

Modify `run_curation()` in `pipeline.py`. After `score_images()` and `mark_duplicates()`, add:

```python
    # 2b. Rank-normalize signals and recompute composite
    from klippbok.curation.scorer import rank_normalize, _compute_composite
    rank_normalize(all_scores)
    for s in all_scores:
        s.raw_composite_score = s.composite_score  # preserve raw
        s.composite_score = _compute_composite(s.ranked_signals, config.mode)

    # 4. Two-tier quality floor
    _apply_quality_floor(all_scores, config)

    # 5. Build pool: exclude hard floor and dedup non-representatives
    passed_scores = [
        s for s in all_scores
        if s.floor_status != "hard_floor" and s.dedup_kept
    ]
```

Replace the old single-cutoff floor logic (the `composites = np.array(...)` / `cutoff = float(np.percentile(...))` / `passed_scores = [s for s in all_scores if s.composite_score >= cutoff and not s.signals.is_duplicate]` block).

Also update the `PipelineSummary`:

```python
    summary = PipelineSummary(
        total_scanned=total,
        passed_quality=len(passed_scores),
        selected=len(selected_ids),
        hard_excluded=sum(1 for s in all_scores if s.floor_status == "hard_floor"),
        soft_flagged=sum(1 for s in all_scores if s.floor_status == "soft_floor"),
    )
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `pytest tests/test_curation_pipeline.py -x -q`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/test_curation_scorer.py tests/test_curation_pipeline.py tests/test_curation_api.py -x -q`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add klippbok/curation/pipeline.py tests/test_curation_pipeline.py
git commit -m "feat(curation): wire rank normalization + two-tier quality floor into pipeline"
```

---

## Chunk 5: Rediversify Guard + Final Verification

### Task 7: Add rediversify pin guard

**Files:**
- Modify: `klippbok/curation/pipeline.py`

- [ ] **Step 1: Add pin guard to `rediversify()`**

In `rediversify()`, after loading embeddings and building `scores_list`, add:

```python
    # Guard: drop pinned IDs not present in embeddings (hard-floor excluded
    # or dedup non-representatives don't have cached embeddings)
    stored_id_set = set(stored_ids)
    dropped_pins = [pid for pid in pinned_ids if pid not in stored_id_set]
    if dropped_pins:
        logger.warning(
            "Dropping %d pinned IDs not in embeddings (hard-floor or dedup non-rep): %s",
            len(dropped_pins), dropped_pins[:5],
        )
    valid_pinned = [pid for pid in pinned_ids if pid in stored_id_set]
```

Then pass `valid_pinned` instead of `pinned_ids` to `select_diverse_subset()`.

Add `dropped_pins` to the returned `CurationResult` — but since `CurationResult` doesn't have that field, store it as metadata or simply log it. The simplest approach: just use `valid_pinned` and let the warning suffice for now.

- [ ] **Step 2: Commit**

```bash
git add klippbok/curation/pipeline.py
git commit -m "fix(curation): guard rediversify against pinning excluded images"
```

### Task 8: Final verification

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: All PASS

- [ ] **Step 2: Verify no import errors**

Run: `python -c "from klippbok.curation.pipeline import run_curation, rediversify; from klippbok.curation.scorer import rank_normalize, mark_duplicates; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Final commit if any cleanup needed**

```bash
git add -A && git commit -m "chore(curation): final cleanup after scoring overhaul"
```

---

## Summary

| Chunk | Tasks | What it delivers |
|-------|-------|-----------------|
| 1 | Tasks 1-3 | Model fields, constants, `are_near_duplicates` threshold param |
| 2 | Task 4 | `rank_normalize()` with full test coverage |
| 3 | Task 5 | Union-find `mark_duplicates()` with group representative selection |
| 4 | Task 6 | Pipeline integration: rank wiring + two-tier floor |
| 5 | Tasks 7-8 | Rediversify guard + final verification |
