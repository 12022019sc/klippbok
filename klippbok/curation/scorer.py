"""Multi-signal image scorer for dataset curation.

Computes 7 ML-based signal scores per image and produces a weighted
composite score that differs between Character and Style modes.

Signal dimensions:
1. face_confidence — InsightFace detection score
2. face_area_ratio — face bbox area / image area
3. identity_similarity — cosine similarity to reference face embedding
4. quality_score — pyiqa TOPIQ-NR perceptual quality
5. aesthetic_score — Aesthetic Predictor V2.5
6. sharpness_whole — whole-image Laplacian variance
7. sharpness_face — face-region Laplacian variance
+ occlusion_score — CLIP zero-shot occlusion detection
+ pose_vector — MediaPipe pose joint angles
+ is_duplicate — pHash near-duplicate flag

All singletons follow the lazy-loading pattern from face_service._get_face_app().
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from klippbok.curation.models import CurationMode, ImageScore, SignalScores
from klippbok.curation.presets import get_weights

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level ML singletons (lazy init)
# ---------------------------------------------------------------------------

_face_app = None
_pyiqa_model = None
_aesthetic_model = None
_aesthetic_preprocessor = None
_clip_embedder = None


def _get_face_app():
    """Return InsightFace FaceAnalysis singleton (GPU-aware)."""
    global _face_app
    if _face_app is None:
        from klippbok.services.face_service import _get_face_app as _get_shared_face_app
        _face_app = _get_shared_face_app()
    return _face_app


def _get_pyiqa_model():
    """Return pyiqa TOPIQ-NR singleton with GPU if available."""
    global _pyiqa_model
    if _pyiqa_model is None:
        import pyiqa
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _pyiqa_model = pyiqa.create_metric("topiq_nr", device=device)
    return _pyiqa_model


def _get_aesthetic_model() -> tuple:
    """Return (aesthetic_model, preprocessor) singleton.

    Uses aesthetic-predictor-v2-5 with SigLIP backbone.
    Falls back to float16 if bfloat16 is not supported.
    """
    global _aesthetic_model, _aesthetic_preprocessor
    if _aesthetic_model is None:
        import torch
        from aesthetic_predictor_v2_5 import convert_v2_5_from_siglip

        model, preprocessor = convert_v2_5_from_siglip(
            low_cpu_mem_usage=True,
            trust_remote_code=True,
        )
        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda":
            try:
                model = model.to(torch.bfloat16).to(device)
            except RuntimeError:
                model = model.to(torch.float16).to(device)
        else:
            model = model.to(device)
        model.eval()
        _aesthetic_model = model
        _aesthetic_preprocessor = preprocessor
    return _aesthetic_model, _aesthetic_preprocessor


def _get_clip_embedder():
    """Return CLIPEmbedder singleton (reuses triage_service pattern)."""
    global _clip_embedder
    if _clip_embedder is None:
        from klippbok.triage.embeddings import CLIPEmbedder
        _clip_embedder = CLIPEmbedder()
    return _clip_embedder


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _image_id(path: Path, project_dir: Path | None = None) -> str:
    """Compute SHA256[:16] of relative path string as image ID.

    Must use relative path to match gallery convention in images.py.
    """
    if project_dir is not None:
        try:
            rel = str(path.relative_to(project_dir))
        except ValueError:
            rel = str(path)
    else:
        rel = str(path)
    return hashlib.sha256(rel.encode()).hexdigest()[:16]


def normalize_score(value: float, low: float, high: float) -> float:
    """Linear normalization to [0, 1] with clamping.

    Args:
        value: Raw score value.
        low: Value mapping to 0.0.
        high: Value mapping to 1.0.

    Returns:
        Normalized score clamped to [0.0, 1.0].
    """
    if high <= low:
        return 0.0
    normalized = (value - low) / (high - low)
    return max(0.0, min(1.0, normalized))


def _compute_face_sharpness(
    img_bgr: np.ndarray,
    bbox: np.ndarray,
) -> float:
    """Compute Laplacian variance for face bounding box region.

    Args:
        img_bgr: BGR image array from cv2.imread.
        bbox: Face bounding box [x1, y1, x2, y2].

    Returns:
        Raw Laplacian variance of the face region.
    """
    x1, y1, x2, y2 = [int(v) for v in bbox]
    h, w = img_bgr.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)

    if x2 <= x1 or y2 <= y1:
        return 0.0

    face_region = img_bgr[y1:y2, x1:x2]
    gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    return float(laplacian.var())


def _compute_composite(signals: SignalScores, mode: CurationMode) -> float:
    """Compute weighted composite score from signal scores.

    Weight category mapping:
    - "face": mean(face_confidence, identity_similarity, occlusion_score)
    - "technical": mean(sharpness_whole, sharpness_face, quality_score)
    - "aesthetic": aesthetic_score
    - "other": face_area_ratio (penalize too small/large)

    Args:
        signals: Individual signal scores.
        mode: Curation mode for weight selection.

    Returns:
        Composite score as a float.
    """
    weights = get_weights(mode)

    face_component = (
        signals.face_confidence
        + signals.identity_similarity
        + signals.occlusion_score
    ) / 3.0

    technical_component = (
        signals.sharpness_whole
        + signals.sharpness_face
        + signals.quality_score
    ) / 3.0

    aesthetic_component = signals.aesthetic_score

    # Penalize extreme face area ratios (too small or too large)
    # Ideal range ~0.05-0.40 of image area
    other_component = signals.face_area_ratio

    composite = (
        weights["face"] * face_component
        + weights["technical"] * technical_component
        + weights["aesthetic"] * aesthetic_component
        + weights["other"] * other_component
    )
    return float(composite)


# ---------------------------------------------------------------------------
# CLIP occlusion detection
# ---------------------------------------------------------------------------

_OCCLUSION_PROMPTS_CLEAR = [
    "a clear photo of a person",
    "a full unobstructed view of a person",
    "a person with nothing blocking their face",
]
_OCCLUSION_PROMPTS_OCCLUDED = [
    "a person partially hidden behind an object",
    "a person with their face blocked or covered",
    "an obstructed or occluded person",
]


def _compute_occlusion_score(image_path: Path) -> float:
    """Use CLIP zero-shot to detect face/body occlusion.

    Returns a score in [0, 1] where 1 = clear view, 0 = occluded.
    """
    try:
        embedder = _get_clip_embedder()
        img_emb = embedder.encode_image(image_path)

        clear_sims = []
        for prompt in _OCCLUSION_PROMPTS_CLEAR:
            text_emb = embedder.encode_text(prompt)
            clear_sims.append(float(np.dot(img_emb, text_emb)))

        occluded_sims = []
        for prompt in _OCCLUSION_PROMPTS_OCCLUDED:
            text_emb = embedder.encode_text(prompt)
            occluded_sims.append(float(np.dot(img_emb, text_emb)))

        clear_avg = sum(clear_sims) / len(clear_sims)
        occluded_avg = sum(occluded_sims) / len(occluded_sims)

        # Normalize: positive = clear, negative = occluded
        raw = clear_avg - occluded_avg
        return normalize_score(raw, -0.1, 0.1)
    except Exception:
        logger.debug("CLIP occlusion scoring failed, defaulting to 0.5")
        return 0.5


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_image(
    image_path: Path,
    mode: CurationMode,
    reference_embedding: np.ndarray | None = None,
    project_dir: Path | None = None,
) -> ImageScore:
    """Score a single image across all signal dimensions.

    Args:
        image_path: Path to the image file.
        mode: "character" or "style" (affects composite weighting).
        reference_embedding: Optional face embedding for identity similarity.

    Returns:
        ImageScore with all signals populated and composite computed.
    """
    image_path = Path(image_path)
    img_bgr = cv2.imread(str(image_path))
    if img_bgr is None:
        logger.warning("Failed to load image: %s", image_path)
        return ImageScore(
            image_id=_image_id(image_path, project_dir),
            relative_path=str(image_path.relative_to(project_dir)) if project_dir else str(image_path),
            mode=mode,
        )

    h, w = img_bgr.shape[:2]
    image_area = h * w

    # --- InsightFace ---
    face_confidence = 0.0
    face_area_ratio = 0.0
    identity_similarity = 0.0
    sharpness_face = 0.0

    try:
        face_app = _get_face_app()
        faces = face_app.get(img_bgr)
        if faces:
            best_face = max(faces, key=lambda f: f.det_score)
            face_confidence = normalize_score(float(best_face.det_score), 0.0, 1.0)

            bbox = best_face.bbox
            fx1, fy1, fx2, fy2 = [float(v) for v in bbox]
            face_area = (fx2 - fx1) * (fy2 - fy1)
            face_area_ratio = normalize_score(face_area / image_area, 0.01, 0.5)

            # Face sharpness
            raw_face_sharp = _compute_face_sharpness(img_bgr, bbox)
            sharpness_face = normalize_score(raw_face_sharp, 50.0, 1000.0)

            # Identity similarity
            if reference_embedding is not None and hasattr(best_face, "normed_embedding"):
                sim = float(np.dot(best_face.normed_embedding, reference_embedding))
                identity_similarity = normalize_score(sim, 0.0, 1.0)
    except Exception as e:
        logger.debug("Face detection failed: %s", e)

    # --- pyiqa TOPIQ-NR ---
    quality_score = 0.0
    try:
        pyiqa_model = _get_pyiqa_model()
        raw_quality = pyiqa_model(str(image_path)).item()
        quality_score = normalize_score(raw_quality, 0.0, 1.0)
    except Exception as e:
        logger.debug("pyiqa scoring failed: %s", e)

    # --- Aesthetic Predictor V2.5 ---
    aesthetic_score = 0.0
    try:
        model, preprocessor = _get_aesthetic_model()
        inputs = preprocessor(image_path)
        pixel_values = inputs["pixel_values"].to(next(model.parameters()).device)
        output = model(pixel_values)
        raw_aesthetic = output.logits[0].item()
        aesthetic_score = normalize_score(raw_aesthetic, 3.0, 8.0)
    except Exception as e:
        logger.debug("Aesthetic scoring failed: %s", e)

    # --- Whole-image sharpness (Laplacian) ---
    sharpness_whole = 0.0
    try:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        raw_sharpness = float(laplacian.var())
        sharpness_whole = normalize_score(raw_sharpness, 50.0, 1000.0)
    except Exception as e:
        logger.debug("Sharpness computation failed: %s", e)

    # --- CLIP occlusion ---
    occlusion_score = _compute_occlusion_score(image_path)

    # --- Build signals ---
    signals = SignalScores(
        face_confidence=face_confidence,
        face_area_ratio=face_area_ratio,
        identity_similarity=identity_similarity,
        quality_score=quality_score,
        aesthetic_score=aesthetic_score,
        sharpness_whole=sharpness_whole,
        sharpness_face=sharpness_face,
        occlusion_score=occlusion_score,
    )

    # --- Composite ---
    composite = _compute_composite(signals, mode)

    return ImageScore(
        image_id=_image_id(image_path, project_dir),
        relative_path=str(image_path.relative_to(project_dir)) if project_dir else str(image_path),
        signals=signals,
        composite_score=composite,
        mode=mode,
    )


def score_images(
    image_paths: list[Path],
    mode: CurationMode,
    reference_embedding: np.ndarray | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    project_dir: Path | None = None,
) -> list[ImageScore]:
    """Score multiple images sequentially.

    GPU models are already loaded as singletons, so sequential scoring
    is efficient (no model reloading).

    Args:
        image_paths: List of image file paths.
        mode: Curation mode.
        reference_embedding: Optional face embedding for identity similarity.
        progress_callback: Optional callable(current, total) for progress tracking.
        project_dir: Project root for relative path ID computation.

    Returns:
        List of ImageScore objects in same order as input.
    """
    total = len(image_paths)
    results: list[ImageScore] = []

    for i, path in enumerate(image_paths, 1):
        score = score_image(path, mode, reference_embedding, project_dir=project_dir)
        results.append(score)
        if progress_callback is not None:
            progress_callback(i, total)

    return results


def mark_duplicates(
    scores: list[ImageScore],
    image_paths: list[Path],
) -> None:
    """Mark near-duplicate images using pHash comparison.

    For each duplicate pair, the lower-scoring image gets is_duplicate=True.
    Mutates scores in-place.

    Args:
        scores: List of ImageScore objects (must match image_paths order).
        image_paths: Corresponding image file paths.
    """
    from klippbok.services.image_service import are_near_duplicates, compute_phash

    n = len(scores)
    if n != len(image_paths):
        raise ValueError("scores and image_paths must have the same length")

    # Compute all pHashes
    hashes: list[str | None] = []
    for path in image_paths:
        try:
            h = compute_phash(path)
            hashes.append(h)
        except Exception:
            hashes.append(None)

    # Pairwise comparison
    for i in range(n):
        if hashes[i] is None or scores[i].signals.is_duplicate:
            continue
        for j in range(i + 1, n):
            if hashes[j] is None or scores[j].signals.is_duplicate:
                continue
            if are_near_duplicates(hashes[i], hashes[j]):
                # Mark the lower-scoring one as duplicate
                if scores[i].composite_score >= scores[j].composite_score:
                    scores[j].signals.is_duplicate = True
                else:
                    scores[i].signals.is_duplicate = True
                    break  # This image is now marked, no need to check more
