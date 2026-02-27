# Feature Landscape: Image Dataset Preparation for LoRA Training

**Domain:** Image dataset curation, cropping, tagging/captioning, and export for LoRA training (SD1.5, SDXL, Flux)
**Researched:** 2026-02-27
**Context:** Extending klippbok (video dataset tool) to support image-based LoRA workflows via web GUI

---

## Table Stakes

Features users expect from any image dataset preparation tool. Missing these and the tool feels broken or incomplete -- users will fall back to Birme + manual txt editing.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Image import (batch)** | Users drag/drop 10-200 images to start | Low | Accept PNG, JPG, WEBP, TIFF. Reject corrupt files with clear errors. |
| **Resolution display per image** | Users must know if image is high enough res for target bucket | Low | Show WxH, megapixels, and green/red indicator vs target resolution |
| **Aspect ratio bucketing preview** | Core to LoRA training -- images grouped by aspect ratio for batch efficiency | Low | klippbok already has bucketing logic. Extend for image-only (no frame_count). Show bucket distribution. |
| **Resize to target resolution** | All trainers expect images at training resolution (512, 768, 1024) | Low | Downscale only. Flag upscale as quality loss (red indicator, per malcolmrey's pattern). |
| **Center crop** | Most basic crop method -- every tool has it | Low | Crop to target bucket dimensions from image center. |
| **Caption file generation (.txt)** | Universal trainer format: image.png paired with image.txt | Low | One .txt per image, same stem name. This is the standard every trainer expects. |
| **Manual caption editing** | Users always need to review/edit auto-generated captions | Low | Text field per image, save to .txt. Inline editing in the gallery view. |
| **Batch export as trainer-ready folder** | End goal of the tool -- output a folder trainers can consume directly | Medium | Resized images + caption .txt files in correct structure. |
| **Model-aware resolution presets** | SD1.5=512px, SDXL/Flux=1024px. Users expect quick selection. | Low | Dropdown or toggle that sets target resolution and valid bucket sizes. |
| **Image preview gallery** | Users need to see all images, their crops, and captions at a glance | Medium | Thumbnail grid with caption overlay. Click to expand/edit. |
| **Duplicate detection** | Duplicate or near-duplicate images waste training budget | Medium | klippbok already has this in video/image_quality.py. Reuse perceptual hash. |
| **Basic quality filtering** | Reject blurry, overexposed, heavily compressed images | Medium | klippbok already has blur/exposure detection. Surface as pass/fail per image. |

---

## Differentiators

Features that set klippbok apart from the existing tools (Birme, BooruDatasetTagManager, SD Tag Editor, LoraTag). Not expected, but highly valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Interactive crop with snap-to-bucket-ratio** | The killer feature from malcolmrey's space. Draggable crop rectangle that snaps to valid training aspect ratios on release. No other standalone tool does this well with a web GUI. | High | CTRL+resize for freeform, release snaps to nearest valid ratio. Red dashed rectangle. Green/red resolution indicator. This is the signature UX. |
| **Auto-crop with subject detection** | AI-based focal point detection (face/person/object) places the crop rectangle intelligently before user fine-tunes. Birme does face detection only; klippbok can do general subject detection via YOLO or saliency maps. | High | Use ultralytics YOLO or similar for subject detection. Fall back to center crop. User always gets final say via interactive crop. |
| **Model-aware captioning defaults** | SD1.5 expects booru-style tags (comma-separated keywords). SDXL/Flux expect natural language sentences. Tool pre-selects the right captioning style based on target model. No other tool does this automatically. | Medium | SD1.5 -> WD14 tagger (booru tags). SDXL/Flux -> JoyCaption/Florence2/Gemini (NL captions). User can override. Leverage klippbok's existing VLM captioning backends. |
| **Unified video+image pipeline** | No other tool handles both video clips AND images in a single dataset workflow. Users training on mixed media (video LoRA + supplementary stills) get one tool instead of two. | Medium | klippbok's existing video pipeline + new image support = unique value. Same bucketing, same captioning backends, same export. |
| **Caption scoring and quality audit** | klippbok already has caption scoring (length, specificity, issues). Apply the same quality analysis to image captions. Flag weak captions before training. | Low | Already built in klippbok.caption.scoring. Just wire to image captions. |
| **Batch tag operations** | Add/remove/replace tags across all captions at once. "Add 'solo' to all", "Remove 'watermark' from all", "Replace 'girl' with '1girl'". Essential for booru-style SD1.5 datasets. | Medium | BooruDatasetTagManager does this but is a standalone desktop app. Having it in the web GUI alongside crop preview is the differentiator. |
| **Trigger word injection** | Automatically prepend a trigger token (e.g., "sks", "ohwx") to all captions. Standard LoRA practice but usually manual. | Low | Simple prefix injection with preview. Per-concept-folder if using DreamBooth-style structure. |
| **Bucket distribution visualization** | Visual chart showing how many images fall into each bucket. Highlights imbalanced buckets (too few images = wasted GPU time, too many = overrepresented). Guides user to crop/add images. | Medium | Build on klippbok's existing bucketing preview. Add histogram/bar chart in GUI. Flag buckets with <2 images. |
| **Multi-trainer export** | Export same dataset in formats for kohya/sd-scripts, ai-toolkit, OneTrainer, SimpleTuner. Different folder structures, different config files. | High | kohya: `<repeats>_<class>/` folders + TOML config. ai-toolkit: YAML config. OneTrainer: JSON config. klippbok already has trainer config generators for video; extend for image. |
| **Per-image crop memory** | Remember crop rectangle per image so users can re-export at different resolutions without re-cropping. Store crop as relative coordinates, not absolute pixels. | Medium | Store as {x%, y%, w%, h%} in metadata. Re-apply at any target resolution. Persist in project YAML. |
| **CLIP-based similarity triage** | Use CLIP embeddings to find images that are too similar (redundant) or too different (outlier). klippbok already has this for video. | Low | Already built in klippbok.triage. Just wire to image inputs. Huge value for dataset quality. |
| **Rotation and flip controls** | Fix orientation issues. Some images need 90-degree rotation or horizontal flip. | Low | Standard image manipulation. Include in crop editor. |

---

## Anti-Features

Features to deliberately NOT build. Common mistakes in this domain that waste effort or harm the tool.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Built-in training** | Training is a completely separate domain with GPU requirements, hyperparameter tuning, model selection. Tools that try to do both (CivitAI trainer, SeaArt) are always mediocre at one or both. klippbok should prepare data, not run training. | Export trainer-ready folders and config files. Let kohya/ai-toolkit/OneTrainer handle training. |
| **Image generation / txt2img** | Some tools include generation for "augmenting" datasets. This bloats the tool and generates low-quality training data. Real images beat synthetic images for LoRA training. | Focus on curating real images well. If users need more data, recommend sourcing more images, not generating them. |
| **Upscaling as a feature** | Upscaling images for training is actively harmful -- it adds no real detail and can introduce artifacts. Tools that offer "upscale to training resolution" mislead users. | Show clear red warnings when source resolution is below target. Recommend users find higher-res originals. Never silently upscale. |
| **Complex regularization image management** | Regularization images (class images for DreamBooth) are increasingly considered unnecessary for modern LoRA training, especially with Flux. Building a full reg-image pipeline is wasted effort. | Support the folder structure if users bring their own reg images, but do not generate or manage them. |
| **Real-time collaborative editing** | This is a single-user internal tool. Multi-user features add enormous complexity for zero value in this context. | Single-user FastAPI backend is sufficient. No WebSocket sync, no user accounts, no permissions. |
| **Plugin/extension system** | Over-engineering for a focused tool. Let users contribute via PRs, not plugins. | Keep architecture modular internally but do not expose plugin APIs. |
| **Automatic dataset augmentation** | Flipping, color jittering, random cropping as "data augmentation" -- this is handled by the trainer, not the dataset prep tool. Doing it in prep creates confusion about what the model actually trains on. | Let trainers handle augmentation via their own config (flip_aug, color_aug in kohya). Document this in export notes. |
| **Cloud storage integration** | S3, Google Drive, Dropbox sync -- adds complexity, auth headaches, and network dependencies for a local tool. | Work with local filesystem. Users can sync folders with their own cloud tools. |

---

## Feature Dependencies

```
Image Import (batch)
  |
  v
Image Preview Gallery
  |
  +---> Resolution Display --------+
  |                                 |
  +---> Basic Quality Filtering     |
  |                                 v
  +---> Duplicate Detection    Model-Aware Resolution Presets
  |                                 |
  v                                 v
Aspect Ratio Bucketing <------  Resize to Target
  |                                 |
  v                                 v
Center Crop ----+            Bucket Distribution Viz
                |
                v
        Interactive Crop (snap-to-ratio)  <--- Auto-Crop (subject detection)
                |
                +---> Per-Image Crop Memory
                |
                v
        Caption File Generation
                |
                +---> Manual Caption Editing
                |
                +---> Model-Aware Captioning Defaults
                |       |
                |       +---> WD14 Tagger (booru tags, SD1.5)
                |       +---> VLM Captions (NL, SDXL/Flux)
                |
                +---> Trigger Word Injection
                |
                +---> Batch Tag Operations
                |
                +---> Caption Scoring/Audit
                |
                v
        Batch Export (trainer-ready folder)
                |
                +---> Multi-Trainer Export (kohya, ai-toolkit, OneTrainer)
```

---

## MVP Recommendation

For MVP (first usable release), prioritize these features in order:

### Must Ship (Phase 1 - Core Image Pipeline)
1. **Image import (batch)** -- entry point for everything
2. **Image preview gallery** -- users need to see what they are working with
3. **Resolution display** with green/red quality indicators
4. **Model-aware resolution presets** (512/768/1024 selector)
5. **Aspect ratio bucketing preview** -- reuse klippbok's existing bucketing
6. **Basic quality filtering** -- reuse klippbok's blur/exposure detection
7. **Duplicate detection** -- reuse klippbok's perceptual hashing

### Must Ship (Phase 2 - Crop + Caption)
8. **Center crop** to bucket dimensions
9. **Interactive crop with snap-to-bucket-ratio** -- THE differentiating feature; ship early
10. **Caption file generation** (.txt per image)
11. **Manual caption editing** in gallery view
12. **Model-aware captioning defaults** -- booru tags for SD1.5, NL for SDXL/Flux
13. **Trigger word injection**

### Must Ship (Phase 3 - Export)
14. **Batch export** as trainer-ready folder structure
15. **Multi-trainer export** (kohya format at minimum, others later)

### Defer to Post-MVP
- **Auto-crop with subject detection**: High complexity, center crop + interactive crop covers 90% of cases. Add YOLO-based detection later.
- **Batch tag operations**: Valuable but not blocking. Users can edit captions individually at first.
- **Bucket distribution visualization**: Nice chart but bucketing preview table is sufficient initially.
- **Per-image crop memory**: Store crops in session first; persistent crop memory can come later.
- **CLIP-based similarity triage**: Already exists in klippbok for video; wiring to images is low effort but not MVP-critical.
- **Rotation/flip controls**: Low complexity but can be added after core crop works.

---

## Captioning Strategy by Target Model

This is a critical differentiator -- getting captioning right per model type.

### SD1.5: Booru-Style Tags
- **Format:** Comma-separated keywords: `1girl, solo, long hair, blue eyes, school uniform, standing, outdoors`
- **Tagger:** WD14 (SwinV2 or ConvNextV2 variant) -- best for anime/illustration. DeepDanbooru as fallback.
- **For photos:** BLIP2 tags or manual tagging
- **Trigger word:** Prepend as first tag: `sks, 1girl, solo, ...`
- **Quality indicator:** Tag count (15-40 tags typical), no contradictions

### SDXL: Natural Language (Preferred) or Tags
- **Format:** Descriptive sentence: `A young woman with long blue hair and bright blue eyes stands outdoors wearing a school uniform. The scene is warmly lit with soft afternoon light.`
- **Tagger:** JoyCaption, Florence2, or Gemini API (klippbok already supports Gemini/OpenAI/Replicate)
- **Hybrid approach:** WD14 tags merged into NL sentence structure (popular in community)
- **Trigger word:** Natural integration: `A photo of sks woman standing...`

### Flux: Natural Language (Required)
- **Format:** Detailed NL captions. Flux uses captions more heavily than any prior model.
- **Tagger:** JoyCaption Alpha Two or Florence2. Must be NL, not tags.
- **Caption quality matters more** than for any other model family.
- **Trigger word:** Naturally embedded in caption.

---

## Trainer Export Format Requirements

### kohya/sd-scripts (Most Common)
```
dataset/
  10_sks person/      # <repeats>_<trigger> <class>
    image1.png
    image1.txt         # caption file, same stem
    image2.png
    image2.txt
```
- Config: TOML file with dataset paths, resolution, batch size
- Caption files: `.txt` or `.caption` extension
- Repeats encoded in folder name
- Supports regularization folders separately

### ai-toolkit (Ostris)
```
dataset/
  config.yaml          # dataset config
  images/
    image1.png
    image1.txt
```
- Config: YAML with training parameters
- Flat image directory with paired .txt captions

### OneTrainer
```
dataset/
  config.json
  images/
    image1.png
    image1.txt
```
- Config: JSON format
- Supports multiple concept directories

### SimpleTuner
```
dataset/
  multidatabackend.json   # dataset config
  images/
    image1.png
    image1.txt
```

**Recommendation:** Ship kohya format first (widest adoption), then ai-toolkit. OneTrainer and SimpleTuner as stretch goals.

---

## Sources

- [Civitai: Detailed Flux Training Guide - Dataset Preparation](https://civitai.com/articles/7777/detailed-flux-training-guide-dataset-preparation) -- Comprehensive guide on bucketing, captioning, and quality criteria (MEDIUM confidence)
- [Civitai: Captioning for LoRA Training - JoyCaption + WD14](https://civitai.com/articles/25066/captioning-for-lora-training-joycaption-wd14-ideas) -- Captioning strategy comparison (MEDIUM confidence)
- [kohya_ss folder structure docs](https://github.com/bmaltais/kohya_ss/blob/master/docs/image_folder_structure.md) -- Official folder naming convention (HIGH confidence)
- [malcolmrey/dataset-preparation HF Space](https://huggingface.co/spaces/malcolmrey/dataset-preparation) -- Reference implementation for interactive cropping (HIGH confidence, project context)
- [LoraTag](https://loratag.ai/) -- Commercial captioning tool for reference (LOW confidence)
- [BooruDatasetTagManager](https://github.com/starik222/BooruDatasetTagManager) -- Desktop tag editor for reference (MEDIUM confidence)
- [Stable Diffusion Tag Manager](https://github.com/PMahern/StableDiffusionTagManager) -- Desktop GUI tag manager (MEDIUM confidence)
- [SDXL-Dataset-Tagger](https://github.com/shift-base/SDXL-Dataset-Tagger) -- WD14+BLIP2 auto-tagger (MEDIUM confidence)
- [Apatero: LoRA Training Best Practices 2025](https://apatero.com/blog/lora-training-best-practices-flux-stable-diffusion-2025) -- General best practices (MEDIUM confidence)
- [sanj.dev: LoRA Training 2025 Ultimate Guide](https://sanj.dev/post/lora-training-2025-ultimate-guide) -- Tool landscape overview (MEDIUM confidence)
- klippbok existing codebase analysis -- bucketing, captioning, quality, triage modules (HIGH confidence)
