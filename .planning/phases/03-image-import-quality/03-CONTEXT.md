# Phase 3: Image Import and Quality - Context

**Gathered:** 2026-02-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Batch image import with validation, model-aware bucketing, quality filtering (blur + upscale), and perceptual duplicate detection. Users import a folder of mixed images and immediately see which are training-ready, which need attention, and how they distribute across resolution buckets.

</domain>

<decisions>
## Implementation Decisions

### Validation reporting
- Summary view by default: "47 imported, 3 rejected" — with ability to drill into individual failures
- Rejection reasons use short code + message format (e.g. `CORRUPT: Failed integrity check`, `UNSUPPORTED: BMP format not accepted`)
- Validation results are persisted in the project so the GUI can display them later without re-running
- Already-imported files are skipped silently — no noise in output

### Warning vs error behavior
- Import and auto-fix where possible (e.g. RGBA→RGB conversion), warn on issues that can't be auto-fixed
- Original files are preserved alongside fixed versions — user can compare
- Images below target resolution are imported with a warning ("needs upscale"), never rejected
- Quality issues are advisory only — never block import or exclude from training automatically

### Bucketing behavior
- Images assigned to nearest valid bucket by aspect ratio — minimal distortion
- Bucket distribution shown as a visual histogram — easy to see heavy/light buckets at a glance
- Extreme aspect ratio images (beyond max_aspect_ratio) are imported with a warning, not rejected
- Bucketing timing: Claude's discretion (automatic on import vs separate step)

### Quality thresholds
- Two quality checks only: blur detection and upscale warning
- Blur detection uses pass/fail with a fixed threshold (no user-adjustable scoring)
- Upscale warning triggers when image is smaller than its assigned bucket dimensions (not just base resolution)
- No exposure or JPEG artifact checks — keep it simple

### Duplicate detection
- Perceptual hashing for near-identical detection (resized copies, re-encoded, minor crops)
- Not similarity-based — won't flag "similar but different" shots
- Runs during import: each new image checked against existing project images
- Auto-keep the highest-resolution version, flag the rest for removal
- Tiebreaker when same resolution: prefer lossless format (PNG > WEBP > JPG)

### Claude's Discretion
- Bucketing timing (auto on import vs separate step)
- Exact perceptual hash algorithm choice
- Blur detection threshold value and algorithm (Laplacian variance or similar)
- Histogram visualization implementation details
- Remaining warning/error edge cases not covered above

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-image-import-quality*
*Context gathered: 2026-02-27*
