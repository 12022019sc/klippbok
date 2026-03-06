---
phase: 07-video-and-clip-integration
plan: "05"
subsystem: triage-api
tags: [backend, api, file-upload, fastapi, triage]
dependency_graph:
  requires: []
  provides: [POST /triage/concepts/upload]
  affects: [frontend/src/pages/TriagePage.tsx]
tech_stack:
  added: []
  patterns: [UploadFile + Form multipart handler, tempfile atomic write pattern]
key_files:
  created:
    - tests/test_triage_api_upload.py
  modified:
    - klippbok/api/routers/triage.py
decisions:
  - "UPLOAD-01: Write upload to temp file in project root, then use add_concept_reference() for copy to concepts/{category}/ — avoids shutil.SameFileError that occurs when writing directly to the target path"
  - "UPLOAD-02: Register /concepts/upload BEFORE /concepts (FastAPI matches in registration order) — prevents path-parameter capture by the existing POST /concepts endpoint"
  - "UPLOAD-03: Rename temp file to original filename before passing to add_concept_reference() so the ConceptReference.name and image_path use the correct stem/extension"
metrics:
  duration: "~5min"
  completed: "2026-03-05"
  tasks_completed: 1
  files_changed: 2
---

# Phase 07 Plan 05: Concepts Upload Endpoint Summary

**One-liner:** FormData file upload endpoint `POST /triage/concepts/upload` closing the 404 gap between TriagePage frontend and triage backend.

## What Was Built

Added `POST /triage/concepts/upload` to `klippbok/api/routers/triage.py`. This endpoint:

- Accepts `multipart/form-data` with a `file: UploadFile` and `category: str = Form(...)`
- Saves the upload atomically via a temporary file, then calls `add_concept_reference()` to copy to `concepts/{category}/`
- Returns the standard ConceptReference dict: `{name, concept_type, image_path, folder_name}`
- Returns 409 when no project directory is configured
- Returns 422 when file or category field is missing (FastAPI built-in validation)

## TDD Flow

**RED:** Created `tests/test_triage_api_upload.py` with 6 tests covering success, file persistence, directory creation, 409, and 422 cases. Tests failed with 405 (endpoint not found).

**GREEN:** Implemented endpoint. First attempt failed with `shutil.SameFileError` because writing directly to the target path then calling `add_concept_reference` caused src == dst. Fixed by using a temp file in the project root, renaming it to the original filename, calling `add_concept_reference` (which copies to the final destination), then cleaning up the temp source. All 6 tests pass.

## Tests

- `test_upload_returns_200_with_concept_reference` — 200 response with correct JSON keys
- `test_upload_saves_file_to_concepts_directory` — file physically at `concepts/character/uploaded.png`
- `test_upload_creates_category_directory_if_missing` — mkdir on first upload to new category
- `test_upload_returns_409_when_no_project_dir` — 409 when app.state.project_dir is None
- `test_upload_returns_422_when_category_missing` — 422 validation error
- `test_upload_returns_422_when_file_missing` — 422 validation error

Full suite: 1455 passed, 4 skipped — no regressions.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed SameFileError from writing upload directly to target path**
- **Found during:** Task 1 GREEN phase
- **Issue:** First implementation wrote the uploaded file directly to `concepts/{category}/{filename}`, then called `add_concept_reference(image_path=dest_path)`. Since `dest_path` was already in the concepts folder, `add_concept_reference` tried to `shutil.copy2(src, dst)` where src == dst, raising `shutil.SameFileError`.
- **Fix:** Write upload to a temp file in the project root, rename it to the original filename, call `add_concept_reference()` which copies to `concepts/{category}/`, then clean up the temp source file in a finally block.
- **Files modified:** klippbok/api/routers/triage.py
- **Commit:** dc78d83

## Commits

| Commit | Message |
|--------|---------|
| dc78d83 | feat(07-05): add POST /triage/concepts/upload endpoint with UploadFile handler |

## Self-Check: PASSED

- `tests/test_triage_api_upload.py` exists: FOUND
- `klippbok/api/routers/triage.py` modified: FOUND
- Commit dc78d83: FOUND
- All 6 upload tests pass: CONFIRMED
- Full suite 1455 passed: CONFIRMED
