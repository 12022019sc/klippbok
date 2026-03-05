"""Video pipeline service functions.

Extracts business logic from the video CLI handlers into a service layer,
making it accessible to the web API without subprocess/CLI coupling.

Functions are stateless module-level callables per [01-01 SVC-01].

Wraps:
- klippbok.video.probe: probe_directory for scan
- klippbok.video.validate: validate_directory for scan
- klippbok.video.scene: detect_scenes for ingest
- klippbok.video.split: split_video_at_scenes / split_video_segments for ingest
- klippbok.video.extract: extract_directory for frame extraction
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from klippbok.video.extract import extract_directory
from klippbok.video.models import ClipInfo, ScanReport
from klippbok.video.probe import probe_directory
from klippbok.video.scene import detect_scenes
from klippbok.video.split import split_video_at_scenes, split_video_segments
from klippbok.video.validate import validate_directory

logger = logging.getLogger(__name__)


def _default_video_config():
    """Return the default VideoConfig (16fps, 720p, auto frame count)."""
    from klippbok.config.data_schema import VideoConfig
    return VideoConfig(fps=16, resolution=720, frame_count="auto")


def scan_project_videos(
    project_dir: Path,
    config=None,
) -> ScanReport:
    """Scan a project directory for video clips and validate them.

    Probes all video files in the directory and validates them against the
    provided VideoConfig. Returns a ScanReport with per-clip validation results.

    Args:
        project_dir: Directory to scan for video files.
        config: VideoConfig with target specs. Uses defaults if None.

    Returns:
        ScanReport with validation results for all found clips.
    """
    if config is None:
        config = _default_video_config()

    logger.info("Scanning project directory for videos: %s", project_dir)
    metadata_list = probe_directory(project_dir)
    report = validate_directory(project_dir, config, metadata_list=metadata_list)
    logger.info(
        "Scan complete: %d clips found, %d valid",
        report.total,
        report.valid,
    )
    return report


def ingest_video(
    video_path: Path,
    output_dir: Path,
    config=None,
    threshold: float = 27.0,
    triage_segments: list[tuple[float, float]] | None = None,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> list[ClipInfo]:
    """Ingest a single video: scene detection + split + normalize.

    Extracted from `_ingest_single_video` in klippbok/video/__main__.py.
    Adds progress_callback support for SSE streaming from the API layer.

    Args:
        video_path: Path to the source video file.
        output_dir: Output directory for normalized clips.
        config: VideoConfig with target specs. Uses defaults if None.
        threshold: Scene detection sensitivity (default 27.0).
        triage_segments: If provided, skip scene detection and split at
            these (start_time, end_time) timestamps. Used for triage-filtered
            ingest where scenes are pre-identified.
        progress_callback: Optional callable(stage_label, current, total)
            called at each major stage transition. Used by the API layer to
            push SSE events without coupling this function to asyncio.

    Returns:
        List of ClipInfo for all produced clips.
    """
    if config is None:
        config = _default_video_config()

    def _emit(stage: str, current: int, total: int) -> None:
        if progress_callback is not None:
            try:
                progress_callback(stage, current, total)
            except Exception:
                logger.debug("progress_callback raised, ignoring", exc_info=True)

    if triage_segments is not None:
        # Filtered ingest: skip scene detection, use pre-identified segments
        _emit("Splitting pre-identified scenes", 0, len(triage_segments))
        logger.info(
            "Triage ingest: splitting %d pre-identified scene(s) from %s",
            len(triage_segments),
            video_path.name,
        )
        clips = split_video_segments(video_path, triage_segments, output_dir, config)
    else:
        # Normal ingest: detect scenes, then split
        _emit("Detecting scenes", 0, 1)
        logger.info("Detecting scenes in: %s (threshold=%.1f)", video_path.name, threshold)
        scenes = detect_scenes(video_path, threshold=threshold)
        _emit("Splitting scenes", 0, len(scenes) + 1)
        logger.info(
            "Found %d scene cut(s) -> %d segment(s), splitting...",
            len(scenes),
            len(scenes) + 1,
        )
        clips = split_video_at_scenes(video_path, scenes, output_dir, config)

    _emit("Complete", len(clips), len(clips))
    logger.info("Ingest complete: %d clips produced from %s", len(clips), video_path.name)
    return clips


def extract_frames(
    clips_dir: Path,
    output_dir: Path,
    frames_per_clip: int = 1,
) -> list[Path]:
    """Extract reference frames from all video clips in a directory.

    Wraps extract_directory with a simple interface for the API layer.
    Uses first_frame strategy by default.

    Args:
        clips_dir: Directory containing video clips.
        output_dir: Directory for extracted PNG reference images.
        frames_per_clip: Number of frames to extract per clip (default 1).
            Currently maps to ExtractionConfig sample_count for best_frame,
            or 1 frame for first_frame strategy.

    Returns:
        List of Paths to extracted PNG files (successful extractions only).
    """
    from klippbok.video.extract_models import ExtractionConfig, ExtractionStrategy

    # Use first_frame if frames_per_clip=1, best_frame otherwise
    if frames_per_clip == 1:
        config = ExtractionConfig(strategy=ExtractionStrategy.FIRST_FRAME)
    else:
        config = ExtractionConfig(
            strategy=ExtractionStrategy.BEST_FRAME,
            sample_count=max(frames_per_clip, 2),
        )

    logger.info(
        "Extracting frames from %s -> %s (strategy=%s)",
        clips_dir,
        output_dir,
        config.strategy.value,
    )
    report = extract_directory(clips_dir, output_dir, config)

    # Return paths of successfully extracted images
    extracted_paths = [
        r.output
        for r in report.results
        if r.success and not r.skipped and r.output is not None
    ]
    logger.info("Extraction complete: %d frames extracted", len(extracted_paths))
    return extracted_paths
