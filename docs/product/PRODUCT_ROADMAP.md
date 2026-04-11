# RegEngine Product Roadmap (FSMA-First)

Last updated: March 9, 2026
Planning horizon: March 2026 through June 2026 (90 days)

## Objective

Convert FSMA free-tool traffic into paid adoption while improving production reliability for ingestion, traceability, and FDA export workflows.

## Current Baseline (In Repo Today)

- Durable FSMA persistence and hash-chain verification in `services/shared/cte_persistence.py`.
- Webhook ingestion V2 in `services/ingestion/app/webhook_router_v2.py`.
- FDA export and verification endpoints in `services/ingestion/app/fda_export_router.py`.
- FSMA graph routers in `services/graph/app/routers/fsma/`.
- Supplier onboarding flow in `frontend/src/app/onboarding/supplier-flow/`.
- Free tools and readiness flows in `frontend/src/app/tools/` plus landing routes.

## 90-Day Priorities

### Priority 1 (P0): Lead Capture On Free Tools

Problem:
Free tools create product-qualified traffic but weak capture/hand-off.

Scope:

- Add `POST /api/leads` in the admin surface for lead capture and attribution.
- Capture email + tool context from FTL checker/readiness result screens.
- Store explicit source metadata (`tool_used`, score/result payload, timestamp).

Likely touchpoints:

- `services/admin/app/` (lead endpoint + validation)
- `frontend/src/app/tools/ftl-checker/`
- `frontend/src/app/tools/readiness-assessment/`
- `frontend/src/app/retailer-readiness/page.tsx`

Success metric:

- >= 25% of completed free-tool sessions include captured contact info.

### Priority 2 (P0): Documentation Reality Cleanup

Problem:
Core docs have contained speculative language that misleads agents and contributors.

Scope:

- Keep `docs/ARCHITECTURE.md` and `docs/PRODUCT_ROADMAP.md` tied to implemented code.
- Establish and enforce `docs/AI_ENGINEERING_STANDARDS.md`.
- Remove or rewrite any docs that describe fictional systems/phases.

Success metric:

- Zero speculative terms in core architecture/roadmap standards docs.
- New contributor/agent setup starts from accurate docs only.

### Priority 3 (P1): Developer Response Examples

Problem:
Developer-facing pages show request samples without enough concrete response payloads.

Scope:

- Add canonical JSON response examples to developer docs/UI.
- Align examples with real endpoint contracts from backend/openapi artifacts.

Likely touchpoints:

- `frontend/src/app/developers/page.tsx`
- `docs/openapi/*.json`
- `docs/tenant/API_EXAMPLES.md`

Success metric:

- Response examples present for all primary FSMA onboarding/ingestion/export examples.

### Priority 4 (P1): Free/Starter Pricing Bridge

Problem:
Gap between free-tool value and paid conversion path.

Scope:

- Add a free/starter tier on pricing and entitlement messaging.
- Define hard limits (for example events/month, seats, support level).
- Wire plan metadata into onboarding and billing UX.

Likely touchpoints:

- `frontend/src/app/pricing/page.tsx`
- `frontend/src/components/billing/`
- backend billing/plan configuration routes

Success metric:

- Higher conversion from free-tool users to authenticated onboarding starts.

## Sequencing

1. Weeks 1-3: Priority 1 + Priority 2
2. Weeks 4-8: Priority 3
3. Weeks 6-12: Priority 4 (parallelized after lead capture instrumentation lands)

## Tracking Metrics

- Free tool completion count
- Lead capture rate
- Onboarding start rate after lead capture
- FDA export endpoint usage
- Time-to-first-successful-ingest per new tenant

## Explicit Non-Goals (This 90-Day Window)

- New non-FSMA vertical expansion
- Broad architectural rewrites unrelated to conversion/reliability goals
- Multi-quarter speculative initiatives without a concrete owner and endpoint
