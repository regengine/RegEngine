---
name: Python Services
applyTo: "{services,tests,scripts}/**/*.py"
description: Backend Python service conventions for RegEngine.
---

# RegEngine Python service rules

- Shared imports come from `services/shared/`.
- For service entrypoints and tests that need `from shared import ...`, follow existing `ensure_shared_importable()` bootstrap patterns from `services/shared/paths.py`.
- Use type hints and keep changes narrow.
- Preserve existing FastAPI patterns, dependency injection, and middleware setup.
- Prefer parameterized database and Cypher access.
- Add or update tests in the nearest existing `tests/` directory for the service you change.
- Use repo-root pytest commands such as `python -m pytest services/<service>/tests -q`.
- Do not replace real verification with made-up `make` commands.
