# Phase 4: Web GUI Foundation - Context

**Gathered:** 2026-02-28
**Status:** Ready for planning

<domain>
## Phase Boundary

FastAPI+React web interface shell with image gallery, thumbnails, per-image status overlays, and progress indicators. Users launch with `klippbok serve` and browse imported images at a glance. Crop editor (Phase 5), captioning (Phase 6), and export (Phase 8) are out of scope.

</domain>

<decisions>
## Implementation Decisions

### Gallery layout
- Masonry layout reflecting actual aspect ratios (not uniform squares)
- Flat grid with filter/sort controls — no visual grouping by bucket or status
- Virtual scrolling for large datasets (render only visible items)
- Click thumbnail opens a lightbox overlay with full-size preview and metadata panel

### Image status display
- Bottom strip overlay on each thumbnail showing all status indicators
- Resolution with green/red indicator — binary: green (downscale OK) / red (upscale needed), no yellow intermediate
- Quality badge — pass/fail for blur detection
- Bucket label — assigned aspect-ratio bucket (e.g. "3:4", "1:1")
- Duplicate flag — visual grouping for near-duplicates (matching colored borders or stacking effect so clusters are visible at a glance)
- Caption preview only in lightbox detail view, not on thumbnails

### Navigation & app shell
- Multi-page layout with top navigation bar
- Three pages for Phase 4: Gallery, Import, Settings
- Model profile selected at project creation time, changeable in Settings
- Single project at a time — switch by loading a different folder

### Progress & feedback
- Batch import runs in background with persistent toast notification (visible across all pages)
- Gallery updates live as images are imported (live feed, thumbnails appear incrementally)
- Errors surface as non-blocking toast notifications — import continues past failures
- Progress is page-local except for the persistent operation toast

### Claude's Discretion
- Exact thumbnail sizes and masonry column configuration
- Filter/sort control placement and options
- Lightbox metadata panel layout
- Toast notification styling and positioning
- SSE implementation details for live updates
- React component architecture and state management approach
- Dark/light theme (if any)

</decisions>

<specifics>
## Specific Ideas

- Reference: malcolmrey's "dataset-preparation" Gradio Space (screenshots in repo root) — similar domain but klippbok uses React, not Gradio, and has multi-page navigation
- The bottom strip on thumbnails should be semi-transparent so it doesn't obscure the image content
- Duplicate visual grouping should make it immediately obvious which images are related without needing to click

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-web-gui-foundation*
*Context gathered: 2026-02-28*
