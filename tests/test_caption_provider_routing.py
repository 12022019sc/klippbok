"""Unit tests for build_vlm_config_from_global in klippbok.services.caption_service.

Tests cover:
- lm_studio preset -> CaptionConfig with provider="openai", api_key="lm-studio"
- nanogpt preset -> CaptionConfig with provider="openai", base_url=nano-gpt.com
- gemini preset -> api_key from config.json (priority over env var)
- gemini preset -> falls back to GEMINI_API_KEY env var when config has no key
- anchor_word passed from manifest.get("anchor_word")
- custom_prompt passed from caption config section
- joycaption preset raises ValueError
- unknown provider raises ValueError
"""

from __future__ import annotations

import os

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_global_config(**overrides: object) -> dict:
    """Minimal global config dict with optional overrides."""
    base = {
        "provider": "lm_studio",
        "lm_studio_base_url": "http://localhost:1234/v1",
        "lm_studio_model": "llava-1.5-13b",
        "nanogpt_api_key": "ngpt-test-key",
        "nanogpt_model": "nanoGPT-vision",
        "gemini_api_key": "cfg-gemini-key",
        "gemini_model": "gemini-2.5-flash",
        "joycaption_path": "",
        "custom_prompt": None,
    }
    base.update(overrides)
    return base


def _make_manifest(**overrides: object) -> dict:
    """Minimal manifest dict."""
    base: dict = {"images": [], "anchor_word": None}
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# lm_studio
# ---------------------------------------------------------------------------


def test_lm_studio_returns_openai_provider() -> None:
    """lm_studio preset returns CaptionConfig with provider='openai'."""
    from klippbok.services.caption_service import build_vlm_config_from_global

    config = _make_global_config()
    manifest = _make_manifest()
    result = build_vlm_config_from_global("lm_studio", config, manifest)

    assert result.provider == "openai"


def test_lm_studio_uses_config_base_url() -> None:
    """lm_studio preset uses lm_studio_base_url from config."""
    from klippbok.services.caption_service import build_vlm_config_from_global

    config = _make_global_config(lm_studio_base_url="http://localhost:9999/v1")
    manifest = _make_manifest()
    result = build_vlm_config_from_global("lm_studio", config, manifest)

    assert result.openai_base_url == "http://localhost:9999/v1"


def test_lm_studio_api_key_is_lm_studio() -> None:
    """lm_studio preset always uses api_key='lm-studio' (LM Studio doesn't need a real key)."""
    from klippbok.services.caption_service import build_vlm_config_from_global

    config = _make_global_config()
    manifest = _make_manifest()
    result = build_vlm_config_from_global("lm_studio", config, manifest)

    assert result.api_key == "lm-studio"


def test_lm_studio_uses_config_model() -> None:
    """lm_studio preset uses lm_studio_model from config."""
    from klippbok.services.caption_service import build_vlm_config_from_global

    config = _make_global_config(lm_studio_model="mistral-7b-vision")
    manifest = _make_manifest()
    result = build_vlm_config_from_global("lm_studio", config, manifest)

    assert result.openai_model == "mistral-7b-vision"


# ---------------------------------------------------------------------------
# nanogpt
# ---------------------------------------------------------------------------


def test_nanogpt_returns_openai_provider() -> None:
    """nanogpt preset returns CaptionConfig with provider='openai'."""
    from klippbok.services.caption_service import build_vlm_config_from_global

    config = _make_global_config()
    manifest = _make_manifest()
    result = build_vlm_config_from_global("nanogpt", config, manifest)

    assert result.provider == "openai"


def test_nanogpt_uses_nanogpt_base_url() -> None:
    """nanogpt preset uses https://nano-gpt.com/api/v1 as base URL."""
    from klippbok.services.caption_service import build_vlm_config_from_global

    config = _make_global_config()
    manifest = _make_manifest()
    result = build_vlm_config_from_global("nanogpt", config, manifest)

    assert result.openai_base_url == "https://nano-gpt.com/api/v1"


def test_nanogpt_uses_api_key_from_config() -> None:
    """nanogpt preset uses nanogpt_api_key from config."""
    from klippbok.services.caption_service import build_vlm_config_from_global

    config = _make_global_config(nanogpt_api_key="my-ngpt-key")
    manifest = _make_manifest()
    result = build_vlm_config_from_global("nanogpt", config, manifest)

    assert result.api_key == "my-ngpt-key"


def test_nanogpt_uses_model_from_config() -> None:
    """nanogpt preset uses nanogpt_model from config."""
    from klippbok.services.caption_service import build_vlm_config_from_global

    config = _make_global_config(nanogpt_model="gpt-4o-vision")
    manifest = _make_manifest()
    result = build_vlm_config_from_global("nanogpt", config, manifest)

    assert result.openai_model == "gpt-4o-vision"


# ---------------------------------------------------------------------------
# gemini
# ---------------------------------------------------------------------------


def test_gemini_returns_gemini_provider() -> None:
    """gemini preset returns CaptionConfig with provider='gemini'."""
    from klippbok.services.caption_service import build_vlm_config_from_global

    config = _make_global_config()
    manifest = _make_manifest()
    result = build_vlm_config_from_global("gemini", config, manifest)

    assert result.provider == "gemini"


def test_gemini_config_key_takes_priority_over_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """gemini preset uses config.json api_key, NOT env var, when both exist."""
    monkeypatch.setenv("GEMINI_API_KEY", "env-gemini-key")

    from klippbok.services.caption_service import build_vlm_config_from_global

    config = _make_global_config(gemini_api_key="cfg-gemini-key")
    manifest = _make_manifest()
    result = build_vlm_config_from_global("gemini", config, manifest)

    assert result.api_key == "cfg-gemini-key"


def test_gemini_falls_back_to_env_var_when_config_has_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """gemini preset falls back to GEMINI_API_KEY env var when config.json has no key."""
    monkeypatch.setenv("GEMINI_API_KEY", "env-only-key")

    from klippbok.services.caption_service import build_vlm_config_from_global

    config = _make_global_config(gemini_api_key="")  # Empty string = no key in config
    manifest = _make_manifest()
    result = build_vlm_config_from_global("gemini", config, manifest)

    assert result.api_key == "env-only-key"


def test_gemini_uses_gemini_model_from_config() -> None:
    """gemini preset uses gemini_model from config."""
    from klippbok.services.caption_service import build_vlm_config_from_global

    config = _make_global_config(gemini_model="gemini-2.0-flash")
    manifest = _make_manifest()
    result = build_vlm_config_from_global("gemini", config, manifest)

    assert result.gemini_model == "gemini-2.0-flash"


# ---------------------------------------------------------------------------
# Common fields (anchor_word, custom_prompt)
# ---------------------------------------------------------------------------


def test_anchor_word_passed_from_manifest() -> None:
    """build_vlm_config_from_global passes anchor_word from manifest.get('anchor_word')."""
    from klippbok.services.caption_service import build_vlm_config_from_global

    config = _make_global_config()
    manifest = _make_manifest(anchor_word="ohwx")
    result = build_vlm_config_from_global("lm_studio", config, manifest)

    assert result.anchor_word == "ohwx"


def test_custom_prompt_passed_from_config() -> None:
    """build_vlm_config_from_global passes custom_prompt from config caption section."""
    from klippbok.services.caption_service import build_vlm_config_from_global

    config = _make_global_config(custom_prompt="Describe this image in detail.")
    manifest = _make_manifest()
    result = build_vlm_config_from_global("gemini", config, manifest)

    assert result.custom_prompt == "Describe this image in detail."


def test_anchor_word_none_when_not_in_manifest() -> None:
    """anchor_word is None when manifest has no 'anchor_word' key."""
    from klippbok.services.caption_service import build_vlm_config_from_global

    config = _make_global_config()
    manifest: dict = {"images": []}  # No anchor_word key
    result = build_vlm_config_from_global("lm_studio", config, manifest)

    assert result.anchor_word is None


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_joycaption_raises_value_error() -> None:
    """joycaption preset raises ValueError (JoyCaption uses subprocess, not CaptionConfig)."""
    from klippbok.services.caption_service import build_vlm_config_from_global

    config = _make_global_config()
    manifest = _make_manifest()

    with pytest.raises(ValueError, match="joycaption"):
        build_vlm_config_from_global("joycaption", config, manifest)


def test_unknown_provider_raises_value_error() -> None:
    """Unknown provider preset raises ValueError."""
    from klippbok.services.caption_service import build_vlm_config_from_global

    config = _make_global_config()
    manifest = _make_manifest()

    with pytest.raises(ValueError, match="unknown_provider"):
        build_vlm_config_from_global("unknown_provider", config, manifest)
