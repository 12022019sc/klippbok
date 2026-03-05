"""Integration tests for video API endpoints.

Tests verify:
  - POST /api/v1/video/ingest/start: Returns 200 with operation_id
  - POST /api/v1/video/ingest/{op_id}/cancel: Returns cancelled=true
  - GET  /api/v1/video/scan: Returns scan report with video metadata list
  - POST /api/v1/video/extract/start: Returns 200 with operation_id
  - POST /api/v1/video/extract/{op_id}/cancel: Returns cancelled=true
  - GET  /api/v1/video/clips: Returns list of video clips with metadata
  - GET  /api/v1/video/clips/{clip_id}/thumbnail: Returns JPEG image

All video_service functions are mocked to avoid subprocess calls.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clip_id(relative_path: str) -> str:
    """Compute clip ID (SHA256[:16] of relative path)."""
    return hashlib.sha256(relative_path.encode()).hexdigest()[:16]


def _make_project(tmp_path: Path) -> Path:
    """Create a minimal project directory with some dummy video files."""
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir(parents=True)
    # Create fake mp4 files (just empty bytes, no real video)
    (clips_dir / "scene_001.mp4").write_bytes(b"fake video")
    (clips_dir / "scene_002.mp4").write_bytes(b"fake video")
    return tmp_path


def _make_app(project_dir: Path):
    """Create a TestClient for the klippbok API."""
    from klippbok.api.app import create_app
    app = create_app(project_dir=project_dir)
    return TestClient(app, raise_server_exceptions=True)


def _make_fake_metadata(video_path: Path):
    """Create a fake VideoMetadata for mocking."""
    from klippbok.video.models import ClipValidation, VideoMetadata
    meta = VideoMetadata(
        path=video_path,
        width=1280,
        height=720,
        fps=16.0,
        frame_count=81,
        duration=5.0625,
        codec="h264",
    )
    return ClipValidation(metadata=meta)


def _make_fake_scan_report(project_dir: Path):
    """Create a fake ScanReport for mocking."""
    from klippbok.video.models import ScanReport
    clips_dir = project_dir / "clips"
    clips = [
        _make_fake_metadata(clips_dir / "scene_001.mp4"),
        _make_fake_metadata(clips_dir / "scene_002.mp4"),
    ]
    return ScanReport(directory=clips_dir, clips=clips)


# ---------------------------------------------------------------------------
# POST /api/v1/video/ingest/start
# ---------------------------------------------------------------------------

class TestIngestStart:
    def test_returns_200_with_operation_id(self, tmp_path: Path) -> None:
        """POST /video/ingest/start returns 200 with operation_id."""
        project_dir = _make_project(tmp_path)
        client = _make_app(project_dir)

        with patch("klippbok.api.routers.video.ingest_video", return_value=[]):
            resp = client.post("/api/v1/video/ingest/start", json={
                "video_path": str(tmp_path / "clips" / "scene_001.mp4"),
            })

        assert resp.status_code == 200
        data = resp.json()
        assert "operation_id" in data
        assert isinstance(data["operation_id"], str)
        assert len(data["operation_id"]) > 0

    def test_returns_409_without_project_dir(self) -> None:
        """POST /video/ingest/start returns 409 when no project_dir set."""
        from klippbok.api.app import create_app
        app = create_app(project_dir=None)
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.post("/api/v1/video/ingest/start", json={
            "video_path": "/some/video.mp4",
        })

        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# POST /api/v1/video/ingest/{op_id}/cancel
# ---------------------------------------------------------------------------

class TestIngestCancel:
    def test_cancel_returns_cancelled_true(self, tmp_path: Path) -> None:
        """POST /video/ingest/{op_id}/cancel returns cancelled=true."""
        project_dir = _make_project(tmp_path)
        client = _make_app(project_dir)

        # Start an ingest operation first
        with patch("klippbok.api.routers.video.ingest_video", return_value=[]):
            start_resp = client.post("/api/v1/video/ingest/start", json={
                "video_path": str(tmp_path / "clips" / "scene_001.mp4"),
            })
        assert start_resp.status_code == 200
        op_id = start_resp.json()["operation_id"]

        cancel_resp = client.post(f"/api/v1/video/ingest/{op_id}/cancel")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["cancelled"] is True

    def test_cancel_nonexistent_op_returns_404(self, tmp_path: Path) -> None:
        """POST /video/ingest/missing-id/cancel returns 404."""
        project_dir = _make_project(tmp_path)
        client = _make_app(project_dir)

        resp = client.post("/api/v1/video/ingest/nonexistent-op-id/cancel")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/video/scan
# ---------------------------------------------------------------------------

class TestVideoScan:
    def test_returns_scan_report_list(self, tmp_path: Path) -> None:
        """GET /video/scan returns list of VideoMetadata dicts."""
        project_dir = _make_project(tmp_path)
        client = _make_app(project_dir)

        fake_report = _make_fake_scan_report(project_dir)

        with patch("klippbok.api.routers.video.scan_project_videos", return_value=fake_report):
            resp = client.get("/api/v1/video/scan")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        # Each item should have video metadata fields
        first = data[0]
        assert "fps" in first
        assert "duration" in first
        assert "width" in first
        assert "height" in first
        assert "codec" in first

    def test_scan_returns_409_without_project_dir(self) -> None:
        """GET /video/scan returns 409 when no project_dir set."""
        from klippbok.api.app import create_app
        app = create_app(project_dir=None)
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.get("/api/v1/video/scan")
        assert resp.status_code == 409

    def test_scan_returns_empty_list_for_no_videos(self, tmp_path: Path) -> None:
        """GET /video/scan returns empty list when no clips found."""
        from klippbok.video.models import ScanReport
        project_dir = _make_project(tmp_path)
        client = _make_app(project_dir)

        empty_report = ScanReport(directory=project_dir)

        with patch("klippbok.api.routers.video.scan_project_videos", return_value=empty_report):
            resp = client.get("/api/v1/video/scan")

        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# POST /api/v1/video/extract/start
# ---------------------------------------------------------------------------

class TestExtractStart:
    def test_returns_200_with_operation_id(self, tmp_path: Path) -> None:
        """POST /video/extract/start returns 200 with operation_id."""
        project_dir = _make_project(tmp_path)
        client = _make_app(project_dir)

        with patch("klippbok.api.routers.video.extract_frames", return_value=[]):
            resp = client.post("/api/v1/video/extract/start", json={
                "frames_per_clip": 1,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert "operation_id" in data
        assert isinstance(data["operation_id"], str)

    def test_returns_409_without_project_dir(self) -> None:
        """POST /video/extract/start returns 409 when no project_dir set."""
        from klippbok.api.app import create_app
        app = create_app(project_dir=None)
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.post("/api/v1/video/extract/start", json={"frames_per_clip": 1})
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# POST /api/v1/video/extract/{op_id}/cancel
# ---------------------------------------------------------------------------

class TestExtractCancel:
    def test_cancel_returns_cancelled_true(self, tmp_path: Path) -> None:
        """POST /video/extract/{op_id}/cancel returns cancelled=true."""
        project_dir = _make_project(tmp_path)
        client = _make_app(project_dir)

        with patch("klippbok.api.routers.video.extract_frames", return_value=[]):
            start_resp = client.post("/api/v1/video/extract/start", json={"frames_per_clip": 1})
        assert start_resp.status_code == 200
        op_id = start_resp.json()["operation_id"]

        cancel_resp = client.post(f"/api/v1/video/extract/{op_id}/cancel")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["cancelled"] is True

    def test_cancel_nonexistent_op_returns_404(self, tmp_path: Path) -> None:
        """POST /video/extract/missing-id/cancel returns 404."""
        project_dir = _make_project(tmp_path)
        client = _make_app(project_dir)

        resp = client.post("/api/v1/video/extract/deadbeef/cancel")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/video/clips
# ---------------------------------------------------------------------------

class TestVideoClips:
    def test_returns_list_of_clips(self, tmp_path: Path) -> None:
        """GET /video/clips returns list of video clips with metadata."""
        project_dir = _make_project(tmp_path)
        client = _make_app(project_dir)

        fake_report = _make_fake_scan_report(project_dir)
        fake_thumb = tmp_path / ".thumbs" / "abc123.jpg"
        fake_thumb.parent.mkdir(parents=True, exist_ok=True)
        fake_thumb.write_bytes(b"fake jpeg")

        with (
            patch("klippbok.api.routers.video.scan_project_videos", return_value=fake_report),
            patch("klippbok.api.routers.video.generate_video_thumbnail", return_value=fake_thumb),
        ):
            resp = client.get("/api/v1/video/clips")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2

        # Each item should have clip metadata
        first = data[0]
        assert "id" in first
        assert "relative_path" in first
        assert "thumbnail_url" in first
        assert "duration" in first
        assert "fps" in first
        assert "width" in first
        assert "height" in first
        assert "frame_count" in first

    def test_returns_409_without_project_dir(self) -> None:
        """GET /video/clips returns 409 when no project_dir set."""
        from klippbok.api.app import create_app
        app = create_app(project_dir=None)
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.get("/api/v1/video/clips")
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /api/v1/video/clips/{clip_id}/thumbnail
# ---------------------------------------------------------------------------

class TestVideoThumbnail:
    def test_returns_jpeg_image(self, tmp_path: Path) -> None:
        """GET /video/clips/{clip_id}/thumbnail returns JPEG image response."""
        project_dir = _make_project(tmp_path)
        client = _make_app(project_dir)

        clip_path = project_dir / "clips" / "scene_001.mp4"
        relative_path = str(clip_path.relative_to(project_dir))
        clip_id = hashlib.sha256(relative_path.encode()).hexdigest()[:16]

        # Create a cached thumbnail file
        thumb_dir = project_dir / ".klippbok" / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        cached_thumb = thumb_dir / "test_thumb.jpg"
        cached_thumb.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100 + b"\xff\xd9")

        fake_report = _make_fake_scan_report(project_dir)

        with (
            patch("klippbok.api.routers.video.scan_project_videos", return_value=fake_report),
            patch("klippbok.api.routers.video.generate_video_thumbnail", return_value=cached_thumb),
        ):
            resp = client.get(f"/api/v1/video/clips/{clip_id}/thumbnail")

        assert resp.status_code == 200
        assert "image" in resp.headers.get("content-type", "")

    def test_thumbnail_not_found_returns_404(self, tmp_path: Path) -> None:
        """GET /video/clips/badid/thumbnail returns 404 for unknown clip_id."""
        project_dir = _make_project(tmp_path)
        client = _make_app(project_dir)

        resp = client.get("/api/v1/video/clips/nonexistentclipid123/thumbnail")
        assert resp.status_code == 404
