# Full E2E Test: Process Videos Workflow

## Context

You are testing the klippbok video processing workflow using Playwright to drive the browser. The app runs at `http://localhost:9000`. You must use Playwright MCP tools (browser_navigate, browser_snapshot, browser_click, browser_take_screenshot, browser_wait_for, etc.) to interact with the UI. Use `curl` via Bash for API-level checks where noted.

## Environment

- Server: `.venv/Scripts/python.exe -m klippbok.api --port 9000` (from `C:\Dev\Projects\klippbok-main`)
- Test project directory: `C:\GenAI\Training\Instagram\natahrie\temp`
- Contents: 56 images (.jpg/.heic/.webp) + 5 videos (.mp4), no subdirectories
- Branch: `feat/dataset-prep-gui`

## Pre-test Setup (REQUIRED)

Before any tests, ensure a clean slate:

1. **Kill any running server**: `taskkill //F //PID $(netstat -ano | grep :9000 | grep LISTEN | awk '{print $5}')` or equivalent
2. **Delete old project data**: Remove `C:\GenAI\Training\Instagram\natahrie\temp\.klippbok` and `C:\GenAI\Training\Instagram\natahrie\temp\refs` directories if they exist
3. **Start the server** in background: `.venv/Scripts/python.exe -m klippbok.api --port 9000`
4. **Wait for startup**: Poll `curl -s http://localhost:9000/api/v1/settings/` until it responds
5. **Set project directory** via API: `curl -X PUT http://localhost:9000/api/v1/settings/ -H "Content-Type: application/json" -d '{"project_dir": "C:/GenAI/Training/Instagram/natahrie/temp"}'`
6. **Trigger initial import**: Navigate to `http://localhost:9000` in Playwright, wait for "Loading images..." to disappear, verify images appear in the gallery grid

After setup, verify baseline state:
- Gallery shows images AND videos (use the "Videos" filter button to confirm 5 video entries exist)
- "Process Videos" button is visible in the gallery toolbar (non-selection mode)
- Note the total image count from the API: `curl -s http://localhost:9000/api/v1/images/ | python -c "import sys,json; print(json.load(sys.stdin)['total'])"`

Take a screenshot after setup as `screenshots/test-00-baseline.png`.

---

## Test Suite

### TEST 1: Gallery — "Process Videos" button visibility

**Goal**: Verify the button appears/hides based on video presence.

1. On the gallery page, confirm "Process Videos" button is visible in the toolbar
2. Click the "Videos" filter button — confirm only video entries are shown
3. Click the "Images" filter button — confirm only image entries are shown
4. Click "All" to reset the filter
5. Verify "Process Videos" button is still visible regardless of active filter

**Screenshot**: `screenshots/test-01-gallery-toolbar.png`

**Pass criteria**: "Process Videos" button is visible whenever the manifest contains video entries, regardless of which media filter is active.

---

### TEST 2: Process Videos — Setup page (all videos)

**Goal**: Verify the setup page loads correctly when navigating from the gallery button.

1. Click "Process Videos" in the gallery toolbar
2. Verify URL is `/process-videos`
3. Verify heading is "Process Videos"
4. Verify subtitle says "Extract reference frames from 5 videos."
5. Verify 5 video thumbnail cards are displayed in the grid
6. Verify each card has a filename label ending in `.mp4`
7. Verify "Start Processing" and "Back to Gallery" buttons are present
8. Click "Back to Gallery" — verify you return to `/` (the gallery)

**Screenshot**: `screenshots/test-02-setup-all.png` (before clicking Back)

**Pass criteria**: Setup page correctly shows all 5 videos with thumbnails, accurate count, and working navigation.

---

### TEST 3: Process Videos — Extraction with progress

**Goal**: Verify the extraction phase shows progress and completes.

1. Navigate to `/process-videos`
2. Click "Start Processing"
3. **Immediately take a snapshot** to capture the "Processing Videos" / progress bar state (this may be fast with only 5 videos — take the snapshot as quickly as possible)
4. Wait for the heading to change to "Review Extracted Frames" (use `browser_wait_for` with text "Review Extracted Frames")
5. Verify the progress state appeared (even if briefly) — the snapshot from step 3 should show either:
   - "Processing Videos" heading with progress bar, OR
   - Already transitioned to "Review Extracted Frames" (acceptable if extraction was instant)

**Screenshot**: `screenshots/test-03-progress.png` (captured at step 3)

**Pass criteria**: Processing starts and completes without errors. Progress UI appeared or extraction was fast enough to skip directly to review.

---

### TEST 4: Process Videos — Review page inspection

**Goal**: Thoroughly inspect the review page state after extraction.

1. You should now be on the "Review Extracted Frames" page
2. Verify the heading says "Review Extracted Frames"
3. Read the subtitle — it should say "N frames extracted from 5 videos" (N >= 5, since each video produces at least 1 frame)
4. Verify stats bar shows frame count and "5 videos"
5. Scroll through the grid — verify each card has:
   - A visible thumbnail image (not broken)
   - A filename label referencing the source `.mp4`
6. Verify three action buttons exist: "Confirm Import (N)", "Discard", "Back to Gallery"
7. Count the frames shown and verify it matches the number in the heading

**Screenshot**: `screenshots/test-04-review.png` (full page if possible)

**Pass criteria**: Review page shows correct counts, all frame thumbnails load, and action buttons are present with correct labels.

---

### TEST 5: Process Videos — Discard flow

**Goal**: Test the discard path — frames should be deleted, videos should remain in gallery.

1. On the review page, click "Discard"
2. Wait for navigation back to gallery (`/`)
3. Check for a toast notification — it should say "Discarded N frames" (not an error)
4. Verify the gallery still shows videos (click "Videos" filter, confirm 5 videos still present)
5. Via API, verify `refs/` directory was cleaned: `ls C:/GenAI/Training/Instagram/natahrie/temp/refs/ 2>/dev/null | wc -l` — should be 0 or directory should not exist
6. Verify total image count is the same as baseline (videos were NOT removed)

**Screenshot**: `screenshots/test-05-after-discard.png`

**Pass criteria**: Discard deletes extracted frames from `refs/`, navigates to gallery, videos remain in manifest, toast shows correct count.

---

### TEST 6: Process Videos — Full confirm flow (all videos)

**Goal**: Test the happy path end-to-end: extract then confirm import.

1. From the gallery, click "Process Videos"
2. On the setup page, click "Start Processing"
3. Wait for "Review Extracted Frames" to appear
4. Note the frame count (N) from the heading
5. Click "Confirm Import (N)"
6. Verify navigation back to gallery (`/`)
7. Check for toast notification — should say "Imported N frames, removed 5 video entries" with actual numbers (NOT `[object Object]`)
8. Click "Videos" filter — verify "No media found" (all videos removed)
9. Click "All" — verify the gallery now contains images + newly imported reference frames
10. Via API, check new total: `curl -s http://localhost:9000/api/v1/images/ | python -c "import sys,json; print(json.load(sys.stdin)['total'])"` — should be baseline + N - 5 (frames added, videos removed)
11. Verify "Process Videos" button is NO LONGER visible in the toolbar (no videos remain)

**Screenshot**: `screenshots/test-06-after-confirm.png`

**Pass criteria**: Frames imported, videos removed, toast shows correct integer counts, gallery updated, "Process Videos" button hidden.

---

### TEST 7: Edge case — No videos remaining

**Goal**: Verify the process-videos page handles the no-video state gracefully.

1. Navigate directly to `/process-videos` (there should be no videos after TEST 6)
2. Verify heading "Process Videos"
3. Verify message "No videos to process in this project."
4. Verify "Back to Gallery" button is the only action
5. Click "Back to Gallery" — verify navigation to `/`

**Screenshot**: `screenshots/test-07-no-videos.png`

**Pass criteria**: Clean empty state with informative message, no errors, working navigation.

---

### TEST 8: Selection mode — Process specific videos

**IMPORTANT**: This test requires videos in the manifest. You must reset the project first:
1. Delete `.klippbok` and `refs` directories from the test project
2. Restart the server OR clear the project and re-set it via `PUT /api/v1/settings/` with `{"project_dir": null}` then re-set it
3. Wait for the gallery to reload and re-import images
4. Verify 5 videos are present again

Now test selection mode:
5. On the gallery page, click "Select Mode"
6. Click the "Videos" filter to show only videos
7. Click on exactly 2 video thumbnails to select them (they should get a visual selection indicator)
8. Verify the selection toolbar shows "2 selected"
9. Verify a "Process Videos (2)" button appears in the selection toolbar
10. Click "Process Videos (2)"
11. Verify the setup page shows exactly 2 videos (not all 5)
12. Verify subtitle says "Extract reference frames from 2 videos."
13. Click "Start Processing" — wait for review
14. Verify frames were extracted only from the 2 selected videos (check the filenames in the review grid match the 2 you selected)
15. Click "Confirm Import" — verify toast shows correct counts
16. Return to gallery — verify 3 videos remain (the 2 processed ones were removed, 3 untouched)

**Screenshots**:
- `screenshots/test-08a-selection.png` (2 videos selected, before clicking Process Videos)
- `screenshots/test-08b-setup-filtered.png` (setup page showing 2 videos)
- `screenshots/test-08c-after-confirm.png` (gallery showing 3 remaining videos)

**Pass criteria**: Selection mode correctly passes only selected video paths. Only those videos are processed and removed. Remaining videos are untouched.

---

## Post-test Summary

After all tests, produce a summary table:

| Test | Description | Result | Issues Found |
|------|-------------|--------|--------------|
| 1 | Button visibility | PASS/FAIL | ... |
| 2 | Setup page (all) | PASS/FAIL | ... |
| 3 | Extraction progress | PASS/FAIL | ... |
| 4 | Review inspection | PASS/FAIL | ... |
| 5 | Discard flow | PASS/FAIL | ... |
| 6 | Confirm flow (all) | PASS/FAIL | ... |
| 7 | No-videos edge case | PASS/FAIL | ... |
| 8 | Selection mode | PASS/FAIL | ... |

For each FAIL, describe:
- What was expected vs what happened
- Screenshot filename showing the issue
- Which file(s) likely need fixing (backend/frontend)
- Severity: blocker / major / minor / cosmetic

For anything that feels confusing or could be improved UX-wise (even if it technically works), note it as a UX observation in the summary.
