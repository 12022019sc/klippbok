# Cleanup Subject Definition — Design

**Date:** 2026-03-06
**Status:** Approved
**Problem:** The cleanup tool hardcodes "photo of a woman" CLIP prompts, offering no way to define the target subject. This causes 100% misclassification on mixed human+object datasets.

## Solution

Add a **setup step** to the Cleanup page before scanning. Two modes:

1. **Text description** — user types a subject description, backend generates CLIP text prompts from it
2. **Reference images** — user picks 1-3 images from the gallery, backend uses CLIP image-to-image similarity

Both modes keep InsightFace face detection as a secondary boost signal.

## Frontend — CleanupPage Idle State

Replace the bare "Start Scan" button with a setup form:

- Two mode toggle cards at top: "Describe" and "Reference Images"
- Clicking one shows its form, hides the other
- **Text mode:** Single text input for subject description
- **Reference mode:** Scrollable thumbnail grid from existing gallery. Click to select (up to 3). Selected images get highlight border + checkmark
- "Start Scan" button disabled until subject defined (text non-empty OR >= 1 reference selected)
- Uses existing `GET /api/v1/images/` for gallery listing and `/api/v1/images/{id}/thumbnail` for thumbnails

## Backend — API Changes

### CleanupStartRequest

```python
class CleanupStartRequest(BaseModel):
    mode: Literal["text", "reference"]
    subject_description: str | None = None      # text mode
    reference_image_ids: list[str] | None = None # reference mode
    clip_threshold: float = 0.25
```

### Text Mode Processing

- Receive `subject_description` (e.g., "woman with dark hair")
- Generate positive prompts: `["photo of {desc}", "portrait of {desc}", "{desc} posing", "selfie of {desc}"]`
- Keep default negative prompts (screenshot, meme, landscape, etc.)
- Pipeline unchanged: CLIP text-to-image similarity

### Reference Mode Processing

- Receive `reference_image_ids`, resolve to file paths via manifest
- Compute CLIP image embeddings for references (1-3 images, done once)
- For each gallery item: compute CLIP image embedding, cosine similarity against each reference, take max
- Net score = max_reference_similarity (no negative prompts needed)
- InsightFace still runs as boost when CLIP score >= threshold
- **Different threshold:** 0.65 for reference mode vs 0.25 for text mode (image-to-image similarity has higher baseline)

### New Functions in cleanup_service.py

- `generate_prompts_from_description(desc: str) -> tuple[list[str], list[str]]`
- `classify_item_by_reference(image_path, embedder, reference_embeddings, threshold, face_app, project_dir) -> CleanupClassification`
- `classify_items_by_reference(item_paths, project_dir, reference_paths, threshold, progress_callback) -> list[CleanupClassification]`

## Files Modified

| File | Change |
|------|--------|
| `klippbok/services/cleanup_service.py` | Add reference mode classification, prompt generation from text, update constants |
| `klippbok/api/routers/cleanup.py` | Update request model, route text vs reference, resolve image IDs to paths |
| `frontend/src/pages/CleanupPage.tsx` | Setup step with mode toggle, text input, reference picker, pass params to startScan |
| `frontend/src/types/cleanup.ts` | Update request type if needed |

## Unchanged

- SSE streaming, progress callback, useCleanupEvents hook
- Review state (flagged grid, confirm removal, unflag toggle)
- InsightFace as boost signal
- `_review/` folder move + audit log
- confirm_removal endpoint

## Testing

- Unit tests: prompt generation, reference classification with mock embeddings
- Integration: text mode scan produces classifications
- Manual browser: both modes on mixed dataset
