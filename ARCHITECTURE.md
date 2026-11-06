# RegEngine Architecture

Last verified: 2026-11-04 — every repository path named in this file resolves
(`scripts/check_docs_links.py`), the Large Modules table is regenerated from the
tree and checked by `scripts/check_docs_counts.py`, and the edge/gateway
paragraph follows the 2026-10-30 archive of the retired topology. The
deployment model, runtime shape, infrastructure and dependency-management prose
was last re-read against code on 2026-07-31; sections carry their own dates
where a claim was verified earlier and not re-checked.

Partial re-verification 2026-08-26 (#2871): only the Alembic schema-head
claim in **Infrastructure** below was re-checked against
`alembic/versions/`. Every other section still carries its 2026-07-31
date and was **not** re-verified on 2026-08-26.

## Deployment Model

RegEngine is deployed as **one consolidated FastAPI app** behind a Next.js
frontend. The checked-in Railway config builds the repo-root `Dockerfile`, and
that image starts `server.main:app`.

The repository still keeps six former service directories because they remain
useful decomposition seams in the codebase:

| Directory | Current role |
| --- | --- |
| `services/admin` | tenants, users, roles, MFA, API keys, audit logs, admin routes |
| `services/ingestion` | webhook, CSV, EPCIS, EDI, sandbox, export, CTE persistence integration |
| `services/compliance` | compliance validation routes and FSMA rules JSON |
| `services/graph` | graph and supply-chain query modules |
| `services/nlp` | regulatory and document extraction modules |
| `services/scheduler` | scheduled jobs, operational checks, and metrics |

## Current Runtime Shape

- `server/main.py` builds the single FastAPI process: app construction,
  middleware order and the lifespan. Since WI-14 (2026-11-04) it calls
  `server/startup_checks.py` (import-time gates and best-effort startup steps),
  `server/workers_boot.py` (task worker and embedded scheduler),
  `server/routers_mount.py` (router registration in first-match order) and
  `server/readiness.py` (`/readiness`).
- Legacy entrypoints like `services/ingestion/main.py` still exist for local
  debugging and compatibility, but they are not the checked-in production
  deploy target.
- Production can auto-disable experimental routers unless
  `ENABLE_EXPERIMENTAL_ROUTERS=true`. See
  `docs/engineering/ROUTER_SURFACE.md` for the current surface audit.

## Infrastructure

- **Backend hosting:** Railway via one monolith container defined by
  `railway.toml`.
- **Frontend:** Next.js App Router app in `frontend/` with a separate CI
  workflow.
- **Database:** PostgreSQL via `DATABASE_URL`. Schema is owned entirely by
  Alembic (`alembic/versions/`, head is **v112** —
  `d8b2056471a7_v112_seed_obligations_security_definer`, which makes
  `seed_obligations_for_tenant` `SECURITY DEFINER` with a pinned `search_path`
  and fail-closed behaviour; verified 2026-08-27);
  the app performs no runtime DDL as of v098/v099. Neither v111 nor v112
  creates a table, so the newest tables are
  `fsma.rule_evaluation_deadletter` (v105, durable dead-letter for
  rule-evaluation persistence, replayed by the
  `rule_evaluation_deadletter_replay` scheduler job) and
  `fsma.tenant_seed_state` (v106, per-tenant obligation seed marker so an
  RLS deny-all empty read is no longer mistaken for an unseeded tenant).
  The revisions after those add no tables: v107 fixes the CTE-correction
  `BEFORE UPDATE` trigger to `RETURN NEW`, v108 adds the `result='error'`
  value plus the v105 marker columns that never shipped, v109 adds a
  tenant-bound `SECURITY DEFINER` team-roster reader, and v110 adds the
  RLS INSERT policy letting authenticated users create their own developer
  profile. v111 then FORCEs RLS on the two regulatory control-plane tables, and
  v112 hardens the `seed_obligations_for_tenant` function used at onboarding.
  `fsma.compliance_evidence_snapshots` (v103) and the v102 mock-audit drill
  records are no longer the newest tables.
- **Runtime helpers:** Redis is used by rate limiting, session/JWT paths,
  subscription/entitlement checks, idempotency caching, and task-processing
  helpers when configured. The local dev stack
  (`docker-compose.dev.yml`) starts PostgreSQL **and** Redis — without Redis
  the subscription gate fails closed with 503, so authenticated ingest does
  not work locally.
- **Async/event backbone:** PostgreSQL-backed task processing via
  `server/workers/task_processor.py` and `services/shared/task_queue.py` is the
  only backbone. The Kafka/Redpanda producers, consumers and the
  `EVENT_BACKBONE` switch were retired on 2026-11-04 (WI-05); the modules are
  under `docs/archive/retired-topology/kafka/` and `confluent-kafka` is no
  longer in `requirements.lock`.
- **Graph:** Neo4j integration code and health checks exist, but the default
  local development stack does not start Neo4j.
- **Edge / gateway:** there is no app-managed nginx layer in production — the
  Railway container runs `gunicorn server.main:app` directly. The authoritative
  defense against a client-supplied `X-RegEngine-Tenant-ID` header is the in-app
  `TenantContextMiddleware` (`services/shared/middleware/tenant_context.py`),
  which rejects the header unless it carries a valid `REGENGINE_INTERNAL_SECRET`
  (covered by `tests/security/test_header_remediation.py`). The reference-only
  nginx config and its tests were archived to `docs/archive/retired-topology/gateway/`
  on 2026-10-30; nothing in the production image or CI loads them.

## Current Architecture Direction

- The deployed shape is already consolidated.
- Current remediation work is about reducing drift between the monolith deploy
  path and older service-shaped scaffolding in code and docs.
- The service directories are code-organization boundaries, not proof of six
  live backend deploys.
- The production spine remains:

```text
ingest -> canonicalize -> validate -> persist evidence -> export
```

## Dependency Management

### Backend (Python)

Backend dependencies are managed at the repository root:

- `requirements.in` is the human-edited production dependency spec.
- `requirements.lock` is the fully pinned, hash-verified install set used by
  the production Docker build and every CI job.
- `requirements-dev.in` / `requirements-dev.lock` add the test tooling (pytest,
  hypothesis, testcontainers, aiosqlite) for CI jobs that run pytest; they are
  constrained by `requirements.lock` and never enter the image.
- `requirements-experimental.in` / `requirements-experimental.lock` hold the
  packages only `EXPERIMENTAL_ROUTERS` modules import (`pyzbar` today, from a
  static import trace); no CI job installs them.
- backend-ci's `image-import-check` job imports `server.main` from a clean
  virtualenv built from `requirements.lock` alone.
- `pyproject.toml` declares the supported Python version range.

Backend CI and security checks run against the root lockfile. Do not treat old
service-scoped dependency assumptions as current deploy truth unless a file
explicitly says it is legacy-only.

### Frontend (Node.js)

Frontend dependencies are locked via `frontend/package-lock.json`. The Next.js
application is validated in its own workflow.

## Known Technical Debt

### Large Modules

Source modules above 1,000 lines, re-measured 2026-11-04 (`wc -l`,
excluding tests; `scripts/check_docs_counts.py` fails CI when this table
drifts from the tree):

| File | Lines | Area | Likely split direction |
| --- | ---: | --- | --- |
| `services/ingestion/app/csv_templates.py` | 2502 | ingestion CSV | split header mapping, template catalogue, and Jev-assisted suggestions |
| `services/scheduler/service.py` | 1459 | scheduler runtime | split scrape orchestration, webhook/alert ack, and job registration |
| `services/shared/api_key_store.py` | 1488 | shared auth | split storage adapters from validation helpers |
| `services/ingestion/app/edi_ingestion/routes.py` | 1470 | ingestion EDI | separate upload handling from parsing and rejection logging |
| `services/shared/canonical_event.py` | 1466 | shared model | split schema, hashing, and conversion helpers |
| `services/shared/canonical_persistence/writer.py` | 1378 | shared persistence | extract write-path helpers and transaction orchestration |
| `services/ingestion/app/fda_export/router.py` | 1340 | export API | separate query, bundle assembly, and format writers |
| `services/graph/app/routers/fsma/compliance.py` | 1284 | graph API | split query builders from response shaping |
| `services/ingestion/app/inflow_workbench.py` | 1271 | ingestion preflight | split preflight, readiness scoring, fix queue, and commit gate |
| `services/graph/app/fsma_audit.py` | 1249 | graph audit | separate traversal from audit-record assembly |
| `services/ingestion/app/compliance_score.py` | 1209 | compliance scoring | split rule evaluation from report shaping |
| `services/ingestion/app/epcis/persistence.py` | 1181 | EPCIS persistence | separate document parsing from row writes |
| `services/shared/data_retention.py` | 1138 | shared retention | split policy table from purge execution |
| `services/ingestion/app/routes_ingest.py` | 1137 | ingestion API | separate route wiring from validation and persistence |
| `server/workers/task_processor.py` | 1126 | async worker | separate queue polling, dispatch, and retry policy |
| `services/admin/app/metrics.py` | 1118 | admin observability | separate metric definitions from collectors/endpoints |
| `services/admin/app/session_store.py` | 1047 | admin auth | split Redis and in-memory backends from session policy |
| `services/ingestion/app/stripe_billing/routes.py` | 1029 | billing API | split plans/checkout, webhooks, portal/invoices, and metered-usage routes into separate modules |
| `services/ingestion/app/fda_export/queries.py` | 1020 | export queries | split range, lot and trace queries from result shaping |
| `services/ingestion/app/fda_export_service.py` | 1019 | export service | separate query assembly from writers |
| `services/ingestion/app/remediation/service.py` | 1013 | remediation | split case lifecycle from notification side effects |

These are refactor candidates, not proof of broken behavior by
themselves.

Resolved since the 2026-05-23 list (verified 2026-07-31): three entries
no longer exist as files — `services/nlp/app/consumer/`,
`services/ingestion/app/webhook_router_v2/`, and
`services/nlp/app/extractors/fsma_extractor/` are now packages of the
same name. Four shrank below the threshold:
`services/shared/cte_persistence/core.py` (2067 → 387, split into
`queries`/`verification`/mixins), `services/shared/identity_resolution/service.py`
(1987 → 146), and `services/scheduler/main.py` (1290 → 231, with the
runtime now in `service.py`). The earlier 2026-05-06 list also included
`kernel/reporting/fsma_engine.py` (since removed) and
`services/ingestion/app/routes.py` (since split — now ~100 lines).
`services/nlp/app/consumer/__init__.py` (1,118 lines) left the table on
2026-11-04 when the Kafka consumer loop was archived (WI-05); the package now
holds only the extraction helpers the task processor imports. `server/main.py`
(1,271 lines) left the same day when WI-14 split it into `startup_checks.py`,
`workers_boot.py`, `routers_mount.py` and `readiness.py` (main is 450 lines).
