"""Export service — manifest-filtered image export for LoRA trainer formats.

Provides the core pipeline for exporting cropped, captioned images from
a klippbok project manifest into trainer-specific formats:
  - kohya/sd-scripts: {repeats}_{trigger} {class}/ folder + kohya_config.toml
  - ai-toolkit (ostris): images/ folder + aitoolkit_config.yaml
  - OneTrainer: images/ + output/ folders + concept.json + training_preset.json

Key functions:
  - get_export_candidates: filter manifest for source="crop" images
  - validate_export_candidates: pre-flight check for missing/empty captions
  - get_export_defaults: model-aware defaults from manifest active_profile
  - perform_export: dispatch to correct generator, return ExportResult
"""

from __future__ import annotations

import json
import logging
import random
import shutil
from pathlib import Path
from typing import Callable, Literal

import yaml
from pydantic import BaseModel, Field

from klippbok.config.model_config import get_profile
from klippbok.services.project_service import load_manifest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ExportConfig(BaseModel):
    """Configuration for a single export operation."""

    trainer: Literal["kohya", "aitoolkit", "onetrainer"] = Field(
        default="kohya",
        description="Target trainer format.",
    )
    repeats: int = Field(
        default=5,
        description="Number of training repeats for this dataset.",
    )
    trigger_word: str = Field(
        default="sks",
        description="Trigger word (anchor word) for the LoRA concept.",
    )
    class_name: str = Field(
        default="person",
        description="Class name (for kohya folder naming and OneTrainer).",
    )
    concept_name: str = Field(
        default="",
        description="Concept name for OneTrainer concept.json.",
    )
    output_dir: Path = Field(
        description="Destination directory for exported files.",
    )


class ExportResult(BaseModel):
    """Result of a completed export operation."""

    status: str = Field(description="'ok' on success.")
    image_count: int = Field(description="Number of images copied.")
    config_path: Path = Field(description="Path to the generated trainer config file.")
    output_dir: Path = Field(description="Directory where files were exported.")
    preset_path: Path | None = Field(default=None, description="Path to training preset (OneTrainer only).")


# ---------------------------------------------------------------------------
# Candidate filtering
# ---------------------------------------------------------------------------


def get_export_candidates(project_dir: Path) -> list[dict]:
    """Return manifest image entries with source='crop'.

    Args:
        project_dir: Root of the project directory.

    Returns:
        List of image entry dicts filtered to source="crop".
        Returns empty list if manifest is missing or has no "images" key.
    """
    manifest = load_manifest(project_dir)
    if manifest is None:
        return []
    return [e for e in manifest.get("images", []) if e.get("source") == "crop"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_export_candidates(entries: list[dict]) -> list[dict]:
    """Check entries for missing or empty captions.

    Args:
        entries: Image entry dicts (typically from get_export_candidates).

    Returns:
        List of issue dicts: {"path": ..., "issue": "missing_caption"|"empty_caption"}.
        Empty list when all entries are valid.
    """
    issues: list[dict] = []
    for entry in entries:
        path = entry.get("path", "")
        if "caption" not in entry:
            issues.append({"path": path, "issue": "missing_caption"})
        elif not entry["caption"].strip():
            issues.append({"path": path, "issue": "empty_caption"})
    return issues


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def get_export_defaults(project_dir: Path) -> dict:
    """Return model-aware export defaults from manifest active_profile.

    Reads the manifest for active_profile and anchor_word, then uses
    get_profile() to determine the base_resolution.

    Args:
        project_dir: Root of the project directory.

    Returns:
        Dict with keys: resolution, default_repeats, trigger_word,
        class_name, concept_name.
    """
    manifest = load_manifest(project_dir)

    active_profile = "sd15"
    anchor_word = "sks"

    if manifest:
        active_profile = manifest.get("active_profile") or "sd15"
        anchor_word = manifest.get("anchor_word") or "sks"

    try:
        profile = get_profile(active_profile)
        resolution = profile.base_resolution
    except KeyError:
        logger.warning("Profile '%s' not found, defaulting to 512", active_profile)
        resolution = 512

    return {
        "resolution": resolution,
        "default_repeats": 5,
        "trigger_word": anchor_word,
        "class_name": "person",
        "concept_name": project_dir.name,
    }


# ---------------------------------------------------------------------------
# File copy helper
# ---------------------------------------------------------------------------


def _copy_images_with_captions(
    entries: list[dict],
    project_dir: Path,
    dest_dir: Path,
    progress_cb: Callable[[int, int], None] | None,
) -> int:
    """Copy image files and write stem-matched .txt caption files.

    Captions are written from the manifest entry's "caption" field,
    NOT from any existing .txt files on disk.

    Args:
        entries: Image entry dicts with "path" and optionally "caption".
        project_dir: Project root — source files are relative to this.
        dest_dir: Destination directory (must already exist).
        progress_cb: Optional callback called as (current, total) after each file.

    Returns:
        Number of image files copied.
    """
    total = len(entries)
    count = 0

    for entry in entries:
        src_path = project_dir / entry["path"]
        filename = src_path.name
        stem = src_path.stem

        # Copy image file
        dest_image = dest_dir / filename
        shutil.copy2(src_path, dest_image)

        # Write caption .txt file from manifest (not disk)
        caption = entry.get("caption", "")
        dest_txt = dest_dir / f"{stem}.txt"
        dest_txt.write_text(caption, encoding="utf-8")

        count += 1
        if progress_cb is not None:
            progress_cb(count, total)

    return count


# ---------------------------------------------------------------------------
# Helper: forward slashes
# ---------------------------------------------------------------------------


def _to_fwd(path: Path) -> str:
    """Convert path to forward-slash string (trainer configs require this on Windows)."""
    return str(path).replace("\\", "/")


# ---------------------------------------------------------------------------
# Kohya generator
# ---------------------------------------------------------------------------


def generate_kohya_export(
    entries: list[dict],
    project_dir: Path,
    config: ExportConfig,
    progress_cb: Callable[[int, int], None] | None,
) -> Path:
    """Generate kohya/sd-scripts folder structure and config TOML.

    Creates:
      {output_dir}/{repeats}_{trigger_word} {class_name}/
        *.jpg / *.png / ...   (image files)
        *.txt                  (caption files from manifest)
      {output_dir}/kohya_config.toml

    Args:
        entries: Image entries to export (source="crop").
        project_dir: Project root.
        config: Export configuration.
        progress_cb: Optional progress callback (current, total).

    Returns:
        Path to kohya_config.toml.
    """
    folder_name = f"{config.repeats}_{config.trigger_word} {config.class_name}"
    image_dir = config.output_dir / folder_name
    image_dir.mkdir(parents=True, exist_ok=True)

    _copy_images_with_captions(entries, project_dir, image_dir, progress_cb)

    # Get resolution from manifest defaults (sd15=512 etc)
    defaults = get_export_defaults(project_dir)
    resolution = defaults["resolution"]

    folder_fwd = _to_fwd(Path(folder_name))

    toml_lines = [
        "[general]",
        "shuffle_caption = false",
        'caption_extension = ".txt"',
        "keep_tokens = 1",
        "",
        "[[datasets]]",
        f"resolution = {resolution}",
        "batch_size = 1",
        "",
        "  [[datasets.subsets]]",
        f'  image_dir = "./{folder_fwd}"',
        f'  class_tokens = "{config.trigger_word} {config.class_name}"',
        f"  num_repeats = {config.repeats}",
        "",
    ]

    toml_content = "\n".join(toml_lines)
    toml_path = config.output_dir / "kohya_config.toml"
    toml_path.write_text(toml_content, encoding="utf-8")

    return toml_path


# ---------------------------------------------------------------------------
# ai-toolkit generator
# ---------------------------------------------------------------------------


def generate_aitoolkit_export(
    entries: list[dict],
    project_dir: Path,
    config: ExportConfig,
    progress_cb: Callable[[int, int], None] | None,
) -> Path:
    """Generate ai-toolkit folder structure and YAML config.

    Creates:
      {output_dir}/images/
        *.jpg / ...   (image files)
        *.txt          (caption files from manifest)
      {output_dir}/aitoolkit_config.yaml

    Args:
        entries: Image entries to export (source="crop").
        project_dir: Project root.
        config: Export configuration.
        progress_cb: Optional progress callback.

    Returns:
        Path to aitoolkit_config.yaml.
    """
    image_dir = config.output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    _copy_images_with_captions(entries, project_dir, image_dir, progress_cb)

    defaults = get_export_defaults(project_dir)
    resolution = defaults["resolution"]

    yaml_data = {
        "datasets": [
            {
                "folder_path": "./images",
                "caption_ext": "txt",
                "resolution": [resolution, resolution],
            }
        ]
    }

    yaml_path = config.output_dir / "aitoolkit_config.yaml"
    yaml_path.write_text(yaml.dump(yaml_data, default_flow_style=False), encoding="utf-8")

    return yaml_path


# ---------------------------------------------------------------------------
# OneTrainer preset loading
# ---------------------------------------------------------------------------


def _load_onetrainer_base_preset() -> dict:
    """Load the SD 1.5 Lora Character - Prodigy preset as the base template.

    OneTrainer's ``train.py`` CLI requires a fully-hydrated config (150+ keys
    with ``__version``). This loads the user's preferred preset directly from
    the OneTrainer installation.

    Returns:
        Dict of the full OneTrainer training config.

    Raises:
        FileNotFoundError: If the preset is not found at the expected path.
    """
    from klippbok.services.global_config_service import load_global_config

    global_cfg = load_global_config()
    configured_path = global_cfg.get("onetrainer", {}).get("onetrainer_path")

    from klippbok.services.onetrainer_service import detect_onetrainer
    ot_root = detect_onetrainer(configured_path)
    if ot_root is None:
        raise FileNotFoundError(
            "OneTrainer not found. Configure the install path in Settings."
        )

    preset_path = ot_root / "training_presets" / "SD 1.5 Lora Character - Prodigy.json"
    if not preset_path.is_file():
        raise FileNotFoundError(
            f"OneTrainer preset not found: {preset_path}. "
            "Ensure 'SD 1.5 Lora Character - Prodigy.json' exists in "
            "OneTrainer's training_presets/ directory."
        )

    data = json.loads(preset_path.read_text(encoding="utf-8"))
    logger.info("Loaded OneTrainer base preset: %s", preset_path.name)
    return data


# ---------------------------------------------------------------------------
# OneTrainer generator
# ---------------------------------------------------------------------------


def generate_onetrainer_export(
    entries: list[dict],
    project_dir: Path,
    config: ExportConfig,
    progress_cb: Callable[[int, int], None] | None,
) -> tuple[Path, Path]:
    """Generate OneTrainer workspace structure, concept.json, and training_preset.json.

    Creates the full OneTrainer workspace layout:
      {output_dir}/dataset/images/     ← images + caption .txt files
      {output_dir}/training_concepts/  ← concept.json
      {output_dir}/training_samples/
      {output_dir}/cache/
      {output_dir}/output/             ← LoRA output
      {output_dir}/backup/
      {output_dir}/save/
      {output_dir}/samples/
      {output_dir}/tensorboard/
      {output_dir}/config/             ← training_preset.json

    The concept.json uses OneTrainer v2 schema with proper image/text sub-objects,
    integer image_variations/text_variations, and float balancing.

    Args:
        entries: Image entries to export (source="crop").
        project_dir: Project root.
        config: Export configuration.
        progress_cb: Optional progress callback.

    Returns:
        Tuple of (concept_path, preset_path).
    """
    # Create OneTrainer workspace directories
    workspace_dirs = [
        "dataset/images",
        "training_concepts",
        "training_samples",
        "cache",
        "output",
        "backup",
        "save",
        "samples",
        "tensorboard",
        "config",
    ]
    for subdir in workspace_dirs:
        (config.output_dir / subdir).mkdir(parents=True, exist_ok=True)

    image_dir = config.output_dir / "dataset" / "images"
    lora_output_dir = config.output_dir / "output"

    _copy_images_with_captions(entries, project_dir, image_dir, progress_cb)

    image_dir_fwd = _to_fwd(image_dir.resolve())
    workspace_dir_fwd = _to_fwd(config.output_dir.resolve())
    cache_dir_fwd = _to_fwd((config.output_dir / "cache").resolve())
    lora_output_fwd = _to_fwd((lora_output_dir / f"{config.trigger_word}.safetensors").resolve())

    defaults = get_export_defaults(project_dir)
    resolution = defaults["resolution"]

    # concept.json — OneTrainer v2 schema
    concept = [
        {
            "__version": 2,
            "name": config.concept_name,
            "type": "STANDARD",
            "path": image_dir_fwd,
            "seed": random.randint(-2**31, 2**31 - 1),
            "enabled": True,
            "include_subdirectories": False,
            "image_variations": 1,
            "text_variations": 1,
            "balancing": float(config.repeats),
            "balancing_strategy": "REPEATS",
            "loss_weight": 1.0,
            "image": {
                "__version": 0,
                "enable_crop_jitter": False,
                "enable_random_flip": False,
                "enable_fixed_flip": False,
                "enable_random_rotate": False,
                "enable_random_brightness": False,
                "enable_random_contrast": False,
                "enable_random_saturation": False,
                "enable_random_hue": False,
                "enable_resolution_override": False,
            },
            "text": {
                "__version": 0,
                "prompt_source": "sample",
                "prompt_path": "",
                "caption_ext": ".txt",
                "enable_tag_shuffling": False,
                "tag_delimiter": ",",
                "keep_tags_count": 1,
                "tag_dropout": 0.0,
                "enable_ucg": False,
            },
        }
    ]

    concept_path = config.output_dir / "training_concepts" / f"{config.concept_name}.json"
    concept_path.write_text(
        json.dumps(concept, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # sample_definition.json — Prompts for generating preview images during
    # training. OneTrainer renders these at each sample_after interval and
    # writes them to TensorBoard so you can visually judge LoRA quality.
    trigger = config.trigger_word
    cls = config.class_name
    sample_prompts = [
        f"{trigger}, {cls}, portrait, looking at camera, soft lighting, simple background",
        f"{trigger}, {cls}, upper body, casual clothing, natural lighting, outdoors",
        f"{trigger}, {cls}, close-up, detailed face, studio lighting, neutral background",
    ]
    neg_prompt = (
        "blurry, low quality, deformed, ugly, bad anatomy, "
        "watermark, text, extra limbs, mutated hands"
    )
    sample_seeds = [42, 1337, 7890]
    sample_definition = [
        {
            "__version": 0,
            "enabled": True,
            "prompt": prompt,
            "negative_prompt": neg_prompt,
            "height": resolution,
            "width": resolution,
            "frames": 1,
            "length": 10.0,
            "seed": seed,
            "random_seed": False,
            "diffusion_steps": 20,
            "cfg_scale": 5.0,
            "noise_scheduler": "DPMPP_SDE_KARRAS",
            "text_encoder_1_layer_skip": 0,
            "text_encoder_2_layer_skip": 0,
            "text_encoder_2_sequence_length": None,
            "text_encoder_3_layer_skip": 0,
            "text_encoder_4_layer_skip": 0,
            "transformer_attention_mask": False,
            "force_last_timestep": False,
            "sample_inpainting": False,
            "base_image_path": "",
            "mask_image_path": "",
        }
        for prompt, seed in zip(sample_prompts, sample_seeds)
    ]

    sample_def_path = config.output_dir / "training_samples" / f"{config.concept_name}.json"
    sample_def_path.write_text(
        json.dumps(sample_definition, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # training_preset.json — Load a fully-hydrated preset from OneTrainer's
    # training_presets/ directory as the base template. OneTrainer's train.py
    # CLI requires a complete config with __version and all fields; partial
    # presets (like the built-in #-prefixed ones) crash during config migration.
    training_preset = _load_onetrainer_base_preset()

    # Overlay klippbok-specific workspace fields
    training_preset["workspace_dir"] = workspace_dir_fwd
    training_preset["cache_dir"] = cache_dir_fwd
    training_preset["concept_file_name"] = _to_fwd(concept_path.resolve())
    training_preset["output_model_destination"] = lora_output_fwd
    training_preset["save_filename_prefix"] = f"{config.concept_name}_epoch"
    training_preset["resolution"] = str(resolution)
    training_preset["tensorboard"] = True
    training_preset["tensorboard_expose"] = False
    training_preset["tensorboard_always_on"] = False  # False = OneTrainer launches TB subprocess
    training_preset["tensorboard_port"] = 6006
    training_preset["sample_definition_file_name"] = _to_fwd(sample_def_path.resolve())
    training_preset["sample_after"] = 1
    training_preset["sample_after_unit"] = "EPOCH"
    training_preset["samples_to_tensorboard"] = True

    preset_path = config.output_dir / "config" / "training_preset.json"
    preset_path.write_text(
        json.dumps(training_preset, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return concept_path, preset_path


# ---------------------------------------------------------------------------
# perform_export (dispatcher)
# ---------------------------------------------------------------------------


def perform_export(
    project_dir: Path,
    config: ExportConfig,
    progress_cb: Callable[[int, int], None] | None,
) -> ExportResult:
    """Run the full export pipeline: get candidates, create output dir, generate files.

    Args:
        project_dir: Project root.
        config: Export configuration including trainer and output_dir.
        progress_cb: Optional progress callback passed to the copy step.

    Returns:
        ExportResult with status, image_count, config_path, and output_dir.
    """
    entries = get_export_candidates(project_dir)

    config.output_dir.mkdir(parents=True, exist_ok=True)

    preset_path: Path | None = None

    if config.trainer == "onetrainer":
        config_path, preset_path = generate_onetrainer_export(
            entries, project_dir, config, progress_cb
        )
    elif config.trainer == "kohya":
        config_path = generate_kohya_export(entries, project_dir, config, progress_cb)
    else:
        config_path = generate_aitoolkit_export(entries, project_dir, config, progress_cb)

    return ExportResult(
        status="ok",
        image_count=len(entries),
        config_path=config_path,
        output_dir=config.output_dir,
        preset_path=preset_path,
    )
