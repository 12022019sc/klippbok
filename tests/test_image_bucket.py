"""Tests for klippbok.image.bucket -- nearest-bucket assignment and upscale detection.

Uses generate_buckets() from config/model_profiles.py to create real bucket lists.
All tests are pure-function -- no file I/O.
"""

from __future__ import annotations

import pytest

from klippbok.config.model_profiles import generate_buckets
from klippbok.image.bucket import assign_to_bucket, needs_upscale


# ---------------------------------------------------------------------------
# Fixtures -- reusable bucket lists
# ---------------------------------------------------------------------------

@pytest.fixture()
def sd15_buckets() -> list[tuple[int, int]]:
    """Standard SD1.5 bucket set: 512 base, 64 step, 256-1024 range."""
    return generate_buckets(512, step_size=64, min_dimension=256, max_dimension=1024)


@pytest.fixture()
def sdxl_buckets() -> list[tuple[int, int]]:
    """SDXL bucket set: 1024 base, 64 step, 512-2048 range."""
    return generate_buckets(1024, step_size=64, min_dimension=512, max_dimension=2048)


# ---------------------------------------------------------------------------
# assign_to_bucket
# ---------------------------------------------------------------------------

class TestAssignToBucket:
    """Tests for assign_to_bucket() -- nearest aspect ratio matching."""

    def test_square_image_gets_square_bucket(
        self, sd15_buckets: list[tuple[int, int]]
    ) -> None:
        """500x500 square image should map to (512, 512) square bucket."""
        result = assign_to_bucket(500, 500, sd15_buckets)
        assert result == (512, 512)

    def test_landscape_image_nearest_bucket(
        self, sd15_buckets: list[tuple[int, int]]
    ) -> None:
        """1920x1080 landscape (AR ~1.78) should map to a valid bucket."""
        result = assign_to_bucket(1920, 1080, sd15_buckets)
        assert result is not None
        assert result in sd15_buckets

    def test_portrait_image_nearest_bucket(
        self, sd15_buckets: list[tuple[int, int]]
    ) -> None:
        """1080x1920 portrait should map to a portrait-orientation bucket."""
        result = assign_to_bucket(1080, 1920, sd15_buckets)
        assert result is not None
        assert result in sd15_buckets
        # Portrait bucket has height > width
        bucket_w, bucket_h = result
        assert bucket_h > bucket_w

    def test_exact_bucket_match(
        self, sd15_buckets: list[tuple[int, int]]
    ) -> None:
        """640x384 image should return (640, 384) exactly -- that bucket exists in SD1.5."""
        # SD1.5 (512 base, 512^2=262144 pixel budget) includes (640, 384) but not (768, 512)
        # because 768*512=393216 > 262144. Use a bucket we know is in the list.
        assert (640, 384) in sd15_buckets, "Precondition: (640, 384) must be a valid SD1.5 bucket"
        result = assign_to_bucket(640, 384, sd15_buckets)
        assert result == (640, 384)

    def test_empty_bucket_list_returns_none(self) -> None:
        """Empty bucket list returns None."""
        result = assign_to_bucket(100, 100, [])
        assert result is None

    def test_extreme_aspect_ratio_returns_none(
        self, sd15_buckets: list[tuple[int, int]]
    ) -> None:
        """1920x200 (AR=9.6) exceeds max_aspect_ratio=2.0 -- returns None."""
        result = assign_to_bucket(1920, 200, sd15_buckets, max_aspect_ratio=2.0)
        assert result is None

    def test_slightly_extreme_returns_bucket(
        self, sd15_buckets: list[tuple[int, int]]
    ) -> None:
        """1920x960 (AR=2.0 exactly) at max_aspect_ratio=2.0 returns a valid bucket."""
        result = assign_to_bucket(1920, 960, sd15_buckets, max_aspect_ratio=2.0)
        assert result is not None
        assert result in sd15_buckets

    def test_sdxl_buckets(self, sdxl_buckets: list[tuple[int, int]]) -> None:
        """2048x1024 with SDXL buckets gets a valid bucket."""
        result = assign_to_bucket(2048, 1024, sdxl_buckets)
        assert result is not None
        assert result in sdxl_buckets


# ---------------------------------------------------------------------------
# needs_upscale
# ---------------------------------------------------------------------------

class TestNeedsUpscale:
    """Tests for needs_upscale() -- detects when image is smaller than bucket."""

    def test_no_upscale_needed_larger_image(self) -> None:
        """1920x1080 image assigned to (768, 512) bucket does NOT need upscale."""
        assert needs_upscale(1920, 1080, 768, 512) is False

    def test_upscale_needed_smaller_image(self) -> None:
        """400x300 image assigned to (512, 512) bucket DOES need upscale."""
        assert needs_upscale(400, 300, 512, 512) is True

    def test_upscale_needed_one_dimension_smaller(self) -> None:
        """600x300 image assigned to (512, 512) bucket DOES need upscale (height < 512)."""
        assert needs_upscale(600, 300, 512, 512) is True

    def test_no_upscale_exact_match(self) -> None:
        """512x512 image assigned to (512, 512) does NOT need upscale."""
        assert needs_upscale(512, 512, 512, 512) is False
