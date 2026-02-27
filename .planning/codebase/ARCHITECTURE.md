# Architecture

**Analysis Date:** 2026-02-27

## Pattern Overview

**Overall:** Modular pipeline architecture with layered abstractions. Klippbok is a **domain-driven video dataset toolkit** that separates concerns into independent modules (video processing, configuration, dataset validation, captioning, triage). Each module operates as a standalone library with explicit entry points via CLI interfaces.

**Key Characteristics:**
- **Domain modules first**: Five independent domain modules (`video`, `config`, `dataset`, `caption`, `triage`) each encapsulating a distinct stage of the pipeline
- **Data-driven validation**: Models accumulate validation issues rather than failing fast — all checks run independently so users get complete error reports
- **Pydantic v2 throughout**: All config, models, and validation use Pydantic BaseModel for type safety and serialization
- **Optional feature groups**: Dependencies are grouped by feature (`video`, `caption`, `triage`, `dataset`). A minimal install includes only `config` and `dataset` validation
- **CLI as thin wrappers**: Both `video.__main__` and `dataset.__main__` are argument parsers that delegate to module functions — no business logic in CLI layer
- **Manifest-driven state tracking**: Pipelines communicate via JSON manifests (`klippbok_manifest.json`, `scene_triage_manifest.json`, `manifest.json`) rather than loose file discovery

## Layers

**Config Layer:**
- Purpose: Define what we're training and how to process it. Loads YAML configuration files into Pydantic models with sensible defaults
- Location: `klippbok/config/`
- Contains: `data_schema.py` (Pydantic models), `loader.py` (YAML loading), `defaults.py` (hardcoded constants)
- Depends on: Only Pydantic (core dependency)
- Used by: All other modules — `video`, `dataset`, `caption`, `triage` all read `KlippbokDataConfig`

**Video Layer:**
- Purpose: Raw footage processing — probe metadata, detect scenes, split into clips, normalize to target specs, extract reference images
- Location: `klippbok/video/`
- Contains: `probe.py` (ffprobe wrapper), `scene.py` (PySceneDetect wrapper), `split.py` (frame-accurate cutting and re-encoding), `extract.py` (reference frame selection), `validate.py` (clip quality checks), `frames.py` (frame extraction utilities)
- Depends on: `config` layer, ffmpeg/ffprobe (external), PySceneDetect (optional)
- Used by: CLI (`video.__main__`), triage module (for video metadata), dataset validation (for frame metrics)

**Dataset Layer:**
- Purpose: High-level dataset operations — pair targets with captions/references, validate completeness, organize into trainer-ready structures, generate manifests
- Location: `klippbok/dataset/`
- Contains: `discover.py` (file discovery and pairing), `validate.py` (orchestrates all quality checks), `organize.py` (output formatting for trainers), `bucketing.py` (group samples by characteristics), `quality.py` (frame quality metrics), `report.py` (formatting for human consumption)
- Depends on: `config`, `video` (for validation functions), Pydantic
- Used by: CLI (`dataset.__main__`), end-to-end pipelines

**Caption Layer:**
- Purpose: Generate descriptive text for training clips via VLM backends. Handles provider abstraction (Gemini, Replicate, OpenAI-compatible), prompt templates, quality scoring
- Location: `klippbok/caption/`
- Contains: `captioner.py` (orchestrates caption generation and auditing), `gemini.py` (Gemini API wrapper), `replicate.py` (Replicate API wrapper), `openai_compat.py` (local/remote OpenAI-compatible endpoints), `prompts.py` (use-case specific prompt templates), `scoring.py` (caption quality metrics without API calls)
- Depends on: `config`, provider SDKs (optional), Pydantic
- Used by: CLI (`video.__main__`), end-to-end workflows

**Triage Layer:**
- Purpose: Match video clips against user-provided reference images using CLIP embeddings. Categorize scenes into concepts. Produces manifest for filtered ingest
- Location: `klippbok/triage/`
- Contains: `triage.py` (main matching logic), `embeddings.py` (CLIP/ViT inference), `concepts.py` (reference image discovery), `filters.py` (scene-level matching aggregation), `sampler.py` (intelligent frame sampling from videos)
- Depends on: `config`, `video` (for probe/frame extraction), torch/transformers (optional)
- Used by: CLI (`video.__main__`), filtered ingest workflows

**Models & Errors:**
- `video/models.py`: VideoMetadata, ClipInfo, ClipValidation, ValidationIssue, SceneBoundary, ScanReport
- `dataset/models.py`: SamplePair, DatasetValidation, DatasetReport, OrganizeResult (relationships between files)
- `caption/models.py`: CaptionConfig, CaptionResult, AuditResult
- `triage/models.py`: ClipTriage, VideoTriageReport, ConceptReference, TriageReport
- Error classes in each module's `errors.py` for domain-specific exceptions

## Data Flow

**Typical Video Processing Pipeline (Raw Footage → Training Clips):**

1. **Discovery**: User points to raw video file or directory
2. **Probing** (`video.probe`): ffprobe extracts metadata (resolution, fps, frame count, codec)
3. **Scene Detection** (`video.scene`): PySceneDetect finds scene cuts (optional, can use triage instead)
4. **Splitting** (`video.split`): Frame-accurate cuts at scene boundaries, re-encode to target specs
5. **Output**: Normalized clips (mp4/mov/mkv), manifest.json metadata
6. **Caption** (`caption.captioner`): VLM generates .txt sidecars
7. **Extract** (`video.extract`): Reference frame PNG for I2V training
8. **Validate** (`dataset.validate`): Pair targets/captions/references, check quality, generate klippbok_manifest.json
9. **Organize** (`dataset.organize`): Copy/move to trainer-specific layout (flat or klippbok hierarchical)

**State Transitions:**
```
Raw Video → [probe] → VideoMetadata
VideoMetadata → [scene detect] → list[SceneBoundary]
Video + Scenes → [split] → list[ClipInfo]
ClipInfo files → [validate] → SamplePair + list[ValidationIssue]
SamplePair + Issues → [organize] → OrganizedSample in output directory
```

**Triage-Guided Pipeline (Raw Footage → Concept-Filtered Clips):**

1. **Reference Discovery** (`triage.concepts`): Scan user-provided `concepts/` folder for concept reference images
2. **Video Sampling** (`triage.sampler`): Extract frames strategically from source videos (first frame, distributed sampling, scene-aware)
3. **Embedding Generation** (`triage.embeddings`): CLIP encode all frames and all reference images
4. **Matching** (`triage.filters`): Similarity comparison, aggregate to scene level, apply threshold
5. **Triage Manifest**: JSON file listing (video_path, scene_timestamp, include: true/false) for scenes matching each concept
6. **Filtered Ingest** (`video.split`): `split_video_segments()` uses manifest to extract ONLY matching scenes
7. **Continue from caption/extract/validate** above

**Manifest Pattern:**
- After each stage, a manifest is written (JSON) listing processed files, metadata, issues
- Manifests are idempotent — running the same command twice should produce the same output
- Manifests serve as both documentation and input to downstream tools

## Key Abstractions

**ValidationIssue:**
- Purpose: Represent a single problem found during validation (error, warning, info)
- Location: `video/models.py` (defined), used throughout all validation layers
- Pattern: Each check adds ValidationIssue to accumulating list, never stops processing early
- Fields: code (machine-readable), severity (error/warning/info), message (human-readable), hint (how to fix), file_path

**SamplePair:**
- Purpose: Represents a single training sample — video target paired with optional caption + reference image
- Location: `dataset/models.py`
- Pattern: Immutable (frozen=True), acts as a container for all data about one training sample
- Created by: `discover.py` (file system discovery)
- Validated by: `validate.py` (adds validation issues)
- Organized by: `organize.py` (outputs to target layout)

**OrganizeLayout:**
- Purpose: Enum for output directory structure — "flat" (musubi/ai-toolkit convention) vs "klippbok" (hierarchical with signals/)
- Location: `dataset/models.py`
- Pattern: Template pattern — each layout knows how to place a SamplePair in a directory tree

**CaptionConfig + CaptionResult:**
- Purpose: Decouple captioning logic from provider details. Config holds all settings (provider, model, prompts). Result holds generated captions + metadata
- Location: `caption/models.py`
- Pattern: Strategy pattern — `captioner.py` selects provider implementation based on config.provider
- Providers: `gemini.py`, `replicate.py`, `openai_compat.py` all implement same interface

**TriageReport (VideoTriageReport, ClipTriage):**
- Purpose: Output of triage matching — structured results of clip ↔ concept matching
- Location: `triage/models.py`
- Pattern: Two variants — VideoTriageReport for raw videos (scene-level), ClipTriage for pre-split clips
- Used by: `organize_clips()` to create concept-named folders

## Entry Points

**Command: `python -m klippbok.video <subcommand>`**
- Location: `video/__main__.py`
- Responsibilities: Parse arguments, load config from YAML or use defaults, delegate to module functions, format and print results
- Subcommands:
  - `scan`: probe_directory → validate_directory → print_scan_report
  - `ingest`: probe_video → detect_scenes → split_video → normalize → [caption] → write manifest
  - `normalize`: normalize_directory (fix fps/resolution/frame_count)
  - `caption`: caption_clips (generate .txt sidecars)
  - `audit`: audit_captions (compare against VLM)
  - `score`: score_directory (caption quality metrics, no API)
  - `extract`: extract_directory (first_frame or best_frame strategy)
  - `triage`: triage_clips (CLIP matching) → [organize_clips] (optional)

**Command: `python -m klippbok.dataset <subcommand>`**
- Location: `dataset/__main__.py`
- Responsibilities: Parse arguments, load data config, orchestrate discovery/validation/organization
- Subcommands:
  - `validate`: validate_all (discover_all_datasets → validate_each_dataset → report)
  - `organize`: organize_dataset (copy/move to output layout, generate trainer configs)

**Direct Library Usage:**
```python
from klippbok.config import load_data_config
from klippbok.video import probe_video, validate_clip
from klippbok.dataset import validate_all, discover_dataset
from klippbok.caption import caption_clips
from klippbok.triage import triage_clips

config = load_data_config("klippbok_data.yaml")
report = validate_all(config)
```

## Error Handling

**Strategy:** Accumulate all issues, never fail fast (except for fatal errors like missing dependencies)

**Patterns:**

1. **FFmpeg/Dependency Errors** (`ProbeError`, `FFmpegNotFoundError`, `SceneDetectNotFoundError`): Checked once at function start, raised immediately with install instructions. Prevents confusing downstream errors

2. **Validation Issues**: Checked independently, each creates a `ValidationIssue` object appended to accumulating list. Final report shows all problems at once

3. **File System Errors** (`OrganizeError`, `DatasetValidationError`): Wrapped with context (which file, why it failed). Path-related errors include both source and target

4. **Provider Errors** (Gemini timeout, rate limit, invalid API key): Caught per-batch in captioner, recorded in `CaptionResult`, allows partial success. User can retry failed files

Example from `dataset/validate.py`:
```python
issues = list(sample.issues)  # Start with existing issues

# Check file types
ft_issue = validate_file_type(sample.target, "video")
if ft_issue is not None:
    issues.append(ft_issue)  # Add to list, continue

# Check caption content
if sample.caption is not None:
    caption_text = sample.caption.read_text()
    if len(caption_text) > config.quality.max_caption_length:
        issues.append(ValidationIssue(...))  # Add, continue

# Return with all issues collected
return sample.model_copy(update={"issues": issues})
```

## Cross-Cutting Concerns

**Logging:**
- Minimal — mostly user-facing print() via CLI __main__ modules
- Some modules use warnings.warn() for non-critical issues (e.g., "non-standard FPS")
- Error context printed to stderr before exit

**Validation:**
- Two layers: (1) Pydantic validation at load time (config schema), (2) Runtime validation at execution time (file checks, metadata checks)
- All runtime validation uses ValidationIssue pattern — accumulate and report

**Authentication:**
- Config layer supports environment variable interpolation for API keys
- VLM backends check for required env vars (GEMINI_API_KEY, REPLICATE_API_TOKEN) at initialization
- Missing API keys raise clear errors with setup instructions

**Path Resolution:**
- All paths normalized to absolute paths immediately after loading config
- Relative paths in YAML are resolved relative to config file directory
- Symlinks followed automatically by Path.resolve()

**Pydantic Models:**
- All models use v2 syntax (modern Python 3.10+ type hints)
- Config uses frozen=True (immutable) for models representing facts (ValidationIssue, SamplePair, VideoMetadata)
- Mutable configs use ConfigDict(validate_assignment=True) to catch errors early
- Field validators used extensively for domain-specific constraints (fps must be > 0, use_case in enum, etc.)

---

*Architecture analysis: 2026-02-27*
