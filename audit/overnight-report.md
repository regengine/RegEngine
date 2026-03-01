# Overnight QA Hardening Report

Date: 2026-03-01

## Scope

This pass focused on the highest-risk user flows and API surfaces called out in the overnight specification:

- Deliver a real `/demo/recall-simulation` experience wired to simulation APIs.
- Harden simulation and EPCIS ingestion endpoint behavior.
- Remove high-visibility dead-end routes/links.
- Reduce placeholder UX in customer-facing routes.
- Document findings in audit artifacts.

## What Was Fixed

### 1) Recall simulation experience is now real and interactive

- Replaced redirect/stub behavior with an interactive client at `frontend/src/app/demo/recall-simulation/RecallSimulationClient.tsx`.
- Implemented scenario-driven run flow and data fetches for:
  - `POST /api/simulations/run`
  - `GET /api/simulations/{id}`
  - `GET /api/simulations/{id}/impact-graph`
  - `GET /api/simulations/{id}/timeline`
  - `GET /api/simulations/{id}/export`
- Added API proxy route at `frontend/src/app/api/simulations/[...path]/route.ts`.

### 2) Simulation API behavior hardened

In `services/ingestion/app/recall_simulations.py`:

- `POST /api/v1/simulations/run` now returns `201 Created`.
- Unknown scenario now returns `400 Bad Request`.
- Scenario listings expose richer metadata (including descriptions).
- Timeline items include location fields for clearer downstream rendering.

### 3) EPCIS ingestion behavior hardened

In `services/ingestion/app/epcis_ingestion.py`:

- Single ingest is idempotent via `eventID` or deterministic payload hash fallback.
- First ingest returns `201`; duplicate ingest returns `200` with `idempotent: true`.
- Batch ingest returns:
  - `400` for empty batch,
  - `207` for mixed success/failure,
  - `201` when all succeed.
- Export endpoint supports filtering (`start_date`, `end_date`, `product_id`) and echoes filters in metadata.

### 4) Dead-end route remediation

- Added/fixed routes so common legacy links resolve:
  - `frontend/src/app/ftl-checker/page.tsx`
  - `frontend/src/app/demo/page.tsx`
  - `frontend/src/app/resources/calculators/page.tsx`
  - `frontend/src/app/contact/page.tsx`
  - `frontend/src/app/api-reference/energy/page.tsx`
- Added docs catch-all fallback at `frontend/src/app/docs/[...slug]/page.tsx`.
- Added public SDK artifact for linked download path: `frontend/public/sdk/verify_chain.py`.

### 5) Placeholder text cleanup

- Removed/reworded high-visibility `Coming Soon` copy in touched app/docs pages.
- Current grep check in `frontend/src/app` reports zero `coming soon` matches.

### 6) Lightweight pytest bootstrap added for local API validation

- Added `services/ingestion/requirements-dev.txt` with a minimal dependency set for focused ingestion API tests.
- Updated `services/ingestion/README.md` with a lightweight local bootstrap flow using a repo-root `.venv` and targeted pytest commands.
- Refactored targeted API tests to mount only required routers (instead of importing full `services/ingestion/main.py`) so they can run without the full service dependency graph:
  - `services/ingestion/tests/test_recall_simulations_api.py`
  - `services/ingestion/tests/test_epcis_ingestion_api.py`

### 7) Touched-page lint triage completed

- Ran ESLint only against modified/new frontend pages touched in this pass.
- Fixed the two blocking lint errors (`react/no-unescaped-entities`) in:
  - `frontend/src/app/docs/aerospace/page.tsx`
  - `frontend/src/app/docs/manufacturing/page.tsx`
- Re-ran targeted lint: **PASS** (no errors in touched files).

## Tests and Verification

### Frontend build

- Command: `npm --prefix frontend run build`
- Result: **PASS** (Next.js production build completes)
- Notes:
  - Existing non-blocking Sentry hook warnings remain.
  - Existing non-blocking data warning during static generation remains (mock fallback path).

### Python validation

- Command:
  `python3 -m py_compile services/ingestion/app/recall_simulations.py services/ingestion/app/epcis_ingestion.py services/ingestion/tests/test_recall_simulations_api.py services/ingestion/tests/test_epcis_ingestion_api.py`
- Result: **PASS** (no syntax errors)

### Pytest runtime

- Commands:
  - `python3 -m venv .venv`
  - `.venv/bin/python -m pip install -r services/ingestion/requirements-dev.txt`
  - `.venv/bin/python -m pytest services/ingestion/tests/test_recall_simulations_api.py services/ingestion/tests/test_epcis_ingestion_api.py`
- Result: **PASS** (`5 passed`)

### Critical journey checks (desktop + mobile)

- Executed Playwright-based browser checks against `next start` on port `4104`.
- Result: **PASS** (`9/9` checks)
- Verified flows:
  - `/demo` resolves into `/demo/supply-chains`
  - recall simulation page CTAs and mocked run flow (timeline + impact graph rendering)
  - retailer readiness path to FTL checker
  - verify page SDK + FTL links
  - white papers links to contact and calculators
  - docs fallback path resolves without 404
  - contact page assessment link
  - mobile rendering of recall simulation hero/CTA

### Targeted frontend lint (touched files only)

- Command: `npx eslint ...` (run against modified/new touched pages only)
- Result: **PASS** after fixing two doc-page issues above

### Link integrity recheck

- Post-remediation scan of internal `href="/..."` links in `frontend/src/app/**/*.tsx` against app routes + public assets reports **0 unresolved internal links**.
- Detailed output captured in `audit/link-map.md`.

## Audit Artifacts

- `audit/frontend-routes.md`
- `audit/api-endpoints.md`
- `audit/link-map.md`
- `audit/overnight-report.md` (this file)

## Remaining Follow-Ups

1. Optionally run non-mocked end-to-end recall simulation checks against a live ingestion backend (to validate proxy + backend behavior together).
2. Optionally expand journey checks into committed Playwright specs for CI.
3. Triage pre-existing global frontend lint debt outside touched pages.

## Continuation Pass (Block 8-10)

### 8) Sales collateral and deployment docs consistency

- Updated FSMA sales collateral for consistency in baseline/target metrics and links:
  - `sales/fsma_supplier_onepager.md`
  - `sales/fsma_cold_outreach_templates.md`
  - `sales/fsma_investor_brief.md`
- Standardized marketing URLs to fully qualified `https://regengine.com/...` links in the FSMA one-pager/outreach docs.
- Aligned outreach and investor framing with the same simulation profile used on homepage messaging:
  - baseline ~18 hours
  - RegEngine scenario response: 42 minutes
  - KDE completeness: 98%
- Updated deployment reference in `docs/FSMA_RAILWAY_DEPLOYMENT.md`:
  - added `API_KEY`, `ALLOWED_ORIGINS`, `STRIPE_WEBHOOK_SECRET` API env coverage
  - updated frontend env vars to `NEXT_PUBLIC_API_BASE_URL` + per-service ports
  - added explicit validation routes for `/demo/supply-chains` and `/demo/recall-simulation`
  - added production note to keep `AUTH_TEST_BYPASS_TOKEN` unset

### 9) Security scans and hardening

- Regex scan reruns across `services/` and `scripts/` show no hardcoded long-form credentials in operational scripts after remediation.
- Replaced hardcoded keys/passwords in utility scripts with environment-driven values:
  - `services/ingestion/scripts/load_test_ingestion.py`
  - `services/ingestion/scripts/stress_test_ingestion.py`
  - `services/ingestion/scripts/verify_pipeline.py`
  - `scripts/deploy_rls.py`
  - `scripts/test_hash_001.py`
  - `scripts/seed_phase2b_key.py`
  - `scripts/test_id_001.py`
- Mutation endpoint dependency scan in ingestion app now flags only two intended public patterns:
  - `POST /api/v1/portal/{portal_id}/submit` (link-token workflow)
  - `POST /api/v1/billing/webhook/stripe` (webhook endpoint)
- Added dual-header API key support in `app/webhook_router.py` so both `X-API-Key` and `X-RegEngine-API-Key` are accepted.
- Hardened supplier portal token flow in `services/ingestion/app/supplier_portal.py`:
  - portal links now honor `expires_days`
  - expiry is validated on detail/read and submit paths
  - expired links are rejected and removed from in-memory store
- CORS allow-headers now explicitly include `X-RegEngine-API-Key` in `services/ingestion/main.py`.

### 10) Final verification rerun

- Frontend production build rerun: **PASS**
  - `npm --prefix frontend run build`
- Full Python compile pass rerun over `services/`: **PASS**
  - `python3 -m compileall services`
- Focused syntax compile of modified scripts/modules: **PASS**
  - `python3 -m py_compile ...`
- Runtime auth/expiry smoke checks via TestClient: **PASS**
  - both `X-API-Key` and `X-RegEngine-API-Key` accepted for webhook ingestion when `API_KEY` is set
  - expired supplier portal links return `404` for details and submit
- Targeted ingestion API pytest rerun: **PASS**
  - `.venv/bin/python -m pytest services/ingestion/tests/test_recall_simulations_api.py services/ingestion/tests/test_epcis_ingestion_api.py`
  - Result: `5 passed`
- Full frontend lint rerun: **FAIL** due to pre-existing repo-wide lint debt not introduced in this pass
  - high volume of legacy `react/no-unescaped-entities` and hook-order/dependency findings across many unrelated files
  - no new lint gate was introduced by the markdown/security/doc changes in this continuation block
