"""Caption service -- model-aware caption routing and persistence.

Orchestrates caption generation by routing to the appropriate backend
based on the active model profile (booru vs natural language), and
persisting captions to both the manifest and sidecar .txt files.

Key functions:
  - get_caption_style_for_project: determine style from profile + override
  - caption_image_for_project: generate caption using appropriate backend
  - save_caption: atomically write sidecar + update manifest entry
  - build_vlm_config_from_global: map named provider preset to CaptionConfig
"""

from __future__ import annotations

import hashlib
import logging
import os
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

        # custom_prompt overrides caption_mode prompt (mirrors captioner.py CLI behavior)
        if vlm_config.custom_prompt:
            prompt = vlm_config.custom_prompt
        else:
            prompt = get_image_prompt(
                caption_mode=vlm_config.caption_mode,
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


# ---------------------------------------------------------------------------
# Batch tag operations (CAPT-06, CAPT-07)
# ---------------------------------------------------------------------------


def batch_add_tag(
    tag: str,
    manifest: dict,
    project_dir: Path,
    image_ids: list[str] | None = None,
) -> int:
    """Add a tag to all (or selected) image captions if not already present.

    Iterates manifest images, appending ``', {tag}'`` to each caption that
    does not already contain the tag (case-insensitive). Writes sidecar .txt
    and updates manifest in place for each modified entry.

    Args:
        tag: The booru-style tag to append (e.g. ``'blue_eyes'``).
        manifest: Project manifest dict (mutated in place).
        project_dir: Absolute path to the project root directory.
        image_ids: Optional list of SHA256[:16] IDs to restrict the operation.
            If None, all images with captions are processed.

    Returns:
        Number of captions that were modified.
    """
    modified = 0
    for entry in manifest.get("images", []):
        caption: str | None = entry.get("caption")
        if caption is None:
            continue

        relative_path: str = entry.get("path", "")
        img_id = _image_id(relative_path)

        if image_ids is not None and img_id not in image_ids:
            continue

        # Case-insensitive duplicate check: split into individual tags
        existing_tags = [t.strip().lower() for t in caption.split(",")]
        if tag.lower() in existing_tags:
            continue

        new_caption = f"{caption}, {tag}"
        abs_path = project_dir / relative_path
        save_caption(abs_path, new_caption, manifest, img_id)
        modified += 1

    return modified


def batch_remove_tag(
    tag: str,
    manifest: dict,
    project_dir: Path,
    image_ids: list[str] | None = None,
) -> int:
    """Remove a tag from all (or selected) image captions.

    Splits each caption by ``', '``, filters out the tag (case-insensitive),
    and rejoins. Writes sidecar .txt and updates manifest in place for each
    modified entry.

    Args:
        tag: The booru-style tag to remove (e.g. ``'solo'``).
        manifest: Project manifest dict (mutated in place).
        project_dir: Absolute path to the project root directory.
        image_ids: Optional list of SHA256[:16] IDs to restrict the operation.
            If None, all images with captions are processed.

    Returns:
        Number of captions that were modified.
    """
    modified = 0
    for entry in manifest.get("images", []):
        caption: str | None = entry.get("caption")
        if caption is None:
            continue

        relative_path: str = entry.get("path", "")
        img_id = _image_id(relative_path)

        if image_ids is not None and img_id not in image_ids:
            continue

        tag_lower = tag.lower()
        parts = [t.strip() for t in caption.split(",")]
        new_parts = [t for t in parts if t.lower() != tag_lower]

        if len(new_parts) == len(parts):
            # Tag was not present; no change needed
            continue

        new_caption = ", ".join(new_parts)
        abs_path = project_dir / relative_path
        save_caption(abs_path, new_caption, manifest, img_id)
        modified += 1

    return modified


def batch_replace_tag(
    old_tag: str,
    new_tag: str,
    manifest: dict,
    project_dir: Path,
    image_ids: list[str] | None = None,
) -> int:
    """Replace one tag with another across all (or selected) image captions.

    Splits each caption by ``', '``, replaces ``old_tag`` with ``new_tag``
    (case-insensitive match), and rejoins. If ``old_tag`` is not found in a
    caption, that caption is skipped (no-op, no error). Writes sidecar .txt
    and updates manifest in place for each modified entry.

    Args:
        old_tag: The tag to find (case-insensitive).
        new_tag: The replacement tag.
        manifest: Project manifest dict (mutated in place).
        project_dir: Absolute path to the project root directory.
        image_ids: Optional list of SHA256[:16] IDs to restrict the operation.
            If None, all images with captions are processed.

    Returns:
        Number of captions that were modified.
    """
    modified = 0
    old_lower = old_tag.lower()

    for entry in manifest.get("images", []):
        caption: str | None = entry.get("caption")
        if caption is None:
            continue

        relative_path: str = entry.get("path", "")
        img_id = _image_id(relative_path)

        if image_ids is not None and img_id not in image_ids:
            continue

        parts = [t.strip() for t in caption.split(",")]
        new_parts = [new_tag if t.lower() == old_lower else t for t in parts]

        if new_parts == parts:
            # old_tag not found; no change
            continue

        new_caption = ", ".join(new_parts)
        abs_path = project_dir / relative_path
        save_caption(abs_path, new_caption, manifest, img_id)
        modified += 1

    return modified


def build_vlm_config_from_global(
    provider: str,
    global_config: dict,
    manifest: dict,
) -> "CaptionConfig":
    """Map a named provider preset to a CaptionConfig instance.

    Reads settings from the global config dict (loaded from
    ~/.klippbok/config.json) and builds the appropriate CaptionConfig.

    Provider priority rules (per user decision):
    - config.json API key ALWAYS takes priority over environment variable.
    - Only falls back to env var when the config value is absent or empty.

    Args:
        provider: Named preset: "lm_studio" | "nanogpt" | "gemini".
            - "joycaption" raises ValueError (uses subprocess, not CaptionConfig).
            - Any other value raises ValueError.
        global_config: Global config dict from load_global_config().
        manifest: Project manifest dict (used to extract anchor_word).

    Returns:
        CaptionConfig populated from the global config and manifest.

    Raises:
        ValueError: For "joycaption" (subprocess-based, not API-based) or
            any unrecognised provider name.
    """
    from klippbok.caption.models import CaptionConfig

    # Common fields from manifest and caption config section
    anchor_word: str | None = manifest.get("anchor_word") or None
    custom_prompt: str | None = global_config.get("custom_prompt") or None

    if provider == "lm_studio":
        base_url = global_config.get("lm_studio_base_url", "http://localhost:1234/v1")
        model = global_config.get("lm_studio_model", "")
        return CaptionConfig(
            provider="openai",
            openai_base_url=base_url,
            openai_model=model,
            api_key="lm-studio",  # LM Studio ignores the key but requires one
            anchor_word=anchor_word,
            custom_prompt=custom_prompt,
        )

    elif provider == "nanogpt":
        api_key = global_config.get("nanogpt_api_key", "")
        model = global_config.get("nanogpt_model", "")
        return CaptionConfig(
            provider="openai",
            openai_base_url="https://nano-gpt.com/api/v1",
            openai_model=model,
            api_key=api_key or None,
            anchor_word=anchor_word,
            custom_prompt=custom_prompt,
        )

    elif provider == "gemini":
        # config.json key takes priority over env var (user decision)
        cfg_key = global_config.get("gemini_api_key", "")
        if cfg_key:
            api_key = cfg_key
        else:
            api_key = os.environ.get("GEMINI_API_KEY", "")
        model = global_config.get("gemini_model", "gemini-2.5-flash")
        return CaptionConfig(
            provider="gemini",
            gemini_model=model,
            api_key=api_key or None,
            anchor_word=anchor_word,
            custom_prompt=custom_prompt,
        )

    elif provider == "joycaption":
        raise ValueError(
            "joycaption uses a subprocess backend and cannot be used with "
            "build_vlm_config_from_global(). Use detect_joycaption() and "
            "launch a subprocess directly."
        )

    else:
        raise ValueError(
            f"Unknown provider preset: '{provider}'. "
            "Supported presets: 'lm_studio', 'nanogpt', 'gemini'. "
            "JoyCaption uses a subprocess and is handled separately."
        )


def batch_prepend_trigger(
    trigger: str,
    manifest: dict,
    project_dir: Path,
    image_ids: list[str] | None = None,
) -> int:
    """Prepend a trigger word to all (or selected) image captions (CAPT-06).

    Reuses :func:`klippbok.caption.captioner._prepend_anchor` which checks
    whether the caption already starts with the trigger (case-insensitive)
    before prepending. Writes sidecar .txt and updates manifest in place for
    each modified entry.

    Args:
        trigger: The trigger word to prepend (e.g. ``'ohwx'``).
        manifest: Project manifest dict (mutated in place).
        project_dir: Absolute path to the project root directory.
        image_ids: Optional list of SHA256[:16] IDs to restrict the operation.
            If None, all images with captions are processed.

    Returns:
        Number of captions that were modified.
    """
    from klippbok.caption.captioner import _prepend_anchor

    modified = 0
    for entry in manifest.get("images", []):
        caption: str | None = entry.get("caption")
        if caption is None:
            continue

        relative_path: str = entry.get("path", "")
        img_id = _image_id(relative_path)

        if image_ids is not None and img_id not in image_ids:
            continue

        new_caption = _prepend_anchor(caption, trigger)
        if new_caption == caption:
            # Already starts with trigger; no change needed
            continue

        abs_path = project_dir / relative_path
        save_caption(abs_path, new_caption, manifest, img_id)
        modified += 1

    return modified
