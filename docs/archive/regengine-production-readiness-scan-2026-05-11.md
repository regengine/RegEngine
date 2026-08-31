> **ARCHIVED — HISTORICAL SNAPSHOT, NOT CURRENT STATE.**
>
> This report describes RegEngine as it stood on **2026-05-11**. It was moved
> from the repository root to `docs/archive/` on 2026-08-27 (#2872) because a
> root-level file reads as current status, and parts of it have since drifted.
> Do not cite it as the present state of the codebase.
>
> Known-stale claims, left in place rather than rewritten so the snapshot stays
> an honest record of what was true on the scan date:
>
> - PROD-001 states `next` is pinned to `16.2.6`. It is now `16.3.1`
>   (`frontend/package.json`).
> - PROD-002 cites `pip-audit -r cli/requirements.txt`. That file no longer
>   declares any dependency — it is a deprecation stub (#2894).
>
> Still accurate as of the archive date: the locked `urllib3` is `2.7.0`, and
> the PROD-001 remediation is live — `frontend/scripts/production-readiness.mjs`,
> the `readiness:production` npm script, and the blocking `Production Readiness
> Gate` job in `.github/workflows/frontend-ci.yml` all still exist. This file is
> the record of why that gate was added, which is why it was archived rather
> than deleted.
>
> The preview URL and deployment id have been redacted; they embedded the Vercel
> account slug.
>
> The unresolved "Testing Gap" section at the end was never closed here; treat it
> as an open question, not a completed verification.

---

# Production Readiness Scan

Date: 2026-05-11

Target deployment: _(preview URL redacted — it embedded the Vercel account slug, #2872)_

Deployment id: _(redacted, #2872)_

## Executive Summary

Status: **Ready to merge.**

The auth/session fix preview built and deployed successfully, the login and session endpoints respond with the expected security headers, and required production auth environment variables are present in Vercel. The previous blocker was cleared by upgrading Next.js from `16.2.4` to `16.2.6` and adding an automated production-readiness gate.

## Findings

### PROD-001: High-severity Next.js advisory blocks production

Severity: High, resolved

Location: `frontend/package.json`, dependency `next`

Evidence:

- `frontend/package.json` now pins `next` to `16.2.6`.
- `npm audit --audit-level=high` reports `found 0 vulnerabilities`.
- `npm run readiness:production` reports `Production readiness gate passed.`
- `npm view next@16.2.6 version dist-tags --json` reports `16.2.6` as available and tagged `latest`.

Impact:

Several advisories affect the current Next.js range, including middleware/proxy bypass, cache poisoning, XSS, SSRF, and denial-of-service classes. Because this app relies on Next.js proxy/middleware for auth and CSRF controls, this should be treated as a promotion blocker.

Fix applied:

- Upgraded `next` to `16.2.6`.
- Added `frontend/scripts/production-readiness.mjs`.
- Added `npm run readiness:production`.
- Added a blocking `Production Readiness Gate` job to `.github/workflows/frontend-ci.yml`.

### PROD-002: Python dependency audit blocks merge

Severity: High, resolved

Location: `requirements.lock`, dependency `urllib3`

Evidence:

- `requirements.lock` now pins `urllib3` to `2.7.0`.
- `pip-audit -r requirements.lock` reports `No known vulnerabilities found`.
- `pip-audit -r cli/requirements.txt` reports `No known vulnerabilities found`.

Fix applied:

- Updated the locked `urllib3` version and hashes from `2.6.3` to `2.7.0`.
- Refactored a test-only JWT rollout fixture to avoid a detect-secrets false positive and refreshed `.secrets.baseline` line metadata.

## Verified Good

- Preview deployment is `Ready` according to `vercel inspect <deployment-id>` (id redacted, #2872).
- Vercel Production env includes `AUTH_SECRET_KEY`, `JWT_SIGNING_KEY`, `CSRF_SECRET`, `ALLOWED_ORIGINS`, `ADMIN_SERVICE_URL`, `NEXT_PUBLIC_ADMIN_URL`, `INGESTION_SERVICE_URL`, `COMPLIANCE_SERVICE_URL`, and `GRAPH_SERVICE_URL`.
- `/login` returns `HTTP/2 200` through `vercel curl`, with enforced `Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and HSTS.
- `/api/session` returns `HTTP/2 200`, `Cache-Control: no-store`, sets `re_csrf` and `re_csrf_sig`, and returns an unauthenticated session shape without exposing tokens.
- Preview runtime error logs: none found for the target deployment in the last 10 minutes.
- Production error logs: none found in the last hour.
- Focused auth/session tests pass: 83 tests across proxy sanitization, session origin, login, and instrumentation.
- ESLint passes for the touched auth/session files.
- `npm audit --audit-level=high` reports `found 0 vulnerabilities`.
- `pip-audit -r requirements.lock` reports `No known vulnerabilities found`.
- `detect-secrets-hook` passes with the committed baseline.
- `npm run build` passes with Next.js `16.2.6`.
- `git diff --check` passes for the auth/session patch.

## Testing Gap

The preview URL is protected by Vercel authentication in a plain browser session, so unauthenticated browser-based verification lands on Vercel login. `vercel curl` can verify the deployment through Vercel's protection bypass, but a real browser login flow still needs testing by someone with preview access or after temporary preview protection bypass is configured.
