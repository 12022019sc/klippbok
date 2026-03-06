# Cleanup Subject Definition — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a subject definition step to the Cleanup page so users can specify what they're looking for (via text description or reference images) before scanning, replacing the hardcoded "woman" CLIP prompts.

**Architecture:** Two classification modes share the same SSE pipeline and review UI. Text mode generates CLIP text prompts from a user description. Reference mode computes CLIP image-to-image similarity against 1-3 gallery images picked by the user. Both modes keep InsightFace face detection as a boost signal.

**Tech Stack:** Python (FastAPI, Pydantic, CLIP via HuggingFace Transformers), React (TypeScript, Zustand store), existing CLIPEmbedder singleton.

---

### Task 1: Backend — Prompt generation and reference classification functions

**Files:**
- Modify: `klippbok/services/cleanup_service.py`
- Test: `tests/test_cleanup_service.py`

**Step 1: Write the failing tests**

Add a new test class at the end of `tests/test_cleanup_service.py`:

```python
# At top — add to existing imports:
from klippbok.services.cleanup_service import (
    # ...existing imports...
    generate_prompts_from_description,
    classify_item_by_reference,
    DEFAULT_REFERENCE_THRESHOLD,
)


class TestGeneratePrompts:
    """Test prompt generation from subject description."""

    def test_generates_positive_prompts_from_description(self):
        pos, neg = generate_prompts_from_description("woman with dark hair")
        assert len(pos) >= 3
        assert any("woman with dark hair" in p for p in pos)
        # Negative prompts should be the defaults
        assert "screenshot" in neg

    def test_empty_description_raises(self):
        with pytest.raises(ValueError, match="empty"):
            generate_prompts_from_description("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            generate_prompts_from_description("   ")


class TestClassifyItemByReference:
    """Test single-item reference-based classification."""

    def test_high_similarity_returns_keep(self, tmp_path: Path):
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        embedder = MagicMock()
        # Image embedding very similar to reference
        image_emb = np.array([0.9, 0.1, 0.0], dtype=np.float32)
        image_emb = image_emb / np.linalg.norm(image_emb)
        embedder.encode_image.return_value = image_emb

        ref_emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        ref_emb = ref_emb / np.linalg.norm(ref_emb)

        result = classify_item_by_reference(
            image_path=img,
            embedder=embedder,
            reference_embeddings=[ref_emb],
            clip_threshold=DEFAULT_REFERENCE_THRESHOLD,
            face_app=None,
            project_dir=tmp_path,
        )

        assert result.label == "keep"
        assert result.clip_score > 0.8

    def test_low_similarity_returns_remove(self, tmp_path: Path):
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        embedder = MagicMock()
        # Image embedding orthogonal to reference
        image_emb = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        embedder.encode_image.return_value = image_emb

        ref_emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        result = classify_item_by_reference(
            image_path=img,
            embedder=embedder,
            reference_embeddings=[ref_emb],
            clip_threshold=DEFAULT_REFERENCE_THRESHOLD,
            face_app=None,
            project_dir=tmp_path,
        )

        assert result.label == "remove"
        assert result.clip_score < 0.2

    def test_multiple_references_uses_max(self, tmp_path: Path):
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        embedder = MagicMock()
        image_emb = np.array([0.9, 0.1, 0.0], dtype=np.float32)
        image_emb = image_emb / np.linalg.norm(image_emb)
        embedder.encode_image.return_value = image_emb

        # Two references: one similar, one orthogonal
        ref1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        ref1 = ref1 / np.linalg.norm(ref1)
        ref2 = np.array([0.0, 0.0, 1.0], dtype=np.float32)

        result = classify_item_by_reference(
            image_path=img,
            embedder=embedder,
            reference_embeddings=[ref1, ref2],
            clip_threshold=DEFAULT_REFERENCE_THRESHOLD,
            face_app=None,
            project_dir=tmp_path,
        )

        # Should use max similarity (against ref1)
        assert result.clip_score > 0.8
```

**Step 2: Run tests to verify they fail**

Run: `cd /c/Dev/Projects/klippbok-main && .venv/Scripts/python.exe -m pytest tests/test_cleanup_service.py::TestGeneratePrompts -v 2>&1 | tail -5`
Expected: FAIL with `ImportError` — functions don't exist yet.

**Step 3: Implement the functions**

In `klippbok/services/cleanup_service.py`:

1. Add constant after `DEFAULT_CLEANUP_THRESHOLD` (line 60):
```python
DEFAULT_REFERENCE_THRESHOLD: float = 0.65
```

2. Add `generate_prompts_from_description` function after `_classify_label` (after line 127):
```python
def generate_prompts_from_description(
    description: str,
) -> tuple[list[str], list[str]]:
    """Generate CLIP text prompts from a user-provided subject description.

    Creates varied positive prompts from the description and returns the
    default negative prompts unchanged.

    Args:
        description: User's subject description (e.g., "woman with dark hair").

    Returns:
        Tuple of (positive_prompts, negative_prompts).

    Raises:
        ValueError: If description is empty or whitespace-only.
    """
    desc = description.strip()
    if not desc:
        raise ValueError("Subject description cannot be empty")

    positive = [
        f"photo of {desc}",
        f"portrait of {desc}",
        f"{desc} posing",
        f"selfie of {desc}",
        f"photo of a {desc}" if not desc.startswith("a ") else f"photo of {desc}",
    ]
    return positive, list(DEFAULT_NEGATIVE_PROMPTS)
```

3. Add `classify_item_by_reference` function after `classify_item` (after line 202):
```python
def classify_item_by_reference(
    image_path: Path,
    embedder: Any,
    reference_embeddings: list[np.ndarray],
    clip_threshold: float,
    face_app: Any | None,
    project_dir: Path | None = None,
) -> CleanupClassification:
    """Classify a single image by CLIP image-to-image similarity against references.

    Computes cosine similarity between the image embedding and each reference
    embedding. Uses the max similarity as the clip_score.

    Args:
        image_path: Path to the image file.
        embedder: CLIPEmbedder instance.
        reference_embeddings: Pre-computed reference image embeddings.
        clip_threshold: Similarity threshold for face detection trigger.
        face_app: InsightFace app or None.
        project_dir: Project root for relative path computation.

    Returns:
        CleanupClassification with similarity score and label.
    """
    image_emb = embedder.encode_image(image_path)

    # Max cosine similarity against all reference embeddings
    max_sim = max(
        (float(np.dot(image_emb, ref_emb)) for ref_emb in reference_embeddings),
        default=0.0,
    )

    # Face detection boost (same layered approach)
    has_face = False
    if max_sim >= clip_threshold and face_app is not None:
        try:
            cv2_image = cv2.imread(str(image_path))
            if cv2_image is not None:
                faces = face_app.get(cv2_image)
                has_face = len(faces) > 0
        except Exception as exc:
            logger.warning("Face detection failed for %s: %s", image_path, exc)

    confidence = compute_confidence(max_sim, has_face, clip_threshold)
    label = _classify_label(confidence)

    if project_dir is not None:
        relative_path = str(image_path.relative_to(project_dir))
    else:
        relative_path = str(image_path)
    item_id = hashlib.sha256(relative_path.encode()).hexdigest()[:16]

    return CleanupClassification(
        item_path=str(image_path),
        item_id=item_id,
        clip_score=max_sim,
        has_face=has_face,
        confidence=confidence,
        label=label,
    )
```

4. Add `classify_items_by_reference` batch function after `classify_items` (after line 285):
```python
def classify_items_by_reference(
    item_paths: list[Path],
    project_dir: Path,
    reference_paths: list[Path],
    clip_threshold: float = DEFAULT_REFERENCE_THRESHOLD,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[CleanupClassification]:
    """Classify a batch of media items using CLIP image-to-image similarity.

    Reference images are encoded ONCE before the loop. Each gallery item
    is compared against all references; max similarity is used.

    Args:
        item_paths: List of image/video paths to classify.
        project_dir: Project root directory.
        reference_paths: List of reference image file paths (1-3).
        clip_threshold: Similarity threshold. Default 0.65 for reference mode.
        progress_callback: Optional callable(current, total) per item.

    Returns:
        List of CleanupClassification, one per input path.
    """
    from klippbok.services.triage_service import _get_or_create_embedder
    from klippbok.services.face_service import check_insightface_available, _get_face_app

    embedder = _get_or_create_embedder()

    # Encode ALL reference images ONCE
    reference_embeddings = embedder.encode_images(reference_paths)

    face_app = None
    if check_insightface_available():
        try:
            face_app = _get_face_app()
        except Exception as exc:
            logger.warning("Failed to initialize InsightFace: %s", exc)

    total = len(item_paths)
    results: list[CleanupClassification] = []

    for i, item_path in enumerate(item_paths, 1):
        item_path = Path(item_path)
        suffix = item_path.suffix.lower()

        if suffix in VIDEO_EXTENSIONS:
            result = _classify_video_by_reference(
                item_path, embedder, reference_embeddings,
                clip_threshold, face_app, project_dir=project_dir,
            )
        else:
            result = classify_item_by_reference(
                item_path, embedder, reference_embeddings,
                clip_threshold, face_app, project_dir=project_dir,
            )

        results.append(result)

        if progress_callback is not None:
            progress_callback(i, total)

    return results
```

5. Add `_classify_video_by_reference` after `_classify_video` (after line 377):
```python
def _classify_video_by_reference(
    video_path: Path,
    embedder: Any,
    reference_embeddings: list[np.ndarray],
    clip_threshold: float,
    face_app: Any | None,
    num_frames: int = 3,
    project_dir: Path | None = None,
) -> CleanupClassification:
    """Classify a video by sampling frames and comparing against reference embeddings."""
    _ensure_sampler_imports()

    try:
        frame_paths = sample_clip_frames(video_path, count=num_frames)
    except Exception as exc:
        logger.warning("Frame sampling failed for %s: %s", video_path, exc)
        frame_paths = []

    if not frame_paths:
        rel = str(video_path.relative_to(project_dir)) if project_dir else str(video_path)
        item_id = hashlib.sha256(rel.encode()).hexdigest()[:16]
        return CleanupClassification(
            item_path=str(video_path), item_id=item_id,
            clip_score=0.0, has_face=False, confidence=0.0, label="remove",
        )

    best_result: CleanupClassification | None = None
    for frame_path in frame_paths:
        result = classify_item_by_reference(
            frame_path, embedder, reference_embeddings,
            clip_threshold, face_app,
        )
        if best_result is None or result.clip_score > best_result.clip_score:
            best_result = result

    try:
        cleanup_frames(frame_paths)
    except Exception:
        pass

    rel = str(video_path.relative_to(project_dir)) if project_dir else str(video_path)
    item_id = hashlib.sha256(rel.encode()).hexdigest()[:16]
    return CleanupClassification(
        item_path=str(video_path), item_id=item_id,
        clip_score=best_result.clip_score, has_face=best_result.has_face,
        confidence=best_result.confidence, label=best_result.label,
    )
```

6. Update the module docstring exports list (line 17) to include the new functions:
```python
"""...
Exports: classify_item, classify_items, classify_item_by_reference,
         classify_items_by_reference, compute_confidence, confirm_removal,
         generate_prompts_from_description,
         CleanupClassification, DEFAULT_CLEANUP_THRESHOLD, DEFAULT_REFERENCE_THRESHOLD
"""
```

**Step 4: Run tests to verify they pass**

Run: `cd /c/Dev/Projects/klippbok-main && .venv/Scripts/python.exe -m pytest tests/test_cleanup_service.py -v 2>&1 | tail -15`
Expected: All tests PASS (existing + new).

**Step 5: Commit**

```bash
git add klippbok/services/cleanup_service.py tests/test_cleanup_service.py
git commit -m "feat: add prompt generation and reference classification to cleanup service"
```

---

### Task 2: Backend — Update cleanup router for text/reference modes

**Files:**
- Modify: `klippbok/api/routers/cleanup.py`

**Step 1: Update the request model and imports**

Replace `CleanupStartRequest` (lines 54-58) and update imports (lines 34-37):

```python
# Updated imports
from klippbok.services.cleanup_service import (
    classify_items,
    classify_items_by_reference,
    confirm_removal,
    generate_prompts_from_description,
    DEFAULT_REFERENCE_THRESHOLD,
)
```

```python
class CleanupStartRequest(BaseModel):
    """Request body for starting a cleanup scan."""
    mode: Literal["text", "reference"] = "text"
    subject_description: str | None = None
    reference_image_ids: list[str] | None = None
    clip_threshold: float | None = None  # None = use mode default
```

Add at top of file:
```python
from typing import Literal
```

**Step 2: Add helper to resolve image IDs to file paths**

After `_resolve_item_paths` (after line 94), add:

```python
def _resolve_image_ids_to_paths(
    project_dir: Path, image_ids: list[str],
) -> list[Path]:
    """Resolve gallery image IDs to file paths via the manifest.

    Args:
        project_dir: Project root directory.
        image_ids: List of SHA256[:16] image IDs.

    Returns:
        List of resolved Path objects.

    Raises:
        HTTPException 400: If any image ID cannot be resolved.
    """
    import hashlib

    manifest_path = project_dir / ".klippbok" / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=400, detail="No manifest found")

    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    images = manifest.get("images", [])

    # Build id -> path lookup
    id_to_path: dict[str, Path] = {}
    for entry in images:
        rel = entry.get("path", "")
        img_id = hashlib.sha256(rel.encode()).hexdigest()[:16]
        id_to_path[img_id] = project_dir / rel

    paths = []
    for img_id in image_ids:
        if img_id not in id_to_path:
            raise HTTPException(
                status_code=400,
                detail=f"Image ID {img_id} not found in manifest",
            )
        path = id_to_path[img_id]
        if not path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Image file not found for ID {img_id}",
            )
        paths.append(path)

    return paths
```

**Step 3: Update `_run_cleanup_bg` to support both modes**

Replace the signature and body of `_run_cleanup_bg` (lines 102-189):

```python
async def _run_cleanup_bg(
    op_id: str,
    project_dir: Path,
    mode: str,
    positive_prompts: list[str] | None,
    negative_prompts: list[str] | None,
    clip_threshold: float,
    reference_paths: list[Path] | None,
) -> None:
    """Background coroutine that runs the cleanup classification pipeline.

    Routes to text-based or reference-based classification depending on mode.
    """
    loop = asyncio.get_running_loop()
    queue = _cleanup_queues[op_id]

    try:
        item_paths = await loop.run_in_executor(
            None,
            lambda: _resolve_item_paths(project_dir),
        )

        total = len(item_paths)

        mode_label = "by reference images" if mode == "reference" else "by text description"
        await queue.put({
            "event": "cleanup_progress",
            "data": {
                "operation_id": op_id,
                "current": 0,
                "total": total,
                "message": f"Starting cleanup scan {mode_label} on {total} items...",
            },
        })

        def progress_callback(current: int, total: int) -> None:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {
                    "event": "cleanup_progress",
                    "data": {
                        "operation_id": op_id,
                        "current": current,
                        "total": total,
                        "message": f"Classifying item {current} of {total}",
                    },
                },
            )

        if mode == "reference" and reference_paths:
            results = await loop.run_in_executor(
                None,
                lambda: classify_items_by_reference(
                    item_paths=item_paths,
                    project_dir=project_dir,
                    reference_paths=reference_paths,
                    clip_threshold=clip_threshold,
                    progress_callback=progress_callback,
                ),
            )
        else:
            results = await loop.run_in_executor(
                None,
                lambda: classify_items(
                    item_paths=item_paths,
                    project_dir=project_dir,
                    positive_prompts=positive_prompts,
                    negative_prompts=negative_prompts,
                    clip_threshold=clip_threshold,
                    progress_callback=progress_callback,
                ),
            )

        result_dicts = [r.model_dump() for r in results]
        _cleanup_results[op_id] = result_dicts

        await queue.put({
            "event": "cleanup_done",
            "data": {
                "operation_id": op_id,
                "current": total,
                "total": total,
                "message": f"Cleanup complete: {len(results)} items classified.",
                "status": "complete",
                "results": result_dicts,
            },
        })

    except Exception as exc:
        logger.error("Cleanup operation %s failed: %s", op_id, exc)
        await queue.put({
            "event": "cleanup_error",
            "data": {
                "operation_id": op_id,
                "message": f"Cleanup failed: {exc}",
            },
        })

    finally:
        await queue.put(None)
```

**Step 4: Update `start_cleanup` endpoint**

Replace the `start_cleanup` function (lines 243-275):

```python
@router.post("/start")
async def start_cleanup(body: CleanupStartRequest, request: Request) -> dict:
    """Start a cleanup classification scan in the background.

    Supports two modes:
    - "text": User provides a subject description, CLIP text-to-image matching.
    - "reference": User provides gallery image IDs, CLIP image-to-image matching.
    """
    project_dir: Path | None = request.app.state.project_dir
    if project_dir is None:
        raise HTTPException(status_code=409, detail="No project directory selected")

    # Validate mode-specific fields
    positive_prompts = None
    negative_prompts = None
    reference_paths = None

    if body.mode == "text":
        if not body.subject_description:
            raise HTTPException(
                status_code=400,
                detail="subject_description is required for text mode",
            )
        positive_prompts, negative_prompts = generate_prompts_from_description(
            body.subject_description,
        )
        threshold = body.clip_threshold if body.clip_threshold is not None else 0.25
    elif body.mode == "reference":
        if not body.reference_image_ids or len(body.reference_image_ids) == 0:
            raise HTTPException(
                status_code=400,
                detail="reference_image_ids is required for reference mode (1-3 images)",
            )
        if len(body.reference_image_ids) > 3:
            raise HTTPException(
                status_code=400,
                detail="Maximum 3 reference images allowed",
            )
        reference_paths = _resolve_image_ids_to_paths(
            project_dir, body.reference_image_ids,
        )
        threshold = body.clip_threshold if body.clip_threshold is not None else DEFAULT_REFERENCE_THRESHOLD
    else:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {body.mode}")

    op_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _cleanup_queues[op_id] = queue

    task = asyncio.create_task(
        _run_cleanup_bg(
            op_id, project_dir,
            mode=body.mode,
            positive_prompts=positive_prompts,
            negative_prompts=negative_prompts,
            clip_threshold=threshold,
            reference_paths=reference_paths,
        ),
        name=f"cleanup-{op_id}",
    )
    _cleanup_tasks[op_id] = task

    logger.info("Started cleanup operation %s (mode=%s)", op_id, body.mode)
    return {"operation_id": op_id}
```

**Step 5: Run existing tests to verify nothing broke**

Run: `cd /c/Dev/Projects/klippbok-main && .venv/Scripts/python.exe -m pytest tests/test_cleanup_service.py -v 2>&1 | tail -15`
Expected: All tests PASS.

**Step 6: Commit**

```bash
git add klippbok/api/routers/cleanup.py
git commit -m "feat: update cleanup router for text/reference scan modes"
```

---

### Task 3: Frontend — Setup step with mode toggle, text input, and reference picker

**Files:**
- Modify: `frontend/src/pages/CleanupPage.tsx`
- Modify: `frontend/src/types/cleanup.ts` (add request type)

**Step 1: Add request type to cleanup.ts**

Add at end of `frontend/src/types/cleanup.ts`:

```typescript
export interface CleanupStartRequest {
  mode: 'text' | 'reference'
  subject_description?: string
  reference_image_ids?: string[]
  clip_threshold?: number
}
```

**Step 2: Rewrite CleanupPage.tsx idle state and startScan**

Replace the full `CleanupPage.tsx` with the updated version. Key changes:

1. Add state for setup form:
```typescript
const [mode, setMode] = useState<'text' | 'reference'>('text')
const [subjectDescription, setSubjectDescription] = useState('')
const [selectedRefIds, setSelectedRefIds] = useState<string[]>([])
const [galleryImages, setGalleryImages] = useState<Array<{ id: string; thumbnail_url: string; relative_path: string }>>([])
const [loadingGallery, setLoadingGallery] = useState(false)
```

2. Fetch gallery when reference mode is selected:
```typescript
useEffect(() => {
  if (mode === 'reference' && galleryImages.length === 0 && !loadingGallery) {
    setLoadingGallery(true)
    fetch('/api/v1/images/')
      .then((res) => res.json())
      .then((data: { total: number; images: Array<{ id: string; thumbnail_url: string; relative_path: string }> }) => {
        setGalleryImages(data.images)
      })
      .catch(() => toast.error('Failed to load gallery'))
      .finally(() => setLoadingGallery(false))
  }
}, [mode, galleryImages.length, loadingGallery])
```

3. Toggle reference selection:
```typescript
function toggleRef(id: string) {
  setSelectedRefIds((prev) =>
    prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 3 ? [...prev, id] : prev,
  )
}
```

4. Update `startScan` to send mode-specific body:
```typescript
async function startScan() {
  clearCleanup()
  const body: Record<string, unknown> =
    mode === 'text'
      ? { mode: 'text', subject_description: subjectDescription.trim() }
      : { mode: 'reference', reference_image_ids: selectedRefIds }

  try {
    const res = await fetch('/api/v1/cleanup/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    // ...rest unchanged
  }
}
```

5. Compute `canStart`:
```typescript
const canStart =
  mode === 'text' ? subjectDescription.trim().length > 0 : selectedRefIds.length > 0
```

6. Replace the idle-state return (lines 262-277) with the setup form:

```tsx
return (
  <div style={{ padding: '2rem', maxWidth: 700 }}>
    <h1 className="page-title">Cleanup</h1>
    <p className="page-subtitle">Define the subject to keep, then scan.</p>

    {/* Mode toggle */}
    <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem' }}>
      <button
        className={`cleanup-mode-btn ${mode === 'text' ? 'cleanup-mode-active' : ''}`}
        onClick={() => setMode('text')}
      >
        Describe Subject
      </button>
      <button
        className={`cleanup-mode-btn ${mode === 'reference' ? 'cleanup-mode-active' : ''}`}
        onClick={() => setMode('reference')}
      >
        Reference Images
      </button>
    </div>

    {/* Text mode */}
    {mode === 'text' && (
      <div style={{ marginBottom: '1.5rem' }}>
        <label style={{ display: 'block', marginBottom: '0.5rem', color: '#d1d5db', fontSize: '0.85rem' }}>
          Describe the subject to keep (e.g., "woman with dark hair", "golden retriever")
        </label>
        <input
          type="text"
          value={subjectDescription}
          onChange={(e) => setSubjectDescription(e.target.value)}
          placeholder="woman with dark hair"
          className="cleanup-text-input"
          onKeyDown={(e) => { if (e.key === 'Enter' && canStart) startScan() }}
        />
      </div>
    )}

    {/* Reference mode */}
    {mode === 'reference' && (
      <div style={{ marginBottom: '1.5rem' }}>
        <label style={{ display: 'block', marginBottom: '0.5rem', color: '#d1d5db', fontSize: '0.85rem' }}>
          Pick 1-3 reference images of your target subject
        </label>
        {loadingGallery ? (
          <p style={{ color: '#9ca3af' }}>Loading gallery...</p>
        ) : galleryImages.length === 0 ? (
          <p style={{ color: '#9ca3af' }}>No images in gallery. Import images first.</p>
        ) : (
          <>
            <p style={{ color: '#9ca3af', fontSize: '0.8rem', marginBottom: '0.5rem' }}>
              Selected: {selectedRefIds.length}/3
            </p>
            <div className="cleanup-ref-grid">
              {galleryImages.map((img) => (
                <div
                  key={img.id}
                  className={`cleanup-ref-card ${selectedRefIds.includes(img.id) ? 'cleanup-ref-selected' : ''}`}
                  onClick={() => toggleRef(img.id)}
                  title={img.relative_path}
                >
                  <img src={img.thumbnail_url} alt={img.relative_path} loading="lazy" />
                  {selectedRefIds.includes(img.id) && (
                    <span className="cleanup-ref-check">&#10003;</span>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    )}

    <button className="import-button" onClick={startScan} disabled={!canStart}>
      Start Cleanup Scan
    </button>
    <p style={{ color: '#6b7280', fontSize: '0.75rem', marginTop: '0.5rem' }}>
      CLIP {mode === 'reference' ? 'image-to-image' : 'text-to-image'} + InsightFace
    </p>
  </div>
)
```

7. Update the scanning-state subtitle (line 154) to remove the hardcoded message:
```tsx
<p className="page-subtitle">Scanning media for items matching your subject...</p>
```

**Step 3: Add CSS classes for the new UI**

In the project's main CSS file (find with `grep -rn "cleanup-grid" frontend/src/`), add:

```css
.cleanup-mode-btn {
  padding: 0.6rem 1.2rem;
  border: 1px solid #374151;
  border-radius: 0.5rem;
  background: transparent;
  color: #d1d5db;
  cursor: pointer;
  font-size: 0.85rem;
  transition: all 0.15s;
}
.cleanup-mode-btn:hover {
  border-color: #6b7280;
}
.cleanup-mode-active {
  border-color: #3b82f6;
  background: rgba(59, 130, 246, 0.1);
  color: #93c5fd;
}
.cleanup-text-input {
  width: 100%;
  padding: 0.6rem 0.75rem;
  border: 1px solid #374151;
  border-radius: 0.5rem;
  background: #1f2937;
  color: #f3f4f6;
  font-size: 0.9rem;
}
.cleanup-text-input:focus {
  outline: none;
  border-color: #3b82f6;
}
.cleanup-ref-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
  gap: 0.5rem;
  max-height: 320px;
  overflow-y: auto;
  padding: 0.25rem;
}
.cleanup-ref-card {
  position: relative;
  aspect-ratio: 1;
  border-radius: 0.375rem;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  transition: border-color 0.15s;
}
.cleanup-ref-card img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.cleanup-ref-card:hover {
  border-color: #6b7280;
}
.cleanup-ref-selected {
  border-color: #3b82f6;
}
.cleanup-ref-check {
  position: absolute;
  top: 4px;
  right: 4px;
  background: #3b82f6;
  color: white;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: bold;
}
```

**Step 4: Build and verify**

Run: `cd /c/Dev/Projects/klippbok-main/frontend && npx vite build 2>&1 | tail -5`
Expected: Build succeeds with no TypeScript errors.

Then copy to static:
```bash
cd /c/Dev/Projects/klippbok-main && rm -rf klippbok/api/static/* && cp -r frontend/dist/* klippbok/api/static/
```

**Step 5: Commit**

```bash
git add frontend/src/pages/CleanupPage.tsx frontend/src/types/cleanup.ts frontend/src/
git commit -m "feat: add subject definition setup step to cleanup page"
```

---

### Task 4: Manual browser test

**Step 1: Restart the server**

```bash
# Kill existing, start fresh
taskkill //PID <pid> //F
.venv/Scripts/python.exe -m klippbok.api --port 9000
```

**Step 2: Test text mode**

1. Navigate to http://localhost:9000/ and open the Cleanup tab
2. Verify setup form appears with "Describe Subject" and "Reference Images" toggle buttons
3. "Describe Subject" should be selected by default
4. Type a subject description matching your dataset
5. Click "Start Cleanup Scan"
6. Verify progress bar shows with updated message
7. Verify results appear with reasonable keep/remove/review classifications

**Step 3: Test reference mode**

1. Click "Reference Images" toggle
2. Verify gallery thumbnails load
3. Click 1-3 images to select — verify highlight border and checkmark
4. Click a 4th image — should not select (max 3 enforced)
5. Click "Start Cleanup Scan"
6. Verify results differ from text mode (hopefully better for specific subject matching)

**Step 4: Verify unchanged functionality**

1. Verify "Click to rescue" still works on flagged items
2. Verify "Confirm Removal" moves files to `_review/`
3. Verify Cancel button works during scan

---

Plan complete and saved to `docs/plans/2026-03-06-cleanup-subject-definition.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
