"""Tests for klippbok.curation.presets module."""

from __future__ import annotations

import pytest

from klippbok.curation.presets import get_target_count_default, get_weights


class TestGetTargetCountDefault:
    """Tests for model-aware target count lookup."""

    @pytest.mark.parametrize(
        "model_name,expected",
        [
            ("sd15", 40),
            ("sdxl", 80),
            ("flux", 100),
            ("pony", 70),
            ("SD15", 40),
            ("SDXL", 80),
            ("Flux", 100),
            ("PONY", 70),
        ],
        ids=[
            "sd15", "sdxl", "flux", "pony",
            "SD15-upper", "SDXL-upper", "Flux-mixed", "PONY-upper",
        ],
    )
    def test_known_models(self, model_name: str, expected: int) -> None:
        assert get_target_count_default(model_name) == expected

    def test_custom_model_returns_default(self) -> None:
        assert get_target_count_default("custom") == 60

    def test_unknown_model_returns_default(self) -> None:
        assert get_target_count_default("some_unknown_model") == 60

    def test_none_returns_default(self) -> None:
        assert get_target_count_default(None) == 60


class TestGetWeights:
    """Tests for mode-specific weight retrieval."""

    def test_character_weights(self) -> None:
        weights = get_weights("character")
        assert weights["face"] == 0.40
        assert weights["technical"] == 0.25
        assert weights["aesthetic"] == 0.20
        assert weights["other"] == 0.15

    def test_style_weights(self) -> None:
        weights = get_weights("style")
        assert weights["aesthetic"] == 0.35
        assert weights["technical"] == 0.30
        assert weights["face"] == 0.20
        assert weights["other"] == 0.15

    def test_character_weights_sum_to_one(self) -> None:
        weights = get_weights("character")
        assert abs(sum(weights.values()) - 1.0) < 1e-9

    def test_style_weights_sum_to_one(self) -> None:
        weights = get_weights("style")
        assert abs(sum(weights.values()) - 1.0) < 1e-9

    def test_get_weights_returns_copy(self) -> None:
        """Ensure returned dict is a copy, not the module constant."""
        w1 = get_weights("character")
        w1["face"] = 999.0
        w2 = get_weights("character")
        assert w2["face"] == 0.40
