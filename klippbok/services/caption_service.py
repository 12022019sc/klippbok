"""Caption service -- model-aware caption routing and persistence.

Orchestrates caption generation by routing to the appropriate backend
based on the active model profile (booru vs natural language), and
persisting captions to both the manifest and sidecar .txt files.

Key functions:
  - get_caption_style_for_project: determine style from profile + override
  - caption_image_for_project: generate caption using appropriate backend
  - save_caption: atomically write sidecar + update manifest entry
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Literal

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from klippbok.caption.models import CaptionConfig


def _image_id(relative_path: str) -> str:
    """Compute the image ID from its relative path.

    Args:
        relative_path: Path relative to project root.

    Returns:
        SHA256 hex digest of the path, truncated to 16 characters.
    """
    return hashlib.sha256(relative_path.encode()).hexdigest()[:16]


def get_caption_style_for_project(
    manifest: dict,
) -> Literal["booru", "natural_language"]:
    """Determine the caption style for a project.

    Checks the manifest for a ``caption_style_override`` key first (CAPT-04).
    If no override is set, falls back to the active profile's ``caption_style``.
    Defaults to "natural_language" if the profile cannot be resolved.

    Args:
        manifest: Project manifest dict (from load_manifest).

    Returns:
        "booru" or "natural_language".
    """
    from klippbok.config.model_config import get_profile

    # 1. Dataset-level override takes priority (CAPT-04)
    override = manifest.get("caption_style_override")
    if override in ("booru", "natural_language"):
        return override  # type: ignore[return-value]

    # 2. Fall back to active model profile
    active_profile = manifest.get("active_profile", "sdxl")
    try:
        profile = get_profile(active_profile)
        return profile.caption_style
    except (KeyError, Exception) as exc:
        logger.warning(
            "Could not resolve profile '%s': %s. Defaulting to natural_language.",
            active_profile, exc,
        )
        return "natural_language"


def caption_image_for_project(
    image_path: Path,
    manifest: dict,
    vlm_config: CaptionConfig | None = None,
    general_threshold: float = 0.35,
) -> str:
    """Generate a caption for an image using the appropriate backend.

    Routes to WD Tagger v3 (booru) or a VLM backend (natural language)
    based on the active model profile and any manifest override.

    Args:
        image_path: Absolute path to the image file.
        manifest: Project manifest dict (used for profile/override lookup).
        vlm_config: CaptionConfig for NL backends. Required when style is
            "natural_language"; ignored for "booru".
        general_threshold: Confidence threshold for booru general tags (0.0-1.0).
            Tags below this score are filtered out. Default 0.35 (WD Tagger standard).

    Returns:
        Caption string ready to write to manifest and sidecar .txt.

    Raises:
        ValueError: If style is "natural_language" but vlm_config is not provided.
        ImportError: If WD Tagger dependencies are not installed.
    """
    style = get_caption_style_for_project(manifest)

    if style == "booru":
        # Lazy import — onnxruntime/pandas are optional [tagger] dependencies
        from klippbok.caption.wd_tagger import tag_image_booru

        general_tags, char_tags = tag_image_booru(
            image_path,
            general_threshold=general_threshold,
        )
        # Characters first (most relevant), then general tags
        all_tags = char_tags + general_tags
        return ", ".join(all_tags)

    else:
        # natural_language — requires VLM config
        if vlm_config is None:
            raise ValueError(
                "vlm_config is required for natural_language captioning. "
                "Provide a CaptionConfig with provider and api_key."
            )

        from klippbok.caption.captioner import _create_backend
        from klippbok.caption.prompts import get_image_prompt

        backend = _create_backend(vlm_config)
        prompt = get_image_prompt(
            use_case=vlm_config.use_case,
            anchor_word=vlm_config.anchor_word,
            secondary_anchors=vlm_config.secondary_anchors,
        )
        return backend.caption_image(image_path, prompt)


def save_caption(
    image_path: Path,
    caption: str,
    manifest: dict,
    image_id: str,
) -> None:
    """Atomically save a caption to both the sidecar .txt and manifest entry.

    MUST be called for every caption write (generate, edit, batch).
    Both storage locations are always updated together to stay in sync.
    The manifest is mutated in place -- caller is responsible for persisting
    the manifest to disk after this function returns.

    Args:
        image_path: Absolute path to the image file on disk.
        caption: The caption text to save.
        manifest: Project manifest dict (mutated in place).
        image_id: SHA256[:16] image ID used to locate the manifest entry.
    """
    # 1. Write sidecar .txt alongside the image (for export pipeline)
    sidecar_path = image_path.with_suffix(".txt")
    sidecar_path.write_text(caption, encoding="utf-8")
    logger.debug("Wrote sidecar caption to %s", sidecar_path)

    # 2. Update the manifest entry in place
    found = False
    for entry in manifest.get("images", []):
        relative_path = entry.get("path", "")
        if _image_id(relative_path) == image_id:
            entry["caption"] = caption
            found = True
            break

    if not found:
        logger.warning(
            "save_caption: image_id '%s' not found in manifest; "
            "sidecar written but manifest not updated.",
            image_id,
        )
