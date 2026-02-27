"""Tests for klippbok.services.project_service."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from klippbok.dataset.models import SamplePair
from klippbok.services import project_service
from klippbok.video.models import IssueCode, Severity, ValidationIssue


# ---------------------------------------------------------------------------
# save_manifest / load_manifest round-trip
# ---------------------------------------------------------------------------

class TestSaveLoadManifest:
    def test_roundtrip(self, tmp_path: Path) -> None:
        samples = [{"stem": "clip_001", "target": "clip_001.mp4", "status": "valid"}]
        path = project_service.save_manifest(tmp_path, samples)
        assert path.exists()

        loaded = project_service.load_manifest(tmp_path)
        assert loaded is not None
        assert loaded["version"] == "1"
        assert loaded["samples"] == samples

    def test_creates_klippbok_directory(self, tmp_path: Path) -> None:
        project_service.save_manifest(tmp_path, [])
        assert (tmp_path / ".klippbok").is_dir()
        assert (tmp_path / ".klippbok" / "manifest.json").exists()

    def test_preserves_created_timestamp(self, tmp_path: Path) -> None:
        """Second save should preserve the original created timestamp."""
        project_service.save_manifest(tmp_path, [{"stem": "a"}])
        first = project_service.load_manifest(tmp_path)
        assert first is not None
        created_1 = first["created"]

        project_service.save_manifest(tmp_path, [{"stem": "a"}, {"stem": "b"}])
        second = project_service.load_manifest(tmp_path)
        assert second is not None
        assert second["created"] == created_1
        assert second["updated"] >= created_1

    def test_custom_version(self, tmp_path: Path) -> None:
        project_service.save_manifest(tmp_path, [], version="2")
        loaded = project_service.load_manifest(tmp_path)
        assert loaded is not None
        assert loaded["version"] == "2"

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        result = project_service.load_manifest(tmp_path)
        assert result is None

    def test_load_missing_version_raises(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / ".klippbok"
        manifest_dir.mkdir()
        (manifest_dir / "manifest.json").write_text('{"samples": []}', encoding="utf-8")

        with pytest.raises(ValueError, match="missing 'version'"):
            project_service.load_manifest(tmp_path)


# ---------------------------------------------------------------------------
# manifest_exists
# ---------------------------------------------------------------------------

class TestManifestExists:
    def test_false_when_missing(self, tmp_path: Path) -> None:
        assert project_service.manifest_exists(tmp_path) is False

    def test_true_after_save(self, tmp_path: Path) -> None:
        project_service.save_manifest(tmp_path, [])
        assert project_service.manifest_exists(tmp_path) is True


# ---------------------------------------------------------------------------
# sample_to_manifest_entry
# ---------------------------------------------------------------------------

class TestSampleToManifestEntry:
    def test_basic_serialization(self, tmp_path: Path) -> None:
        sample = SamplePair(
            stem="clip_001",
            target=tmp_path / "clip_001.mp4",
            caption=tmp_path / "clip_001.txt",
            reference=tmp_path / "clip_001.png",
            width=1280,
            height=720,
            frame_count=17,
        )
        entry = project_service.sample_to_manifest_entry(sample, tmp_path)

        assert entry["stem"] == "clip_001"
        assert entry["target"] == "clip_001.mp4"
        assert entry["caption"] == "clip_001.txt"
        assert entry["reference"] == "clip_001.png"
        assert entry["width"] == 1280
        assert entry["height"] == 720
        assert entry["frame_count"] == 17
        assert entry["type"] == "video"
        assert entry["status"] == "valid"

    def test_relative_paths(self, tmp_path: Path) -> None:
        """Paths should be relative to project_dir."""
        sub = tmp_path / "data" / "clips"
        sample = SamplePair(
            stem="x",
            target=sub / "x.mp4",
            caption=sub / "x.txt",
        )
        entry = project_service.sample_to_manifest_entry(sample, tmp_path)
        # Should use forward-slash relative paths (or OS-native relative)
        assert "x.mp4" in entry["target"]
        assert str(tmp_path) not in entry["target"]

    def test_invalid_sample_status(self, tmp_path: Path) -> None:
        error = ValidationIssue(
            code=IssueCode.CAPTION_MISSING,
            severity=Severity.ERROR,
            message="Missing caption",
            field="caption",
        )
        sample = SamplePair(
            stem="bad",
            target=tmp_path / "bad.mp4",
            issues=[error],
        )
        entry = project_service.sample_to_manifest_entry(sample, tmp_path)
        assert entry["status"] == "invalid"
        assert len(entry["issues"]) == 1
        assert entry["issues"][0]["code"] == "CAPTION_MISSING"

    def test_no_optional_fields_when_none(self, tmp_path: Path) -> None:
        """Optional fields should be omitted when None."""
        sample = SamplePair(stem="x", target=tmp_path / "x.mp4")
        entry = project_service.sample_to_manifest_entry(sample, tmp_path)
        assert "caption" not in entry
        assert "reference" not in entry
        assert "width" not in entry
        assert "height" not in entry
        assert "frame_count" not in entry

    def test_issues_not_present_when_empty(self, tmp_path: Path) -> None:
        sample = SamplePair(stem="x", target=tmp_path / "x.mp4")
        entry = project_service.sample_to_manifest_entry(sample, tmp_path)
        assert "issues" not in entry
