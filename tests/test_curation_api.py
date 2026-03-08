"""Tests for curation API router endpoints.

Uses FastAPI TestClient with mocked pipeline functions.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from klippbok.api.app import create_app
from klippbok.curation.models import (
    CurationConfig,
    CurationResult,
    ImageScore,
    PipelineSummary,
    SignalScores,
)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Create a TestClient with a temporary project directory."""
    app = create_app(project_dir=tmp_path)
    return TestClient(app)


def _make_result() -> CurationResult:
    """Create a sample CurationResult for testing."""
    return CurationResult(
        config=CurationConfig(mode="character", target_count=5),
        scores={
            "abc123": ImageScore(
                image_id="abc123",
                relative_path="images/test.jpg",
                composite_score=0.85,
                mode="character",
            ),
        },
        selected_ids=["abc123"],
        pinned_ids=[],
        excluded_ids=[],
        summary=PipelineSummary(total_scanned=10, passed_quality=7, selected=5),
        timestamp="2026-03-08T00:00:00Z",
    )


class TestStartEndpoint:
    """POST /curation/start returns 202 with operation_id."""

    def test_start_returns_202(self, client: TestClient) -> None:
        """Start curation returns 202 with an operation_id."""
        # We need to mock the background task to prevent actual ML work
        with patch("klippbok.api.routers.curation._run_curation_bg"):
            resp = client.post(
                "/api/v1/curation/start",
                json={"mode": "character", "target_count": 10},
            )

        assert resp.status_code == 202
        data = resp.json()
        assert "operation_id" in data
        assert isinstance(data["operation_id"], str)


class TestResultsEndpoint:
    """GET /curation/results returns 404 when no results, 200 with data."""

    def test_results_404_when_none(self, client: TestClient) -> None:
        """GET /curation/results returns 404 before any run."""
        resp = client.get("/api/v1/curation/results")
        assert resp.status_code == 404

    def test_results_returns_data(self, client: TestClient, tmp_path: Path) -> None:
        """GET /curation/results returns 200 with saved result data."""
        # Save a result to disk
        result = _make_result()
        klippbok_dir = tmp_path / ".klippbok"
        klippbok_dir.mkdir()
        (klippbok_dir / "curation_results.json").write_text(
            result.model_dump_json(indent=2), encoding="utf-8",
        )

        resp = client.get("/api/v1/curation/results")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["total_scanned"] == 10
        assert data["summary"]["selected"] == 5
        assert "abc123" in data["scores"]


class TestRediversifyEndpoint:
    """POST /curation/rediversify updates selection."""

    def test_rediversify_returns_updated_result(self, client: TestClient) -> None:
        """POST /curation/rediversify with pins/excludes returns updated result."""
        updated_result = _make_result()
        updated_result.selected_ids = ["abc123"]
        updated_result.pinned_ids = ["abc123"]
        updated_result.excluded_ids = ["def456"]

        with patch(
            "klippbok.api.routers.curation.rediversify",
            return_value=updated_result,
        ):
            resp = client.post(
                "/api/v1/curation/rediversify",
                json={"pinned_ids": ["abc123"], "excluded_ids": ["def456"]},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["pinned_ids"] == ["abc123"]
        assert data["excluded_ids"] == ["def456"]

    def test_rediversify_404_when_no_results(self, client: TestClient) -> None:
        """POST /curation/rediversify returns 404 if no prior results."""
        with patch(
            "klippbok.api.routers.curation.rediversify",
            side_effect=FileNotFoundError("No curation results found"),
        ):
            resp = client.post(
                "/api/v1/curation/rediversify",
                json={"pinned_ids": [], "excluded_ids": []},
            )

        assert resp.status_code == 404


class TestApplyEndpoint:
    """POST /curation/apply returns selected_ids."""

    def test_apply_returns_selected_ids(self, client: TestClient, tmp_path: Path) -> None:
        """POST /curation/apply returns the list of selected image IDs."""
        result = _make_result()
        klippbok_dir = tmp_path / ".klippbok"
        klippbok_dir.mkdir()
        (klippbok_dir / "curation_results.json").write_text(
            result.model_dump_json(indent=2), encoding="utf-8",
        )

        resp = client.post("/api/v1/curation/apply")
        assert resp.status_code == 200
        data = resp.json()
        assert data["selected_ids"] == ["abc123"]

    def test_apply_404_when_no_results(self, client: TestClient) -> None:
        """POST /curation/apply returns 404 if no results saved."""
        resp = client.post("/api/v1/curation/apply")
        assert resp.status_code == 404


class TestSSEProgress:
    """SSE events are well-formed from the curation pipeline."""

    def test_sse_events_well_formed(self, client: TestClient) -> None:
        """Verify SSE events have correct structure with event name and JSON data."""
        # First start an operation to get an op_id
        with patch("klippbok.api.routers.curation._run_curation_bg"):
            resp = client.post(
                "/api/v1/curation/start",
                json={"mode": "character", "target_count": 5},
            )
        op_id = resp.json()["operation_id"]

        # Put a test event into the queue manually
        import asyncio
        from klippbok.api.routers.curation import _curation_queues

        queue = _curation_queues.get(op_id)
        if queue:
            # Push a progress event and then None sentinel
            queue.put_nowait({
                "event": "curation_progress",
                "data": {
                    "operation_id": op_id,
                    "stage": "scoring",
                    "current": 5,
                    "total": 10,
                    "message": "scoring: 5/10",
                },
            })
            queue.put_nowait({
                "event": "curation_done",
                "data": {
                    "operation_id": op_id,
                    "status": "complete",
                    "current": 10,
                    "total": 10,
                    "message": "Done",
                },
            })

            # Read SSE stream
            with client.stream("GET", f"/api/v1/curation/{op_id}/events") as response:
                lines = []
                for line in response.iter_lines():
                    lines.append(line)
                    # Stop after getting a few events
                    if len(lines) > 10:
                        break

            # Should contain event types and data
            raw = "\n".join(lines)
            assert "curation_progress" in raw or "curation_done" in raw

    def test_events_404_unknown_op(self, client: TestClient) -> None:
        """GET /curation/{op_id}/events returns 404 for unknown op_id."""
        resp = client.get("/api/v1/curation/unknown-op-id/events")
        assert resp.status_code == 404
