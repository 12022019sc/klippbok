# Phase 7: Video and CLIP Integration - Context

**Gathered:** 2026-03-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Expose the existing video pipeline (ingest, scan, extract, triage) and CLIP-based triage from the web GUI, extend CLIP triage to standalone images, add face-embedding-based auto-subject identification (InsightFace) for character LoRA workflows, and unify video clips into the existing gallery alongside images.

</domain>

<decisions>
## Implementation Decisions

### Video workflow scope
- Four CLI commands get GUI exposure: **ingest**, **scan**, **triage**, **extract**
- Caption, score, audit, normalize stay CLI-only (caption already has GUI coverage for images)
- Video clips appear in the **unified gallery** alongside images (not a separate gallery)
- Video captioning is accessible from the existing **CaptionPage** — backend already supports video captioning, GUI passes clip paths
- Smart defaults for ingest config (16fps, 720p, auto frames) with an **Advanced toggle** for threshold, max-frames, resolution
- Both video upload and directory picker supported for ingest input (upload for small files, directory for large raw footage)
- Extracted reference frames viewable/manageable in a **concepts gallery** on the Triage page

### Navigation & page layout
- **Video page** (new nav item): single page with **top tabs** for Ingest, Scan, Extract
- **Triage page** (new nav item): separate dedicated page for CLIP matching (works with both video clips and images)
- Nav order: Gallery → Import → **Video** → Crop → Caption → **Triage** → Settings
- Gallery gets **filter controls**: All | Images | Videos toggle to focus on one media type
- Video clip thumbnails: **play button overlay** (centered, semi-transparent) + **duration badge** (corner, e.g., "3.2s")
- Clicking a video clip in gallery lightbox shows **video playback** with `<video>` element and play controls
- Scan tab shows **project-wide auto-scan** results for all video clips (runs automatically when videos are present)
- Scan results also displayed as **per-clip metadata badges** on gallery thumbnails (fps, frame count, duration, validation)

### Image triage UX (ARCH-08)
- Concept references added via **dedicated 'Add to Concepts' action** on gallery images (right-click or contextual button, not selection mode)
- Additional references uploadable directly on the Triage page concepts gallery panel
- Triage results: **score overlay on gallery items** (similarity badge + color: green=match, yellow=borderline, grey=no match) + **results summary panel** on Triage page for batch decisions
- Threshold: **adjustable slider** (0.5–1.0, default 0.70) with **borderline range** (threshold-0.1 to threshold = yellow/review zone)
- Triage results **persisted to triage_manifest.json** (survives page refresh, available for filtered ingest)

### Auto-subject identification (InsightFace)
- **Face embeddings via InsightFace** for automatic subject identification across imported images
- Targets character LoRA workflow: detect faces, generate identity embeddings, cluster same-person images
- Results shown in a **Suggested Subjects panel** on the Triage page (e.g., "Person A: 12 images, Person B: 5 images")
- User names clusters and confirms → confirmed clusters become concept references
- Auto-picks the **highest-quality image** from each cluster as primary reference; user can swap

### Filtered ingest pipeline
- Claude's Discretion: Whether triage → filtered ingest runs as a connected pipeline from the GUI, or triage produces the manifest and user triggers ingest separately. Claude picks based on complexity vs. value.

### Progress & cancellation
- Video ingest: **stage-aware progress bar** with SSE — shows current stage label + overall % (e.g., "Scene detection... 45%", "Splitting clip 3/7... 60%")
- Face embedding computation: **progress with ETA** per image ("Computing face embeddings... 23/150 images (ETA: 45s)")
- CLIP triage: **simple progress bar** (0–100% across all CLIP steps, no stage labels)
- All long-running operations (ingest, triage, face embedding) are **cancelable** via cancel button — graceful termination, keeps results produced so far

### Claude's Discretion
- Video clip thumbnail generation strategy (first frame extraction, caching)
- InsightFace model selection and dependency management (optional `[triage]` extra)
- Face embedding clustering algorithm (DBSCAN, agglomerative, etc.) and similarity threshold
- SSE event naming for video operations (following existing patterns: `ingest_progress`, `triage_progress`, `face_progress`, etc.)
- API router organization for video endpoints
- Whether to reuse the existing `triage_manifest.json` format or extend it for GUI-specific fields

</decisions>

<specifics>
## Specific Ideas

- Primary use case is **character LoRAs of human females** — the typical workflow is: import reference images of the character → scan raw video footage → triage to find scenes containing the character → extract the best frames → build the dataset
- User wants the system to be flexible for both **individual subjects** (same person across many images) and **subject types** (e.g., "realistic photos of human females" as a category)
- Face embeddings chosen over CLIP clustering for subject identification because identity matching is critical for character LoRAs — CLIP is good at visual similarity but not reliable for distinguishing individual people
- The "triage first" workflow is the key pipeline: identify scenes with your character BEFORE spending time splitting everything

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `klippbok/triage/embeddings.py`: CLIPEmbedder class with encode_image, encode_images, encode_text, best_match_score — ready for GUI integration
- `klippbok/triage/triage.py`: triage_clips() and triage_videos() orchestrators — can be called from API routes
- `klippbok/triage/concepts.py`: discover_concepts() reads concepts/ folder structure — reusable for concepts gallery
- `klippbok/video/__main__.py`: CLI commands (cmd_ingest, cmd_scan, cmd_extract, cmd_triage) — business logic to extract into service functions
- `klippbok/video/probe.py`: probe_video(), probe_directory() — metadata extraction for scan results
- `klippbok/video/validate.py`: validate_directory(), format_scan_report() — validation for scan tab
- `klippbok/video/extract.py`: extract_directory(), extract_from_selections() — reference frame extraction
- `klippbok/video/scene.py`: detect_scenes() — scene detection for ingest pipeline
- `klippbok/video/split.py`: split_video_at_scenes(), split_video_segments() — splitting for ingest
- Existing SSE patterns: asyncio.Queue per operation_id, named events (import_error, upscale_error, caption_error)
- SelectionToolbar component (Phase 5) — pattern for gallery actions
- Zustand store with selectionMode/selectedImageIds — existing selection state management

### Established Patterns
- SSE for long-running ops: POST starts background task → GET /events/{op_id} streams progress → cancel endpoint
- SHA256[:16] for item IDs (stable, URL-safe)
- Routers registered before StaticFiles mount
- app.state for shared state (project_dir, etc.)
- Optional dependency groups (video, caption, dataset, triage)
- Manifest-driven state tracking (JSON manifests for pipeline communication)

### Integration Points
- Gallery API (`/api/v1/images/`) needs extension for video clips (or new `/api/v1/clips/` endpoint)
- NavBar.tsx — add Video and Triage nav items
- App router — add /video and /triage routes
- Gallery types (GalleryItem) need video-specific fields (fps, frame_count, duration, media_type)
- Lightbox component needs video playback support for clip items
- ThumbnailCard needs video overlay (play button, duration badge)
- CaptionPage needs to handle video clip captioning alongside images

</code_context>

<deferred>
## Deferred Ideas

None — all discussed items included in phase scope per user decision.

</deferred>

---

*Phase: 07-video-and-clip-integration*
*Context gathered: 2026-03-05*
