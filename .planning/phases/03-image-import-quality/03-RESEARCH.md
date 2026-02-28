# Phase 3: Image Import and Quality - Research

**Researched:** 2026-02-27
**Domain:** Image validation, perceptual hashing, blur detection, aspect-ratio bucketing
**Confidence:** HIGH

---

## Summary

Phase 3 adds three capabilities to the existing image module foundation: (1) a complete batch import pipeline that skips already-imported files, persists validation results to the project manifest, and produces summary reports; (2) model-aware aspect-ratio bucketing that assigns each image to its nearest valid bucket and produces a distribution histogram; and (3) quality analysis covering blur detection (Laplacian variance via numpy + Pillow) and perceptual-hash-based near-duplicate detection (imagehash 4.3.2 with pHash).

The codebase already has the image probe/validate/discover pipeline (Phase 1), the model profile and bucket generation system (Phase 2), and a project manifest (project_service.py). Phase 3 wires these together with three new modules: `image/bucket.py` (assignment logic), `image/quality.py` (blur + upscale checks), and `image/dedup.py` (perceptual hashing). The service layer (`services/image_service.py`) is expanded to orchestrate the full import flow.

A key finding: the existing `video/image_quality.py` uses OpenCV for Laplacian variance. Phase 3 should **not** introduce the OpenCV dependency to the `image` module — use numpy + Pillow instead, since Pillow is already required via `[image]` extras and the math is identical. imagehash is the standard ecosystem library for perceptual hashing; pHash with hash size 8 and a Hamming distance threshold of 10 is the recommended configuration for near-duplicate (not exact duplicate) detection.

**Primary recommendation:** Implement blur detection with numpy + Pillow (Laplacian kernel via `numpy.convolve`/`scipy.signal.convolve2d` or using Pillow's `ImageFilter.Kernel`), use `imagehash.phash()` for deduplication, and assign images to buckets using `argmin(|bucket_aspect - image_aspect|)` matching the NovelAI/kohya algorithm already reflected in `config/model_profiles.py:generate_buckets()`.

---

## Standard Stack

### Core (already in project)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Pillow | 12.1.1 (installed) | Image probing, format detection, TIFF/PNG/JPEG/WebP reading, grayscale conversion | Already required via `[image]` extras; handles all four target formats natively |
| numpy | 2.4.2 (installed) | Laplacian variance computation (blur detection) without OpenCV | Already a transitive dep via triage/torch; avoids OpenCV dependency in image module |
| pydantic v2 | >=2.0 | All result models (frozen, immutable) | Established project pattern |

### New Dependencies Required

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| imagehash | 4.3.2 (latest, Feb 2025) | Perceptual hashing for near-duplicate detection | Standard ecosystem library; pure Python + Pillow + numpy; no OpenCV needed |
| scipy | latest | Required by imagehash for pHash (FFT-based) | Transitive dependency of imagehash for phash algorithm |

### Dependency Addition

Add to `pyproject.toml` under `[project.optional-dependencies]`:

```toml
image = [
    "Pillow>=9.0",
    "imagehash>=4.3",
    "scipy>=1.9",
]
```

imagehash depends on scipy for pHash's DCT (via `scipy.fftpack`). Both are pure Python wheels with no system library requirements.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| imagehash pHash | OpenCV + custom implementation | OpenCV is a heavy dep not in image extras; imagehash is purpose-built, well-maintained |
| numpy Laplacian | OpenCV cv2.Laplacian | OpenCV already used in `video/image_quality.py`, but image module should stay Pillow-only |
| imagehash pHash | dhash (standalone package) | dhash is simpler but pHash is more robust to photometric attacks (brightness, contrast changes); imagehash provides both if needed |

### Installation

```bash
pip install "imagehash>=4.3" "scipy>=1.9"
# or with project extras:
pip install "klippbok[image]"  # after updating pyproject.toml
```

---

## Architecture Patterns

### Recommended Module Structure

New files for Phase 3:

```
klippbok/image/
├── bucket.py       # Image bucket assignment (nearest aspect ratio)
├── quality.py      # Blur detection (Laplacian variance via numpy/Pillow)
├── dedup.py        # Perceptual hashing (imagehash pHash)
└── import_result.py  # ImageImportResult model (summary + per-image results)
```

Expanded service:

```
klippbok/services/
└── image_service.py  # Extended: full import pipeline, dedup, bucketing, reporting
```

### Pattern 1: Nearest-Bucket Assignment

**What:** For each image, compute its aspect ratio, then find the bucket whose aspect ratio is closest by absolute difference.

**When to use:** Always during import. Bucketing is automatic on import (Claude's discretion per CONTEXT.md — this is the right choice: immediate feedback).

**Algorithm (matches kohya/NovelAI standard):**

```python
# Source: NovelAI bucketing algorithm, reflected in generate_buckets() in model_profiles.py
from klippbok.config.model_profiles import generate_buckets, ModelProfile

def assign_bucket(
    width: int,
    height: int,
    profile: ModelProfile,
    max_aspect_ratio: float = 2.0,
) -> tuple[int, int] | None:
    """Assign image to nearest bucket by aspect ratio.

    Returns None if no bucket is within max_aspect_ratio (extreme image).
    """
    buckets = generate_buckets(
        base_resolution=profile.base_resolution,
        step_size=profile.bucket_config.step_size,
        min_dimension=profile.bucket_config.min_dimension,
        max_dimension=profile.bucket_config.max_dimension,
        max_aspect_ratio=max_aspect_ratio,
    )
    if not buckets:
        return None

    image_ar = width / height
    best = min(buckets, key=lambda b: abs((b[0] / b[1]) - image_ar))

    # If the image aspect ratio exceeds max_aspect_ratio, flag but still assign
    image_max_ar = max(width, height) / min(width, height)
    if image_max_ar > max_aspect_ratio:
        return None  # Will become IMAGE_NO_VALID_BUCKET warning

    return best
```

Note: `IMAGE_NO_VALID_BUCKET` already exists in `IssueCode` enum — use it for extreme aspect ratio warnings.

### Pattern 2: Blur Detection Without OpenCV

**What:** Laplacian variance using numpy array operations on a Pillow grayscale image. Identical math to `video/image_quality.py` but without the OpenCV import.

**Implementation:**

```python
import numpy as np
from PIL import Image

# Laplacian kernel (same 3x3 operator used by cv2.Laplacian)
_LAPLACIAN_KERNEL = np.array([
    [0,  1,  0],
    [1, -4,  1],
    [0,  1,  0],
], dtype=np.float64)

def compute_blur_score(image: Image.Image) -> float:
    """Compute Laplacian variance as blur metric. Higher = sharper."""
    gray = image.convert("L")
    arr = np.array(gray, dtype=np.float64)
    from scipy.signal import convolve2d
    laplacian = convolve2d(arr, _LAPLACIAN_KERNEL, mode="valid")
    return float(laplacian.var())
```

**Threshold:** 100.0 is documented as working well for photographs. Phase 3 uses pass/fail with a fixed threshold — no user adjustment per CONTEXT.md decisions.

**When to use:** Called on every imported image after probing. Result stored in the import record.

### Pattern 3: Perceptual Hash — pHash via imagehash

**What:** imagehash.phash() produces a 64-bit perceptual hash. Two images are near-duplicates if their Hamming distance is <= threshold.

**Algorithm selection:** pHash (not dHash). Rationale:
- pHash is more robust to photometric changes (brightness, contrast, minor color shifts) — common in re-encoded images
- dHash (recommended at threshold 2 for exact duplicates) is too strict for the "near-identical" use case
- imagehash documentation and multiple sources agree: pHash with threshold 10 catches resized, re-compressed, and minor-crop variants

**Implementation:**

```python
# Source: imagehash 4.3 PyPI docs + verified with official GitHub README
import imagehash
from PIL import Image

PHASH_THRESHOLD = 10  # Hamming distance: <= 10 means near-duplicate

def compute_phash(image_path: Path) -> str:
    """Compute pHash for an image. Returns hex string for persistence."""
    with Image.open(image_path) as img:
        h = imagehash.phash(img)  # hash_size=8 default (64-bit hash)
    return str(h)  # Serialize to hex string for manifest storage

def are_near_duplicates(hash_hex_a: str, hash_hex_b: str) -> bool:
    """Returns True if two images are near-duplicates."""
    ha = imagehash.hex_to_hash(hash_hex_a)
    hb = imagehash.hex_to_hash(hash_hex_b)
    return (ha - hb) <= PHASH_THRESHOLD  # Hamming distance
```

**Persistence:** Store hash as hex string in manifest entry. On re-import, load existing hashes from manifest and compare new images against them. O(N) per new image, acceptable for typical dataset sizes (<10,000 images).

### Pattern 4: Already-Imported Skip Logic

**What:** Before probing, check if path is already in the project manifest. Skip silently if found.

**Implementation:** Load manifest on import start, build a set of known paths (relative), compare each discovered path before probing.

```python
known_paths: set[str] = {
    entry["path"] for entry in manifest.get("images", [])
    if "path" in entry
}
```

### Pattern 5: Upscale Warning

**What:** After bucket assignment, compare image dimensions to the assigned bucket dimensions. Flag if image is smaller than its bucket.

```python
# IssueCode.IMAGE_BELOW_MIN_RESOLUTION already exists -- add IMAGE_UPSCALE_REQUIRED
# OR: reuse IMAGE_BELOW_MIN_RESOLUTION with a different message targeting bucket size
# Recommendation: Add new IssueCode IMAGE_UPSCALE_REQUIRED to be explicit
```

Per CONTEXT.md, upscale warning triggers when image is smaller than its assigned bucket dimensions (not just base resolution). This is distinct from the existing `IMAGE_BELOW_MIN_RESOLUTION` check (which uses a fixed pixel threshold). Add `IMAGE_UPSCALE_REQUIRED` to `IssueCode` enum.

### Pattern 6: Auto-Keep Strategy for Duplicates

**What:** When near-duplicates are found, auto-keep the highest-resolution version. Tiebreaker: prefer lossless format (PNG > WEBP > JPG).

**Implementation:**

```python
FORMAT_PREFERENCE = {"png": 0, "webp": 1, "jpeg": 2}  # lower = preferred

def select_keeper(images: list[ImageMetadata]) -> ImageMetadata:
    """Select the image to keep from a near-duplicate group."""
    return min(
        images,
        key=lambda m: (-m.pixel_count, FORMAT_PREFERENCE.get(m.format, 99))
    )
```

### Pattern 7: Tiff Support

Pillow 12.1.1 natively reads TIFF files and reports format as `"tiff"`. The existing `SUPPORTED_IMAGE_FORMATS` set in `image/models.py` must be extended:

```python
# Current (Phase 1):
SUPPORTED_IMAGE_FORMATS: set[str] = {"png", "jpeg", "webp"}
SUPPORTED_IMAGE_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".webp"}

# Phase 3 update:
SUPPORTED_IMAGE_FORMATS: set[str] = {"png", "jpeg", "webp", "tiff"}
SUPPORTED_IMAGE_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
```

**Note:** Pillow reports format as `"tiff"` (lowercase) for `.tif` and `.tiff` files. Both extensions must be in `SUPPORTED_IMAGE_EXTENSIONS`.

### Anti-Patterns to Avoid

- **Don't import OpenCV into `klippbok/image/`**: OpenCV belongs to `video/` module only. Use numpy + scipy for Laplacian.
- **Don't block import on quality issues**: Per CONTEXT.md, blur and upscale warnings are advisory only. Never raise errors for quality checks.
- **Don't compute pHash on corrupt images**: Gate dedup on `not metadata.is_corrupt` — a corrupt image has no meaningful hash.
- **Don't use dHash for near-duplicate detection**: dHash with threshold 2 catches only near-exact duplicates. pHash with threshold 10 catches resized/recompressed copies.
- **Don't O(N²) scan on every import**: Build a set of existing hashes from manifest on import start; compare each new image only once against the set.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Perceptual hash | Custom DCT-based hash | `imagehash.phash()` | Correct implementation of PHash is non-trivial; imagehash is battle-tested, maintained, widely used |
| Hash comparison | Bit-counting loop | `hash_a - hash_b` (imagehash operator) | imagehash overloads `-` to return Hamming distance natively |
| Hash persistence | Custom serialization | `str(hash)` / `imagehash.hex_to_hash()` | imagehash serialization is stable and round-trips cleanly |
| Laplacian operator | Custom filter | numpy array with known kernel | The 3x3 Laplacian kernel is a fixed mathematical definition; just write it as a constant |
| Bucket generation | Re-implement | `generate_buckets()` from `config/model_profiles.py` | Already implemented and tested in Phase 2 |

**Key insight:** The image processing problems in this phase look mathematically simple but have many edge cases (CMYK Pillow modes, 16-bit TIFF, float32 numpy types). Use proven libraries and be defensive about type conversions.

---

## Common Pitfalls

### Pitfall 1: Pillow Mode vs Format Confusion

**What goes wrong:** Treating `image.format` and `image.mode` interchangeably. `format` is the file format ("tiff"), `mode` is the color space ("RGB", "CMYK", "L", "I", etc.).

**Why it happens:** TIFF files can be CMYK (print) or RGB (photo) — both are valid TIFF format but different modes.

**How to avoid:** Check `image.mode` separately from `image.format`. CMYK TIFFs cannot be used directly for training — add a WARNING issue (like RGBA → auto-convert CMYK to RGB with white background).

**Warning signs:** `img.mode == "CMYK"` or `img.mode == "I"` (32-bit grayscale) — both require conversion.

### Pitfall 2: imagehash Requires Open PIL Image (Not Path)

**What goes wrong:** Passing a file path string to `imagehash.phash()`.

**Why it happens:** imagehash takes a PIL `Image` object, not a path.

**How to avoid:**

```python
# CORRECT
with Image.open(path) as img:
    h = imagehash.phash(img)

# WRONG — TypeError
h = imagehash.phash(path)
```

### Pitfall 3: Numpy Array Dtype for Laplacian

**What goes wrong:** Computing Laplacian on a `uint8` array causes integer overflow in convolution.

**Why it happens:** The Laplacian kernel has negative coefficients. uint8 subtraction wraps.

**How to avoid:** Always convert to float64 before convolution:

```python
arr = np.array(gray, dtype=np.float64)  # NOT dtype=np.uint8
```

### Pitfall 4: Laplacian Variance Affected by Image Size

**What goes wrong:** Small images (256x256) give lower variance than large images with identical sharpness, making a fixed threshold unreliable.

**Why it happens:** Variance computation is not normalized by image area.

**How to avoid:** The fixed threshold approach (pass/fail at 100.0) is per CONTEXT.md — accept this limitation. The threshold 100.0 is documented as reasonable for photographs. Apply it consistently; don't try to normalize.

**Warning signs:** Images failing blur check that are visually acceptable — this is a known advisory limitation.

### Pitfall 5: TIFF Multi-Page Files

**What goes wrong:** A multi-page TIFF opens successfully with Pillow but only the first frame is read. The `n_frames` attribute exists but only the first is probed.

**Why it happens:** Pillow's `Image.open()` positions on frame 0. Multi-page TIFFs (e.g., scanned documents) are unusual in photo datasets but can appear.

**How to avoid:** In `probe_image()`, check `getattr(img, 'n_frames', 1)`. If `n_frames > 1`, add an INFO-level issue noting only the first frame will be used. Do not reject — import first frame with warning.

### Pitfall 6: Already-Imported Check Must Use Canonical Paths

**What goes wrong:** Same image imported twice via different relative paths (e.g., via symlink or mount point differences).

**Why it happens:** Path comparison breaks if one uses absolute and the other uses relative paths.

**How to avoid:** Normalize all paths to `Path.resolve()` before comparison. Store resolved paths in manifest.

### Pitfall 7: Dedup Across Different Imports

**What goes wrong:** Near-duplicate check only runs against images already in the manifest, misses duplicates within the same batch being imported.

**Why it happens:** If dedup only loads existing hashes and then imports, two images in the same new batch won't be compared against each other.

**How to avoid:** Build the hash map incrementally during import — after each new image is hashed, add its hash to the in-memory comparison set before processing the next image.

---

## Code Examples

### Full Blur Check (Pillow + numpy, no OpenCV)

```python
# No external source — derived from standard Laplacian definition + numpy docs
import numpy as np
from PIL import Image

_LAPLACIAN_3x3 = np.array([
    [0,  1,  0],
    [1, -4,  1],
    [0,  1,  0],
], dtype=np.float64)

BLUR_THRESHOLD = 100.0  # Fixed pass/fail threshold

def compute_laplacian_variance(img: Image.Image) -> float:
    """Compute Laplacian variance (sharpness metric). Higher = sharper."""
    gray = np.array(img.convert("L"), dtype=np.float64)
    from scipy.signal import convolve2d
    lap = convolve2d(gray, _LAPLACIAN_3x3, mode="valid")
    return float(lap.var())

def is_blurry(img: Image.Image) -> bool:
    """True if image Laplacian variance is below fixed threshold."""
    return compute_laplacian_variance(img) < BLUR_THRESHOLD
```

### Perceptual Hash Workflow

```python
# Source: imagehash 4.3 PyPI documentation + GitHub README
import imagehash
from PIL import Image

PHASH_THRESHOLD = 10  # Hamming distance <= 10 = near-duplicate

def hash_image(path: Path) -> str:
    """Compute pHash for image. Returns hex string."""
    with Image.open(path) as img:
        return str(imagehash.phash(img))  # hash_size=8 default = 64-bit

def is_near_duplicate(hex_a: str, hex_b: str) -> bool:
    """True if two images are near-duplicates (Hamming <= threshold)."""
    return (imagehash.hex_to_hash(hex_a) - imagehash.hex_to_hash(hex_b)) <= PHASH_THRESHOLD
```

### Nearest Bucket Assignment

```python
# Based on NovelAI bucketing algorithm (argmin aspect ratio delta)
def assign_to_bucket(
    width: int,
    height: int,
    buckets: list[tuple[int, int]],
) -> tuple[int, int] | None:
    """Find the nearest bucket for an image by aspect ratio.

    Returns None if image aspect ratio exceeds max_aspect_ratio
    (no valid bucket available — already excluded from generated list).
    """
    if not buckets:
        return None
    image_ar = width / height
    return min(buckets, key=lambda b: abs(b[0] / b[1] - image_ar))
```

### ImageImportResult Model (new)

```python
# Follows frozen Pydantic pattern established in Phase 1
from pydantic import BaseModel, ConfigDict, Field

class ImageImportEntry(BaseModel):
    """Per-image result of the import pipeline."""
    model_config = ConfigDict(frozen=True)

    path: Path
    metadata: ImageMetadata | None = None       # None if corrupt/unreadable
    validation: ImageValidation | None = None
    bucket: tuple[int, int] | None = None        # (width, height) assigned bucket
    blur_score: float | None = None
    phash: str | None = None                     # Hex string for persistence
    is_near_duplicate: bool = False
    duplicate_of: Path | None = None             # Path of the "keeper"
    skipped: bool = False                        # Already in manifest

class ImageImportReport(BaseModel):
    """Summary of a batch import."""
    model_config = ConfigDict(frozen=True)

    total_discovered: int
    imported: int
    skipped_existing: int
    rejected: int                                # ERROR-severity validation failures
    warned: int                                  # WARNING-severity (imported with issues)
    near_duplicates_flagged: int
    entries: list[ImageImportEntry] = Field(default_factory=list)

    @property
    def bucket_distribution(self) -> dict[str, int]:
        """Count per bucket key, e.g. {'512x512': 47, '768x512': 12}."""
        dist: dict[str, int] = {}
        for e in self.entries:
            if e.bucket:
                key = f"{e.bucket[0]}x{e.bucket[1]}"
                dist[key] = dist.get(key, 0) + 1
        return dist
```

### Manifest Entry for Images

```python
# Extension of project_service.py pattern for image entries
def image_to_manifest_entry(
    entry: ImageImportEntry,
    project_dir: Path,
) -> dict:
    """Serialize an image import entry for manifest storage."""
    def _rel(p: Path | None) -> str | None:
        if p is None:
            return None
        try:
            return str(p.resolve().relative_to(project_dir.resolve()))
        except ValueError:
            return str(p)

    result: dict = {
        "type": "image",
        "path": _rel(entry.path),
        "status": "valid" if (entry.validation and entry.validation.is_valid) else "invalid",
    }
    if entry.metadata:
        result["width"] = entry.metadata.width
        result["height"] = entry.metadata.height
        result["format"] = entry.metadata.format
    if entry.bucket:
        result["bucket"] = f"{entry.bucket[0]}x{entry.bucket[1]}"
    if entry.phash:
        result["phash"] = entry.phash
    if entry.blur_score is not None:
        result["blur_score"] = round(entry.blur_score, 2)
    if entry.is_near_duplicate:
        result["near_duplicate_of"] = _rel(entry.duplicate_of)
    if entry.validation and entry.validation.issues:
        result["issues"] = [
            {"code": i.code.value, "severity": i.severity.value, "message": i.message}
            for i in entry.validation.issues
        ]
    return result
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| OpenCV for Laplacian | numpy + Pillow + scipy convolution | This phase | Removes heavy dep from image module |
| No dedup | imagehash pHash | This phase | Standard library approach |
| Video-only bucketing (dataset/bucketing.py) | Model-profile-aware image bucketing (image/bucket.py) | This phase | Reuses generate_buckets() from Phase 2 |
| TIFF not in SUPPORTED_IMAGE_FORMATS | Add "tiff" to set | This phase | Requirements IMG-01 demands TIFF support |

---

## What Already Exists (Reuse, Don't Re-implement)

| What | Where | How Phase 3 Uses It |
|------|-------|----------------------|
| `probe_image()` | `image/probe.py` | Call for every discovered image |
| `validate_image()` | `image/validate.py` | Call after probe; augment with quality issues |
| `discover_images()` | `image/discover.py` | Call to scan directories; extend for TIFF exts |
| `generate_buckets()` | `config/model_profiles.py` | Call with effective profile to get bucket list |
| `resolve_effective_config()` | `config/model_config.py` | Merge per-project overrides before bucketing |
| `IssueCode` enum | `video/models.py` | Add `IMAGE_UPSCALE_REQUIRED`; reuse existing codes |
| `ValidationIssue` | `video/models.py` | Use for all quality findings |
| `save_manifest()` / `load_manifest()` | `services/project_service.py` | Persist image import results |
| `ImageMetadata`, `ImageValidation` | `image/models.py` | Extend, don't replace |

---

## IssueCode Changes Required

Add to `video/models.py` IssueCode enum (established single-source-of-truth for issue codes):

```python
# New codes for Phase 3:
IMAGE_UPSCALE_REQUIRED = "IMAGE_UPSCALE_REQUIRED"   # Image smaller than assigned bucket
IMAGE_BLUR_DETECTED = "IMAGE_BLUR_DETECTED"          # Laplacian variance below threshold
IMAGE_NEAR_DUPLICATE = "IMAGE_NEAR_DUPLICATE"        # pHash distance within threshold
IMAGE_EXTREME_ASPECT = "IMAGE_EXTREME_ASPECT"        # Aspect ratio beyond max_aspect_ratio
IMAGE_TIFF_MULTIPAGE = "IMAGE_TIFF_MULTIPAGE"        # Multi-page TIFF, first frame only
```

All five are WARNING severity per CONTEXT.md decisions (quality issues are advisory).

---

## Open Questions

1. **scipy.signal.convolve2d vs Pillow ImageFilter.Kernel for Laplacian**
   - What we know: Both work mathematically; scipy is already required by imagehash for pHash (no extra dep); Pillow's `Kernel` class supports 3x3 custom kernels but the scale/offset parameters make it tricky.
   - What's unclear: Whether the Pillow Kernel approach produces numerically identical results to scipy convolution.
   - Recommendation: Use `scipy.signal.convolve2d` — it's a direct dep via imagehash anyway, straightforward to test, and mathematically unambiguous.

2. **Manifest schema for image entries vs video entries**
   - What we know: Current manifest stores video entries. Image entries need additional fields (bucket, phash, blur_score).
   - What's unclear: Should image and video entries share the same `samples` list with `type` discriminator, or be stored in a separate `images` key?
   - Recommendation: Use separate `"images"` top-level key in manifest alongside existing `"samples"` (which is video). This avoids touching the video manifest format and keeps a clean separation.

3. **Blur threshold for real photographs**
   - What we know: 100.0 is documented as reasonable for general photographs. The `video/image_quality.py` uses 5.0 for blank detection and doesn't implement a general blur threshold.
   - What's unclear: Whether 100.0 is too strict for small images (256x256) or images with intentional soft focus.
   - Recommendation: Use 100.0 as fixed threshold per CONTEXT.md (pass/fail, not adjustable). Document the threshold clearly in code comments.

---

## Sources

### Primary (HIGH confidence)

- Pillow 12.1.1 official docs (https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html) — format support, TIFF, mode details
- Pillow 12.1.1 ImageFilter docs (https://pillow.readthedocs.io/en/stable/reference/ImageFilter.html) — FIND_EDGES, Kernel class
- imagehash 4.3.2 PyPI (https://pypi.org/project/ImageHash/) — version, installation, algorithms
- imagehash GitHub README (https://github.com/JohannesBuchner/imagehash) — API, hash serialization, comparison
- Codebase analysis: `klippbok/image/`, `klippbok/config/`, `klippbok/services/`, `klippbok/video/image_quality.py` — existing patterns, dependencies, models

### Secondary (MEDIUM confidence)

- Ben Hoyt's duplicate image detection article (https://benhoyt.com/writings/duplicate-image-detection/) — dHash threshold 2 for exact duplicates; informed recommendation to use pHash threshold 10 for near-duplicates
- imagededup documentation (https://idealo.github.io/imagededup/methods/hashing/) — pHash default threshold 15; cross-validates our recommendation of 10
- NovelAI aspect ratio bucketing (https://github.com/questianon/backup-of-novelai-aspect-ratio-bucketing) — argmin algorithm confirmed in kohya discussions

### Tertiary (LOW confidence)

- Multiple blog posts on Laplacian variance threshold 100.0 for photographs — single-domain evidence, not cross-validated with official source

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Pillow and numpy are confirmed installed; imagehash 4.3.2 version confirmed on PyPI; scipy is imagehash's documented dependency
- Architecture: HIGH — all patterns derived from direct codebase analysis of existing Phases 1 and 2 implementations
- Blur threshold: MEDIUM — 100.0 is widely cited but domain-dependent; fixed per CONTEXT.md anyway
- pHash threshold: MEDIUM — threshold 10 supported by multiple sources; imagededup uses 15, ben hoyt uses 2 for exact-only; 10 is a reasonable middle ground

**Research date:** 2026-02-27
**Valid until:** 2026-03-27 (imagehash is stable; Pillow and numpy APIs are stable)
