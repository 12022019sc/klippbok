# Pitfalls Research

**Domain:** Image + video LoRA dataset preparation with web GUI
**Researched:** 2026-02-27
**Confidence:** MEDIUM-HIGH (verified across multiple community sources, official tools, and existing codebase review)

## Critical Pitfalls

### Pitfall 1: Wrong Resolution Targets Per Model

**What goes wrong:**
SD1.5 was trained at 512x512, SDXL at 1024x1024, Flux at varying resolutions. Using the wrong base resolution for bucketing causes training quality degradation -- either wasted VRAM on unnecessarily large images or undertrained details from images that are too small. A common mistake is treating all models the same or confusing which model uses which resolution.

**Why it happens:**
The project already has `VALID_RESOLUTIONS = {480, 720}` hardcoded for Wan video. When extending to image models, developers often copy resolution assumptions from one model to another. Online guides frequently contradict each other -- one earlier search result incorrectly claimed SD1.5 uses 1024x1024 and Flux uses 512x512, which is backwards.

**How to avoid:**
- Define resolution targets per model type in config schema, not as global constants
- SD1.5: base 512, bucketing around 512x512 area (buckets sum to ~1024 total pixels W+H)
- SDXL/Pony/Illustrious: base 1024, bucketing around 1024x1024 area
- Flux: variable, but commonly 512-1024 depending on variant
- Make this a required field in dataset config, not inferred

**Warning signs:**
- All bucket resolutions the same regardless of target model
- Resolution config lives in `defaults.py` as a single constant rather than per-model
- Images getting upscaled to meet minimum resolution (quality loss)

**Phase to address:**
Config schema extension phase -- when adding `ImageConfig` alongside `VideoConfig`, resolution targets must be model-aware from day one.

---

### Pitfall 2: Bucketing Algorithm Produces Unexpected Crops

**What goes wrong:**
Users prepare images at what they think are correct aspect ratios, but the bucketing algorithm assigns them to different buckets than expected, causing significant cropping that cuts off heads, hands, or key subject details. An image at 576x768 (6:8 ratio) may get assigned to a 448x576 bucket (7:9 ratio) because the algorithm optimizes for maximum image area, not aspect ratio preservation.

**Why it happens:**
Bucketing algorithms (as used in kohya/sd-scripts) prioritize keeping the resized image area as large as possible within the bucket constraints. This means aspect ratios shift subtly. Additionally, bucket width + height must meet minimum thresholds, and buckets need at least 2 images to be useful for training. The interaction between these constraints is non-obvious.

**How to avoid:**
- In the interactive cropper, show the user which bucket their crop will land in BEFORE they confirm
- Display the actual bucket dimensions and the resulting crop overlay
- Limit supported aspect ratios to a curated set per model (e.g., for SD1.5 at 512 base: 1:1, 2:3, 3:2, 3:4, 4:3, 9:16, 16:9) and snap the crop tool to these
- Show bucket distribution statistics in the dataset view so users can see if a bucket has only 1 image (ineffective for training)

**Warning signs:**
- Users crop images but training results show clipped subjects
- Bucket distribution is highly unbalanced (many single-image buckets)
- Auto-crop produces different results than what the preview showed

**Phase to address:**
Interactive cropping phase -- the crop UI must be bucket-aware from the start, not added as an afterthought.

---

### Pitfall 3: Bolting GUI State onto a Stateless CLI Pipeline

**What goes wrong:**
The existing klippbok pipeline is stateless: each CLI command reads files from disk, processes them, and writes results. Adding a GUI that expects persistent state (current dataset, processing progress, undo history, selected images) creates a mismatch. Developers end up with two systems: the CLI's file-based state and the GUI's in-memory state, which drift apart. Users make changes in the GUI, but the underlying files don't reflect them until explicit save. Or worse, CLI operations invalidate the GUI state.

**Why it happens:**
The path of least resistance is wrapping each CLI function with an API endpoint. But CLIs are fire-and-forget while GUIs are interactive and stateful. The GUI needs to know "what has changed since last refresh" and "what is the current state of the dataset," which the CLI never needed to answer.

**How to avoid:**
- Define a clear boundary: the GUI operates on a "project" abstraction backed by a manifest file, not directly on the CLI pipeline
- The API layer should own a `ProjectState` model (Pydantic) that tracks: dataset path, processing status, selected images, crop decisions, tag edits
- Persist state to a project file (JSON/YAML) so the GUI can resume sessions
- CLI and GUI share the same underlying functions but the GUI adds a state layer on top
- Never let the GUI call CLI commands via subprocess -- import and call the Python functions directly

**Warning signs:**
- API endpoints that shell out to CLI commands
- GUI shows stale data after backend processing
- No way to resume a partially-completed editing session
- "Refresh" button needed to see current state

**Phase to address:**
API layer design phase -- must be resolved before building any frontend. The state management architecture determines everything downstream.

---

### Pitfall 4: Tag System Conflates Booru Tags and Natural Language Captions

**What goes wrong:**
SD1.5 models (trained on booru data) expect comma-separated danbooru-style tags: `1girl, solo, blue_eyes, long_hair, school_uniform`. SDXL/Flux models expect natural language captions: "A girl with blue eyes and long hair wearing a school uniform." Building a single tagging interface that treats these as the same thing produces captions that work for neither model well.

**Why it happens:**
Both are "text that describes an image" so they seem interchangeable. But booru tags have strict conventions: specific tag vocabulary, underscores not spaces, ordering conventions (character tags before clothing before background), quality tags (`masterpiece, best quality`), and "anti-tags" (`lowres, bad anatomy`). Natural language captions have none of these constraints.

**How to avoid:**
- Implement two distinct caption modes in the config schema: `tag` mode and `caption` mode
- For tag mode: provide autocomplete from a danbooru tag database, enforce comma separation, support tag categories (general, character, copyright, meta), and offer quality tag presets
- For caption mode: freeform text with optional VLM-generated suggestions
- Store both formats in the caption file if the user wants dual-model support (some tools support this with a separator)
- The UI must clearly indicate which mode is active and format accordingly
- Auto-tagging threshold should default to 0.5-0.7 for booru tags (lower = too many irrelevant tags, higher = missing important ones)

**Warning signs:**
- Single text field for all caption types
- Booru tags written with spaces instead of underscores
- No tag vocabulary validation or autocomplete
- Natural language captions getting comma-split into pseudo-tags

**Phase to address:**
Tagging/captioning phase -- needs to be designed as two separate systems sharing a UI framework, not one system with a format toggle.

---

### Pitfall 5: Browser Canvas Chokes on High-Resolution Source Images

**What goes wrong:**
LoRA source images are often 2048x2048 or larger (the Civitai guide mentions up to 4096px for off-site training). Loading these directly into an HTML5 Canvas for interactive cropping causes browser tab crashes, severe lag, or "canvas size exceeds maximum" errors. Mobile browsers and lower-end machines fail first.

**Why it happens:**
Canvas elements have hard pixel limits (varies by browser: Chrome ~16384x16384, Safari ~4096x4096 on iOS). Even within limits, a 4096x4096 RGBA image consumes 64MB of raw bitmap memory per canvas. Multiple images loaded for a gallery view multiply this. React re-renders with large canvas state cause frame drops.

**How to avoid:**
- Never load full-resolution images into the browser canvas for cropping
- Generate server-side preview thumbnails (e.g., max 1024px longest side) for the crop UI
- Send crop coordinates back to the server; perform the actual crop on the full-resolution image server-side using PIL/Pillow
- Use `loading="lazy"` and virtualized lists for image galleries
- For the crop component itself, use `useRef` for DOM manipulation instead of React state (React state updates on every mouse move during drag cause severe jank, as documented in the react-image-crop community)

**Warning signs:**
- Browser tab memory exceeds 500MB when viewing dataset
- Crop preview stutters or lags during drag
- "Canvas exceeds maximum size" errors in console
- Images load as broken/blank on some devices

**Phase to address:**
Frontend implementation phase -- the thumbnail generation API endpoint must exist before the crop UI is built.

---

### Pitfall 6: Auto-Crop Subject Detection Fails on Non-Human Subjects

**What goes wrong:**
Subject detection models (YOLO, face detection, saliency maps) are heavily biased toward human faces and bodies. For LoRA training of objects, animals, vehicles, environments, or anime characters, auto-crop centers on the wrong region or fails to detect any subject at all, defaulting to center-crop which randomly clips the actual subject.

**Why it happens:**
Most readily available subject detection models were trained on photo datasets dominated by human subjects. Anime/illustration detection requires specialized models. Object detection for arbitrary categories requires either a general-purpose detector (slower, less precise) or category-specific models (impractical to maintain).

**How to avoid:**
- Use auto-crop as a suggestion, not a final decision -- always show the proposed crop for user confirmation
- Implement multiple detection strategies: face detection (for portraits), saliency detection (for general content), center-crop (fallback)
- For anime content, consider using anime-specific face detectors (e.g., lbpcascade_animeface or similar)
- Allow users to set a "subject hint" per dataset (person, object, scene) that selects the detection strategy
- The crop UI should make it trivial to adjust auto-crop results manually (drag to reposition, not re-draw from scratch)

**Warning signs:**
- Auto-crop consistently centers on faces even for full-body character LoRAs
- Environment/object datasets get random crops
- No manual override path for failed auto-detection
- Detection confidence scores not surfaced to the user

**Phase to address:**
Auto-crop implementation phase -- must design for fallback and manual override from the start.

---

### Pitfall 7: Silent Error Swallowing in Existing Pipeline Breaks GUI Feedback

**What goes wrong:**
The existing klippbok codebase has multiple `except Exception as e` blocks (at least 15+ instances found in triage.py, split.py, __main__.py) that log errors but continue processing. In a CLI context, users see the log output and notice failures. In a GUI context, these silent failures cause datasets with missing images, incomplete captions, or dropped clips -- with no indication to the user that something went wrong.

**Why it happens:**
CLI tools are designed to be resilient: process what you can, skip what you cannot, report at the end. GUIs expect real-time feedback: show progress, surface errors immediately, let users decide how to handle failures.

**How to avoid:**
- Before wrapping existing functions in API endpoints, audit and categorize all exception handlers:
  - **Fatal errors** (should stop processing and notify user): file not found, permission denied, out of memory
  - **Recoverable errors** (should flag item and continue): single image corrupt, single caption API timeout
  - **Warnings** (should log but not block): non-standard format, slight resolution mismatch
- Implement a structured error reporting system: each processing function returns a result object with `success`, `warnings`, and `errors` fields
- The GUI should display a per-item status (success/warning/error) in the dataset view
- Existing `try/except Exception` blocks must be reviewed and tightened to specific exception types

**Warning signs:**
- Processing "completes" but output has fewer items than input with no explanation
- GUI shows 100% progress but some items are missing
- Error logs exist but GUI shows no errors
- No per-item status in dataset view

**Phase to address:**
API layer phase -- error handling refactor must happen before GUI integration, or the GUI will inherit all the CLI's silent failure modes.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Storing crop coordinates in filename (e.g., `img_x100_y200_w512_h512.png`) | No database needed | Filenames become unreadable, can't store multiple crop versions, breaks on rename | Never -- use a sidecar JSON or manifest |
| Loading CLIP model per API request | Simple stateless API | 2-3 second load time per request, 2GB+ memory churn | Never -- use a singleton loaded at startup (already identified as existing issue) |
| Performing image processing in the API request handler (synchronous) | Simple implementation | Blocks the event loop, timeouts on large batches, no progress reporting | Only for single-image operations under 1 second |
| Storing tags as a flat comma-separated string | Matches caption file format | Cannot distinguish tag categories, no structured editing, no tag frequency analysis | MVP only -- migrate to structured tag objects before building advanced tag features |
| Using FastAPI BackgroundTasks for batch processing | No Celery/Redis dependency | No persistence (lost on restart), no retry, no progress tracking, no cancellation | Single-user internal tool with batches under 100 items |
| Generating thumbnails on-demand per request | No pre-processing step needed | Repeated work, slow gallery load, no caching | Never -- generate thumbnails once on import and cache |

## Integration Gotchas

Common mistakes when connecting to external services and tools.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| VLM captioning (Gemini/OpenAI) for images | Sending full-resolution images to the API | Resize to ~1024px max before API call -- saves bandwidth, cost, and often improves caption quality (less noise) |
| danbooru tag autocomplete | Bundling the entire danbooru tag database (~500K+ tags) into the frontend | Load a curated subset (~10K most common tags) at startup, use server-side search for the long tail |
| CLIP embeddings for triage | Running CLIP inference on every image every time triage is triggered | Cache embeddings per image (keyed by file hash), only recompute when image changes |
| kohya/sd-scripts config generation | Hardcoding training parameters into the config template | Generate dataset section only (paths, buckets, captions), leave training params as clearly-marked user-editable sections with sensible defaults |
| React dev server to FastAPI proxy | CORS configuration in production that differs from dev | Use Vite proxy in dev (`/api` -> `localhost:8000`), serve React build from FastAPI's static files in production -- single origin, no CORS needed |

## Performance Traps

Patterns that work at small scale but fail as dataset size grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Loading all dataset images into memory for gallery view | Works fine with 20 images | Virtualized list (react-window or similar), paginated API, lazy loading | 200+ images (browser tab > 1GB) |
| Re-reading all caption files on every dataset refresh | Fast with 10 files | Cache captions in project state, invalidate on file change (watchdog or mtime check) | 500+ caption files (noticeable delay) |
| Computing perceptual hashes for duplicate detection on every validation | Works in seconds for small sets | Cache hashes per image (keyed by path + mtime), incremental updates only | 1000+ images (O(n^2) comparisons) |
| Sequential image processing in API handlers | Acceptable for 5 images | Use `asyncio.gather` or `concurrent.futures.ThreadPoolExecutor` for batch operations | 50+ images (request timeout) |
| Full-size image transfer over API for crop preview | Fast on localhost | Return thumbnail URLs, load full-size only when user clicks to edit | 100+ images in gallery (network saturation even on localhost) |
| Unthrottled WebSocket progress updates | Works fine | Throttle to max 10 updates/second, batch progress for multi-item operations | 500+ items processing (WebSocket message flood) |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Serving raw filesystem paths in API responses | Path traversal if GUI sends modified paths back to API for operations | Use opaque IDs or relative paths from a configured root; validate all paths are within the project directory |
| Accepting arbitrary image URLs for download without validation | SSRF if server fetches from user-provided URLs | For a single-user internal tool this is low risk, but still validate URLs against allowlists if implemented |
| Storing VLM API keys in the project manifest file | Keys committed to git if manifest is tracked | Keep API keys in `.env` only (already the pattern), never in project state files |
| No rate limiting on VLM caption API calls | Accidental API bill spike from batch re-captioning | Add confirmation dialog for batch operations, show estimated API cost, implement a configurable rate limit |

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Crop tool without undo/history | User accidentally saves a bad crop, original is overwritten | Always keep original image, store crops as coordinates in manifest, generate cropped versions on export |
| No visual diff between original and cropped version | User cannot assess crop quality without switching views | Side-by-side or overlay toggle showing original vs. crop with bucket grid overlay |
| Tag editor without bulk operations | Editing tags one image at a time for a 200-image dataset | Multi-select images, apply/remove tags in bulk, "apply to all similar" based on CLIP similarity |
| Progress indication only at batch level ("Processing... 47%") | User has no idea which images succeeded or failed | Per-item status icons in the gallery (pending/processing/success/warning/error), click to see details |
| Dataset export with no dry-run preview | User generates a 500-image dataset, discovers bucket distribution is bad, must redo | Show bucket distribution, sample grid, and estimated training parameters BEFORE export |
| Forcing sequential workflow (import -> crop -> tag -> export) | User cannot tag while reviewing crops, or revisit crops after tagging | Non-linear workflow: all operations available on any image at any time, dataset validation runs continuously |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Image cropping:** Often missing EXIF rotation handling -- verify images display correctly regardless of EXIF orientation tag (common with phone photos)
- [ ] **Bucketing:** Often missing the minimum-images-per-bucket check -- verify no bucket contains only 1 image (training will not optimize these effectively)
- [ ] **Tag autocomplete:** Often missing tag alias resolution -- verify that searching "1girl" also finds "solo female" and vice versa (danbooru has extensive alias tables)
- [ ] **Caption files:** Often missing encoding validation -- verify all .txt files are UTF-8 (Windows tools sometimes produce UTF-16 or Latin-1, which training scripts may not handle)
- [ ] **Dataset export:** Often missing the "trigger word in every caption" check -- verify the anchor/trigger word appears in all caption files (SD1.5 LoRAs require this for activation)
- [ ] **Image format:** Often missing alpha channel handling -- verify PNG images with transparency are converted to RGB before training (alpha channels cause dimension mismatches)
- [ ] **Resolution validation:** Often missing the "minimum dimension" check for bucketing -- verify no image dimension falls below the model's minimum (e.g., 256px for SD1.5 buckets)
- [ ] **Gallery view:** Often missing sort/filter -- verify users can sort by resolution, aspect ratio, tag count, and filter by validation status
- [ ] **WebSocket progress:** Often missing reconnection logic -- verify the frontend reconnects and recovers state after a brief network interruption or browser tab sleep

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Wrong resolution targets used for entire dataset | MEDIUM | Re-run bucketing with correct target resolution; crops may need review but originals should be preserved |
| Unexpected bucket crops cut off subjects | LOW | If originals preserved: adjust crop coordinates in manifest, re-export. If originals overwritten: HIGH cost, must re-source images |
| GUI state out of sync with filesystem | LOW | Implement a "rescan" operation that rebuilds project state from filesystem; design for this from the start |
| Tags in wrong format (NL captions where booru tags expected) | MEDIUM | Batch re-tag using auto-tagger with correct mode; manual review still needed for quality |
| Browser crashes on large datasets | LOW | Implement pagination/virtualization retroactively; existing data is unaffected |
| Silent processing errors produced incomplete dataset | MEDIUM | Re-run validation on output dataset; re-process failed items. Worse if failures were not logged at all |
| CLIP model loaded per request causing OOM | LOW | Refactor to singleton pattern; the fix is straightforward but must be done before scaling |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Wrong resolution targets | Config schema extension | Unit test: each model type produces correct bucket dimensions |
| Unexpected bucket crops | Interactive cropping UI | Integration test: crop coordinates map to expected bucket; visual QA |
| GUI state vs CLI state mismatch | API layer architecture | Test: modify via API, verify filesystem; modify filesystem, verify API reflects change |
| Tag/caption format confusion | Tagging system design | Unit test: tag mode produces comma-separated booru format; caption mode produces NL |
| Canvas memory on large images | Frontend image handling | Load test: open gallery with 500 images at 2048px, measure memory |
| Auto-crop fails on non-human subjects | Auto-crop implementation | Test with object, animal, and anime datasets; measure detection hit rate |
| Silent error swallowing | Error handling refactor (pre-GUI) | Audit: zero bare `except Exception` blocks; all errors surface in API response |
| Originals overwritten by crops | Image storage architecture | Verify: original images never modified; crops stored as coordinates or separate files |
| Single-image CLIP load per instance | API startup / singleton pattern | Verify: CLIP model loaded once at startup, shared across requests |
| No progress reporting for batch operations | WebSocket/SSE implementation | Test: batch process 100 images, verify per-item progress updates received by frontend |

## Sources

- [Civitai: Opinionated Guide to All LoRA Training (2025 Update)](https://civitai.com/articles/1716/opinionated-guide-to-all-lora-training-2025-update) -- dataset quality and resolution guidance
- [Sable Confusion: How Are Images Assigned to Buckets](https://medium.com/@sableconfusion/lora-training-practice-in-kohya-ss-how-are-images-assigned-to-buckets-19b2a3e97c6c) -- bucket assignment algorithm details
- [Sable Confusion: Don't "Don't Upscale Bucket Resolution"](https://medium.com/@sableconfusion/dont-don-t-upscale-bucket-resolution-9905d7f98ce2) -- bucketing tradeoffs
- [kohya_ss Discussion #2861: How Does Bucketing Work](https://github.com/bmaltais/kohya_ss/discussions/2861) -- bucket algorithm behavior
- [DEV.to: Building a React Image Cropper - Unexpected Problems](https://dev.to/mjoycemilburn/building-a-react-image-cropper-a-whole-world-of-unexpected-problems-300i) -- canvas, CORS, React state performance issues
- [FastAPI GitHub Discussion #6741: WebSocket Pauses Background Tasks](https://github.com/fastapi/fastapi/discussions/6741) -- background task + WebSocket interaction bug
- [FastAPI Docs: Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) -- limitations of built-in background tasks
- [Civitai: Automated Anime Character Dataset](https://civitai.com/articles/218/automated-anime-character-dataset-for-character-loras) -- auto-tagging thresholds and pitfalls
- [Civitai: Detailed Flux Training Guide: Dataset Preparation](https://civitai.com/articles/7777/detailed-flux-training-guide-dataset-preparation) -- focus crop vs center crop
- [NovelAI Aspect Ratio Bucketing](https://github.com/NovelAI/novelai-aspect-ratio-bucketing) -- reference bucketing implementation
- [Klippbok codebase review (2026-02-26)](../docs/codebase-review.md) -- existing error handling patterns, file size violations, sequential processing issues
- [Klippbok image/SD1.5 support analysis (2026-02-26)](../docs/image-sd15-support-analysis.md) -- Wan coupling points, image-ready components

---
*Pitfalls research for: klippbok image+GUI extension*
*Researched: 2026-02-27*
