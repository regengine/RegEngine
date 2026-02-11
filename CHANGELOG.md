# Changelog

All notable changes to this project will be documented in this file.

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
