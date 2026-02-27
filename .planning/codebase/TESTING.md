# Testing Patterns

**Analysis Date:** 2026-02-27

## Test Framework

**Runner:**
- pytest 7.0+
- Config: `pyproject.toml` with `[tool.pytest.ini_options]`

**Assertion Library:**
- pytest's built-in assertions (no special library)

**Run Commands:**
```bash
pytest                    # Run all tests in tests/
pytest -x                 # Stop on first failure
pytest -k "pattern"       # Run matching tests only
pytest tests/test_captioner.py::TestPrependAnchor::test_prepend_when_absent  # Single test
```

## Test File Organization

**Location:**
- Separate directory: `tests/` (not co-located with source)
- Tests mirror source module structure but are separate

**Naming:**
- Test file: `test_<module>.py` where `<module>` matches source module name
- Test class: `Test<Feature>` (PascalCase)
- Test method: `test_<specific_case>` (snake_case, descriptive)
- Example:
  - Source: `klippbok/caption/captioner.py`
  - Test: `tests/test_captioner.py`
  - Class: `class TestPrependAnchor`
  - Method: `def test_prepend_when_absent`

**Structure:**
```
tests/
├── conftest.py                      # Shared fixtures, markers, PATH setup
├── test_captioner.py                # Tests for caption/captioner.py
├── test_caption_models.py           # Tests for caption/models.py
├── test_dataset_validate.py         # Tests for dataset/validate.py
└── test_data_config.py              # Tests for config/data_schema.py
```

## Conftest Patterns

**Location:** `tests/conftest.py`

**Key Fixtures:**
- `tiny_video(tmp_path: Path) -> Path` - 16fps, 320x240, 17 frames, H.264
- `tiny_video_30fps(tmp_path: Path) -> Path` - 30fps variant (wrong fps for training)
- `tiny_video_720p(tmp_path: Path) -> Path` - 1280x720 resolution
- `tiny_video_18frames(tmp_path: Path) -> Path` - Invalid frame count (18, not 4n+1)
- `two_scene_video(tmp_path: Path) -> Path` - Two scenes with abrupt color change

**Custom Markers:**
- `@requires_ffmpeg` - Skip if ffmpeg/ffprobe not in PATH
- `@requires_scenedetect` - Skip if PySceneDetect not installed

**PATH Setup:**
- Conftest automatically detects WinGet-installed ffmpeg
- No shell restart needed after install

**Example from `tests/conftest.py`:**
```python
@pytest.fixture
def tiny_video(tmp_path: Path) -> Path:
    """Create a tiny test video: 16fps, 320x240, 17 frames (~1s), H.264.

    Uses ffmpeg's testsrc2 filter to generate colored frames.
    Skipped automatically if ffmpeg is not available.

    Returns:
        Path to the generated .mp4 file.
    """
    if not _has_ffmpeg():
        pytest.skip("ffmpeg not available")

    output = tmp_path / "test_clip.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "testsrc2=size=320x240:rate=16:duration=1.0625",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-frames:v", "17",
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0:
        pytest.skip(f"Failed to create test video: ...")

    return output
```

## Test Structure

**Class-based organization:**
- One test class per function/feature (not per module)
- Example: `class TestPrependAnchor` for function `_prepend_anchor()`
- Organizes related tests into logical groups

**Test pattern from `tests/test_captioner.py`:**
```python
class TestPrependAnchor:
    """Tests for _prepend_anchor() — pure function, no I/O."""

    def test_prepend_when_absent(self) -> None:
        """Adds anchor word with comma when not present."""
        result = _prepend_anchor("A girl walks through a forest", "Luna")
        assert result == "Luna, a girl walks through a forest"

    def test_no_prepend_when_present(self) -> None:
        """Does not duplicate anchor word if already at start."""
        result = _prepend_anchor("Luna is walking through a forest", "Luna")
        assert result == "Luna is walking through a forest"

    def test_case_insensitive(self) -> None:
        """Anchor detection is case-insensitive."""
        result = _prepend_anchor("luna stands on a rooftop", "Luna")
        assert result == "luna stands on a rooftop"
```

**Setup/Teardown:**
- No explicit setup/teardown patterns
- Use fixtures for setup (preferable to `setUp()`/`tearDown()`)
- Fixtures automatically handle cleanup via pytest's scope management
- `tmp_path` fixture provides isolated temporary directories

**Assertions:**
- Direct pytest assertions: `assert result == expected`
- Use context for clarity: `assert any(i.code == IssueCode.CAPTION_EMPTY for i in result.issues)`
- Exception assertions: `with pytest.raises(ValueError, match="..."):`

## Parametrized Tests

**Pattern:**
```python
@pytest.mark.parametrize("method", ["lanczos", "bicubic", "bilinear", "area"])
def test_valid_downscale_method(self, method: str) -> None:
    """Each downscale method is valid."""
    config = KlippbokDataConfig(
        datasets=[{"path": "."}],
        video=VideoConfig(downscale_method=method)
    )
    assert config.video.downscale_method == method
```

**Usage:**
- Table-driven tests for enumerating valid values
- Found in `tests/test_data_config.py`
- Reduces boilerplate for testing multiple similar cases

## Mocking

**Framework:** `unittest.mock` (standard library)

**Pattern from `tests/test_captioner.py`:**
```python
class MockBackend(VLMBackend):
    """Fake VLM backend that returns predictable captions.

    Records all calls for assertion. Can be configured to fail on
    specific files.
    """

    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.calls: list[dict] = []
        self.fail_on = fail_on or set()

    def caption_video(self, path: Path, prompt: str) -> str:
        self.calls.append({"type": "video", "path": path, "prompt": prompt})
        if path.name in self.fail_on:
            raise RuntimeError(f"Mock failure on {path.name}")
        return f"Caption for {path.stem}"

    def caption_image(self, path: Path, prompt: str) -> str:
        self.calls.append({"type": "image", "path": path, "prompt": prompt})
        if path.name in self.fail_on:
            raise RuntimeError(f"Mock failure on {path.name}")
        return f"Image caption for {path.stem}"
```

**What to Mock:**
- External APIs (Gemini, Replicate, OpenAI)
- Slow operations (ffmpeg if possible — use small test videos instead)
- File system (sparingly — use `tmp_path` fixture instead)
- Random or time-dependent code

**What NOT to Mock:**
- Core business logic (validate, discover, organize)
- Data models (Pydantic models behave as unit-tested)
- Pure functions (test directly)
- Filesystem operations in integration tests (use real tmp files)

## Test Types

**Unit Tests (Dominant):**
- Pure functions: `_prepend_anchor()`, `_resolve_one()`, prompt formatting
- Small scope, no external dependencies
- Fast execution (under 1s each typically)
- High coverage: most test files are unit tests
- Example: `tests/test_caption_prompts.py` - all pure function tests

**Integration Tests:**
- Validation against real or fake dataset structures
- Create temporary files via `tmp_path` fixture
- Test relationships between modules
- Example: `tests/test_dataset_validate.py` — uses helper functions:
  ```python
  def _touch(path: Path, content: bytes = b"") -> Path:
      """Create a file with content."""
      path.parent.mkdir(parents=True, exist_ok=True)
      path.write_bytes(content)
      return path

  def _make_textured_image(path: Path, size: int = 64) -> Path:
      """Create an image with enough texture to not be blank."""
      rng = np.random.RandomState(42)
      img = rng.randint(0, 256, (size, size, 3), dtype=np.uint8)
      return _save_image(path, img)
  ```

**E2E Tests:**
- Not found in this codebase
- Would test full CLI workflows end-to-end
- Not prioritized given CLI is for data curation (not mission-critical)

## Common Patterns

**Async Testing:**
- Not used — codebase is synchronous
- All functions are regular `def`, not `async def`

**Error Testing:**
```python
def test_invalid(self) -> None:
    """Invalid use_case raises ValueError."""
    with pytest.raises(ValueError, match="Unknown use_case"):
        get_video_prompt("invalid_use_case")
```

**File-based Testing:**
```python
def test_perfect_sample(self, tmp_path: Path):
    """A sample with valid caption and textured reference has no issues."""
    _touch(tmp_path / "clip.mp4")
    _touch(tmp_path / "clip.txt", b"A girl walks through a garden.")
    _make_textured_image(tmp_path / "clip.png")

    sample = SamplePair(
        stem="clip",
        target=tmp_path / "clip.mp4",
        caption=tmp_path / "clip.txt",
        reference=tmp_path / "clip.png",
    )
    config = _default_config()
    result = validate_sample(sample, config)
    assert result.is_valid
```

**Config-based Testing:**
```python
def test_defaults(self) -> None:
    config = CaptionConfig()
    assert config.provider == "gemini"
    assert config.timeout == 120
    assert config.max_retries == 5
```

## Coverage

**Requirements:** Not enforced (no coverage config in pyproject.toml)

**Current State:**
- Heavy unit test coverage for data models
- Good coverage for validation/discovery logic
- CLI commands have integration tests
- Mocking used to avoid API calls

**View Coverage:**
```bash
# Would require pytest-cov plugin (not installed)
# Could run: pip install pytest-cov && pytest --cov=klippbok
```

## Test File Examples

**Pure function tests** (`tests/test_caption_prompts.py`):
- Simple input → output validation
- No fixtures needed
- Fast, deterministic

**Model validation tests** (`tests/test_caption_models.py`):
- Pydantic config → validation
- Tests defaults, required fields, enums
- Uses `pytest.raises()` for invalid configs

**Integration tests** (`tests/test_dataset_validate.py`):
- Creates temporary files and directories
- Tests cross-module behavior
- Uses helper functions like `_touch()` and `_make_textured_image()`

**CLI tests** (`tests/test_dataset_cli.py`):
- Tests command-line parsing and execution
- Uses actual subprocess/command invocation

---

*Testing analysis: 2026-02-27*
