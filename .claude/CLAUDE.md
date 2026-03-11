# klippbok

Video dataset curation, preparation, and annotation for LoRA training.

## Quick Commands

```bash
pytest                    # Run all tests
pytest -x                 # Stop on first failure
pytest -k "pattern"       # Run matching tests
pip install -e ".[dev]"   # Install with dev dependencies
pip install -e ".[all]"   # Install all optional dependencies
cd frontend && npx vite build   # Build frontend (pnpm not available, use npx)
```

## Server

```bash
.venv/Scripts/python.exe -m klippbok.api --port 9000   # MUST use .venv Python
```

## IMPORTANT: Frontend Build

The server serves from `klippbok/api/static/`, NOT `frontend/dist/`. TWO STEPS required:
1. **Build**: `cd frontend && npx vite build`
2. **Copy**: `cd <project-root> && rm -rf klippbok/api/static/* && cp -r frontend/dist/* klippbok/api/static/`
After copy, restart the server. Building alone is NOT enough.

## Frontend Stack

React 19, TypeScript 5.9, Vite 7, Zustand 5, TanStack Query 5, Playwright (E2E)

```bash
cd frontend && npx playwright test           # Run E2E tests
cd frontend && npx playwright test --headed  # Run E2E headed
```

## Prerequisites

- Python 3.10+
- pip
- ffmpeg (for video processing)

## Architecture

```
klippbok/
├── api/        # FastAPI server, routers, static file serving
├── caption/    # AI-powered video captioning (Gemini, OpenAI, Replicate)
├── config/     # YAML data schema, defaults, config loading
├── dataset/    # Dataset discovery, validation, bucketing, manifest generation
├── image/      # Autocrop, dedup, quality scoring, bucketing, probe
├── services/   # Business logic layer — bridges API routers to domain modules
├── triage/     # Embedding-based scene triage and concept filtering
└── video/      # Video probing, splitting, frame extraction, scene detection
```

## API Routers

All endpoints under `/api/v1/`. Routers in `klippbok/api/routers/`:
`images`, `video`, `captions`, `crop`, `upscale`, `triage`, `cleanup`, `browse`, `import_`, `settings`

## Key Patterns

- Pydantic v2 models for data validation throughout
- YAML-based configuration (`klippbok_data.yaml`)
- Optional dependency groups: video, caption, dataset, triage, image
- CLI entry via `__main__.py` modules (dataset, video)
- `_image_id()` = SHA256[:16] of relative path (not content) — used in images.py, crop.py, caption_service.py
- Thumbnail cache at `.klippbok/thumbnails/{image_id}.jpg`
- Processing temp dirs go in project's `.klippbok/`, NOT system temp
