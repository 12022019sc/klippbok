"""Per-project model config overrides, profile resolution, and custom profile CRUD.

Provides the configuration layer that lets users customize model defaults
per-project and create/manage custom profiles. Override values are stored
in .klippbok/model_config.json within the project directory. Custom profiles
live in ~/.klippbok/profiles/ as individual JSON files.

Key functions:
  - resolve_effective_config: merge overrides onto a base profile
  - load_model_config / save_model_config: per-project override persistence
  - reset_override_field: clear a single override back to profile default
  - save_custom_profile / delete_custom_profile: custom profile CRUD
  - get_profile / list_profiles: unified profile lookup (built-in + custom)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from klippbok.config.model_defaults import BUILTIN_PROFILES
from klippbok.config.model_profiles import (
    BucketConfig,
    ModelProfile,
    TrainingHints,
)

logger = logging.getLogger(__name__)

# ─── Constants ───

_PROJECT_CONFIG_DIR = ".klippbok"
_PROJECT_CONFIG_FILE = "model_config.json"
_USER_PROFILES_DIR = Path.home() / ".klippbok" / "profiles"

# Overridable fields on ModelConfigOverride (excluding profile_name)
_OVERRIDE_FIELDS = frozenset({
    "base_resolution",
    "caption_style",
    "bucket_step_size",
    "bucket_min_dimension",
    "bucket_max_dimension",
    "network_rank_default",
    "learning_rate_range",
    "network_alpha_ratio",
    "description",
})


# ─── Override Schema ───


class ModelConfigOverride(BaseModel):
    """Per-project overrides for a model profile.

    All fields except profile_name are optional. Non-None fields will be
    merged onto the base profile by resolve_effective_config().
    """

    profile_name: str = Field(
        description="Name of the base profile to override.",
    )
    base_resolution: int | None = Field(
        default=None,
        description="Override base resolution in pixels.",
    )
    caption_style: Literal["booru", "natural_language"] | None = Field(
        default=None,
        description="Override captioning style.",
    )
    bucket_step_size: int | None = Field(
        default=None,
        description="Override bucket step size.",
    )
    bucket_min_dimension: int | None = Field(
        default=None,
        description="Override bucket minimum dimension.",
    )
    bucket_max_dimension: int | None = Field(
        default=None,
        description="Override bucket maximum dimension.",
    )
    network_rank_default: int | None = Field(
        default=None,
        description="Override default network rank.",
    )
    learning_rate_range: tuple[float, float] | None = Field(
        default=None,
        description="Override learning rate range (min, max).",
    )
    network_alpha_ratio: float | None = Field(
        default=None,
        description="Override network alpha ratio.",
    )
    description: str | None = Field(
        default=None,
        description="Override profile description.",
    )


# ─── Profile Resolution ───


def resolve_effective_config(
    profile: ModelProfile,
    overrides: ModelConfigOverride | None,
) -> ModelProfile:
    """Merge overrides onto a base profile, producing a new ModelProfile.

    Non-None override fields replace their corresponding profile values.
    The result is validated as a full ModelProfile (e.g., base_resolution
    must still be aligned with step_size).

    Args:
        profile: The base ModelProfile to start from.
        overrides: Per-project overrides, or None for no overrides.

    Returns:
        A new ModelProfile with overrides applied.

    Raises:
        ValueError: If the merged result fails ModelProfile validation.
    """
    if overrides is None:
        return profile

    # Build bucket_config with overrides
    bucket_kwargs: dict = {
        "step_size": profile.bucket_config.step_size,
        "min_dimension": profile.bucket_config.min_dimension,
        "max_dimension": profile.bucket_config.max_dimension,
    }
    if overrides.bucket_step_size is not None:
        bucket_kwargs["step_size"] = overrides.bucket_step_size
    if overrides.bucket_min_dimension is not None:
        bucket_kwargs["min_dimension"] = overrides.bucket_min_dimension
    if overrides.bucket_max_dimension is not None:
        bucket_kwargs["max_dimension"] = overrides.bucket_max_dimension

    # Build training_hints with overrides
    hints_kwargs: dict = {
        "learning_rate_range": profile.training_hints.learning_rate_range,
        "network_rank_range": profile.training_hints.network_rank_range,
        "network_rank_default": profile.training_hints.network_rank_default,
        "network_alpha_ratio": profile.training_hints.network_alpha_ratio,
    }
    if overrides.network_rank_default is not None:
        hints_kwargs["network_rank_default"] = overrides.network_rank_default
    if overrides.learning_rate_range is not None:
        hints_kwargs["learning_rate_range"] = overrides.learning_rate_range
    if overrides.network_alpha_ratio is not None:
        hints_kwargs["network_alpha_ratio"] = overrides.network_alpha_ratio

    # Build profile kwargs
    profile_kwargs: dict = {
        "name": profile.name,
        "display_name": profile.display_name,
        "base_resolution": profile.base_resolution,
        "caption_style": profile.caption_style,
        "bucket_config": BucketConfig(**bucket_kwargs),
        "training_hints": TrainingHints(**hints_kwargs),
        "description": profile.description,
    }

    if overrides.base_resolution is not None:
        profile_kwargs["base_resolution"] = overrides.base_resolution
    if overrides.caption_style is not None:
        profile_kwargs["caption_style"] = overrides.caption_style
    if overrides.description is not None:
        profile_kwargs["description"] = overrides.description

    return ModelProfile(**profile_kwargs)


# ─── Per-Project Persistence ───


def save_model_config(
    project_dir: Path,
    overrides: ModelConfigOverride,
) -> Path:
    """Save per-project model config overrides to .klippbok/model_config.json.

    Creates the .klippbok/ directory if it doesn't exist. Only non-None
    override fields are written to disk.

    Args:
        project_dir: Root directory of the project.
        overrides: The overrides to persist.

    Returns:
        Path to the written config file.
    """
    config_dir = project_dir / _PROJECT_CONFIG_DIR
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / _PROJECT_CONFIG_FILE

    data = overrides.model_dump(exclude_none=True)
    config_path.write_text(json.dumps(data, indent=2) + "\n")
    logger.debug("Saved model config to %s", config_path)
    return config_path


def load_model_config(project_dir: Path) -> ModelConfigOverride | None:
    """Load per-project model config overrides from .klippbok/model_config.json.

    Args:
        project_dir: Root directory of the project.

    Returns:
        ModelConfigOverride if config file exists, None otherwise.
    """
    config_path = project_dir / _PROJECT_CONFIG_DIR / _PROJECT_CONFIG_FILE
    if not config_path.is_file():
        return None

    data = json.loads(config_path.read_text())
    return ModelConfigOverride(**data)


def reset_override_field(
    project_dir: Path,
    field_name: str,
) -> ModelConfigOverride:
    """Reset a single override field to None (profile default).

    Loads the current overrides, sets the named field to None, saves,
    and returns the updated overrides.

    Args:
        project_dir: Root directory of the project.
        field_name: Name of the override field to reset.

    Returns:
        Updated ModelConfigOverride with the field set to None.

    Raises:
        ValueError: If field_name is not a valid override field.
        FileNotFoundError: If no config file exists.
    """
    if field_name not in _OVERRIDE_FIELDS:
        raise ValueError(
            f"Unknown override field '{field_name}'. "
            f"Valid fields: {sorted(_OVERRIDE_FIELDS)}"
        )

    overrides = load_model_config(project_dir)
    if overrides is None:
        raise FileNotFoundError(
            f"No model config found in {project_dir / _PROJECT_CONFIG_DIR}"
        )

    # Create updated overrides with the field reset to None
    data = overrides.model_dump(exclude_none=True)
    data.pop(field_name, None)
    updated = ModelConfigOverride(**data)

    save_model_config(project_dir, updated)
    return updated


# ─── Custom Profile CRUD ───


def save_custom_profile(
    profile: ModelProfile,
    based_on: str = "",
) -> Path:
    """Save a custom profile to ~/.klippbok/profiles/{name}.json.

    Creates the profiles directory if it doesn't exist. The profile is
    serialized to JSON with an optional based_on metadata field.

    Args:
        profile: The ModelProfile to save.
        based_on: Name of the profile this was derived from (metadata only).

    Returns:
        Path to the written profile file.
    """
    _USER_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    profile_path = _USER_PROFILES_DIR / f"{profile.name}.json"

    data = profile.model_dump(mode="json")
    if based_on:
        data["based_on"] = based_on

    profile_path.write_text(json.dumps(data, indent=2) + "\n")
    logger.debug("Saved custom profile '%s' to %s", profile.name, profile_path)
    return profile_path


def delete_custom_profile(name: str) -> None:
    """Delete a custom profile by name.

    Args:
        name: Name of the custom profile to delete.

    Raises:
        ValueError: If name refers to a built-in profile.
        FileNotFoundError: If no custom profile with that name exists.
    """
    if name in BUILTIN_PROFILES:
        raise ValueError(
            f"Cannot delete built-in profile '{name}'. "
            f"Only custom profiles can be deleted."
        )

    profile_path = _USER_PROFILES_DIR / f"{name}.json"
    if not profile_path.is_file():
        raise FileNotFoundError(
            f"Custom profile '{name}' not found at {profile_path}"
        )

    profile_path.unlink()
    logger.debug("Deleted custom profile '%s'", name)


def _load_custom_profile(name: str) -> ModelProfile:
    """Load a single custom profile from disk.

    Args:
        name: Name of the custom profile.

    Returns:
        The loaded ModelProfile.

    Raises:
        FileNotFoundError: If the profile file doesn't exist.
    """
    profile_path = _USER_PROFILES_DIR / f"{name}.json"
    if not profile_path.is_file():
        raise FileNotFoundError(
            f"Custom profile '{name}' not found at {profile_path}"
        )

    data = json.loads(profile_path.read_text())
    # Remove metadata fields not part of ModelProfile
    data.pop("based_on", None)
    return ModelProfile(**data)


def _load_all_custom_profiles() -> list[ModelProfile]:
    """Load all custom profiles from ~/.klippbok/profiles/.

    Returns:
        List of custom ModelProfile instances. Empty if directory
        doesn't exist or contains no valid profiles.
    """
    if not _USER_PROFILES_DIR.is_dir():
        return []

    profiles: list[ModelProfile] = []
    for path in sorted(_USER_PROFILES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            data.pop("based_on", None)
            profiles.append(ModelProfile(**data))
        except Exception:
            logger.warning("Failed to load custom profile from %s", path)
    return profiles


# ─── Profile Lookup ───


def get_profile(name: str) -> ModelProfile:
    """Look up a profile by name, checking built-ins first then custom profiles.

    Args:
        name: Profile name to look up.

    Returns:
        The matching ModelProfile.

    Raises:
        KeyError: If no built-in or custom profile with that name exists.
    """
    if name in BUILTIN_PROFILES:
        return BUILTIN_PROFILES[name]

    try:
        return _load_custom_profile(name)
    except FileNotFoundError:
        available = sorted(
            list(BUILTIN_PROFILES.keys())
            + [p.name for p in _load_all_custom_profiles()]
        )
        raise KeyError(
            f"Profile '{name}' not found. Available: {available}"
        )


def list_profiles() -> list[ModelProfile]:
    """List all available profiles (built-in + custom).

    Built-in profiles are listed first, followed by custom profiles.
    Custom profiles that shadow built-in names are excluded.

    Returns:
        List of all available ModelProfile instances.
    """
    builtin_names = set(BUILTIN_PROFILES.keys())
    profiles = list(BUILTIN_PROFILES.values())

    for custom in _load_all_custom_profiles():
        if custom.name not in builtin_names:
            profiles.append(custom)

    return profiles
