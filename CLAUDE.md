# CLAUDE.md — Project Instructions

---

## Critical Rules

### 0. NEVER Publish Sensitive Data

- NEVER commit passwords, API keys, tokens, or secrets to git/npm/docker
- NEVER commit `.env` files — ALWAYS verify `.env` is in `.gitignore`
- Before ANY commit: verify no secrets are included
- NEVER output secrets in suggestions, logs, or responses

### 5. NEVER Hardcode Credentials

- ALWAYS use environment variables for secrets
- NEVER put API keys, passwords, or tokens directly in code
- NEVER hardcode connection strings — use DATABASE_URL from .env

### 6. ALWAYS Ask Before Deploying

- NEVER auto-deploy, even if the fix seems simple
- NEVER assume approval — wait for explicit "yes, deploy"
- ALWAYS ask before deploying to production

### 7. Quality Gates (soft warnings, not blockers)

- Source files > 500 lines should be reviewed for splitting opportunities
- Functions > 50 lines should be reviewed for extraction opportunities
- Test files are exempt from line limits
- All tests must pass before committing

### 8. Parallelize Independent Awaits

- When multiple `await` calls are independent, ALWAYS use `Promise.all` (or `asyncio.gather` in Python)
- NEVER await independent operations sequentially

### 9. Git Workflow — NEVER Work Directly on Main

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
project/
├── CLAUDE.md              # You are here
├── CLAUDE.local.md        # Personal overrides (gitignored)
├── .claude/
│   ├── commands/          # Slash commands
│   ├── hooks/             # Enforcement scripts
│   ├── skills/            # Triggered expertise
│   └── agents/            # Custom subagents
├── project-docs/
│   ├── ARCHITECTURE.md    # System overview & data flow
│   ├── INFRASTRUCTURE.md  # Deployment & environment details
│   └── DECISIONS.md       # Why we chose X over Y
├── src/                   # Application source
├── tests/                 # Test files
└── scripts/               # Dev/build scripts
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

---

## Naming — NEVER Rename Mid-Project

Renaming packages, modules, or key variables mid-project causes cascading failures. If you must rename:

1. Create a checklist of ALL files and references first
2. Use IDE semantic rename (not search-and-replace)
3. Full project search for old name after renaming

---

## Plan Mode — Plan First, Code Second

For any non-trivial task, start in plan mode. Use plan mode for: new features, refactors, architectural changes, multi-file edits.

---

## Workflow Preferences

- Quality over speed — if unsure, ask before executing
- Plan first, code second — use plan mode for non-trivial tasks
- One task, one chat — `/clear` between unrelated tasks
