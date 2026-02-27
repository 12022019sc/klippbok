# Phase 2: Model Configuration - Research

**Researched:** 2026-02-27
**Domain:** Model profile schema, bucket generation, config override system
**Confidence:** HIGH

## Summary

Phase 2 delivers a model profile system that maps target model selection (SD1.5, SDXL, Flux, Pony, custom) to resolution presets, bucket sizes, caption style defaults, and training hyperparameter hints. The codebase already has a config system (`klippbok/config/`) with Pydantic v2 models and YAML loading, a bucketing preview system (`klippbok/dataset/bucketing.py`), and a project manifest at `.klippbok/manifest.json`. Phase 2 adds a new model profile schema, a per-project override config at `.klippbok/model_config.json`, and user-level custom profiles at `~/.klippbok/profiles/`.

The bucket generation algorithm should follow the kohya/sd-scripts pixel-budget approach: given a base resolution (defining max pixel area), min/max dimension bounds, and a step size, enumerate all valid (width, height) pairs where `width * height <= base_resolution^2`, both dimensions are multiples of the step size, and both fall within the min/max range. This is the industry standard and what trainers like musubi-tuner, ai-toolkit, and kohya expect.

No external libraries are needed -- this phase is pure Pydantic models, JSON file I/O, and arithmetic. All dependencies already exist in the project.

**Primary recommendation:** Define model profiles as frozen Pydantic models with a `generate_buckets()` function. Store built-in profiles as module-level constants. Store overrides in `.klippbok/model_config.json` using a layered merge pattern (profile defaults -> project overrides). Store custom profiles as JSON files in `~/.klippbok/profiles/`.

## Standard Stack

### Core

No new libraries needed. Phase 2 uses only existing dependencies:

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | >=2.0 | Model profile schema, validation, serialization | Already the project's schema layer |
| pyyaml | >=6.0 | Config loading (existing) | Already a base dependency |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json (stdlib) | -- | Profile and override persistence | `.klippbok/model_config.json` and `~/.klippbok/profiles/*.json` |
| pathlib (stdlib) | -- | Cross-platform path handling for `~/.klippbok/` | User-level custom profile storage |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| JSON for profiles | YAML | YAML is human-friendlier but JSON matches the existing manifest pattern and is simpler for machine-written config |
| Frozen Pydantic models for profiles | Plain dicts | Dicts offer no validation; Pydantic catches invalid profiles at construction time |
| Module-level constants for built-ins | YAML files bundled as package data | Constants are simpler, testable, and don't require file I/O at import time |

## Architecture Patterns

### Recommended Project Structure

```
klippbok/
  config/
    data_schema.py          # Existing -- NOT modified
    defaults.py             # Existing -- extended with model constants
    loader.py               # Existing -- NOT modified
    model_profiles.py       # NEW: ModelProfile schema + built-in profiles
    model_defaults.py       # NEW: Built-in profile constant definitions
    model_config.py         # NEW: Per-project override loading/saving
    __init__.py             # Updated: export new public API
```

### Pattern 1: Frozen Profile Schema with Computed Buckets

**What:** A `ModelProfile` Pydantic model defines all model-specific defaults. Bucket lists are computed on demand from profile parameters, not stored statically.

**When to use:** Always -- profiles define *parameters*, not *results*. Buckets are derived from (base_resolution, step_size, min_dimension, max_dimension).

**Example:**
```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class BucketConfig(BaseModel):
    """Parameters for bucket generation."""
    model_config = ConfigDict(frozen=True)

    step_size: int = Field(default=64, description="Pixel step for dimension alignment")
    min_dimension: int = Field(default=256, description="Minimum bucket dimension")
    max_dimension: int = Field(default=1024, description="Maximum bucket dimension")
    # max_area is derived from base_resolution^2


class TrainingHints(BaseModel):
    """Training hyperparameter suggestions for export config generation (Phase 8)."""
    model_config = ConfigDict(frozen=True)

    learning_rate_range: tuple[float, float] = (1e-5, 1e-3)
    network_rank_range: tuple[int, int] = (4, 128)
    network_rank_default: int = 32
    network_alpha_ratio: float = 0.5  # alpha = rank * ratio


class ModelProfile(BaseModel):
    """A target model profile defining resolution, bucket, and caption defaults."""
    model_config = ConfigDict(frozen=True)

    name: str
    display_name: str
    base_resolution: int  # e.g., 512 for SD1.5, 1024 for SDXL
    caption_style: Literal["booru", "natural_language"]
    bucket_config: BucketConfig = Field(default_factory=BucketConfig)
    training_hints: TrainingHints = Field(default_factory=TrainingHints)
    description: str = ""
```

### Pattern 2: Pixel-Budget Bucket Generation (kohya-compatible)

**What:** Generate all valid (width, height) pairs within a pixel budget, aligned to a step grid. This is the algorithm used by kohya/sd-scripts, musubi-tuner, and ai-toolkit.

**When to use:** Whenever buckets need to be computed for a model profile.

**Algorithm (verified against kohya/sd-scripts):**
```python
def generate_buckets(
    base_resolution: int,
    step_size: int = 64,
    min_dimension: int = 256,
    max_dimension: int | None = None,
) -> list[tuple[int, int]]:
    """Generate valid bucket resolutions within a pixel budget.

    The pixel budget is base_resolution^2 (e.g., 512^2 = 262,144 for SD1.5).
    Each bucket (w, h) satisfies:
      - w * h <= pixel_budget
      - w % step_size == 0
      - h % step_size == 0
      - min_dimension <= w <= max_dimension
      - min_dimension <= h <= max_dimension

    Args:
        base_resolution: Defines pixel budget (base_resolution^2).
        step_size: Dimension alignment step (64 for SD1.5/SDXL, 32 also valid for SDXL).
        min_dimension: Smallest allowed dimension.
        max_dimension: Largest allowed dimension (defaults to 2 * base_resolution).

    Returns:
        Sorted list of (width, height) tuples.
    """
    if max_dimension is None:
        max_dimension = base_resolution * 2

    pixel_budget = base_resolution * base_resolution
    buckets: set[tuple[int, int]] = set()

    w = min_dimension
    while w <= max_dimension:
        # Max height that fits within pixel budget at this width
        max_h = min(max_dimension, (pixel_budget // w) // step_size * step_size)
        if max_h >= min_dimension:
            buckets.add((w, max_h))
            # Also add the transposed pair
            if max_h != w:
                buckets.add((max_h, w))
        w += step_size

    return sorted(buckets)
```

**SD1.5 example (512 base, 64 step):** Produces buckets like (256, 1024), (320, 768), (384, 640), (448, 576), (512, 512), (576, 448), etc.

**SDXL example (1024 base, 64 step):** Produces buckets like (512, 2048), (576, 1792), ..., (1024, 1024), ..., (2048, 512).

### Pattern 3: Layered Override System

**What:** Per-project overrides merge on top of the base profile. Each field can be independently overridden or reset to default. The override file stores only the delta.

**When to use:** When loading the effective model config for a project.

**Example:**
```python
class ModelConfigOverride(BaseModel):
    """Per-project overrides on top of a model profile.

    Only overridden fields are stored. None means 'use profile default'.
    """
    profile_name: str  # Which built-in or custom profile this is based on
    base_resolution: int | None = None
    caption_style: Literal["booru", "natural_language"] | None = None
    bucket_step_size: int | None = None
    bucket_min_dimension: int | None = None
    bucket_max_dimension: int | None = None
    # training_hints overrides...


def resolve_effective_config(
    profile: ModelProfile,
    overrides: ModelConfigOverride | None,
) -> ModelProfile:
    """Merge overrides onto a base profile, producing the effective config.

    Non-None override fields replace profile defaults.
    Returns a new frozen ModelProfile with overrides applied.
    """
    if overrides is None:
        return profile

    data = profile.model_dump()
    override_data = overrides.model_dump(exclude_none=True, exclude={"profile_name"})

    # Flatten nested overrides into the profile structure
    if "bucket_step_size" in override_data:
        data["bucket_config"]["step_size"] = override_data.pop("bucket_step_size")
    # ... similar for other nested fields

    for key, value in override_data.items():
        if key in data:
            data[key] = value

    return ModelProfile(**data)
```

### Pattern 4: User-Level Custom Profiles

**What:** Custom profiles are stored as JSON files in `~/.klippbok/profiles/`. They are created by cloning a built-in profile and modifying it.

**When to use:** When users need profiles for models not covered by the four built-ins.

**Storage layout:**
```
~/.klippbok/
  profiles/
    my_custom_model.json
    illustrious_xl.json
```

**File format:**
```json
{
  "name": "illustrious_xl",
  "display_name": "Illustrious XL",
  "based_on": "sdxl",
  "base_resolution": 1024,
  "caption_style": "booru",
  "bucket_config": {
    "step_size": 64,
    "min_dimension": 512,
    "max_dimension": 2048
  },
  "training_hints": {
    "learning_rate_range": [5e-5, 5e-4],
    "network_rank_range": [16, 64],
    "network_rank_default": 32,
    "network_alpha_ratio": 0.5
  },
  "description": "Illustrious XL (anime-focused SDXL finetune, booru tags)"
}
```

### Anti-Patterns to Avoid

- **Storing bucket lists in profiles:** Buckets should be computed from parameters, not stored. Storing them creates sync issues when parameters change and bloats the profile files.
- **Mutable profile objects:** Profiles must be frozen Pydantic models. Overrides produce a NEW profile via `resolve_effective_config()`, never mutate the original.
- **Merging overrides into the base YAML config:** Model config overrides live in `.klippbok/model_config.json`, separate from `klippbok_data.yaml`. The data config describes the dataset; the model config describes what model the dataset targets. These are different concerns.
- **Per-dataset model profiles:** The context decision is one model profile per project. Do not design for per-dataset profiles.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Bucket generation | Custom aspect-ratio heuristics | Pixel-budget algorithm (kohya-compatible) | Every trainer expects kohya-style buckets. Custom algorithms produce incompatible bucket sets. |
| Config merge/layering | Manual dict merging with edge cases | Pydantic `model_dump(exclude_none=True)` + reconstruction | Pydantic handles validation, defaults, and type coercion. Manual merging misses edge cases. |
| JSON serialization | Custom serializers | Pydantic `model_dump_json()` / `model_validate_json()` | Pydantic v2 has built-in JSON serialization that handles all field types correctly. |
| Path expansion for `~` | Manual `os.path.expanduser` | `Path.home()` / `Path.expanduser()` | Standard library, cross-platform, handles edge cases. |

**Key insight:** The bucket generation algorithm is the only non-trivial computation in this phase. Everything else is schema definition, file I/O, and config merging -- all well-served by Pydantic v2's built-in capabilities.

## Common Pitfalls

### Pitfall 1: Wrong Bucket Step Size for Model

**What goes wrong:** Using step_size=64 for all models when SDXL can benefit from step_size=32. Or using step_size=32 for SD1.5 which produces buckets that most SD1.5 trainers don't expect.
**Why it happens:** Treating all models as having the same VAE architecture constraints.
**How to avoid:** Each model profile defines its own bucket_config with appropriate step_size. SD1.5: 64. SDXL: 64 (default) or 32. Flux: 64. Make step_size a profile parameter, not a global constant.
**Warning signs:** Training crashes with "size mismatch" errors, or wasted VRAM from overly granular buckets.

### Pitfall 2: Override Persistence Without Profile Reference

**What goes wrong:** Storing overrides without recording which base profile they apply to. If the user switches from SD1.5 to SDXL, the old overrides (resolution=768) may silently apply to the new profile.
**Why it happens:** Treating overrides as absolute values rather than deltas on a specific profile.
**How to avoid:** `model_config.json` always includes `profile_name`. When the profile changes, the override system either clears overrides or warns about stale overrides.
**Warning signs:** Base resolution of 768px on an SDXL project (neither SD1.5's 512 nor SDXL's 1024).

### Pitfall 3: max_dimension Too Large Produces Extreme Aspect Ratios

**What goes wrong:** With max_dimension = 2 * base_resolution and no aspect ratio constraint, the bucket generator produces extreme ratios like 256x1024 (1:4) that most trainers handle poorly.
**Why it happens:** Pixel budget alone doesn't constrain aspect ratio.
**How to avoid:** Add an aspect ratio range constraint. Kohya uses min_bucket_reso and max_bucket_reso which implicitly constrains ratios. A practical range is 1:3 to 3:1 (or equivalently, aspect ratio between 0.33 and 3.0). This should be a configurable parameter on BucketConfig with sensible defaults.
**Warning signs:** Single-sample buckets at extreme aspect ratios that get padded during training.

### Pitfall 4: Custom Profile Validation Too Loose

**What goes wrong:** User creates a custom profile with base_resolution=100 or step_size=7, which produces buckets incompatible with any real trainer.
**Why it happens:** Accepting arbitrary values without sanity checks.
**How to avoid:** Validate that base_resolution is a multiple of step_size, step_size is a power of 2 (8, 16, 32, 64), and base_resolution is within a reasonable range (128-4096). Use Pydantic validators on the model.
**Warning signs:** Zero buckets generated, or buckets that no trainer can use.

### Pitfall 5: Confusing caption_style with caption_format

**What goes wrong:** Mixing up the caption *style* (booru tags vs natural language -- a model-level default set by Phase 2) with the caption *format* (txt vs jsonl -- a dataset-level file format set by the existing data config).
**Why it happens:** Both involve "how captions are handled" but at different abstraction levels.
**How to avoid:** `caption_style` in ModelProfile is about *what kind of text* (booru tags vs NL). `TextControlConfig.format` in the data schema is about *what file format* (txt vs jsonl). These are orthogonal. Phase 6 (Captioning) connects them: caption_style determines which captioner (WD Tagger vs VLM) to use, while format determines where captions are stored.
**Warning signs:** Natural language captions being comma-split as if they were booru tags, or booru tags being joined into sentences.

## Code Examples

### Built-in Profile Definitions

```python
# In klippbok/config/model_defaults.py

from klippbok.config.model_profiles import (
    BucketConfig, ModelProfile, TrainingHints,
)

SD15_PROFILE = ModelProfile(
    name="sd15",
    display_name="Stable Diffusion 1.5",
    base_resolution=512,
    caption_style="booru",
    bucket_config=BucketConfig(
        step_size=64,
        min_dimension=256,
        max_dimension=1024,
    ),
    training_hints=TrainingHints(
        learning_rate_range=(1e-5, 1e-3),
        network_rank_range=(4, 128),
        network_rank_default=32,
        network_alpha_ratio=0.5,
    ),
    description="SD1.5 — 512px base, booru-style tags, 262K pixel budget",
)

SDXL_PROFILE = ModelProfile(
    name="sdxl",
    display_name="Stable Diffusion XL",
    base_resolution=1024,
    caption_style="natural_language",
    bucket_config=BucketConfig(
        step_size=64,
        min_dimension=512,
        max_dimension=2048,
    ),
    training_hints=TrainingHints(
        learning_rate_range=(5e-6, 5e-4),
        network_rank_range=(8, 128),
        network_rank_default=32,
        network_alpha_ratio=0.5,
    ),
    description="SDXL — 1024px base, natural language captions, 1M pixel budget",
)

FLUX_PROFILE = ModelProfile(
    name="flux",
    display_name="Flux (dev & schnell)",
    base_resolution=1024,
    caption_style="natural_language",
    bucket_config=BucketConfig(
        step_size=64,
        min_dimension=512,
        max_dimension=2048,
    ),
    training_hints=TrainingHints(
        learning_rate_range=(8e-5, 2e-3),
        network_rank_range=(16, 64),
        network_rank_default=32,
        network_alpha_ratio=1.0,  # Flux LoRAs typically use alpha = rank
    ),
    description="Flux — 1024px base, natural language captions, covers dev and schnell",
)

PONY_PROFILE = ModelProfile(
    name="pony",
    display_name="Pony Diffusion XL",
    base_resolution=1024,
    caption_style="booru",
    bucket_config=BucketConfig(
        step_size=64,
        min_dimension=512,
        max_dimension=2048,
    ),
    training_hints=TrainingHints(
        learning_rate_range=(5e-6, 5e-4),
        network_rank_range=(8, 128),
        network_rank_default=32,
        network_alpha_ratio=0.5,
    ),
    description="Pony XL — 1024px base, booru-style tags (SDXL-based anime model)",
)

BUILTIN_PROFILES: dict[str, ModelProfile] = {
    p.name: p for p in [SD15_PROFILE, SDXL_PROFILE, FLUX_PROFILE, PONY_PROFILE]
}
```

### Loading and Saving Model Config

```python
# In klippbok/config/model_config.py

import json
from pathlib import Path

from klippbok.config.model_profiles import ModelProfile, ModelConfigOverride
from klippbok.config.model_defaults import BUILTIN_PROFILES

MODEL_CONFIG_FILE = "model_config.json"
KLIPPBOK_DIR = ".klippbok"
USER_PROFILES_DIR = Path.home() / ".klippbok" / "profiles"


def load_model_config(project_dir: Path) -> ModelConfigOverride | None:
    """Load per-project model config overrides."""
    config_path = project_dir / KLIPPBOK_DIR / MODEL_CONFIG_FILE
    if not config_path.exists():
        return None
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return ModelConfigOverride.model_validate(data)


def save_model_config(
    project_dir: Path,
    overrides: ModelConfigOverride,
) -> Path:
    """Save per-project model config overrides."""
    config_dir = project_dir / KLIPPBOK_DIR
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / MODEL_CONFIG_FILE
    config_path.write_text(
        overrides.model_dump_json(indent=2, exclude_none=True) + "\n",
        encoding="utf-8",
    )
    return config_path


def get_profile(name: str) -> ModelProfile:
    """Get a model profile by name (built-in or custom)."""
    if name in BUILTIN_PROFILES:
        return BUILTIN_PROFILES[name]
    return _load_custom_profile(name)


def list_profiles() -> list[ModelProfile]:
    """List all available profiles (built-in + custom)."""
    profiles = list(BUILTIN_PROFILES.values())
    profiles.extend(_load_all_custom_profiles())
    return profiles
```

### Bucket Generation with Aspect Ratio Constraint

```python
def generate_buckets(
    base_resolution: int,
    step_size: int = 64,
    min_dimension: int = 256,
    max_dimension: int | None = None,
    max_aspect_ratio: float = 3.0,
) -> list[tuple[int, int]]:
    """Generate valid bucket resolutions within a pixel budget.

    Follows the kohya/sd-scripts algorithm:
    1. Pixel budget = base_resolution^2
    2. For each width from min_dimension to max_dimension (step_size increments):
       a. Compute max valid height = floor(pixel_budget / width) snapped to step_size
       b. Clamp height to [min_dimension, max_dimension]
       c. Check aspect ratio constraint
       d. Add (width, height) and (height, width) if both are valid
    3. Return sorted, deduplicated bucket list
    """
    if max_dimension is None:
        max_dimension = base_resolution * 2

    pixel_budget = base_resolution * base_resolution
    buckets: set[tuple[int, int]] = set()

    w = min_dimension
    while w <= max_dimension:
        h = (pixel_budget // w) // step_size * step_size
        h = min(h, max_dimension)

        if h >= min_dimension:
            ratio = max(w, h) / min(w, h)
            if ratio <= max_aspect_ratio:
                buckets.add((w, h))
                if w != h:
                    buckets.add((h, w))

        w += step_size

    return sorted(buckets)
```

### Override Reset for Individual Fields

```python
def reset_override_field(
    project_dir: Path,
    field_name: str,
) -> ModelConfigOverride:
    """Reset a single override field back to profile default.

    Sets the field to None in the override config, which means
    'use the base profile value'.
    """
    overrides = load_model_config(project_dir)
    if overrides is None:
        raise ValueError("No model config exists for this project")

    data = overrides.model_dump()
    if field_name not in data:
        raise ValueError(f"Unknown field: {field_name}")

    data[field_name] = None
    updated = ModelConfigOverride.model_validate(data)
    save_model_config(project_dir, updated)
    return updated
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Fixed 512x512 or 1024x1024 only | Multi-resolution bucketing with pixel budget | ~2023 (kohya sd-scripts) | Training uses varied aspect ratios, dramatically improving quality |
| SD1.5 was the default | SDXL/Flux are now primary targets | 2024-2025 | Most new LoRAs target SDXL or Flux; SD1.5 is legacy but still widely used |
| Single step size (64) for all | SDXL supports step_size=32 | kohya sd-scripts 0.8+ | Finer bucket granularity for SDXL, reducing wasted pixels |
| Booru tags for everything | NL captions for SDXL/Flux, booru for SD1.5/Pony | 2024+ | SDXL/Flux text encoders (CLIP-G, T5) understand NL better than tag lists |
| Manual bucket list definition | Auto-generated from pixel budget | Standard practice | Less error-prone, consistent with trainer expectations |

**Deprecated/outdated:**
- DeepDanbooru for tagging (superseded by WD Tagger v3)
- Fixed resolution training without bucketing (wastes data quality)
- Using NL captions for SD1.5 training (CLIP encoder works better with tags)

## Open Questions

1. **Exact aspect ratio constraint value**
   - What we know: Kohya uses min_bucket_reso/max_bucket_reso which implicitly limits ratios. Most practical training uses ratios up to about 1:2 or 1:3.
   - What's unclear: Whether 3.0 or 2.0 is the better default max_aspect_ratio.
   - Recommendation: Default to 2.0 (covers portrait/landscape up to 1:2), allow override. This matches common trainer defaults where min=base/2, max=base*2.

2. **Bucket step size: 64 fixed or configurable per-profile?**
   - What we know: SD1.5 uses 64. SDXL can use 32 or 64. Flux uses 64. Most users never change this.
   - What's unclear: Whether making it configurable adds value or just confusion.
   - Recommendation: Configurable in BucketConfig (already designed above) but default to 64 for all built-in profiles. Advanced users can override per-project.

3. **Training hints accuracy**
   - What we know: Learning rate ranges and rank suggestions vary by community source. No single authoritative reference.
   - What's unclear: Exact optimal ranges change as trainers evolve.
   - Recommendation: Use conservative ranges gathered from multiple sources (kohya wiki, civitai guides, ai-toolkit docs). These are *hints* for Phase 8 export, not enforced constraints. Mark as MEDIUM confidence.

4. **Interaction with existing BucketingConfig in data_schema.py**
   - What we know: `BucketingConfig` in `data_schema.py` handles video bucketing with dimensions=[aspect_ratio, frame_count, resolution]. This is 3D bucketing for video clips.
   - What's unclear: Should the model profile's bucket generation replace or coexist with the existing video bucketing?
   - Recommendation: Coexist. The model profile generates the *valid resolution buckets* for images. The existing video `BucketingConfig` handles the *3D bucketing* (aspect + frames + resolution) for video clips. They serve different purposes. Phase 2 bucket generation is for the image pipeline (Phase 3+); video bucketing remains as-is.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `klippbok/config/data_schema.py`, `klippbok/config/defaults.py`, `klippbok/config/loader.py`, `klippbok/dataset/bucketing.py`, `klippbok/dataset/trainers.py`, `klippbok/services/project_service.py`
- `.planning/phases/01-architecture-foundation/01-RESEARCH.md` -- established patterns and conventions
- `.planning/phases/02-model-configuration/02-CONTEXT.md` -- locked decisions from discussion phase

### Secondary (MEDIUM confidence)
- [kohya-ss/sd-scripts bucket algorithm](https://github.com/kohya-ss/sd-scripts/blob/main/library/train_util.py) -- bucket generation with pixel budget, step_size, min/max dimensions
- [kohya-ss SDXL training docs](https://github.com/kohya-ss/sd-scripts/blob/main/docs/train_SDXL-en.md) -- SDXL bucket_reso_steps=32 or 64
- [Sable Confusion: Bucket Assignment](https://medium.com/@sableconfusion/lora-training-practice-in-kohya-ss-how-are-images-assigned-to-buckets-19b2a3e97c6c) -- detailed explanation of kohya bucket assignment with examples
- [kohya LoRA training parameters wiki](https://github.com/bmaltais/kohya_ss/wiki/LoRA-training-parameters) -- learning rate, network rank recommendations
- [LoRA Training Best Practices 2025](https://apatero.com/blog/lora-training-best-practices-flux-stable-diffusion-2025) -- Flux training settings and resolution guidance
- [Civitai: Pony/Illustrious XL LoRA Training](https://civitai.com/articles/10288/lora-training-workflow-pony-illustrious-xl) -- Pony XL booru tag workflow

### Tertiary (LOW confidence)
- Training hint values (learning rates, rank ranges) -- aggregated from multiple community sources, not from official model documentation. Treat as reasonable defaults, not ground truth.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, pure Pydantic + JSON + stdlib
- Architecture: HIGH -- follows established codebase patterns (frozen models, stateless functions, `.klippbok/` directory)
- Bucket generation algorithm: HIGH -- verified against kohya/sd-scripts source (the industry standard)
- Built-in profile values (resolutions, step sizes): HIGH -- well-established community consensus
- Training hints (learning rates, rank ranges): MEDIUM -- aggregated from multiple sources, varies by use case
- Pitfalls: HIGH -- derived from real issues (kohya GitHub issues, community reports)

**Research date:** 2026-02-27
**Valid until:** 2026-04-27 (60 days -- model profiles are stable, training recommendations evolve slowly)
