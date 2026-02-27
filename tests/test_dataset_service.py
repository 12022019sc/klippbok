"""Tests for klippbok.services.dataset_service."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from klippbok.config.data_schema import KlippbokDataConfig
from klippbok.dataset.models import DatasetReport, OrganizeLayout, OrganizeResult
from klippbok.services import dataset_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _touch(path: Path, content: bytes = b"") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _make_textured_image(path: Path, size: int = 64) -> Path:
    rng = np.random.RandomState(42)
    img = rng.randint(0, 256, (size, size, 3), dtype=np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)
    return path


def _make_flat_dataset(tmp_path: Path, stems: list[str]) -> Path:
    for stem in stems:
        _touch(tmp_path / f"{stem}.mp4")
        _touch(tmp_path / f"{stem}.txt", f"Caption for {stem}.".encode())
        _make_textured_image(tmp_path / f"{stem}.png")
    return tmp_path


# ---------------------------------------------------------------------------
# validate()
# ---------------------------------------------------------------------------

class TestValidate:
    def test_returns_dataset_report(self, tmp_path: Path) -> None:
        _make_flat_dataset(tmp_path, ["a", "b"])
        config = KlippbokDataConfig(datasets=[{"path": str(tmp_path)}])
        report = dataset_service.validate(config, tmp_path)
        assert isinstance(report, DatasetReport)
        assert report.total_samples == 2

    def test_empty_dataset_returns_report(self, tmp_path: Path) -> None:
        config = KlippbokDataConfig(datasets=[{"path": str(tmp_path)}])
        report = dataset_service.validate(config, tmp_path)
        assert isinstance(report, DatasetReport)
        assert report.total_samples == 0

    def test_quality_override_applied(self, tmp_path: Path) -> None:
        """Quality flag should set blur_threshold and exposure_range."""
        _make_flat_dataset(tmp_path, ["a"])
        config = KlippbokDataConfig(datasets=[{"path": str(tmp_path)}])

        # Call with quality=True -- should not raise
        report = dataset_service.validate(config, tmp_path, quality=True)
        assert isinstance(report, DatasetReport)

    def test_duplicates_override_applied(self, tmp_path: Path) -> None:
        """Duplicates flag should enable duplicate detection."""
        img = np.full((64, 64, 3), 128, dtype=np.uint8)
        _touch(tmp_path / "a.mp4")
        _touch(tmp_path / "a.txt", b"Caption a")
        cv2.imwrite(str(tmp_path / "a.png"), img)
        _touch(tmp_path / "b.mp4")
        _touch(tmp_path / "b.txt", b"Caption b")
        cv2.imwrite(str(tmp_path / "b.png"), img)

        config = KlippbokDataConfig(datasets=[{"path": str(tmp_path)}])
        report = dataset_service.validate(config, tmp_path, duplicates=True)
        assert isinstance(report, DatasetReport)

    def test_quality_preserves_existing_thresholds(self, tmp_path: Path) -> None:
        """quality=True should not overwrite already-configured thresholds."""
        _make_flat_dataset(tmp_path, ["a"])
        config = KlippbokDataConfig(
            datasets=[{"path": str(tmp_path)}],
            quality={"blur_threshold": 100.0},
        )
        report = dataset_service.validate(config, tmp_path, quality=True)
        assert isinstance(report, DatasetReport)


# ---------------------------------------------------------------------------
# organize()
# ---------------------------------------------------------------------------

class TestOrganize:
    def test_returns_organize_result(self, tmp_path: Path) -> None:
        src = _make_flat_dataset(tmp_path / "src", ["a", "b"])
        out = tmp_path / "out"
        result = dataset_service.organize(
            source_dir=src,
            output_dir=out,
            layout=OrganizeLayout.FLAT,
        )
        assert isinstance(result, OrganizeResult)
        assert result.organized_count == 2

    def test_dry_run_creates_nothing(self, tmp_path: Path) -> None:
        src = _make_flat_dataset(tmp_path / "src", ["a"])
        out = tmp_path / "out"
        result = dataset_service.organize(
            source_dir=src,
            output_dir=out,
            layout=OrganizeLayout.FLAT,
            dry_run=True,
        )
        assert result.dry_run is True
        assert not out.exists()

    def test_concepts_filtering(self, tmp_path: Path) -> None:
        sorted_dir = tmp_path / "sorted"
        _make_flat_dataset(sorted_dir / "holly", ["clip_a"])
        _make_flat_dataset(sorted_dir / "cat", ["clip_b"])
        out = tmp_path / "out"

        result = dataset_service.organize(
            source_dir=sorted_dir,
            output_dir=out,
            layout=OrganizeLayout.FLAT,
            concepts="holly",
        )
        assert result.organized_count == 1
        assert (out / "clip_a.mp4").exists()
        assert not (out / "clip_b.mp4").exists()


# ---------------------------------------------------------------------------
# preview_bucketing()
# ---------------------------------------------------------------------------

class TestPreviewBucketing:
    def test_returns_bucketing_result(self) -> None:
        from klippbok.dataset.bucketing import BucketingResult
        from klippbok.dataset.models import (
            DatasetValidation,
            SamplePair,
            StructureType,
        )

        samples = [
            SamplePair(
                stem="a", target=Path("a.mp4"),
                width=320, height=240, frame_count=17,
            ),
            SamplePair(
                stem="b", target=Path("b.mp4"),
                width=320, height=240, frame_count=17,
            ),
        ]
        report = DatasetReport(
            datasets=[
                DatasetValidation(
                    source_path=Path("/data"),
                    structure=StructureType.FLAT,
                    samples=samples,
                ),
            ],
        )
        result = dataset_service.preview_bucketing(report)
        assert isinstance(result, BucketingResult)
        assert result.total_buckets == 1
        assert result.total_assigned == 2
