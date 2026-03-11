# CLAUDE.md — Project Instructions

---

## Critical Rules

Security rules (secrets, credentials, deploy gates) inherited from ~/.claude/CLAUDE.md.

### Git Workflow — NEVER Work Directly on Main

**Branch BEFORE editing any files:**

```bash
git branch --show-current
# If on main → create a feature branch IMMEDIATELY:
git checkout -b feat/<task-name>
```

**Branch naming conventions:**
- `feat/<name>` — new features
- `fix/<name>` — bug fixes
- `docs/<name>` — documentation changes
- `refactor/<name>` — code refactors
- `chore/<name>` — maintenance tasks
- `test/<name>` — test additions

---

## When Something Seems Wrong

Before jumping to conclusions:

- Missing UI element? → Check feature gates BEFORE assuming bug
- Empty data? → Check if services are running BEFORE assuming broken
- 404 error? → Check service separation BEFORE adding endpoint
- Auth failing? → Check which auth system BEFORE debugging
- Test failing? → Read the error message fully BEFORE changing code

---

## Project Structure

```
klippbok-main/
├── klippbok/              # Python package
│   ├── api/               # FastAPI server + routers
│   │   ├── routers/       # API endpoints (images, video, captions, crop, triage, etc.)
│   │   └── static/        # Built frontend served here
│   ├── caption/           # AI captioning (Gemini, OpenAI, Replicate, LM Studio)
│   ├── config/            # YAML schema, defaults, config loading
│   ├── dataset/           # Discovery, validation, bucketing, manifest
│   ├── image/             # Autocrop, dedup, quality scoring, bucketing, probe
│   ├── services/          # Business logic layer (caption, crop, face, upscale, video, etc.)
│   ├── triage/            # Embedding-based scene triage and filtering
│   └── video/             # Probing, splitting, frame extraction, scene detection
├── frontend/              # React 19 + TypeScript + Vite + Zustand
│   └── src/
│       ├── components/    # Caption, Crop, Gallery, Video, Layout, Lightbox
│       ├── pages/         # Gallery, Video, Caption, Crop, Triage, Import, Settings, etc.
│       └── stores/        # Zustand state management
├── tests/                 # pytest test suite
├── project-docs/          # ARCHITECTURE.md, DECISIONS.md, INFRASTRUCTURE.md
└── .planning/             # GSD planning artifacts (roadmap, phases, state)
```

---

## Coding Standards — Python

### Type Hints ALWAYS

- Every function MUST have type hints for all parameters AND return type
- Use modern syntax: `str | None` (not `Optional[str]`), `list[str]` (not `List[str]`)

### Testing

- pytest only — NEVER use unittest
- Use `@pytest.mark.parametrize` for table-driven tests
- Every test MUST have meaningful assertions

### Style & Tooling

- Async consistently: FastAPI handlers must be `async def` for I/O operations
- Virtual environment: ALWAYS use `.venv/` — NEVER install packages globally
- Pydantic models: Use `BaseModel` for all request/response schemas
- ruff: Run `ruff check` before committing

### Error Handling

```python
# CORRECT — handle errors explicitly
try:
    user = await get_user_by_id(user_id)
    if not user:
        raise NotFoundError("User not found")
    return user
except Exception as err:
    logger.error("Failed to get user", extra={"id": user_id, "error": str(err)})
    raise

# WRONG — swallow errors silently
try:
    return await get_user_by_id(user_id)
except Exception:
    return None  # silent failure
```

### API Versioning

```
CORRECT: /api/v1/users
WRONG:   /api/users
```

Every API endpoint MUST use `/api/v1/` prefix. No exceptions.
