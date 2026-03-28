# RegEngine Full-Feature Debug Report

**Date:** 2026-03-27 | **Scope:** All services, frontend, infra, tests | **Initiated by:** Christopher

---

## Executive Summary

Four parallel debug scans covered backend services, frontend, infrastructure/CI, and test suite. **41 issues found** across all layers. The platform is fundamentally solid — no SQL injection, no broken imports, auth on 99% of endpoints — but there are actionable gaps that need closing before production.

| Severity | Count | Effort |
|----------|-------|--------|
| Critical | 6 | ~4 hours |
| Warning/High | 14 | ~6 hours |
| Medium | 11 | ~4 hours |
| Low/Info | 10 | — (backlog) |

---

## Critical Issues (Fix Before Deploy)

### 1. Secrets Committed to Git History
**Files:** `.env`, `frontend/.env.local`
**Impact:** 8 hardcoded production credentials (MinIO, Neo4j, Admin key, auth tokens, Supabase keys) are in git history even though `.gitignore` covers them.
**Fix:** `git filter-branch` to remove from history → rotate ALL secrets in production → force push.
**Effort:** 2-3 hours (includes secret rotation)

### 2. localStorage Auth Token Remnants (18 instances)
**Files:** 8 frontend files still read `regengine_access_token` from localStorage
**Impact:** PR #327 cookie migration was incomplete. XSS can still steal tokens from localStorage.
**Fix:** Replace all `localStorage.getItem('regengine_access_token')` with cookie-based auth reads via `/api/session`.
**Effort:** 30 minutes

### 3. Unprotected Endpoint — Discovery Queue
**File:** `services/ingestion/app/routes.py:354`
**Impact:** `GET /v1/ingest/discovery/queue` lacks `Depends(require_api_key)`. Unauthenticated access to discovery queue.
**Fix:** Add `_auth=Depends(require_api_key)` parameter.
**Effort:** 2 minutes

### 4. CI/CD Silently Passes on Failures
**Files:** `backend-ci.yml:192`, `frontend-ci.yml:91,117,136`
**Impact:** `continue-on-error: true` on linting, ESLint, tests, and npm audit means broken code can merge.
**Fix:** Remove `continue-on-error: true` from all test/lint steps.
**Effort:** 10 minutes

### 5. Silent Test Failures via pytest.skip()
**Files:** ~40+ instances across security test files
**Impact:** Tests skip on `ConnectError` instead of failing — security tests pass even when services are down.
**Fix:** Add a `--require-services` flag; in CI, fail instead of skip when services are unreachable.
**Effort:** 1 hour

### 6. SQL Injection Test Accepts 200 as Valid
**File:** Security test suite
**Impact:** A test checking SQL injection payloads accepts HTTP 200 as a passing result — meaning if injection succeeds, the test still passes.
**Fix:** Assert response is 400 only, not 200.
**Effort:** 10 minutes

---

## High / Warning Issues

### 7. Missing Security Headers in next.config.js
No Content-Security-Policy, X-Frame-Options, or HSTS in the frontend config. Ingress headers only protect API routes, not the Next.js app itself.

### 8. NEXT_PUBLIC_API_KEY Fallback in 16 Files
Frontend files use `NEXT_PUBLIC_API_KEY` as auth fallback — this key is baked into the JS bundle and visible to anyone.

### 9. K8s Resource Limits Missing on 3 Deployments
`admin`, `ingestion`, and `scheduler` deployments lack CPU/memory limits. A runaway process can starve the node.

### 10. K8s Ingress Missing Security Annotations
No `force-ssl-redirect`, no `X-Content-Type-Options`, no CSP in ingress annotations.

### 11. Generic Exception Handlers (8 instances)
`webhook_router_v2.py`, `compliance_score.py`, `product_catalog.py` still use `except Exception:` catching everything including `SystemExit` and `KeyboardInterrupt`.

### 12. Frontend Dockerfile Runs as Root
No `USER` directive — container runs as root, expanding blast radius of any exploit.

### 13. Missing Error Boundaries (20+ routes)
Only 3 route directories have `error.tsx`. The rest will show a white screen on crash.

### 14. PII in localStorage (FTL Checker)
User email stored in localStorage without encryption.

### 15. Hardcoded Localhost Fallbacks (5 backend configs)
Config files fall back to `localhost:XXXX` when env vars are unset — silent misconfiguration in production.

### 16. Frontend E2E Tests — Weak Assertions (90+ instances)
Broad accept ranges (e.g., status code 200 OR 400 OR 401 OR 403) mean tests pass regardless of behavior.

### 17. test-all.sh Doesn't Implement 4-Stage QA Model
The script runs basic checks, not the described Fast Gate → System Sim → AI Analysis → Decision Gate pipeline.

### 18. Missing __init__.py in 15+ Test Directories
Test discovery may silently skip entire directories.

### 19. Incomplete CSRF/JWT Rotation Test Coverage
CSRF double-submit and JWT `kid` rotation have tests but don't cover edge cases (expired CSRF, rotated-away key).

### 20. Scheduler Missing Readiness Probe
K8s deployment has no readiness probe — traffic routes to the pod before it's ready.

---

## Medium Issues

21. Hardcoded test credentials in conftest.py
22. 15+ `sleep()` calls in tests instead of polling/retry
23. Missing fixture scope specifications
24. Shallow health checks in test-all.sh (HTTP 200 only, no body validation)
25. Playwright retries disabled locally
26. Shared test database (no isolation between test runs)
27. Critical service coverage gaps (scheduler: 3 files, compliance: 2 files)
28. No test documentation/docstrings
29. Missing edge case tests (rate limiting, DoS, malformed JWT)
30. `pg` dependency in frontend package.json (unused)
31. Hardcoded test URLs prevent CI/staging testing

---

## What's Clean (No Issues Found)

- SQL injection surface area (SafeQueryBuilder used correctly)
- Import resolution (all paths valid across all services)
- TypeScript typing (no problematic `any` types remaining)
- Route integrity (no dead links in frontend)
- API endpoint matching (frontend ↔ backend routes align)
- No race conditions in backend services
- No dead code blocks
- Auth guards on 99% of endpoints (1 exception noted above)

---

## Recommended Fix Order

| Priority | Items | Time | Gate |
|----------|-------|------|------|
| **P0 — Today** | #1 (secrets), #2 (localStorage), #3 (auth gap), #4 (CI), #6 (test assertion) | 4 hrs | Before any deploy |
| **P1 — This week** | #5 (test skips), #7-10 (security headers, K8s), #12 (Dockerfile) | 4 hrs | Before production |
| **P2 — Next sprint** | #11, #13-20 (error boundaries, test quality) | 6 hrs | Before investor demo |
| **Backlog** | #21-31 (medium items) | 4 hrs | As capacity allows |

---

## Detailed Reports

- Backend scan: `RegEngine-Debug-Report.md`
- Frontend scan: `RegEngine_Frontend_Debug_Report.txt`
- Test suite scan: `RegEngine_Debug_Report.md` (working dir)
