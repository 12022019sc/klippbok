"""Unit tests for WD Tagger v3 ONNX preprocessing and tag filtering.

Tests use mocked onnxruntime to avoid downloading the ~380MB ONNX model.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rgb_image(width: int, height: int, color: tuple[int, int, int] = (255, 0, 0)) -> Image.Image:
    """Create a solid-color RGB image."""
    img = Image.new("RGB", (width, height), color)
    return img


def _make_rgba_image(width: int, height: int) -> Image.Image:
    """Create a 32x32 RGBA image with semi-transparent pixels."""
    img = Image.new("RGBA", (width, height), (200, 100, 50, 128))
    return img


# ---------------------------------------------------------------------------
# Task 1 — preprocessing
# ---------------------------------------------------------------------------

class TestPrepareImage:
    """Tests for prepare_image() preprocessing function."""

    def test_prepare_image_rgb_output_shape(self) -> None:
        """100x50 RGB image produces [1, target_size, target_size, 3] float32 array."""
        from klippbok.caption.wd_tagger import prepare_image

        img = _make_rgb_image(100, 50)
        target_size = 64  # Use smaller size in tests to keep fast
        result = prepare_image(img, target_size)

        assert result.shape == (1, target_size, target_size, 3), (
            f"Expected shape (1, {target_size}, {target_size}, 3), got {result.shape}"
        )

    def test_prepare_image_rgb_dtype_float32(self) -> None:
        """Output array must be float32."""
        from klippbok.caption.wd_tagger import prepare_image

        img = _make_rgb_image(100, 50)
        result = prepare_image(img, 64)

        assert result.dtype == np.float32, f"Expected float32, got {result.dtype}"

    def test_prepare_image_rgba_composites_onto_white(self) -> None:
        """RGBA image with transparency composites correctly onto white background."""
        from klippbok.caption.wd_tagger import prepare_image

        # Create an RGBA image where alpha=0 (fully transparent)
        img = Image.new("RGBA", (32, 32), (255, 0, 0, 0))  # fully transparent red
        result = prepare_image(img, 32)

        # Transparent pixels should become white (255, 255, 255) in RGB
        # In BGR order that is still (255, 255, 255)
        # Values stay between 0-255 as float
        pixel = result[0, 0, 0, :]  # BGR
        assert pixel[0] == pytest.approx(255.0), "Blue channel of transparent pixel should be 255 (white)"
        assert pixel[1] == pytest.approx(255.0), "Green channel of transparent pixel should be 255 (white)"
        assert pixel[2] == pytest.approx(255.0), "Red channel of transparent pixel should be 255 (white)"

    def test_prepare_image_rgba_semi_transparent_blends(self) -> None:
        """RGBA image with semi-transparency blends with white background."""
        from klippbok.caption.wd_tagger import prepare_image

        # Create RGBA image: fully opaque red pixel at (0,0)
        img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))  # fully opaque red
        result = prepare_image(img, 32)

        # In BGR order: red pixel becomes (0, 0, 255) in BGR
        pixel = result[0, 0, 0, :]  # first pixel, BGR
        assert pixel[0] == pytest.approx(0.0), "Blue channel of opaque red should be 0"
        assert pixel[1] == pytest.approx(0.0), "Green channel of opaque red should be 0"
        assert pixel[2] == pytest.approx(255.0), "Red channel of opaque red in BGR pos[2] should be 255"

    def test_prepare_image_square_padding_wide(self) -> None:
        """Wide image (100x50) is padded to 100x100 square before resize."""
        from klippbok.caption.wd_tagger import prepare_image

        img = _make_rgb_image(100, 50, color=(0, 128, 0))  # green
        result = prepare_image(img, 100)

        # Output must be square
        assert result.shape[1] == result.shape[2] == 100

    def test_prepare_image_square_padding_tall(self) -> None:
        """Tall image (50x100) is padded to 100x100 square before resize."""
        from klippbok.caption.wd_tagger import prepare_image

        img = _make_rgb_image(50, 100, color=(0, 0, 255))  # blue
        result = prepare_image(img, 100)

        assert result.shape[1] == result.shape[2] == 100

    def test_prepare_image_bgr_channel_order(self) -> None:
        """Pure red [255,0,0] in RGB becomes [0,0,255] in BGR (last channel = 255)."""
        from klippbok.caption.wd_tagger import prepare_image

        # Pure red image
        img = _make_rgb_image(32, 32, color=(255, 0, 0))
        result = prepare_image(img, 32)

        # After RGB->BGR: B=0, G=0, R=255 stored as float32
        pixel = result[0, 16, 16, :]  # center pixel
        assert pixel[0] == pytest.approx(0.0), "BGR Blue channel of pure red image should be 0"
        assert pixel[1] == pytest.approx(0.0), "BGR Green channel of pure red image should be 0"
        assert pixel[2] == pytest.approx(255.0), "BGR Red channel of pure red image should be 255 (last)"

    def test_prepare_image_nhwc_format(self) -> None:
        """Output has batch dimension first: shape is [1, H, W, C] not [C, H, W]."""
        from klippbok.caption.wd_tagger import prepare_image

        img = _make_rgb_image(64, 64)
        result = prepare_image(img, 64)

        assert result.ndim == 4, f"Expected 4D NHWC array, got {result.ndim}D"
        assert result.shape[0] == 1, "Batch dimension must be 1"
        assert result.shape[3] == 3, "Channel dimension (last) must be 3"


# ---------------------------------------------------------------------------
# Task 2 — tag filtering with mocked ONNX
# ---------------------------------------------------------------------------

def _make_mock_tagger(
    tag_names: list[str],
    categories: list[int],
    scores: list[float],
    target_size: int = 64,
) -> tuple:
    """Build a fake (model, tag_names, general_indexes, character_indexes, target_size) tuple.

    Does NOT import pandas — uses numpy directly so tests run without [tagger] deps.
    """
    categories_arr = np.array(categories, dtype=np.int32)
    general_indexes = np.where(categories_arr == 0)[0]
    character_indexes = np.where(categories_arr == 4)[0]

    mock_model = MagicMock()
    mock_input = MagicMock()
    mock_input.name = "input"
    mock_input.shape = [1, target_size, target_size, 3]
    mock_output = MagicMock()
    mock_output.name = "output"
    mock_model.get_inputs.return_value = [mock_input]
    mock_model.get_outputs.return_value = [mock_output]
    mock_model.run.return_value = [np.array([scores], dtype=np.float32)]

    return mock_model, tag_names, general_indexes, character_indexes, target_size


class TestTagFiltering:
    """Tests for tag_image_booru() filtering, sorting, and escaping."""

    def test_tag_filtering_general_above_threshold(self, tmp_path: Path) -> None:
        """Only general tags above general_threshold=0.35 are returned."""
        from klippbok.caption.wd_tagger import tag_image_booru

        # 3 general tags: scores 0.8, 0.3, 0.5
        tagger = _make_mock_tagger(
            tag_names=["high_tag", "low_tag", "mid_tag"],
            categories=[0, 0, 0],
            scores=[0.8, 0.3, 0.5],
        )

        img_path = tmp_path / "test.png"
        Image.new("RGB", (64, 64), (128, 128, 128)).save(str(img_path))

        with patch("klippbok.caption.wd_tagger._get_tagger", return_value=tagger):
            general, chars = tag_image_booru(img_path, general_threshold=0.35)

        # Only tags with score > 0.35 should appear (0.8 and 0.5, not 0.3)
        assert "high_tag" in general
        assert "mid_tag" in general
        assert "low_tag" not in general, "Tag with score 0.3 should be excluded (below 0.35)"
        assert chars == []

    def test_tag_filtering_character_above_threshold(self, tmp_path: Path) -> None:
        """Only character tags above character_threshold=0.85 are returned."""
        from klippbok.caption.wd_tagger import tag_image_booru

        tagger = _make_mock_tagger(
            tag_names=["char_high", "char_low"],
            categories=[4, 4],
            scores=[0.90, 0.80],
        )

        img_path = tmp_path / "test.png"
        Image.new("RGB", (64, 64)).save(str(img_path))

        with patch("klippbok.caption.wd_tagger._get_tagger", return_value=tagger):
            general, chars = tag_image_booru(img_path, character_threshold=0.85)

        assert "char_high" in chars
        assert "char_low" not in chars, "Tag with score 0.80 should be excluded (below 0.85)"
        assert general == []

    def test_tag_filtering_general_at_threshold_excluded(self, tmp_path: Path) -> None:
        """Tag with score exactly equal to threshold is NOT included (strict >)."""
        from klippbok.caption.wd_tagger import tag_image_booru

        tagger = _make_mock_tagger(
            tag_names=["exact_tag"],
            categories=[0],
            scores=[0.35],  # exactly at threshold
        )

        img_path = tmp_path / "test.png"
        Image.new("RGB", (64, 64)).save(str(img_path))

        with patch("klippbok.caption.wd_tagger._get_tagger", return_value=tagger):
            general, chars = tag_image_booru(img_path, general_threshold=0.35)

        assert "exact_tag" not in general, "Score exactly at threshold should be excluded (strict >)"

    @pytest.mark.parametrize("threshold,score,expected_in", [
        (0.35, 0.36, True),   # just above threshold
        (0.35, 0.35, False),  # exactly at threshold (strict >)
        (0.35, 0.34, False),  # just below threshold
        (0.85, 0.90, True),   # clearly above character threshold
        (0.85, 0.80, False),  # clearly below character threshold
    ])
    def test_threshold_edge_cases_general(
        self,
        tmp_path: Path,
        threshold: float,
        score: float,
        expected_in: bool,
    ) -> None:
        """Parametrized threshold edge cases for general tags."""
        from klippbok.caption.wd_tagger import tag_image_booru

        tagger = _make_mock_tagger(
            tag_names=["edge_tag"],
            categories=[0],
            scores=[score],
        )

        img_path = tmp_path / "test.png"
        Image.new("RGB", (64, 64)).save(str(img_path))

        with patch("klippbok.caption.wd_tagger._get_tagger", return_value=tagger):
            general, _ = tag_image_booru(img_path, general_threshold=threshold)

        tag_present = "edge_tag" in general
        assert tag_present == expected_in, (
            f"score={score}, threshold={threshold}: expected in={expected_in}, got in={tag_present}"
        )

    def test_parentheses_escape(self, tmp_path: Path) -> None:
        """Tags containing parentheses are escaped: tag_(name) -> tag_\\(name\\)."""
        from klippbok.caption.wd_tagger import tag_image_booru

        tagger = _make_mock_tagger(
            tag_names=["tag_(name)", "normal_tag"],
            categories=[0, 0],
            scores=[0.9, 0.9],
        )

        img_path = tmp_path / "test.png"
        Image.new("RGB", (64, 64)).save(str(img_path))

        with patch("klippbok.caption.wd_tagger._get_tagger", return_value=tagger):
            general, _ = tag_image_booru(img_path, general_threshold=0.35)

        assert r"tag_\(name\)" in general, "Parentheses in tag names must be escaped"
        assert "tag_(name)" not in general, "Unescaped parentheses should not appear"
        assert "normal_tag" in general

    def test_tag_sorting_descending(self, tmp_path: Path) -> None:
        """Tags are sorted by score descending (highest confidence first)."""
        from klippbok.caption.wd_tagger import tag_image_booru

        tagger = _make_mock_tagger(
            tag_names=["low_score", "high_score", "mid_score"],
            categories=[0, 0, 0],
            scores=[0.4, 0.9, 0.7],
        )

        img_path = tmp_path / "test.png"
        Image.new("RGB", (64, 64)).save(str(img_path))

        with patch("klippbok.caption.wd_tagger._get_tagger", return_value=tagger):
            general, _ = tag_image_booru(img_path, general_threshold=0.35)

        assert general == ["high_score", "mid_score", "low_score"], (
            f"Tags must be sorted highest score first, got: {general}"
        )

    def test_general_and_character_separated(self, tmp_path: Path) -> None:
        """General and character tags are returned in separate lists."""
        from klippbok.caption.wd_tagger import tag_image_booru

        tagger = _make_mock_tagger(
            tag_names=["general_tag", "char_tag"],
            categories=[0, 4],
            scores=[0.8, 0.9],
        )

        img_path = tmp_path / "test.png"
        Image.new("RGB", (64, 64)).save(str(img_path))

        with patch("klippbok.caption.wd_tagger._get_tagger", return_value=tagger):
            general, chars = tag_image_booru(
                img_path, general_threshold=0.35, character_threshold=0.85
            )

        assert "general_tag" in general
        assert "char_tag" not in general
        assert "char_tag" in chars
        assert "general_tag" not in chars


# ---------------------------------------------------------------------------
# Task 3 — import error message
# ---------------------------------------------------------------------------

class TestImportErrorMessage:
    """Tests for missing dependency error handling."""

    def test_import_error_message_mentions_pip_install(self) -> None:
        """When onnxruntime is not installed, ImportError message includes pip install hint."""
        from klippbok.caption.wd_tagger import _get_tagger

        # Clear the lru_cache so we trigger the import path fresh
        _get_tagger.cache_clear()

        # Simulate ImportError for onnxruntime
        with patch.dict(sys.modules, {"onnxruntime": None, "pandas": None, "huggingface_hub": None}):
            with pytest.raises(ImportError) as exc_info:
                _get_tagger()

        error_message = str(exc_info.value)
        assert "klippbok[tagger]" in error_message, (
            f"Error message should mention 'klippbok[tagger]', got: {error_message}"
        )
        assert "pip install" in error_message, (
            f"Error message should mention 'pip install', got: {error_message}"
        )

        # Restore cache state for other tests
        _get_tagger.cache_clear()
