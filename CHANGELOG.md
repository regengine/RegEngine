# Changelog

All notable changes to this project will be documented in this file.

## v0.7.0 — Phase 4 Accessibility Polish (WCAG 2.1 AA)

- **Keyboard Accessibility (WS2/WS3/WS5)**
  - Made the marketing Free Tools dropdown fully keyboard operable with button trigger semantics, menu roles, Escape/arrow navigation, and click-outside close behavior.
  - Added keyboard-selectable pricing tier cards using `radiogroup`/`radio` semantics and Enter/Space support.
  - Added tab/tabpanel semantics and arrow-key navigation for developer example and language selectors.
- **Landmarks & Navigation (WS1)**
  - Added a skip-to-content link and `main` target ID in the root layout.
  - Added landmark labels for navigation/footer regions to improve screen reader orientation.
- **Reduced Motion (WS4)**
  - Added global `prefers-reduced-motion` CSS overrides to disable non-essential animation and transitions.
  - Enabled Framer Motion reduced-motion behavior using `MotionConfig reducedMotion="user"`.
- **Touch Targets & Semantic Polish (WS6)**
  - Increased shared button minimum heights and enforced a 44x44 mobile menu target.
  - Improved homepage heading structure and hid decorative emoji icons from screen readers.
- **Validation**
  - Verified implementation with `npm run lint` and `npm run build`.

## v0.6.0 — Phase 3 Onboarding UX Redesign

- **Onboarding Hub (WS1)**
  - Replaced `/onboarding` redirect behavior with a dedicated onboarding hub page.
  - Added two clear paths: guided wizard (`/onboarding/supplier-flow`) and bulk upload (`/onboarding/bulk-upload`).
- **Dark Theme Migration (WS2/WS3)**
  - Migrated onboarding supplier flow visuals from hardcoded/light styles to shared `--re-*` design tokens.
  - Updated bulk upload page to tokenized dark styling and removed legacy `slate-*`/`emerald-*` class usage.
- **Navigation Unification (WS4/WS5)**
  - Added `frontend/src/app/onboarding/layout.tsx` onboarding shell with consistent top navigation.
  - Hid marketing header/footer on onboarding routes to maintain focused flow context.
  - Added cross-links between marketing, onboarding, and dashboard, including dashboard bridge links and a supplier completion CTA to `/dashboard`.
- **Validation**
  - Verified with `npm run lint` and `npm run build` after implementation.

## v0.5.0 — Billing Platform Audit Remediation

- **Security Middleware (P0)**
  - Added rate limiting (100 req/min per client), security headers, and `X-Request-ID` tracing via `middleware.py`.
  - Centralized shared utilities (`format_cents`, `get_tenant_id`, `paginate`) in `utils.py`.
- **API Quality (P1)**
  - Added pagination (`page`, `page_size`) to all 12 list endpoints across 6 routers.
  - Standardized error responses with a global `ValueError` → `HTTPException` handler.
  - Added `Field(gt=0)` validation on all `amount_cents` fields (invoices, partners, dunning).
- **Code Quality (P2)**
  - Migrated 55+ inline `f"${x / 100:,.2f}"` patterns to centralized `format_cents()` across 10 engines and all routers.
  - Replaced duplicated `_get_tenant_id()` with shared utility.
  - Removed fragile `sys.path.insert()` hacks from 4 router files.
  - Fixed import bugs: `format_cents4` typo, missing `uuid4` in 2 engines.
- **Testing**
  - 331/331 tests passing — zero regressions.
  - 16 new middleware and utility tests added.

## v0.4.0 — Phase 7 Security Hardening: RLS & Double-Lock Isolation

- **Database-Enforced Isolation (RLS)**
  - Enforced `ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` on multi-tenant tables (`documents`, `vertical_projects`, `evidence_logs`, `audit_logs`).
  - Implemented dynamic session-scoped policies using `app.tenant_id`.
- **Application-Layer Context Binding**
  - Updated `get_current_tenant` to automatically bind the authenticated `tenant_id` to the database session context.
  - Standardized `TenantContext` usage across all administrative and vertical service routes.
- **Vertical-Specific Hardening**
  - Added explicit security gates to the Healthcare Enterprise service to trigger RLS enforcement on sensitive data endpoints.
- **Production Readiness**
  - Released `production_bundle/` containing auditable documentation (SOC2, HIPAA), RLS regression tests, and developer security tools.
  - Optimized `.gitignore` to exclude build artifacts.

## v0.3.0 — Domain APIs, Correlation IDs, Rate Limiting, and Tests

- Domain-scoped APIs
  - Added `/api/kyc/basic`, `/api/aml/watchlist`, `/api/privacy/rule-lookup`, `/api/filings/schema-check` with strict request/response models and standardized disclaimers.
  - Wired domain router into ingestion service.
- Correlation & observability
  - Propagate `X-Request-ID` end-to-end (demo → ingestion → NLP → Kafka → graph) and bind into structlog context.
  - Added Graph API `GET /v1/provisions/by-request?id=<uuid>` to fetch provisions by `provenance.request_id`.
- Citation/versioning
  - Extended `ExtractionPayload` with `rule_version`, `source_uri`, `jurisdiction_code` (plus `effective_date` already present).
  - Clarified `GraphEvent.provenance` to include `request_id`.
- Rate limiting
  - Free-tier endpoints limited (60/min) with `X-RateLimit-*` headers.
  - Optional Redis-backed limiter via `RATE_LIMIT_BACKEND=redis` and `REDIS_URL`; startup health check logs readiness.
- Tests
  - Added tests for domain routes, rate limiter behavior, Kafka correlation headers + provenance, and graph by-request API.

 
### Setup notes

- Optional: `pip install -e .[rate_limit]` to enable Redis-backed limiter.
- Env: `RATE_LIMIT_BACKEND=redis`, `REDIS_URL="redis://localhost:6379/0"`.

### Next considerations

- Per-route configurable limits and Redis readiness probes in deployment manifests.
- Additional tests for graph consumer context isolation and ingestion URL validator edge cases.
