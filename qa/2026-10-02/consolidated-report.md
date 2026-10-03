# Consolidated QA Report — regengine/RegEngine

- **Date:** 2026-10-02
- **Scope:** private repo `regengine/RegEngine`, default branch `main`, static READ-ONLY review
- **Access:** no git clone; all content via GitHub API (`/git/trees/main?recursive=1` → 3,832 files, not truncated; selective `/contents/{path}` fetches)
- **Passes:** backend (static, OWASP API-lite), frontend (static, Next.js App Router), UX (static README/docs walkthrough)
- **Files changed:** none. **What changed:** n/a (read-only).
- **Tests run:** none — static review only. No test was executed, the app was never run, no browser was used, no signup/login attempted, no API calls made, no secrets touched.

## Executive summary

RegEngine is a pre-production, API-first FSMA 204 traceability evidence platform: one consolidated FastAPI app (`server/main.py` → `gunicorn server.main:app`) behind a Next.js frontend, Postgres (Alembic-owned schema) + Redis, with tenant isolation enforced by RLS, a canonical tenant resolver, and a fail-closed middleware. The codebase shows the marks of sustained security remediation: peppered API-key hashes, digest-only OTP storage, timing-safe secret comparison, envelope-normalized errors, SHA-pinned workflow tooling, hash-pinned dependencies, and unusually honest control docs (README "Important Limitations", a copy-remediation plan that prosecutes its own marketing claims).

The review found **no Critical** issues. The heaviest items are product/posture decisions rather than code bugs:

1. **The supplier-remediation workflow is implemented but cannot run in production** — `remediation` is a boot-critical `COMPLIANCE_ROUTERS` member yet is deliberately excluded from the 25-name production router allowlist (`server/router_policy.py`), and the README acknowledges the exclusion. Meanwhile `PRODUCTION_SURFACE.md` still describes it as boot-critical. For a compliance product whose pitch includes supplier correction, "implemented but not deployable" is the decision Christopher most needs to own.
2. **Webhook HMAC signature verification is opt-in** — with `WEBHOOK_HMAC_SECRET` unset (the default), API-key auth alone guards event ingest, and the code comments admit a leaked key is then sufficient to forge a tenant's supply-chain events. Documented migration state, but the default production posture is worth confirming.
3. **Frontend/marketing copy contains claims the repo's own 2026-08-02 copy audit flags as false or misleading** (pricing contradictions, legal-entity inconsistency, fabricated-evidence language, hardcoded audit actors, synthetic audit-log rows). Status of the remediation PR batches could not be verified statically — treat as open.
4. **Metered billing accumulates usage that is never reported to Stripe automatically** — no scheduler job, no frontend surface; an operator must call the report endpoint per tenant. Disclosed in the README; a revenue-operations gap if anyone assumes otherwise.

**Ghost-workflow verification (explicit):** `.github/workflows/` on `main` contains 24 files (listed below). No file is named `BuildFailed`; a case-insensitive search for `buildfailed` across all 3,832 tree entries returned zero matches. The orphaned workflow record (id 342065254, blank name, path literally `BuildFailed`, state `deleted`) cannot correspond to any file on current `main`. **Confirmed: no main-branch workflow file could match the orphan record.** (inflow-lab wf 370344878 is a different repo, out of scope.)

## Severity-rated findings

### High
*None.*

### Medium

**M-1 — Supplier remediation: boot-critical in code, excluded from production, docs conflict.**
- `server/router_policy.py:88-96` — `COMPLIANCE_ROUTERS` includes `remediation`; non-prod boot raises `RuntimeError` if it's disabled without `ALLOW_DISABLE_COMPLIANCE_ROUTERS=true` (`:158-164`).
- `server/router_policy.py:55-81` — `PRODUCTION_ENABLED_ROUTERS` (25 names) omits `remediation`; the production exact-match check (`:143-156`) rejects any `ENABLED_ROUTERS` that adds it.
- `README.md` — "Supplier CSV manifest remediation (implemented; **excluded from the production router allowlist**)"; the buyer dashboard "requires the remediation API to be enabled".
- `PRODUCTION_SURFACE.md` — lists `remediation` under "Boot-critical routers" as compliance-critical.
- The token-scoped supplier flow itself is well-built (`services/ingestion/app/remediation/supplier_router.py`: single-use link exchange → 30-min session, token-hash-only storage, fragment-carried tokens, attested append-only corrections, uniform error bodies). It just can't run in production.
- **Decision needed (Christopher):** is supplier remediation part of the production FSMA story? If yes, it needs promotion into the production allowlist with the tenant/auth/contract tests the Promotion Rule requires. If no, `PRODUCTION_SURFACE.md` and the README's capability framing should say so plainly, because a buyer's technical evaluator will read "implemented" as "available".

**M-2 — Webhook HMAC verification is fail-open when `WEBHOOK_HMAC_SECRET` is unset.**
- `services/ingestion/app/webhook_router_v2/security.py:98-103` (docstring): "API-key auth alone makes any key leak (logs, proxies, .env) sufficient to forge a tenant's supply-chain events."
- `security.py:124-132`: unset secret → verification skipped ("migration ramp"), with `webhook_hmac_configured()` exposed for `/health` alarming ("F-5").
- `.env.example` does not set it, so every fresh deploy defaults to key-only ingest.
- **Action:** confirm `WEBHOOK_HMAC_SECRET` is set in production and the `/health`-based alarm is wired; consider a loud boot log (not the secret) when unset in production. Documented as intentional — this is a confirm-don't-fix item unless the migration ramp is meant to be over.

**M-3 — `PRODUCTION_SURFACE.md` no longer describes `server/router_policy.py`.**
- Doc says exposure is controlled by `DISABLED_ROUTERS` / `ENABLE_EXPERIMENTAL_ROUTERS`, with compliance-router disables raising at import.
- Code: production **rejects** `DISABLED_ROUTERS` (`router_policy.py:120-124`) and `ENABLE_EXPERIMENTAL_ROUTERS` (`:125-129`) outright; `ENABLED_ROUTERS` must match the approved 25-name set exactly (`:131-156`). The escape hatch is local/test-only.
- Also: `proof_recall` line ref "server/main.py:654" is stale (actual mount 658-661); the doc's most important live claim — "Neither [proof_verify/proof_recall] has a recorded sign-off against the Promotion Rule — that review is outstanding (#2838)" — stands.
- **Action:** rewrite the "Current Router Control" section to describe the exact-allowlist model; refresh line refs.

**M-4 — Frontend/marketing copy claims flagged false by the repo's own audit (status unverified).**
- `frontend/COPY_REMEDIATION_PLAN.md` (2026-08-02) records, verified against code/FDA/Federal Register: three-way pricing contradiction ($425/$549/$639 vs $999/$1299/$1499 vs $425–$749/mo); legal entity "RegEngine Inc. / Los Angeles, CA" (Terms) vs "RegEngine, Inc. / Wilmington, Delaware" (DPA); support-response promises inconsistent; "pre-production" vs production plans; workspace/tenant/account used interchangeably in UI; docs promise "free developer account in minutes" while `/developers` is request-gated; demo flow renders "Integrity Status: VERIFIED" / "100% unbreakable provenance linking" over sample output; "customer interviews", "retailers are already requiring traceability NOW", named real companies in `/fsma/market` ("75+" over 48 entries); `dashboard/compliance` "FSMA 204 Compliant — meets current FDA requirements"; audit-log "Compliant with 21 CFR Part 11 … SOX" + "Tamper-proof" badge; recall-report "ready to respond to a 24-hour FDA records request"; CFR citation `§ 1.1330` should be `§ 1.1345`; non-CTE sample event types (`transport`, `quality_check`, `CREATION`); hardcoded `'dashboard_user'` audit actor; synthetic client-side audit-log rows + decorative "Chain Verified" stat.
- The plan is written as a to-do list of PR batches (PR-1…PR-6); nothing in this static pass could confirm they landed. `pyproject.toml` still carries `admin@regengine.io` (wrong domain per the plan) at HEAD — one data point suggesting at least some items are still open.
- **Decision needed (Christopher):** confirm whether the COPY_REMEDIATION_PLAN PR batches shipped; if not, the public site is making regulatory and evidentiary claims engineering has already judged misleading.

**M-5 — Obligation-check / compliance-alert writes fail silently on DB errors.**
- `services/ingestion/app/webhook_router_v2/validation.py:_check_obligations`: rules SELECT failure → savepoint rollback, `return []`; per-alert INSERT failure → savepoint rollback + `logger.warning`; outer catch-all → `return []`. Ingest succeeds with no compliance alerts and no surfaced signal (no metric, no response field) that the obligation pass was skipped.
- Fail-open direction (availability over alerting) is defensible; the missing piece is observability — an operator cannot distinguish "no obligations applied" from "obligation check crashed". Recommend a counter/log at warning level and/or a response flag.

### Low

**L-1 — `kdes` dict and `traceability_lot_code` lack size caps** (`services/ingestion/app/webhook_models.py:177,184-186`). Batch capped at 500 events, `product_description` at 500 chars, but `kdes: Dict[str, Any]` is unbounded and `traceability_lot_code` has only `min_length=3`. No explicit request-body size limit found in fetched files. Tenant-scoped rate limiting (`routes.py:127`) mitigates unauthenticated abuse; consider a body cap or per-field cap for hostile-tenant scenarios.

**L-2 — `requirements.in:2-3` references `[tool.poetry.dependencies]`; no poetry section exists.** `pyproject.toml` has only `[project]` metadata; the real mechanism is pip-tools (`requirements.lock` = `pip-compile --generate-hashes`, verified `==` pins with multi-hash entries). Stale comment; hygiene itself is good.

**L-3 — `frontend/src/hooks/use-api-query.ts` (the "PREFERRED pattern") throws generic `API error: {status} {statusText}`** on failure, while the older `frontend/src/lib/api-client.ts:488-499` carefully normalizes mixed backend envelopes. Pages on the preferred hook show raw HTTP status text unless they map statuses themselves. UX-consistency, not security.

**L-4 — `frontend/src/components/ui/spinner.tsx` has no `role="status"` / accessible loading text**; screen readers get no loading announcement. The login page already uses `role="status"`/`role="alert"` on `Callout`s (`PasswordlessEntryClient.tsx:145-172`), so the pattern exists — the shared primitive just doesn't use it.

**L-5 — `frontend/PAGE_AUDIT.md` (2026-07-13) vs `frontend/next.config.js`:** audit says `/compliance/*` is still shadowed by a catch-all redirect "pending founder decision (#1183)"; the config at HEAD redirects only the bare `/compliance` path with a comment describing the catch-all as the fixed past. Either the audit is stale or the config regressed — config reads like the fix. Update/close the audit note.

**L-6 — Silent OTP dead end without Resend.** README documents that without `RESEND_API_KEY` (unset in `.env.example`, not even listed), "codes are not delivered at all — the challenge flow drops the code with only an error log," while the login page promises "a sign-in code is on its way." A new developer exercising login locally hits a silent dead end. Recommend a dev-mode banner or README note in the local-dev section.

**L-7 — Metered billing never reports to Stripe on its own.** README "Important Limitations" (verified): nothing periodically calls `report_tenant_usage_to_stripe`; usage accumulates in `billing.tenant_usage_counters` until an operator calls `POST /api/v1/billing/usage/report`; no scheduler job ("documented, unbuilt follow-up"), no frontend surface; opt-in assumes a manually-created `regengine_label_events` Stripe meter; `GET /usage` period is a local calendar-month approximation of the Stripe invoice anchor; v121 migration has no dedicated migration test and its `billing.*` tables sit outside the RLS coverage gate (`tests/migrations/test_rls_coverage.py` sweeps `fsma` + curated `public` only — README discloses). Disclosed honestly; the risk is operational/revenue (usage billed late or never) and RLS posture not CI-locked.

**L-8 — Control-doc aging.** `ARCHITECTURE.md` "Last verified: 2026-07-31" (partial 2026-08-26 for Alembic head only); `frontend/PAGE_AUDIT.md` 2026-07-13; `frontend/docs/accessibility_audit.md` 2026-01-27. The verification-date banner pattern is good; the dates are aging on docs that make security-adjacent claims.

### Verified strengths (no action)
- Tenant isolation: `TenantContextMiddleware` fails closed, rejects spoofed `X-RegEngine-Tenant-ID` without valid `REGENGINE_INTERNAL_SECRET` (timing-safe compare), resets RLS contextvar per request, cardinality-safe spoof counter (`services/shared/middleware/tenant_context.py`).
- API keys: peppered HMAC-SHA256 with legacy-SHA256 fallback candidates; lookup via session GUC, never raw in SQL (`services/shared/api_key_store.py:71-144`).
- OTP: `generate_secure_otp()` with digest-only persistence, TTL, attempt counting, rate-limited generation (`challenges_router.py:207,229-235`).
- Stripe webhooks: signature verified via `stripe.Webhook.construct_event` **before** rate-limit consumption (#2929); dedup claim released on handler failure so failed events stay retryable (#2818); missing secret → 500 (`stripe_billing/webhooks.py:698-760`).
- `IngestEvent` validation: enum CTE types, `quantity gt=0`, timestamp/future guards, GLN check-digit, required-KDE per CTE, location-required model validator (`webhook_models.py`).
- Error handling: centralized normalized `{type, message}` envelope, 5xx sanitization, Sentry tenant/correlation tagging (`services/shared/error_handling.py`, wired `server/main.py:378-380`); `E_TENANT_MISMATCH`/`E_NO_PRINCIPAL`/`E_NO_TENANT` codes verified in `services/shared/tenant_context.py:110-183`.
- Secrets: no live secrets in tree; `.env.example` placeholder-only; `.gitignore` covers `.env*`; `.gitleaks.toml` extends upstream defaults (with a documented #2809 fix); security workflow pins all action SHAs and privileged installs; `CREDENTIAL_ROTATION_RUNBOOK.md` at HEAD is policy-only (the 2026-08-02 S1 secret-in-doc concern appears remediated for HEAD).
- Public proof endpoints: 5MB/64-entry/25MB-decompressed guards, zip-slip rejection, Merkle recompute, fail-closed on missing declared root, 10/min and 5/min IP rate limits, zero DB imports (`proof_verify_router.py`, `proof_recall_router.py`).
- Login page: open-redirect protection, no user enumeration, double-submit guard (`PasswordlessEntryClient.tsx`).
- README: all 16 Documentation-Map links resolve against the main tree; "Important Limitations" section is unusually candid (dual-write cutover, billing follow-ups, auth caveats).

## What was NOT tested
- No test execution of any kind (unit, integration, e2e). The repo's suites (`pytest`, `npm run test:run`, Playwright) were not run.
- No live run: the app was never booted, no Docker/DB, no API calls, no browser rendering.
- No secrets-dependent paths exercised (Stripe, Resend, Supabase, webhooks).
- ~3,800 of 3,832 files were not opened; findings rest only on the ~30 files fetched (listed in the per-pass logs).
- Copy findings (M-4) were not re-verified against current pages — they are reported from the repo's own 2026-08-02 audit as open-by-default.

## Remaining risks
1. **Unreviewed surface:** the static sample covered auth/tenant/ingest/billing/proof/docs; Alembic migration SQL, scheduler jobs, EPCIS/EDI parsers, CSV ingest internals, email ingest, NLP/graph services, and 163 frontend pages were not reviewed. A focused second pass on `services/scheduler/` and `services/ingestion/app/csv*` would close the highest-value gaps.
2. **Doc drift compounds:** PRODUCTION_SURFACE.md (M-3), PAGE_AUDIT.md (L-5), and ARCHITECTURE.md dates (L-8) are drifting from code. The repo's convention ("verify against code, not docs") is right but only works if someone keeps doing it.
3. **Copy risk is now the top external risk:** engineering controls look solid; the misleading-claims surface (M-4) is what a prospect, auditor, or regulator actually sees.
4. **Billing operations:** metered usage with no automatic Stripe reporting (L-7) is a revenue-leakage vector the moment any tenant is metered.
5. **Live state unknown:** nothing here asserts production deploy state — `ENABLED_ROUTERS`, `WEBHOOK_HMAC_SECRET`, `RESEND_API_KEY`, Stripe meter existence, and the dual-write cutover flags must be read from the deployed environment, not the repo.

## Recommended next step
Decide M-1 (is supplier remediation a production capability?) and confirm M-4's status (did the copy-remediation PR batches ship?) — both are Christopher decisions, not engineering tasks. Then: (a) rewrite `PRODUCTION_SURFACE.md`'s "Current Router Control" for the exact-allowlist model; (b) confirm `WEBHOOK_HMAC_SECRET` is set in production with the `/health` alarm wired; (c) add observability to the obligation-check skip path (M-5). If a second QA cycle is wanted, point it at `services/scheduler/`, CSV ingest, and the Alembic migration SQL, which this pass did not cover.

## Anything needing Christopher's decision
1. **M-1:** Promote `remediation` into the production router allowlist (with Promotion-Rule tests), or declare it out of the production contract and fix `PRODUCTION_SURFACE.md` accordingly.
2. **M-4:** Did the `frontend/COPY_REMEDIATION_PLAN.md` PR batches (PR-1…PR-6, incl. pricing/entity/support-promise decisions D1–D10) ship? Several appear open (e.g. `admin@regengine.io` still in `pyproject.toml`).
3. **M-2:** Is the webhook-HMAC "migration ramp" over — i.e., should `WEBHOOK_HMAC_SECRET` be mandatory in production?
4. **L-7:** Who calls `POST /api/v1/billing/usage/report`, on what schedule — or is metered billing intentionally manual for now?

## Appendix — `.github/workflows/` on main (24 files)
agent-sweep.yml, api-surface-issue.yml, backend-ci.yml, bundle-analysis.yml, demo-smoke.yml, dependabot-lock-sync.yml, deploy.yml, frontend-ci.yml, inflow-contract-ci.yml, infra-k8s-ci.yml, legacy-code-scan.yml, openapi-public-spec.yml, pr-gate.yml, pr-quality.yml, production-uptime.yml, proxy-smoke.yml, public-api-surface.yml, qa-health.yml, qa-pipeline.yml, review-gates.yml, sdk-ci.yml, security.yml, sentinel.yml, test-suite-check.yml.
