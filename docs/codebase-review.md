# Klippbok Codebase Review

**Date:** 2026-02-26
**Scope:** Full codebase audit of all source and test files
**Codebase size:** ~12,566 lines of Python source across 42 modules, ~38 test files

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Code Quality](#2-code-quality)
3. [Architecture Analysis](#3-architecture-analysis)
4. [Security](#4-security)
5. [Performance](#5-performance)
6. [Testing](#6-testing)
7. [Configuration](#7-configuration)
8. [Dependencies](#8-dependencies)
9. [Documentation](#9-documentation)
10. [Issues and Recommendations](#10-issues-and-recommendations)

---

## 1. Project Overview

Klippbok is a Python toolkit for video dataset curation, preparation, and annotation targeting LoRA (Low-Rank Adaptation) training workflows -- specifically for the Wan video generation model. The project provides a complete pipeline from raw video ingestion through to training-ready dataset packaging.

### Core Pipeline

1. **Scan/Probe** -- Discover videos and extract metadata via ffprobe
2. **Scene Detection** -- Split source videos at shot boundaries using PySceneDetect
3. **Normalization** -- Re-encode clips to target FPS (16fps), resolution (480p/720p), and frame count (4n+1)
4. **Triage** -- CLIP-based embedding matching against reference concept images to filter relevant scenes
5. **Captioning** -- Generate textual descriptions via VLMs (Gemini, OpenAI-compatible, Replicate)
6. **Reference Extraction** -- Pull representative still frames from clips
7. **Dataset Organization** -- Structure, validate, bucket, and generate trainer configs

### Module Map

| Module | Lines | Purpose |
|--------|-------|---------|
| `klippbok/config/` | ~1,000 | YAML schema, defaults, config loading |
| `klippbok/caption/` | ~1,500 | VLM captioning backends, scoring, prompts |
| `klippbok/video/` | ~4,200 | Video processing, probing, splitting, validation, CLI |
| `klippbok/dataset/` | ~2,800 | Dataset discovery, validation, bucketing, trainer configs |
| `klippbok/triage/` | ~1,150 | CLIP embeddings, concept matching, filtering |

---

## 2. Code Quality

### Strengths

**Consistent Pydantic v2 usage.** The codebase uses `BaseModel` with `model_config = ConfigDict(frozen=True)` across almost all data classes. This enforces immutability and provides automatic validation, serialization, and clear schemas. Examples include `VideoMetadata`, `CaptionConfig`, `ExtractionConfig`, `SamplePair`, and many more.

**Well-structured error hierarchies.** Custom exception classes are organized into meaningful hierarchies:

```
# klippbok/video/errors.py
KlippbokVideoError (base)
  +-- FFmpegNotFoundError
  +-- ProbeError
  +-- SceneDetectionError
  +-- SplitError
  +-- FrameExtractionError
  +-- ImageQualityError

# klippbok/dataset/errors.py
KlippbokDatasetError (base)
  +-- DiscoveryError
  +-- ValidationError
  +-- OrganizeError
  +-- TrainerConfigError
  +-- ManifestError
```

**Meaningful enum types.** The codebase defines specific enums for issue severity (`Severity`), issue codes (`IssueCode`), extraction strategies (`ExtractionStrategy`), concept types (`ConceptType`), and organization layouts (`OrganizeLayout`). These replace magic strings throughout.

**Clean function signatures with type hints.** Nearly all functions have full parameter and return type annotations using modern syntax (`str | None` rather than `Optional[str]`).

### Areas for Improvement

**Several files exceed 300 lines.** The project's own quality gate specifies a 300-line file limit. Six source files breach this:

| File | Lines | Exceeds By |
|------|-------|------------|
| `video/__main__.py` | 844 | 544 |
| `triage/triage.py` | 793 | 493 |
| `video/extract.py` | 728 | 428 |
| `config/data_schema.py` | 675 | 375 |
| `video/split.py` | 564 | 264 |
| `video/validate.py` | 511 | 211 |

The `video/__main__.py` file at 844 lines is the most egregious. It contains the full CLI parser, all command handlers (`cmd_scan`, `cmd_ingest`, `cmd_normalize`, `cmd_caption`, `cmd_score`, `cmd_extract`, `cmd_triage`, `cmd_audit`), and helper functions. This should be decomposed.

**The `format` parameter shadows a Python builtin.** In `klippbok/video/frames.py`, the function `extract_frames()` uses `format` as a parameter name, which shadows the built-in `format()` function. While not a bug, it is a code smell.

**Inconsistent module-level exports.** Some `__init__.py` files provide clean public APIs (e.g., `klippbok/video/__init__.py` with explicit imports), while others are minimal or absent.

---

## 3. Architecture Analysis

### Overall Architecture: Well-Designed

The project follows a clean, modular architecture with five distinct packages that map directly to pipeline stages. Dependencies flow in one direction: `config` is a leaf dependency, `video` and `caption` are independent processing modules, `triage` depends on video probing, and `dataset` integrates the outputs.

### Design Patterns

**Abstract Base Class for VLM Backends.** The `VLMBackend` ABC in `klippbok/caption/base.py` defines `caption_video()` and `caption_image()` as the interface. Three concrete backends implement this: `GeminiBackend`, `OpenAICompatBackend`, `ReplicateBackend`. The factory function `_create_backend()` in `captioner.py` handles instantiation.

**Registry Pattern for Trainer Configs.** The `@register_trainer` decorator in `klippbok/dataset/trainers.py` enables a plug-in system for training configuration generators. Currently registered: `musubi-tuner` (TOML output) and `ai-toolkit` (YAML output).

```python
# klippbok/dataset/trainers.py
_TRAINERS: dict[str, TrainerFunc] = {}

def register_trainer(name: str) -> Callable:
    def decorator(fn: TrainerFunc) -> TrainerFunc:
        _TRAINERS[name] = fn
        return fn
    return decorator
```

**Duration-Adaptive Triage.** The `triage_clips()` function in `klippbok/triage/triage.py` automatically detects whether inputs are short clips (<30s, clip-level triage) or long videos (>=30s, scene-level triage with scene detection). This is a well-thought-out UX pattern that avoids requiring the user to know which mode to use.

### Separation of Concerns

The separation between models, logic, and CLI is generally clean:

- **Models**: `video/models.py`, `video/extract_models.py`, `dataset/models.py`, `triage/models.py`, `caption/models.py`
- **Logic**: `video/probe.py`, `video/split.py`, `video/validate.py`, `dataset/discover.py`, `dataset/validate.py`, `triage/triage.py`, etc.
- **CLI**: `video/__main__.py`, `dataset/__main__.py`

However, some logic leaks into CLI modules. For example, `_load_triage_manifest()` is defined in `video/__main__.py` rather than in a dedicated manifest/IO module.

### Data Flow

```
Raw Video --> probe_video() --> VideoMetadata
          --> detect_scenes() --> SceneBoundary[]
          --> split_video_at_scenes() --> clip files
          --> normalize_clip() --> normalized clips (16fps, 480p/720p, 4n+1 frames)
          --> triage_clips() --> TriageReport / VideoTriageReport
          --> caption_clips() --> .txt sidecar files
          --> extract_directory() --> reference .png images
          --> discover_dataset() --> SamplePair[]
          --> validate_dataset() --> DatasetValidation
          --> build_manifest() --> klippbok_manifest.json
          --> generate_*_config() --> trainer TOML/YAML
```

---

## 4. Security

### Subprocess Calls

The codebase makes extensive use of `subprocess.run()` for ffmpeg and ffprobe invocations. These are generally handled safely:

- Arguments are passed as lists (not shell strings), avoiding shell injection
- `capture_output=True` is used consistently
- Return codes are checked

**One concern:** The `_ffmpeg.py` auto-discovery searches Windows package manager paths (`WinGet`, `Chocolatey`, `Scoop`) for ffmpeg binaries. While practical, this trusts binaries found in user-writable paths without verification.

### API Key Handling

Caption backends accept API keys via constructor parameters:

```python
# klippbok/caption/gemini.py
class GeminiBackend(VLMBackend):
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
```

These are passed from environment variables through the CLI layer, not hardcoded. No secrets were found committed in the codebase.

### File System Operations

- `organize_dataset()` and `organize_clips()` perform file copy/move operations. Both support a `dry_run` mode for safety.
- Path traversal is not a practical concern since all paths come from local CLI arguments, not untrusted network input.

### No Critical Security Issues Found

The project is a local CLI tool, not a network service. The security surface is limited to subprocess execution and file I/O, both of which are handled appropriately.

---

## 5. Performance

### Subprocess Overhead

Video processing is inherently subprocess-heavy (ffmpeg, ffprobe). The codebase processes files sequentially with individual subprocess calls. For large batches, this could be slow.

**Observation:** `probe_directory()` in `klippbok/video/probe.py` probes each video sequentially. For directories with hundreds of files, parallel probing would be significantly faster.

**Observation:** `normalize_directory()` in `klippbok/video/split.py` processes clips sequentially. Each normalization spawns one or more ffmpeg processes.

### CLIP Embedding

The triage module loads CLIP models and processes frames. The `CLIPEmbedder` class caches the model in memory, which is correct. Frame sampling uses ffmpeg subprocess calls for extraction, which is the main bottleneck.

### Duplicate Detection

`find_duplicates()` in `klippbok/dataset/quality.py` uses perceptual hashing (dHash) with a union-find algorithm for grouping. This is O(n^2) in the worst case for pair-wise comparison but uses Hamming distance thresholding to prune. For typical dataset sizes (hundreds to low thousands of clips), this is adequate.

### Caption Scoring

`score_directory()` in `klippbok/caption/scoring.py` reads and scores captions sequentially. Since scoring is pure string analysis (no I/O-heavy operations), this is fast enough.

### Recommendations

- Consider `asyncio.gather` or `concurrent.futures.ThreadPoolExecutor` for batch probe and normalize operations
- The `_subdivide_segments()` function is efficient with O(n) complexity
- Frame extraction sampling uses evenly-spaced timestamps, avoiding unnecessary decoding

---

## 6. Testing

### Coverage Summary

The test suite contains **38 test files** covering all five modules plus cross-cutting concerns. The testing approach is thorough and well-organized.

| Area | Test Files | Approach |
|------|-----------|----------|
| Config | 1 | Comprehensive schema validation, edge cases, backwards compat |
| Caption | 7 | Mock backends, prompt templates, scoring, models |
| Video | 13 | Mix of unit (pure logic) and integration (ffmpeg-dependent) |
| Dataset | 10 | Filesystem-based tests with tmp_path, model validation |
| Triage | 7 | Mock CLIP/ffmpeg, model tests, concept discovery |

### Strengths

**Conditional skip markers.** Tests requiring external tools use well-designed markers:

```python
# tests/conftest.py
requires_ffmpeg = pytest.mark.skipif(
    not shutil.which("ffmpeg"), reason="ffmpeg not in PATH"
)
requires_scenedetect = pytest.mark.skipif(
    not _scenedetect_available(), reason="scenedetect not installed"
)
```

This allows the test suite to run meaningfully even without optional dependencies installed.

**Comprehensive fixtures.** The `conftest.py` provides multiple video fixtures generated via ffmpeg: `tiny_video` (320x240, 16fps), `tiny_video_720p`, `tiny_video_30fps`, `tiny_video_18frames`, `tiny_video_two_scene`. These are cached at session scope for efficiency.

**Good boundary testing.** Tests cover edge cases well:
- Zero-denominator frame rates (`test_zero_denominator`)
- N/A SAR values (`test_na`)
- Empty directories, nonexistent paths
- 4n+1 frame count validation with various inputs
- Backwards compatibility for config loading

**Mock isolation.** Caption backend tests use `unittest.mock` effectively to isolate from external APIs. The `MockBackend` class in `test_captioner.py` provides controllable behavior.

### Areas for Improvement

**Helper function duplication across test files.** Several test files define their own `_touch()`, `_make_flat_dataset()`, `_write_test_image()`, or similar helper functions. These should be consolidated into `conftest.py` or a `tests/helpers.py` module.

Duplicated helpers appear in:
- `tests/test_dataset_organize.py` -- `_touch()`, `_make_flat_dataset()`
- `tests/test_dataset_organize_cli.py` -- `_touch()`, `_make_flat_dataset()`
- `tests/test_dataset_validate.py` -- `_touch()`
- `tests/test_extract_cli.py` -- `_write_test_image()`
- `tests/test_video_extract.py` -- `_write_test_image()`
- `tests/test_triage_organize.py` -- `_make_ref()`, `_make_clip()`

**No parametrized edge case tables.** The CLAUDE.md specifies using `@pytest.mark.parametrize` for table-driven tests. While some tests cover multiple scenarios, they do so with individual test methods rather than parametrize decorators. Good candidates for parametrize include:
- `TestParseFrameRate` (5 cases that could be one parametrized test)
- `TestParseSAR` (6 cases)
- `test_nearest_valid_frame_count` scenarios

**No integration test for the full pipeline.** There is no single test that exercises the complete flow from raw video through to organized dataset output. Individual stages are well-tested, but the end-to-end contract is not verified.

---

## 7. Configuration

### Schema Design

The configuration system is built on a deeply nested Pydantic model hierarchy rooted at `KlippbokDataConfig` in `klippbok/config/data_schema.py`. Key design decisions:

- **Frozen models** with `ConfigDict(frozen=True)` for immutability
- **4n+1 frame count validation** via `@field_validator` for Wan model compatibility
- **Multi-dataset support** via `datasets: dict[str, DatasetConfig]`
- **Backwards compatibility** for `trigger_word` -> `anchor_word` rename

### Configuration Loading

`load_data_config()` in `klippbok/config/loader.py` implements a robust loading pipeline:

1. Find YAML file (explicit path or search current/parent directories)
2. Parse YAML with safe_load
3. Apply backwards compatibility transforms
4. Validate through Pydantic
5. Resolve relative paths to absolute

### Constants

`klippbok/config/defaults.py` centralizes training-specific constants:

```python
WAN_TRAINING_FPS = 16
VALID_RESOLUTIONS = {480, 720}
UMT5_MAX_TOKENS = 512
VALID_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv"}
```

### Observation

The `data_schema.py` file at 675 lines is large because it defines the entire nested schema in one file. While this keeps the schema cohesive, splitting into sub-schemas per pipeline stage would improve navigability.

---

## 8. Dependencies

### Dependency Groups (pyproject.toml)

The project uses optional dependency groups effectively:

| Group | Packages | Purpose |
|-------|----------|---------|
| Core | pydantic, pyyaml | Always required |
| `video` | opencv-python-headless, scenedetect | Video processing |
| `caption` | google-genai, openai, httpx, replicate | VLM captioning |
| `dataset` | rich | Formatted reports |
| `triage` | transformers, torch, Pillow | CLIP embeddings |
| `dev` | pytest, ruff | Development tools |
| `all` | All of the above | Full installation |

### Observations

**Good isolation.** Each module gracefully handles missing optional dependencies. For example, caption backends check for their SDK at import time and raise clear errors.

**Heavy ML dependencies.** The `triage` group pulls in `torch` and `transformers`, which are large packages. This is unavoidable for CLIP functionality but is properly isolated as optional.

**No dependency pinning.** The `pyproject.toml` uses minimum version specifiers (`>=`) rather than pinned versions. There is no `requirements-lock.txt` or equivalent. For a library/tool project this is acceptable, but a lockfile would improve reproducibility.

**Python 3.10+ required.** The project uses `requires-python = ">=3.10"`, enabling modern syntax like `X | Y` union types and structural pattern matching.

---

## 9. Documentation

### Existing Documentation

The `docs/` directory contains focused guides:
- `CAPTIONING.md` -- VLM captioning workflow
- `COMMANDS.md` -- CLI command reference
- `PIPELINES.md` -- Pipeline stage descriptions
- `WALKTHROUGH.md` -- End-to-end tutorial

The `README.md` provides a comprehensive project overview with a pipeline diagram.

### Code Documentation

**Module-level docstrings** are present on all test files and most source modules. They clearly describe the module's purpose and any external requirements.

**Function-level docstrings** are present on most public functions. They describe parameters, return values, and behavior.

**Inline comments** are used appropriately to explain non-obvious logic, such as the 4n+1 frame count formula and subdivision tail absorption.

### Areas for Improvement

- No `ARCHITECTURE.md` file despite the project structure expecting one at `project-docs/ARCHITECTURE.md`
- No `DECISIONS.md` or `INFRASTRUCTURE.md` as referenced in `CLAUDE.md`
- The `CLAUDE.md` references API versioning rules (`/api/v1/`) that are not applicable to this project (it is a CLI tool, not a web service)

---

## 10. Issues and Recommendations

### Critical (Must Fix)

**C1: Six source files exceed the 300-line quality gate.**

The project defines a 300-line file limit, but six files significantly exceed it. The most impactful refactoring targets:

| Priority | File | Lines | Recommendation |
|----------|------|-------|----------------|
| 1 | `video/__main__.py` | 844 | Extract command handlers into `video/commands/` package with one module per subcommand |
| 2 | `triage/triage.py` | 793 | Split scene-level triage (`triage_videos`, `_write_scene_manifest`) into `triage/scene_triage.py` |
| 3 | `video/extract.py` | 728 | Separate extraction strategies into individual modules or a strategy pattern |
| 4 | `config/data_schema.py` | 675 | Split into `config/video_schema.py`, `config/caption_schema.py`, `config/dataset_schema.py` |
| 5 | `video/split.py` | 564 | Extract `_subdivide_segments` and directory-level operations |
| 6 | `video/validate.py` | 511 | Extract report formatting into `video/report.py` |

### Important (Should Fix)

**I1: Consolidate duplicated test helpers.**

At least six test files define their own `_touch()`, `_make_flat_dataset()`, or `_write_test_image()` helpers. These should be moved to `tests/conftest.py` or a shared `tests/helpers.py` module to reduce duplication and ensure consistency.

**I2: Logic functions defined inside CLI module.**

`_load_triage_manifest()` is defined in `video/__main__.py` (a CLI module) but is imported by test files as business logic. This function should live in a dedicated module (e.g., `triage/manifest.py` or `video/manifest.py`).

**I3: Sequential processing of batch operations.**

`probe_directory()`, `normalize_directory()`, and `caption_clips()` all process files sequentially. For directories with many files, parallelizing with `concurrent.futures.ThreadPoolExecutor` (for subprocess-bound work) or `asyncio` would improve throughput significantly.

**I4: Missing end-to-end integration test.**

No test exercises the full pipeline from video input through to organized dataset output. A single integration test (even with a small synthetic video) would catch interface mismatches between pipeline stages.

**I5: `dataset/organize.py` and `dataset/quality.py` exceed 300 lines.**

`organize.py` is at 326 lines and `quality.py` at 303 lines. While only slightly over the limit, they should be monitored as they grow.

### Suggestions (Nice to Have)

**S1: Use `@pytest.mark.parametrize` for repetitive test cases.**

Several test classes enumerate similar test cases as individual methods. Converting to parametrized tests would be more concise and easier to extend. For example:

```python
# Before (5 separate test methods)
class TestParseFrameRate:
    def test_fraction(self): ...
    def test_ntsc(self): ...
    def test_plain_float(self): ...
    def test_invalid(self): ...
    def test_zero_denominator(self): ...

# After (1 parametrized test)
class TestParseFrameRate:
    @pytest.mark.parametrize("input_str,expected", [
        ("30/1", 30.0),
        ("24000/1001", 23.976),
        ("16.0", 16.0),
        ("invalid", 0.0),
        ("30/0", 0.0),
    ])
    def test_parse_frame_rate(self, input_str, expected):
        assert abs(_parse_frame_rate(input_str) - expected) < 0.001
```

**S2: Avoid shadowing the `format` builtin.**

In `klippbok/video/frames.py`, rename the `format` parameter to `output_format` or `image_format`.

**S3: Add a dependency lockfile.**

Consider adding a `requirements-lock.txt` or using `pip-tools` / `uv` for reproducible installs, especially for the heavy ML dependencies in the triage group.

**S4: Remove inapplicable standards from CLAUDE.md.**

The project CLAUDE.md includes rules about API versioning (`/api/v1/`), FastAPI handlers, and database connections that do not apply to this CLI tool. These inherited rules add noise and should be trimmed to match the actual project type.

**S5: Create the missing project documentation files.**

The project structure template references `project-docs/ARCHITECTURE.md`, `project-docs/DECISIONS.md`, and `project-docs/INFRASTRUCTURE.md`. At minimum, an `ARCHITECTURE.md` documenting the pipeline data flow and module dependencies would be valuable.

**S6: Consider adding `py.typed` marker.**

Since the codebase has comprehensive type annotations, adding a `py.typed` marker file would allow downstream consumers to benefit from the type information via PEP 561.

---

## Summary

Klippbok is a well-architected Python project with strong foundations:

- **Clean module boundaries** with five focused packages
- **Comprehensive Pydantic v2 models** enforcing data validation and immutability
- **Thorough test suite** (38 files) with good use of conditional markers and fixtures
- **Well-designed abstractions** including the VLM backend ABC and trainer registry pattern
- **Proper error handling** with custom exception hierarchies
- **Good documentation** including pipeline guides and a walkthrough

The primary areas needing attention are:

1. **File size violations** -- six files exceed the project's own 300-line quality gate, with `video/__main__.py` at 844 lines being the most pressing
2. **Test helper duplication** -- shared helpers should be consolidated
3. **Sequential batch processing** -- parallelization would improve performance for large datasets
4. **Missing integration tests** -- no end-to-end pipeline test exists

None of these are blocking issues. The codebase is functional, well-tested, and maintainable. The recommendations above would bring it into full compliance with its own stated quality standards and improve scalability for larger workflows.
