# RegEngine Architecture

Last verified: 2026-05-06

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

- `server/main.py` mounts routers from the service directories into a single
  FastAPI process.
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
- **Database:** PostgreSQL via `DATABASE_URL`.
- **Runtime helpers:** Redis is used by rate limiting, session/JWT paths, and
  task-processing helpers when configured.
- **Async/event backbone:** the consolidated deploy path uses PostgreSQL-backed
  task processing via `server/workers/task_processor.py` and
  `services/shared/task_queue.py`. Legacy Kafka/Redpanda code paths still exist
  in-tree and should be treated as remediation drift, not the primary deploy
  contract.
- **Graph:** Neo4j integration code and health checks exist, but the default
  local development stack does not start Neo4j.

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

Representative source modules above 1,000 lines as of 2026-05-06:

| File | Lines | Area | Likely split direction |
| --- | ---: | --- | --- |
| `services/shared/cte_persistence/core.py` | 2041 | shared persistence | extract query builder, batch ops, and verification helpers |
| `services/shared/identity_resolution/service.py` | 1987 | shared identity resolution | extract matcher, scorer, and orchestration paths |
| `services/nlp/app/consumer.py` | 1875 | NLP ingestion worker | separate consumer loop, auth, DLQ, and routing concerns |
| `services/nlp/app/extractors/fsma_extractor.py` | 1664 | NLP extraction | split entity resolution, classifiers, and mapping logic |
| `services/ingestion/app/webhook_router_v2.py` | 1476 | ingestion API | extract auth, validation, persistence, and response shaping |
| `services/ingestion/app/fda_export/router.py` | 1294 | export API | separate query, bundle assembly, and format writers |
| `services/scheduler/main.py` | 1234 | scheduler runtime | split job registration, health, and retention flows |
| `kernel/reporting/fsma_engine.py` | 1198 | reporting engine | separate scoring, report assembly, and formatting |
| `services/shared/canonical_persistence/writer.py` | 1155 | shared persistence | extract write-path helpers and transaction orchestration |
| `services/shared/api_key_store.py` | 1077 | shared auth | split storage adapters from validation helpers |
| `services/admin/app/metrics.py` | 1053 | admin observability | separate metric definitions from collectors/endpoints |
| `services/ingestion/app/routes.py` | 1050 | ingestion API | split non-core routes into narrower router modules |

These are refactor candidates, not proof of broken behavior by themselves.
