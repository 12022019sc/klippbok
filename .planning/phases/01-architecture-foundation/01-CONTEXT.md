# Phase 1: Architecture Foundation - Context

**Gathered:** 2026-02-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Service layer, image domain module, unified data models, and dependency structure that both CLI and future API routes share — without breaking existing CLI workflows (`klippbok dataset`, `klippbok video`).

</domain>

<decisions>
## Implementation Decisions

### Image format support
- Accept PNG, JPG/JPEG, WEBP only — common web formats that cover 95%+ of dataset images
- Unsupported formats (TIFF, BMP, etc.) are flagged as a ValidationIssue (`format_unsupported`), not silently skipped
- RGBA images accepted and auto-flattened to RGB (composite onto white background) — trainers only need RGB
- Corrupt/truncated files treated the same as unsupported formats — ValidationIssue with appropriate issue type, accumulative (not fail-fast)

### Image validation rules
- Validation is accumulative — collect ALL issues per image, user sees everything at once
- Phase 1 validation covers: format, corruption, dimensions, color mode (structural checks only)
- Quality analysis (blur, upscale detection, exposure, duplicates) deferred to Phase 3
- Resolution validation is bucket-aware, not simple min-dimension — a 256x768 image is valid if it fits a bucket's pixel area budget
- Images that don't fit any valid bucket are flagged with the nearest valid bucket suggestion

### SamplePair unification
- Mixed datasets: a single dataset can contain both image and video samples
- Start minimal, extend later: core fields are source path, type (image/video), dimensions, caption — designed for future phases to add fields without breaking changes
- Caption is optional — samples can exist without captions since captioning happens in Phase 6
- No processing history/audit trail — only store current state of each sample

### Service layer boundaries
- Existing CLI commands refactored to call through the service layer — single code path for CLI and future API
- Project manifest: a persistent file (YAML/JSON) tracks all samples and their state, survives between sessions, enables resume

### Claude's Discretion
- Service granularity (one per domain vs unified vs hybrid)
- Service statefulness model (how CLI short-lived vs API long-lived contexts are handled)
- Manifest file format and location
- Image domain module internal structure

</decisions>

<specifics>
## Specific Ideas

- Bucket validation should work like malcomrey's tool: 256x768 is valid for bucket size 512 because it's the pixel area budget that matters, not the shortest side alone
- User's existing manual workflow is: upscale first, then crop — the tool should support this flow in later phases

</specifics>

<deferred>
## Deferred Ideas

- Upscale detection and quality scoring — Phase 3
- How upscaling/cropping order should work in the pipeline — Phase 3 / Phase 5

</deferred>

---

*Phase: 01-architecture-foundation*
*Context gathered: 2026-02-27*
