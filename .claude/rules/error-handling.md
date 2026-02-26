---
paths:
  - "**/*.py"
---

# Error Handling

When designing error handling, load the ce:handling-errors skill.

Key principles:
- Never swallow errors silently
- Preserve error context when re-throwing
- Log errors once at the appropriate boundary
