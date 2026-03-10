"""GPU VRAM monitoring service.

Queries the GPU's current VRAM usage via nvidia-smi to detect whether a
GPU-intensive operation (e.g. LoRA training) is already running.

Key functions:
  - get_gpu_vram_used_mb: query VRAM used in MB via nvidia-smi
  - is_gpu_busy: check if VRAM usage exceeds the busy threshold

Design decisions:
  - Graceful fallback: returns None/False when nvidia-smi is unavailable
  - timeout=5s prevents blocking the caller on a hung nvidia-smi
  - VRAM_BUSY_THRESHOLD_MB = 4096 (4GB): safe "something heavy is running"
    signal for RTX 5080 (16GB). Idle desktop uses ~500MB-1GB; LoRA training
    uses 8-14GB. 4GB is well above idle noise and below typical training load.
  - Full path fallback for Windows where nvidia-smi may not be on PATH
"""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)

# RTX 5080 has 16GB VRAM. LoRA training typically uses 8-14GB.
# 4GB is a conservative threshold well above idle (~500MB) and below
# the minimum training footprint.
VRAM_BUSY_THRESHOLD_MB: int = 4096

# Fallback path for Windows systems where nvidia-smi is not on PATH
_NVIDIA_SMI_FALLBACK = r"C:\Windows\System32\nvidia-smi.exe"


def get_gpu_vram_used_mb() -> int | None:
    """Query the GPU's current VRAM usage in megabytes.

    Runs ``nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits``
    and parses the first line as an integer. Falls back to the full Windows
    system path if ``nvidia-smi`` is not on the PATH.

    Returns:
        VRAM used in MB as an integer, or ``None`` if the query fails for any
        reason (nvidia-smi not found, timeout, parse error, non-NVIDIA GPU).
    """
    query_args = [
        "--query-gpu=memory.used",
        "--format=csv,noheader,nounits",
    ]

    for cmd in ["nvidia-smi", _NVIDIA_SMI_FALLBACK]:
        try:
            result = subprocess.run(
                [cmd] + query_args,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                continue
            raw = result.stdout.strip().splitlines()
            if not raw:
                continue
            return int(raw[0].strip())
        except FileNotFoundError:
            # nvidia-smi not at this path — try fallback
            continue
        except (ValueError, IndexError) as exc:
            logger.debug("Failed to parse nvidia-smi output: %s", exc)
            return None
        except subprocess.TimeoutExpired:
            logger.debug("nvidia-smi timed out after 5 seconds")
            return None
        except OSError as exc:
            logger.debug("nvidia-smi OS error: %s", exc)
            return None

    logger.debug("nvidia-smi not found at any candidate path")
    return None


def is_gpu_busy(threshold_mb: int = VRAM_BUSY_THRESHOLD_MB) -> bool:
    """Check whether the GPU is currently busy (running a heavy workload).

    Uses VRAM usage as a proxy for GPU activity. If VRAM cannot be queried
    (e.g. no NVIDIA GPU), returns ``False`` (assume OK to proceed).

    Args:
        threshold_mb: VRAM usage in MB above which the GPU is considered busy.
            Defaults to ``VRAM_BUSY_THRESHOLD_MB`` (4096 MB).

    Returns:
        True if GPU VRAM usage strictly exceeds ``threshold_mb``.
        False if usage is at or below the threshold, or if the check fails.
    """
    vram_used = get_gpu_vram_used_mb()
    if vram_used is None:
        return False
    return vram_used > threshold_mb
