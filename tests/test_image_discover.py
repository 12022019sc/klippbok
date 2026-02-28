"""Tests for klippbok.image.discover -- uses tmp_path fixtures.

Creates temporary directories with mixed file types to test discovery.
"""

from pathlib import Path

import pytest

from klippbok.image.discover import discover_images
from klippbok.image.errors import ImageError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _touch(path: Path) -> Path:
    """Create an empty file at path, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDiscoverImages:
    """Tests for discover_images function."""

    def test_finds_image_files(self, tmp_path: Path) -> None:
        """Discovers PNG, JPG, JPEG, and WEBP files."""
        _touch(tmp_path / "photo.png")
        _touch(tmp_path / "photo.jpg")
        _touch(tmp_path / "photo.jpeg")
        _touch(tmp_path / "photo.webp")
        _touch(tmp_path / "notes.txt")
        _touch(tmp_path / "video.mp4")

        result = discover_images(tmp_path)
        names = [p.name for p in result]
        assert "photo.png" in names
        assert "photo.jpg" in names
        assert "photo.jpeg" in names
        assert "photo.webp" in names
        assert "notes.txt" not in names
        assert "video.mp4" not in names

    def test_returns_only_images(self, tmp_path: Path) -> None:
        """Only returns files with supported image extensions (png, jpg, jpeg, webp, tif, tiff)."""
        _touch(tmp_path / "a.png")
        _touch(tmp_path / "b.bmp")
        _touch(tmp_path / "c.tiff")
        _touch(tmp_path / "d.gif")

        result = discover_images(tmp_path)
        # .png and .tiff are both supported; .bmp and .gif are not
        assert len(result) == 2
        names = [p.name for p in result]
        assert "a.png" in names
        assert "c.tiff" in names
        assert "b.bmp" not in names
        assert "d.gif" not in names

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Empty directory returns empty list."""
        result = discover_images(tmp_path)
        assert result == []

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        """Raises ImageError for nonexistent directory."""
        fake_dir = tmp_path / "does_not_exist"
        with pytest.raises(ImageError, match="does not exist"):
            discover_images(fake_dir)

    def test_file_path_raises(self, tmp_path: Path) -> None:
        """Raises ImageError if given a file path instead of directory."""
        file_path = _touch(tmp_path / "photo.png")
        with pytest.raises(ImageError, match="not a directory"):
            discover_images(file_path)

    def test_skips_hidden_files(self, tmp_path: Path) -> None:
        """Hidden files (starting with '.') are skipped."""
        _touch(tmp_path / ".hidden.png")
        _touch(tmp_path / "visible.png")

        result = discover_images(tmp_path)
        names = [p.name for p in result]
        assert "visible.png" in names
        assert ".hidden.png" not in names

    def test_sorted_output(self, tmp_path: Path) -> None:
        """Results are sorted by path."""
        _touch(tmp_path / "c.png")
        _touch(tmp_path / "a.png")
        _touch(tmp_path / "b.png")

        result = discover_images(tmp_path)
        names = [p.name for p in result]
        assert names == ["a.png", "b.png", "c.png"]

    def test_recursive_false(self, tmp_path: Path) -> None:
        """Non-recursive mode does not descend into subdirectories."""
        _touch(tmp_path / "root.png")
        _touch(tmp_path / "subdir" / "nested.png")

        result = discover_images(tmp_path, recursive=False)
        names = [p.name for p in result]
        assert "root.png" in names
        assert "nested.png" not in names

    def test_recursive_true(self, tmp_path: Path) -> None:
        """Recursive mode finds images in subdirectories."""
        _touch(tmp_path / "root.png")
        _touch(tmp_path / "subdir" / "nested.png")
        _touch(tmp_path / "subdir" / "deep" / "deep.jpg")

        result = discover_images(tmp_path, recursive=True)
        names = [p.name for p in result]
        assert "root.png" in names
        assert "nested.png" in names
        assert "deep.jpg" in names

    def test_case_insensitive_extension(self, tmp_path: Path) -> None:
        """Extensions are matched case-insensitively."""
        _touch(tmp_path / "photo.PNG")
        _touch(tmp_path / "photo.JPG")

        result = discover_images(tmp_path)
        assert len(result) == 2
