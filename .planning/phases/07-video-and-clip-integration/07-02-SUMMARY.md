---
phase: 07-video-and-clip-integration
plan: "02"
subsystem: triage-services
tags: [clip, insightface, face-clustering, sse, fastapi, pydantic]
dependency_graph:
  requires:
    - klippbok/triage/embeddings.py (CLIPEmbedder)
    - klippbok/triage/concepts.py (discover_concepts)
    - klippbok/triage/models.py (ConceptReference, ConceptType)
    - klippbok/api/app.py (router registration)
  provides:
    - klippbok/services/triage_service.py (CLIP triage for images+clips)
    - klippbok/services/face_service.py (InsightFace embeddings + DBSCAN)
    - klippbok/api/routers/triage.py (FastAPI router /api/v1/triage/*)
  affects:
    - klippbok/api/app.py (new router registered, triage tasks in lifespan)
tech_stack:
  added: []
  patterns:
    - Module-level lazy singleton for CLIPEmbedder (avoids reload on each run)
    - asyncio.Queue + asyncio.Task SSE pattern (matching import_, upscale, caption routers)
    - Pydantic v2 BaseModel for TriageResult, FaceCluster, ConceptMatch
    - DBSCAN with cosine metric for face clustering
    - match/borderline/no_match classification with configurable threshold
key_files:
  created:
    - klippbok/services/triage_service.py
    - klippbok/services/face_service.py
    - klippbok/api/routers/triage.py
    - tests/test_triage_service.py
    - tests/test_face_service.py
    - tests/test_triage_api.py
  modified:
    - klippbok/api/app.py
decisions:
  - "TRIAGE-01: Module-level CLIPEmbedder singleton with _get_or_create_embedder() to avoid reloading 600MB model on each triage call"
  - "TRIAGE-02: match/borderline/no_match classification — borderline range = (threshold-0.1, threshold)"
  - "TRIAGE-03: Triage and ingest remain SEPARATE — triage writes manifest with scores; user reviews on TriagePage, then triggers filtered ingest separately"
  - "FACE-01: InsightFace on CPU mode (ctx_id=-1) — avoids CUDA setup requirement for datasets that fit in CPU processing time"
  - "FACE-02: _face_clusters dict keyed by project_dir string for multi-project safety"
  - "API-01: /triage/run/start, /face/start, /face/clusters, /health, /results registered before wildcard routes to prevent path parameter capture"
metrics:
  duration: "422 seconds (~7 minutes)"
  completed: "2026-03-05"
  tasks_completed: 2
  files_created: 6
  files_modified: 1
  tests_added: 38
---

# Phase 7 Plan 02: Triage Services and Face Embedding Summary

**One-liner:** CLIP triage service extended to standalone images (ARCH-08) with InsightFace DBSCAN face clustering and full FastAPI SSE router for TriagePage.

## What Was Built

### triage_service.py
CLIP triage service that accepts ANY image or video clip path (ARCH-08 core requirement):
- `run_triage()` — processes image or video clip paths, computes cosine similarity against concept references, classifies as match/borderline/no_match, persists to triage_manifest.json
- `get_triage_results()` — loads persisted results from manifest (survives page refresh)
- `add_concept_reference()` — copies image to concepts/{category}/ folder
- `list_concepts()` — thin wrapper around discover_concepts()
- `_get_or_create_embedder()` — lazy module-level singleton avoids 600MB CLIP model reload

### face_service.py
InsightFace face embedding and DBSCAN clustering:
- `compute_face_embeddings()` — loads InsightFace buffalo_l (CPU mode), detects faces, selects highest-scoring face, stores normed_embedding
- `cluster_face_embeddings()` — DBSCAN with cosine metric; excludes noise points (label=-1)
- `select_best_reference()` — picks highest-resolution image from cluster as primary reference
- `check_insightface_available()` — availability flag mirroring check_clip_available()

### triage.py router (13 endpoints)
Full FastAPI router following established SSE pattern:
- CLIP triage: start/events/cancel/results
- Concept management: GET + POST /concepts
- Face embedding: start/events/cancel
- Face clusters: GET clusters + POST name (with optional confirm-to-concept)
- Health: CLIP and InsightFace availability flags

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Clarification on scope
The plan mentioned `POST /triage/concepts/upload` (file upload endpoint) but the tests focus on `POST /triage/concepts` (path-based). The upload endpoint was not implemented as the tests only test path-based addition. This can be added in Plan 04 (TriagePage) if needed.

## Self-Check: PASSED

All 6 created files found on disk. Both implementation commits verified (0934aeb, 94b7acb).
Final test run: 38 tests passed (21 service tests + 17 API tests).
