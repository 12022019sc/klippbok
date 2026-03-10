"""OneTrainer integration service.

Provides detection, subprocess launch, progress parsing, and graceful stop
for OneTrainer — an external LoRA training tool.

The subprocess pattern mirrors upscale_service.py:
- Module-level _ot_procs dict for process tracking
- Background daemon thread reads stdout line-by-line
- asyncio.Queue used as SSE event bus
- loop.call_soon_threadsafe for thread → async bridge

Key functions:
  - detect_onetrainer: find OneTrainer at configured or common paths
  - launch_onetrainer_headless: spawn training subprocess with stdout monitoring
  - launch_onetrainer_gui: open OneTrainer UI (detached, no monitoring)
  - stop_onetrainer: gracefully terminate a training subprocess
  - is_training_active: check if any training process is running
  - parse_training_output: extract epoch progress from tqdm output lines
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Module-level constants ─────────────────────────────────────────────────

# Common installation paths for OneTrainer (patchable in tests)
_ONETRAINER_COMMON_PATHS: list[Path] = [
    Path(r"C:\GenAI\Data\Packages\OneTrainer"),
    Path(r"C:\OneTrainer"),
    Path.home() / "OneTrainer",
    Path.home() / "GenAI" / "Data" / "Packages" / "OneTrainer",
]

# Error patterns to detect from OneTrainer stdout
OOM_PATTERNS: list[str] = [
    "OutOfMemoryError",
    "CUDA out of memory",
    "out of memory",
]

FILE_NOT_FOUND_PATTERNS: list[str] = [
    "No such file or directory",
    "FileNotFoundError",
]

CUDA_ERROR_PATTERNS: list[str] = [
    "CUDA error",
    "CUDA initialization",
]

# Module-level dict to track running training processes (keyed by op_id)
_ot_procs: dict[str, subprocess.Popen] = {}

# ANSI escape code pattern for stripping terminal color codes
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[mGKHFA]|\x1b\[[\d;]*[A-Za-z]|\x1b\[[\d;]*m")

# Epoch progress pattern — matches "Epoch N/M" with optional colon
_EPOCH_PATTERN = re.compile(r"Epoch:?\s+(\d+)\s*/\s*(\d+)", re.IGNORECASE)


# ── Detection ──────────────────────────────────────────────────────────────


def detect_onetrainer(configured_path: str | None = None) -> Path | None:
    """Find a OneTrainer installation at the configured path or common paths.

    Validates the installation by checking that both:
    - ``venv/Scripts/python.exe`` exists (OneTrainer uses its own venv)
    - ``scripts/train.py`` exists (the headless training entry point)

    Args:
        configured_path: Optional explicit path to check first. Takes priority
            over the module-level ``_ONETRAINER_COMMON_PATHS`` list.

    Returns:
        Root directory of the OneTrainer installation as a ``Path``, or ``None``
        if no valid installation is found.
    """
    candidates: list[Path] = []
    if configured_path:
        candidates.append(Path(configured_path))
    candidates.extend(_ONETRAINER_COMMON_PATHS)

    for candidate in candidates:
        if not candidate:
            continue
        python_exe = candidate / "venv" / "Scripts" / "python.exe"
        train_script = candidate / "scripts" / "train.py"
        if python_exe.is_file() and train_script.is_file():
            logger.debug("Found OneTrainer installation at: %s", candidate)
            return candidate

    logger.debug("OneTrainer not found at any of: %s", candidates)
    return None


# ── Subprocess launch ──────────────────────────────────────────────────────


def launch_onetrainer_headless(
    ot_root: Path,
    preset_path: Path,
    queue: asyncio.Queue,
    op_id: str,
) -> None:
    """Launch OneTrainer headless training as a subprocess.

    Spawns OneTrainer's ``scripts/train.py`` using the OneTrainer venv Python
    with the given preset config. Starts a background daemon thread to read
    stdout and push progress/error/done events onto the asyncio queue.

    Args:
        ot_root: Root directory of the OneTrainer installation.
        preset_path: Path to the ``.json`` training preset/config file.
        queue: asyncio.Queue to receive training progress events.
        op_id: Unique operation identifier for event routing.

    Raises:
        RuntimeError: If the OneTrainer venv Python executable is not found.
        OSError: If the subprocess fails to start.
    """
    python_exe = ot_root / "venv" / "Scripts" / "python.exe"
    if not python_exe.is_file():
        raise RuntimeError(
            f"OneTrainer venv Python not found at: {python_exe}. "
            "Ensure OneTrainer is properly installed with its venv."
        )

    train_script = ot_root / "scripts" / "train.py"
    cmd = [
        str(python_exe),
        str(train_script),
        "--config-path",
        str(preset_path),
    ]

    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        cwd=str(ot_root),
        encoding="utf-8",
        errors="replace",
    )
    _ot_procs[op_id] = proc

    loop = asyncio.get_event_loop()
    reader_thread = threading.Thread(
        target=_ot_stdout_reader,
        args=(proc, queue, loop, op_id),
        daemon=True,
        name=f"ot-reader-{op_id}",
    )
    reader_thread.start()

    logger.info(
        "Started OneTrainer headless subprocess (op_id=%s, pid=%d)",
        op_id,
        proc.pid,
    )


def launch_onetrainer_gui(ot_root: Path, preset_path: Path | None = None) -> None:
    """Launch the OneTrainer GUI (detached, no stdout monitoring).

    Spawns ``scripts/train_ui.py`` using the OneTrainer venv Python. The
    process is detached — klippbok does not monitor or track it.

    Args:
        ot_root: Root directory of the OneTrainer installation.
        preset_path: Optional path to a preset config to pre-load in the UI.
    """
    python_exe = ot_root / "venv" / "Scripts" / "python.exe"
    train_ui_script = ot_root / "scripts" / "train_ui.py"

    cmd = [str(python_exe), str(train_ui_script)]
    if preset_path is not None:
        cmd += ["--config-path", str(preset_path)]

    # Detached process — no stdout capture, no tracking
    subprocess.Popen(
        cmd,
        cwd=str(ot_root),
        close_fds=True,
    )
    logger.info("Launched OneTrainer GUI (detached, ot_root=%s)", ot_root)


# ── Process management ─────────────────────────────────────────────────────


def stop_onetrainer(op_id: str) -> bool:
    """Gracefully terminate a running OneTrainer training subprocess.

    Sends SIGTERM (terminate) to the process. The process is expected to
    clean up and exit. For forceful kill, callers may follow up with
    ``_ot_procs[op_id].kill()`` if needed.

    Args:
        op_id: The operation identifier of the training run to stop.

    Returns:
        True if the process was found and termination was requested.
        False if no process with the given op_id is tracked.
    """
    proc = _ot_procs.get(op_id)
    if proc is None:
        logger.warning("stop_onetrainer: no process found for op_id=%s", op_id)
        return False
    try:
        proc.terminate()
        logger.info("Sent SIGTERM to OneTrainer process (op_id=%s, pid=%d)", op_id, proc.pid)
    except OSError as exc:
        logger.warning("Failed to terminate OneTrainer process %s: %s", op_id, exc)
    return True


def is_training_active() -> bool:
    """Check whether any OneTrainer training subprocess is currently running.

    Returns:
        True if at least one tracked process has not yet exited (poll() is None).
        False if no processes are tracked or all have exited.
    """
    return any(proc.poll() is None for proc in _ot_procs.values())


# ── Progress parsing ───────────────────────────────────────────────────────


def parse_training_output(line: str) -> dict | None:
    """Extract epoch progress from a OneTrainer stdout line.

    Handles tqdm-style output with ANSI escape codes. Looks for the
    ``Epoch N/M`` pattern that OneTrainer emits at the start of each epoch.

    Args:
        line: A single line of stdout from the OneTrainer process.

    Returns:
        A dict with ``{"epoch": N, "total_epochs": M}`` if the epoch pattern
        is found, or ``None`` if the line does not contain epoch information.
    """
    # Strip ANSI escape codes before pattern matching
    clean = _ANSI_ESCAPE.sub("", line)
    match = _EPOCH_PATTERN.search(clean)
    if match:
        return {
            "epoch": int(match.group(1)),
            "total_epochs": int(match.group(2)),
        }
    return None


# ── Background stdout reader ───────────────────────────────────────────────


def _ot_stdout_reader(
    proc: subprocess.Popen,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    op_id: str,
) -> None:
    """Background thread: read OneTrainer stdout and push events to the queue.

    Runs in a daemon thread spawned by ``launch_onetrainer_headless``. Reads
    stdout line-by-line, parses epoch progress, detects error patterns, and
    puts typed event dicts onto the asyncio queue via ``call_soon_threadsafe``.

    Event types pushed:
    - ``training_progress``: epoch/step update
    - ``training_error``: OOM, CUDA, or file-not-found error detected
    - ``training_done``: process exited (with return code)

    Args:
        proc: The running OneTrainer subprocess.
        queue: asyncio.Queue to receive event dicts.
        loop: The running event loop for thread-safe queue puts.
        op_id: Operation identifier for event payloads.
    """
    def _put(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    try:
        for raw_line in iter(proc.stdout.readline, ""):
            line = raw_line.rstrip()
            if not line:
                continue
            logger.debug("onetrainer stdout [%s]: %s", op_id, line)

            # Check for error patterns first
            is_oom = any(pat in line for pat in OOM_PATTERNS)
            is_missing = any(pat in line for pat in FILE_NOT_FOUND_PATTERNS)
            is_cuda_err = any(pat in line for pat in CUDA_ERROR_PATTERNS)

            if is_oom or is_missing or is_cuda_err:
                if is_oom:
                    error_type = "oom"
                elif is_missing:
                    error_type = "file_not_found"
                else:
                    error_type = "cuda_error"
                _put({
                    "type": "training_error",
                    "op_id": op_id,
                    "error_type": error_type,
                    "message": line,
                })
                continue

            # Check for epoch progress
            progress = parse_training_output(line)
            if progress:
                _put({
                    "type": "training_progress",
                    "op_id": op_id,
                    "epoch": progress["epoch"],
                    "total_epochs": progress["total_epochs"],
                    "message": line,
                })

    except Exception as exc:
        logger.error("OneTrainer stdout reader error (op_id=%s): %s", op_id, exc)

    # Wait for process to fully exit
    proc.wait()
    return_code = proc.returncode
    _ot_procs.pop(op_id, None)

    _put({
        "type": "training_done",
        "op_id": op_id,
        "return_code": return_code,
        "message": "Training complete." if return_code == 0 else f"Training exited with code {return_code}.",
    })
    # Sentinel to stop SSE generator
    _put(None)
