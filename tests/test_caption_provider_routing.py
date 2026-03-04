"""Unit tests for build_vlm_config_from_global and JoyCaption routing.

Tests cover:
- lm_studio preset -> CaptionConfig with provider="openai", api_key="lm-studio"
- nanogpt preset -> CaptionConfig with provider="openai", base_url=nano-gpt.com
- gemini preset -> api_key from config.json (priority over env var)
- gemini preset -> falls back to GEMINI_API_KEY env var when config has no key
- anchor_word passed from manifest.get("anchor_word")
- custom_prompt passed from caption config section
- joycaption preset raises ValueError (for build_vlm_config_from_global)
- unknown provider raises ValueError
- JoyCaption detect + subprocess helpers
"""

from __future__ import annotations

import os
from pathlib import Path

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


# ---------------------------------------------------------------------------
# JoyCaption detection and subprocess helpers
# ---------------------------------------------------------------------------


def test_detect_joycaption_returns_none_when_not_installed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """detect_joycaption returns None when no installation exists."""
    import klippbok.caption.joycaption as jc_mod

    # Patch paths to a dir that doesn't have a venv
    monkeypatch.setattr(jc_mod, "_JOYCAPTION_COMMON_PATHS", [tmp_path / "nonexistent"])
    from klippbok.caption.joycaption import detect_joycaption
    assert detect_joycaption() is None


def test_detect_joycaption_returns_path_when_installed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """detect_joycaption returns the root path when a venv/Scripts/python.exe exists."""
    import klippbok.caption.joycaption as jc_mod

    # Create a fake JoyCaption installation
    venv_dir = tmp_path / "venv" / "Scripts"
    venv_dir.mkdir(parents=True)
    (venv_dir / "python.exe").write_text("fake")

    monkeypatch.setattr(jc_mod, "_JOYCAPTION_COMMON_PATHS", [tmp_path])
    from klippbok.caption.joycaption import detect_joycaption
    assert detect_joycaption() == tmp_path


def test_get_venv_python_windows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """get_venv_python returns the Windows python path when it exists."""
    import klippbok.caption.joycaption as jc_mod

    monkeypatch.setattr(jc_mod.platform, "system", lambda: "Windows")

    venv_dir = tmp_path / "venv" / "Scripts"
    venv_dir.mkdir(parents=True)
    (venv_dir / "python.exe").write_text("fake")

    from klippbok.caption.joycaption import get_venv_python
    result = get_venv_python(tmp_path)
    assert result == venv_dir / "python.exe"


def test_get_venv_python_raises_when_not_found(tmp_path: Path) -> None:
    """get_venv_python raises FileNotFoundError when venv python is missing."""
    from klippbok.caption.joycaption import get_venv_python

    with pytest.raises(FileNotFoundError, match="venv Python not found"):
        get_venv_python(tmp_path)


def test_custom_prompt_used_in_caption_image_for_project(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """caption_image_for_project uses custom_prompt when set on vlm_config."""
    from klippbok.caption.models import CaptionConfig
    from klippbok.services.caption_service import caption_image_for_project

    # Create a test image
    img_path = tmp_path / "test.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    captured_prompt = []

    class FakeBackend:
        def caption_image(self, path: Path, prompt: str) -> str:
            captured_prompt.append(prompt)
            return "test caption"

    monkeypatch.setattr(
        "klippbok.services.caption_service._create_backend",
        lambda _cfg: FakeBackend(),
        raising=False,
    )
    # Patch at the correct import location
    import klippbok.caption.captioner as captioner_mod
    monkeypatch.setattr(captioner_mod, "_create_backend", lambda _cfg: FakeBackend())
    monkeypatch.setattr(
        "klippbok.services.caption_service._create_backend",
        lambda _cfg: FakeBackend(),
        raising=False,
    )

    config = CaptionConfig(
        provider="openai",
        custom_prompt="My custom prompt here",
    )
    manifest = {"images": [], "caption_style_override": "natural_language"}

    # Need to patch the import inside the function
    import klippbok.services.caption_service as svc_mod
    original_create = None
    try:
        from klippbok.caption import captioner
        original_create = captioner._create_backend
        captioner._create_backend = lambda _cfg: FakeBackend()

        result = caption_image_for_project(img_path, manifest, config)
        assert result == "test caption"
        assert captured_prompt[0] == "My custom prompt here"
    finally:
        if original_create:
            captioner._create_backend = original_create
