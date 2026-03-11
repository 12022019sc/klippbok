"""CLIP triage service for standalone images and video clips.

Extends the existing triage module to work with standalone image paths
(not just video clip paths) — fulfilling ARCH-08.

Key design decisions:
- Module-level lazy CLIPEmbedder singleton to avoid repeated model loading
  (per research pitfall #1 in 07-RESEARCH.md)
- Triage and ingest are SEPARATE workflows: this service writes a manifest
  with scores and classifications; the user reviews via TriagePage, then
  optionally triggers filtered ingest separately
- classification thresholds: match >= threshold, borderline >= threshold-0.1,
  no_match < threshold-0.1

Exports: run_triage, get_triage_results, add_concept_reference, list_concepts,
         TriageResult, ConceptMatch
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable, Literal

import numpy as np
from pydantic import BaseModel

from klippbok.triage.concepts import discover_concepts
from klippbok.triage.models import ConceptReference

# ---------------------------------------------------------------------------
# Module-level embedder singleton (lazy init)
# ---------------------------------------------------------------------------

_embedder = None
_embedder_model_name: str | None = None


def _get_or_create_embedder(model_name: str = "openai/clip-vit-base-patch32"):
    """Return the module-level CLIPEmbedder, creating it on first call.

    Using a module-level singleton avoids reloading the CLIP model on every
    triage run, which would be very slow (~30s per load on CPU).
    """
    global _embedder, _embedder_model_name
    if _embedder is None or _embedder_model_name != model_name:
        from klippbok.triage.embeddings import CLIPEmbedder
        _embedder = CLIPEmbedder(model_name=model_name)
        _embedder_model_name = model_name
    return _embedder


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ConceptMatch(BaseModel):
    """A match between an item and a concept reference."""
    concept_name: str
    score: float


class TriageResult(BaseModel):
    """Triage result for a single item (image or video clip)."""
    item_path: str
    item_id: str  # SHA256[:16] of item_path string
    best_score: float
    matches: list[ConceptMatch]
    classification: Literal["match", "borderline", "no_match"]


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def _compute_item_id(path: str | Path, project_dir: Path | None = None) -> str:
    """Compute a stable, URL-safe item ID from a path.

    Uses SHA256[:16] of the manifest-format relative path string (when
    project_dir is provided), matching the ID scheme used by the images API.
    Falls back to the full path string when project_dir is not available.
    """
    from klippbok.utils.paths import image_id, to_manifest_path

    p = Path(path)
    if project_dir is not None:
        return image_id(to_manifest_path(p, project_dir))
    return image_id(str(path).replace("\\", "/"))


def _classify(score: float, threshold: float) -> Literal["match", "borderline", "no_match"]:
    """Classify an item based on its best similarity score.

    Args:
        score: Best cosine similarity score (0.0 to 1.0).
        threshold: Minimum score for a definitive match.

    Returns:
        "match" if score >= threshold,
        "borderline" if score >= threshold - 0.1,
        "no_match" otherwise.
    """
    if score >= threshold:
        return "match"
    elif score >= threshold - 0.1:
        return "borderline"
    else:
        return "no_match"


def run_triage(
    item_paths: list[Path],
    concepts_dir: Path,
    threshold: float = 0.70,
    frames_per_clip: int = 5,
    output_path: Path | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    model_name: str = "openai/clip-vit-base-patch32",
    project_dir: Path | None = None,
) -> list[TriageResult]:
    """Run CLIP triage on a list of item paths (images or video clips).

    The key ARCH-08 function: accepts ANY image or video clip path.
    For images, uses CLIPEmbedder.encode_image directly. For video clips,
    samples frames and uses the best-matching frame score.

    Args:
        item_paths: List of image or video clip paths to triage.
        concepts_dir: Directory with concept reference images organized in
            type subfolders (e.g. concepts/character/holly.jpg).
        threshold: Minimum cosine similarity for a definitive match (0.0-1.0).
            Default 0.70. Borderline range = (threshold-0.1, threshold).
        frames_per_clip: Number of frames to sample per video clip (default: 5).
            Ignored for image files.
        output_path: If provided, persist results to triage_manifest.json at
            this path. Enables result survival across page refresh.
        progress_callback: Optional callable(current, total) called after
            each item is processed.
        model_name: CLIP model to use.

    Returns:
        List of TriageResult, one per item path, in the same order.

    Raises:
        ImportError: if torch/transformers aren't installed (CLIP dependency).
        FileNotFoundError: if concepts_dir doesn't exist.
    """
    VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

    # Lazy-load embedder
    embedder = _get_or_create_embedder(model_name)

    # Discover concept references
    concepts = discover_concepts(concepts_dir)

    # Encode all reference images
    ref_embeddings: dict[ConceptReference, np.ndarray] = {}
    for ref in concepts:
        try:
            ref_embeddings[ref] = embedder.encode_image(ref.image_path)
        except Exception:
            pass  # Skip unreadable references silently — logged at caller level

    total = len(item_paths)
    results: list[TriageResult] = []

    for i, item_path in enumerate(item_paths, 1):
        item_path = Path(item_path)
        suffix = item_path.suffix.lower()

        # Encode the item
        if suffix in VIDEO_EXTENSIONS:
            # For video clips: sample frames and take best score per reference
            item_frame_embeddings = _encode_video_frames(embedder, item_path, frames_per_clip)
        else:
            # For images: encode directly
            item_emb = embedder.encode_image(item_path)
            item_frame_embeddings = [item_emb]

        # Score against each reference
        matches: list[ConceptMatch] = []
        best_score = 0.0

        for ref, ref_emb in ref_embeddings.items():
            if item_frame_embeddings:
                # Take highest similarity across all frames
                scores = [float(np.dot(frame_emb, ref_emb)) for frame_emb in item_frame_embeddings]
                score = max(scores)
            else:
                score = 0.0

            if score >= threshold - 0.1:  # Include borderline matches too
                matches.append(ConceptMatch(concept_name=ref.name, score=score))
            if score > best_score:
                best_score = score

        # Sort matches by score descending
        matches.sort(key=lambda m: m.score, reverse=True)

        result = TriageResult(
            item_path=str(item_path),
            item_id=_compute_item_id(item_path, project_dir),
            best_score=best_score,
            matches=matches,
            classification=_classify(best_score, threshold),
        )
        results.append(result)

        if progress_callback is not None:
            progress_callback(i, total)

    # Persist results if output_path given
    if output_path is not None:
        _persist_results(results, Path(output_path))

    return results


def _encode_video_frames(
    embedder,
    video_path: Path,
    frames_per_clip: int,
) -> list[np.ndarray]:
    """Sample frames from a video clip and encode them with CLIP.

    Args:
        embedder: CLIPEmbedder instance.
        video_path: Path to the video clip.
        frames_per_clip: Number of frames to sample.

    Returns:
        List of embedding arrays. Empty list if sampling fails.
    """
    try:
        from klippbok.triage.sampler import cleanup_frames, sample_clip_frames
        frame_paths = sample_clip_frames(video_path, count=frames_per_clip)
        if not frame_paths:
            return []
        embeddings = embedder.encode_images(frame_paths)
        cleanup_frames(frame_paths)
        return embeddings
    except Exception:
        return []


def _persist_results(results: list[TriageResult], output_path: Path) -> None:
    """Write triage results to a JSON manifest file.

    Args:
        results: List of TriageResult objects to persist.
        output_path: Path to write the manifest JSON file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "results": [r.model_dump() for r in results],
    }
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def get_triage_results(manifest_path: Path) -> list[TriageResult]:
    """Load persisted triage results from a JSON manifest file.

    Args:
        manifest_path: Path to the triage_manifest.json file.

    Returns:
        List of TriageResult objects. Empty list if file doesn't exist.
    """
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        return []

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = []
    for item in data.get("results", []):
        results.append(TriageResult(**item))
    return results


def add_concept_reference(
    image_path: Path,
    concepts_dir: Path,
    category: str,
) -> ConceptReference:
    """Copy an image into the concepts directory as a named reference.

    Creates concepts/{category}/ if it doesn't exist, then copies the
    source image into that folder. Returns a ConceptReference for the
    newly added image.

    Args:
        image_path: Source image path to copy.
        concepts_dir: Root concepts directory (e.g. project/concepts/).
        category: Folder name within concepts/ (e.g. "character", "setting").

    Returns:
        ConceptReference for the copied image.
    """
    image_path = Path(image_path)
    concepts_dir = Path(concepts_dir)

    target_dir = concepts_dir / category
    target_dir.mkdir(parents=True, exist_ok=True)

    dest = target_dir / image_path.name
    shutil.copy2(str(image_path), str(dest))

    from klippbok.triage.models import resolve_concept_type
    concept_type = resolve_concept_type(category)

    return ConceptReference(
        name=image_path.stem,
        concept_type=concept_type,
        image_path=dest,
        folder_name=category,
    )


def list_concepts(concepts_dir: Path) -> list[ConceptReference]:
    """List all concept references from the concepts directory.

    A thin wrapper around discover_concepts() for consistency with
    the other service functions.

    Args:
        concepts_dir: Root concepts directory to scan.

    Returns:
        List of ConceptReference objects discovered in the folder structure.
    """
    return discover_concepts(concepts_dir)
