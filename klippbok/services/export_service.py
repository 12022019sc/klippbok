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
# OneTrainer generator
# ---------------------------------------------------------------------------


def generate_onetrainer_export(
    entries: list[dict],
    project_dir: Path,
    config: ExportConfig,
    progress_cb: Callable[[int, int], None] | None,
) -> Path:
    """Generate OneTrainer folder structure, concept.json, and training_preset.json.

    Creates:
      {output_dir}/images/
        *.jpg / ...
        *.txt
      {output_dir}/output/       (LoRA output directory)
      {output_dir}/concept.json
      {output_dir}/training_preset.json

    The training_preset.json is based on the user's "SD 1.5 Lora Character - Prodigy"
    preset: rank 64, 7 epochs, batch 2, Prodigy optimizer, 768px resolution.

    Args:
        entries: Image entries to export (source="crop").
        project_dir: Project root.
        config: Export configuration.
        progress_cb: Optional progress callback.

    Returns:
        Path to concept.json.
    """
    image_dir = config.output_dir / "images"
    lora_output_dir = config.output_dir / "output"
    image_dir.mkdir(parents=True, exist_ok=True)
    lora_output_dir.mkdir(parents=True, exist_ok=True)

    _copy_images_with_captions(entries, project_dir, image_dir, progress_cb)

    image_dir_fwd = _to_fwd(image_dir.resolve())
    lora_output_fwd = _to_fwd((lora_output_dir / f"{config.concept_name}.safetensors").resolve())
    concept_file_fwd = _to_fwd((config.output_dir / "concept.json").resolve())

    defaults = get_export_defaults(project_dir)
    resolution = defaults["resolution"]

    # concept.json — OneTrainer concept array
    concept = [
        {
            "name": config.concept_name,
            "type": "STANDARD",
            "path": image_dir_fwd,
            "text": {
                "prompt_source": "sample",
                "prompt_path": "",
                "caption_ext": ".txt",
            },
            "image_variations": [
                {
                    "width": resolution,
                    "height": resolution,
                    "depth": 1,
                    "aspect_ratio_bucketing": True,
                    "resolution": resolution * resolution,
                }
            ],
            "balancing": "REPEATS",
            "repeats": config.repeats,
            "enabled": True,
        }
    ]

    concept_path = config.output_dir / "concept.json"
    concept_path.write_text(
        json.dumps(concept, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # training_preset.json — Prodigy preset template (SD1.5 Lora Character)
    # Based on user's "SD 1.5 Lora Character - Prodigy" preset.
    # TODO: set base_model_name to actual SD1.5 checkpoint path.
    training_preset = {
        "model_type": "STABLE_DIFFUSION",
        # TODO: set base_model_name to your SD1.5 checkpoint path
        "base_model_name": "TODO: path/to/sd15_model.safetensors",
        "concept_file_name": concept_file_fwd,
        "output_model_destination": lora_output_fwd,
        "lora_output": lora_output_fwd,
        "output_model_format": "SAFETENSORS",
        "train_dtype": "FLOAT_16",
        "fallback_train_dtype": "BFLOAT_16",
        "optimizer": {
            "optimizer": "PRODIGY",
            "weight_decay": 0.01,
            "decouple": True,
            "use_bias_correction": True,
            "betas": [0.9, 0.99],
            "safeguard_warmup": False,
            "d_coef": 1.0,
        },
        "learning_rate_scheduler": "CONSTANT",
        "learning_rate": 1.0,
        "learning_rate_warmup_steps": 0,
        "train_unet": True,
        "train_text_encoder": False,
        "network_type": "LORA",
        "network_rank": 64,
        "network_alpha": 32.0,
        "resolution": resolution,
        "num_epochs": 7,
        "batch_size": 2,
        "gradient_checkpointing": True,
        "tensorboard": True,
        "tensorboard_port": 6006,
    }

    preset_path = config.output_dir / "training_preset.json"
    preset_path.write_text(
        json.dumps(training_preset, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return concept_path


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

    generators = {
        "kohya": generate_kohya_export,
        "aitoolkit": generate_aitoolkit_export,
        "onetrainer": generate_onetrainer_export,
    }

    generator = generators[config.trainer]
    config_path = generator(entries, project_dir, config, progress_cb)

    return ExportResult(
        status="ok",
        image_count=len(entries),
        config_path=config_path,
        output_dir=config.output_dir,
    )
