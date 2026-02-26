---
paths:
  - "**/test_*.py"
  - "**/*_test.py"
  - "**/tests/**"
  - "**/*.test.*"
---

# Testing Rules

When writing tests, load the ce:writing-tests skill for general patterns.

## Flaky Tests

When fixing flaky tests, load the ce:fixing-flaky-tests skill.

| Symptom | Likely Cause |
|---------|--------------|
| Passes alone, fails in suite | Shared state |
| Random timing failures | Race condition |
