"""Tests for klippbok.image.dedup module."""

from __future__ import annotations

from klippbok.image.dedup import are_near_duplicates


def test_are_near_duplicates_custom_threshold() -> None:
    """Custom threshold parameter narrows match window."""
    h1 = "0" * 16  # 64-bit hash as hex
    h2 = "ff00000000000000"  # differs in 8 bits
    # Default threshold (10) should match
    assert are_near_duplicates(h1, h2) is True
    # Tight threshold (6) should NOT match
    assert are_near_duplicates(h1, h2, threshold=6) is False
    # Exact match always works
    assert are_near_duplicates(h1, h1, threshold=1) is True
