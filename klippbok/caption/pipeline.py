"""Caption post-processing pipelines.

Pure functions for cleaning, filtering, and trimming captions after VLM
or JoyCaption generation. All functions are stateless and independently testable.

Two top-level pipelines:
- apply_vlm_pipeline: for LM Studio, NanoGPT, Gemini, Replicate providers
- apply_joycaption_pipeline: for JoyCaption subprocess output

Pipeline stages:
1. Provider-specific artifact stripping (preambles, markdown, wrapping quotes)
2. Trigger word injection (anchor_word prepended if not already present)
3. Appearance tag filtering (context_only modes only)
4. Tag deduplication
5. Token budget trimming (anchor word never trimmed)
"""

from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Default blacklists
# ---------------------------------------------------------------------------

DEFAULT_APPEARANCE_BLACKLIST: list[str] = [
    # Hair colors
    "blonde hair",
    "brown hair",
    "black hair",
    "red hair",
    "white hair",
    "silver hair",
    "pink hair",
    "blue hair",
    "purple hair",
    "green hair",
    "orange hair",
    "grey hair",
    "gray hair",
    # Hair length/style
    "long hair",
    "short hair",
    "medium hair",
    "very long hair",
    "wavy hair",
    "straight hair",
    "curly hair",
    "twintails",
    "ponytail",
    "braid",
    "braids",
    # Eyes
    "blue eyes",
    "brown eyes",
    "green eyes",
    "red eyes",
    "purple eyes",
    "golden eyes",
    "yellow eyes",
    "grey eyes",
    "gray eyes",
    "black eyes",
    "heterochromia",
    "aqua eyes",
    # Body type
    "large breasts",
    "small breasts",
    "medium breasts",
    "flat chest",
    "slim",
    "petite",
    "curvy",
    "athletic",
    # Skin
    "pale skin",
    "dark skin",
    "tan skin",
    "fair skin",
    # General physical
    "tall",
    "short stature",
    "freckles",
    "mole",
]
"""Default appearance tag blacklist — physical traits a LoRA will learn itself.

Used for context_only_tags and context_only_natural modes. User can extend this
via appearance_blacklist_extra in ~/.klippbok/config.json.
"""

_NOISE_TAG_BLACKLIST: list[str] = [
    "watermark",
    "signature",
    "text",
    "logo",
    "username",
    "artist name",
    "patreon logo",
    "twitter logo",
    "patreon username",
    "twitter username",
]
"""Tags to always remove in tag-mode output — visual noise, not semantic content."""

# ---------------------------------------------------------------------------
# VLM artifact stripping patterns
# ---------------------------------------------------------------------------

_VLM_PREFIX_PATTERNS = [
    r"^here\s+(?:is|are)\s+(?:a\s+)?(?:caption|description|tags?)[:\s]+",
    r"^here\s+are\s+(?:some\s+)?(?:booru[-\s]?like\s+)?tags?[:\s]+",
    r"^caption[:\s]+",
    r"^tags?[:\s]+",
    r"^(?:sure|certainly|of\s+course)[!,.]?\s+",
]


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _count_tokens_approx(text: str) -> int:
    """Approximate token count using word-based estimation.

    Uses the OpenAI rule of thumb: 1 token ≈ 0.75 words.
    Sufficient for SD1.5 (75-token), SDXL (150-token), Flux (225-token) budgets.

    Args:
        text: Input text string.

    Returns:
        Estimated token count (minimum 1).
    """
    words = text.split()
    if not words:
        return 1
    return max(1, round(len(words) / 0.75))


def _normalize_tag(tag: str) -> str:
    """Normalize a tag for comparison: lowercase, underscores to spaces, strip."""
    return tag.lower().replace("_", " ").strip()


def _tag_is_appearance(tag: str, blacklist: list[str]) -> bool:
    """Check if a tag matches any entry in the appearance blacklist.

    Uses bidirectional substring matching after normalization:
    - blacklist item is substring of tag (e.g. "blonde hair" in "long blonde hair")
    - tag is substring of blacklist item (e.g. "braid" in "braids")

    Args:
        tag: The tag to check.
        blacklist: List of appearance tag patterns.

    Returns:
        True if the tag should be filtered out.
    """
    norm_tag = _normalize_tag(tag)
    return any(
        _normalize_tag(bl) in norm_tag or norm_tag in _normalize_tag(bl)
        for bl in blacklist
    )


def _prepend_anchor(caption: str, anchor_word: str) -> str:
    """Prepend anchor word to caption if not already present.

    Checks if the caption already starts with the anchor word (case-insensitive).
    If not, prepends it. If the first character is uppercase, lowercases it for
    natural reading flow.

    Args:
        caption: The generated caption text.
        anchor_word: The trigger word to prepend.

    Returns:
        Caption with anchor word at the start.

    Examples:
        >>> _prepend_anchor("A girl walks", "Luna")
        "Luna, a girl walks"
        >>> _prepend_anchor("Luna is walking", "Luna")
        "Luna is walking"
    """
    if caption.lower().startswith(anchor_word.lower()):
        return caption

    # Lowercase the first character of the caption for natural flow
    if caption and caption[0].isupper():
        caption = caption[0].lower() + caption[1:]

    return f"{anchor_word}, {caption}"


def _strip_vlm_artifacts(text: str) -> str:
    """Remove common VLM response preambles and formatting.

    Strips:
    - Preamble phrases like "Here is a caption:", "Sure!", "Caption:"
    - Markdown bold/italic formatting
    - Wrapping double quotes

    Args:
        text: Raw VLM output string.

    Returns:
        Cleaned text with artifacts removed.
    """
    text = text.strip()
    # Strip markdown bold/italic
    text = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", text)
    # Strip wrapping quotes
    if text.startswith('"') and text.endswith('"') and len(text) > 2:
        text = text[1:-1]
    # Strip preamble prefixes (case-insensitive)
    for pattern in _VLM_PREFIX_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    return text.strip()


def _strip_joycaption_prefixes(text: str) -> str:
    """Remove JoyCaption-specific output prefixes.

    JoyCaption sometimes outputs a header before the actual tags, like:
    "here are the booru-like tags: tag1, tag2, ..."

    This is distinct from general VLM artifact stripping because JoyCaption
    outputs are structured (comma-separated tags), not prose.

    Args:
        text: Raw JoyCaption output string.

    Returns:
        Text with JoyCaption-specific prefixes removed.
    """
    text = text.strip()
    # JoyCaption-specific tag prefix patterns
    joycaption_patterns = [
        r"^here\s+are\s+(?:the\s+)?(?:booru[-\s]?like\s+)?tags?[:\s]+",
        r"^booru[-\s]?(?:like\s+)?tags?[:\s]+",
        r"^tags?[:\s]+",
    ]
    for pattern in joycaption_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    return text.strip()


def _apply_tag_blacklist(caption: str, blacklist: list[str]) -> str:
    """Remove tags matching the blacklist from a comma-separated tag caption.

    Args:
        caption: Comma-separated tag string.
        blacklist: List of tags to remove (exact match, case-insensitive).

    Returns:
        Filtered tag string with matching tags removed.
    """
    if not blacklist or not caption.strip():
        return caption
    blacklist_normalized = {_normalize_tag(b) for b in blacklist}
    parts = [t.strip() for t in caption.split(",") if t.strip()]
    filtered = [t for t in parts if _normalize_tag(t) not in blacklist_normalized]
    return ", ".join(filtered)


def _dedup_tags(caption: str) -> str:
    """Remove duplicate tags from a comma-separated tag string, preserving order.

    Uses a seen set with normalized comparison (lowercase, underscores → spaces).

    Args:
        caption: Comma-separated tag string.

    Returns:
        Deduplicated tag string with original capitalization preserved.
    """
    if not caption.strip():
        return caption
    parts = [t.strip() for t in caption.split(",") if t.strip()]
    seen: set[str] = set()
    unique: list[str] = []
    for tag in parts:
        norm = _normalize_tag(tag)
        if norm not in seen:
            seen.add(norm)
            unique.append(tag)
    return ", ".join(unique)


def _filter_appearance_tags(
    caption: str,
    appearance_blacklist: list[str],
) -> str:
    """Filter physical appearance tags from a comma-separated tag caption.

    Removes tags that match any entry in the appearance blacklist using
    normalized bidirectional substring matching. Designed for context_only
    modes where the LoRA learns appearance from images — captions should
    describe context, not physical traits.

    Args:
        caption: Comma-separated tag string.
        appearance_blacklist: List of appearance tag patterns to filter.

    Returns:
        Filtered tag string with appearance tags removed.
    """
    if not appearance_blacklist or not caption.strip():
        return caption
    parts = [t.strip() for t in caption.split(",") if t.strip()]
    filtered = [t for t in parts if not _tag_is_appearance(t, appearance_blacklist)]
    return ", ".join(filtered)


def _trim_to_budget(
    caption: str,
    token_budget: int,
    anchor_word: str | None,
    caption_mode: str,
) -> str:
    """Trim a caption to fit within a token budget.

    The anchor/trigger word is NEVER removed — it is always protected.

    For tag modes (booru_tags, context_only_tags):
        Drops tags from the end (lowest-priority tags last).

    For natural language modes (context_only_natural, descriptive, straightforward):
        Trims at the last complete sentence boundary within the budget.

    Args:
        caption: The caption text to trim.
        token_budget: Maximum allowed token count.
        anchor_word: Trigger word to protect from trimming (may be None).
        caption_mode: One of the 5 caption modes.

    Returns:
        Trimmed caption that fits within the token budget.
    """
    if _count_tokens_approx(caption) <= token_budget:
        return caption

    is_tag_mode = caption_mode in ("booru_tags", "context_only_tags")

    if is_tag_mode:
        # Tags: drop from end (lowest-confidence tags added last, so drop them first)
        tags = [t.strip() for t in caption.split(",") if t.strip()]
        anchor_norm = anchor_word.lower() if anchor_word else None

        # Separate protected (anchor) from trimmable tags
        protected: list[str] = []
        rest: list[str] = []
        for tag in tags:
            if anchor_norm and tag.lower() == anchor_norm:
                protected.append(tag)
            else:
                rest.append(tag)

        # Drop from end until under budget
        while rest and _count_tokens_approx(", ".join(protected + rest)) > token_budget:
            rest.pop()

        return ", ".join(protected + rest)

    else:
        # Natural language: trim at last complete sentence within budget
        sentences = re.split(r"(?<=[.!?])\s+", caption)
        result: list[str] = []
        for sentence in sentences:
            candidate = " ".join(result + [sentence])
            if _count_tokens_approx(candidate) <= token_budget:
                result.append(sentence)
            else:
                break
        if result:
            return " ".join(result)
        # Fallback: no complete sentence fits — return as much as possible
        return caption[: max(1, token_budget * 4)]


# ---------------------------------------------------------------------------
# Top-level pipelines
# ---------------------------------------------------------------------------


def apply_vlm_pipeline(
    caption: str,
    anchor_word: str | None,
    token_budget: int,
    caption_mode: str,
) -> str:
    """Post-processing pipeline for VLM provider output.

    Steps:
    1. VLM artifact stripping (preambles, markdown, wrapping quotes)
    2. Trigger word injection (anchor prepended if not already present)
    3. Token budget trimming (anchor word protected)

    Artifact stripping runs BEFORE trigger injection — preamble patterns only
    match at position 0, so stripping first ensures ^-anchored regex works
    correctly on raw VLM output.

    Args:
        caption: Raw VLM output string.
        anchor_word: Trigger word to prepend. None = no trigger.
        token_budget: Maximum token count for the output.
        caption_mode: Caption mode — controls trimming behavior.

    Returns:
        Processed caption ready for storage.
    """
    # 1. Artifact stripping (strip preambles on raw VLM output before anchor injection)
    caption = _strip_vlm_artifacts(caption)
    # 2. Trigger word injection (anchor is never a preamble pattern)
    if anchor_word:
        caption = _prepend_anchor(caption, anchor_word)
    # 3. Token budget trimming (trigger word is protected)
    caption = _trim_to_budget(caption, token_budget, anchor_word, caption_mode)
    return caption


def apply_joycaption_pipeline(
    caption: str,
    anchor_word: str | None,
    token_budget: int,
    caption_mode: str,
    appearance_blacklist: list[str],
) -> str:
    """Post-processing pipeline for JoyCaption subprocess output.

    Steps:
    1. Strip JoyCaption-specific prefixes ("here are the tags:")
    2. Apply noise tag blacklist (watermark, signature, etc.)
    3. Deduplicate tags (order-preserving)
    4. Appearance tag filter (only for context_only_tags and context_only_natural)
    5. Trigger word injection (anchor prepended if not already present)
    6. Token budget trimming (anchor word protected)

    JoyCaption outputs are already comma-separated tags, so VLM artifact
    stripping is NOT applied (it would corrupt valid tags with colons/commas).

    Args:
        caption: Raw JoyCaption output string.
        anchor_word: Trigger word to prepend. None = no trigger.
        token_budget: Maximum token count for the output.
        caption_mode: Caption mode — controls appearance filtering and trimming.
        appearance_blacklist: List of appearance tag patterns to filter.
            Use DEFAULT_APPEARANCE_BLACKLIST or extend with user additions.

    Returns:
        Processed caption ready for storage.
    """
    # 1. Strip JoyCaption-specific prefix headers
    caption = _strip_joycaption_prefixes(caption)
    # 2. Remove noise tags (watermarks, signatures, etc.)
    caption = _apply_tag_blacklist(caption, _NOISE_TAG_BLACKLIST)
    # 3. Deduplicate tags preserving order
    caption = _dedup_tags(caption)
    # 4. Context-only appearance filter (character LoRA modes only)
    if caption_mode in ("context_only_tags", "context_only_natural"):
        caption = _filter_appearance_tags(caption, appearance_blacklist)
    # 5. Trigger word injection
    if anchor_word and caption:
        caption = _prepend_anchor(caption, anchor_word)
    elif anchor_word and not caption:
        caption = anchor_word
    # 6. Token budget trimming
    caption = _trim_to_budget(caption, token_budget, anchor_word, caption_mode)
    return caption
