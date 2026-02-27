# Klippbok v2

## What This Is

A model-agnostic dataset preparation tool for LoRA training, supporting both image and video workflows. Extends the original klippbok (video-only, WAN LoRAs) into a unified tool that handles SD1.5, SDXL, Flux, Qwen, and other diffusion models. Includes a full-featured web GUI (FastAPI + React) for managing the entire pipeline from import through export.

Internal-use tool for a single developer/user.

## Core Value

Users can take raw images or video of any size/resolution/quality and produce correctly bucketed, captioned, training-ready datasets for any supported diffusion model — through an intuitive web interface.

## Requirements

### Validated

- ✓ Video probing via ffprobe (metadata extraction: resolution, fps, codec, frame count) — existing
- ✓ Scene detection via PySceneDetect (automatic cut detection in source video) — existing
- ✓ Video splitting (frame-accurate cutting at scene boundaries, re-encoding to target specs) — existing
- ✓ Reference frame extraction (first_frame or best_frame strategy for I2V training) — existing
- ✓ AI-powered captioning via multiple providers (Gemini, Replicate, OpenAI-compatible) — existing
- ✓ Caption quality scoring (offline metrics without API calls) — existing
- ✓ CLIP-based triage (embedding similarity matching of clips against concept references) — existing
- ✓ Dataset discovery and validation (file pairing, completeness checks, quality reports) — existing
- ✓ Resolution bucketing (group samples by characteristics for training) — existing
- ✓ Dataset organization (output to flat or hierarchical layouts for different trainers) — existing
- ✓ Manifest-driven state tracking (JSON manifests for pipeline communication) — existing
- ✓ YAML-based configuration with Pydantic v2 validation — existing
- ✓ Optional dependency groups (video, caption, dataset, triage) — existing
- ✓ Accumulative validation pattern (collect all issues, never fail fast) — existing

### Active

- [ ] Image import and processing pipeline (load images of any size/resolution/quality)
- [ ] Interactive image cropping with snap-to-bucket-ratio (like malcolmrey's dataset cutter)
- [ ] Auto-crop with subject detection (AI detects subject, crops to best resolution bucket)
- [ ] Resolution-bounded bucket selection (512 for SD1.5, 768, 1024 for SDXL/Flux)
- [ ] Upscale quality warning (visual indicator when crop requires upscaling)
- [ ] Model-aware captioning defaults (booru-style tags for SD1.5, natural language for Flux/SDXL) with user override
- [ ] Booru-style tag generation (danbooru tag format for SD1.5 training)
- [ ] Multi-model target configuration (select target model, get appropriate defaults)
- [ ] Web GUI — full pipeline control (FastAPI backend + React frontend)
- [ ] GUI: Image import with drag-and-drop upload
- [ ] GUI: Interactive crop editor with resolution snap, rotation, zoom
- [ ] GUI: Batch image gallery view with per-image crop regions
- [ ] GUI: Caption editor (view, edit, regenerate captions per image)
- [ ] GUI: Dataset export (download cropped + captioned dataset as archive)
- [ ] GUI: Video pipeline integration (existing video workflows accessible from GUI)
- [ ] GUI: Configuration management (target model, bucket sizes, caption settings)
- [ ] Unified SamplePair model supporting both image and video targets
- [ ] Image-specific validation (resolution checks, format validation, quality metrics)
- [ ] Extend existing CLIP triage to work with standalone images (not just video frames)

### Out of Scope

- Mobile app — web-first, internal tool only
- Real-time training integration — this is dataset preparation, not training
- Cloud deployment / multi-user auth — single developer, runs locally
- Video editing features (trimming, color grading) — only splitting at scene boundaries
- Image generation — this tool prepares training data, not generates images
- Automatic model training pipeline — export dataset, train separately

## Context

**Existing codebase:** klippbok is a mature Python pipeline for video dataset curation. It has a modular architecture with 5 domain modules (video, config, dataset, caption, triage), CLI entry points, and strong Pydantic v2 patterns. The codebase is well-structured but has known tech debt (silent error swallowing, missing progress bars, no resumable pipelines).

**This is a fork:** New project forked from klippbok. All existing capabilities are preserved and extended. The fork adds image support alongside video, and wraps everything in a web GUI.

**Target models:**
- SD1.5 (primary focus) — 512x512 base, booru-style tags, bucketing within 262,144 pixel budget
- SDXL — 1024x1024 base, natural language captions
- Flux — 1024x1024 base, natural language captions
- Qwen — TBD, adaptable architecture
- Architecture designed to add new models via configuration, not code changes

**Reference tool:** malcolmrey's [dataset-preparation](https://huggingface.co/spaces/malcolmrey/dataset-preparation) HuggingFace Space — a static frontend tool with interactive image cropping, bucket size selection (512/768/1024), non-square toggle, snap-to-ratio on resize, rotation controls, zoom slider, upscale quality warning (green/red resolution text), and batch download. Our tool will replicate and extend this functionality within the full klippbok pipeline.

**Captioning approach per model:**
- SD1.5: Booru-style tags (danbooru format), no natural language
- SDXL/Flux/Qwen: Natural language descriptions via VLM providers
- User can override defaults per dataset

## Constraints

- **Tech stack (backend)**: Python 3.10+, FastAPI, existing klippbok modules — must integrate with current Pydantic v2 patterns
- **Tech stack (frontend)**: React (TypeScript) — chosen for full control over crop editor UX
- **Tech stack (image processing)**: Pillow for image I/O, potentially OpenCV for subject detection in auto-crop
- **Dependencies**: Keep optional dependency group pattern — GUI deps should be a separate `[gui]` extra
- **Single user**: No auth, no multi-tenancy, no cloud deployment considerations
- **Existing patterns**: Must preserve manifest-driven state tracking, accumulative validation, and modular architecture

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| FastAPI + React for GUI | Full control over crop editor UX; Gradio too limiting for interactive canvas operations | — Pending |
| Fork rather than extend in-place | Clean separation, freedom to restructure without breaking existing klippbok users | — Pending |
| Model-aware defaults with user override | Different models need different captioning; defaults reduce friction, override preserves flexibility | — Pending |
| Both auto-crop and interactive crop | Auto-crop for bulk processing speed, interactive for fine-tuning — covers both workflows | — Pending |
| Booru tags as first-class caption format | SD1.5 is primary focus and requires danbooru-style tags, not natural language | — Pending |

---
*Last updated: 2026-02-27 after initialization*
