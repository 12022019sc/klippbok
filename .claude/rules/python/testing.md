---
paths:
  - "**/test_*.py"
  - "**/*_test.py"
  - "**/tests/**/*.py"
---

# Python Testing

Extends the universal testing rules with Python-specific patterns.

## Commands

```bash
pytest                    # Run all tests
pytest -x                 # Stop on first failure
pytest -k "pattern"       # Run matching tests
pytest --tb=short         # Shorter tracebacks
```

## Project Conventions

- Test files use `test_` prefix
- Fixtures in `tests/conftest.py`
- Uses `pytest-tmp-files` for temporary file fixtures
- Test fixtures include sample video clips in `tests/fixtures/`

## HTTP Mocking

Use `respx` for HTTP mocking:

```python
import respx
from httpx import Response

@respx.mock
@pytest.mark.asyncio
async def test_api_call():
    respx.get("https://api.example.com/data").mock(
        return_value=Response(200, json={"key": "value"})
    )
```
