"""Tests for generate_buckets algorithm."""

from __future__ import annotations

import pytest

from klippbok.config.model_profiles import generate_buckets


class TestGenerateBucketsSD15:
    """Tests for SD1.5 bucket generation (512 base)."""

    def test_sd15_buckets_contain_512x512(self) -> None:
        """generate_buckets(512) includes (512, 512)."""
        buckets = generate_buckets(512)
        assert (512, 512) in buckets

    def test_sd15_buckets_are_symmetric(self) -> None:
        """For every (w, h) in result, (h, w) is also present (except squares)."""
        buckets = generate_buckets(512)
        for w, h in buckets:
            if w != h:
                assert (h, w) in buckets, f"Missing transpose of ({w}, {h})"


class TestBucketConstraints:
    """Tests for bucket generation constraints."""

    def test_all_dimensions_are_multiples_of_step(self) -> None:
        """Every w and h in result is divisible by step_size."""
        step = 64
        buckets = generate_buckets(512, step_size=step)
        for w, h in buckets:
            assert w % step == 0, f"Width {w} not multiple of {step}"
            assert h % step == 0, f"Height {h} not multiple of {step}"

    def test_all_buckets_within_pixel_budget(self) -> None:
        """Every w*h <= base_resolution^2."""
        base = 512
        buckets = generate_buckets(base)
        pixel_budget = base * base
        for w, h in buckets:
            assert w * h <= pixel_budget, f"Bucket ({w}, {h}) exceeds budget {pixel_budget}"

    def test_no_extreme_aspect_ratios(self) -> None:
        """max(w,h)/min(w,h) <= max_aspect_ratio for all buckets."""
        max_ar = 2.0
        buckets = generate_buckets(512, max_aspect_ratio=max_ar)
        for w, h in buckets:
            ratio = max(w, h) / min(w, h)
            assert ratio <= max_ar + 1e-9, f"Bucket ({w}, {h}) ratio {ratio} > {max_ar}"

    def test_min_dimension_respected(self) -> None:
        """No dimension below min_dimension."""
        min_dim = 256
        buckets = generate_buckets(512, min_dimension=min_dim)
        for w, h in buckets:
            assert w >= min_dim, f"Width {w} below min {min_dim}"
            assert h >= min_dim, f"Height {h} below min {min_dim}"

    def test_max_dimension_respected(self) -> None:
        """No dimension above max_dimension."""
        max_dim = 1024
        buckets = generate_buckets(512, max_dimension=max_dim)
        for w, h in buckets:
            assert w <= max_dim, f"Width {w} above max {max_dim}"
            assert h <= max_dim, f"Height {h} above max {max_dim}"


class TestBucketGenerationSDXL:
    """Tests for SDXL bucket generation (1024 base)."""

    def test_sdxl_buckets_contain_1024x1024(self) -> None:
        """generate_buckets(1024, min_dimension=512, max_dimension=2048) includes (1024, 1024)."""
        buckets = generate_buckets(1024, min_dimension=512, max_dimension=2048)
        assert (1024, 1024) in buckets


class TestBucketEdgeCases:
    """Tests for edge cases in bucket generation."""

    def test_custom_max_aspect_ratio(self) -> None:
        """max_aspect_ratio=1.5 excludes buckets with ratio > 1.5."""
        buckets = generate_buckets(512, max_aspect_ratio=1.5)
        for w, h in buckets:
            ratio = max(w, h) / min(w, h)
            assert ratio <= 1.5 + 1e-9, f"Bucket ({w}, {h}) ratio {ratio} > 1.5"
        # Also verify that some buckets exist
        assert len(buckets) > 0

    def test_empty_buckets_on_impossible_params(self) -> None:
        """generate_buckets(64, min_dimension=512) returns empty list."""
        buckets = generate_buckets(64, min_dimension=512)
        assert buckets == []

    def test_sd15_bucket_count(self) -> None:
        """generate_buckets(512, step_size=64, min_dimension=256, max_dimension=1024, max_aspect_ratio=2.0) produces expected count."""
        buckets = generate_buckets(
            512,
            step_size=64,
            min_dimension=256,
            max_dimension=1024,
            max_aspect_ratio=2.0,
        )
        # Must have at least the square bucket plus some landscape/portrait pairs
        assert len(buckets) >= 5
        # All buckets unique
        assert len(buckets) == len(set(buckets))
