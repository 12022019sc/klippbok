# Phase 2: Model Configuration - Context

**Gathered:** 2026-02-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can select a target model (SD1.5, SDXL, Flux, custom) and get correct resolution presets, bucket sizes, and captioning defaults automatically — with full override capability. This phase delivers the model profile system and configuration layer. It does NOT deliver UI for selecting models (that's Phase 4+) or captioning logic (Phase 6).

</domain>

<decisions>
## Implementation Decisions

### Built-in model profiles
- Four built-in profiles: SD1.5, SDXL, Flux, Pony
- SD1.5: 512px base resolution, booru-style caption default
- SDXL: 1024px base resolution, natural language caption default
- Flux: single profile (covers both dev and schnell), 1024px base, natural language caption default
- Pony: SDXL-based (1024px base), booru-style caption default
- Profiles include training hyperparameter hints (learning rate ranges, network rank suggestions) for use in Phase 8 export config generation

### Override behavior
- Overrides apply per-project (one model profile per project)
- When a value is overridden, the original model default is shown as reference (e.g., "Resolution: 768px (default: 512px)")
- Overrides stored in a separate config file (.klippbok/model_config.json), not in the project manifest
- Individual field reset supported — each overridden field can be reset to default independently

### Custom model creation
- Custom profiles created by cloning an existing built-in profile and modifying it
- Stored at user level (~/.klippbok/) — available across all projects
- Minimum required fields: name, base resolution, caption style (booru vs natural language)
- No import/export for now — custom profiles are local only

### Bucket calculation
- Claude's Discretion: bucket generation method (pixel budget vs fixed dimension steps) — pick based on what trainers actually expect
- Claude's Discretion: dimension step size — configurable vs fixed, pick the practical approach
- Buckets are auto-generated from parameters only — no manual add/remove of individual buckets
- Claude's Discretion: aspect ratio range — pick based on common trainer defaults

</decisions>

<specifics>
## Specific Ideas

- Training hints in profiles should be useful for Phase 8 export config generation (kohya TOML, ai-toolkit YAML, etc.)
- Override display should make it clear what's changed vs default without cluttering the interface

</specifics>

<deferred>
## Deferred Ideas

- Profile import/export for sharing custom profiles — add when needed
- Per-dataset model profiles within a project — current decision is per-project only

</deferred>

---

*Phase: 02-model-configuration*
*Context gathered: 2026-02-27*
