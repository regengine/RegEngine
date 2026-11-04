# RegEngine

**FSMA 204 food traceability: supplier data in, verifiable evidence out.**

RegEngine is an API-first traceability evidence platform for food supply chains. It ingests supplier and ERP records, normalizes Critical Tracking Events (CTEs) and Key Data Elements (KDEs), evaluates versioned rules, and produces tenant-scoped records, tamper-evident audit evidence, and FDA-oriented exports.

Inflow Workbench prepares data with preflight checks, readiness scores, a fix queue, and a commit gate. Optional Jev assistance suggests CSV column mappings and missing event types; deterministic validation and authenticated tenant boundaries remain authoritative.

[Website](https://regengine.co) · [Verify a bundle](https://regengine.co/verify) · [Product description](docs/PRODUCT_DESCRIPTION.md) · [Python SDK](regengine/README.md)

This is a pre-production application with deployed public proof surfaces. The capability inventory below describes checked-in implementation and release policy, not proof of customer adoption or live configuration.

## Public proof surface

You don't have to take our word for any of this — try it yourself:

- [regengine.co/verify](https://regengine.co/verify) — drop an audit bundle exported from your own workspace into the verifier and confirm file-hash and Merkle-root integrity.

This README describes behavior that is visible in checked-in code, configuration, tests, and runbooks.

## Current Status

- Stage: pre-production.
- Backend deploy target in checked-in Railway config: one consolidated FastAPI app in [server/main.py](server/main.py), built by the repo-root [Dockerfile](Dockerfile).
- Frontend: Next.js App Router app in [frontend/](frontend/).
- Database migrations: Alembic at [alembic/versions/](alembic/versions/).
- Tenant isolation posture: tenant authority is derived from authenticated principal state; caller-supplied tenant IDs are assertions only.
- Primary domain: FSMA 204 food traceability. Other regulatory, document, NLP, and graph modules exist, but FSMA ingestion and compliance are the best-evidenced product path in this repository.

## What The Product Does

Implemented capabilities in the current tree. Route availability is controlled by [server/router_policy.py](server/router_policy.py); a module or UI page existing does not mean its API is enabled in production.

| Capability | Evidence |
| --- | --- |
| API key protected webhook CTE ingest | [services/ingestion/app/webhook_router_v2/routes.py](services/ingestion/app/webhook_router_v2/routes.py) |
| Canonical tenant context for API-key, JWT, and ingestion RBAC callers | [services/shared/tenant_context.py](services/shared/tenant_context.py) |
| Legacy ingestion route tenant-context migration inventory | [docs/security/tenant-route-inventory.md](docs/security/tenant-route-inventory.md) |
| Paid endpoint subscription gate | [services/ingestion/app/subscription_gate.py](services/ingestion/app/subscription_gate.py) |
| CSV template download and CSV or Excel `.xlsx` CTE ingest (workbook converted to CSV text on the same route) | [services/ingestion/app/csv_templates.py](services/ingestion/app/csv_templates.py), [services/ingestion/app/shared/xlsx_rows.py](services/ingestion/app/shared/xlsx_rows.py), [docs/engineering/TRACEABILITY_FILE_INTAKE.md](docs/engineering/TRACEABILITY_FILE_INTAKE.md) |
| EPCIS 2.0 JSON and XML ingest, including the `/ingest` dashboard upload tab | [services/ingestion/app/epcis/router.py](services/ingestion/app/epcis/router.py), [frontend/src/lib/epcis-upload.ts](frontend/src/lib/epcis-upload.ts) |
| GS1 identifier check-digit validation (GLN/GTIN/SSCC) used by webhook and EPCIS ingest | [services/shared/fsma_validation.py](services/shared/fsma_validation.py) |
| Optional Jev CSV column mapping and file-CTE suggestions, confidence-based review, upload UI prompts, and operator preview/evaluation tools; automatic application defaults off | [services/shared/jev/](services/shared/jev/), [docs/engineering/JEV_HEADER_MAPPING.md](docs/engineering/JEV_HEADER_MAPPING.md) |
| Optional LlamaIndex Extract v2.5 document extraction: a fail-open second pass on bulk-upload supplier PDFs the table parser cannot read, with per-field citations, confidence and evidence; rows still go through classify, validate and human commit; operator command-line tool | [services/shared/document_extract/](services/shared/document_extract/), [docs/engineering/DOCUMENT_EXTRACT.md](docs/engineering/DOCUMENT_EXTRACT.md) |
| Inflow Workbench preflight, readiness, fix queue, scenario library, and commit gate | [services/ingestion/app/inflow_workbench.py](services/ingestion/app/inflow_workbench.py) |
| Supplier portal preflight before persistence | [services/ingestion/app/supplier_portal.py](services/ingestion/app/supplier_portal.py) |
| Supplier CSV manifest remediation (implemented; excluded from the production router allowlist): byte-exact manifest intake, per-row validation and staging with provenance, exception/remediation cases, case-scoped single-use supplier correction links, revalidation with granular release, deterministic evidence bundles, scheduler-drained correction-link email delivery | [services/ingestion/app/remediation/](services/ingestion/app/remediation/) |
| Buyer remediation dashboard (requires the remediation API to be enabled; manifest list, per-record case status, release and correction-link actions) | [frontend/src/app/remediation/page.tsx](frontend/src/app/remediation/page.tsx) |
| CTE persistence, hash-chain storage, and verification (legacy and canonical stores; dual-write retirement mid-cutover) | [services/shared/cte_persistence/core.py](services/shared/cte_persistence/core.py), [services/shared/canonical_persistence/writer.py](services/shared/canonical_persistence/writer.py), [docs/persistence/dual-write-cutover.md](docs/persistence/dual-write-cutover.md) |
| Compliance score reads from stored FSMA CTE data | [services/ingestion/app/compliance_score.py](services/ingestion/app/compliance_score.py) |
| FDA-oriented CSV and evidence-bundle export routes | [services/ingestion/app/fda_export/router.py](services/ingestion/app/fda_export/router.py) |
| Request-response cases, scoped evidence package assembly, and auditor workflows | [services/ingestion/app/request_workflow_router.py](services/ingestion/app/request_workflow_router.py), [services/ingestion/app/auditor_router.py](services/ingestion/app/auditor_router.py) |
| Recall readiness assessments, gap checklists, and recall reports | [services/ingestion/app/readiness_router.py](services/ingestion/app/readiness_router.py), [services/ingestion/app/recall_report.py](services/ingestion/app/recall_report.py) |
| EPCIS JSON-LD export and broader recall simulations (experimental routers; excluded from the production allowlist) | [services/ingestion/app/epcis_export.py](services/ingestion/app/epcis_export.py), [services/ingestion/app/recall_simulations.py](services/ingestion/app/recall_simulations.py) |
| Subscription-gated access and persisted usage metering; Stripe usage reporting requires an operator call | [services/ingestion/app/subscription_gate.py](services/ingestion/app/subscription_gate.py), [DESIGN_metering-billing.md](DESIGN_metering-billing.md) |
| Tenant/admin/user/API-key management, including a sysadmin rename of an organization and the tenant row that shares its id | [services/admin/app/](services/admin/app/), [docs/engineering/ADMIN_ORGANIZATIONS.md](docs/engineering/ADMIN_ORGANIZATIONS.md) |
| Persisted admin tenant provisioning | [services/admin/app/routes.py](services/admin/app/routes.py) |
| Tamper-evident admin audit log hashing | [services/admin/app/audit.py](services/admin/app/audit.py) |
| Audit-chain verification for admin audit exports | [services/admin/app/audit_integrity.py](services/admin/app/audit_integrity.py) |
| Passwordless email-OTP and passkey login | [services/admin/app/auth/challenges_router.py](services/admin/app/auth/challenges_router.py), [frontend/src/lib/passwordless-auth.ts](frontend/src/lib/passwordless-auth.ts) |
| Public email-verification gate for free compliance tools (no-auth lead capture with rate limits, GDPR lead-erasure endpoints) | [services/admin/app/tool_verification_routes.py](services/admin/app/tool_verification_routes.py) |
| Scheduler jobs (deadline monitor, data archival, outbox drains, scheduled recall drills with persisted mock-audit drill records) and scheduler metrics surface | [services/scheduler/](services/scheduler/) |
| Frontend dashboard, auth, sandbox, docs, and product pages. `/contact` and `/signup` both post to `POST /api/contact` | [frontend/src/app/](frontend/src/app/), [docs/operations/LAUNCH_TRUST_PROVISIONING.md](docs/operations/LAUNCH_TRUST_PROVISIONING.md) |
| Inbound email ingestion: Postmark inbound-parse webhook, Basic-Auth + per-tenant sender allowlist, CSV attachments routed through the existing CSV ingest path, claim-then-act idempotent audit trail. Built and unit-tested; **not enabled in production** and has no admin/self-service provisioning UI — see [docs/engineering/EMAIL_INGESTION.md](docs/engineering/EMAIL_INGESTION.md) | [services/ingestion/app/email_ingest/](services/ingestion/app/email_ingest/) |

## Production Spine

```text
ingest source record
  -> preflight in Inflow Workbench
  -> normalize to CTE/KDE shape
  -> score readiness and route fix queue items
  -> pass commit gate
  -> persist tenant-scoped event data
  -> evaluate rules
  -> expose compliance/audit/export views
```

The diagram describes the Workbench workflow. Direct webhook, CSV, and EPCIS intake has route-specific validation and persistence; it does not universally pass through Workbench. Event persistence is mid-migration from a legacy CTE store to a canonical hash-chain store: some write paths still write both stores, newer paths write canonical-only, and read paths have consumer-specific cutover flags. Chain verification defaults to canonical reads; FDA CSV export v1 retains a legacy code default. Historical rollout observations are recorded in the cutover runbook; current deployment flags must be read back separately (see [docs/persistence/dual-write-cutover.md](docs/persistence/dual-write-cutover.md)). Graph, NLP, generic regulatory-intelligence, and document-ingestion modules are present, but they should not be treated as the core product contract without checking the relevant tests and deploy wiring.

## Architecture

### Runtime Shape

The repo still contains six service directories:

| Directory | Purpose |
| --- | --- |
| [services/admin](services/admin) | tenants, users, roles, MFA, API keys, audit logs, admin routes |
| [services/ingestion](services/ingestion) | webhook, CSV, EPCIS, sandbox, export, CTE persistence integration |
| [services/compliance](services/compliance) | compliance validation routes and FSMA rules JSON |
| [services/graph](services/graph) | graph and supply-chain query modules |
| [services/nlp](services/nlp) | regulatory/document extraction modules |
| [services/scheduler](services/scheduler) | scheduled jobs, job metrics, operational checks |

The repo-root Dockerfile copies all service directories and starts [server/main.py](server/main.py) with Gunicorn/Uvicorn. `server/main.py` mounts routers from the service directories into one FastAPI process.

The old independent service entrypoints still exist, for example [services/ingestion/main.py](services/ingestion/main.py), but the repo-root [railway.toml](railway.toml) points at the root Dockerfile.

### Infrastructure

Verified from checked-in config and code:

- PostgreSQL is required. Production connection is supplied through `DATABASE_URL`.
- Local development stack in [docker-compose.dev.yml](docker-compose.dev.yml) starts PostgreSQL and Redis (Redis backs the subscription gate, rate limiting, and idempotency caching — without it authenticated ingest fails closed with 503).
- Redis is used by rate limiting, queues, session/subscription checks, and other runtime paths when configured.
- Neo4j code and health checks exist, but the default local development stack does not start Neo4j. The deploy-gating `/readiness` probe contacts Neo4j only when the graph subsystem is enabled; with `NEO4J_URI` set but graph routers disabled (the production default) Neo4j is reported `not_probed` and never contacted. Only PostgreSQL failure returns 503 from `/readiness`; Redis/Neo4j errors degrade the payload but still return 200 ([server/main.py](server/main.py)).
- The frontend is a separate Next.js application with its own package lock and CI workflow.

## Data And Schema

- Alembic is the active schema migration system.
- Root migration config: [alembic.ini](alembic.ini).
- Migration files: [alembic/versions/](alembic/versions/).
- Deploy migration runner: [scripts/run-migrations.sh](scripts/run-migrations.sh).
- Runtime DDL is fully owned by Alembic as of v098/v099: application boot performs no schema DDL, the boot-time RLS function definitions were dropped in favor of migration-pinned `set_tenant_context` / `set_admin_context`, and the app role can run without `CREATE` privilege (a startup `admin_database_init_skipped` warning is expected under least privilege). One-transaction revoke runbooks: [runbooks/prod-revoke-create-after-v098.sql](runbooks/prod-revoke-create-after-v098.sql), [runbooks/prod-least-privilege-db-role.sql](runbooks/prod-least-privilege-db-role.sql).
- Legacy Flyway-style SQL migrations under service directories have been removed (meta-issue #2004); [scripts/check_orphan_migrations.py](scripts/check_orphan_migrations.py) is a CI guard that keeps orphan migrations at zero, rejects any reintroduced top-level Flyway tree, and enforces the `alembic/sql` reference contract in both directions: an `alembic/sql` file referenced by no Alembic revision fails CI (archive it under [docs/archive/migrations/](docs/archive/migrations/) instead), and a revision referencing a missing SQL file fails CI. Superseded companion SQL already archived: see [docs/archive/migrations/README.md](docs/archive/migrations/README.md).
- Per-label metered billing (v121, [alembic/versions/20260912_ceb552c6d36d_v121_billing_usage_counters.py](alembic/versions/20260912_ceb552c6d36d_v121_billing_usage_counters.py)) adds a new `billing` schema — the first Postgres-durable billing state in the repo; Stripe subscription/customer state otherwise lives entirely in Redis ([services/ingestion/app/stripe_billing/state.py](services/ingestion/app/stripe_billing/state.py)). Design, deviations, and known follow-ups: [DESIGN_metering-billing.md](DESIGN_metering-billing.md).

Schema-related CI guards include:

- [scripts/check_alembic_revisions.py](scripts/check_alembic_revisions.py)
- [scripts/check_tenant_id_uuid_only.py](scripts/check_tenant_id_uuid_only.py)
- [scripts/check_orphan_migrations.py](scripts/check_orphan_migrations.py)
- ORM drift gate: `alembic check` runs in backend CI against an Alembic-head database. [alembic/env.py](alembic/env.py) registers all four declarative Bases (admin, agent-operator, api-key store, scheduler state) so every ORM model is compared for structural drift; raw-SQL-managed tables with no ORM model are exempt by design.
- Schema parity contract: [scripts/schema_parity_audit.py](scripts/schema_parity_audit.py) compares the migrated schema against the checked-in contract [docs/schema/expected_schema.json](docs/schema/expected_schema.json) — every table, including raw-SQL FSMA tables the ORM gate cannot see. A migration that changes the schema must regenerate the snapshot in the same PR or CI fails. The checked-in snapshot includes `billing.tenant_usage_counters` and `billing.tenant_usage_event_ledger`; schema parity is distinct from the RLS test coverage described below.
- RLS regression gate scope: [tests/migrations/test_rls_coverage.py](tests/migrations/test_rls_coverage.py) only sweeps the `fsma` schema plus a curated `public` allowlist. Tables in other schemas — including the new `billing.tenant_usage_event_ledger` / `billing.tenant_usage_counters` (v121) — are not examined by this gate. The v121 migration enables and `FORCE`s RLS with a real `get_tenant_context()` predicate on both tables (code-reviewed), but that posture is not CI-locked the way `fsma.*` tables are, and there is no dedicated `tests/migrations/test_v121_*.py` migration test (unlike v111/v120).
- Seeded mid-chain migration rehearsal: [tests/migrations/test_seeded_mid_chain_upgrade.py](tests/migrations/test_seeded_mid_chain_upgrade.py) upgrades to v089, seeds representative rows (including audit rows that arm the append-only trigger), then upgrades to head. Runs as a two-leg CI matrix (app-roles-only and Supabase-like client roles). Added after a row-dependent backfill passed empty-database CI and then failed production deploys (#2588, #2589).

## Rule Enforcement

FSMA rule evaluation has both advisory and blocking modes.

- The rule enforcement switch is `RULES_ENGINE_ENFORCE`.
- Supported modes are implemented in [services/shared/rules/enforcement.py](services/shared/rules/enforcement.py).
- Rollout steps are documented in [docs/runbooks/RULES_ENGINE_ENFORCE_ROLLOUT.md](docs/runbooks/RULES_ENGINE_ENFORCE_ROLLOUT.md).
- The compliance `POST /validate` endpoint derives its verdicts from the same versioned rules engine ([services/compliance/app/routes.py](services/compliance/app/routes.py)), not a local field check. Evaluation there is advisory (nothing is persisted), tenant identity comes from the authenticated API key rather than the payload, and engine no-verdict outcomes fail closed: `valid=false` with a `NO_VERDICT` error, or `503` when the rules database is unavailable. Golden tests: [tests/compliance/test_validate_rules_engine_golden.py](tests/compliance/test_validate_rules_engine_golden.py).

Do not assume every ingestion path rejects all non-compliant records by default. Check the deployed `RULES_ENGINE_ENFORCE` setting and route-specific tests before treating a tenant path as blocking.

## Security And Tenant Boundaries

Verified controls in the codebase:

- API-key auth and API-key storage utilities live under [services/shared/auth.py](services/shared/auth.py) and [services/shared/api_key_store.py](services/shared/api_key_store.py).
- The accepted API key is stored on `request.state.api_key`, and ingestion RBAC stores the accepted principal on `request.state.principal`.
- [services/shared/tenant_context.py](services/shared/tenant_context.py) is the canonical resolver for tenant-scoped request authority.
- Transaction-scoped setting of the PostgreSQL RLS tenant GUC (`app.tenant_id`) is converged on the canonical `set_tenant_guc` / `set_tenant_guc_if_uuid` helpers in [services/shared/tenant_context.py](services/shared/tenant_context.py); the `adhoc-tenant-guc-set-config` Semgrep rule in [.semgrep/tenant-trust.yaml](.semgrep/tenant-trust.yaml) fails CI ([.github/workflows/security.yml](.github/workflows/security.yml)) on inline `set_config('app.tenant_id', ...)` call sites. Two deliberate session-scoped exceptions set the GUC through the SQL `set_tenant_context()` function instead: [services/admin/app/models.py](services/admin/app/models.py) and [services/ingestion/regengine_ingestion/storage/database.py](services/ingestion/regengine_ingestion/storage/database.py). The Semgrep rule is defense-in-depth; the fail-hard RLS predicate remains the enforcement layer.
- The tenant GUC is propagated app-wide through a SQLAlchemy Engine begin hook in [services/shared/database.py](services/shared/database.py). Production startup unconditionally verifies both `DATABASE_URL` and `ADMIN_DATABASE_URL` roles and aborts when either is SUPERUSER, BYPASSRLS, or has an unknown posture. `REGENGINE_REQUIRE_RLS_ENFORCEMENT=1` remains required deployment evidence, not an opt-out switch.
- Ingestion authorization helpers live in [services/ingestion/app/authz.py](services/ingestion/app/authz.py).
- Legacy ingestion routers use [services/ingestion/app/webhook_compat.py](services/ingestion/app/webhook_compat.py) to authenticate API keys and resolve `TenantContext` before route handlers read or write tenant data.
- Admin auth routes and MFA code live under [services/admin/app/](services/admin/app/).
- Tenant context middleware lives under [services/shared/middleware/](services/shared/middleware/).
- PostgreSQL RLS migrations exist in Alembic.
- Rate limiting code exists for multiple surfaces, including tenant-scoped ingestion limits and auth-related limits.
- Paid endpoint access uses [services/ingestion/app/subscription_gate.py](services/ingestion/app/subscription_gate.py) and derives tenant from authenticated principal state, not request tenant claims.
- Admin tenant creation through `POST /v1/admin/tenants` persists a `TenantModel` row with active status before returning the tenant UUID.
- Primary frontend login is passwordless: email one-time-code and WebAuthn passkey login, issued through HTTP-only cookie sessions. See [services/admin/app/auth/challenges_router.py](services/admin/app/auth/challenges_router.py), [frontend/src/lib/passwordless-auth.ts](frontend/src/lib/passwordless-auth.ts), and [frontend/src/app/login/PasswordlessEntryClient.tsx](frontend/src/app/login/PasswordlessEntryClient.tsx). OTP codes are delivered by Resend. In local E2E mode only (`REGENGINE_E2E_MODE` plus `REGENGINE_E2E_EMAIL_OUTBOX`; hard-blocked in production by [services/admin/app/e2e_safety.py](services/admin/app/e2e_safety.py)), codes are also written to a Playwright outbox file. If `RESEND_API_KEY` is unset outside E2E mode, codes are not delivered at all — the challenge flow drops the code with only an error log. Logout revokes the opaque browser session server-side, not just client-side cookie clearing.
- Sign-in code emails are eligibility-gated: the challenge flow only dispatches a code when the address maps to a verified `user_emails` row with a keyed email fingerprint, an active user, and an `organization_memberships` row (`_load_valid_identity` in [services/admin/app/auth/challenges_router.py](services/admin/app/auth/challenges_router.py)). Ineligible addresses receive the same accepted challenge response but no email (logged as `auth_challenge_email_suppressed_ineligible_identity`). Identity rows are provisioned at invite acceptance via [services/admin/app/auth/identity_helpers.py](services/admin/app/auth/identity_helpers.py); users predating that provisioning are backfilled by Alembic v094 ([alembic/versions/20260715_feb267263e0a_v094_passwordless_identity_backfill.py](alembic/versions/20260715_feb267263e0a_v094_passwordless_identity_backfill.py)), which hard-fails in production if `AUTH_OTP_HMAC_SECRET` is unset.
- A legacy Supabase-session code path still exists in [frontend/src/proxy.ts](frontend/src/proxy.ts) alongside the passwordless flow; do not assume it has been fully removed. [frontend/src/lib/auth-context.tsx](frontend/src/lib/auth-context.tsx) is now cookie-session only.
- A public, unauthenticated lead-capture surface exists under `/api/v1/tools` ([services/admin/app/tool_verification_routes.py](services/admin/app/tool_verification_routes.py)): email in, 6-digit code out, verified leads stored in `tool_leads`, plus public GDPR lead-erasure endpoints. Endpoints are rate limited. Tool-access JWTs are signed with a dedicated `TOOL_ACCESS_SECRET` that is never shared with session keys; startup raises in production if it is unset. Tool-access JWTs expire after 24 hours and the `/api/tools/check-access` gate verifies that expiry on every check; the optional `TOOL_ACCESS_TOKEN_EXPIRE_HOURS` env var can only shorten the lifetime (values above 24 hours fall back to the default) and is never required.
- A supplier-facing, token-scoped surface (no account, no principal) exists under `/api/v1/remediation/supplier` ([services/ingestion/app/remediation/supplier_router.py](services/ingestion/app/remediation/supplier_router.py)): buyer-issued correction links carry the raw token in the URL fragment, which browsers never send to the server; the JSON endpoints receive the token in the request body, so it never appears in a URL path or query string and cannot land in access/proxy logs. Only token hashes are stored ([services/ingestion/app/remediation/tokens.py](services/ingestion/app/remediation/tokens.py)); exchange is single-use and mints one 30-minute session; token and session failures return uniform error bodies, with deny reasons for known tokens recorded in the audit log rather than the response; the JSON endpoints are rate limited (the static `/form` page is not). Tenant identity is read only from the server-side token row — supplier request bodies define no tenant field.
- Production client-side JS errors report to a sampled first-party beacon at `/api/client-errors` ([frontend/src/instrumentation-client.ts](frontend/src/instrumentation-client.ts), [frontend/src/app/api/client-errors/route.ts](frontend/src/app/api/client-errors/route.ts)): 10% of page loads with a per-load report cap, query strings stripped client- and server-side, payloads carry no user identifiers, per-IP rate limited (per server instance), and the route always responds 204/429 with no body. The beacon keeps browser Sentry out of the frontend instrumentation entry point, but `@sentry/nextjs` is still statically imported by client error-boundary components (for example [frontend/src/app/error.tsx](frontend/src/app/error.tsx)), so do not treat the client bundle as third-party-SDK-free.

Tenant-scoped HTTP handlers must use authenticated principal state as the source of tenant authority. Path, query, header, and JSON body `tenant_id` values are treated as caller assertions only; conflicts with the authenticated tenant fail closed with `409 E_TENANT_MISMATCH`. Missing principal or tenant context fails with `401 E_NO_PRINCIPAL` or `401 E_NO_TENANT`. The current legacy ingestion route inventory is maintained in [docs/security/tenant-route-inventory.md](docs/security/tenant-route-inventory.md).

Subscription-gated paid routes also fail closed: missing or inactive subscriptions return `402`, and Redis/circuit uncertainty returns `503` because the service cannot confirm entitlement state.

Known authentication caveat: two login/session code paths (passwordless cookie sessions and the legacy Supabase-session flow in `proxy.ts`) coexist in the frontend. Treat auth behavior as code-and-test verified, not marketing-copy verified.

## Local Development

Prerequisites:

- Python 3.11 or 3.12. `pyproject.toml` declares `>=3.11,<3.13`.
- Node/npm for the frontend.
- Docker for local PostgreSQL.

Backend setup:

```bash
python3 -m venv venv
source venv/bin/activate
pip install --require-hashes -r requirements.lock

export POSTGRES_PASSWORD=regengine
docker compose -f docker-compose.dev.yml up -d

export DATABASE_URL="postgresql://regengine:${POSTGRES_PASSWORD}@localhost:5432/regengine"
export ADMIN_DATABASE_URL="postgresql://regengine_sysadmin:${POSTGRES_PASSWORD}@localhost:5432/regengine"
export MIGRATIONS_DATABASE_URL="postgresql://regengine_owner:${POSTGRES_PASSWORD}@localhost:5432/regengine"
export REDIS_URL="redis://localhost:6379/0"
./scripts/run-migrations.sh
```

Mint a local test API key against this stack (seeds the test tenant and its
`trialing` billing status too, so subscription-gated routes work):

```bash
./venv/bin/python scripts/create_test_api_key.py
```

The raw key is never printed in full. It is written once to
`~/.regengine/test-api-key` (mode 0600, override with `--key-file`); load it
with `export REGENGINE_TEST_API_KEY="$(cat ~/.regengine/test-api-key)"` and
pass it in the `X-RegEngine-API-Key` header.
In development the backend validates DB-backed keys only when the server
process runs with `ENABLE_DB_API_KEYS=true`.

To exercise the full customer experience against this stack — provisioning a
tenant and API key, activating billing, ingesting from a simulated customer
system, and verifying evidence — run the customer-journey harness in the
[inflow-lab](https://github.com/regengine/inflow-lab) repo. Provide a
pre-provisioned, tenant-bound `REGENGINE_API_KEY`; automated demo callers may
not mint live credentials. The harness seeds `billing:tenant:{tenant_id}` in
Redis so the subscription gate passes.

Run the persisted Inflow-to-RegEngine proof when you need real local evidence instead of DB-free simulation:

```bash
DATABASE_URL="postgresql://regengine:${POSTGRES_PASSWORD}@localhost:5432/regengine" \
  ./venv/bin/python scripts/verify_inflow_to_regengine_e2e.py \
  --output-dir /tmp/regengine-inflow-e2e
```

Run the consolidated backend:

```bash
source venv/bin/activate
uvicorn server.main:app --reload --port 8000
```

Run an individual legacy service entrypoint when needed:

```bash
source venv/bin/activate
uvicorn services.ingestion.main:app --reload --port 8002
```

Frontend setup:

```bash
cd frontend
npm install
npm run dev
```

## Testing

Backend:

```bash
source venv/bin/activate
pytest
```

Ingestion full suite, matching the xdist step of the CI hard gate (the CI job additionally runs [services/ingestion/tests/remediation/](services/ingestion/tests/remediation/) single-process against a dedicated migrated Postgres database):

```bash
source venv/bin/activate
pytest services/ingestion/tests --dist=loadfile -n auto -q --no-cov
```

Frontend:

```bash
cd frontend
npm run lint
npm run test:run
```

Security and tenant-boundary checks:

```bash
python3 -m pytest services/shared/tests services/ingestion/tests services/admin/tests services/compliance/tests -q --no-cov
python3 -m pytest --collect-only -q
semgrep --config=.semgrep/tenant-trust.yaml --error .
```

Notes:

- The ingestion full suite is a hard backend CI gate.
- Root pytest discovery includes [services/compliance/tests](services/compliance/tests).
- Local `.env` is loaded by `BaseServiceSettings`; developer-specific values can affect config-default tests. CI runs from a clean environment.
- Some integration tests skip when Docker, external services, or a live local service are unavailable.
- The security and FSMA-204 verification suites ([tests/security/test_security_audit_fixes.py](tests/security/test_security_audit_fixes.py), [tests/data_integrity/test_fsma_204_verification_phase2b.py](tests/data_integrity/test_fsma_204_verification_phase2b.py)) run in-process against the consolidated app via `TestClient` and do not skip on connection errors. A live golden-corpus smoke is opt-in via `REGENGINE_LIVE_SMOKE=1` and fails, never skips, when the target stack is unreachable.
- The supplier-remediation integration tests ([services/ingestion/tests/remediation/](services/ingestion/tests/remediation/)) need a migrated Postgres reachable through `REMEDIATION_TEST_SUPERUSER_DSN`/`REMEDIATION_TEST_APP_DSN`; they skip locally without one. CI sets `REGENGINE_REQUIRE_DB=1`, which turns an unreachable database into a hard failure instead of a skip.

## CI/CD

Main workflows live in [.github/workflows/](.github/workflows/).

Backend CI ([.github/workflows/backend-ci.yml](.github/workflows/backend-ci.yml)) includes:

- test matrix by service
- lint matrix by service plus `services/shared`
- Docker build for the consolidated image
- security audit matrix
- Alembic revision guard
- orphan migration guard
- tenant_id UUID guard
- ORM drift gate (`alembic check` across all registered ORM Bases, against an Alembic-head database)
- schema parity audit (migrated schema vs [docs/schema/expected_schema.json](docs/schema/expected_schema.json))
- seeded mid-chain migration rehearsal (upgrade over seeded rows; app-roles-only and Supabase-like client-role matrix)
- ingestion full suite hard gate; the same job also runs the supplier-remediation integration tests in [services/ingestion/tests/remediation/](services/ingestion/tests/remediation/) single-process against a second Alembic-migrated Postgres database, with `REGENGINE_REQUIRE_DB=1` so an unreachable database fails the gate instead of skipping
- repo-root security/RLS/isolation suite hard gate, including the in-process security and FSMA-204 contract suites ([tests/security/test_security_audit_fixes.py](tests/security/test_security_audit_fixes.py), [tests/data_integrity/test_fsma_204_verification_phase2b.py](tests/data_integrity/test_fsma_204_verification_phase2b.py)) run against the consolidated app
- live-DB regression suite: every `tests/shared/test_*_live.py` file (glob, not an explicit list) runs against an Alembic-migrated scratch Postgres on every PR and nightly, with skips treated as fatal — added after two incidents where live-DB tests silently skipped in CI and regressions reached production (#2658)
- final `ci-status` gate

Backend and frontend CI also run nightly on a cron schedule, plus manual `workflow_dispatch`. Because the push/pull-request triggers are path-filtered, stretches of merges that miss the filters leave gates unexercised; the nightly run surfaces gate drift on `main` as a red run within 24 hours. Scheduled runs use their own concurrency group so a nightly cannot cancel an in-flight push-triggered run.

The security workflow ([.github/workflows/security.yml](.github/workflows/security.yml)) separately runs blocking Semgrep gates (the OWASP top-ten and security-audit registry rulesets plus the repo's tenant-trust rules — zero blocking findings allowed), gitleaks and detect-secrets secrets scanning, and a workflow tool-pinning gate that rejects non-SHA-pinned action refs and unpinned semgrep/pip-audit/Railway-CLI installs across every workflow file in [.github/workflows/](.github/workflows/); these run outside the backend `ci-status` gate.

Frontend CI is separate in [.github/workflows/frontend-ci.yml](.github/workflows/frontend-ci.yml).

SDK CI ([.github/workflows/sdk-ci.yml](.github/workflows/sdk-ci.yml)) is path-filtered to `regengine/**`, `tests/sdk/**`, and the workflow file itself. It installs the SDK package into a clean venv (`pip install ./regengine`, plus pytest, pytest-asyncio, httpx, and requests — no backend dependency tree) and runs [tests/sdk/](tests/sdk/) from outside the repo root with `PYTHONPATH` cleared, so the installed package is exercised rather than the source tree. The route-contract test in that suite requires FastAPI, skips in the clean venv, and runs in the full backend suite instead.

## Deployment

Verified deployment files:

- [Dockerfile](Dockerfile) builds the backend image, installs root `requirements.lock`, runs Alembic migrations through [scripts/run-migrations.sh](scripts/run-migrations.sh), and starts `server.main:app`.
- [railway.toml](railway.toml) points Railway at the root Dockerfile and uses `/readiness` as the healthcheck.
- [frontend/](frontend/) is a Next.js application with its own package lock and scripts.

## Python SDK

- A Python client package lives at [regengine/](regengine/) (see [regengine/README.md](regengine/README.md)). It is not published to PyPI; install from source with `pip install -e ./regengine`.
- Hosted-route client surface: record lookup and query. Forward/backward trace, timeline, FDA export, recall-drill, and readiness methods require experimental graph routes and are unavailable under the production router allowlist; see `RegEngineClient.EXPERIMENTAL_METHODS` in [regengine/client.py](regengine/client.py). The client cannot create records and has no per-category FTL lookup.
- The `regengine-verify` CLI ([regengine/verify_records.py](regengine/verify_records.py)) verifies record hashes online or offline. The separate public Merkle bundle verifier served at regengine.co/sdk/verify_chain.py is checked in at [frontend/public/sdk/verify_chain.py](frontend/public/sdk/verify_chain.py).

## Important Limitations

These are current repo facts, not speculation:

- The codebase still contains both consolidated-monolith wiring and legacy service entrypoints.
- Legacy/orphan migration files were burned down to zero (#2004). [scripts/orphan_migrations_allowlist.txt](scripts/orphan_migrations_allowlist.txt) is a comments-only zero-state contract; [scripts/check_orphan_migrations.py](scripts/check_orphan_migrations.py) fails CI if any orphan migration file or allowlist entry reappears.
- A live ORM-to-database type assertion startup check runs for the admin
  ORM/schema path, the shared `api_keys` auth tables, and the agent-operator
  tables (`ingestion_runs`, `ingestion_run_receipts`, `agent_artifacts`,
  `agent_artifact_reviews`) — see `server/main.py` startup. Extend that
  coverage deliberately if more ORM surfaces become part of the production
  contract; ORM surfaces outside these three Bases are not boot-checked.
- CTE persistence is mid-retirement of a dual-write scheme (WS-1, #1335). `CanonicalEventStore` defaults to writing both the canonical hash-chain store (`fsma.traceability_events`) and the legacy store (`fsma.cte_events`); several newer ingest routes intentionally write canonical-only. Chain verification reads the canonical store **by default** since #3039 (code default flipped 2026-09-02; `CHAIN_VERIFY_READ_CANONICAL=0` is the emergency rollback — the canonical verifier recomputes event digests from row content, which the legacy verifier cannot). The FDA v1 recall export retains a legacy code default, with canonical reads controlled by `FDA_EXPORT_V1_READ_CANONICAL`. The [cutover runbook](docs/persistence/dual-write-cutover.md) records earlier production rollout observations; verify the current deployed flag separately before asserting live read behavior. CI enforces dual-write parity and legacy-vs-canonical golden equivalence in [tests/invariants/](tests/invariants/); plan, read-path inventory, and never-do list live in the same doc.
- Rule failures are not universally blocking unless the relevant enforcement mode is enabled and the route supports it.
- Some architecture documentation is older than the current Dockerfile/server wiring; verify against code before using docs as operational truth.
- Neo4j and Redpanda/Kafka-compatible code paths exist, but the default local dev compose file ([docker-compose.dev.yml](docker-compose.dev.yml)) starts only PostgreSQL and Redis — no Neo4j, no Kafka/Redpanda broker.
- [services/ingestion/app/webhook_compat.py](services/ingestion/app/webhook_compat.py) still exposes an internal non-HTTP `ingest_events()` helper that requires a tenant-bearing payload because it has no request context. HTTP and router callers should derive that payload tenant from authenticated tenant context.
- Supplier remediation notification delivery is recipient-gated. [services/ingestion/app/remediation/delivery.py](services/ingestion/app/remediation/delivery.py) drains the notification outbox and sends correction-link emails via Resend from the scheduler leader (v101 added delivery-status columns). Only rows enqueued with a recipient are delivered; rows without a recipient remain previews, and legacy pre-v101 `pending` rows are never drained — draining them would revoke links buyers already shared out of band. At send time the drainer re-validates the referenced token and follows the buyer reissue path, so a delivered email never carries a revoked or superseded link.
- Per-label metered billing ([DESIGN_metering-billing.md](DESIGN_metering-billing.md); code under [services/ingestion/app/stripe_billing/usage.py](services/ingestion/app/stripe_billing/usage.py), [usage_reporting.py](services/ingestion/app/stripe_billing/usage_reporting.py), and the `/usage*` routes in [routes.py](services/ingestion/app/stripe_billing/routes.py)) counts every accepted `TraceabilityEvent` toward a tenant's usage unconditionally (`CanonicalEventStore.persist_event`/`persist_events_batch`, on by default), but reporting that usage to Stripe is not automatic:
  - Nothing periodically calls `report_tenant_usage_to_stripe`. Usage accumulates in `billing.tenant_usage_counters` until an admin/operator calls `POST /api/v1/billing/usage/report` for a tenant. A periodic scheduler job is a documented, unbuilt follow-up (DESIGN doc §5.1/§7.3) — it is not wired into [services/scheduler/service.py](services/scheduler/service.py).
  - `POST /api/v1/billing/usage/opt-in` assumes a Stripe Billing Meter named `regengine_label_events` already exists in the Stripe Dashboard and that `STRIPE_PRICE_METERED_LABEL_EVENTS` is set; nothing in this repo creates either, and opt-in returns `500` if the env var is unset.
  - All tests for this feature (`services/ingestion/tests/test_billing_usage_core.py`, `test_billing_usage_reporting.py`, `test_billing_usage_routes.py`, `services/shared/tests/test_canonical_persistence_meter_usage.py`) run against a fake SQLAlchemy session and a monkeypatched `stripe.billing.MeterEvent.create` — no test exercises a live Postgres or a live Stripe API call, and (per the Data And Schema section above) the v121 migration has no dedicated migration test and its new tables sit outside the automated RLS coverage gate.
  - `GET /api/v1/billing/usage`'s `billing_period_start`/`_end` are a local UTC-calendar-month approximation, not the tenant's real Stripe invoice anchor (deviation documented in DESIGN doc §3.3/§7.2). This does not change what Stripe actually bills — Stripe's own Meter aggregates usage into the customer's real invoice period regardless of local bucketing — only what the endpoint displays as the "current period".
  - There is no frontend surface for this yet; it is a backend API slice only (`GET /usage`, `POST /usage/report`, `POST`/`DELETE /usage/opt-in`).
- This repository does not prove broad production adoption, paid customer status, regulatory approval, or FDA certification.

## Documentation Map

- [docs/PRODUCT_DESCRIPTION.md](docs/PRODUCT_DESCRIPTION.md) — canonical positioning and capability availability.
- [docs/engineering/JEV_HEADER_MAPPING.md](docs/engineering/JEV_HEADER_MAPPING.md) — optional CSV suggestions, review policy, privacy defaults, and evaluation tools.
- [docs/engineering/DOCUMENT_EXTRACT.md](docs/engineering/DOCUMENT_EXTRACT.md) — optional document data extraction (LlamaIndex Extract v2.5 on supplier PDFs): request flow, failure modes, data handling, configuration, command line.
- [docs/engineering/TRACEABILITY_FILE_INTAKE.md](docs/engineering/TRACEABILITY_FILE_INTAKE.md) — Excel `.xlsx` on the CSV ingest route, the dashboard EPCIS 2.0 upload, and X12 944/945 warehouse advices: routes, field mapping, and rejection rules.
- [frontend/README.md](frontend/README.md) — current UI surfaces and consolidated-backend development setup.

- [2026-09-04 GitHub issue review and rollout](docs/audits/GITHUB_ISSUE_REVIEW_2026_09_04.md) — fixes, validation, and outstanding provisioning.
- [DESIGN_metering-billing.md](DESIGN_metering-billing.md) — per-label metered billing: schema, the `persist_event`/`persist_events_batch` usage-counting hook, Stripe Billing Meters reporting, API surface, and documented deviations/follow-ups (see also the Data And Schema and Important Limitations sections above).

- [docs/engineering/EMAIL_INGESTION.md](docs/engineering/EMAIL_INGESTION.md) - inbound email (Postmark) ingestion: how it works, config, rollout status, and known limitations.
- [ARCHITECTURE.md](ARCHITECTURE.md) - current runtime shape, system map, and debt register.
- [ASYNC_PROCESSES.md](ASYNC_PROCESSES.md) - async and background processing notes.
- [CANONICAL_OWNERSHIP.md](CANONICAL_OWNERSHIP.md) - module ownership notes.
- [SECURITY.md](SECURITY.md) - security posture.
- [docs/security/tenant-route-inventory.md](docs/security/tenant-route-inventory.md) - tenant-scoped ingestion route inventory.
- [docs/persistence/dual-write-cutover.md](docs/persistence/dual-write-cutover.md) - CTE dual-write retirement plan and read-path cutover inventory.
- [docs/architecture/agent-org.md](docs/architecture/agent-org.md) - agent organization v1 (pods, dev-only inboxes, scoped keys, suppression gate): what's real today and what isn't. Full design rationale in [DESIGN_agent-org.md](DESIGN_agent-org.md).
- [CHANGELOG.md](CHANGELOG.md) - change history.
- [CONTRIBUTING.md](CONTRIBUTING.md) - contribution workflow.
- [docs/runbooks/](docs/runbooks) - operational runbooks.

## License

RegEngine is proprietary, source-visible software — all rights reserved by RegEngine LLC ([LICENSE](LICENSE)). **This repository is private.** Transparency and audit are served by the public proof surface above, which requires no source access; where source is shared it is shared under licence, not as an open-source project: viewing the source is welcome, but no rights to use, modify, or redistribute are granted. External pull requests are not accepted ([CONTRIBUTING.md](CONTRIBUTING.md)). Licensing inquiries: legal@regengine.co.

> **Before changing this repository's visibility**, work through [docs/security/PRE_PUBLIC_CHECKLIST.md](docs/security/PRE_PUBLIC_CHECKLIST.md). Confidential business material is currently tracked in-tree, and `git rm` removes it from `HEAD` only — every prior revision stays readable.

Permissive exceptions — the public verifier tools are **Apache 2.0** (declared in [LICENSE](LICENSE)) so anyone can use, copy, and embed them: the Merkle bundle verifier ([frontend/public/sdk/verify_chain.py](frontend/public/sdk/verify_chain.py)) and the `regengine-verify` per-record CLI ([regengine/verify_records.py](regengine/verify_records.py)). [Inflow Lab](https://github.com/regengine/inflow-lab), the integration simulator, is Apache 2.0 in its own repository for the same reason.

## Contributing

Before changing schema, ingestion, auth, tenant isolation, or audit logic, start with:

- [docs/engineering/SCHEMA_CHANGE_POLICY.md](docs/engineering/SCHEMA_CHANGE_POLICY.md)
- [.github/agents/regengine-implementer.agent.md](.github/agents/regengine-implementer.agent.md)
- [.github/CODEOWNERS](.github/CODEOWNERS)

Keep changes scoped. Do not treat old issue text, stale docs, or marketing copy as proof of current behavior; verify against code, tests, and GitHub Actions. If docs and code conflict, fix or call out the conflict in the PR.
