# Technology Stack

**Analysis Date:** 2026-02-27

## Languages

**Primary:**
- Python 3.10+ - Core application language for video processing, dataset curation, and ML pipelines

**Secondary:**
- Shell (bash) - ffmpeg/ffprobe wrapper scripts and installation discovery

## Runtime

**Environment:**
- Python 3.10, 3.11, 3.12 (specified in `pyproject.toml`)
- Platform: Linux, macOS, Windows (with ffmpeg discovery)

**Package Manager:**
- pip (PyPI)
- Lockfile: No lock file present (direct dependency specification in `pyproject.toml`)

## Frameworks

**Core:**
- Pydantic v2 - Data validation and configuration models across all modules (`klippbok/config/`, `klippbok/caption/`, `klippbok/dataset/`, `klippbok/triage/`)
- PyYAML 6.0+ - YAML config parsing (`klippbok/config/loader.py`)

**Testing:**
- pytest 7.0+ - Test runner (`pyproject.toml`)
- pytest-tmp-files 0.0.2+ - Temporary file fixtures

**Build/Dev:**
- hatchling - Build backend

## Key Dependencies

**Video Processing (Optional - `[video]` extra):**
- scenedetect[opencv] 0.6+ - Scene detection via temporal discontinuity (`klippbok/video/scene.py`)
  - **Why it matters:** Essential for splitting video into temporally coherent clips for LoRA training
  - Provides: `ContentDetector`, `SceneManager` for automatic cut detection
- ffmpeg/ffprobe - External system dependency for frame extraction, video probing, clip splitting
  - **Why it matters:** Core video I/O operations (no Python wrapper — called directly via subprocess)
  - Discovery: Auto-detection of WinGet installations via `klippbok/video/_ffmpeg.py`

**AI Captioning (Optional - `[caption]` extra):**
- google-genai 1.0+ - Google Gemini API client (`klippbok/caption/gemini.py`)
  - Handles video upload, polling, cleanup via Gemini Files API
- requests 2.20+ - HTTP client for Replicate and OpenAI-compatible APIs
  - Used by: `klippbok/caption/replicate.py`, `klippbok/caption/openai_compat.py`
  - **Why it matters:** Raw HTTP implementation avoids additional SDK dependencies; supports multiple providers

**Dataset Management (Optional - `[dataset]` extra):**
- filetype 1.2+ - Magic-byte file type validation (`klippbok/dataset/discover.py`)
  - **Why it matters:** Validates video/image files beyond extension checking
  - Graceful degradation: Falls back to extension-based classification if not installed
- rich 13.0+ - Terminal UI and formatted output (`klippbok/dataset/report.py`)
  - Provides: Tables, panels, colored console output for quality reports

**Embedding & Triage (Optional - `[triage]` extra):**
- torch 2.0+ - PyTorch for CLIP inference (`klippbok/triage/embeddings.py`)
  - Heavy dependency with lazy imports at runtime
- transformers 4.30+ - HuggingFace Transformers for CLIP model loading
  - Model: `openai/clip-vit-base-patch32` (default)
  - Lazy imports with helpful error messages if missing
- Pillow 9.0+ - Image processing support for triage embeddings

**Core Dependencies (Always Installed):**
- pydantic 2.0+ - Mandatory for all data schemas
- pyyaml 6.0+ - YAML config file loading

## Configuration

**Environment Variables:**
- `GEMINI_API_KEY` - Google Gemini API key for captioning (required if provider="gemini")
- `REPLICATE_API_TOKEN` - Replicate API token for captioning (required if provider="replicate")
- Both are optional; checked at runtime in caption backends

**Config Format:**
- YAML-based configuration (`klippbok_data.yaml`)
- Loaded and validated by `klippbok/config/loader.py`
- Pydantic models in `klippbok/config/data_schema.py`
- Backwards compatibility with shorthand `dataset.path` syntax

**Build Configuration:**
- `pyproject.toml` - Single source of truth for dependencies, metadata, pytest config
- No additional build files (setup.py, setup.cfg)

## Platform Requirements

**Development:**
- Python 3.10+ installed
- ffmpeg and ffprobe on PATH (auto-discovered on Windows)
- Optional: GPU support for triage module (CUDA recommended for torch)

**Production:**
- All optional dependencies can be installed selectively via extras: `pip install klippbok[video,caption,dataset,triage]` or `pip install klippbok[all]`
- Deployment target: Any platform with Python 3.10+ and ffmpeg

## External System Dependencies

**Critical:**
- ffmpeg 4.0+ - Video frame extraction, splitting, probing
  - Required for: Video processing pipeline
  - No Python fallback — direct subprocess calls
  - Auto-discovered on Windows via `klippbok/video/_ffmpeg.py`

**Conditional:**
- CUDA (NVIDIA GPU drivers) - Optional but recommended for torch-based triage module
- OpenAI-compatible API server (Ollama, vLLM, LM Studio) - Required if using `provider="openai"` for captioning

## Dependency Management Strategy

**Optional Grouping:**
- All heavy ML dependencies (torch, transformers, scenedetect[opencv]) are optional
- Modular imports with runtime checks and helpful error messages
- Examples from codebase:
  - `klippbok/video/scene.py`: Lazy import of scenedetect with custom error handler
  - `klippbok/triage/embeddings.py`: Lazy torch/transformers with GPU setup guidance
  - `klippbok/caption/captioner.py`: Conditional import based on provider choice

**No Monolithic Build:**
- Each module imports its dependencies only when used
- Enables lightweight CLI tools (dataset discovery) without installing video/ML dependencies

---

*Stack analysis: 2026-02-27*
