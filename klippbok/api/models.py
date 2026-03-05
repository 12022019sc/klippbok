"""Pydantic response schemas for the klippbok API.

These models define the JSON contract between the FastAPI backend
and the React frontend.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ImageStatusResponse(BaseModel):
    """Response model for a single image entry in the gallery.

    Fields mirror the manifest structure produced by batch_import_images,
    with computed fields added for frontend convenience (id, thumbnail_url).
    """

    id: str
    """SHA256 of relative_path, truncated to 16 hex characters."""

    relative_path: str
    """Path relative to the project root (e.g. 'images/photo.jpg')."""

    thumbnail_url: str
    """URL to fetch the JPEG thumbnail (e.g. '/api/v1/images/{id}/thumbnail')."""

    width: int
    """Image width in pixels."""

    height: int
    """Image height in pixels."""

    resolution_ok: bool
    """True if the image does NOT require upscaling to fit its bucket."""

    quality_pass: bool
    """True if no blur was detected (IMAGE_BLUR_DETECTED issue absent)."""

    bucket: str | None
    """Assigned training bucket, e.g. '768x512', or None if not assigned."""

    is_near_duplicate: bool
    """True if the image was flagged as a near-duplicate of another image."""

    duplicate_group_id: str | None
    """First 8 hex chars of the pHash for grouping duplicates, or None."""

    caption: str | None
    """Caption text if available, or None."""

    media_type: str = "image"
    """Media type: 'image' or 'video'."""

    full_url: str = ""
    """URL to fetch the full-resolution original file."""

    video_url: str | None = None
    """URL to stream the video file, or None for images."""


class GalleryResponse(BaseModel):
    """Response model for the image gallery list endpoint."""

    total: int
    """Total number of images in the response."""

    images: list[ImageStatusResponse]
    """List of image status objects."""


class ImportRequest(BaseModel):
    """Request body for starting a batch import."""

    directory: str
    """Absolute or relative path to the directory to import from."""

    recursive: bool = False
    """If True, scan subdirectories for images."""


class ImportStarted(BaseModel):
    """Response returned when a batch import is started."""

    operation_id: str
    """UUID identifying this import operation. Use for SSE progress stream."""


class ImportProgress(BaseModel):
    """SSE event payload for import progress updates."""

    operation_id: str
    """UUID of the import operation."""

    current: int
    """Number of images processed so far."""

    total: int
    """Total number of images to process."""

    message: str
    """Human-readable status message."""

    status: str
    """Operation status: 'running' | 'complete' | 'error'."""


class SettingsResponse(BaseModel):
    """Response model for reading current project settings."""

    project_dir: str | None
    """Absolute path to the project directory, or None if no project is active."""

    active_profile: str | None
    """Currently active model profile name, or None if not set."""

    anchor_word: str | None = None
    """Trigger word prepended to all captions, or None if not set."""


class SettingsUpdate(BaseModel):
    """Request body for updating project settings."""

    project_dir: str | None = None
    """Set the active project directory. Creates .klippbok/ if needed."""

    active_profile: str | None = None
    """New active model profile name, or None to clear."""

    anchor_word: str | None = None
    """Trigger word prepended to all captions. Persisted per-project in manifest."""


# --- Directory browser models ---


class DirEntry(BaseModel):
    """A single directory entry for the filesystem browser."""

    name: str
    """Display name (e.g. 'Documents')."""

    path: str
    """Absolute path (e.g. 'C:\\Users\\Shayne\\Documents')."""


class BrowseRootsResponse(BaseModel):
    """Response for listing filesystem roots (drive letters on Windows)."""

    roots: list[DirEntry]
    """Drive letters on Windows, ['/'] on Linux/macOS."""

    home_dir: str
    """User home directory — default start location for the browser."""


class BrowseListResponse(BaseModel):
    """Response for listing subdirectories of a given path."""

    current_path: str
    """Resolved absolute path being listed."""

    parent_path: str | None
    """Parent directory, or None when at a filesystem root."""

    entries: list[DirEntry]
    """Subdirectories only, sorted case-insensitive alphabetically."""

    error: str | None = None
    """Permission or access error message, if any."""


class MkdirRequest(BaseModel):
    """Request body for creating a new subdirectory."""

    parent_path: str
    """Parent directory where the new folder will be created."""

    name: str
    """Name of the new folder (no path separators or '..' allowed)."""


# --- Crop models ---


class CropApplyItem(BaseModel):
    """A single image crop operation specification."""

    image_id: str
    """SHA256[:16] image ID."""

    source_path: str | None = None
    """Absolute path to the source image file (optional — resolved from image_id)."""

    left: int
    """Left edge of crop region in post-rotation image coordinates."""

    top: int
    """Top edge of crop region in post-rotation image coordinates."""

    width: int
    """Width of crop region in pixels."""

    height: int
    """Height of crop region in pixels."""

    rotation: int = 0
    """Rotation in degrees (0, 90, 180, 270)."""

    flip_h: bool = False
    """If True, apply horizontal flip."""

    flip_v: bool = False
    """If True, apply vertical flip."""

    target_width: int
    """Target output width (bucket dimension)."""

    target_height: int
    """Target output height (bucket dimension)."""


class CropApplyRequest(BaseModel):
    """Request body for applying a batch of crop operations."""

    crops: list[CropApplyItem]
    """List of individual crop operations to apply."""


class CropApplyResult(BaseModel):
    """Result of a single crop operation."""

    image_id: str
    """SHA256[:16] image ID."""

    success: bool
    """True if the crop was applied successfully."""

    output_path: str | None = None
    """Absolute path to the output file, or None on failure."""

    error: str | None = None
    """Error message if success is False, or None on success."""


class AutoCropRequest(BaseModel):
    """Request body for running auto-crop on a set of images."""

    image_ids: list[str]
    """List of SHA256[:16] image IDs to auto-crop."""

    bucket_size: int = 1024
    """Base resolution for bucket generation (512, 768, or 1024)."""

    allow_non_square: bool = True
    """If False, restrict buckets to 1:1 square only."""


class AutoCropResult(BaseModel):
    """Auto-crop result for a single image."""

    image_id: str
    """SHA256[:16] image ID."""

    left: int
    """Left edge of the suggested crop in image coordinates."""

    top: int
    """Top edge of the suggested crop in image coordinates."""

    width: int
    """Width of the suggested crop in pixels."""

    height: int
    """Height of the suggested crop in pixels."""

    target_bucket: tuple[int, int]
    """Nearest matching training bucket (width, height)."""

    detection_type: str
    """How the crop was determined: 'pose' (person detected) or 'center' (fallback)."""


# --- Upscale models ---


class UpscaleRequest(BaseModel):
    """Request body for starting a batch upscale operation."""

    image_ids: list[str]
    """List of SHA256[:16] image IDs to upscale."""

    upscaler: str = "seedvr2"
    """Upscaler backend: 'seedvr2' or 'nmkd_siax'."""

    scale_factor: int = 2
    """Upscale factor (e.g. 2 for 2x)."""


class UpscaleProgress(BaseModel):
    """SSE event payload for upscale progress updates."""

    operation_id: str
    """UUID of the upscale operation."""

    current: int
    """Number of images upscaled so far."""

    total: int
    """Total number of images to upscale."""

    message: str
    """Human-readable status message."""

    status: str
    """Operation status: 'running' | 'complete' | 'error'."""


# --- Caption models ---


class CaptionProviderConfig(BaseModel):
    """Provider configuration stored in ~/.klippbok/config.json.

    Holds all provider-specific settings: API keys, base URLs, model names.
    Returned by GET /captions/config and accepted by PUT /captions/config.
    """

    provider: str = "lm_studio"
    """Active provider preset: 'lm_studio' | 'nanogpt' | 'gemini' | 'joycaption'."""

    lm_studio_base_url: str = "http://localhost:1234/v1"
    """Base URL for the LM Studio OpenAI-compatible API."""

    lm_studio_model: str = ""
    """Model name for LM Studio (e.g. 'llava-1.5-13b'). Empty = use whatever is loaded."""

    nanogpt_api_key: str = ""
    """API key for NanoGPT (https://nano-gpt.com)."""

    nanogpt_model: str = ""
    """Model name for NanoGPT vision API."""

    gemini_api_key: str = ""
    """API key for Google Gemini. Overrides GEMINI_API_KEY env var when set."""

    gemini_model: str = "gemini-2.5-flash"
    """Gemini model to use for captioning."""

    joycaption_path: str = ""
    """Path to the JoyCaption installation root (auto-detected if empty)."""

    custom_prompt: str | None = None
    """Custom prompt that overrides the built-in use-case prompt when set."""


class CaptionGenerateRequest(BaseModel):
    """Request body for starting a batch caption generation operation."""

    image_ids: list[str] | None = None
    """SHA256[:16] image IDs to caption. None means caption all images."""

    style: Literal["booru", "natural_language", "auto"] = "auto"
    """Caption style override. 'auto' uses the active model profile default."""

    overwrite: bool = False
    """If True, re-caption images that already have a caption."""

    provider: str | None = None
    """VLM provider for natural language captioning: 'gemini', 'replicate', or 'openai'.
    Required when style is 'natural_language'; ignored for 'booru'."""

    api_key: str | None = None
    """API key for the VLM provider. Required for external providers."""

    general_threshold: float = 0.35
    """Confidence threshold for booru general tags (0.0-1.0).
    Tags below this score are filtered. Default 0.35 is the WD Tagger standard."""

    provider_preset: str | None = None
    """Named provider preset: 'lm_studio' | 'nanogpt' | 'gemini' | 'joycaption'.
    When set, overrides provider + api_key from global config. Takes priority over
    the provider/api_key fields above."""


class CaptionStarted(BaseModel):
    """Response returned when a batch caption generation is started."""

    operation_id: str
    """UUID identifying this caption operation. Use for SSE progress stream."""


class CaptionProgress(BaseModel):
    """SSE event payload for caption generation progress updates."""

    operation_id: str
    """UUID of the caption operation."""

    current: int
    """Number of images captioned so far."""

    total: int
    """Total number of images to caption."""

    message: str
    """Human-readable status message."""

    status: str
    """Operation status: 'running' | 'complete' | 'error'."""


class ProfileInfo(BaseModel):
    """Summary of an available model profile for the Settings UI dropdown."""

    name: str
    """Profile identifier (e.g. 'sd15', 'sdxl', 'flux', 'pony')."""

    display_name: str
    """Human-readable name (e.g. 'Stable Diffusion 1.5')."""

    caption_style: str
    """Default captioning style: 'booru' or 'natural_language'."""

    base_resolution: int
    """Base training resolution in pixels (e.g. 512, 1024)."""


class CaptionUpdateRequest(BaseModel):
    """Request body for updating a single image caption (inline edit)."""

    caption: str
    """The new caption text. Replaces the existing caption."""


class CaptionUpdateResponse(BaseModel):
    """Response after updating a single image caption."""

    image_id: str
    """SHA256[:16] image ID of the updated image."""

    caption: str
    """The saved caption text."""

    sidecar_written: bool
    """True if the sidecar .txt file was successfully written."""


class CaptionBatchRequest(BaseModel):
    """Request body for a batch caption tag operation."""

    operation: Literal["add_tag", "remove_tag", "replace_tag", "prepend_trigger"]
    """The batch operation to perform."""

    value: str
    """The tag or trigger word to operate on (add, remove, replace old, or prepend)."""

    replace_with: str | None = None
    """Replacement tag for 'replace_tag' operation. Ignored for other operations."""

    image_ids: list[str] | None = None
    """Optional list of SHA256[:16] image IDs to restrict the operation.
    If None, the operation applies to all images with captions."""


class CaptionBatchResponse(BaseModel):
    """Response after a batch caption tag operation."""

    operation: str
    """The operation that was performed."""

    modified_count: int
    """Number of captions that were modified."""


class CaptionScoreResponse(BaseModel):
    """Caption quality score for a single image."""

    image_id: str
    """SHA256[:16] image ID."""

    caption: str
    """The caption text that was scored."""

    overall: float
    """Weighted overall quality score (0.0–1.0, higher is better)."""

    length_score: float
    """How appropriate the caption length is (0.0–1.0)."""

    specificity_score: float
    """How concrete vs vague the description is (0.0–1.0)."""

    issues: list[str]
    """Human-readable descriptions of detected problems."""
