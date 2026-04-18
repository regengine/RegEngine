# Service tests — import conventions

Every service under `services/` ships its own top-level `app/` package, so
multiple `app`s exist side-by-side. Python's module cache only holds one
at a time, which broke cross-service test collection until #1435.

**Pattern for test files under `services/<svc>/tests/`:**

- Use short `from app.X import ...` and `from shared.X import ...`.
- Do NOT add per-file `sys.path.insert(...)` or re-import service dirs.
- The root `conftest.py` switches `sys.path` + invalidates the cached
  `app` module automatically before each collector runs, based on the
  owning service path.

**Pattern for tests under top-level `tests/` that reach into a service:**

- Prefer fully-qualified imports: `from services.<svc>.app.X import ...`.
- If a test must use the short `from app.X` form, add its path to
  `_TEST_TO_SERVICE_OVERRIDES` in the root `conftest.py`.

**Regression guard:** `.github/workflows/test-suite-check.yml` runs
`pytest --collect-only` and fails the build on any ERROR.
