"""WD Tagger v3 ONNX backend for booru-style tag generation.

Reference: https://huggingface.co/spaces/SmilingWolf/wd-tagger/raw/main/app.py
Model: SmilingWolf/wd-vit-tagger-v3 (onnxruntime CPU inference)
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

MODEL_REPO = "SmilingWolf/wd-vit-tagger-v3"
MODEL_FILENAME = "model.onnx"
LABEL_FILENAME = "selected_tags.csv"
GENERAL_THRESHOLD = 0.35
CHARACTER_THRESHOLD = 0.85


def prepare_image(image: Image.Image, model_target_size: int) -> np.ndarray:
    """Preprocess image for WD Tagger v3 ONNX inference.

    Steps:
    1. Composite RGBA onto white background (handles PNG transparency).
    2. Pad to square with white fill (preserves aspect ratio).
    3. Resize to model_target_size using BICUBIC.
    4. Convert to float32 numpy array.
    5. Reverse channel order RGB -> BGR (model was trained on BGR).
    6. Add batch dimension -> [1, H, W, C] (NHWC format).

    Args:
        image: PIL Image (any mode).
        model_target_size: Target square size extracted from ONNX input shape.

    Returns:
        np.ndarray of shape [1, model_target_size, model_target_size, 3], dtype float32, BGR.
    """
    # Step 1: RGBA composite onto white background
    canvas = Image.new("RGBA", image.size, (255, 255, 255))
    canvas.alpha_composite(image.convert("RGBA"))
    image = canvas.convert("RGB")

    # Step 2: Pad to square with white fill
    max_dim = max(image.size)
    pad_left = (max_dim - image.size[0]) // 2
    pad_top = (max_dim - image.size[1]) // 2
    padded = Image.new("RGB", (max_dim, max_dim), (255, 255, 255))
    padded.paste(image, (pad_left, pad_top))

    # Step 3: Resize to model target size
    if max_dim != model_target_size:
        padded = padded.resize((model_target_size, model_target_size), Image.BICUBIC)

    # Steps 4-6: Array + BGR + batch dimension
    arr = np.asarray(padded, dtype=np.float32)
    arr = arr[:, :, ::-1]  # RGB -> BGR
    return np.expand_dims(arr, axis=0)  # [H, W, C] -> [1, H, W, C]


@lru_cache(maxsize=1)
def _get_tagger() -> tuple:
    """Load WD Tagger v3 ONNX model once and cache.

    Lazy-imports onnxruntime, pandas, and huggingface_hub so they are only
    required when the tagger is actually used (not at module import time).

    Returns:
        Tuple of (model, tag_names, general_indexes, character_indexes, target_size).

    Raises:
        ImportError: If [tagger] dependencies are not installed.
    """
    try:
        import onnxruntime as rt
        import pandas as pd
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise ImportError(
            f"WD Tagger requires additional dependencies: {exc}. "
            "Install with: pip install 'klippbok[tagger]'"
        ) from exc

    csv_path = hf_hub_download(MODEL_REPO, LABEL_FILENAME)
    model_path = hf_hub_download(MODEL_REPO, MODEL_FILENAME)

    tags_df = pd.read_csv(csv_path)
    tag_names: list[str] = tags_df["name"].tolist()
    # category 0 = general tags, category 4 = character tags
    general_indexes = np.where(tags_df["category"] == 0)[0]
    character_indexes = np.where(tags_df["category"] == 4)[0]

    model = rt.InferenceSession(model_path)
    # Extract target size from ONNX input shape — do NOT hardcode 448
    _, height, _width, _ = model.get_inputs()[0].shape

    return model, tag_names, general_indexes, character_indexes, height


def tag_image_booru(
    image_path: Path,
    general_threshold: float = GENERAL_THRESHOLD,
    character_threshold: float = CHARACTER_THRESHOLD,
) -> tuple[list[str], list[str]]:
    """Tag a single image with booru-style tags via WD Tagger v3 ONNX.

    Parentheses in tag names are escaped per booru convention:
    ``(`` -> ``\\(`` and ``)`` -> ``\\)``.

    Args:
        image_path: Path to the image file.
        general_threshold: Minimum score to include a general tag (default 0.35).
        character_threshold: Minimum score to include a character tag (default 0.85).

    Returns:
        Tuple of (general_tags, character_tags). Each list is sorted by score
        descending (highest confidence first).
    """
    model, tag_names, general_idx, char_idx, target_size = _get_tagger()

    image = Image.open(image_path)
    arr = prepare_image(image, target_size)

    input_name = model.get_inputs()[0].name
    label_name = model.get_outputs()[0].name
    preds = model.run([label_name], {input_name: arr})[0]

    labels = list(zip(tag_names, preds[0].astype(float)))

    # General tags: filter by threshold, sort descending, escape parens
    general_scored = [
        (labels[i][0], labels[i][1])
        for i in general_idx
        if labels[i][1] > general_threshold
    ]
    general_scored.sort(key=lambda x: x[1], reverse=True)
    general_tags = [
        t.replace("(", r"\(").replace(")", r"\)") for t, _ in general_scored
    ]

    # Character tags: filter by threshold, sort descending, escape parens
    char_scored = [
        (labels[i][0], labels[i][1])
        for i in char_idx
        if labels[i][1] > character_threshold
    ]
    char_scored.sort(key=lambda x: x[1], reverse=True)
    char_tags = [
        t.replace("(", r"\(").replace(")", r"\)") for t, _ in char_scored
    ]

    return general_tags, char_tags
