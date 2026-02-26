# klippbok

Video dataset curation, preparation, and annotation for LoRA training.

## Quick Commands

```bash
pytest                    # Run all tests
pytest -x                 # Stop on first failure
pytest -k "pattern"       # Run matching tests
pip install -e ".[dev]"   # Install with dev dependencies
pip install -e ".[all]"   # Install all optional dependencies
```

## Prerequisites

- Python 3.10+
- pip
- ffmpeg (for video processing)

## Architecture

```
klippbok/
├── caption/    # AI-powered video captioning (Gemini, OpenAI, Replicate)
├── config/     # YAML data schema, defaults, config loading
├── dataset/    # Dataset discovery, validation, bucketing, manifest generation
├── triage/     # Embedding-based scene triage and concept filtering
└── video/      # Video probing, splitting, frame extraction, scene detection
```

## Key Patterns

- Pydantic v2 models for data validation throughout
- YAML-based configuration (`klippbok_data.yaml`)
- Optional dependency groups: video, caption, dataset, triage
- CLI entry via `__main__.py` modules (dataset, video)
