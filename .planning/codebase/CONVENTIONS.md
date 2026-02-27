# Coding Conventions

**Analysis Date:** 2026-02-27

## Naming Patterns

**Files:**
- All lowercase with underscores: `config_loader.py`, `image_quality.py`, `data_schema.py`
- Module grouping by domain: `caption/`, `dataset/`, `video/`, `config/`, `triage/`
- Test files: `test_<module>.py` (mirrors source module name)
- Internal/private functions use leading underscore: `_resolve_paths()`, `_check_ffmpeg()`

**Functions:**
- snake_case for all function names
- Private functions prefixed with single underscore: `_create_backend()`, `_find_video_files()`
- Public API functions exported in `__init__.py` files for convenience

**Variables:**
- snake_case: `video_path`, `frame_count`, `api_key`
- Single-letter variables only in comprehensions/tight loops
- Descriptive names: `base_dir` not `bd`, `is_valid` not `valid`

**Types & Classes:**
- PascalCase for all classes: `VLMBackend`, `SamplePair`, `ValidationIssue`, `CaptionConfig`
- Enums inherit from `str, Enum` for YAML serialization: `class StructureType(str, Enum)`
- Exception classes: `KlippbokConfigError`, `DatasetValidationError`, `FFmpegNotFoundError`

## Code Style

**Formatting:**
- No explicit formatter configured (ruff check available but no Black)
- Implicit style: 4-space indentation, max line length not enforced but practical
- Type hints on all functions (required in CLAUDE.md)

**Imports:**
- Future annotations always first: `from __future__ import annotations`
- Standard library imports grouped, then third-party, then local
- Sorted within groups alphabetically
- Example pattern from `klippbok/caption/captioner.py`:
  ```python
  from __future__ import annotations

  import time
  from pathlib import Path

  from klippbok.caption.base import VLMBackend
  from klippbok.caption.models import AuditResult, CaptionConfig, CaptionResult
  ```

**Linting:**
- No .eslintrc or .flake8 configured in repo
- Project allows what's written in CLAUDE.md: strict quality gates
- Type hints are expected throughout

## Type Hints

**Pattern:**
- Every function MUST have return type: `def load_data_config(path: str | Path) -> KlippbokDataConfig`
- Union types use modern syntax `str | None` (not `Optional[str]`)
- `list[Type]` and `dict[Key, Value]` (lowercase, not `List` or `Dict`)
- Pydantic models use `ConfigDict(frozen=True)` for immutability

**Example from `klippbok/dataset/models.py`:**
```python
def __init__(
    self,
    api_key: str | None = None,
    model: str = "gemini-2.5-flash",
    timeout: int = 120,
) -> None:
```

## Error Handling

**Pattern - Always explicit, logged, re-raised:**
```python
try:
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=10)
except (FileNotFoundError, subprocess.TimeoutExpired):
    raise FFmpegNotFoundError("ffmpeg")
```

**Custom Exceptions:**
- Inherit from domain-specific base: `KlippbokVideoError`, `KlippbokDatasetError`, `KlippbokConfigError`
- Include context in `__init__`: path, detail, helpful message
- Constructor formats user-facing message with solution hint
- Examples in `klippbok/video/errors.py`:
  - `FFmpegNotFoundError` → "Install with: winget install ffmpeg"
  - `ProbeError` → "Failed to probe '...': {detail}"
  - `ExtractionError` → "Failed to extract frame from '...': {detail}"

**Never swallow errors silently** — CLAUDE.md requirement
- Always catch at appropriate boundary
- Add context before re-raising
- If catching Exception broadly, log/transform before raising

## Logging

**Framework:** `print()` for user-facing output (no logging module imported)
- Command-line tools use print for status, progress, results
- Progress indicators: `print(f"  [{i}/{total}] {filename}")`
- Error output goes to print as well (captured in same stream)
- Examples from `klippbok/caption/captioner.py`:
  ```python
  print(f"No video files found in {directory}")
  print(f"  [{i}/{total}] {video_path.name} - skipped (caption exists)")
  print(f"           OK {elapsed:.1f}s - {len(caption)} chars")
  ```

**No imports of `logging` module** — project uses print-based output for CLI transparency

## Comments & Docstrings

**Module docstrings:**
- Required at top of every file
- Describe the module's purpose and usage
- Include example usage with code blocks
- Format: triple-quoted string with text + optional code example

**Example from `klippbok/config/loader.py`:**
```python
"""Config loader for Klippbok data configs.

Handles YAML loading, path resolution, backwards compatibility, and
human-readable error formatting. This is the main entry point for
consuming a Klippbok data config.

Usage::

    from klippbok.config import load_data_config
    config = load_data_config("path/to/klippbok_data.yaml")
"""
```

**Function docstrings:**
- Required for all public functions
- First line: brief one-liner
- Args/Returns/Raises sections (Google style implicit)
- Example from `klippbok/video/extract.py`:
  ```python
  def extract_first_frame(
      video_path: str | Path,
      output_path: str | Path,
  ) -> ExtractionResult:
      """Extract frame 0 from a video as a lossless PNG.

      The first frame is the standard reference image for I2V training.
      This is deterministic, fast (reads only the first frame), and
      matches how I2V models are typically conditioned.

      Args:
          video_path: Path to the source video file.
          output_path: Path for the output PNG file.

      Returns:
          ExtractionResult with metadata about what was extracted.

      Raises:
          FFmpegNotFoundError: if ffmpeg is not in PATH.
          ExtractionError: if ffmpeg fails to extract the frame.
      """
  ```

**Inline comments:**
- Used sparingly — code should be self-documenting
- Line comments above code, not at end of line
- Used for context about WHY, not WHAT
- Example: `# Backwards compatibility: if user put path in dataset.path`

## Function Design

**Size limits:** Per CLAUDE.md — no function > 50 lines
- Most functions in codebase are 20-40 lines
- Larger operations split into private helpers with underscore prefix
- Example: `_check_ffmpeg()`, `_run_ffmpeg()`, `_resolve_paths()` are helper functions

**Parameters:**
- Use `str | Path` for filesystem paths (accept both, convert to Path early)
- Use Pydantic models for configuration (not scattered **kwargs)
- Optional parameters come after required ones
- Example from `klippbok/video/extract.py`:
  ```python
  def extract_frame_at(
      video_path: str | Path,
      output_path: str | Path,
      frame_number: int | None = None,
      timestamp: float | None = None,
  ) -> ExtractionResult:
  ```

**Return Values:**
- Always explicit return type in signature
- Return Pydantic models for structured data (not dicts)
- Return specialized Result objects: `ExtractionResult`, `CaptionResult`, `ScanReport`
- Return immutable models (`frozen=True`) for read-only data

## Module Design

**Exports:**
- Public API exported from `__init__.py`
- Example from `klippbok/caption/__init__.py`:
  ```python
  from klippbok.caption.captioner import audit_captions, caption_clips
  from klippbok.caption.models import AuditResult, CaptionConfig, CaptionResult
  from klippbok.caption.scoring import ComputedScore, ScoreCategory
  ```

**Barrel Files:**
- Each subpackage has `__init__.py` that re-exports key classes/functions
- Allows `from klippbok.caption import caption_clips` instead of long internal path
- Keeps public API stable even if internal modules reorganized

**File Organization:**
- `models.py` - Pydantic data classes
- `errors.py` - Custom exception classes
- `<feature>.py` - Core logic/functions
- `base.py` - Abstract base classes (e.g., `VLMBackend`)
- `__init__.py` - Public API exports
- `__main__.py` - CLI entry point

---

*Convention analysis: 2026-02-27*
