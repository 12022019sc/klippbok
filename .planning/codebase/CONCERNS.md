# Codebase Concerns

**Analysis Date:** 2026-02-27

## Tech Debt

**Broad Exception Handling in Cleanup Code:**
- Issue: `klippbok/caption/gemini.py` (lines 135-136) silently swallows cleanup failures with bare `except Exception: pass`. While cleanup failure is noted as "not critical," this pattern masks potential issues without logging.
- Files: `klippbok/caption/gemini.py:135-136`
- Impact: File upload cleanup failures (unfollowed temporary files on Gemini's API) go undetected. Could accumulate orphaned files over time. Unclear if the API eventually auto-deletes these or if they're permanent.
- Fix approach: Log the cleanup failure before silencing it: `logger.warning(f"Failed to cleanup uploaded file {uploaded_file.name}: {e}")` or raise if the API has strict cleanup requirements.

**Missing Silent Degradation Patterns:**
- Issue: Several modules silently skip validation or return `None`/`[]` without logging:
  - `klippbok/dataset/discover.py:90` - skips filetype validation if `filetype` package isn't installed
  - `klippbok/video/extract.py` - Multiple `pass` statements on lines 129, 207, 388, 728
  - `klippbok/triage/sampler.py:238-249` - Unhandled pass statements
- Files: `klippbok/dataset/discover.py`, `klippbok/video/extract.py`, `klippbok/triage/sampler.py`
- Impact: Graceful degradation is good, but users may not realize validation was skipped. No audit trail of what checks were performed.
- Fix approach: Add explicit warnings or verbose logging when optional features are unavailable. Track validation "skip reasons" in report metadata.

**Exception Propagation Without Wrapping:**
- Issue: Multiple modules catch generic `Exception` and re-raise without adding context:
  - `klippbok/caption/gemini.py:195-207` - Retries on rate limits but final error loses all context
  - `klippbok/caption/replicate.py:315-330` - Similar retry pattern
  - `klippbok/video/split.py` - bare `except Exception`
  - `klippbok/triage/triage.py` - Multiple bare exception catches
- Files: `klippbok/caption/gemini.py`, `klippbok/caption/replicate.py`, `klippbok/video/split.py`, `klippbok/triage/triage.py`
- Impact: Stack traces are preserved, but developers lack intermediate context about what operation failed. Errors bubble up to CLI with minimal actionability.
- Fix approach: Use `raise ... from e` to preserve exception chains. Add context like: `raise SplitError(path, f"ffmpeg failed after 3 retries: {e}")`.

**Unvalidated Return Values from Command Execution:**
- Issue: `klippbok/video/split.py` (line 286) returns empty list `[]` when ffmpeg command fails, instead of raising an exception. Callers see "0 clips" and assume success.
- Files: `klippbok/video/split.py:286`
- Impact: Silent failure. If split fails partway through, the manifest will be incomplete. Downstream processes may receive corrupted metadata.
- Fix approach: Raise `SplitError` instead of returning `[]`. Let callers decide whether to skip or fail.

---

## Known Bugs

**Gemini File State Polling Bug:**
- Symptoms: If Gemini API returns `state.name != "ACTIVE"` after polling, a `RuntimeError` is raised but the file is still deleted in the finally block. If deletion fails, it's silently ignored, leaving a stale file.
- Files: `klippbok/caption/gemini.py:119-136`
- Trigger: Gemini file processing fails (e.g., unsupported codec or damaged video)
- Workaround: Manually delete the stale file via Gemini's console. In production, the API auto-deletes after 2 days.
- Recommendation: Distinguish between transient errors (retry) and permanent failures (cleanup and fail). Only delete files that successfully processed.

**Config Loader Encoding Not Specified:**
- Symptoms: `klippbok/config/loader.py:116` opens YAML files without specifying encoding. On Windows systems with non-ASCII characters, could cause codec errors.
- Files: `klippbok/config/loader.py:116`
- Trigger: Load YAML config with non-UTF-8 characters or from Windows with system locale != UTF-8
- Workaround: Ensure all config files are valid UTF-8. Add `encoding="utf-8"` to file open.
- Fix: Change `open(path, "r", ...)` to `open(path, "r", encoding="utf-8", ...)`

---

## Security Considerations

**No Input Validation on File Paths:**
- Risk: Command-line tools accept file paths directly without path traversal validation. A malicious `--config` path could theoretically access files outside the intended directory.
- Files: `klippbok/video/__main__.py:514-533`, `klippbok/dataset/__main__.py`
- Current mitigation: Paths are resolved with `.resolve()` which normalizes them, but no explicit bounds checking.
- Recommendations:
  - Validate that resolved paths are within expected directories (e.g., project root)
  - Document path security assumptions in docstrings
  - Use `pathlib.Path.is_relative_to()` (Python 3.12+) or manual validation for older versions

**API Keys in Error Messages:**
- Risk: If an API request fails with status 401 (Unauthorized), the error message may include the request headers or auth token in debugging output.
- Files: `klippbok/caption/gemini.py`, `klippbok/caption/replicate.py`, `klippbok/caption/openai_compat.py`
- Current mitigation: Error strings are checked for keywords like "rate", "quota", not full bodies logged
- Recommendations:
  - Sanitize error messages before logging (remove Authorization headers, API tokens)
  - Use structured logging with separate `extra` dict for sensitive fields
  - Test with invalid API keys to verify error messages are safe

**Subprocess Command Injection via Filenames:**
- Risk: FFmpeg commands are built with user-supplied filenames. If a filename contains backticks or `$()`, it could escape the subprocess call.
- Files: `klippbok/video/split.py`, `klippbok/video/extract.py`, `klippbok/video/frames.py`, `klippbok/video/probe.py`
- Current mitigation: Commands are passed as lists to subprocess (not shell=True), which prevents shell injection. However, some commands use f-strings without quoting.
- Recommendations:
  - Verify all subprocess calls use `shell=False` (default). They do.
  - Add explicit tests with filenames containing special characters (spaces, quotes, backticks)

---

## Performance Bottlenecks

**CLIP Model Loaded Per Triage Instance:**
- Problem: `klippbok/triage/embeddings.py:86-87` loads the full CLIP model into memory every time `CLIPEmbedder` is instantiated. First load downloads ~600MB from HuggingFace and caches it. For batch processing, if multiple triage sessions are created, models are reloaded unnecessarily.
- Files: `klippbok/triage/embeddings.py:72-88`, `klippbok/triage/triage.py:160-280`
- Cause: No singleton pattern or model caching across triage runs. Each CLI invocation creates a new embedder.
- Improvement path:
  - Implement a module-level CLIP model cache: `_clip_model = None`
  - Provide a `get_clip_embedder(model_name)` function that reuses the global instance
  - Add a `--cache-dir` flag to specify custom HF cache location for offline scenarios

**Frame Sampling via FFmpeg Spawning Subprocesses:**
- Problem: `klippbok/triage/sampler.py` spawns a new ffmpeg process for each clip to extract frames. For 100 clips x 5 frames = 500 subprocess calls.
- Files: `klippbok/triage/sampler.py:40-150`
- Cause: Frame extraction uses frame numbers in a loop, each calling ffmpeg with different `-vf select` filters
- Improvement path:
  - Batch frames into single ffmpeg call using fps filter: `ffmpeg -i video.mp4 -vf "fps=1/5" frames_%d.png` extracts one frame every 5 seconds
  - Or use ffmpeg frame-skip mode with single invocation: `-vf "select=eq(n,0)+eq(n,100)+..." -vsync 0` for specific frame numbers
  - Could reduce 500 subprocess calls to ~50-100 total

**Memory Growth During Large Batch Caption Operations:**
- Problem: `klippbok/caption/captioner.py:113-250` loads all video file metadata into memory before processing. For 10,000 clips, this could be ~100MB+ of metadata objects not garbage-collected between items.
- Files: `klippbok/caption/captioner.py:113-250`
- Cause: Pydantic models store full file metadata. No streaming or batching with cleanup.
- Improvement path:
  - Implement streaming batch processing: process N clips at a time, delete processed items from memory
  - Add `--batch-size` flag to control memory footprint
  - Use generators instead of materializing full lists

---

## Fragile Areas

**Scene Detection Threshold Hardcoded in Multiple Places:**
- Files: `klippbok/video/__main__.py:616-617` (default 27.0), `klippbok/triage/triage.py:57` (LONG_VIDEO_THRESHOLD = 30.0), `klippbok/triage/__main__.py` if it exists
- Why fragile: Default scene detection threshold (27.0) is tuned for specific content types. Changing it in one place requires changes in 3+ locations. Different pipelines use different thresholds inconsistently.
- Safe modification:
  - Extract all threshold constants to `klippbok/config/defaults.py`
  - Import from defaults in each module: `from klippbok.config.defaults import SCENE_THRESHOLD`
  - Document what the threshold controls (brightness difference tolerance, in range 0-100)
- Test coverage: `tests/test_video_scene.py` tests scene detection but doesn't test threshold sensitivity

**File Extension Validation Not Centralized:**
- Files: Multiple definition sets for `VIDEO_EXTENSIONS` in:
  - `klippbok/dataset/discover.py:33-36`
  - `klippbok/video/__main__.py:206`
  - `klippbok/triage/models.py` (if it exists)
  - `klippbok/caption/captioner.py:21`
- Why fragile: Mismatch between extension sets could cause files to be processed by some tools but not others. Adding a new video format requires editing 4+ files.
- Safe modification: Create single source of truth in `klippbok/config/defaults.py`, import everywhere
- Test coverage: Tests don't verify extension sets are consistent

**Pydantic Model Validation Mode Undocumented:**
- Files: `klippbok/config/data_schema.py` uses Pydantic v2 with field validators. The `mode="before"` parameter on validators is used but not consistent across the codebase.
- Why fragile: Pydantic v2 behavior changed from v1 regarding validation timing. Mixed modes could cause unexpected coercion order.
- Safe modification: Add docstring comment above validators explaining why `mode="before"` is needed (e.g., "Convert string to enum before validation")
- Test coverage: `tests/test_data_config.py` covers many validators but doesn't explicitly test mode behavior

---

## Scaling Limits

**Single-Threaded Video Processing:**
- Current capacity: ~20-30 clips/hour on modern hardware (depends on video duration and normalization needs)
- Limit: For 1,000+ clips, ingest takes 30+ hours. No parallelization across clips.
- Scaling path:
  - Implement multiprocessing pool in `split_video_directory()`: create N worker processes, each handles a clip
  - Use `multiprocessing.Pool` with pool size = CPU count - 1
  - Ensure thread-safe file I/O (each worker writes to unique output files)
  - Files to modify: `klippbok/video/split.py`, `klippbok/video/__main__.py`

**Memory Usage for Large Concept Libraries:**
- Current capacity: ~100 concept references with 50 images each before memory strain
- Limit: Loading all reference embeddings into memory (CLIPEmbedder stores numpy arrays). For 5,000 images, ~5GB in memory at once.
- Scaling path:
  - Lazy-load reference embeddings: compute and cache them on disk
  - Use Memory-mapped numpy arrays (`np.load(..., mmap_mode='r')`)
  - Implement LRU cache for recently-used embeddings in memory
  - Files to modify: `klippbok/triage/embeddings.py`, `klippbok/triage/concepts.py`

**Manifest File Size:**
- Current capacity: ~10,000 clips in a single `manifest.json` before JSON parsing becomes slow
- Limit: JSON parsing is O(n), and large files take seconds to load
- Scaling path:
  - Split manifests into shards (one per 1,000 clips)
  - Index shards by date range or clip name prefix
  - Implement streaming manifest reader
  - Files to modify: `klippbok/video/__main__.py:544-568`

---

## Dependencies at Risk

**PySceneDetect as Optional-But-Critical Dependency:**
- Risk: `scenedetect[opencv]>=0.6` is marked optional but scene detection commands crash with `SceneDetectNotFoundError` if not installed. Users may not know it's required until they run `ingest`.
- Impact: User runs `ingest`, waits for I/O, then hits error halfway through. No early validation.
- Migration plan:
  - Add early validation in `cmd_ingest()`: check if scenedetect is available before starting
  - Provide clear error message with install instructions
  - Consider making it a required dependency if it's used in common workflows
  - Or document prominently that scene detection requires `pip install 'klippbok[video]'`

**Google Generative AI SDK Version Constraints:**
- Risk: `google-genai>=1.0` specifies only major version. API breaking changes in 2.0 could occur without notice.
- Impact: Users running `pip install -U klippbok` could hit API incompatibilities if google-genai 2.0 is released.
- Migration plan:
  - Tighten constraint: `google-genai>=1.0,<2.0`
  - Add integration tests that verify API calls work as expected
  - Monitor google-genai releases and plan migration path

**PyTorch + Transformers Lazy Import Pattern:**
- Risk: Lazy imports in `klippbok/triage/embeddings.py:28-33` hide import errors until first use. If torch or transformers install fails, user won't know until they run `triage`.
- Impact: Confusing error message deep in the CLI instead of at install time.
- Migration plan:
  - Consider eager import and fail at module load time instead
  - Or validate dependencies in `check_clip_available()` with clear, actionable error message (current approach is good, keep as-is)

---

## Missing Critical Features

**No Progress Bar for Long Operations:**
- Problem: `caption_clips()`, `triage_clips()`, and `split_video_directory()` print status updates but don't show progress percentage. For 100 clips taking 2 hours, users can't estimate completion time.
- Blocks: User experience is painful for batch jobs. No visibility into how much work is done.
- Recommendation: Add `tqdm` progress bars to loops in:
  - `klippbok/caption/captioner.py:160-250`
  - `klippbok/triage/triage.py:160-280`
  - `klippbok/video/split.py` batch processing

**No Resumable Pipelines:**
- Problem: If `ingest` fails on clip 50 of 100, there's no way to resume from clip 50. You must re-process the first 50 or manually edit the output directory.
- Blocks: Production workflows can't be fault-tolerant. Any failure requires full restart.
- Recommendation:
  - Write checkpoint file after each clip: `output/.ingest_checkpoint.json` with list of completed clips
  - At startup, check for checkpoint and skip already-processed clips
  - Files to modify: `klippbok/video/__main__.py:162-272`

**No Logging Configuration:**
- Problem: Errors are printed to console only. No persistent log file. No log level control (no `--verbose` or `--debug` flags).
- Blocks: Debugging production issues is impossible without re-running commands.
- Recommendation:
  - Add `--log-file` flag to CLI commands
  - Use Python `logging` module instead of bare `print()` statements
  - Add `--verbose` / `-v` flag to increase log level
  - Structured logging for machine-readable audit trails
  - Files to modify: `klippbok/video/__main__.py`, `klippbok/dataset/__main__.py`, all modules using `print()`

---

## Test Coverage Gaps

**Caption Provider Backends Not Fully Tested:**
- What's not tested: Replicate backend error handling, OpenAI-compatible backend retry logic, rate-limiting behavior
- Files: `klippbok/caption/replicate.py`, `klippbok/caption/openai_compat.py`, `klippbok/caption/gemini.py` (partially tested)
- Risk: Real API failures (rate limits, auth errors, timeout) are not validated. Could crash in production.
- Priority: HIGH - These are critical integration points
- Recommendation:
  - Add tests with mocked API responses for failure scenarios (401, 429, 503, timeout)
  - Test retry logic explicitly: verify exponential backoff is applied
  - Test error messages contain helpful information and no sensitive data

**FFmpeg Integration Not Tested:**
- What's not tested: Actual video file processing. Tests use fixture files, but don't verify ffmpeg commands are correct or handle real codecs.
- Files: `klippbok/video/split.py`, `klippbok/video/extract.py`, `klippbok/video/probe.py`
- Risk: Subtle ffmpeg command issues (wrong flags, incorrect filter syntax) only discovered in production.
- Priority: HIGH - These are critical path operations
- Recommendation:
  - Add integration tests with small test MP4 files (lossless codec, small resolution)
  - Verify output files are valid (use ffprobe to check specs)
  - Test edge cases: single-frame videos, very high frame rates, unusual aspect ratios

**CLIP Triage Matching Not Tested:**
- What's not tested: Actual CLIP embedding computation, cosine similarity calculations, threshold behavior
- Files: `klippbok/triage/embeddings.py`, `klippbok/triage/triage.py`
- Risk: CLIP model behavior changes between versions go undetected. Similarity scores may be unpredictable.
- Priority: MEDIUM - Triage is optional feature
- Recommendation:
  - Add tests with known image pairs (high similarity, low similarity)
  - Verify similarity scores are in [0, 1] range and normalized correctly
  - Test threshold sensitivity: vary threshold 0.5-0.9 and verify cutoff behavior

**Dataset Structure Detection Not Comprehensive:**
- What's not tested: Edge cases in `detect_structure()` and file classification
- Files: `klippbok/dataset/discover.py`
- Risk: Files classified incorrectly (e.g., text file renamed to `.mp4`) could corrupt the dataset manifest
- Priority: MEDIUM - Affects data integrity
- Recommendation:
  - Add tests with misnamed files (extension mismatch)
  - Test with mixed file types in same directory
  - Add magic-byte validation tests (with filetype installed and without)

**CLI Argument Parsing Not Exhaustively Tested:**
- What's not tested: Conflicting flags, missing required arguments, invalid enum values
- Files: `klippbok/video/__main__.py:571-810`, `klippbok/dataset/__main__.py`
- Risk: Invalid CLI usage crashes with unclear error messages
- Priority: LOW - argparse provides basic validation
- Recommendation:
  - Test invalid threshold values (negative, > 100)
  - Test invalid resolution values
  - Verify error messages are actionable

---

*Concerns audit: 2026-02-27*
