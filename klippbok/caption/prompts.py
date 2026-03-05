"""Prompt templates for VLM captioning.

Five caption modes covering the main LoRA training use cases:

1. booru_tags       — comma-separated tags (SD1.5 LoRA)
2. context_only_tags  — tags WITHOUT physical appearance (Character LoRA)
3. context_only_natural — NL WITHOUT physical appearance (Character LoRA)
4. descriptive      — detailed natural language (SDXL/Flux)
5. straightforward  — factual NL, no speculation (SDXL/Flux)

Context-only modes instruct the VLM to omit physical appearance.
The LoRA learns appearance from images — captions should capture context.

Good: "close-up, Luna looks up at the open sky"
Bad:  "It's a close-up of Luna, shot from below, as she looks intently up."

Framing (close-up, wide shot, etc.) leads as a tag when notable.
The anchor word is used as a natural name, not mechanically prepended.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Image captioning prompts — 5 modes
# ---------------------------------------------------------------------------

IMAGE_PROMPT_BOORU_TAGS = """\
Write a list of Booru-like tags for this image, comma-separated.{anchor_line}{secondary_line}
Include subject, action, setting, composition, and mood tags.
Do NOT include quality tags (masterpiece, best quality, absurdres).
Output ONLY the tags, no explanations, no numbering."""

IMAGE_PROMPT_CONTEXT_ONLY_TAGS = """\
Write Booru-like tags for this image, comma-separated.{anchor_line}{secondary_line}
Do NOT include tags describing physical appearance (hair color, eye color, clothing, body type, skin tone).
Focus ONLY on setting, action, pose, expression, and context.
Output ONLY the tags, no explanations, no numbering."""

IMAGE_PROMPT_CONTEXT_ONLY_NATURAL = """\
Write a short natural language caption for this image.{anchor_line}{secondary_line}
Do NOT describe any physical appearance (hair color, eye color, clothing, body type, skin tone).
Focus ONLY on the action, setting, mood, and context.
Output ONLY the caption — no options, no numbering, no markdown formatting."""

IMAGE_PROMPT_DESCRIPTIVE = """\
Write a detailed natural language caption for this image.{anchor_line}{secondary_line}
Describe the subject, their action, the setting, lighting, mood, and relevant details.
Be thorough but natural — write as a generation prompt, not a film review.
Output ONLY the caption — no options, no numbering, no markdown formatting."""

IMAGE_PROMPT_STRAIGHTFORWARD = """\
Write a short factual caption for this image.{anchor_line}{secondary_line}
State only what you can directly observe. Do not speculate, interpret emotions, or infer context.
Be concise and precise — describe what is visible, not what might be implied.
Output ONLY the caption — no options, no numbering, no markdown formatting."""


# ---------------------------------------------------------------------------
# Video captioning prompts — 5 modes
# ---------------------------------------------------------------------------

VIDEO_PROMPT_BOORU_TAGS = """\
Write a list of Booru-like tags for this video clip, comma-separated.{anchor_line}{secondary_line}
Include subject, action, setting, composition, and motion tags.
Do NOT include quality tags (masterpiece, best quality, absurdres).
Output ONLY the tags, no explanations, no numbering."""

VIDEO_PROMPT_CONTEXT_ONLY_TAGS = """\
Write Booru-like tags for this video clip, comma-separated.{anchor_line}{secondary_line}
Do NOT include tags describing physical appearance (hair color, eye color, clothing, body type, skin tone).
Focus ONLY on setting, action, pose, expression, motion, and context.
Output ONLY the tags, no explanations, no numbering."""

VIDEO_PROMPT_CONTEXT_ONLY_NATURAL = """\
Write a short natural language caption for this video clip.{anchor_line}{secondary_line}
Do NOT describe any physical appearance (hair color, eye color, clothing, body type, skin tone).
Focus ONLY on the action, movement, setting, mood, and context.
Output ONLY the caption — no options, no numbering, no markdown formatting."""

VIDEO_PROMPT_DESCRIPTIVE = """\
Write a detailed natural language caption for this video clip.{anchor_line}{secondary_line}
Describe the subject, their action and movement, the setting, lighting, mood, and relevant details.
Note framing (close-up, wide shot) if notable. Be thorough but natural.
Output ONLY the caption — no options, no numbering, no markdown formatting."""

VIDEO_PROMPT_STRAIGHTFORWARD = """\
Write a short factual caption for this video clip.{anchor_line}{secondary_line}
State only what you can directly observe: who is present, what they are doing, and where.
Do not speculate, interpret emotions, or infer context beyond what is visible.
Output ONLY the caption — no options, no numbering, no markdown formatting."""


# ---------------------------------------------------------------------------
# Lookup dicts
# ---------------------------------------------------------------------------

IMAGE_PROMPTS: dict[str, str] = {
    "booru_tags": IMAGE_PROMPT_BOORU_TAGS,
    "context_only_tags": IMAGE_PROMPT_CONTEXT_ONLY_TAGS,
    "context_only_natural": IMAGE_PROMPT_CONTEXT_ONLY_NATURAL,
    "descriptive": IMAGE_PROMPT_DESCRIPTIVE,
    "straightforward": IMAGE_PROMPT_STRAIGHTFORWARD,
}

VIDEO_PROMPTS: dict[str, str] = {
    "booru_tags": VIDEO_PROMPT_BOORU_TAGS,
    "context_only_tags": VIDEO_PROMPT_CONTEXT_ONLY_TAGS,
    "context_only_natural": VIDEO_PROMPT_CONTEXT_ONLY_NATURAL,
    "descriptive": VIDEO_PROMPT_DESCRIPTIVE,
    "straightforward": VIDEO_PROMPT_STRAIGHTFORWARD,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_video_prompt(
    caption_mode: str | None = None,
    anchor_word: str | None = None,
    secondary_anchors: list[str] | None = None,
) -> str:
    """Get the appropriate video captioning prompt for a caption mode.

    When an anchor word is provided, it's woven into the prompt so the
    VLM uses it as the character/object's name naturally. Secondary
    anchors are additional tags the VLM should try to mention.

    Args:
        caption_mode: One of 'booru_tags', 'context_only_tags', 'context_only_natural',
            'descriptive', 'straightforward'. Unknown modes fall back to 'context_only_tags'.
        anchor_word: Primary trigger word — used as the subject's name.
        secondary_anchors: Additional tags to mention (e.g. ["vintage", "retro"]).

    Returns:
        The prompt string, ready to send to the VLM.
    """
    template = VIDEO_PROMPTS.get(caption_mode, VIDEO_PROMPT_CONTEXT_ONLY_TAGS)
    return _fill_prompt(template, anchor_word, secondary_anchors)


def get_image_prompt(
    caption_mode: str | None = None,
    anchor_word: str | None = None,
    secondary_anchors: list[str] | None = None,
) -> str:
    """Get the appropriate image captioning prompt for a caption mode.

    Args:
        caption_mode: One of 'booru_tags', 'context_only_tags', 'context_only_natural',
            'descriptive', 'straightforward'. Unknown modes fall back to 'context_only_tags'.
        anchor_word: Primary trigger word — used as the subject's name.
        secondary_anchors: Additional tags to mention.

    Returns:
        The prompt string, ready to send to the VLM.
    """
    template = IMAGE_PROMPTS.get(caption_mode, IMAGE_PROMPT_CONTEXT_ONLY_TAGS)
    return _fill_prompt(template, anchor_word, secondary_anchors)


def _fill_prompt(
    template: str,
    anchor_word: str | None = None,
    secondary_anchors: list[str] | None = None,
) -> str:
    """Fill a prompt template with anchor word and secondary anchors.

    Handles the {anchor_line} and {secondary_line} placeholders.
    When no anchor is set, these are cleaned out so the prompt reads naturally.

    The anchor word is presented as the subject's name — the VLM should
    weave it into the caption naturally, not prepend/append it mechanically.

    Secondary anchors are things that may or may not be visible in the clip.
    The VLM should only mention them if it actually sees them.
    """
    if anchor_word:
        anchor_line = (
            f"\nThe subject's name is \"{anchor_word}\". "
            f"Use \"{anchor_word}\" naturally in the caption as their name."
        )
    else:
        anchor_line = ""

    if secondary_anchors:
        tags = ", ".join(f'"{t}"' for t in secondary_anchors)
        secondary_line = (
            f"\nThese words may be relevant: {tags}. "
            f"Only use them if you can actually see what they describe — "
            f"do not force them in."
        )
    else:
        secondary_line = ""

    result = template
    result = result.replace("{anchor_line}", anchor_line)
    result = result.replace("{secondary_line}", secondary_line)
    return result


def format_prompt(prompt: str, **variables: str) -> str:
    """Safely substitute template variables in a prompt string.

    Variables use {curly_brace} syntax. Only variables that appear in the
    prompt are substituted — extra variables are silently ignored, and
    missing variables are left as-is (no KeyError).

    This is intentionally NOT str.format() because we want missing
    variables to pass through unchanged rather than raising errors.

    Args:
        prompt: The prompt template with {variable} placeholders.
        **variables: Variable name → value mappings.

    Returns:
        The prompt with known variables substituted.

    Examples:
        >>> format_prompt("Describe {anchor_word} in detail", anchor_word="Luna")
        "Describe Luna in detail"
        >>> format_prompt("No variables here")
        "No variables here"
        >>> format_prompt("{missing} stays", other="ignored")
        "{missing} stays"
    """
    result = prompt
    for key, value in variables.items():
        result = result.replace(f"{{{key}}}", value)
    return result
