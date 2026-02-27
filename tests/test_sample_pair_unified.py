"""Tests for unified SamplePair with type discriminator.

Validates that:
- SamplePair defaults to type="video" (backwards compatibility)
- SamplePair supports type="image" with image-specific fields
- Existing construction patterns still work unchanged
- Frozen model prevents mutation
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from klippbok.dataset.models import SamplePair
from klippbok.video.models import IssueCode, Severity, ValidationIssue


class TestSamplePairTypeDefault:
    """SamplePair defaults to type='video' for backwards compatibility."""

    def test_no_type_defaults_to_video(self):
        sample = SamplePair(stem="clip_001", target=Path("clip_001.mp4"))
        assert sample.type == "video"

    def test_explicit_video_type(self):
        sample = SamplePair(type="video", stem="clip", target=Path("clip.mp4"))
        assert sample.type == "video"

    def test_existing_construction_unchanged(self):
        """The exact construction pattern used throughout the codebase still works."""
        sample = SamplePair(
            stem="clip_001",
            target=Path("/data/clip_001.mp4"),
            caption=Path("/data/clip_001.txt"),
            reference=Path("/data/clip_001.png"),
            width=1280,
            height=720,
            frame_count=17,
            fps=16.0,
        )
        assert sample.type == "video"
        assert sample.stem == "clip_001"
        assert sample.has_caption is True
        assert sample.has_reference is True


class TestSamplePairImageType:
    """SamplePair with type='image' for image targets."""

    def test_image_sample_creation(self):
        sample = SamplePair(
            type="image",
            stem="img_001",
            target=Path("img_001.png"),
            format="png",
            color_mode="RGB",
        )
        assert sample.type == "image"
        assert sample.format == "png"
        assert sample.color_mode == "RGB"

    def test_image_sample_with_dimensions(self):
        sample = SamplePair(
            type="image",
            stem="photo",
            target=Path("photo.jpg"),
            format="jpeg",
            color_mode="RGB",
            width=1920,
            height=1080,
        )
        assert sample.width == 1920
        assert sample.height == 1080

    def test_image_sample_with_caption(self):
        sample = SamplePair(
            type="image",
            stem="img",
            target=Path("img.png"),
            caption=Path("img.txt"),
            format="png",
            color_mode="RGB",
        )
        assert sample.has_caption is True

    def test_image_sample_rgba(self):
        sample = SamplePair(
            type="image",
            stem="logo",
            target=Path("logo.png"),
            format="png",
            color_mode="RGBA",
        )
        assert sample.color_mode == "RGBA"


class TestSamplePairImageDefaults:
    """Image-specific fields default to None for video samples."""

    def test_format_none_for_video(self):
        sample = SamplePair(stem="clip", target=Path("clip.mp4"))
        assert sample.format is None

    def test_color_mode_none_for_video(self):
        sample = SamplePair(stem="clip", target=Path("clip.mp4"))
        assert sample.color_mode is None

    def test_frame_count_none_for_image(self):
        sample = SamplePair(
            type="image",
            stem="img",
            target=Path("img.png"),
            format="png",
            color_mode="RGB",
        )
        assert sample.frame_count is None
        assert sample.fps is None


class TestSamplePairProperties:
    """is_valid, errors, warnings work for both types."""

    def test_image_sample_is_valid(self):
        sample = SamplePair(
            type="image",
            stem="img",
            target=Path("img.png"),
            format="png",
            color_mode="RGB",
        )
        assert sample.is_valid is True
        assert len(sample.errors) == 0
        assert len(sample.warnings) == 0

    def test_image_sample_with_error(self):
        issue = ValidationIssue(
            code=IssueCode.CAPTION_MISSING,
            severity=Severity.ERROR,
            message="No caption",
            field="caption",
        )
        sample = SamplePair(
            type="image",
            stem="img",
            target=Path("img.png"),
            issues=[issue],
        )
        assert sample.is_valid is False
        assert len(sample.errors) == 1

    def test_image_sample_with_warning(self):
        issue = ValidationIssue(
            code=IssueCode.IMAGE_RGBA_CONVERSION,
            severity=Severity.WARNING,
            message="Has alpha",
            field="color_mode",
        )
        sample = SamplePair(
            type="image",
            stem="img",
            target=Path("img.png"),
            issues=[issue],
        )
        assert sample.is_valid is True
        assert len(sample.warnings) == 1


class TestSamplePairFrozen:
    """SamplePair is immutable -- can't change type after construction."""

    def test_cannot_assign_type(self):
        sample = SamplePair(stem="clip", target=Path("clip.mp4"))
        with pytest.raises(ValidationError):
            sample.type = "image"  # type: ignore[misc]

    def test_cannot_assign_format(self):
        sample = SamplePair(stem="clip", target=Path("clip.mp4"))
        with pytest.raises(ValidationError):
            sample.format = "png"  # type: ignore[misc]

    def test_cannot_assign_color_mode(self):
        sample = SamplePair(stem="clip", target=Path("clip.mp4"))
        with pytest.raises(ValidationError):
            sample.color_mode = "RGB"  # type: ignore[misc]


class TestSamplePairTypeValidation:
    """Type field only accepts 'image' or 'video'."""

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError):
            SamplePair(type="audio", stem="x", target=Path("x.wav"))  # type: ignore[arg-type]
