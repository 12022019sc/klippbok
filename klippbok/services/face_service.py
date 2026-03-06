"""InsightFace face embedding and DBSCAN clustering service.

Provides face-based subject identification for character LoRA workflows.
InsightFace detects faces and produces 512-dim embeddings. DBSCAN clusters
similar embeddings to group images of the same person.

Key design decisions:
- CPU mode (ctx_id=-1) per open question #1 in 07-RESEARCH.md — GPU setup
  requires additional CUDA libraries; CPU is sufficient for typical dataset sizes
- Module-level FaceAnalysis singleton to avoid repeated model loading
- DBSCAN with cosine metric (not euclidean) — normalized embeddings use cosine
  similarity natively; eps=0.4 works well for InsightFace buffalo_l embeddings
- Noise points (DBSCAN label=-1) are excluded from clusters

Exports: compute_face_embeddings, cluster_face_embeddings, check_insightface_available,
         select_best_reference, FaceCluster
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Optional dependency check
# ---------------------------------------------------------------------------

_INSIGHTFACE_AVAILABLE = False
try:
    import insightface  # noqa: F401
    _INSIGHTFACE_AVAILABLE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# DBSCAN import (sklearn is a lighter dependency than insightface)
# ---------------------------------------------------------------------------
try:
    from sklearn.cluster import DBSCAN
except ImportError:
    DBSCAN = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Pillow Image (for resolution checking)
# ---------------------------------------------------------------------------
try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Module-level FaceAnalysis singleton (lazy init)
# ---------------------------------------------------------------------------

_face_app = None


def _get_face_app():
    """Return the module-level FaceAnalysis app, creating it on first call.

    Uses buffalo_l model on CPU (ctx_id=-1) for compatibility.
    """
    global _face_app
    if _face_app is None:
        import insightface
        app = insightface.app.FaceAnalysis(name="buffalo_l")
        app.prepare(ctx_id=-1)
        _face_app = app
    return _face_app


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class FaceCluster(BaseModel):
    """A cluster of images containing the same person's face.

    Produced by DBSCAN clustering of InsightFace embeddings.
    """
    cluster_id: int
    """Cluster identifier (0-based, sequential)."""

    image_paths: list[str]
    """Paths to images in this cluster."""

    suggested_name: str | None = None
    """User-assigned name for this person (set via API)."""

    primary_reference: str | None = None
    """Best quality image from this cluster (highest resolution)."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_insightface_available() -> bool:
    """Return True if insightface is installed and importable.

    Mirrors check_clip_available() pattern from triage/embeddings.py.

    Returns:
        True if insightface is available, False otherwise.
    """
    return _INSIGHTFACE_AVAILABLE


def compute_face_embeddings(
    image_paths: list[Path],
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, np.ndarray]:
    """Compute InsightFace face embeddings for a list of images.

    For each image: load via cv2, detect faces, select the face with the
    highest detection score, store its normed_embedding. Images with no
    detected face are skipped.

    Args:
        image_paths: List of image file paths to process.
        progress_callback: Optional callable(current, total) called after
            each image is processed.

    Returns:
        Dict mapping path string to 512-dim embedding array.
        Only contains entries for images where a face was detected.

    Raises:
        ImportError: if insightface is not installed.
        RuntimeError: if cv2 is not installed.
    """
    import cv2

    if not _INSIGHTFACE_AVAILABLE:
        raise ImportError(
            "Face embedding requires InsightFace.\n"
            "Install with:\n"
            "  pip install insightface onnxruntime\n"
            "  pip install opencv-python-headless"
        )

    app = _get_face_app()
    total = len(image_paths)
    result: dict[str, np.ndarray] = {}

    for i, path in enumerate(image_paths, 1):
        path = Path(path)
        img = cv2.imread(str(path))

        if img is not None:
            faces = app.get(img)
            if faces:
                # Select face with highest detection score
                best_face = max(faces, key=lambda f: f.det_score)
                result[str(path)] = best_face.normed_embedding

        if progress_callback is not None:
            progress_callback(i, total)

    return result


def cluster_face_embeddings(
    embeddings: dict[str, np.ndarray],
    eps: float = 0.4,
    min_samples: int = 2,
) -> list[FaceCluster]:
    """Group face embeddings into clusters using DBSCAN.

    Uses cosine metric (appropriate for L2-normalized InsightFace embeddings).
    Noise points (DBSCAN label=-1) are excluded from the returned clusters.

    Args:
        embeddings: Dict of {image_path: embedding_array} from
            compute_face_embeddings().
        eps: DBSCAN epsilon (maximum distance between neighbors).
            Default 0.4 works well for InsightFace buffalo_l cosine distances.
        min_samples: Minimum samples to form a core point (default: 2).

    Returns:
        List of FaceCluster objects. Each cluster has a cluster_id and the
        list of image paths assigned to it. Clusters are ordered by cluster_id.
        Returns empty list if embeddings is empty.
    """
    if not embeddings:
        return []

    if DBSCAN is None:
        raise ImportError(
            "Face clustering requires scikit-learn.\n"
            "Install with: pip install scikit-learn"
        )

    paths = list(embeddings.keys())
    emb_matrix = np.array([embeddings[p] for p in paths], dtype=np.float32)

    labels = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine").fit_predict(emb_matrix)

    # Group paths by cluster label (excluding noise = -1)
    cluster_map: dict[int, list[str]] = {}
    for path, label in zip(paths, labels):
        if label == -1:
            continue
        cluster_map.setdefault(int(label), []).append(path)

    clusters: list[FaceCluster] = []
    for cluster_id in sorted(cluster_map.keys()):
        image_paths = cluster_map[cluster_id]
        cluster = FaceCluster(
            cluster_id=cluster_id,
            image_paths=image_paths,
        )
        # Auto-select the highest-resolution image as primary reference
        cluster.primary_reference = select_best_reference(cluster)
        clusters.append(cluster)

    return clusters


def select_best_reference(cluster: FaceCluster) -> str:
    """Pick the highest-resolution image from a face cluster.

    Uses Pillow to open each image and compare width*height. The image
    with the most pixels is returned as the primary reference — higher
    resolution typically means better embedding quality.

    Args:
        cluster: FaceCluster containing the candidate image paths.

    Returns:
        Path string of the highest-resolution image in the cluster.
    """
    if not cluster.image_paths:
        raise ValueError("Cluster has no image paths")

    best_path = cluster.image_paths[0]
    best_pixels = 0

    for path_str in cluster.image_paths:
        try:
            img = Image.open(path_str)
            w, h = img.size
            pixels = w * h
            if pixels > best_pixels:
                best_pixels = pixels
                best_path = path_str
        except Exception:
            pass  # Skip unreadable images

    return best_path
