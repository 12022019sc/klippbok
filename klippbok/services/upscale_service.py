"""Upscale subprocess management service.

Provides detection and launch helpers for external upscaler tools:
- SeedVR2 (diffusion-based, high quality, requires its own venv)
- NMKD-Siax (ESRGAN via realesrgan-ncnn-vulkan binary, fast)

The subprocess pattern follows the same approach as FFmpeg integration:
detect the tool at common paths, fall back to env var override, launch
as Popen with line-by-line stdout parsing for progress.

Pattern reference: klippbok/api/routers/import_.py SSE pattern.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


# ── SeedVR2 detection ──────────────────────────────────────────────────────

def _build_seedvr2_paths() -> list[Path]:
    """Build the list of candidate SeedVR2 paths to check."""
    candidates: list[Path] = [
        Path(r"C:\GenAI\Tools\SeedVR2"),
        Path.home() / "GenAI" / "Tools" / "SeedVR2",
    ]
    env_path = os.environ.get("SEEDVR2_PATH")
    if env_path:
        candidates.append(Path(env_path))
    return candidates


# Module-level list (can be patched in tests)
_SEEDVR2_COMMON_PATHS: list[Path] = _build_seedvr2_paths()


def detect_seedvr2() -> Path | None:
    """Find a SeedVR2 installation at known paths.

    Checks each candidate path for the presence of both:
    - venv/Scripts/python.exe (Windows) or venv/bin/python (Linux/macOS)
    - inference_cli.py (primary) or batch_upscale.py (fallback)

    Also checks the SEEDVR2_PATH environment variable.

    Returns:
        Root directory of the SeedVR2 installation, or None if not found.
    """
    for candidate in _SEEDVR2_COMMON_PATHS:
        if not candidate:
            continue
        # Support both Windows (Scripts) and Linux/macOS (bin) venv layouts
        python_candidates = [
            candidate / "venv" / "Scripts" / "python.exe",  # Windows
            candidate / "venv" / "bin" / "python",           # Linux/macOS
        ]
        # Prefer inference_cli.py (direct invocation avoids subprocess-in-subprocess)
        cli_script = candidate / "inference_cli.py"
        batch_script = candidate / "batch_upscale.py"

        has_python = any(p.is_file() for p in python_candidates)
        if has_python and (cli_script.is_file() or batch_script.is_file()):
            logger.debug("Found SeedVR2 installation at: %s", candidate)
            return candidate

    logger.debug("SeedVR2 not found at any of: %s", _SEEDVR2_COMMON_PATHS)
    return None


def get_seedvr2_python(seedvr2_root: Path) -> Path | None:
    """Get the Python executable path within the SeedVR2 venv.

    Args:
        seedvr2_root: Root directory of the SeedVR2 installation.

    Returns:
        Path to the Python executable, or None if not found.
    """
    windows_python = seedvr2_root / "venv" / "Scripts" / "python.exe"
    if windows_python.is_file():
        return windows_python
    linux_python = seedvr2_root / "venv" / "bin" / "python"
    if linux_python.is_file():
        return linux_python
    return None


# ── NMKD-Siax detection ───────────────────────────────────────────────────

def _build_nmkd_paths() -> list[Path]:
    """Build the list of candidate NMKD-Siax / realesrgan-ncnn-vulkan paths."""
    candidates: list[Path] = [
        Path(r"C:\GenAI\Tools\realesrgan-ncnn-vulkan\realesrgan-ncnn-vulkan.exe"),
        Path.home() / "GenAI" / "Tools" / "realesrgan-ncnn-vulkan" / "realesrgan-ncnn-vulkan.exe",
        Path("/usr/local/bin/realesrgan-ncnn-vulkan"),
        Path("/usr/bin/realesrgan-ncnn-vulkan"),
    ]
    env_path = os.environ.get("NMKD_SIAX_PATH")
    if env_path:
        candidates.append(Path(env_path))
    return candidates


# Module-level list (can be patched in tests)
_NMKD_SIAX_COMMON_PATHS: list[Path] = _build_nmkd_paths()


def detect_nmkd_siax() -> Path | None:
    """Find the realesrgan-ncnn-vulkan binary for NMKD-Siax upscaling.

    Checks common installation paths and the NMKD_SIAX_PATH environment
    variable for the realesrgan-ncnn-vulkan binary.

    Returns:
        Path to the binary, or None if not found.
    """
    for candidate in _NMKD_SIAX_COMMON_PATHS:
        if not candidate:
            continue
        if candidate.is_file():
            logger.debug("Found NMKD-Siax binary at: %s", candidate)
            return candidate

    logger.debug("NMKD-Siax not found at any of: %s", _NMKD_SIAX_COMMON_PATHS)
    return None


# ── Upscale subprocess ────────────────────────────────────────────────────

# Module-level dict to store subprocess references for cancellation.
# Keyed by operation ID. Cleaned up when process exits.
_procs: dict[str, subprocess.Popen] = {}

# Mapping from staged filename → original absolute path, keyed by op_id.
# Used by the apply endpoint to copy upscaled files back over originals.
_mappings: dict[str, dict[str, Path]] = {}


def get_mapping(op_id: str) -> dict[str, Path] | None:
    """Return the staged-name → original-path mapping for an operation."""
    return _mappings.get(op_id)


def clear_mapping(op_id: str) -> None:
    """Remove the mapping for a completed/cancelled operation."""
    _mappings.pop(op_id, None)


def cancel_upscale(op_id: str) -> bool:
    """Kill a running upscale subprocess.

    Args:
        op_id: Operation UUID to cancel.

    Returns:
        True if the process was found and killed, False if not found.
    """
    proc = _procs.get(op_id)
    if proc is None:
        return False
    try:
        proc.kill()
        logger.info("Killed upscale subprocess for operation %s (pid=%d)", op_id, proc.pid)
    except OSError as exc:
        logger.warning("Failed to kill upscale process %s: %s", op_id, exc)
    return True


def _stdout_reader(
    proc: subprocess.Popen,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    op_id: str,
    total: int,
    upscaler: str,
    staging_dir: Path | None = None,
) -> None:
    """Read upscaler stdout in a background thread and push progress to asyncio queue.

    For SeedVR2: matches "Processing file N/M" lines from inference_cli.py.
    For other upscalers: uses generic "N/M" pattern matching.

    Args:
        proc: Running subprocess.
        queue: asyncio.Queue to push UpscaleProgress events onto.
        loop: The event loop to schedule queue.put coroutines on.
        op_id: Operation UUID for event payloads.
        total: Total number of images (the ground truth for progress).
        upscaler: Upscaler backend name ("seedvr2" or "nmkd_siax").
        staging_dir: Temp input dir to clean up after process exits.
    """
    from klippbok.api.models import UpscaleProgress

    # SeedVR2: only match "Processing file N/M" (ignore tqdm batch noise)
    file_pattern = re.compile(r"Processing file\s+(\d+)\s*/\s*(\d+)", re.IGNORECASE)
    # NMKD / other: generic "N/M" pattern
    generic_pattern = re.compile(r"(\d+)\s*/\s*(\d+)")

    try:
        for line in iter(proc.stdout.readline, ""):
            line = line.rstrip()
            if not line:
                continue
            logger.debug("upscaler stdout: %s", line)

            if upscaler == "seedvr2":
                # Only match the specific "Processing file" line
                file_match = file_pattern.search(line)
                if file_match:
                    current = int(file_match.group(1))
                    event = UpscaleProgress(
                        operation_id=op_id,
                        current=current,
                        total=total,
                        message=f"Upscaling {current}/{total} images...",
                        status="running",
                    )
                    asyncio.run_coroutine_threadsafe(queue.put(event), loop)
            else:
                # Generic fallback for NMKD-Siax etc.
                match = generic_pattern.search(line)
                if match:
                    current = int(match.group(1))
                    file_total = int(match.group(2))
                    event = UpscaleProgress(
                        operation_id=op_id,
                        current=current,
                        total=file_total,
                        message=f"Upscaling {current}/{file_total} images...",
                        status="running",
                    )
                    asyncio.run_coroutine_threadsafe(queue.put(event), loop)
    except Exception as exc:
        logger.error("upscaler stdout reader failed: %s", exc)

    # Wait for process completion
    proc.wait()
    return_code = proc.returncode

    # Clean up proc reference
    _procs.pop(op_id, None)

    if return_code == 0:
        final_event = UpscaleProgress(
            operation_id=op_id,
            current=total,
            total=total,
            message="Upscaling complete.",
            status="complete",
        )
    elif return_code < 0 or return_code == 1:
        # Negative return code = killed by signal (Unix), code 1 on Windows kill
        final_event = UpscaleProgress(
            operation_id=op_id,
            current=0,
            total=total,
            message="Upscaling cancelled.",
            status="error",
        )
    else:
        final_event = UpscaleProgress(
            operation_id=op_id,
            current=0,
            total=total,
            message=f"Upscaler exited with code {return_code}.",
            status="error",
        )

    asyncio.run_coroutine_threadsafe(queue.put(final_event), loop)
    # Sentinel to signal SSE generator to stop
    asyncio.run_coroutine_threadsafe(queue.put(None), loop)

    # Clean up staging input dir (selected images were copied here)
    if staging_dir and staging_dir.exists():
        import shutil
        shutil.rmtree(str(staging_dir), ignore_errors=True)


async def start_upscale(
    image_paths: list[Path],
    output_dir: Path,
    upscaler: str,
    scale_factor: int,
    queue: asyncio.Queue,
    op_id: str,
    project_dir: Path | None = None,
) -> None:
    """Start an upscale subprocess and push progress events to the queue.

    Spawns the appropriate upscaler tool as a subprocess and reads its
    stdout in a background thread. Progress events are pushed to the
    asyncio queue for consumption by the SSE generator.

    Args:
        image_paths: List of source image paths to upscale.
        output_dir: Directory where upscaled images should be saved.
        upscaler: Upscaler backend name: "seedvr2" or "nmkd_siax".
        scale_factor: Upscale multiplier (e.g. 2 for 2x).
        queue: asyncio.Queue to receive UpscaleProgress events.
        op_id: Operation UUID for event payloads.
        project_dir: Project directory for staging within .klippbok/.

    Raises:
        RuntimeError: If the requested upscaler is not installed or configured.
    """
    from klippbok.api.models import UpscaleProgress
    import shutil

    total = len(image_paths)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create staging dir with only the selected images so the upscaler
    # doesn't process the entire source directory.
    # Keep staging inside the project's .klippbok/ dir.
    if project_dir is not None:
        staging_dir = project_dir / ".klippbok" / "staging" / f"upscale-{op_id}"
    else:
        import tempfile
        staging_dir = Path(tempfile.mkdtemp(prefix="klippbok-upscale-input-"))
    staging_dir.mkdir(parents=True, exist_ok=True)
    name_mapping: dict[str, Path] = {}  # staged_name -> original_abs_path
    used_names: set[str] = set()
    for img_path in image_paths:
        name = img_path.name
        if name in used_names:
            stem, suffix = img_path.stem, img_path.suffix
            counter = 2
            while name in used_names:
                name = f"{stem}_{counter}{suffix}"
                counter += 1
        used_names.add(name)
        shutil.copy2(str(img_path), str(staging_dir / name))
        name_mapping[name] = img_path.resolve()

    _mappings[op_id] = name_mapping

    if upscaler == "seedvr2":
        seedvr2_root = detect_seedvr2()
        if seedvr2_root is None:
            err_event = UpscaleProgress(
                operation_id=op_id,
                current=0,
                total=total,
                message=(
                    "SeedVR2 not found. Install it at C:\\GenAI\\Tools\\SeedVR2 "
                    "or set the SEEDVR2_PATH environment variable."
                ),
                status="error",
            )
            await queue.put(err_event)
            await queue.put(None)
            return

        python_exe = get_seedvr2_python(seedvr2_root)
        if python_exe is None:
            err_event = UpscaleProgress(
                operation_id=op_id,
                current=0,
                total=total,
                message="SeedVR2 venv Python executable not found.",
                status="error",
            )
            await queue.put(err_event)
            await queue.put(None)
            return

        # Call inference_cli.py directly instead of batch_upscale.py to avoid
        # subprocess-in-subprocess fragility and give us direct stdout control.
        cli_script = seedvr2_root / "inference_cli.py"
        input_dir = staging_dir

        # Map scale factor to resolution (matching batch_upscale.py SCALE_PRESETS)
        scale_to_resolution = {2: 1440, 4: 2160, 8: 4320}
        resolution = scale_to_resolution.get(scale_factor, 1440)

        cmd = [
            str(python_exe),
            str(cli_script),
            str(input_dir),
            "--output", str(output_dir),
            "--dit_model", "seedvr2_ema_3b_fp8_e4m3fn.safetensors",
            "--resolution", str(resolution),
            "--max_resolution", str(resolution * 2),
            "--batch_size", "1",
            "--color_correction", "lab",
            "--dit_offload_device", "cpu",
            "--vae_offload_device", "cpu",
            "--cache_dit", "--cache_vae",
        ]

        env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                cwd=str(seedvr2_root),
                encoding="utf-8",
                errors="replace",
            )
        except Exception as exc:
            err_event = UpscaleProgress(
                operation_id=op_id,
                current=0,
                total=total,
                message=f"Failed to start SeedVR2: {exc}",
                status="error",
            )
            await queue.put(err_event)
            await queue.put(None)
            return

    elif upscaler == "nmkd_siax":
        binary = detect_nmkd_siax()
        if binary is None:
            err_event = UpscaleProgress(
                operation_id=op_id,
                current=0,
                total=total,
                message=(
                    "NMKD-Siax (realesrgan-ncnn-vulkan) not found. "
                    "Install it and set NMKD_SIAX_PATH environment variable."
                ),
                status="error",
            )
            await queue.put(err_event)
            await queue.put(None)
            return

        # realesrgan-ncnn-vulkan processes one image at a time;
        # for batch, spawn one subprocess per image
        input_dir = staging_dir
        cmd = [
            str(binary),
            "-i", str(input_dir),
            "-o", str(output_dir),
            "-n", "4x_NMKD-Siax_200k",
            "-s", str(scale_factor),
        ]

        env = {**os.environ}

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )
        except Exception as exc:
            err_event = UpscaleProgress(
                operation_id=op_id,
                current=0,
                total=total,
                message=f"Failed to start NMKD-Siax: {exc}",
                status="error",
            )
            await queue.put(err_event)
            await queue.put(None)
            return
    else:
        err_event = UpscaleProgress(
            operation_id=op_id,
            current=0,
            total=total,
            message=f"Unknown upscaler: {upscaler!r}. Use 'seedvr2' or 'nmkd_siax'.",
            status="error",
        )
        await queue.put(err_event)
        await queue.put(None)
        return

    # Store proc reference for cancellation support
    _procs[op_id] = proc

    # Start background thread to read stdout without blocking the event loop
    loop = asyncio.get_event_loop()
    reader_thread = threading.Thread(
        target=_stdout_reader,
        args=(proc, queue, loop, op_id, total, upscaler, staging_dir),
        daemon=True,
        name=f"upscale-reader-{op_id}",
    )
    reader_thread.start()

    logger.info(
        "Started %s upscale subprocess (op_id=%s, pid=%d, %d images)",
        upscaler, op_id, proc.pid, total,
    )
