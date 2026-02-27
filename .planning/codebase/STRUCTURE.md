# Codebase Structure

**Analysis Date:** 2026-02-27

## Directory Layout

```
klippbok-main/
├── klippbok/                    # Main package (domain modules)
│   ├── __init__.py
│   ├── config/                  # Configuration schema and loading
│   │   ├── __init__.py
│   │   ├── data_schema.py       # Pydantic models for klippbok_data.yaml
│   │   ├── loader.py            # YAML file loading and validation
│   │   └── defaults.py          # Hardcoded constants and valid ranges
│   ├── video/                   # Video processing (probe, split, normalize, extract, validate)
│   │   ├── __init__.py
│   │   ├── __main__.py          # CLI entry point (scan, ingest, normalize, caption, etc.)
│   │   ├── _ffmpeg.py           # FFmpeg auto-discovery (Windows compatibility)
│   │   ├── models.py            # VideoMetadata, ClipInfo, ValidationIssue, ScanReport
│   │   ├── errors.py            # Domain errors (ProbeError, FFmpegNotFoundError, etc.)
│   │   ├── probe.py             # ffprobe wrapper — extract video metadata
│   │   ├── scene.py             # PySceneDetect wrapper — find scene cuts
│   │   ├── split.py             # FFmpeg splitting and re-encoding
│   │   ├── extract.py           # Extract reference frames from clips
│   │   ├── extract_models.py    # ExtractionConfig, ExtractionStrategy
│   │   ├── frames.py            # Frame extraction utilities
│   │   ├── image_quality.py     # Blur, exposure, sharpness detection
│   │   └── validate.py          # Clip quality validation (metadata checks, scene coherence)
│   ├── dataset/                 # Dataset discovery, validation, organization
│   │   ├── __init__.py
│   │   ├── __main__.py          # CLI entry point (validate, organize)
│   │   ├── models.py            # SamplePair, DatasetValidation, DatasetReport, OrganizeResult
│   │   ├── errors.py            # Domain errors (DatasetValidationError, OrganizeError)
│   │   ├── discover.py          # File discovery and pairing (targets ↔ captions ↔ references)
│   │   ├── validate.py          # Core validation orchestration
│   │   ├── quality.py           # Dataset-level quality checks (captions, reference images)
│   │   ├── organize.py          # Output organization (flat vs. klippbok layout)
│   │   ├── bucketing.py         # Group samples by characteristics for balanced training
│   │   ├── trainers.py          # Trainer-specific config generation (musubi, aitoolkit)
│   │   ├── manifest.py          # JSON manifest generation and reading
│   │   └── report.py            # Human-readable result formatting
│   ├── caption/                 # VLM captioning (Gemini, Replicate, Ollama)
│   │   ├── __init__.py
│   │   ├── models.py            # CaptionConfig, CaptionResult, AuditResult
│   │   ├── base.py              # CaptionBackend abstract base class
│   │   ├── captioner.py         # Main caption_clips() and audit_captions() functions
│   │   ├── gemini.py            # Google Gemini API wrapper
│   │   ├── replicate.py         # Replicate API wrapper
│   │   ├── openai_compat.py     # OpenAI-compatible backend (Ollama, vLLM, etc.)
│   │   ├── prompts.py           # Use-case specific prompt templates
│   │   └── scoring.py           # Caption quality metrics (no API calls)
│   └── triage/                  # CLIP-based clip categorization
│       ├── __init__.py
│       ├── models.py            # ClipMatch, VideoTriageReport, ClipTriage, TriageReport
│       ├── triage.py            # Main triage_clips() and organize_clips() functions
│       ├── embeddings.py        # CLIP/ViT inference and caching
│       ├── concepts.py          # Reference image discovery and organization
│       ├── filters.py           # Scene-level matching aggregation
│       └── sampler.py           # Intelligent frame sampling from videos
├── tests/                       # Test suite
│   ├── conftest.py              # Pytest fixtures and global test setup
│   ├── fixtures/                # Test data (sample videos, images, config files)
│   ├── test_*.py                # Test modules (one per major component)
│   └── sample_character/        # Reference data for character triage tests
├── docs/                        # User-facing documentation
│   ├── PIPELINES.md             # 6 supported processing pipelines
│   ├── COMMANDS.md              # Full command reference with examples
│   ├── WALKTHROUGH.md           # Step-by-step guides for each provider
│   ├── assets/                  # Screenshots, diagrams
│   └── debug/                   # Debugging guides
├── examples/                    # Example usage scripts and configs
├── .planning/                   # GSD planning artifacts
│   └── codebase/                # This directory — architecture docs
├── .claude/                     # Claude Code configuration
│   ├── commands/                # Custom slash commands
│   ├── hooks/                   # Enforcement scripts (secret scanning, etc.)
│   ├── rules/                   # Project-specific rules
│   └── skills/                  # Reusable expertise modules
├── project-docs/                # Project-level documentation
│   ├── ARCHITECTURE.md          # Higher-level system design
│   ├── INFRASTRUCTURE.md        # Deployment details
│   └── DECISIONS.md             # Why we chose X over Y
├── pyproject.toml               # Package metadata, dependencies, optional feature groups
├── CLAUDE.md                    # Team-wide project instructions
├── CLAUDE.local.md              # Personal workflow preferences (gitignored)
└── README.md                    # User-facing overview
```

## Directory Purposes

**`klippbok/`**
- Purpose: Main package containing all domain logic
- Contains: Five module packages (config, video, dataset, caption, triage) + support modules
- Key files: Each module has `__init__.py` (exports public API), `__main__.py` (CLI entry for video/dataset), `models.py` (data structures), `errors.py` (exceptions)

**`klippbok/config/`**
- Purpose: Configuration schema definition and loading
- Contains: Pydantic models describing klippbok_data.yaml structure, YAML parser, default values
- Key files:
  - `data_schema.py`: KlippbokDataConfig, DatasetIdentityConfig, VideoConfig, QualityConfig, BucketingConfig (all Pydantic BaseModel)
  - `loader.py`: load_data_config() function, handles path resolution and YAML parsing
  - `defaults.py`: Constants like WAN_TRAINING_FPS=16, VALID_RESOLUTIONS, UMT5_MAX_TOKENS

**`klippbok/video/`**
- Purpose: Video file processing — metadata extraction, scene detection, splitting, normalization, validation
- Contains: 13 Python files implementing video pipeline stages
- Key files:
  - `probe.py`: probe_video(), probe_directory() — ffprobe wrapper
  - `scene.py`: detect_scenes() — PySceneDetect wrapper
  - `split.py`: split_video_at_scenes(), split_video_segments(), normalize_directory() — ffmpeg wrapper for cutting and re-encoding
  - `extract.py`: extract_directory(), extract_from_selections() — reference frame extraction
  - `validate.py`: validate_directory(), validate_clip() — quality checks and scene coherence
  - `__main__.py`: CLI for all video commands (scan, ingest, normalize, caption, audit, score, extract, triage)

**`klippbok/dataset/`**
- Purpose: High-level dataset operations — discovery, validation, organization, manifest generation
- Contains: 12 Python files for dataset-level concerns
- Key files:
  - `discover.py`: discover_dataset(), pair_samples() — filesystem crawling and file pairing
  - `validate.py`: validate_all(), validate_sample() — core validation orchestration
  - `organize.py`: organize_dataset() — output directory structure creation
  - `bucketing.py`: preview_bucketing() — sample grouping for balanced training
  - `trainers.py`: Trainer-specific config generation (musubi, aitoolkit)
  - `quality.py`: Caption-level and reference-image-level quality checks
  - `manifest.py`: build_manifest(), write_manifest(), read_manifest() — JSON state files
  - `__main__.py`: CLI for dataset commands (validate, organize)

**`klippbok/caption/`**
- Purpose: VLM-powered caption generation and quality assessment
- Contains: 9 Python files for captioning workflow
- Key files:
  - `captioner.py`: caption_clips(), audit_captions() — main entry points
  - `gemini.py`: Google Gemini API integration
  - `replicate.py`: Replicate API integration
  - `openai_compat.py`: OpenAI-compatible endpoints (Ollama, vLLM, etc.)
  - `prompts.py`: Use-case-specific prompt templates (character, style, motion, object)
  - `scoring.py`: score_directory(), score_caption() — local caption quality metrics
  - `base.py`: CaptionBackend abstract base class
  - `models.py`: CaptionConfig, CaptionResult, AuditResult

**`klippbok/triage/`**
- Purpose: CLIP-based scene matching and categorization
- Contains: 7 Python files for triage workflow
- Key files:
  - `triage.py`: triage_clips(), triage_videos(), organize_clips() — main entry points
  - `embeddings.py`: CLIP model loading, inference, embedding caching
  - `concepts.py`: discover_concepts() — reference image discovery
  - `sampler.py`: Frame sampling strategies (first frame, best frame, distributed)
  - `filters.py`: Aggregate frame-level matches to scene level, apply thresholds
  - `models.py`: ClipMatch, VideoTriageReport, ClipTriage, TriageReport

**`tests/`**
- Purpose: Test suite for all modules
- Contains: 30+ test files (one per module), test fixtures, sample data
- Key files:
  - `conftest.py`: Pytest configuration, shared fixtures
  - `test_data_config.py`: Config schema and loading tests
  - `test_dataset_discover.py`, `test_dataset_validate.py`, `test_dataset_organize.py`: Dataset module tests
  - `test_video_*.py`: Video module tests (probe, scene, split, extract, validate)
  - `test_caption_*.py`: Captioning tests
  - `test_gemini_backend.py`, `test_replicate_backend.py`: Provider-specific tests
  - `fixtures/`: Sample video files, images, config files

**`docs/`**
- Purpose: User-facing documentation
- Contains: Guides, command reference, walkthrough tutorials
- Key files:
  - `PIPELINES.md`: Six supported processing workflows
  - `COMMANDS.md`: Full command reference with all flags and examples
  - `WALKTHROUGH.md`: Step-by-step setup for each VLM provider
  - `debug/`: Troubleshooting guides

**`.planning/codebase/`**
- Purpose: GSD planning artifacts (this directory)
- Contains: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, STACK.md, INTEGRATIONS.md, CONCERNS.md

## Key File Locations

**Entry Points:**
- `klippbok/video/__main__.py`: `python -m klippbok.video <command>` (scan, ingest, normalize, caption, audit, score, extract, triage)
- `klippbok/dataset/__main__.py`: `python -m klippbok.dataset <command>` (validate, organize)

**Configuration:**
- `klippbok/config/data_schema.py`: Pydantic schema for klippbok_data.yaml
- `klippbok/config/defaults.py`: Hardcoded constants (WAN_TRAINING_FPS, VALID_RESOLUTIONS, etc.)
- `pyproject.toml`: Package metadata, dependencies, optional feature groups [video], [caption], [dataset], [triage]

**Core Logic:**
- Video pipeline: `klippbok/video/probe.py`, `scene.py`, `split.py`, `extract.py`, `validate.py`
- Dataset pipeline: `klippbok/dataset/discover.py`, `validate.py`, `organize.py`
- Captioning: `klippbok/caption/captioner.py` (delegates to `gemini.py`, `replicate.py`, `openai_compat.py`)
- Triage: `klippbok/triage/triage.py` (uses `embeddings.py`, `concepts.py`, `sampler.py`)

**Testing:**
- `tests/conftest.py`: Pytest fixtures (tmp_path, sample_video, sample_image, etc.)
- `tests/test_data_config.py`: Config loading tests
- `tests/test_dataset_*.py`: Dataset module tests
- `tests/test_video_*.py`: Video module tests
- `tests/fixtures/`: Sample data (test videos, images, config files)

## Naming Conventions

**Files:**
- Module packages: lowercase (`config/`, `video/`, `dataset/`, `caption/`, `triage/`)
- Python files: lowercase_with_underscores (`data_schema.py`, `extract_models.py`)
- Test files: `test_<module>.py` (e.g., `test_dataset_validate.py`)
- Config files: `klippbok_data.yaml` (in user datasets), `klippbok_manifest.json` (output)

**Directories:**
- Concept folders (user-created): lowercase matching concept type (e.g., `concepts/character/`, `concepts/style/`)
- Dataset folders: user-named (e.g., `video_clips/`, `training/`)
- Output folders: user-specified via `--output` flag

**Python Naming:**
- Classes: PascalCase (VideoMetadata, SamplePair, CaptionConfig)
- Functions: snake_case (probe_video(), validate_sample(), organize_dataset())
- Constants: UPPER_CASE (WAN_TRAINING_FPS, VALID_RESOLUTIONS)
- Private helpers: _leading_underscore (_check_ffprobe(), _parse_frame_rate())

## Where to Add New Code

**New Video Processing Stage (e.g., deshake, stabilization):**
- Implementation: `klippbok/video/new_stage.py` (follow probe.py/split.py pattern)
- Models: Add to `klippbok/video/models.py` if needed (e.g., StabilizationResult)
- Integration: Add import to `klippbok/video/__init__.py`, add CLI subcommand to `klippbok/video/__main__.py`
- Tests: Create `tests/test_video_new_stage.py` with fixtures from conftest

**New Caption Provider (e.g., Claude API, Azure Vision):**
- Implementation: `klippbok/caption/new_provider.py` (inherit from `base.py` CaptionBackend)
- Integration: Import and register in `captioner.py` provider selection logic
- Config: Add provider option to `caption/models.py` CaptionConfig validation
- Tests: Create `tests/test_new_provider.py` with mock API responses
- Docs: Update `docs/COMMANDS.md` and `docs/WALKTHROUGH.md`

**New Quality Metric:**
- Implementation: Add function to `klippbok/video/image_quality.py` (for image) or `klippbok/dataset/quality.py` (for dataset-level)
- Integration: Call from `klippbok/video/validate.py` or `klippbok/dataset/validate.py`
- Config: Add threshold parameter to `klippbok/config/data_schema.py` QualityConfig
- Tests: Add test case to `tests/test_image_quality.py` or `tests/test_dataset_quality.py`

**New Trainer Output Format:**
- Implementation: Add function to `klippbok/dataset/trainers.py` (format_for_trainer_name())
- Integration: Import in `organize.py`, call from organize_dataset()
- Config: Add trainer name to valid choices in `klippbok/dataset/__main__.py` argument parser
- Tests: Add test to `tests/test_dataset_trainers.py`

**New Utility Module (shared helpers):**
- Location: Add to appropriate existing module (don't create new top-level module)
  - Frame utilities: `klippbok/video/frames.py`
  - Path/file utilities: `klippbok/dataset/discover.py` (file discovery already here)
  - Encoding utilities: `klippbok/video/split.py`

## Special Directories

**`tests/fixtures/`**
- Purpose: Sample data for testing
- Generated: No (checked into git)
- Committed: Yes
- Contains: Sample video files, images, YAML config templates, JSON manifests
- Subdirectories:
  - `sample_character/`: Reference images and test videos for character triage tests

**`klippbok/` (package)**
- Purpose: Main application code
- Generated: No
- Committed: Yes
- Structure: Five domain modules (config, video, dataset, caption, triage)

**`.planning/codebase/`**
- Purpose: GSD codebase analysis documents
- Generated: Yes (by GSD mapping commands)
- Committed: Yes
- Contains: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, STACK.md, INTEGRATIONS.md, CONCERNS.md

**`.claude/`**
- Purpose: Claude Code configuration
- Generated: Partially (some checked in, some user-added)
- Committed: Yes
- Contains: Custom commands, enforcement hooks, rules, skills

**`project-docs/`**
- Purpose: Team documentation (not user-facing)
- Generated: No
- Committed: Yes
- Contains: System design decisions, infrastructure notes, architecture rationale

---

*Structure analysis: 2026-02-27*
