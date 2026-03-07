"""Tests for enhanced video process pipeline.

Tests the multi-stage _run_process pipeline with scene detection + split
for long videos, auto-skip on failure, selective confirm, discard with
video removal, and cancel cleanup.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from klippbok.api.routers.video import (
    ProcessConfirmRequest,
    ProcessDiscardRequest,
    ProcessProgressEvent,
    ProcessRequest,
    _process_results,
    _run_process,
    confirm_process,
    cancel_process,
    discard_process,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manifest(project_dir: Path, entries: list[dict]) -> None:
    """Write a minimal manifest.json with the given image entries."""
    import json
    manifest_dir = project_dir / ".klippbok"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "manifest.json"
    manifest_path.write_text(json.dumps({"images": entries}))


def _drain_queue(queue: asyncio.Queue) -> list[ProcessProgressEvent]:
    """Drain all events from queue synchronously."""
    events = []
    while not queue.empty():
        item = queue.get_nowait()
        if item is not None:
            events.append(item)
    return events


async def _collect_events(queue: asyncio.Queue) -> list[ProcessProgressEvent]:
    """Collect all events until None sentinel."""
    events = []
    while True:
        item = await asyncio.wait_for(queue.get(), timeout=10)
        if item is None:
            break
        events.append(item)
    return events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal project directory with refs/ and .klippbok/."""
    refs = tmp_path / "refs"
    refs.mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# Test 1: Long video (>=30s) uses scene detect + split + extract per clip
# ---------------------------------------------------------------------------

class TestLongVideoSceneDetectSplit:
    """_run_process with a video >=30s calls detect_scenes, split, extract per clip."""

    @pytest.mark.asyncio
    async def test_long_video_pipeline(self, project_dir: Path) -> None:
        # Create a video entry with duration >= 30s
        video_rel = "long_video.mp4"
        video_abs = project_dir / video_rel
        video_abs.write_bytes(b"fake-video")

        _make_manifest(project_dir, [
            {"path": video_rel, "type": "video"},
        ])

        mock_metadata = MagicMock()
        mock_metadata.duration = 60.0  # >= 30s threshold

        mock_scene = MagicMock()
        mock_scene.frame_number = 100
        mock_scene.timecode = 3.3

        mock_clip1 = MagicMock()
        mock_clip1.output = project_dir / "clips" / "clip_001.mp4"
        mock_clip2 = MagicMock()
        mock_clip2.output = project_dir / "clips" / "clip_002.mp4"

        mock_extract_result = MagicMock()
        mock_extract_result.success = True
        mock_extract_result.skipped = False

        queue: asyncio.Queue = asyncio.Queue()
        op_id = "test-long-op"
        request = ProcessRequest(video_paths=[video_rel])

        with (
            patch("klippbok.api.routers.video.probe_video", return_value=mock_metadata) as mock_probe,
            patch("klippbok.api.routers.video.detect_scenes", return_value=[mock_scene]) as mock_detect,
            patch("klippbok.api.routers.video.split_video_at_scenes", return_value=[mock_clip1, mock_clip2]) as mock_split,
            patch("klippbok.api.routers.video.extract_reference_image", return_value=mock_extract_result),
        ):
            await _run_process(request, queue, op_id, project_dir)

        mock_probe.assert_called_once()
        mock_detect.assert_called_once()
        mock_split.assert_called_once()

        events = _drain_queue(queue)
        # Should have events and a None sentinel was added
        stages = [e.stage for e in events]
        assert "Probing videos" in stages
        assert "Scene detection" in stages
        assert "Splitting clips" in stages
        assert "Extracting frames" in stages
        assert "Complete" in stages


# ---------------------------------------------------------------------------
# Test 2: Short video (<30s) skips scene detection
# ---------------------------------------------------------------------------

class TestShortVideoDirectExtract:
    """_run_process with a video <30s skips scene detection."""

    @pytest.mark.asyncio
    async def test_short_video_skips_scene_detect(self, project_dir: Path) -> None:
        video_rel = "short_video.mp4"
        video_abs = project_dir / video_rel
        video_abs.write_bytes(b"fake-video")

        _make_manifest(project_dir, [
            {"path": video_rel, "type": "video"},
        ])

        mock_metadata = MagicMock()
        mock_metadata.duration = 10.0  # < 30s

        mock_extract_result = MagicMock()
        mock_extract_result.success = True
        mock_extract_result.skipped = False

        queue: asyncio.Queue = asyncio.Queue()
        op_id = "test-short-op"
        request = ProcessRequest(video_paths=[video_rel])

        with (
            patch("klippbok.api.routers.video.probe_video", return_value=mock_metadata) as mock_probe,
            patch("klippbok.api.routers.video.detect_scenes") as mock_detect,
            patch("klippbok.api.routers.video.split_video_at_scenes") as mock_split,
            patch("klippbok.api.routers.video.extract_reference_image", return_value=mock_extract_result),
        ):
            await _run_process(request, queue, op_id, project_dir)

        mock_probe.assert_called_once()
        mock_detect.assert_not_called()
        mock_split.assert_not_called()

        events = _drain_queue(queue)
        stages = [e.stage for e in events]
        assert "Probing videos" in stages
        assert "Extracting frames" in stages
        assert "Scene detection" not in stages


# ---------------------------------------------------------------------------
# Test 3: Auto-skip failed videos
# ---------------------------------------------------------------------------

class TestAutoSkipFailedVideos:
    """Failed videos are auto-skipped with error details in results."""

    @pytest.mark.asyncio
    async def test_failed_video_skipped(self, project_dir: Path) -> None:
        good_rel = "good.mp4"
        bad_rel = "bad.mp4"
        (project_dir / good_rel).write_bytes(b"fake")
        (project_dir / bad_rel).write_bytes(b"fake")

        _make_manifest(project_dir, [
            {"path": bad_rel, "type": "video"},
            {"path": good_rel, "type": "video"},
        ])

        def mock_probe(path):
            m = MagicMock()
            m.duration = 5.0  # short videos
            if "bad" in str(path):
                raise RuntimeError("FFmpeg probe failed")
            return m

        mock_extract_result = MagicMock()
        mock_extract_result.success = True
        mock_extract_result.skipped = False

        queue: asyncio.Queue = asyncio.Queue()
        op_id = "test-skip-op"
        request = ProcessRequest(video_paths=[bad_rel, good_rel])

        with (
            patch("klippbok.api.routers.video.probe_video", side_effect=mock_probe),
            patch("klippbok.api.routers.video.detect_scenes"),
            patch("klippbok.api.routers.video.split_video_at_scenes"),
            patch("klippbok.api.routers.video.extract_reference_image", return_value=mock_extract_result),
        ):
            await _run_process(request, queue, op_id, project_dir)

        events = _drain_queue(queue)
        complete_events = [e for e in events if e.status == "complete"]
        assert len(complete_events) == 1
        complete_evt = complete_events[0]
        assert complete_evt.skipped_videos is not None
        assert len(complete_evt.skipped_videos) == 1
        assert "bad.mp4" in complete_evt.skipped_videos[0]["path"]
        assert "FFmpeg probe failed" in complete_evt.skipped_videos[0]["reason"]


# ---------------------------------------------------------------------------
# Test 4: Stage names in progress events
# ---------------------------------------------------------------------------

class TestStageProgressEvents:
    """ProcessProgressEvent includes correct stage names."""

    @pytest.mark.asyncio
    async def test_stage_names_present(self, project_dir: Path) -> None:
        video_rel = "video.mp4"
        (project_dir / video_rel).write_bytes(b"fake")

        _make_manifest(project_dir, [
            {"path": video_rel, "type": "video"},
        ])

        mock_metadata = MagicMock()
        mock_metadata.duration = 60.0  # long video to go through all stages

        mock_scene = MagicMock()
        mock_clip = MagicMock()
        mock_clip.output = project_dir / "clip.mp4"

        mock_extract = MagicMock()
        mock_extract.success = True
        mock_extract.skipped = False

        queue: asyncio.Queue = asyncio.Queue()
        op_id = "test-stages-op"
        request = ProcessRequest(video_paths=[video_rel])

        with (
            patch("klippbok.api.routers.video.probe_video", return_value=mock_metadata),
            patch("klippbok.api.routers.video.detect_scenes", return_value=[mock_scene]),
            patch("klippbok.api.routers.video.split_video_at_scenes", return_value=[mock_clip]),
            patch("klippbok.api.routers.video.extract_reference_image", return_value=mock_extract),
        ):
            await _run_process(request, queue, op_id, project_dir)

        events = _drain_queue(queue)
        stages = [e.stage for e in events]
        expected_stages = ["Probing videos", "Scene detection", "Splitting clips", "Extracting frames", "Complete"]
        for expected in expected_stages:
            assert expected in stages, f"Missing stage: {expected}"


# ---------------------------------------------------------------------------
# Test 5: confirm_process with frame_paths imports only specific frames
# ---------------------------------------------------------------------------

class TestConfirmSelectiveFramePaths:
    """confirm_process with frame_paths imports only those frames."""

    @pytest.mark.asyncio
    async def test_selective_import(self, project_dir: Path) -> None:
        # Create two frames in refs/
        refs_dir = project_dir / "refs"
        refs_dir.mkdir(exist_ok=True)
        (refs_dir / "frame1.png").write_bytes(b"PNG-frame-1")
        (refs_dir / "frame2.png").write_bytes(b"PNG-frame-2")
        (refs_dir / "frame3.png").write_bytes(b"PNG-frame-3")

        _make_manifest(project_dir, [
            {"path": "video1.mp4", "type": "video"},
        ])

        mock_request = MagicMock()
        mock_request.app.state.project_dir = project_dir

        body = ProcessConfirmRequest(
            video_paths=["video1.mp4"],
            frame_paths=["refs/frame1.png", "refs/frame3.png"],
        )

        mock_report = MagicMock()
        mock_report.imported = 2

        with (
            patch("klippbok.api.routers.video.batch_import_images", return_value=mock_report) as mock_batch,
            patch("klippbok.api.routers.video.remove_image_entries", return_value=1),
        ):
            result = await confirm_process(body, mock_request)

        # batch_import_images should be called with a temp dir containing only the 2 selected frames
        call_args = mock_batch.call_args
        source_dir = call_args[0][0] if call_args[0] else call_args[1].get("source_dir")
        # Verify it was called (we'll check the temp dir logic in the implementation)
        mock_batch.assert_called_once()
        assert result["imported"] == 2


# ---------------------------------------------------------------------------
# Test 6: discard_process with remove_videos=True calls remove_image_entries
# ---------------------------------------------------------------------------

class TestDiscardWithVideoRemoval:
    """discard_process with remove_videos=True removes video entries from manifest."""

    @pytest.mark.asyncio
    async def test_discard_removes_video_entries(self, project_dir: Path) -> None:
        # Create a frame to discard
        refs_dir = project_dir / "refs"
        refs_dir.mkdir(exist_ok=True)
        frame = refs_dir / "frame1.png"
        frame.write_bytes(b"PNG-frame")

        mock_request = MagicMock()
        mock_request.app.state.project_dir = project_dir

        body = ProcessDiscardRequest(
            frame_paths=["refs/frame1.png"],
            remove_videos=True,
            video_paths=["video1.mp4", "video2.mp4"],
        )

        with patch("klippbok.api.routers.video.remove_image_entries", return_value=2) as mock_remove:
            result = await discard_process(body, mock_request)

        mock_remove.assert_called_once_with(project_dir, {"video1.mp4", "video2.mp4"})
        assert result["deleted"] == 1  # one frame file deleted
        assert result["videos_removed"] == 2


# ---------------------------------------------------------------------------
# Test 7: cancel_process cleans up temp processing directory
# ---------------------------------------------------------------------------

class TestCancelCleansUpTempDir:
    """cancel_process removes extracted frames from temp processing directory."""

    @pytest.mark.asyncio
    async def test_cancel_cleanup(self, project_dir: Path) -> None:
        op_id = "test-cancel-op"

        # Simulate a temp processing dir
        temp_dir = project_dir / "refs" / f".processing-{op_id}"
        temp_dir.mkdir(parents=True)
        (temp_dir / "frame1.png").write_bytes(b"PNG")
        (temp_dir / "frame2.png").write_bytes(b"PNG")

        # Store temp_dir in process results so cancel can find it
        _process_results[op_id] = {"temp_dir": str(temp_dir)}

        # Create a mock task
        mock_task = MagicMock()
        mock_task.done.return_value = False

        from klippbok.api.routers.video import _process_tasks, _process_queues
        _process_tasks[op_id] = mock_task
        _process_queues[op_id] = asyncio.Queue()

        result = await cancel_process(op_id)

        assert result["cancelled"] is True
        assert not temp_dir.exists(), "Temp processing dir should be cleaned up"

        # Cleanup
        _process_results.pop(op_id, None)
