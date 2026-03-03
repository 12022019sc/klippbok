# Phase 6: Captioning System - Research

**Researched:** 2026-03-03
**Domain:** Booru tagging (WD Tagger v3 ONNX), VLM NL captioning, React inline editor, caption persistence
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CAPT-01 | Booru-style tag generation via WD Tagger v3 (ONNX) for SD1.5 datasets | WD Tagger v3 ONNX preprocessing pipeline fully documented; onnxruntime + huggingface_hub are the standard stack |
| CAPT-02 | Natural language caption generation via existing VLM backends (Gemini, Replicate, OpenAI-compatible) | `klippbok/caption/` already has all three backends with `caption_image()` methods ready to use |
| CAPT-03 | Caption style automatically selected based on target model (booru for SD1.5, NL for SDXL/Flux) | `ModelProfile.caption_style` is already "booru" or "natural_language"; need new `caption_service.py` that reads this |
| CAPT-04 | User can override caption style per dataset regardless of model default | Requires a dataset-level settings field persisted in manifest; new `caption_style_override` key |
| CAPT-05 | Manual caption editing: inline text editor per image in gallery view | Lightbox slideFooter is the correct extension point; PATCH endpoint to update manifest caption field |
| CAPT-06 | Trigger word injection: auto-prepend configurable trigger token to all captions | `_prepend_anchor()` logic already exists in captioner.py; needs a batch API endpoint and manifest persistence |
| CAPT-07 | Batch tag operations: add, remove, or replace tags across all captions at once | New `POST /captions/batch` endpoint with operation enum; works on manifest "caption" field for all images |
| CAPT-08 | Caption quality scoring via existing klippbok scoring (length, specificity, issues) | `score_caption()` in `klippbok/caption/scoring.py` is ready; need adapter for image captions (scoring is tuned for video currently) |
| GUI-04 | Inline caption editor alongside image preview in expanded view | Lightbox slideFooter already renders captions as read-only; needs upgrade to editable `<textarea>` |
| GUI-06 | Model configuration selector (dropdown/panel) affecting resolution + caption defaults | Settings page needs a model profile dropdown; profile determines auto-caption style; existing `GET/PUT /settings` stub + manifest |
</phase_requirements>

---

## Summary

Phase 6 adds the captioning system across four plans: WD Tagger v3 ONNX integration (CAPT-01), NL captioning via existing backends with model-aware routing (CAPT-02/03/04), inline caption editing UI (CAPT-05/GUI-04), and trigger words, batch operations, and quality scoring (CAPT-06/07/08). The model configuration selector (GUI-06) is delivered as part of the settings page enhancement.

The caption domain is partially built. `klippbok/caption/` has Gemini, Replicate, and OpenAI-compatible backends all with `caption_image()` methods. `scoring.py` has `score_caption()`. `captioner.py` has `_prepend_anchor()`. What is **entirely new** is WD Tagger v3 ONNX (no existing code), a `caption_service.py` that wraps both paths (booru vs NL), a PATCH endpoint for saving edits, a batch operations endpoint, and the caption editor UI component.

The manifest already has a `caption` field per image (set to `None` until captioned). Caption storage is sidecar `.txt` files on disk plus the `caption` field in manifest for API display. The SSE pattern from import/upscale applies to batch captioning progress.

**Primary recommendation:** Build `klippbok/caption/wd_tagger.py` for ONNX, `klippbok/services/caption_service.py` as the orchestrator, `klippbok/api/routers/captions.py` for all caption endpoints (generate/edit/batch), and a `CaptionPanel` React component in the lightbox footer for inline editing.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| onnxruntime | >=1.17.0 | Run WD Tagger v3 ONNX model for inference | Required by SmilingWolf's reference implementation; CPU inference without PyTorch |
| huggingface_hub | >=0.20 | Download model.onnx + selected_tags.csv from HF | Standard HF download pattern; handles caching to ~/.cache/huggingface/ |
| numpy | >=1.21 (already installed) | Image array preprocessing for ONNX input | Already in `[image]` extras; required for NHWC float32 array |
| Pillow | >=9.0 (already installed) | Pad-to-square, BICUBIC resize, RGBA→RGB composite | Already in `[image]` extras |
| pandas | >=1.0 | Read `selected_tags.csv` for tag label mapping | Used in SmilingWolf's reference app.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| google-genai | >=1.0 (already in `[caption]`) | Gemini NL captioning backend | SDXL/Flux datasets with Gemini key |
| requests | >=2.20 (already in `[caption]`) | Replicate and OpenAI-compat backends | Non-Gemini NL captioning |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| onnxruntime | torch + timm | 2-5x larger install; onnxruntime is the "no GPU required" path |
| huggingface_hub download | Manual wget | HF hub handles authentication, caching, resume; don't hand-roll |
| pandas for CSV | csv module | pandas aligns with reference implementation; csv module is viable if avoiding pandas dep |

**Installation (new deps only):**
```bash
pip install onnxruntime>=1.17.0 huggingface_hub>=0.20 pandas>=1.0
```

Add to `pyproject.toml` as a new `[tagger]` optional dependency group:
```toml
tagger = [
    "klippbok[image]",
    "onnxruntime>=1.17.0",
    "huggingface_hub>=0.20",
    "pandas>=1.0",
]
```

---

## Architecture Patterns

### Caption Storage Model

Captions are stored in two places (must stay in sync):

1. **Manifest** (`caption` field on each image entry): Used by the API to return captions without reading disk.
2. **Sidecar `.txt` file** (same stem as the image file, e.g. `photo.txt`): Used by export pipeline (Phase 8).

The `caption` field in the manifest is the source of truth for the API. Sidecar files are written at caption time and read back on import if the manifest is stale. This mirrors the existing video caption pattern in `captioner.py`.

### Recommended Module Structure
```
klippbok/
├── caption/
│   ├── wd_tagger.py        # NEW: WD Tagger v3 ONNX backend
│   ├── base.py             # Existing VLMBackend ABC
│   ├── captioner.py        # Existing orchestrator (extend for images)
│   ├── scoring.py          # Existing scorer (add image-aware config)
│   └── ...
├── services/
│   └── caption_service.py  # NEW: model-aware caption orchestrator
└── api/
    └── routers/
        └── captions.py     # NEW: caption endpoints

frontend/src/
├── components/
│   └── Caption/
│       ├── CaptionPanel.tsx       # NEW: inline caption editor
│       └── BatchCaptionModal.tsx  # NEW: batch tag operations
├── hooks/
│   └── useCaptionEvents.ts        # NEW: SSE hook for batch captioning progress
└── pages/
    └── GalleryPage.tsx             # Extend lightbox with CaptionPanel
```

### Pattern 1: WD Tagger v3 ONNX Preprocessing

**What:** Exact preprocessing required by SmilingWolf's ONNX model
**When to use:** Every time an image is tagged via WD Tagger
**Source:** https://huggingface.co/spaces/SmilingWolf/wd-tagger/raw/main/app.py

```python
# Source: SmilingWolf wd-tagger app.py (official reference implementation)
import numpy as np
from PIL import Image

def prepare_image(image: Image.Image, model_target_size: int) -> np.ndarray:
    """Preprocess image for WD Tagger v3 ONNX inference.

    Steps:
    1. Composite RGBA onto white background (handles PNG transparency)
    2. Pad to square with white fill (preserves aspect ratio)
    3. Resize to model_target_size (448 for ViT, extracted from model input shape)
    4. Convert to float32 numpy array
    5. Reverse channel order RGB -> BGR (model was trained on BGR)
    6. Add batch dimension [1, H, W, C]
    """
    # Step 1: RGBA → RGB with white background
    canvas = Image.new("RGBA", image.size, (255, 255, 255))
    canvas.alpha_composite(image.convert("RGBA"))
    image = canvas.convert("RGB")

    # Step 2: Pad to square
    max_dim = max(image.size)
    pad_left = (max_dim - image.size[0]) // 2
    pad_top = (max_dim - image.size[1]) // 2
    padded = Image.new("RGB", (max_dim, max_dim), (255, 255, 255))
    padded.paste(image, (pad_left, pad_top))

    # Step 3: Resize
    if max_dim != model_target_size:
        padded = padded.resize((model_target_size, model_target_size), Image.BICUBIC)

    # Step 4-6: Array + BGR + batch dimension
    arr = np.asarray(padded, dtype=np.float32)
    arr = arr[:, :, ::-1]  # RGB → BGR
    return np.expand_dims(arr, axis=0)
```

### Pattern 2: WD Tagger v3 ONNX Inference

```python
# Source: SmilingWolf wd-tagger app.py (official reference implementation)
import onnxruntime as rt
import pandas as pd
from huggingface_hub import hf_hub_download

MODEL_REPO = "SmilingWolf/wd-vit-tagger-v3"
MODEL_FILENAME = "model.onnx"
LABEL_FILENAME = "selected_tags.csv"
GENERAL_THRESHOLD = 0.35   # Standard threshold for general tags
CHARACTER_THRESHOLD = 0.85  # Standard threshold for character tags

def load_wd_tagger(model_repo: str = MODEL_REPO):
    """Download and load WD Tagger v3 ONNX model from Hugging Face."""
    csv_path = hf_hub_download(model_repo, LABEL_FILENAME)
    model_path = hf_hub_download(model_repo, MODEL_FILENAME)

    tags_df = pd.read_csv(csv_path)
    tag_names = tags_df["name"].tolist()
    # Categories: 9=rating, 0=general, 4=character
    general_indexes = np.where(tags_df["category"] == 0)[0]
    character_indexes = np.where(tags_df["category"] == 4)[0]

    model = rt.InferenceSession(model_path)
    _, height, width, _ = model.get_inputs()[0].shape  # e.g. 448

    return model, tag_names, general_indexes, character_indexes, height

def tag_image(
    image_path: Path,
    model, tag_names, general_indexes, character_indexes, target_size,
    general_thresh: float = GENERAL_THRESHOLD,
) -> list[str]:
    """Tag a single image. Returns comma-separated booru tag list."""
    image = Image.open(image_path)
    image_array = prepare_image(image, target_size)

    input_name = model.get_inputs()[0].name
    label_name = model.get_outputs()[0].name
    preds = model.run([label_name], {input_name: image_array})[0]

    labels = list(zip(tag_names, preds[0].astype(float)))
    general_tags = [labels[i] for i in general_indexes]
    result = [(tag, score) for tag, score in general_tags if score > general_thresh]
    result.sort(key=lambda x: x[1], reverse=True)

    # Escape parentheses (booru convention)
    return [tag.replace("(", r"\(").replace(")", r"\)") for tag, _ in result]
```

### Pattern 3: Model-Aware Caption Routing

```python
# caption_service.py
def get_caption_style_for_project(
    project_dir: Path,
    manifest: dict,
) -> Literal["booru", "natural_language"]:
    """Determine caption style from active profile, with override support."""
    # Check for dataset-level override first
    override = manifest.get("caption_style_override")
    if override in ("booru", "natural_language"):
        return override

    # Fall back to model profile default
    active_profile = manifest.get("active_profile", "sdxl")
    profile = get_builtin_profile(active_profile)
    if profile:
        return profile.caption_style
    return "natural_language"  # safe default
```

### Pattern 4: Caption Edit PATCH Endpoint

```python
# Source: project pattern from crop.py / settings.py
@router.patch("/{image_id}/caption")
async def update_caption(
    image_id: str,
    body: CaptionUpdateRequest,
    request: Request,
) -> CaptionUpdateResponse:
    """Update a single image caption in manifest + write sidecar .txt."""
    # 1. Find entry by image_id
    # 2. Update manifest["images"][i]["caption"] = body.caption
    # 3. Write sidecar: image_path.with_suffix(".txt").write_text(body.caption)
    # 4. Save manifest
    # 5. Return updated entry
```

### Pattern 5: Batch Caption Generation (SSE)

The batch captioning operation uses the same SSE pattern as import and upscale:

```python
# Source: pattern from klippbok/api/routers/upscale.py
@router.post("/generate")
async def start_caption_generation(
    body: CaptionGenerateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> CaptionStarted:
    """Start batch caption generation. Returns operation_id for SSE."""
    operation_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _queues[operation_id] = queue
    background_tasks.add_task(_run_caption_batch, operation_id, body, queue, project_dir)
    return CaptionStarted(operation_id=operation_id)

@router.get("/{op_id}/events")
async def caption_events(op_id: str, request: Request):
    """SSE stream for caption generation progress."""
    # mirrors upscale events pattern exactly
```

### Pattern 6: Scoring Adapter for Images

The existing `ScoringConfig` is tuned for video (expects temporal language, long captions). For image booru tags, use a custom config:

```python
# Source: klippbok/caption/scoring.py (adapt for image captions)
IMAGE_SCORING_CONFIG = ScoringConfig(
    min_good_length=20,       # booru tags are short: "1girl, solo, blue_hair" = ~25 chars
    max_good_length=300,      # NL captions for images are shorter than video
    min_acceptable_length=10,
    max_acceptable_length=500,
    weight_length=0.40,
    weight_temporal=0.0,      # temporal irrelevant for images
    weight_specificity=0.40,
    weight_repetition=0.20,
)
```

### Anti-Patterns to Avoid

- **Blocking event loop with ONNX inference:** `onnxruntime.run()` is synchronous. Wrap in `run_in_executor` (matches crop.py pattern for Pillow/MediaPipe).
- **Loading ONNX model per image:** Load once at startup or on first call; cache the session. ONNX model init is expensive (~1-2s).
- **Storing tags as comma-separated string directly:** The manifest `caption` field stores the final formatted caption string. For booru tags, this is the comma-joined list. Consistency with existing pattern.
- **Overwriting existing captions without user consent:** Respect `overwrite: bool` field (existing pattern from `captioner.py`).
- **Hard-coding 448x448:** Extract from `model.get_inputs()[0].shape` at load time — different v3 variants have different sizes.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ONNX model download + caching | Custom wget/requests download | `huggingface_hub.hf_hub_download()` | HF hub handles auth, caching, resume, version pinning |
| Booru tag thresholding algorithm | Custom threshold logic | SmilingWolf's reference implementation (MCut or fixed 0.35) | Reference implementation is validated against Danbooru |
| NL caption generation | New VLM API client | Existing `GeminiBackend`, `ReplicateBackend`, `OpenAICompatBackend` | All have `caption_image(path, prompt)` already |
| Caption quality scoring | New scoring system | `score_caption()` from `klippbok/caption/scoring.py` | Already handles length, specificity, repetition |
| Trigger word prepending | New string manipulation | `_prepend_anchor()` from `captioner.py` | Already handles "already starts with" check |
| SSE progress streaming | New SSE implementation | asyncio.Queue + sse-starlette pattern (from upscale router) | Proven pattern, already in codebase |

---

## Common Pitfalls

### Pitfall 1: ONNX Model Input Format
**What goes wrong:** Image sent as `[H, W, C]` float32 with values 0-255 in RGB order fails inference.
**Why it happens:** WD Tagger expects NHWC format (batch first), BGR channel order, float32.
**How to avoid:** Follow the exact 6-step preprocessing in Pattern 1 above. The `[::-1]` channel reversal is not obvious.
**Warning signs:** Inference returns all near-zero scores or garbage tags.

### Pitfall 2: Model Target Size Assumption
**What goes wrong:** Hard-coding 448 as the image size; breaks for `wd-eva02-large-tagger-v3` which may differ.
**Why it happens:** Documentation implies 448x448 but it's model-specific.
**How to avoid:** Always extract size from `model.get_inputs()[0].shape` after loading.
**Warning signs:** `ONNX shape mismatch` runtime error.

### Pitfall 3: Caption Field vs Sidecar File Out of Sync
**What goes wrong:** User edits caption in UI; manifest updates but `.txt` sidecar doesn't (or vice versa). Phase 8 export reads sidecar files.
**Why it happens:** Two storage locations without transactional writes.
**How to avoid:** Every caption write (generate, edit, batch) MUST write both manifest AND sidecar in the same function. Extract a `_save_caption(image_path, caption, manifest_entry)` helper.
**Warning signs:** Export produces wrong captions; UI shows different value than sidecar.

### Pitfall 4: Blocking Event Loop with ONNX
**What goes wrong:** ONNX inference blocks FastAPI for several seconds per image; all other requests stall.
**Why it happens:** `onnxruntime.run()` is synchronous CPU-bound work in an async handler.
**How to avoid:** Use `await asyncio.get_event_loop().run_in_executor(None, ...)` — matches the pattern in `crop.py`.
**Warning signs:** Gallery endpoint becomes unresponsive during captioning.

### Pitfall 5: Scoring Config Mismatch for Booru Tags
**What goes wrong:** `score_caption("1girl, solo, blue_hair")` returns very low score because it's 20 chars with no temporal words.
**Why it happens:** `ScoringConfig` defaults are tuned for video captions (80-400 chars, temporal language expected).
**How to avoid:** Use `IMAGE_SCORING_CONFIG` (see Pattern 6) for image captions; pass it explicitly to `score_caption()`.
**Warning signs:** All booru-style captions score < 0.1.

### Pitfall 6: pandas Not in Default Install
**What goes wrong:** `import pandas` fails for users who installed `pip install klippbok` without `[tagger]`.
**Why it happens:** pandas is a new dependency not in any existing group.
**How to avoid:** Guard the import inside `wd_tagger.py` with a clear error message pointing to `pip install 'klippbok[tagger]'`. Same pattern as MediaPipe lazy-import in `autocrop.py`.
**Warning signs:** `ModuleNotFoundError: No module named 'pandas'` with no helpful message.

---

## Code Examples

### WD Tagger v3 ONNX Full Example
```python
# Source: https://huggingface.co/spaces/SmilingWolf/wd-tagger/raw/main/app.py
# (adapted to match klippbok module pattern)

from __future__ import annotations
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

MODEL_REPO = "SmilingWolf/wd-vit-tagger-v3"
MODEL_FILENAME = "model.onnx"
LABEL_FILENAME = "selected_tags.csv"


@lru_cache(maxsize=1)
def _get_tagger():
    """Load WD Tagger once; cache via lru_cache."""
    try:
        import onnxruntime as rt
        import pandas as pd
        from huggingface_hub import hf_hub_download
    except ImportError as e:
        raise ImportError(
            f"WD Tagger requires additional dependencies: {e}. "
            "Install with: pip install 'klippbok[tagger]'"
        ) from e

    csv_path = hf_hub_download(MODEL_REPO, LABEL_FILENAME)
    model_path = hf_hub_download(MODEL_REPO, MODEL_FILENAME)

    tags_df = pd.read_csv(csv_path)
    tag_names = tags_df["name"].tolist()
    general_indexes = np.where(tags_df["category"] == 0)[0]
    character_indexes = np.where(tags_df["category"] == 4)[0]

    model = rt.InferenceSession(model_path)
    _, height, width, _ = model.get_inputs()[0].shape

    return model, tag_names, general_indexes, character_indexes, height


def tag_image_booru(
    image_path: Path,
    general_threshold: float = 0.35,
    character_threshold: float = 0.85,
) -> tuple[list[str], list[str]]:
    """Tag a single image with booru-style tags.

    Returns:
        (general_tags, character_tags) — each is a list of tag strings.
    """
    model, tag_names, general_idx, char_idx, target_size = _get_tagger()

    image = Image.open(image_path)

    # Preprocess: RGBA→RGB, pad to square, resize, float32 BGR NHWC
    canvas = Image.new("RGBA", image.size, (255, 255, 255))
    canvas.alpha_composite(image.convert("RGBA"))
    image = canvas.convert("RGB")

    max_dim = max(image.size)
    padded = Image.new("RGB", (max_dim, max_dim), (255, 255, 255))
    padded.paste(image, ((max_dim - image.size[0]) // 2, (max_dim - image.size[1]) // 2))
    if max_dim != target_size:
        padded = padded.resize((target_size, target_size), Image.BICUBIC)

    arr = np.asarray(padded, dtype=np.float32)[:, :, ::-1]
    arr = np.expand_dims(arr, axis=0)

    # Inference
    input_name = model.get_inputs()[0].name
    label_name = model.get_outputs()[0].name
    preds = model.run([label_name], {input_name: arr})[0]

    labels = list(zip(tag_names, preds[0].astype(float)))

    general = [(labels[i][0], labels[i][1]) for i in general_idx if labels[i][1] > general_threshold]
    general.sort(key=lambda x: x[1], reverse=True)
    general_tags = [t.replace("(", r"\(").replace(")", r"\)") for t, _ in general]

    chars = [(labels[i][0], labels[i][1]) for i in char_idx if labels[i][1] > character_threshold]
    chars.sort(key=lambda x: x[1], reverse=True)
    char_tags = [t.replace("(", r"\(").replace(")", r"\)") for t, _ in chars]

    return general_tags, char_tags
```

### Caption Service Routing Example
```python
# Source: project pattern from caption/captioner.py + config/model_profiles.py
from klippbok.config.model_profiles import get_builtin_profile

def caption_image_for_project(
    image_path: Path,
    project_dir: Path,
    manifest: dict,
    vlm_config: CaptionConfig | None = None,
    general_threshold: float = 0.35,
) -> str:
    """Caption an image using the style appropriate for the active model profile.

    - booru style: runs WD Tagger v3 ONNX
    - natural_language style: runs the configured VLM backend

    Returns the caption string (ready to write to manifest + sidecar .txt).
    """
    style = get_caption_style_for_project(project_dir, manifest)

    if style == "booru":
        from klippbok.caption.wd_tagger import tag_image_booru
        general_tags, char_tags = tag_image_booru(image_path, general_threshold)
        all_tags = char_tags + general_tags  # characters first
        return ", ".join(all_tags)
    else:
        # Natural language via VLM backend
        if vlm_config is None:
            raise ValueError("vlm_config required for natural_language captioning")
        from klippbok.caption.captioner import _create_backend
        from klippbok.caption.prompts import get_image_prompt
        backend = _create_backend(vlm_config)
        prompt = get_image_prompt(vlm_config.use_case, vlm_config.anchor_word)
        return backend.caption_image(image_path, prompt)
```

### Caption Save Helper
```python
def _save_caption(
    image_path: Path,
    caption: str,
    project_dir: Path,
    manifest: dict,
    image_id: str,
) -> None:
    """Atomically update both sidecar .txt and manifest caption field.

    MUST be called for every caption write (generate, edit, batch operations).
    """
    # 1. Write sidecar .txt (for export pipeline)
    sidecar_path = image_path.with_suffix(".txt")
    sidecar_path.write_text(caption, encoding="utf-8")

    # 2. Update manifest entry
    for entry in manifest.get("images", []):
        if _image_id(entry["path"]) == image_id:
            entry["caption"] = caption
            break

    # 3. Persist manifest
    from klippbok.services.project_service import save_image_entries
    # ... persist the updated manifest
```

---

## API Design

### New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/captions/generate` | Start batch caption generation (returns op_id for SSE) |
| GET | `/api/v1/captions/{op_id}/events` | SSE stream for generation progress |
| PATCH | `/api/v1/captions/{image_id}` | Update single image caption (inline edit) |
| POST | `/api/v1/captions/batch` | Batch tag operations (add/remove/replace/trigger) |
| GET | `/api/v1/captions/scores` | Get quality scores for all captioned images |

### New Pydantic Models (in `klippbok/api/models.py`)

```python
class CaptionGenerateRequest(BaseModel):
    image_ids: list[str] | None = None  # None = all images
    style: Literal["booru", "natural_language", "auto"] = "auto"
    overwrite: bool = False
    # VLM config (for NL only):
    provider: str | None = None  # "gemini", "replicate", "openai"

class CaptionUpdateRequest(BaseModel):
    caption: str

class CaptionBatchRequest(BaseModel):
    operation: Literal["add_tag", "remove_tag", "replace_tag", "prepend_trigger"]
    value: str           # tag to add/remove/replace/trigger
    replace_with: str | None = None  # for "replace_tag" only
    image_ids: list[str] | None = None  # None = all images

class CaptionScore(BaseModel):
    image_id: str
    caption: str
    overall: float
    length_score: float
    specificity_score: float
    repetition_score: float
    issues: list[str]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| WD14 (ViT-B/16) | WD Tagger v3 (ViT, ConvNext, SwinV2) | 2024 | Better accuracy, same ONNX interface |
| Fixed 448x448 assumption | Extract from model.get_inputs()[0].shape | v3 models | Correct for different architecture variants |
| `optional[str]` for Optional in Pydantic | `str | None` modern union syntax | Pydantic v2 | Already used in project |

**Deprecated/outdated:**
- WD14 (v1/v2): replaced by v3 series. Use `SmilingWolf/wd-vit-tagger-v3` (the standard choice per community consensus).
- `rt.SessionOptions` CUDA provider: overkill for this use case; CPU inference is fine for datasets of a few hundred images.

---

## Open Questions

1. **pandas dependency size**
   - What we know: pandas is ~20MB installed; it's only needed to read `selected_tags.csv`
   - What's unclear: Is this acceptable for the `[tagger]` optional group? Could use `csv` module instead.
   - Recommendation: Use pandas to match the reference implementation exactly. If size is a concern, a follow-up can swap to `csv` module — the interface won't change.

2. **ONNX model caching location**
   - What we know: `hf_hub_download` caches to `~/.cache/huggingface/hub/` by default (~380MB for `model.onnx`)
   - What's unclear: Should we surface the cache path in Settings so users understand disk usage?
   - Recommendation: Accept HF default cache for Phase 6; add disk usage display in Phase 8 or as a future improvement.

3. **WD Tagger for NSFW content**
   - What we know: WD Tagger v3 outputs rating tags (general/sensitive/questionable/explicit)
   - What's unclear: Should the API expose rating tags, or only general+character tags?
   - Recommendation: Return only `general + character` tags for the caption string; ignore rating tags. Keep it simple.

4. **GUI-06 scope: Model profile selector**
   - What we know: `GET/PUT /settings` already exists; `active_profile` is stored in manifest; SettingsPage is a stub
   - What's unclear: Should GUI-06 be a full settings panel redesign or a simple dropdown in SettingsPage?
   - Recommendation: Minimal change — add a dropdown to SettingsPage that calls `PUT /settings` with `active_profile`. Caption style follows automatically from the profile.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.x |
| Config file | `pytest.ini` or `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `pytest tests/test_wd_tagger.py tests/test_caption_service.py -x` |
| Full suite command | `pytest` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CAPT-01 | WD Tagger tags an image and returns booru-style list | unit | `pytest tests/test_wd_tagger.py -x` | ❌ Wave 0 |
| CAPT-01 | Preprocessing: RGBA image produces correct NHWC float32 BGR array | unit | `pytest tests/test_wd_tagger.py::test_prepare_image -x` | ❌ Wave 0 |
| CAPT-02 | NL caption via Gemini backend calls caption_image() | unit (mock) | `pytest tests/test_caption_service.py::test_nl_caption_gemini -x` | ❌ Wave 0 |
| CAPT-03 | SD1.5 profile routes to booru; SDXL routes to NL | unit | `pytest tests/test_caption_service.py::test_caption_routing -x` | ❌ Wave 0 |
| CAPT-04 | caption_style_override in manifest overrides profile default | unit | `pytest tests/test_caption_service.py::test_style_override -x` | ❌ Wave 0 |
| CAPT-05 | PATCH /captions/{id} updates manifest + writes sidecar .txt | integration | `pytest tests/test_caption_api.py::test_update_caption -x` | ❌ Wave 0 |
| CAPT-06 | Trigger word prepend adds token to all captions | unit | `pytest tests/test_caption_service.py::test_trigger_prepend -x` | ❌ Wave 0 |
| CAPT-07 | Batch add_tag adds tag to all captions; remove_tag removes it | unit | `pytest tests/test_caption_service.py::test_batch_operations -x` | ❌ Wave 0 |
| CAPT-08 | score_caption with IMAGE_SCORING_CONFIG scores booru tags correctly | unit | `pytest tests/test_caption_scoring.py::test_image_scoring_config -x` | ❌ Wave 0 (test_caption_scoring.py EXISTS, add new test) |
| GUI-04 | CaptionPanel renders caption text in lightbox footer | manual | N/A | N/A |
| GUI-06 | SettingsPage profile dropdown changes active_profile via PUT /settings | manual | N/A | N/A |

### Sampling Rate
- **Per task commit:** `pytest tests/test_wd_tagger.py tests/test_caption_service.py tests/test_caption_api.py -x`
- **Per wave merge:** `pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_wd_tagger.py` — covers CAPT-01 (preprocessing, threshold filtering). Use a 32x32 test PNG; mock onnxruntime for unit tests (avoid 380MB model download in CI)
- [ ] `tests/test_caption_service.py` — covers CAPT-02, CAPT-03, CAPT-04, CAPT-06, CAPT-07. Mock the WD Tagger and VLM backends.
- [ ] `tests/test_caption_api.py` — covers CAPT-05 (PATCH endpoint, manifest + sidecar sync). Use TestClient with a temp project dir.
- [ ] `tests/test_caption_scoring.py` already exists — add `test_image_scoring_config()` to existing file (no new file needed).

---

## Sources

### Primary (HIGH confidence)
- `https://huggingface.co/spaces/SmilingWolf/wd-tagger/raw/main/app.py` — Complete preprocessing pipeline, ONNX loading, threshold values, output formatting (fetched directly)
- `klippbok/caption/` (codebase) — Existing VLM backends, scoring module, captioner orchestrator
- `klippbok/api/models.py` (codebase) — API model patterns, SSE architecture
- `klippbok/config/model_profiles.py` (codebase) — ModelProfile.caption_style field exists and is "booru" or "natural_language"
- `klippbok/services/project_service.py` (codebase) — Manifest structure, caption field, save_image_entries pattern

### Secondary (MEDIUM confidence)
- `https://huggingface.co/SmilingWolf/wd-vit-tagger-v3` — Model details: 379MB model.onnx, selected_tags.csv, onnxruntime>=1.17.0 requirement
- `https://github.com/SmilingWolf/wdv3-jax` — Output format: general_threshold=0.35, character_threshold=0.75-0.85

### Tertiary (LOW confidence)
- General ecosystem search results confirming onnxruntime + huggingface_hub as standard WD tagger integration pattern

---

## Metadata

**Confidence breakdown:**
- WD Tagger v3 ONNX preprocessing: HIGH — fetched from official app.py directly
- VLM backends (CAPT-02): HIGH — code exists in codebase
- Architecture patterns: HIGH — based on existing code patterns in codebase
- Scoring adapter: HIGH — score_caption() source read; config adjustment is straightforward
- Default thresholds (0.35/0.85): MEDIUM — from wdv3-jax README examples, not official docs

**Research date:** 2026-03-03
**Valid until:** 2026-06-01 (WD tagger stable; HF API stable)
