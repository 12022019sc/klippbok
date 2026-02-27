# Image & SD1.5 LoRA Support — Feasibility Analysis

**Date:** 2026-02-26
**Scope:** What it would take to extend klippbok to support image-based LoRA training for models like SD1.5

---

## Executive Summary

Klippbok is tightly coupled to Wan video models in specific ways, but the core architecture is surprisingly generic. Captioning, CLIP-based triage, dataset discovery, bucketing, and validation all have foundations that work with images. The main blockers are the 4n+1 frame count constraint, the video-only config schema, and the Wan-specific trainer config generators.

**Recommended approach:** Extend klippbok with conditional logic rather than forking.

---

## What Already Works with Images

| Component | Location | Why It Works |
|-----------|----------|--------------|
| Caption backends | `caption/base.py` | `VLMBackend` ABC has both `caption_video()` and `caption_image()` |
| Dataset discovery | `dataset/discover.py` | Recognizes `IMAGE_EXTENSIONS` (.png, .jpg, .webp, etc.), pairs by filename stem |
| Dataset validation | `dataset/validate.py` | Checks completeness generically (caption present? reference present?) |
| Bucketing | `dataset/bucketing.py` | Works with `(width, height, frame_count)` — images are just `frame_count=1` |
| CLIP triage | `triage/embeddings.py` | `encode_images()` works on any PIL Image regardless of source |
| Image quality | `video/image_quality.py` | Blur/exposure/duplicate detection works on individual images |
| Reference extraction | `video/extract.py` | `copy_image_as_reference()` already handles images |
| Dataset organization | `dataset/organize.py` | Directory layout is media-agnostic |

---

## Blockers & Required Changes

### 1. Wan's 4n+1 Frame Count Constraint — HIGH effort

The biggest coupling. Wan's 3D causal VAE requires frame counts of {1, 5, 9, 13, ...81}. Baked into:

| File | Function/Field | What It Does |
|------|---------------|--------------|
| `config/defaults.py` | `valid_frame_counts()` | Generates the {1, 5, 9, ...} set |
| `config/data_schema.py` | `VideoConfig.validate_frame_count()` | Rejects non-4n+1 values |
| `config/data_schema.py` | `VideoConfig.frame_count` | Field docs mention Wan VAE |
| `video/validate.py` | `nearest_valid_frame_count()` | Trims clips to 4n+1 |
| `video/validate.py` | `validate_clip()` | Enforces 4n+1 validation |

**Fix:** Make frame count validation conditional per model. For images, skip entirely.

### 2. Config Schema is Video-Only — MODERATE effort

`VideoConfig` has fps, frame_count, max_frames — all meaningless for images.

**Options:**
- Create an `ImageConfig` alongside `VideoConfig` in `config/data_schema.py`
- Refactor to a generic `MediaConfig` with optional video-only fields

**SD1.5 would need:** resolution tiers (512, 768, 1024), aspect ratio handling, color space validation.

### 3. Trainer Config Generators — MODERATE effort

`dataset/trainers.py` generates configs for musubi-tuner and ai-toolkit — both Wan-specific.

**For SD1.5:** Need new generators for kohya/sd-scripts config format, or other SD1.5-compatible trainers.

### 4. Discovery Hardcodes Video as "Target" — LOW effort

In `discover.py`, the targets directory scan only accepts `VIDEO_EXTENSIONS`:

```python
if f.suffix.lower() in VIDEO_EXTENSIONS:  # ← needs image extensions too
```

**Fix:** Add `IMAGE_EXTENSIONS` to target discovery, or make it configurable.

### 5. Video Probe/Validate Assume Video — MODERATE effort

- `video/probe.py` uses ffprobe for metadata — images need PIL/Pillow-based extraction
- `video/validate.py` checks fps/duration/frame_count — needs an image-specific validation path

### 6. Triage Frame Sampling — LOW-MODERATE effort

`triage/sampler.py` samples N frames from video per scene. For images, this becomes "select N images per folder" — simpler logic but needs a new code path.

---

## What Can Be Skipped Entirely

These modules are video-only and don't apply to images:

| Module | Purpose | For Images |
|--------|---------|------------|
| `video/scene.py` | Scene detection via ffmpeg | N/A — images don't have scenes |
| `video/frames.py` | Frame extraction from video | N/A — images are already frames |
| Motion quality checks | Optical flow analysis | N/A — no motion in still images |

---

## Hardcoded Model References

| Reference | Location | Impact |
|-----------|----------|--------|
| 4n+1 frame count | config, validators | Core validation — must be made conditional |
| 16 FPS default (`WAN_TRAINING_FPS`) | `config/defaults.py` | Just a default, easily overridden |
| 480/720p resolutions | `config/defaults.py`, `dataset/trainers.py` | Parametrizable |
| UMT5 512 token limit | `config/defaults.py` | Caption encoder assumption, overridable |
| Wan architecture docs | Comments/docstrings throughout | Non-functional, can rewrite |

---

## Implementation Plan

### Phase 1: Image Discovery & Pairing (Low effort)
- Update `discover.py` to treat images as valid targets
- Handle mixed video/image datasets (or separate modes)

### Phase 2: Config Schema (Moderate effort)
- Make `VideoConfig.frame_count` optional or create `ImageConfig`
- Decouple frame_count from bucketing
- Add image-specific resolution tiers
- Make 4n+1 validation conditional (skip for images)

### Phase 3: Image Metadata & Validation (Moderate effort)
- Add PIL-based image probe (resolution, format, color space)
- Skip video-only validation checks for image inputs
- Keep blur/exposure/duplicate checks (already work)

### Phase 4: Triage for Images (Low effort)
- Add `triage_images()` alongside `triage_clips()`
- Reuse all CLIP embedding/matching logic
- Route based on input file type

### Phase 5: Caption Pipeline (Low effort)
- Wire `caption_image()` into the batch pipeline
- Same prompt system works for both (use_case, anchor_word, etc.)

### Phase 6: SD1.5 Trainer Config (Moderate effort)
- Implement kohya/sd-scripts config generator
- Register in trainer registry pattern
- Document new trainer type

### Phase 7: CLI & Documentation (Low effort)
- Update CLI entry points to accept image mode
- Update README and docs
- Add example YAML configs for SD1.5

---

## Summary Table

| Module | Video-Coupled? | Image-Ready? | Effort to Adapt |
|--------|----------------|--------------|-----------------|
| `config/` | HIGH (4n+1, FPS) | No | MODERATE |
| `dataset/discover.py` | No | YES | LOW |
| `dataset/validate.py` | No | YES | NONE |
| `dataset/bucketing.py` | Partial | MOSTLY | LOW |
| `dataset/organize.py` | No | YES | NONE |
| `dataset/trainers.py` | HIGH (Wan-specific) | No | HIGH |
| `video/probe.py` | ONLY VIDEO | No | HIGH |
| `video/validate.py` | MOSTLY VIDEO | Partial | MODERATE |
| `video/frames.py` | ONLY VIDEO | N/A | N/A |
| `video/extract.py` | No | YES | NONE |
| `video/scene.py` | ONLY VIDEO | N/A | N/A |
| `caption/` | No | YES | LOW |
| `triage/` | Mostly | MOSTLY | LOW-MODERATE |
