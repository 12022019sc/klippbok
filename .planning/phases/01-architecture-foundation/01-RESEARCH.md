# Phase 1 Research: Architecture Foundation

**Researched:** 2026-02-27
**Mode:** Phase-specific implementation research
**Overall confidence:** HIGH (based entirely on codebase analysis -- no external dependencies to verify)

---

## 1. Current Architecture Analysis

### What Exists Today

The codebase has four domain modules (`video/`, `dataset/`, `caption/`, `triage/`) with two CLI entry points (`video/__main__.py`, `dataset/__main__.py`). There is **no service layer** -- CLI commands directly call library functions and compose results inline.

**Current call flow (dataset CLI example):**
```
CLI (__main__.py cmd_validate)
  -> imports load_config, validate_all, build_manifest directly
  -> calls validate_all(config, config_dir)
  -> formats report inline
  -> handles manifest writing inline
```

**Current call flow (video CLI example):**
```
CLI (__main__.py cmd_ingest)
  -> imports probe_video, detect_scenes, split_video_at_scenes directly
  -> calls them sequentially inline
  -> writes manifest as JSON inline
```

Both CLIs contain significant business logic (path resolution, config override application, concept filtering, manifest generation) that would need duplicating for API routes.

### Established Patterns (must follow)

| Pattern | Where Used | Description |
|---------|-----------|-------------|
| Frozen Pydantic models | `video/models.py`, `dataset/models.py` | `model_config = ConfigDict(frozen=True)` on all data models |
| Accumulative validation | `video/validate.py`, `dataset/validate.py` | Collect all `ValidationIssue` objects, never fail-fast |
| `ValidationIssue` structure | `video/models.py` lines 172-198 | `code: IssueCode`, `severity: Severity`, `message: str`, `field: str`, `actual: Any`, `expected: Any` |
| `IssueCode` enum | `video/models.py` lines 37-83 | `{WHAT}_{PROBLEM}` naming, all codes in one enum |
| Severity levels | `video/models.py` lines 25-34 | ERROR (can't use), WARNING (fixable), INFO (no action) |
| Optional dependency groups | `pyproject.toml` | `[video]`, `[caption]`, `[dataset]`, `[triage]`, `[all]`, `[dev]` |
| Stem-based file pairing | `dataset/discover.py` | Files joined by filename stem across roles (target, caption, reference) |
| Errors with fix hints | `video/errors.py`, `dataset/errors.py` | Every error message says what's wrong + how to fix it |
| `__init__.py` re-exports | `video/__init__.py`, `triage/__init__.py` | Public API defined via `__all__` with categorized imports |
| Config from YAML | `config/loader.py` | `load_data_config()` handles YAML, directory, or path input |

### Current SamplePair Model

Located in `dataset/models.py` lines 61-124. Key characteristics:
- **Video-only**: `target: Path` is assumed to be a video file
- **Video-specific metadata**: `width`, `height`, `frame_count`, `fps` -- no image equivalents
- **Hardcoded role names**: target (video), caption (.txt), reference (image)
- **No type discriminator**: No field indicating whether this is an image or video sample

### Current Discovery System

`dataset/discover.py` classifies files by extension:
- `VIDEO_EXTENSIONS` -> "target" role
- `IMAGE_EXTENSIONS` -> "reference" role (never "target")
- `CAPTION_EXTENSIONS` -> "caption" role

This means **images are always treated as references, never as training targets**. Phase 1 must change this classification logic.

### Current Manifest System

Two separate manifest systems exist:
1. **Dataset manifest** (`dataset/manifest.py`): `klippbok_manifest.json` -- validation snapshot, not persistent state
2. **Video manifest** (`video/__main__.py` `_write_manifest`): `manifest.json` -- processing results, written inline

Neither is a "project manifest" that tracks sample state across sessions.

---

## 2. Service Layer Design

### Problem Statement

Business logic is embedded in CLI `cmd_*` functions. For Phase 4 (API routes), this logic must be callable from both CLI and API without duplication. A service layer provides this single code path.

### Recommended Approach: Domain Services

**One service per domain, not a monolithic service class.**

Rationale: The existing codebase is organized by domain (`video/`, `dataset/`, `caption/`, `triage/`). A service-per-domain approach preserves this structure and keeps each service focused.

```
klippbok/
  services/
    __init__.py
    dataset_service.py    # validate, organize, manifest
    image_service.py      # import, validate, quality (new)
    project_service.py    # project manifest, cross-domain state
```

**Service characteristics:**
- **Stateless functions, not classes**: Each service function takes its inputs and returns results. No `self`, no instance state. This matches the existing pattern (all library functions are stateless).
- **CLI lifespan = single function call**: CLI calls `service.validate(config)`, gets result, exits.
- **API lifespan = same function calls**: API route calls `service.validate(config)`, returns JSON response.
- **No service registry/DI framework**: Overkill for this codebase. Direct imports are fine.

**Why not a single service class:**
- The domains are independent (video, image, dataset, caption)
- A monolithic class would grow unwieldy
- Separate modules are easier to test
- Matches the existing module-per-domain pattern

### What Moves Into Services

From `dataset/__main__.py cmd_validate` (lines 159-255):
- Config loading and CLI override application -> `dataset_service.validate()`
- Bucketing preview -> `dataset_service.preview_bucketing()`
- Manifest writing -> `project_service.save_manifest()`

From `video/__main__.py cmd_ingest` (lines 162-307):
- Video ingest orchestration -> `video_service.ingest()` (Phase 7, not Phase 1)

**Phase 1 scope**: Create `dataset_service.py` and `image_service.py` with the patterns. Refactor `dataset/__main__.py` to call through the service. Do NOT refactor `video/__main__.py` yet (that's Phase 7).

### Project Manifest

The context document specifies: "a persistent file (YAML/JSON) tracks all samples and their state, survives between sessions, enables resume."

**Recommendation: JSON format, `.klippbok/manifest.json` location.**

Rationale:
- JSON is already used for the existing manifest (`klippbok_manifest.json`)
- YAML would add pyyaml as a hard dependency for reading state (it already is, but JSON is simpler for machine-written state files)
- `.klippbok/` directory keeps project state separate from user data files
- Single file avoids multi-file coordination problems

**Manifest structure (minimal for Phase 1):**
```json
{
  "version": "1",
  "created": "2026-02-27T...",
  "updated": "2026-02-27T...",
  "samples": [
    {
      "stem": "image_001",
      "type": "image",
      "source": "relative/path/to/image_001.png",
      "width": 1920,
      "height": 1080,
      "caption": "relative/path/to/image_001.txt",
      "issues": [],
      "status": "valid"
    }
  ]
}
```

**Key decisions:**
- Relative paths (portable across machines)
- `type` field for discrimination ("image" or "video")
- `status` field for quick filtering without revalidating
- `issues` stored as serialized `ValidationIssue` objects
- No processing history (per context decision)

---

## 3. Image Domain Module

### Module Structure

Follow the exact pattern of `video/` and `dataset/`:

```
klippbok/image/
  __init__.py          # Public API re-exports with __all__
  models.py            # Frozen Pydantic models (ImageMetadata, ImageValidation)
  validate.py          # Accumulative validation (format, corruption, dimensions, color mode)
  discover.py          # File discovery (find images in a directory)
  errors.py            # Domain-specific exceptions
```

### ImageMetadata Model

Analogous to `VideoMetadata` in `video/models.py`:

```python
class ImageMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: Path
    width: int
    height: int
    format: str          # "png", "jpeg", "webp"
    color_mode: str      # "RGB", "RGBA", "L", "P", etc.
    file_size: int | None = None
    has_alpha: bool = False
    is_corrupt: bool = False
```

**Probing strategy**: Use `Pillow` for image reading.
- `PIL.Image.open()` with `.verify()` for corruption detection
- Open again (after verify closes it) for actual metadata
- No ffprobe needed -- pure Python

**Pillow dependency**: Currently only in `[triage]` optional group. For Phase 1, Pillow should be added as a base dependency OR in a new `[image]` optional group.

**Recommendation: Add Pillow to a new `[image]` optional group.** Rationale:
- Keeps the CLI-only video workflow lightweight (no Pillow needed)
- Consistent with existing pattern of optional groups
- The `[gui]` group (ARCH-05) will depend on `[image]`

### Image Validation

Follow the accumulative pattern from `video/validate.py`:

```python
def validate_image(
    metadata: ImageMetadata,
    config: ImageConfig,  # new config section
) -> ImageValidation:
    issues: list[ValidationIssue] = []

    # Format check
    if metadata.format not in SUPPORTED_FORMATS:
        issues.append(...)

    # Corruption check
    if metadata.is_corrupt:
        issues.append(...)

    # Dimensions check (bucket-aware, not simple min-dimension)
    if not fits_any_bucket(metadata.width, metadata.height, config.buckets):
        issues.append(...)  # include nearest valid bucket suggestion

    # Color mode check
    if metadata.color_mode == "RGBA":
        issues.append(...)  # warning: will flatten to RGB

    return ImageValidation(metadata=metadata, issues=issues)
```

### New IssueCode Values

Need to extend the existing `IssueCode` enum in `video/models.py`:

```python
# Image-specific issues (Phase 1)
IMAGE_FORMAT_UNSUPPORTED = "IMAGE_FORMAT_UNSUPPORTED"
IMAGE_CORRUPT = "IMAGE_CORRUPT"
IMAGE_RGBA_CONVERSION = "IMAGE_RGBA_CONVERSION"
IMAGE_NO_VALID_BUCKET = "IMAGE_NO_VALID_BUCKET"
IMAGE_BELOW_MIN_RESOLUTION = "IMAGE_BELOW_MIN_RESOLUTION"
```

**Important**: These go in the EXISTING `IssueCode` enum in `video/models.py`, not in a new enum. The codebase uses a single `IssueCode` enum shared across all domains. This is an intentional pattern -- it makes issue filtering consistent.

### Supported Formats

Per context decisions: PNG, JPG/JPEG, WEBP only.

```python
SUPPORTED_IMAGE_FORMATS: set[str] = {"png", "jpeg", "webp"}
# Note: PIL reports "jpeg" not "jpg"
SUPPORTED_IMAGE_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".webp"}
```

### RGBA Handling

Per context: "RGBA images accepted and auto-flattened to RGB (composite onto white background)."

This is a **transformation**, not just validation. Phase 1 validates and flags; the actual flattening happens during export (Phase 8) or import (Phase 3). For Phase 1, the validator produces a WARNING-severity `IMAGE_RGBA_CONVERSION` issue.

---

## 4. Unified SamplePair Model

### Current State

`SamplePair` in `dataset/models.py` is video-specific:
- `target: Path` assumed to be video
- `width`, `height`, `frame_count`, `fps` are video metadata
- `reference: Path | None` is always an image reference for I2V

### Unification Strategy

**Option A: Discriminated union with Literal type field**

```python
class SamplePair(BaseModel):
    model_config = ConfigDict(frozen=True)

    stem: str
    type: Literal["image", "video"]
    target: Path
    caption: Path | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)

    # Shared dimensions
    width: int | None = None
    height: int | None = None

    # Video-specific (None for images)
    frame_count: int | None = None
    fps: float | None = None
    reference: Path | None = None  # I2V reference image

    # Image-specific (None for videos)
    format: str | None = None       # "png", "jpeg", "webp"
    color_mode: str | None = None   # "RGB", "RGBA"
```

**Option B: Separate subclasses with a union type**

```python
class ImageSample(BaseModel):
    type: Literal["image"] = "image"
    ...image fields...

class VideoSample(BaseModel):
    type: Literal["video"] = "video"
    ...video fields...

SamplePair = ImageSample | VideoSample  # discriminated union
```

**Recommendation: Option A (single model with type discriminator).**

Rationale:
1. **Minimizes downstream breakage**: All existing code uses `SamplePair` directly. A single model with a new `type` field is backwards-compatible if `type` defaults to `"video"`.
2. **Simpler iteration**: `for sample in dataset.samples` works regardless of type. No isinstance checks needed for shared operations (issue reporting, stem access, etc.).
3. **Context says "start minimal"**: A flat model with optional fields is simpler than a class hierarchy.
4. **Frozen models prevent invalid combinations**: Can't set `fps` on an image at construction time if the caller doesn't pass it.

**Migration path:**
1. Add `type: Literal["image", "video"] = "video"` to existing `SamplePair`
2. Add `format: str | None = None` and `color_mode: str | None = None`
3. All existing code continues to work (type defaults to "video")
4. New image code creates `SamplePair(type="image", ...)`

### Discovery Changes

`dataset/discover.py` currently puts all images in "reference" role. For mixed datasets:

```python
def _classify_extension(path: Path, target_type: str = "video") -> str:
    """Classify a file by its extension into a role.

    target_type controls whether images are targets or references:
    - "video": images are references (existing behavior)
    - "image": images are targets (new behavior)
    - "mixed": both video and image files are targets
    """
```

**Recommendation**: Add a `target_type` parameter to the discovery system rather than changing the default. This preserves backwards compatibility for existing CLI workflows.

---

## 5. Dependency Structure

### Current Groups

```toml
[project.optional-dependencies]
video = ["scenedetect[opencv]>=0.6"]
caption = ["google-genai>=1.0", "requests>=2.20"]
dataset = ["filetype>=1.2", "rich>=13.0"]
triage = ["torch>=2.0", "transformers>=4.30", "Pillow>=9.0"]
all = ["klippbok[video]", "klippbok[caption]", "klippbok[dataset]", "klippbok[triage]"]
dev = ["pytest>=7.0", "pytest-tmp-files>=0.0.2"]
```

### Needed Changes

```toml
[project.optional-dependencies]
image = ["Pillow>=9.0"]                           # NEW: image processing
video = ["scenedetect[opencv]>=0.6"]
caption = ["google-genai>=1.0", "requests>=2.20"]
dataset = ["filetype>=1.2", "rich>=13.0"]
triage = ["torch>=2.0", "transformers>=4.30", "klippbok[image]"]  # triage depends on image
gui = [                                             # NEW: Phase 4+ but define group now
    "klippbok[image]",
    "fastapi>=0.100",
    "uvicorn>=0.20",
]
all = ["klippbok[video]", "klippbok[caption]", "klippbok[dataset]", "klippbok[triage]", "klippbok[image]"]
dev = ["pytest>=7.0", "pytest-tmp-files>=0.0.2", "Pillow>=9.0"]  # tests need Pillow
```

**Key decisions:**
- `[image]` group is separate from `[gui]` -- image validation can run headless
- `[triage]` already has Pillow; now depends on `[image]` to avoid duplication
- `[gui]` group defined as empty/placeholder in Phase 1, populated in Phase 4
- Pillow added to `[dev]` so image tests work in CI

---

## 6. Backwards Compatibility

### Risk Assessment

| Change | Risk | Mitigation |
|--------|------|------------|
| Adding `type` field to SamplePair | LOW | Default to "video", all existing code works |
| Adding new IssueCode values | NONE | Enum extension is backwards-compatible |
| Moving CLI logic to services | MEDIUM | CLI behavior must be identical; test both |
| Changing discover.py classification | HIGH | Must not change default behavior for video-only datasets |
| New `[image]` dependency group | NONE | Additive change |
| New `klippbok/image/` module | NONE | Additive, no existing code changes |

### Testing Strategy for ARCH-07

Create a specific test suite that verifies existing CLI behavior is unchanged:

```python
def test_dataset_validate_cli_unchanged():
    """Existing `python -m klippbok.dataset validate` produces identical output."""

def test_video_scan_cli_unchanged():
    """Existing `python -m klippbok.video scan` produces identical output."""
```

These tests should be written FIRST (before refactoring) to serve as regression guards.

---

## 7. Plan-Specific Findings

### Plan 01-01: Service Layer and Project Manifest

**What needs to happen:**
1. Create `klippbok/services/` package
2. Create `dataset_service.py` with functions extracted from `dataset/__main__.py cmd_validate` and `cmd_organize`
3. Create `project_service.py` with project manifest read/write
4. Refactor `dataset/__main__.py` to call through services
5. Verify CLI behavior is unchanged

**Key risk:** The refactoring of `cmd_validate` and `cmd_organize` is the most delicate part. These functions have complex branching (config overrides, concept filtering, manifest writing). Extract carefully.

**Estimated complexity:** Medium. The logic extraction is straightforward but requires careful testing.

### Plan 01-02: Image Domain Module

**What needs to happen:**
1. Create `klippbok/image/` package with `models.py`, `validate.py`, `discover.py`, `errors.py`, `__init__.py`
2. Add image-specific `IssueCode` values to `video/models.py`
3. Add `[image]` dependency group to `pyproject.toml`
4. Create `image_service.py` in services
5. Write tests

**Key risk:** Pillow version compatibility. The triage module already requires `Pillow>=9.0` which should be sufficient. `Image.verify()` has existed since PIL 1.0.

**Important Pillow pattern for corruption detection:**
```python
from PIL import Image

def probe_image(path: Path) -> ImageMetadata:
    try:
        img = Image.open(path)
        img.verify()  # checks for corruption, closes file
    except Exception:
        return ImageMetadata(path=path, is_corrupt=True, ...)

    # Must re-open after verify() -- verify closes the image
    img = Image.open(path)
    return ImageMetadata(
        path=path,
        width=img.width,
        height=img.height,
        format=img.format.lower(),  # "PNG" -> "png", "JPEG" -> "jpeg"
        color_mode=img.mode,
        has_alpha="A" in img.mode,
    )
```

**Estimated complexity:** Low-Medium. Standard module creation following established patterns.

### Plan 01-03: Unified SamplePair and Dependency Groups

**What needs to happen:**
1. Add `type` field to `SamplePair` with `"video"` default
2. Add `format` and `color_mode` optional fields
3. Update `dataset/discover.py` to support image targets (behind a parameter)
4. Update `pyproject.toml` dependency groups
5. Update `dataset/__init__.py` and `image/__init__.py` exports
6. Verify all existing tests pass unchanged

**Key risk:** The `SamplePair` model is used extensively in `dataset/validate.py`, `dataset/organize.py`, `dataset/manifest.py`, `dataset/bucketing.py`, and `dataset/report.py`. All these modules reconstruct `SamplePair` objects. Adding fields with defaults means no changes are needed in these files, but verify.

**Frozen model gotcha:** Because SamplePair is frozen, all existing code uses constructor kwargs, not mutation. Adding optional fields with defaults won't break any constructors. This is a strength of the frozen pattern.

**Estimated complexity:** Low. Additive changes with defaults.

---

## 8. Open Questions for Implementation

1. **Where should `ValidationIssue` and `IssueCode` live long-term?** Currently in `video/models.py`, but they're used by `dataset/`, and Phase 1 adds image usage. Consider moving to a shared location like `klippbok/models.py` or `klippbok/validation.py`. However, this is a rename risk -- could do it now or defer.

   **Recommendation:** Defer the move. Add image issue codes to the existing `video/models.py` enum. It's ugly (image codes in a "video" module) but safe. Moving can happen in a cleanup phase.

2. **Bucket-aware resolution validation**: The context says "Resolution validation is bucket-aware, not simple min-dimension." This requires knowing the bucket definitions, which come from model profiles (Phase 2). For Phase 1, validate against basic dimensions. Add bucket-aware validation in Phase 3 when model config exists.

   **Recommendation:** Phase 1 validates format, corruption, dimensions (min/max), and color mode. Bucket-aware validation deferred to Phase 3.

3. **Service function signatures**: Should services accept `KlippbokDataConfig` objects or raw parameters?

   **Recommendation:** Accept `KlippbokDataConfig` objects. This is what the library functions already accept, and it keeps the service layer thin. CLI handles config loading, service handles business logic.

---

## 9. Confidence Assessment

| Area | Confidence | Reason |
|------|-----------|--------|
| Current codebase patterns | HIGH | Direct code analysis, no assumptions |
| Service layer design | HIGH | Standard refactoring pattern, well-understood |
| Image module structure | HIGH | Follows existing patterns exactly |
| SamplePair unification | HIGH | Additive change with defaults, low risk |
| Pillow API for probing | HIGH | `Image.open()` / `.verify()` is stable, long-established API |
| Dependency groups | HIGH | Additive changes to `pyproject.toml` |
| Backwards compatibility | HIGH | Default values preserve all existing behavior |
| Bucket-aware validation | MEDIUM | Deferred to Phase 3; needs model profiles first |

---

## 10. Implementation Order Recommendation

```
01-01: Service layer and project manifest
  - Create services/ package structure
  - Extract dataset CLI logic into dataset_service.py
  - Create project manifest read/write in project_service.py
  - Refactor dataset/__main__.py to call services
  - Write regression tests for CLI behavior

01-02: Image domain module
  - Create image/ package (models, validate, discover, errors)
  - Add image IssueCode values to video/models.py
  - Add [image] dependency group
  - Create image_service.py
  - Write unit tests for image validation

01-03: Unified SamplePair and dependency groups
  - Add type discriminator to SamplePair
  - Add image-specific optional fields
  - Update discover.py for mixed target types
  - Finalize dependency groups
  - Run full test suite, verify no regressions
```

This order is correct: services first (foundation), then image module (new domain), then unification (connecting them). Each plan is independently testable.
