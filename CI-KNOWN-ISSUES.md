# CI Known Issues & Pre-Existing Failures

**Last audited:** 2026-03-31 (PR #476)
**Total CI checks:** 55 | **Passing:** 51 | **Failing:** 2 | **Skipping:** 3

---

## 1. SAST (Semgrep) — 64 blocking findings

**Status:** Fails on every PR
**Root cause:** Semgrep flags all `sqlalchemy.text()` usage as potential SQL injection, even when parameterized queries are used correctly with bound `:param` placeholders.

### Finding breakdown

| Rule | Count | Severity | Actual Risk |
|---|---|---|---|
| `avoid-sqlalchemy-text` | 19 files | Blocking | **False positive** — all uses are parameterized with `:param` syntax, not f-string interpolation |
| `detected-username-and-password-in-uri` | 1 file | Blocking | **True positive** — hardcoded test DB URI in `scripts/utilities/db_test.py` |
| `dockerfile.missing-user` | 1 file | Blocking | **Low risk** — `kernel/reporting/Dockerfile` runs without USER directive |

### Files flagged for `avoid-sqlalchemy-text` (all use parameterized queries)

| File | Notes |
|---|---|
| `scripts/regctl/tenant.py` | Admin CLI tool |
| `server/workers/lot_tracing.py` | Lot tracing worker |
| `services/graph/app/fsma_audit.py` | Audit queries |
| `services/ingestion/app/alerts.py` | Alert system |
| `services/ingestion/app/audit_export_log.py` | Audit export |
| `services/ingestion/app/audit_log.py` | Audit logging |
| `services/ingestion/app/auditor_router.py` | Auditor endpoints |
| `services/ingestion/app/canonical_router.py` | Canonical event CRUD |
| `services/ingestion/app/epcis_export.py` | EPCIS export |
| `services/ingestion/app/epcis_ingestion.py` | EPCIS import |
| `services/ingestion/app/exchange_api.py` | B2B exchange |
| `services/ingestion/app/fda_export_router.py` | FDA export |
| `services/ingestion/app/incident_router.py` | Incident management |
| `services/scheduler/app/metrics.py` | Scheduler metrics |
| `services/shared/canonical_persistence.py` | Canonical event persistence |
| `services/shared/cte_persistence.py` | CTE persistence |
| `services/shared/exception_queue.py` | Exception queue |
| `services/shared/identity_resolution.py` | Identity resolution |
| `services/shared/request_workflow.py` | Request workflow |
| `services/shared/rules_engine.py` | Rules engine |
| `services/shared/external_connectors/base.py` | External connector base |

### Recommended fix options

**Option A (preferred): Add `.semgrepignore`** to suppress `avoid-sqlalchemy-text` for files that use parameterized queries. This is the standard approach for codebases that legitimately use `text()` with bound parameters.

```
# .semgrepignore
# These files use sqlalchemy.text() with parameterized queries (:param syntax)
# and are not vulnerable to SQL injection. Semgrep cannot distinguish
# parameterized text() from f-string text().
```

**Option B: Inline `# nosemgrep` comments** on each `text()` call with a justification comment.

**Option C: Fix the 2 real findings** and suppress the false positives:
1. `scripts/utilities/db_test.py` — move DB URI to environment variable
2. `kernel/reporting/Dockerfile` — add `USER` directive

---

## 2. E2E Tests (Playwright) — 46 failures

**Status:** Fails on every PR
**Root cause:** E2E tests require a running frontend (port 3001) and backend (port 8400) with real auth. CI only builds the frontend but does not start backend services or seed test users.

### Test files and failure counts

| Test File | Tests | Failure Reason |
|---|---|---|
| `invite_flow.spec.ts` | 1 | Cannot login — no backend |
| `login-dashboard.spec.ts` | 7 | Cannot login — no backend |
| `rbac-gates.spec.ts` | 7 | Cannot login — no backend |
| `security-audit-fixes.spec.ts` | 18 | Cannot login — no backend |
| `snapshot-creation.spec.ts` | 6 | Cannot login — no backend |
| `tenant-isolation.spec.ts` | 7 | Cannot login — no backend |
| **Total** | **46** | |

All failures are `page.goto('/login')` timing out because no backend serves the login page with auth capabilities.

### Recommended fix options

**Option A (preferred): Skip E2E in CI, run locally/on-demand.** Add `if: github.event_name == 'workflow_dispatch'` to the E2E job so it only runs when manually triggered with a full environment.

**Option B: Add a backend service container** to the E2E workflow using Docker Compose with test credentials and a seeded database.

**Option C: Mark E2E as `continue-on-error: true`** so it reports but doesn't block.

---

## 3. Skipping checks (expected)

| Check | Reason |
|---|---|
| Audit Chain Integrity | Requires `AUDIT_API_BASE` and `AUDIT_VERIFY_TOKEN` secrets — scheduled/manual only |
| Container Scan (Trivy) | Depends on Docker build matrix completion |
| Tenant Isolation & Auth Tests | Requires `TEST_DATABASE_URL` and `TEST_API_BASE` secrets — scheduled/manual only |

These are conditional checks that only run with specific secrets or on schedule. Not failures.

---

## 4. Other pre-existing issues (not CI failures)

### TypeScript type-check warnings (not in CI pipeline)

Running `tsc --noEmit` locally surfaces pre-existing errors in test infrastructure:
- `playwright.config.ts` — missing `@playwright/test` types
- `src/__tests__/**` — missing `vitest`, `@testing-library/react` types
- These are dev dependency resolution issues, not code bugs

### Frontend `package-lock.json` drift

The worktree `npm install` generates a slightly different `package-lock.json` than the main branch. This is normal for worktrees and should not be committed unless intentional dependency changes were made.

---

## Priority action items

| # | Issue | Severity | Effort | Impact |
|---|---|---|---|---|
| 1 | Fix `scripts/utilities/db_test.py` hardcoded DB URI | **High** (real secret) | 5 min | Eliminates 1 true-positive Semgrep finding |
| 2 | Add `USER` to `kernel/reporting/Dockerfile` | **Medium** | 5 min | Eliminates 1 Dockerfile finding |
| 3 | Create `.semgrepignore` for parameterized `text()` | **Medium** | 15 min | Eliminates 19 false-positive findings, makes SAST green |
| 4 | Gate E2E tests behind `workflow_dispatch` | **Low** | 10 min | Makes E2E check green (or remove from required checks) |
