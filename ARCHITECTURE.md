# RegEngine Architecture

Runtime shape, router policy, and infrastructure below were checked against
repository revision `07126f662c50a49a03ddd0cfc17e7c77ce8803a3` on 2026-11-04.
They describe checked-in configuration and code, not proof of what is running
in any environment. The technical-debt measurements remain dated historical
observations; remeasure before using them for planning.

## Deployment Model

The checked-in deployment target is **one consolidated FastAPI app** and a
separate Next.js frontend. Railway configuration builds the repo-root
`Dockerfile`; the image runs migrations and starts `server.main:app`.
The checked-in production deployment workflow is manually dispatched and
requires a successful backend CI gate. A merge does not establish that a
revision has been deployed; verify the deployed revision and configuration
separately.

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

- `server/main.py` mounts routers from the service directories into a single
  FastAPI process.
- Legacy entrypoints like `services/ingestion/main.py` still exist for local
  debugging and compatibility, but they are not the checked-in production
  deploy target.
- Production requires `ENABLED_ROUTERS` to match the exact release-approved
  set in `server/router_policy.py`; missing, extra, or unknown names abort
  startup. Production rejects `DISABLED_ROUTERS` and
  `ENABLE_EXPERIMENTAL_ROUTERS=true`. Non-production retains broad mounting
  and a `DISABLED_ROUTERS` override, with additional protection for compliance
  routers. Some base routes are mounted unconditionally. See
  `docs/engineering/ROUTER_SURFACE.md` for the surface audit.

## Infrastructure

- **Backend hosting target:** Railway via one container configured by
  `railway.toml`; this file does not prove the current live deployment.
- **Frontend:** Next.js App Router app in `frontend/` with a separate CI
  workflow.
- **Database:** PostgreSQL via `DATABASE_URL`, with schema managed by
  Alembic (`alembic/versions/`). At the revision above,
  `python3 scripts/check_alembic_revisions.py` reports the single head
  `08c7cf36ddbe` (v141). This is the repository migration head, not evidence
  that any database has reached it. The deployed migration runner requires a
  separate `MIGRATIONS_DATABASE_URL` schema-owner credential; local scratch
  databases may use `DATABASE_URL`. Application boot performs no schema DDL
  as of v098/v099.
- **Runtime helpers:** Redis is used by rate limiting, session/JWT paths,
  subscription/entitlement checks, idempotency caching, and task-processing
  helpers when configured. The local dev stack
  (`docker-compose.dev.yml`) starts PostgreSQL **and** Redis — without Redis
  the subscription gate fails closed with 503, so authenticated ingest does
  not work locally.
- **Async/event backbone:** the consolidated deploy path uses PostgreSQL-backed
  task processing via `server/workers/task_processor.py` and
  `services/shared/task_queue.py`. Legacy Kafka/Redpanda code paths still exist
  in-tree and should be treated as remediation drift, not the primary deploy
  contract.
- **Graph:** Neo4j integration code and health checks exist, but the default
  local development stack does not start Neo4j.
- **Readiness:** `/readiness` requires PostgreSQL, Redis in strict deployed
  runtimes, and healthy essential background units (the ingestion worker and,
  when enabled, the embedded scheduler). Probe capacity exhaustion or timeout
  also returns 503. Neo4j and rate-limiter health do not alone fail readiness;
  `/health` is a separate liveness endpoint. See `server/main.py`.
- **Edge / gateway:** the checked-in Railway container runs
  `gunicorn server.main:app` directly. The defense against a client-supplied
  `X-RegEngine-Tenant-ID` header is the in-app
  `TenantContextMiddleware` (`services/shared/middleware/tenant_context.py`),
  which rejects the header unless it carries a valid `REGENGINE_INTERNAL_SECRET`
  (covered by `tests/security/test_header_remediation.py`). `infra/gateway/nginx.conf`
  is a reference-only config (with its own test suite); it is not in the
  checked-in image. Verify any external gateway configuration separately.

## Current Architecture Direction

- The checked-in backend deployment target is consolidated.
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

- `requirements.in` is the human-edited dependency spec.
- `requirements.lock` is the fully pinned, hash-verified install set used by CI
  and the production Docker build.
- `pyproject.toml` declares the supported Python version range.

Backend CI and security checks run against the root lockfile. Do not treat old
service-scoped dependency assumptions as current deploy truth unless a file
explicitly says it is legacy-only.

### Frontend (Node.js)

Frontend dependencies are locked via `frontend/package-lock.json`. The Next.js
application is validated in its own workflow.

## Known Technical Debt

### Large Modules

Source modules above 1,000 lines, re-measured 2026-07-31 (`wc -l`,
excluding tests):

| File | Lines | Area | Likely split direction |
| --- | ---: | --- | --- |
| `services/ingestion/app/fda_export/router.py` | 1312 | export API | separate query, bundle assembly, and format writers |
| `services/scheduler/service.py` | 1268 | scheduler runtime | split scrape orchestration, emission/ack, and job registration |
| `services/shared/canonical_persistence/writer.py` | 1228 | shared persistence | extract write-path helpers and transaction orchestration |
| `services/ingestion/app/inflow_workbench.py` | 1216 | ingestion preflight | split preflight, readiness scoring, fix queue, and commit gate |
| `services/shared/api_key_store.py` | 1180 | shared auth | split storage adapters from validation helpers |
| `services/ingestion/app/routes_ingest.py` | 1118 | ingestion API | separate route wiring from validation and persistence |
| `services/graph/app/routers/fsma/compliance.py` | 1094 | graph API | split query builders from response shaping |
| `server/main.py` | 1088 | app composition | extract router registration and startup checks from lifespan |
| `services/shared/canonical_event.py` | 1074 | shared model | split schema, hashing, and conversion helpers |
| `server/workers/task_processor.py` | 1063 | async worker | separate queue polling, dispatch, and retry policy |
| `services/admin/app/metrics.py` | 1046 | admin observability | separate metric definitions from collectors/endpoints |
| `services/admin/app/session_store.py` | 1042 | admin auth | split Redis and in-memory backends from session policy |
| `services/graph/app/fsma_audit.py` | 1020 | graph audit | separate traversal from audit-record assembly |

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
