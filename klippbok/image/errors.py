"""Klippbok image domain errors.

Custom exceptions for image processing operations. Every error includes
a clear message about what went wrong AND how to fix it.

Follows the same pattern as klippbok.video.errors and
klippbok.dataset.errors.
"""

from __future__ import annotations


class ImageError(Exception):
    """Base exception for all image processing errors.

    Subclasses provide specific context for different failure modes.
    All error messages follow the pattern: what happened + how to fix it.
    """

    pass


class ImageProbeError(ImageError):
    """Failed to probe an image file.

    Common causes: file doesn't exist, file is not a valid image,
    Pillow can't open the file format.

    Fix: Check that the file exists, is a supported format (PNG, JPEG, WEBP),
    and is not zero-length.
    """

    def __init__(self, path: str, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"Failed to probe image '{path}': {detail}")


class ImageValidationError(ImageError):
    """Image validation encountered a fatal error.

    This is for structural problems that prevent validation from running
    at all -- not for individual image issues (those are collected as
    ValidationIssue objects, not exceptions).

    Fix: Ensure the image metadata was probed successfully before validation.
    """

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"Image validation failed: {detail}")
