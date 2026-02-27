"""Klippbok service layer.

Stateless business logic extracted from CLI commands. Both CLI and future
API/GUI routes call these functions -- no duplication, identical behavior.

Services:
    dataset_service: Dataset validation, organization, and bucketing preview.
    project_service: Project manifest persistence (.klippbok/manifest.json).
    image_service: Image import, validation, and discovery.
"""

from klippbok.services import image_service
from klippbok.services.dataset_service import (
    organize,
    preview_bucketing,
    validate,
)
from klippbok.services.project_service import (
    load_manifest,
    manifest_exists,
    sample_to_manifest_entry,
    save_manifest,
)

__all__ = [
    # Dataset service
    "validate",
    "organize",
    "preview_bucketing",
    # Project service
    "save_manifest",
    "load_manifest",
    "manifest_exists",
    "sample_to_manifest_entry",
    # Image service
    "image_service",
]
