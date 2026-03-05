"""Tests for klippbok.caption.pipeline — post-processing pipeline functions.

TDD: These tests are written BEFORE the implementation.
Tests cover:
- CaptionMode model fields (CaptionConfig, CaptionGenerateRequest, CaptionProviderConfig)
- ModelProfile.default_token_budget
- apply_vlm_pipeline: trigger injection, artifact stripping, token trimming
- apply_joycaption_pipeline: prefix strip, blacklist, dedup, appearance filter, trim
- _filter_appearance_tags: hair/eye/body removal, preservation of unrelated tags
- _strip_vlm_artifacts: VLM preambles, markdown bold, wrapping quotes
- _trim_to_budget: tag mode drops from end; NL mode trims at sentence boundary
- Anchor word is never trimmed by token budget
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Model field tests
# ---------------------------------------------------------------------------


class TestCaptionConfigFields:
    """CaptionConfig has caption_mode and max_tokens; use_case is gone."""

    def test_accepts_caption_mode(self) -> None:
        from klippbok.caption.models import CaptionConfig

        config = CaptionConfig(caption_mode="booru_tags", max_tokens=75)
        assert config.caption_mode == "booru_tags"
        assert config.max_tokens == 75

    def test_default_caption_mode(self) -> None:
        from klippbok.caption.models import CaptionConfig

        config = CaptionConfig()
        assert config.caption_mode == "context_only_tags"

    def test_max_tokens_default_none(self) -> None:
        from klippbok.caption.models import CaptionConfig

        config = CaptionConfig()
        assert config.max_tokens is None

    def test_all_5_modes_accepted(self) -> None:
        from klippbok.caption.models import CaptionConfig

        modes = [
            "booru_tags",
            "context_only_tags",
            "context_only_natural",
            "descriptive",
            "straightforward",
        ]
        for mode in modes:
            config = CaptionConfig(caption_mode=mode)
            assert config.caption_mode == mode

    def test_use_case_field_removed(self) -> None:
        """use_case is gone — passing it raises ValidationError."""
        from pydantic import ValidationError

        from klippbok.caption.models import CaptionConfig

        with pytest.raises((ValidationError, TypeError)):
            CaptionConfig(use_case="character")  # type: ignore[call-arg]

    def test_caption_mode_type_exported(self) -> None:
        from klippbok.caption.models import CAPTION_MODE_DEFAULT, CaptionMode

        assert CaptionMode is not None
        assert CAPTION_MODE_DEFAULT == "context_only_tags"


class TestCaptionGenerateRequestFields:
    """CaptionGenerateRequest has caption_mode; style field is gone."""

    def test_accepts_caption_mode(self) -> None:
        from klippbok.api.models import CaptionGenerateRequest

        req = CaptionGenerateRequest(caption_mode="descriptive")
        assert req.caption_mode == "descriptive"

    def test_caption_mode_default_none(self) -> None:
        from klippbok.api.models import CaptionGenerateRequest

        req = CaptionGenerateRequest()
        assert req.caption_mode is None

    def test_style_field_removed(self) -> None:
        """style field is gone."""
        from klippbok.api.models import CaptionGenerateRequest

        req = CaptionGenerateRequest()
        assert not hasattr(req, "style")


class TestCaptionProviderConfigFields:
    """CaptionProviderConfig has caption_mode and max_tokens."""

    def test_caption_mode_field(self) -> None:
        from klippbok.api.models import CaptionProviderConfig

        cfg = CaptionProviderConfig(caption_mode="booru_tags")
        assert cfg.caption_mode == "booru_tags"

    def test_caption_mode_default(self) -> None:
        from klippbok.api.models import CaptionProviderConfig

        cfg = CaptionProviderConfig()
        assert cfg.caption_mode == "context_only_tags"

    def test_max_tokens_field(self) -> None:
        from klippbok.api.models import CaptionProviderConfig

        cfg = CaptionProviderConfig(max_tokens=150)
        assert cfg.max_tokens == 150

    def test_max_tokens_default_none(self) -> None:
        from klippbok.api.models import CaptionProviderConfig

        cfg = CaptionProviderConfig()
        assert cfg.max_tokens is None


class TestModelProfileTokenBudget:
    """ModelProfile.default_token_budget field exists with correct values."""

    def test_sd15_budget(self) -> None:
        from klippbok.config.model_defaults import SD15_PROFILE

        assert SD15_PROFILE.default_token_budget == 75

    def test_sdxl_budget(self) -> None:
        from klippbok.config.model_defaults import SDXL_PROFILE

        assert SDXL_PROFILE.default_token_budget == 150

    def test_flux_budget(self) -> None:
        from klippbok.config.model_defaults import FLUX_PROFILE

        assert FLUX_PROFILE.default_token_budget == 225

    def test_pony_budget(self) -> None:
        from klippbok.config.model_defaults import PONY_PROFILE

        assert PONY_PROFILE.default_token_budget == 75

    def test_model_profile_accepts_budget(self) -> None:
        from klippbok.config.model_profiles import ModelProfile

        profile = ModelProfile(
            name="test",
            display_name="Test",
            base_resolution=512,
            caption_style="booru",
            default_token_budget=100,
        )
        assert profile.default_token_budget == 100

    def test_model_profile_default_budget(self) -> None:
        """Default budget is 150 (SDXL-safe)."""
        from klippbok.config.model_profiles import ModelProfile

        profile = ModelProfile(
            name="test",
            display_name="Test",
            base_resolution=512,
            caption_style="booru",
        )
        assert profile.default_token_budget == 150


# ---------------------------------------------------------------------------
# Pipeline module exports
# ---------------------------------------------------------------------------


class TestPipelineModuleExports:
    """pipeline.py exports the expected names."""

    def test_exports_apply_vlm_pipeline(self) -> None:
        from klippbok.caption.pipeline import apply_vlm_pipeline

        assert callable(apply_vlm_pipeline)

    def test_exports_apply_joycaption_pipeline(self) -> None:
        from klippbok.caption.pipeline import apply_joycaption_pipeline

        assert callable(apply_joycaption_pipeline)

    def test_exports_default_appearance_blacklist(self) -> None:
        from klippbok.caption.pipeline import DEFAULT_APPEARANCE_BLACKLIST

        assert isinstance(DEFAULT_APPEARANCE_BLACKLIST, list)
        assert len(DEFAULT_APPEARANCE_BLACKLIST) > 0


# ---------------------------------------------------------------------------
# _count_tokens_approx
# ---------------------------------------------------------------------------


class TestCountTokensApprox:
    """_count_tokens_approx returns reasonable approximation."""

    def test_empty_string(self) -> None:
        from klippbok.caption.pipeline import _count_tokens_approx

        assert _count_tokens_approx("") >= 1

    def test_single_word(self) -> None:
        from klippbok.caption.pipeline import _count_tokens_approx

        result = _count_tokens_approx("hello")
        assert result >= 1

    def test_longer_text(self) -> None:
        from klippbok.caption.pipeline import _count_tokens_approx

        # 6 words → approx 8 tokens (6 / 0.75)
        result = _count_tokens_approx("one two three four five six")
        assert result == 8

    def test_short_tags(self) -> None:
        from klippbok.caption.pipeline import _count_tokens_approx

        # 3 words in tag list
        result = _count_tokens_approx("blonde hair, blue eyes, smile")
        assert result >= 3


# ---------------------------------------------------------------------------
# _strip_vlm_artifacts
# ---------------------------------------------------------------------------


class TestStripVlmArtifacts:
    """_strip_vlm_artifacts removes VLM preambles and formatting."""

    def test_strips_here_is_a_caption(self) -> None:
        from klippbok.caption.pipeline import _strip_vlm_artifacts

        result = _strip_vlm_artifacts("Here is a caption: Luna stands in the park.")
        assert "Here is a caption:" not in result
        assert "Luna stands in the park" in result

    def test_strips_sure_prefix(self) -> None:
        from klippbok.caption.pipeline import _strip_vlm_artifacts

        result = _strip_vlm_artifacts("Sure! Luna stands in the park.")
        assert result.startswith("Luna")

    def test_strips_markdown_bold(self) -> None:
        from klippbok.caption.pipeline import _strip_vlm_artifacts

        result = _strip_vlm_artifacts("**Luna** stands in the park.")
        assert "**" not in result
        assert "Luna" in result

    def test_strips_wrapping_quotes(self) -> None:
        from klippbok.caption.pipeline import _strip_vlm_artifacts

        result = _strip_vlm_artifacts('"Luna stands in the park."')
        assert not result.startswith('"')
        assert not result.endswith('"')
        assert "Luna" in result

    def test_strips_caption_colon_prefix(self) -> None:
        from klippbok.caption.pipeline import _strip_vlm_artifacts

        result = _strip_vlm_artifacts("Caption: Luna stands in the park.")
        assert "Caption:" not in result

    def test_no_op_on_clean_caption(self) -> None:
        from klippbok.caption.pipeline import _strip_vlm_artifacts

        caption = "Luna stands in the park, smiling."
        result = _strip_vlm_artifacts(caption)
        assert result == caption

    def test_strips_certainly_prefix(self) -> None:
        from klippbok.caption.pipeline import _strip_vlm_artifacts

        result = _strip_vlm_artifacts("Certainly! Here is the caption for you.")
        assert not result.lower().startswith("certainly")


# ---------------------------------------------------------------------------
# _filter_appearance_tags
# ---------------------------------------------------------------------------


class TestFilterAppearanceTags:
    """_filter_appearance_tags removes physical appearance tags."""

    def test_removes_blonde_hair(self) -> None:
        from klippbok.caption.pipeline import (
            DEFAULT_APPEARANCE_BLACKLIST,
            _filter_appearance_tags,
        )

        caption = "1girl, blonde hair, smiling, park, sunny day"
        result = _filter_appearance_tags(caption, DEFAULT_APPEARANCE_BLACKLIST)
        assert "blonde hair" not in result

    def test_removes_blue_eyes(self) -> None:
        from klippbok.caption.pipeline import (
            DEFAULT_APPEARANCE_BLACKLIST,
            _filter_appearance_tags,
        )

        caption = "1girl, blue eyes, sitting, forest"
        result = _filter_appearance_tags(caption, DEFAULT_APPEARANCE_BLACKLIST)
        assert "blue eyes" not in result

    def test_removes_large_breasts(self) -> None:
        from klippbok.caption.pipeline import (
            DEFAULT_APPEARANCE_BLACKLIST,
            _filter_appearance_tags,
        )

        caption = "1girl, large breasts, standing, city"
        result = _filter_appearance_tags(caption, DEFAULT_APPEARANCE_BLACKLIST)
        assert "large breasts" not in result

    def test_preserves_smiling(self) -> None:
        from klippbok.caption.pipeline import (
            DEFAULT_APPEARANCE_BLACKLIST,
            _filter_appearance_tags,
        )

        caption = "1girl, blonde hair, smiling, park"
        result = _filter_appearance_tags(caption, DEFAULT_APPEARANCE_BLACKLIST)
        assert "smiling" in result

    def test_preserves_park(self) -> None:
        from klippbok.caption.pipeline import (
            DEFAULT_APPEARANCE_BLACKLIST,
            _filter_appearance_tags,
        )

        caption = "1girl, blonde hair, smiling, park, sitting"
        result = _filter_appearance_tags(caption, DEFAULT_APPEARANCE_BLACKLIST)
        assert "park" in result

    def test_preserves_sitting(self) -> None:
        from klippbok.caption.pipeline import (
            DEFAULT_APPEARANCE_BLACKLIST,
            _filter_appearance_tags,
        )

        caption = "1girl, blonde hair, smiling, park, sitting"
        result = _filter_appearance_tags(caption, DEFAULT_APPEARANCE_BLACKLIST)
        assert "sitting" in result

    @pytest.mark.parametrize("hair_tag", [
        "blonde hair",
        "brown hair",
        "black hair",
        "red hair",
        "white hair",
        "long hair",
        "short hair",
        "twintails",
        "ponytail",
    ])
    def test_removes_hair_tags(self, hair_tag: str) -> None:
        from klippbok.caption.pipeline import (
            DEFAULT_APPEARANCE_BLACKLIST,
            _filter_appearance_tags,
        )

        caption = f"1girl, {hair_tag}, outdoor scene"
        result = _filter_appearance_tags(caption, DEFAULT_APPEARANCE_BLACKLIST)
        assert hair_tag not in result

    @pytest.mark.parametrize("eye_tag", [
        "blue eyes",
        "brown eyes",
        "green eyes",
        "red eyes",
        "purple eyes",
    ])
    def test_removes_eye_tags(self, eye_tag: str) -> None:
        from klippbok.caption.pipeline import (
            DEFAULT_APPEARANCE_BLACKLIST,
            _filter_appearance_tags,
        )

        caption = f"1girl, {eye_tag}, outdoor scene"
        result = _filter_appearance_tags(caption, DEFAULT_APPEARANCE_BLACKLIST)
        assert eye_tag not in result

    def test_custom_blacklist(self) -> None:
        from klippbok.caption.pipeline import _filter_appearance_tags

        caption = "luna, custom_appearance_tag, standing, park"
        result = _filter_appearance_tags(caption, ["custom_appearance_tag"])
        assert "custom_appearance_tag" not in result
        assert "standing" in result

    def test_empty_caption(self) -> None:
        from klippbok.caption.pipeline import _filter_appearance_tags

        result = _filter_appearance_tags("", [])
        assert result == ""

    def test_empty_blacklist_no_op(self) -> None:
        from klippbok.caption.pipeline import _filter_appearance_tags

        caption = "blonde hair, blue eyes, smiling"
        result = _filter_appearance_tags(caption, [])
        assert result == caption


# ---------------------------------------------------------------------------
# _trim_to_budget
# ---------------------------------------------------------------------------


class TestTrimToBudget:
    """_trim_to_budget trims captions to token budget."""

    def test_tag_mode_drops_from_end(self) -> None:
        from klippbok.caption.pipeline import _trim_to_budget

        caption = "trigger, tag1, tag2, tag3, tag4, tag5, tag6, tag7, tag8, tag9"
        result = _trim_to_budget(caption, token_budget=5, anchor_word="trigger", caption_mode="booru_tags")
        assert "trigger" in result
        assert "tag9" not in result

    def test_tag_mode_anchor_never_dropped(self) -> None:
        """Trigger word is never removed by token budget."""
        from klippbok.caption.pipeline import _trim_to_budget

        caption = "trigger, tag1, tag2, tag3, tag4, tag5, tag6, tag7, tag8"
        result = _trim_to_budget(caption, token_budget=2, anchor_word="trigger", caption_mode="booru_tags")
        assert "trigger" in result

    def test_nl_mode_trims_at_sentence_boundary(self) -> None:
        """NL mode trims at last complete sentence."""
        from klippbok.caption.pipeline import _trim_to_budget

        long_caption = "Luna stands in the park. She is smiling. The sky is blue. A bird flies past."
        result = _trim_to_budget(long_caption, token_budget=10, anchor_word="Luna", caption_mode="descriptive")
        # Must end at a sentence boundary
        assert result.endswith(".")

    def test_under_budget_no_change(self) -> None:
        """Short caption under budget is unchanged."""
        from klippbok.caption.pipeline import _trim_to_budget

        caption = "Luna smiles."
        result = _trim_to_budget(caption, token_budget=200, anchor_word="Luna", caption_mode="descriptive")
        assert result == caption

    def test_context_only_tags_mode_drops_from_end(self) -> None:
        from klippbok.caption.pipeline import _trim_to_budget

        caption = "anchor, a, b, c, d, e, f, g, h, i, j"
        result = _trim_to_budget(caption, token_budget=3, anchor_word="anchor", caption_mode="context_only_tags")
        assert "anchor" in result
        assert "j" not in result

    def test_no_anchor_tag_mode(self) -> None:
        """Tag mode without anchor still trims from end."""
        from klippbok.caption.pipeline import _trim_to_budget

        caption = "tag1, tag2, tag3, tag4, tag5, tag6, tag7, tag8"
        result = _trim_to_budget(caption, token_budget=3, anchor_word=None, caption_mode="booru_tags")
        assert "tag1" in result
        assert "tag8" not in result

    def test_nl_mode_straightforward(self) -> None:
        from klippbok.caption.pipeline import _trim_to_budget

        long_caption = "A girl walks. She is tall. Her coat is red. The street is busy."
        result = _trim_to_budget(long_caption, token_budget=6, anchor_word=None, caption_mode="straightforward")
        assert result.endswith(".")


# ---------------------------------------------------------------------------
# apply_vlm_pipeline
# ---------------------------------------------------------------------------


class TestVlmPipeline:
    """apply_vlm_pipeline: trigger injection, artifact strip, token trim."""

    def test_prepends_anchor_word(self) -> None:
        from klippbok.caption.pipeline import apply_vlm_pipeline

        result = apply_vlm_pipeline(
            "a girl stands in the park",
            anchor_word="Luna",
            token_budget=200,
            caption_mode="descriptive",
        )
        assert result.lower().startswith("luna")

    def test_strips_vlm_artifacts(self) -> None:
        from klippbok.caption.pipeline import apply_vlm_pipeline

        result = apply_vlm_pipeline(
            "Here is a caption: a girl stands in the park",
            anchor_word=None,
            token_budget=200,
            caption_mode="descriptive",
        )
        assert "Here is a caption:" not in result

    def test_no_anchor_no_prepend(self) -> None:
        from klippbok.caption.pipeline import apply_vlm_pipeline

        result = apply_vlm_pipeline(
            "A girl stands in the park.",
            anchor_word=None,
            token_budget=200,
            caption_mode="descriptive",
        )
        # Should still work, just no anchor prepended
        assert "girl" in result.lower() or "park" in result.lower()

    def test_trims_to_budget(self) -> None:
        from klippbok.caption.pipeline import apply_vlm_pipeline

        # Generate a very long NL caption
        long_caption = (
            "Luna stands in the park. "
            "She is looking at the sky. "
            "The clouds are white. "
            "Trees surround her. "
            "Birds fly overhead. "
            "The grass is green. "
        )
        result = apply_vlm_pipeline(
            long_caption,
            anchor_word="Luna",
            token_budget=10,
            caption_mode="descriptive",
        )
        # Should be significantly shorter
        from klippbok.caption.pipeline import _count_tokens_approx
        assert _count_tokens_approx(result) <= 15  # some tolerance

    def test_anchor_never_trimmed(self) -> None:
        from klippbok.caption.pipeline import apply_vlm_pipeline

        long_caption = "tag1, tag2, tag3, tag4, tag5, tag6, tag7, tag8, tag9, tag10"
        result = apply_vlm_pipeline(
            long_caption,
            anchor_word="trigger",
            token_budget=3,
            caption_mode="booru_tags",
        )
        assert "trigger" in result.lower()


# ---------------------------------------------------------------------------
# apply_joycaption_pipeline
# ---------------------------------------------------------------------------


class TestJoyCaptionPipeline:
    """apply_joycaption_pipeline: prefix strip, blacklist, dedup, context filter, trim."""

    def test_strips_joycaption_prefix(self) -> None:
        from klippbok.caption.pipeline import apply_joycaption_pipeline

        result = apply_joycaption_pipeline(
            "here are the booru-like tags: 1girl, smiling, park",
            anchor_word=None,
            token_budget=200,
            caption_mode="booru_tags",
            appearance_blacklist=[],
        )
        assert "here are the booru-like tags:" not in result.lower()
        assert "1girl" in result

    def test_deduplicates_tags(self) -> None:
        from klippbok.caption.pipeline import apply_joycaption_pipeline

        result = apply_joycaption_pipeline(
            "smiling, 1girl, smiling, park, park",
            anchor_word=None,
            token_budget=200,
            caption_mode="booru_tags",
            appearance_blacklist=[],
        )
        # smiling should appear only once
        tags = [t.strip() for t in result.split(",") if t.strip()]
        assert tags.count("smiling") == 1

    def test_context_only_filters_appearance(self) -> None:
        from klippbok.caption.pipeline import (
            DEFAULT_APPEARANCE_BLACKLIST,
            apply_joycaption_pipeline,
        )

        result = apply_joycaption_pipeline(
            "luna, blonde hair, smiling, park",
            anchor_word="luna",
            token_budget=200,
            caption_mode="context_only_tags",
            appearance_blacklist=DEFAULT_APPEARANCE_BLACKLIST,
        )
        assert "blonde hair" not in result
        assert "smiling" in result

    def test_booru_tags_does_not_filter_appearance(self) -> None:
        """booru_tags mode does NOT apply appearance filter."""
        from klippbok.caption.pipeline import (
            DEFAULT_APPEARANCE_BLACKLIST,
            apply_joycaption_pipeline,
        )

        result = apply_joycaption_pipeline(
            "1girl, blonde hair, smiling, park",
            anchor_word=None,
            token_budget=200,
            caption_mode="booru_tags",
            appearance_blacklist=DEFAULT_APPEARANCE_BLACKLIST,
        )
        # blonde hair should NOT be filtered in booru_tags mode
        assert "blonde hair" in result

    def test_prepends_anchor_word(self) -> None:
        from klippbok.caption.pipeline import (
            DEFAULT_APPEARANCE_BLACKLIST,
            apply_joycaption_pipeline,
        )

        result = apply_joycaption_pipeline(
            "smiling, park, standing",
            anchor_word="luna",
            token_budget=200,
            caption_mode="context_only_tags",
            appearance_blacklist=DEFAULT_APPEARANCE_BLACKLIST,
        )
        assert result.lower().startswith("luna")

    def test_anchor_never_trimmed(self) -> None:
        from klippbok.caption.pipeline import apply_joycaption_pipeline

        long_caption = "tag1, tag2, tag3, tag4, tag5, tag6, tag7, tag8, tag9, tag10"
        result = apply_joycaption_pipeline(
            long_caption,
            anchor_word="trigger",
            token_budget=2,
            caption_mode="booru_tags",
            appearance_blacklist=[],
        )
        assert "trigger" in result.lower()

    def test_empty_caption(self) -> None:
        from klippbok.caption.pipeline import apply_joycaption_pipeline

        result = apply_joycaption_pipeline(
            "",
            anchor_word=None,
            token_budget=200,
            caption_mode="booru_tags",
            appearance_blacklist=[],
        )
        # Should not crash; may return empty string or anchor
        assert isinstance(result, str)

    def test_anchor_already_present(self) -> None:
        """If anchor already in caption, don't prepend again."""
        from klippbok.caption.pipeline import apply_joycaption_pipeline

        result = apply_joycaption_pipeline(
            "luna, smiling, park",
            anchor_word="luna",
            token_budget=200,
            caption_mode="booru_tags",
            appearance_blacklist=[],
        )
        tags = [t.strip().lower() for t in result.split(",")]
        assert tags.count("luna") == 1
