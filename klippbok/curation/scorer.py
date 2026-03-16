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

import logging
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from klippbok.curation.models import CurationMode, ImageScore, SignalScores
from klippbok.curation.presets import CURATION_PHASH_THRESHOLD, get_weights
from klippbok.image.dedup import are_near_duplicates, compute_phash
from klippbok.utils.paths import image_id, to_manifest_path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level ML singletons (lazy init)
# ---------------------------------------------------------------------------

_face_app = None
_pyiqa_model = None
_aesthetic_model = None
_aesthetic_preprocessor = None
_clip_embedder = None

# Warn-once flags for dependency failures
_pyiqa_warned = False
_aesthetic_warned = False


def _get_face_app():
    """Return InsightFace FaceAnalysis singleton for curation.

    Only loads detection + recognition modules (skips landmark and
    genderage models that curation doesn't use), saving ~1 GB VRAM
    and 3 ONNX sessions.
    """
    global _face_app
    if _face_app is None:
        import insightface

        app = insightface.app.FaceAnalysis(
            name="buffalo_l",
            allowed_modules=["detection", "recognition"],
        )
        try:
            import onnxruntime
            has_gpu = "CUDAExecutionProvider" in onnxruntime.get_available_providers()
        except ImportError:
            has_gpu = False
        app.prepare(ctx_id=0 if has_gpu else -1)
        _face_app = app
    return _face_app


def _get_pyiqa_model():
    """Return pyiqa TOPIQ-NR singleton with GPU if available.

    Includes a numpy compatibility shim: pyiqa depends on imgaug which
    uses ``np.sctypes`` removed in NumPy 2.0.  We restore the attribute
    before importing so the rest of the library works normally.
    """
    global _pyiqa_model
    if _pyiqa_model is None:
        import numpy as _np
        if not hasattr(_np, "sctypes"):
            _np.sctypes = {
                "float": [_np.float16, _np.float32, _np.float64],
                "int": [_np.int8, _np.int16, _np.int32, _np.int64],
                "uint": [_np.uint8, _np.uint16, _np.uint32, _np.uint64],
                "complex": [_np.complex64, _np.complex128],
                "others": [bool, object, bytes, str, _np.void],
            }
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
    """Compute SHA256[:16] of manifest-format relative path string as image ID.

    Uses the canonical image_id() from utils.paths with proper path
    normalization (forward slashes) to match gallery convention.
    """
    if project_dir is not None:
        return image_id(to_manifest_path(path, project_dir))
    return image_id(str(path).replace("\\", "/"))


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


_RANKED_SIGNAL_NAMES: list[str] = [
    "face_confidence",
    "identity_similarity",
    "quality_score",
    "aesthetic_score",
    "sharpness_whole",
    "sharpness_face",
    "occlusion_score",
]
"""Signal dimensions that get percentile rank normalization."""


def rank_normalize(scores: list[ImageScore]) -> None:
    """Convert raw signal values to percentile ranks in-place.

    For each signal dimension, compute the percentile rank across all
    images. Ties get averaged rank. Results stored in ranked_signals.
    face_area_ratio is copied as-is (meaningful physical ratio, not ranked).

    Args:
        scores: List of ImageScore objects. Modified in-place.
    """
    from scipy.stats import rankdata

    n = len(scores)
    if n == 0:
        return

    if n == 1:
        scores[0].ranked_signals = scores[0].signals.model_copy()
        for name in _RANKED_SIGNAL_NAMES:
            setattr(scores[0].ranked_signals, name, 1.0)
        scores[0].ranked_signals.face_area_ratio = scores[0].signals.face_area_ratio
        return

    # Initialize ranked_signals from raw signals
    for s in scores:
        s.ranked_signals = s.signals.model_copy()

    for name in _RANKED_SIGNAL_NAMES:
        raw_values = [getattr(s.signals, name) for s in scores]
        ranks = rankdata(raw_values, method="average")
        for i, s in enumerate(scores):
            normalized_rank = (ranks[i] - 1) / (n - 1)
            setattr(s.ranked_signals, name, normalized_rank)

    # face_area_ratio: copy as-is (already set by model_copy, but explicit)
    for s in scores:
        s.ranked_signals.face_area_ratio = s.signals.face_area_ratio


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
            sharpness_face = normalize_score(raw_face_sharp, 10.0, 500.0)

            # Identity similarity
            if reference_embedding is not None and hasattr(best_face, "normed_embedding"):
                sim = float(np.dot(best_face.normed_embedding, reference_embedding))
                identity_similarity = normalize_score(sim, 0.0, 1.0)
    except Exception as e:
        logger.debug("Face detection failed: %s", e)

    # --- pyiqa TOPIQ-NR ---
    quality_score = 0.0
    try:
        import torch as _torch
        pyiqa_model = _get_pyiqa_model()
        with _torch.no_grad():
            raw_quality = pyiqa_model(str(image_path)).item()
        quality_score = normalize_score(raw_quality, 0.0, 1.0)
    except Exception as e:
        global _pyiqa_warned
        if not _pyiqa_warned:
            logger.warning("pyiqa scoring failed (will default to 0.0): %s", e)
            _pyiqa_warned = True
        else:
            logger.debug("pyiqa scoring failed: %s", e)

    # --- Aesthetic Predictor V2.5 ---
    aesthetic_score = 0.0
    try:
        import torch as _torch
        model, preprocessor = _get_aesthetic_model()
        with _torch.no_grad():
            inputs = preprocessor(str(image_path))
            pv = inputs["pixel_values"]
            # preprocessor may return list[ndarray] — convert to tensor
            if isinstance(pv, list):
                pv = _torch.stack([_torch.from_numpy(a) for a in pv])
            param = next(model.parameters())
            pixel_values = pv.to(device=param.device, dtype=param.dtype)
            output = model(pixel_values)
            raw_aesthetic = output.logits[0].item()
        del pixel_values, output, pv, inputs
        aesthetic_score = normalize_score(raw_aesthetic, 3.0, 8.0)
    except Exception as e:
        global _aesthetic_warned
        if not _aesthetic_warned:
            logger.warning("Aesthetic scoring failed (will default to 0.0): %s", e)
            _aesthetic_warned = True
        else:
            logger.debug("Aesthetic scoring failed: %s", e)

    # --- Whole-image sharpness (Laplacian) ---
    sharpness_whole = 0.0
    try:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        raw_sharpness = float(laplacian.var())
        sharpness_whole = normalize_score(raw_sharpness, 10.0, 500.0)
    except Exception as e:
        logger.debug("Sharpness computation failed: %s", e)

    # Free cv2 image before CLIP pass (different model, different memory pool)
    del img_bgr

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
    """Score images using batch-per-model processing to minimize peak VRAM.

    Processes all images through each ML model one at a time, unloading each
    model before loading the next.  This keeps peak VRAM to a single model's
    weights + one image's working memory (~3-4 GB) instead of loading all four
    models simultaneously (~6+ GB with per-image accumulation).

    Phase order (one GPU model resident at a time):
      1. Face detection  — InsightFace / ONNX (~1 GB)
      2. Quality scoring — pyiqa TOPIQ-NR (~1 GB)
      3. Aesthetic        — SigLIP backbone (~2.5 GB)
      4. Sharpness        — CPU-only Laplacian (0 VRAM)
      5. CLIP occlusion  — CLIP ViT-B/32 (~0.6 GB)

    Args:
        image_paths: List of image file paths.
        mode: Curation mode.
        reference_embedding: Optional face embedding for identity similarity.
        progress_callback: Optional callable(current, total) for progress tracking.
        project_dir: Project root for relative path ID computation.

    Returns:
        List of ImageScore objects in same order as input.
    """
    import gc

    import torch

    total = len(image_paths)
    if total == 0:
        return []

    global _face_app, _pyiqa_model, _pyiqa_warned
    global _aesthetic_model, _aesthetic_preprocessor, _aesthetic_warned
    global _clip_embedder

    def _flush_gpu(phase: str = "") -> None:
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            if phase:
                free_gb, total_gb = (v / (1024 ** 3) for v in torch.cuda.mem_get_info())
                logger.info(
                    "VRAM after %s: %.2f / %.2f GB free",
                    phase, free_gb, total_gb,
                )

    # Progress spans all 5 phases: total_steps = N * 5
    _NUM_PHASES = 5
    total_steps = total * _NUM_PHASES
    step = 0

    def _tick() -> None:
        nonlocal step
        step += 1
        if progress_callback is not None:
            progress_callback(step, total_steps)

    # Pre-allocate per-image result arrays
    face_confidences = [0.0] * total
    face_area_ratios = [0.0] * total
    identity_sims = [0.0] * total
    sharpness_faces = [0.0] * total
    quality_scores_arr = [0.0] * total
    aesthetic_scores_arr = [0.0] * total
    sharpness_wholes = [0.0] * total
    occlusion_scores_arr = [0.5] * total

    # ── Phase 1: Face detection (InsightFace / ONNX) ─────────────────────
    face_app = None
    try:
        face_app = _get_face_app()
        for i, path in enumerate(image_paths):
            try:
                img_bgr = cv2.imread(str(path))
                if img_bgr is not None:
                    h, w = img_bgr.shape[:2]
                    image_area = h * w
                    faces = face_app.get(img_bgr)
                    if faces:
                        best = max(faces, key=lambda f: f.det_score)
                        face_confidences[i] = normalize_score(
                            float(best.det_score), 0.0, 1.0,
                        )
                        bbox = best.bbox
                        fx1, fy1, fx2, fy2 = (float(v) for v in bbox)
                        face_area = (fx2 - fx1) * (fy2 - fy1)
                        face_area_ratios[i] = normalize_score(
                            face_area / image_area, 0.01, 0.5,
                        )
                        sharpness_faces[i] = normalize_score(
                            _compute_face_sharpness(img_bgr, bbox), 10.0, 500.0,
                        )
                        if (
                            reference_embedding is not None
                            and hasattr(best, "normed_embedding")
                        ):
                            sim = float(np.dot(best.normed_embedding, reference_embedding))
                            identity_sims[i] = normalize_score(sim, 0.0, 1.0)
                    del img_bgr
            except Exception as e:
                logger.debug("Face detection failed for %s: %s", path, e)
            _tick()
    except Exception as e:
        logger.warning("Face detection phase failed: %s", e)
        step = total  # skip remaining face ticks in progress

    # InsightFace is ONNX — can't .cpu(); must delete ALL references to free GPU
    del face_app
    _face_app = None
    # Also clear face_service's singleton in case _auto_detect_reference loaded it
    try:
        from klippbok.services import face_service as _fs
        _fs._face_app = None
    except Exception:
        pass
    _flush_gpu("face unload")

    # ── Phase 2: Quality scoring (pyiqa TOPIQ-NR) ────────────────────────
    pyiqa_model = None
    try:
        pyiqa_model = _get_pyiqa_model()
        for i, path in enumerate(image_paths):
            try:
                with torch.no_grad():
                    raw_quality = pyiqa_model(str(path)).item()
                quality_scores_arr[i] = normalize_score(raw_quality, 0.0, 1.0)
            except Exception as e:
                if not _pyiqa_warned:
                    logger.warning("pyiqa scoring failed (will default to 0.0): %s", e)
                    _pyiqa_warned = True
                else:
                    logger.debug("pyiqa scoring failed: %s", e)
            # Release cached CUDA blocks every image — without this,
            # PyTorch's caching allocator accumulates ~0.12 GB/image
            # and OOMs around image 70 on 16 GB VRAM.
            torch.cuda.empty_cache()
            _tick()
    except Exception as e:
        logger.warning("pyiqa phase failed: %s", e)
        step = 2 * total

    # Unload pyiqa from GPU — move to CPU first for instant VRAM release
    if pyiqa_model is not None:
        try:
            pyiqa_model.cpu()
        except Exception:
            pass
    del pyiqa_model
    _pyiqa_model = None
    _flush_gpu("pyiqa unload")

    # ── Phase 3: Aesthetic scoring (SigLIP backbone) ─────────────────────
    aes_model = None
    preprocessor = None
    try:
        aes_model, preprocessor = _get_aesthetic_model()
        for i, path in enumerate(image_paths):
            try:
                with torch.no_grad():
                    inputs = preprocessor(str(path))
                    pv = inputs["pixel_values"]
                    if isinstance(pv, list):
                        pv = torch.stack([torch.from_numpy(a) for a in pv])
                    param = next(aes_model.parameters())
                    pixel_values = pv.to(device=param.device, dtype=param.dtype)
                    output = aes_model(pixel_values)
                    raw_aesthetic = output.logits[0].item()
                del pixel_values, output, pv, inputs
                aesthetic_scores_arr[i] = normalize_score(raw_aesthetic, 3.0, 8.0)
            except Exception as e:
                if not _aesthetic_warned:
                    logger.warning("Aesthetic scoring failed (will default to 0.0): %s", e)
                    _aesthetic_warned = True
                else:
                    logger.debug("Aesthetic scoring failed: %s", e)
            torch.cuda.empty_cache()
            _tick()
    except Exception as e:
        logger.warning("Aesthetic phase failed: %s", e)
        step = 3 * total

    # Unload aesthetic model from GPU — move to CPU first for instant VRAM release
    if aes_model is not None:
        try:
            aes_model.cpu()
        except Exception:
            pass
    del aes_model, preprocessor
    _aesthetic_model = None
    _aesthetic_preprocessor = None
    _flush_gpu("aesthetic unload")

    # ── Phase 4: Whole-image sharpness (CPU — no VRAM) ───────────────────
    for i, path in enumerate(image_paths):
        try:
            img_bgr = cv2.imread(str(path))
            if img_bgr is not None:
                gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
                laplacian = cv2.Laplacian(gray, cv2.CV_64F)
                sharpness_wholes[i] = normalize_score(
                    float(laplacian.var()), 10.0, 500.0,
                )
                del img_bgr
        except Exception as e:
            logger.debug("Sharpness computation failed for %s: %s", path, e)
        _tick()

    # ── Phase 5: CLIP occlusion scoring ──────────────────────────────────
    embedder = None
    try:
        embedder = _get_clip_embedder()
        # Pre-compute text embeddings once (same 6 prompts for every image)
        clear_embs = [embedder.encode_text(p) for p in _OCCLUSION_PROMPTS_CLEAR]
        occluded_embs = [embedder.encode_text(p) for p in _OCCLUSION_PROMPTS_OCCLUDED]

        for i, path in enumerate(image_paths):
            try:
                img_emb = embedder.encode_image(path)
                clear_avg = sum(
                    float(np.dot(img_emb, te)) for te in clear_embs
                ) / len(clear_embs)
                occluded_avg = sum(
                    float(np.dot(img_emb, te)) for te in occluded_embs
                ) / len(occluded_embs)
                raw = clear_avg - occluded_avg
                occlusion_scores_arr[i] = normalize_score(raw, -0.1, 0.1)
            except Exception:
                logger.debug("CLIP occlusion scoring failed for %s", path)
            torch.cuda.empty_cache()
            _tick()
    except Exception as e:
        logger.warning("CLIP occlusion phase failed: %s", e)
        step = 5 * total

    # Unload CLIP from GPU — move model to CPU first for instant VRAM release
    if embedder is not None:
        try:
            embedder._model.cpu()
        except Exception:
            pass
    del embedder
    _clip_embedder = None
    _flush_gpu("CLIP unload")

    # ── Assemble ImageScore results ──────────────────────────────────────
    results: list[ImageScore] = []
    for i, path in enumerate(image_paths):
        signals = SignalScores(
            face_confidence=face_confidences[i],
            face_area_ratio=face_area_ratios[i],
            identity_similarity=identity_sims[i],
            quality_score=quality_scores_arr[i],
            aesthetic_score=aesthetic_scores_arr[i],
            sharpness_whole=sharpness_wholes[i],
            sharpness_face=sharpness_faces[i],
            occlusion_score=occlusion_scores_arr[i],
        )
        composite = _compute_composite(signals, mode)
        try:
            rel = str(path.relative_to(project_dir)) if project_dir else str(path)
        except ValueError:
            rel = str(path)
        results.append(ImageScore(
            image_id=_image_id(path, project_dir),
            relative_path=rel,
            signals=signals,
            composite_score=composite,
            mode=mode,
        ))

    return results


def mark_duplicates(
    scores: list[ImageScore],
    image_paths: list[Path],
) -> None:
    """Group near-duplicate images using pHash + union-find.

    For each duplicate group, the highest-composite-score image is
    kept as the representative. Others get dedup_kept=False and
    signals.is_duplicate=True (backwards compat).

    Uses CURATION_PHASH_THRESHOLD (6) — tighter than import validation (10).

    Args:
        scores: List of ImageScore objects (must match image_paths order).
        image_paths: Corresponding image file paths.
    """
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

    # Union-find with path compression
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]  # path compression
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    # Pairwise comparison with tighter curation threshold
    for i in range(n):
        if hashes[i] is None:
            continue
        for j in range(i + 1, n):
            if hashes[j] is None:
                continue
            if are_near_duplicates(hashes[i], hashes[j], threshold=CURATION_PHASH_THRESHOLD):
                union(i, j)

    # Build groups from union-find roots
    groups: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        groups.setdefault(root, []).append(i)

    # Assign group IDs and select representatives
    for root, members in groups.items():
        if len(members) < 2:
            continue  # unique image, no group assignment needed
        group_id = scores[root].image_id
        best_idx = max(members, key=lambda i: scores[i].composite_score)
        for i in members:
            scores[i].dedup_group_id = group_id
            if i == best_idx:
                scores[i].dedup_kept = True
            else:
                scores[i].dedup_kept = False
                scores[i].signals.is_duplicate = True  # backwards compat
