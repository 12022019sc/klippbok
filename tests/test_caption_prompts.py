"""Tests for klippbok.caption.prompts — pure Python, no API calls.

Tests prompt template selection, anchor word injection, and secondary anchors.
Uses caption_mode-based API (replaces old use_case-based API).
"""

import pytest

from klippbok.caption.prompts import (
    IMAGE_PROMPTS,
    VIDEO_PROMPTS,
    _fill_prompt,
    format_prompt,
    get_image_prompt,
    get_video_prompt,
)


class TestGetVideoPrompt:
    """Tests for video prompt selection by caption_mode."""

    def test_booru_tags(self) -> None:
        prompt = get_video_prompt("booru_tags")
        assert "tags" in prompt.lower()
        assert "comma" in prompt.lower() or "comma-separated" in prompt.lower()

    def test_context_only_tags(self) -> None:
        prompt = get_video_prompt("context_only_tags")
        assert "do not" in prompt.lower() or "not include" in prompt.lower()
        assert "appearance" in prompt.lower() or "physical" in prompt.lower()

    def test_context_only_natural(self) -> None:
        prompt = get_video_prompt("context_only_natural")
        assert "do not" in prompt.lower() or "not describe" in prompt.lower()
        assert "appearance" in prompt.lower() or "physical" in prompt.lower()
        assert "caption" in prompt.lower()

    def test_descriptive(self) -> None:
        prompt = get_video_prompt("descriptive")
        assert "detailed" in prompt.lower() or "describe" in prompt.lower()
        assert "caption" in prompt.lower()

    def test_straightforward(self) -> None:
        prompt = get_video_prompt("straightforward")
        assert "factual" in prompt.lower() or "observe" in prompt.lower()
        assert "caption" in prompt.lower()

    def test_unknown_mode_falls_back(self) -> None:
        """Unknown caption_mode falls back to context_only_tags (not raising)."""
        prompt = get_video_prompt("invalid_mode")
        assert "caption" in prompt.lower() or "video" in prompt.lower()

    def test_none_mode_falls_back(self) -> None:
        """None caption_mode falls back to context_only_tags."""
        prompt = get_video_prompt(None)
        # Should return some valid prompt
        assert len(prompt) > 20

    def test_all_5_modes_have_templates(self) -> None:
        """All 5 modes have distinct templates."""
        modes = ["booru_tags", "context_only_tags", "context_only_natural", "descriptive", "straightforward"]
        prompts = [get_video_prompt(m) for m in modes]
        # All prompts are different
        assert len(set(prompts)) == 5


class TestGetImagePrompt:
    """Tests for image prompt selection by caption_mode."""

    def test_booru_tags(self) -> None:
        prompt = get_image_prompt("booru_tags")
        assert "tags" in prompt.lower()
        assert "image" in prompt.lower()

    def test_context_only_tags(self) -> None:
        prompt = get_image_prompt("context_only_tags")
        assert "do not" in prompt.lower() or "not include" in prompt.lower()
        assert "appearance" in prompt.lower() or "physical" in prompt.lower()

    def test_context_only_natural(self) -> None:
        prompt = get_image_prompt("context_only_natural")
        assert "do not" in prompt.lower() or "not describe" in prompt.lower()
        assert "caption" in prompt.lower()

    def test_descriptive(self) -> None:
        prompt = get_image_prompt("descriptive")
        assert "detailed" in prompt.lower() or "describe" in prompt.lower()

    def test_straightforward(self) -> None:
        prompt = get_image_prompt("straightforward")
        assert "factual" in prompt.lower() or "observe" in prompt.lower()

    def test_unknown_mode_falls_back(self) -> None:
        """Unknown caption_mode falls back gracefully."""
        prompt = get_image_prompt("unknown_mode")
        assert "image" in prompt.lower()

    def test_none_mode_falls_back(self) -> None:
        prompt = get_image_prompt(None)
        assert len(prompt) > 20

    def test_all_5_modes_have_templates(self) -> None:
        modes = ["booru_tags", "context_only_tags", "context_only_natural", "descriptive", "straightforward"]
        prompts = [get_image_prompt(m) for m in modes]
        assert len(set(prompts)) == 5


class TestAnchorWordInjection:
    """Tests that anchor words are woven into prompts naturally."""

    def test_anchor_injected_into_context_only_tags(self) -> None:
        prompt = get_video_prompt("context_only_tags", anchor_word="luna")
        assert "luna" in prompt.lower()
        assert "naturally" in prompt.lower()

    def test_anchor_injected_into_descriptive(self) -> None:
        prompt = get_image_prompt("descriptive", anchor_word="luna")
        assert "luna" in prompt.lower()
        assert "naturally" in prompt.lower()

    def test_no_anchor_no_placeholder_leak(self) -> None:
        """Without anchor, no unfilled placeholders remain."""
        for mode in ["booru_tags", "context_only_tags", "context_only_natural", "descriptive", "straightforward"]:
            prompt = get_video_prompt(mode)
            assert "{" not in prompt, f"{mode} without anchor has unfilled placeholder"
            prompt = get_image_prompt(mode)
            assert "{" not in prompt, f"image {mode} without anchor has unfilled placeholder"

    def test_with_anchor_no_placeholder_leak(self) -> None:
        """With anchor, no unfilled placeholders remain."""
        for mode in ["booru_tags", "context_only_tags", "context_only_natural", "descriptive", "straightforward"]:
            prompt = get_video_prompt(mode, anchor_word="testanchor")
            assert "{" not in prompt, f"{mode} with anchor has unfilled placeholder"

    def test_no_anchor_no_anchor_instruction(self) -> None:
        """Without anchor, the anchor instruction line is absent."""
        prompt = get_video_prompt("context_only_tags")
        assert "name is" not in prompt.lower()

    def test_all_modes_accept_anchor(self) -> None:
        for mode in ["booru_tags", "context_only_tags", "context_only_natural", "descriptive", "straightforward"]:
            prompt = get_video_prompt(mode, anchor_word="testanchor")
            assert "testanchor" in prompt.lower(), f"{mode} missing anchor"


class TestSecondaryAnchors:
    """Tests for secondary anchor tags in prompts."""

    def test_secondary_anchors_included(self) -> None:
        prompt = get_video_prompt(
            "context_only_tags", anchor_word="luna",
            secondary_anchors=["vintage", "retro"],
        )
        assert "vintage" in prompt.lower()
        assert "retro" in prompt.lower()

    def test_secondary_anchors_conditional_instruction(self) -> None:
        prompt = get_video_prompt(
            "context_only_tags", anchor_word="luna",
            secondary_anchors=["vintage"],
        )
        assert "only" in prompt.lower()

    def test_no_secondary_anchors_no_extra_instruction(self) -> None:
        prompt = get_video_prompt("context_only_tags", anchor_word="luna")
        assert "may be relevant" not in prompt.lower()

    def test_secondary_without_primary(self) -> None:
        prompt = get_video_prompt(
            "context_only_tags",
            secondary_anchors=["vintage", "retro"],
        )
        assert "vintage" in prompt.lower()
        assert "retro" in prompt.lower()

    def test_secondary_on_all_modes(self) -> None:
        for mode in ["booru_tags", "context_only_tags", "context_only_natural", "descriptive", "straightforward"]:
            prompt = get_video_prompt(mode, secondary_anchors=["tag1"])
            assert "tag1" in prompt.lower(), f"{mode} missing secondary anchor"


class TestPromptContent:
    """Tests that prompts contain the right instructions for each mode."""

    def test_context_only_omits_appearance(self) -> None:
        for mode in ["context_only_tags", "context_only_natural"]:
            prompt = get_video_prompt(mode)
            assert "do not" in prompt.lower() or "not include" in prompt.lower()

    def test_booru_tags_requests_tags_not_prose(self) -> None:
        prompt = get_video_prompt("booru_tags")
        assert "comma" in prompt.lower() or "tags" in prompt.lower()

    def test_descriptive_requests_detail(self) -> None:
        prompt = get_image_prompt("descriptive")
        assert "detailed" in prompt.lower() or "describe" in prompt.lower()

    def test_straightforward_requests_factual(self) -> None:
        prompt = get_image_prompt("straightforward")
        assert "factual" in prompt.lower() or "observe" in prompt.lower()

    def test_image_prompts_mention_image(self) -> None:
        for mode in ["booru_tags", "context_only_tags", "context_only_natural", "descriptive", "straightforward"]:
            prompt = get_image_prompt(mode)
            assert "image" in prompt.lower(), f"Image prompt for {mode} doesn't mention 'image'"

    def test_video_prompts_mention_video(self) -> None:
        for mode in ["booru_tags", "context_only_tags", "context_only_natural", "descriptive", "straightforward"]:
            prompt = get_video_prompt(mode)
            assert "video" in prompt.lower() or "clip" in prompt.lower(), \
                f"Video prompt for {mode} doesn't mention 'video' or 'clip'"


class TestPromptDicts:
    """Tests for IMAGE_PROMPTS and VIDEO_PROMPTS dicts."""

    def test_image_prompts_has_5_entries(self) -> None:
        assert len(IMAGE_PROMPTS) == 5

    def test_video_prompts_has_5_entries(self) -> None:
        assert len(VIDEO_PROMPTS) == 5

    def test_image_prompts_keys(self) -> None:
        expected = {"booru_tags", "context_only_tags", "context_only_natural", "descriptive", "straightforward"}
        assert set(IMAGE_PROMPTS.keys()) == expected

    def test_video_prompts_keys(self) -> None:
        expected = {"booru_tags", "context_only_tags", "context_only_natural", "descriptive", "straightforward"}
        assert set(VIDEO_PROMPTS.keys()) == expected

    def test_no_none_keys(self) -> None:
        assert None not in IMAGE_PROMPTS
        assert None not in VIDEO_PROMPTS


class TestFillPrompt:
    """Tests for _fill_prompt — anchor injection helper."""

    def test_anchor_line_injected(self) -> None:
        template = "Describe the scene.{anchor_line} Be concise."
        result = _fill_prompt(template, anchor_word="luna")
        assert "luna" in result.lower()
        assert "{anchor_line}" not in result

    def test_anchor_line_empty_without_anchor(self) -> None:
        template = "Describe the scene.{anchor_line} Be concise."
        result = _fill_prompt(template)
        assert "name is" not in result.lower()
        assert "{anchor_line}" not in result

    def test_secondary_line_injected(self) -> None:
        template = "Describe.{secondary_line}"
        result = _fill_prompt(template, secondary_anchors=["vintage"])
        assert "vintage" in result
        assert "{secondary_line}" not in result

    def test_secondary_empty_without_anchors(self) -> None:
        template = "Describe.{secondary_line}"
        result = _fill_prompt(template)
        assert "{secondary_line}" not in result


class TestFormatPrompt:
    """Tests for format_prompt() — safe template variable substitution."""

    def test_basic_substitution(self) -> None:
        result = format_prompt("Describe {anchor_word} in detail", anchor_word="Luna")
        assert result == "Describe Luna in detail"

    def test_multiple_variables(self) -> None:
        result = format_prompt(
            "{name} is in {place}",
            name="Luna",
            place="the plaza",
        )
        assert result == "Luna is in the plaza"

    def test_no_variables(self) -> None:
        result = format_prompt("No variables here")
        assert result == "No variables here"

    def test_missing_variable_preserved(self) -> None:
        result = format_prompt("{missing} stays", other="ignored")
        assert result == "{missing} stays"

    def test_extra_variables_ignored(self) -> None:
        result = format_prompt("Hello world", unused="value")
        assert result == "Hello world"


class TestCustomPrompt:
    """Tests for custom_prompt field on CaptionConfig."""

    def test_custom_prompt_field(self) -> None:
        from klippbok.caption.models import CaptionConfig
        config = CaptionConfig(custom_prompt="My custom instructions here")
        assert config.custom_prompt == "My custom instructions here"

    def test_custom_prompt_default_none(self) -> None:
        from klippbok.caption.models import CaptionConfig
        config = CaptionConfig()
        assert config.custom_prompt is None

    def test_custom_prompt_overrides_in_captioner(self) -> None:
        """custom_prompt takes priority over caption_mode in caption_clips."""
        from pathlib import Path

        from klippbok.caption.base import VLMBackend
        from klippbok.caption.captioner import caption_clips
        from klippbok.caption.models import CaptionConfig

        class PromptCapture(VLMBackend):
            """Records the prompt it receives."""
            def __init__(self):
                self.received_prompts: list[str] = []
            def caption_video(self, path: Path, prompt: str) -> str:
                self.received_prompts.append(prompt)
                return "test caption"
            def caption_image(self, path: Path, prompt: str) -> str:
                return "test"

        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / "clip.mp4").write_bytes(b"\x00")

            capture = PromptCapture()

            import klippbok.caption.captioner as cap_mod
            original = cap_mod._create_backend
            cap_mod._create_backend = lambda config: capture

            try:
                config = CaptionConfig(
                    provider="gemini",
                    caption_mode="context_only_tags",
                    custom_prompt="My totally custom prompt",
                    between_request_delay=0,
                )
                caption_clips(tmp, config)
            finally:
                cap_mod._create_backend = original

            assert capture.received_prompts == ["My totally custom prompt"]


class TestSecondaryAnchorsConfig:
    """Tests for secondary_anchors on CaptionConfig."""

    def test_secondary_anchors_field(self) -> None:
        from klippbok.caption.models import CaptionConfig
        config = CaptionConfig(secondary_anchors=["vintage", "retro"])
        assert config.secondary_anchors == ["vintage", "retro"]

    def test_secondary_anchors_default_none(self) -> None:
        from klippbok.caption.models import CaptionConfig
        config = CaptionConfig()
        assert config.secondary_anchors is None
