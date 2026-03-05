"""Unit tests for klippbok.services.video_service.

Tests mock underlying video module functions to avoid subprocess calls.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from klippbok.video.models import (
    ClipInfo,
    ClipValidation,
    ScanReport,
    VideoMetadata,
)


# ---------------------------------------------------------------------------
# Helpers to build fake model instances
# ---------------------------------------------------------------------------

def _make_metadata(path: Path | None = None) -> VideoMetadata:
    """Build a minimal VideoMetadata for testing."""
    return VideoMetadata(
        path=path or Path("/fake/clip.mp4"),
        width=1280,
        height=720,
        fps=16.0,
        frame_count=81,
        duration=5.0625,
        codec="h264",
    )


def _make_clip_validation(metadata: VideoMetadata | None = None) -> ClipValidation:
    return ClipValidation(metadata=metadata or _make_metadata())


def _make_clip_info(source: Path | None = None, output: Path | None = None) -> ClipInfo:
    return ClipInfo(
        source=source or Path("/fake/source.mp4"),
        output=output or Path("/fake/output/clip_000.mp4"),
        frame_count=81,
        duration=5.0625,
        width=1280,
        height=720,
        fps=16.0,
        was_reencoded=False,
    )


# ---------------------------------------------------------------------------
# scan_project_videos
# ---------------------------------------------------------------------------

class TestScanProjectVideos:
    def test_returns_scan_report_with_clips(self, tmp_path: Path) -> None:
        """scan_project_videos returns ScanReport with metadata for clips."""
        from klippbok.services.video_service import scan_project_videos

        meta = _make_metadata(tmp_path / "clip.mp4")
        validation = _make_clip_validation(meta)
        fake_report = ScanReport(directory=tmp_path, clips=[validation])

        with (
            patch("klippbok.services.video_service.probe_directory", return_value=[meta]) as mock_probe,
            patch("klippbok.services.video_service.validate_directory", return_value=fake_report) as mock_validate,
        ):
            report = scan_project_videos(tmp_path)

        assert isinstance(report, ScanReport)
        assert report.total == 1
        mock_probe.assert_called_once_with(tmp_path)
        mock_validate.assert_called_once()

    def test_returns_empty_report_for_no_videos(self, tmp_path: Path) -> None:
        """scan_project_videos returns empty report when no videos found."""
        from klippbok.services.video_service import scan_project_videos

        empty_report = ScanReport(directory=tmp_path, clips=[])

        with (
            patch("klippbok.services.video_service.probe_directory", return_value=[]),
            patch("klippbok.services.video_service.validate_directory", return_value=empty_report),
        ):
            report = scan_project_videos(tmp_path)

        assert isinstance(report, ScanReport)
        assert report.total == 0

    def test_uses_default_config_when_none_provided(self, tmp_path: Path) -> None:
        """scan_project_videos uses VideoConfig defaults when config=None."""
        from klippbok.config.data_schema import VideoConfig
        from klippbok.services.video_service import scan_project_videos

        fake_report = ScanReport(directory=tmp_path)

        with (
            patch("klippbok.services.video_service.probe_directory", return_value=[]),
            patch("klippbok.services.video_service.validate_directory", return_value=fake_report) as mock_validate,
        ):
            scan_project_videos(tmp_path)

        # Should have been called with a VideoConfig
        args, kwargs = mock_validate.call_args
        # Second positional arg is config
        config_arg = args[1] if len(args) > 1 else kwargs.get("config")
        assert isinstance(config_arg, VideoConfig)


# ---------------------------------------------------------------------------
# ingest_video
# ---------------------------------------------------------------------------

class TestIngestVideo:
    def test_calls_scene_detection_and_split(self, tmp_path: Path) -> None:
        """ingest_video calls detect_scenes then split_video_at_scenes."""
        from klippbok.services.video_service import ingest_video

        video_path = tmp_path / "source.mp4"
        output_dir = tmp_path / "out"
        fake_scenes = [(0.0, 3.5), (3.5, 7.0)]
        fake_clips = [_make_clip_info()]

        with (
            patch("klippbok.services.video_service.detect_scenes", return_value=fake_scenes) as mock_detect,
            patch("klippbok.services.video_service.split_video_at_scenes", return_value=fake_clips) as mock_split,
        ):
            result = ingest_video(video_path, output_dir)

        assert result == fake_clips
        mock_detect.assert_called_once_with(video_path, threshold=27.0)
        mock_split.assert_called_once()

    def test_skips_scene_detection_with_triage_segments(self, tmp_path: Path) -> None:
        """ingest_video uses triage_segments directly, skips scene detection."""
        from klippbok.services.video_service import ingest_video

        video_path = tmp_path / "source.mp4"
        output_dir = tmp_path / "out"
        triage_segments = [(1.0, 4.0), (6.0, 9.0)]
        fake_clips = [_make_clip_info()]

        with (
            patch("klippbok.services.video_service.detect_scenes") as mock_detect,
            patch("klippbok.services.video_service.split_video_segments", return_value=fake_clips) as mock_split,
        ):
            result = ingest_video(video_path, output_dir, triage_segments=triage_segments)

        assert result == fake_clips
        mock_detect.assert_not_called()
        mock_split.assert_called_once()

    def test_calls_progress_callback(self, tmp_path: Path) -> None:
        """ingest_video calls progress_callback at stage transitions."""
        from klippbok.services.video_service import ingest_video

        video_path = tmp_path / "source.mp4"
        output_dir = tmp_path / "out"
        fake_clips = [_make_clip_info()]
        callback_calls: list[tuple] = []

        def record_callback(stage: str, current: int, total: int) -> None:
            callback_calls.append((stage, current, total))

        with (
            patch("klippbok.services.video_service.detect_scenes", return_value=[]),
            patch("klippbok.services.video_service.split_video_at_scenes", return_value=fake_clips),
        ):
            ingest_video(video_path, output_dir, progress_callback=record_callback)

        assert len(callback_calls) >= 1  # at least one progress event emitted

    def test_returns_list_of_clip_info(self, tmp_path: Path) -> None:
        """ingest_video returns list[ClipInfo] from the split function."""
        from klippbok.services.video_service import ingest_video

        video_path = tmp_path / "source.mp4"
        output_dir = tmp_path / "out"
        expected_clips = [_make_clip_info(), _make_clip_info()]

        with (
            patch("klippbok.services.video_service.detect_scenes", return_value=[]),
            patch("klippbok.services.video_service.split_video_at_scenes", return_value=expected_clips),
        ):
            result = ingest_video(video_path, output_dir)

        assert result == expected_clips
        assert all(isinstance(c, ClipInfo) for c in result)


# ---------------------------------------------------------------------------
# extract_frames
# ---------------------------------------------------------------------------

class TestExtractFrames:
    def test_calls_extract_directory_and_returns_paths(self, tmp_path: Path) -> None:
        """extract_frames wraps extract_directory and returns list of Paths."""
        from klippbok.services.video_service import extract_frames
        from klippbok.video.extract_models import ExtractionReport, ExtractionResult

        clips_dir = tmp_path / "clips"
        output_dir = tmp_path / "refs"
        expected_paths = [output_dir / "clip_000.png", output_dir / "clip_001.png"]

        fake_report = ExtractionReport(
            results=[
                ExtractionResult(
                    source=clips_dir / f"clip_{i:03d}.mp4",
                    output=p,
                    success=True,
                )
                for i, p in enumerate(expected_paths)
            ]
        )

        with patch("klippbok.services.video_service.extract_directory", return_value=fake_report) as mock_extract:
            result = extract_frames(clips_dir, output_dir)

        assert result == expected_paths
        mock_extract.assert_called_once()
        # clips_dir and output_dir should be first two args
        call_args = mock_extract.call_args
        assert call_args[0][0] == clips_dir
        assert call_args[0][1] == output_dir

    def test_passes_frames_per_clip_to_extract_directory(self, tmp_path: Path) -> None:
        """extract_frames passes frames_per_clip to extract_directory config."""
        from klippbok.services.video_service import extract_frames
        from klippbok.video.extract_models import ExtractionReport

        clips_dir = tmp_path / "clips"
        output_dir = tmp_path / "refs"
        empty_report = ExtractionReport()

        with patch("klippbok.services.video_service.extract_directory", return_value=empty_report) as mock_extract:
            extract_frames(clips_dir, output_dir, frames_per_clip=3)

        mock_extract.assert_called_once()


# ---------------------------------------------------------------------------
# generate_video_thumbnail
# ---------------------------------------------------------------------------

class TestGenerateVideoThumbnail:
    def test_extracts_first_frame_via_ffmpeg(self, tmp_path: Path) -> None:
        """generate_video_thumbnail calls ffmpeg and returns thumb path."""
        from klippbok.api.thumbnail import generate_video_thumbnail

        video_path = tmp_path / "clip.mp4"
        video_path.write_bytes(b"fake video content")
        cache_dir = tmp_path / ".thumbs"

        fake_result = MagicMock()
        fake_result.returncode = 0

        def fake_run(cmd, **kwargs):
            # Simulate ffmpeg writing the output file
            out_path = Path(cmd[-1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"fake jpeg")
            return fake_result

        with patch("subprocess.run", side_effect=fake_run):
            thumb = generate_video_thumbnail(video_path, cache_dir)

        assert thumb.exists()
        assert thumb.suffix == ".jpg"
        assert thumb.parent == cache_dir

    def test_returns_cached_file_on_second_call(self, tmp_path: Path) -> None:
        """generate_video_thumbnail returns cached JPEG without calling ffmpeg again."""
        from klippbok.api.thumbnail import generate_video_thumbnail

        video_path = tmp_path / "clip.mp4"
        video_path.write_bytes(b"fake video content")
        cache_dir = tmp_path / ".thumbs"

        fake_result = MagicMock()
        fake_result.returncode = 0

        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            out_path = Path(cmd[-1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"fake jpeg")
            return fake_result

        with patch("subprocess.run", side_effect=fake_run):
            thumb1 = generate_video_thumbnail(video_path, cache_dir)
            thumb2 = generate_video_thumbnail(video_path, cache_dir)

        assert thumb1 == thumb2
        assert call_count == 1  # ffmpeg only called once

    def test_cache_key_based_on_absolute_path(self, tmp_path: Path) -> None:
        """generate_video_thumbnail uses SHA256[:16] of absolute path as cache key."""
        import hashlib
        from klippbok.api.thumbnail import generate_video_thumbnail

        video_path = tmp_path / "clip.mp4"
        video_path.write_bytes(b"fake video content")
        cache_dir = tmp_path / ".thumbs"

        expected_hash = hashlib.sha256(str(video_path.resolve()).encode()).hexdigest()[:16]

        fake_result = MagicMock()
        fake_result.returncode = 0

        def fake_run(cmd, **kwargs):
            out_path = Path(cmd[-1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"fake jpeg")
            return fake_result

        with patch("subprocess.run", side_effect=fake_run):
            thumb = generate_video_thumbnail(video_path, cache_dir)

        assert thumb.stem == expected_hash
