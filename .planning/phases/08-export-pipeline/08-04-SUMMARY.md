---
phase: 08-export-pipeline
plan: "04"
subsystem: training-pipeline
tags: [training, onetrainer, sse, gpu, settings, frontend]
dependency_graph:
  requires: [08-02, 08-03]
  provides: [training-panel, gpu-busy-guards, settings-tools]
  affects: [ExportPage, SettingsPage, CleanupPage, CuratePage, TriagePage]
tech_stack:
  added: []
  patterns: [SSE event routing, TanStack Query polling, GPU busy guard pattern]
key_files:
  created:
    - frontend/src/hooks/useTrainingEvents.ts
    - frontend/src/hooks/useGpuStatus.ts
    - frontend/src/components/Export/ModelPicker.tsx
    - frontend/src/components/Export/TrainingConfig.tsx
    - frontend/src/components/Export/TrainingPanel.tsx
  modified:
    - klippbok/api/routers/export.py
    - klippbok/api/routers/settings.py
    - frontend/src/pages/ExportPage.tsx
    - frontend/src/pages/SettingsPage.tsx
    - frontend/src/pages/CleanupPage.tsx
    - frontend/src/pages/CuratePage.tsx
    - frontend/src/pages/TriagePage.tsx
    - frontend/src/App.css
decisions:
  - "GPU busy guard uses OR of gpuBusy || trainingActive for maximum safety"
  - "TrainingPanel shown only for onetrainer trainer (not kohya/aitoolkit which don't have preset_path)"
  - "useGpuStatus polls every 30s via TanStack Query refetchInterval -- no manual polling loop"
  - "CuratePage GPU guard passes no-op onStart when gpuInUse -- avoids breaking CurationConfig props interface"
  - "TensorBoard iframe stays visible after training completes for post-training analysis"
metrics:
  duration: 655
  completed_date: "2026-03-10"
  tasks_completed: 2
  files_modified: 13
requirements: [GUI-07]
---

# Phase 08 Plan 04: Training Panel UI and GPU Busy Guards Summary

OneTrainer training panel with SSE progress, TensorBoard iframe, completion/error states, settings integration for tool paths, and GPU busy guards on Cleanup/Curate/Triage pages.

## What Was Built

### Backend (Task 1)

**Export router additions** (`klippbok/api/routers/export.py`):
- `GET /export/train/status` — OneTrainer detection, training active flag, GPU VRAM usage
- `POST /export/train/start` — Reads preset, applies param overrides, launches headless training via SSE queue
- `GET /export/train/{op_id}/events` — SSE stream with training_progress/error/done events
- `POST /export/train/{op_id}/stop` — Graceful SIGTERM via stop_onetrainer()
- `POST /export/train/launch-gui` — Detached OneTrainer GUI launch
- `GET /export/train/models` — Scans model_dir for .safetensors/.ckpt files grouped by subfolder

**Settings router additions** (`klippbok/api/routers/settings.py`):
- `GET /settings/tools` — Returns onetrainer_path and model_dir from global config
- `PUT /settings/tools` — Validates paths exist, saves to global config under 'onetrainer' key

### Frontend (Task 2)

**Hooks**:
- `useTrainingEvents.ts` — EventSource hook for training SSE events. Handles training_progress (epoch/total), training_error (message/log_snippet), training_done (lora_path/epochs/duration)
- `useGpuStatus.ts` — TanStack Query polling hook. Polls /export/train/status every 30s. Returns { gpuBusy, trainingActive, vramUsedMb }

**Export components**:
- `ModelPicker.tsx` — Fetches model list, groups by subfolder with optgroups, links to Settings if empty
- `TrainingConfig.tsx` — Form: base model picker + rank/alpha/epochs/batch/lr/resolution fields
- `TrainingPanel.tsx` — Full 5-state machine:
  - Not configured: message + link to Settings
  - Ready: TrainingConfig form + Start Headless + Open GUI buttons
  - Training: epoch progress bar + TensorBoard iframe + Stop button
  - Complete: success banner (lora_path, epochs, duration) + TensorBoard + New Training button
  - Error: error message + monospace log snippet + Retry button

**Page updates**:
- `ExportPage.tsx` — TrainingPanel shown below ExportProgress when result is non-null AND trainer === 'onetrainer'
- `SettingsPage.tsx` — External Tools section with OneTrainer path input (+ Auto-detect button), model dir input, Save Tool Settings button
- `CleanupPage.tsx` — GPU busy banner + Start Cleanup Scan disabled with tooltip when gpuInUse
- `CuratePage.tsx` — GPU busy banner + Start Curation no-op when gpuInUse
- `TriagePage.tsx` — GPU busy banner + Run Triage and Compute Face Embeddings disabled when gpuInUse

**CSS**: Training panel styles, TensorBoard iframe sizing, model picker, training config grid, GPU banners, completion banner, error panel with monospace pre.

## Decisions Made

- GPU busy guard uses `gpuBusy || trainingActive` — catches both direct VRAM use and klippbok-launched training
- TrainingPanel only shown for OneTrainer trainer since preset_path concept is OT-specific
- `useGpuStatus` uses TanStack Query refetchInterval for efficient polling without manual setInterval
- TensorBoard iframe rendered inside training panel — stays visible after completion for loss curve review
- CuratePage passes a no-op function when GPU busy rather than modifying CurationConfig props interface (avoids cascading prop changes)

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

All created files verified to exist. All commits verified in git log:
- 2fae0cd: feat(08-04): add training API endpoints and settings tools
- 0d83567: feat(08-04): training panel UI, settings tools, and GPU busy guards
