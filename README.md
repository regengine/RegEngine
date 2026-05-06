# RegEngine

RegEngine is a pre-production FSMA 204 traceability application. The codebase ingests food supply-chain records, normalizes them into CTE/KDE event data, stores tenant-scoped records in PostgreSQL, evaluates rule outcomes, and exposes audit/export surfaces for FDA traceability workflows.

Current product wedge: Inflow prepares, Engine proves. Supplier and ERP data is preflighted, scored, routed into a fix queue, and gated before it becomes tenant-scoped traceability evidence.

This README describes behavior that is visible in checked-in code, configuration, tests, and runbooks.

## Current Status

- Stage: pre-production.
- Backend deploy target in checked-in Railway config: one consolidated FastAPI app in [server/main.py](server/main.py), built by the repo-root [Dockerfile](Dockerfile).
- Frontend: Next.js App Router app in [frontend/](frontend/).
- Database migrations: Alembic at [alembic/versions/](alembic/versions/).
- Primary domain: FSMA 204 food traceability. Other regulatory, document, NLP, and graph modules exist, but FSMA ingestion and compliance are the best-evidenced product path in this repository.

## What The Product Does

Verified product capabilities in the current tree:

| Capability | Evidence |
| --- | --- |
| API key protected webhook CTE ingest | [services/ingestion/app/webhook_router_v2.py](services/ingestion/app/webhook_router_v2.py) |
| CSV template download and CSV CTE ingest | [services/ingestion/app/csv_templates.py](services/ingestion/app/csv_templates.py) |
| EPCIS ingest routes | [services/ingestion/app/epcis/router.py](services/ingestion/app/epcis/router.py) |
| EDI ingest routes and parser modules | [services/ingestion/app/edi_ingestion/](services/ingestion/app/edi_ingestion/) |
| Inflow Workbench preflight, readiness, fix queue, scenario library, and commit gate | [services/ingestion/app/inflow_workbench.py](services/ingestion/app/inflow_workbench.py) |
| Supplier portal preflight before persistence | [services/ingestion/app/supplier_portal.py](services/ingestion/app/supplier_portal.py) |
| CTE persistence, hash-chain storage, and verification | [services/shared/cte_persistence/core.py](services/shared/cte_persistence/core.py) |
| Compliance score reads from stored FSMA CTE data | [services/ingestion/app/compliance_score.py](services/ingestion/app/compliance_score.py) |
| FDA export routes | [services/ingestion/app/fda_export/router.py](services/ingestion/app/fda_export/router.py) |
| Tenant/admin/user/API-key management | [services/admin/app/](services/admin/app/) |
| Tamper-evident admin audit log hashing | [services/admin/app/audit.py](services/admin/app/audit.py) |
| Audit-chain verification for admin audit exports | [services/admin/app/audit_integrity.py](services/admin/app/audit_integrity.py) |
| Scheduler jobs and scheduler metrics surface | [services/scheduler/](services/scheduler/) |
| Frontend dashboard, auth, sandbox, docs, and product pages | [frontend/src/app/](frontend/src/app/) |

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

The strongest tested path is Inflow Workbench preflight plus persisted CTE data plus compliance/export support. Graph, NLP, generic regulatory-intelligence, and document-ingestion modules are present, but they should not be treated as the core product contract without checking the relevant tests and deploy wiring.

## Architecture

### Runtime Shape

The repo still contains six service directories:

| Directory | Purpose |
| --- | --- |
| [services/admin](services/admin) | tenants, users, roles, MFA, API keys, audit logs, admin routes |
| [services/ingestion](services/ingestion) | webhook, CSV, EPCIS, EDI, sandbox, export, CTE persistence integration |
| [services/compliance](services/compliance) | compliance validation routes and FSMA rules JSON |
| [services/graph](services/graph) | graph and supply-chain query modules |
| [services/nlp](services/nlp) | regulatory/document extraction modules |
| [services/scheduler](services/scheduler) | scheduled jobs, job metrics, operational checks |

The repo-root Dockerfile copies all service directories and starts [server/main.py](server/main.py) with Gunicorn/Uvicorn. `server/main.py` mounts routers from the service directories into one FastAPI process.

The old independent service entrypoints still exist, for example [services/ingestion/main.py](services/ingestion/main.py), but the repo-root [railway.toml](railway.toml) points at the root Dockerfile.

### Infrastructure

Verified from checked-in config and code:

- PostgreSQL is required. Production connection is supplied through `DATABASE_URL`.
- Local development stack in [docker-compose.dev.yml](docker-compose.dev.yml) starts PostgreSQL only.
- Redis is used by rate limiting, queues, session/subscription checks, and other runtime paths when configured.
- Neo4j code and health checks exist, but the default local development stack does not start Neo4j.
- The frontend is a separate Next.js application with its own package lock and CI workflow.

## Data And Schema

- Alembic is the active schema migration system.
- Root migration config: [alembic.ini](alembic.ini).
- Migration files: [alembic/versions/](alembic/versions/).
- Deploy migration runner: [scripts/run-migrations.sh](scripts/run-migrations.sh).
- Legacy Flyway-style SQL files still exist under service directories and are tracked as orphan-migration debt by [scripts/check_orphan_migrations.py](scripts/check_orphan_migrations.py).

Schema-related CI guards include:

- [scripts/check_alembic_revisions.py](scripts/check_alembic_revisions.py)
- [scripts/check_tenant_id_uuid_only.py](scripts/check_tenant_id_uuid_only.py)
- [scripts/check_orphan_migrations.py](scripts/check_orphan_migrations.py)

## Rule Enforcement

FSMA rule evaluation has both advisory and blocking modes.

- The rule enforcement switch is `RULES_ENGINE_ENFORCE`.
- Supported modes are implemented in [services/shared/rules/enforcement.py](services/shared/rules/enforcement.py).
- Rollout steps are documented in [docs/runbooks/RULES_ENGINE_ENFORCE_ROLLOUT.md](docs/runbooks/RULES_ENGINE_ENFORCE_ROLLOUT.md).

Do not assume every ingestion path rejects all non-compliant records by default. Check the deployed `RULES_ENGINE_ENFORCE` setting and route-specific tests before treating a tenant path as blocking.

## Security And Tenant Boundaries

Verified controls in the codebase:

- API-key auth and API-key storage utilities live under [services/shared/auth.py](services/shared/auth.py) and [services/shared/api_key_store.py](services/shared/api_key_store.py).
- Ingestion authorization helpers live in [services/ingestion/app/authz.py](services/ingestion/app/authz.py).
- Admin auth routes and MFA code live under [services/admin/app/](services/admin/app/).
- Tenant context middleware lives under [services/shared/middleware/](services/shared/middleware/).
- PostgreSQL RLS migrations exist in Alembic.
- Rate limiting code exists for multiple surfaces, including tenant-scoped ingestion limits and auth-related limits.
- Frontend auth uses Supabase session state plus a RegEngine JWT/cookie flow. See [frontend/src/lib/auth-context.tsx](frontend/src/lib/auth-context.tsx), [frontend/src/proxy.ts](frontend/src/proxy.ts), and [frontend/src/app/login/LoginClient.tsx](frontend/src/app/login/LoginClient.tsx).

Known authentication caveat: the dual Supabase plus RegEngine JWT flow can produce session mismatch states. Treat auth behavior as code-and-test verified, not marketing-copy verified.

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
alembic upgrade head
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

Ingestion full suite, matching the CI hard gate:

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

Notes:

- The ingestion full suite is a hard backend CI gate.
- Local `.env` is loaded by `BaseServiceSettings`; developer-specific values can affect config-default tests. CI runs from a clean environment.
- Some integration tests skip when Docker, external services, or a live local service are unavailable.

## CI/CD

Main workflows live in [.github/workflows/](.github/workflows/).

Backend CI includes:

- test matrix by service
- lint matrix by service plus `services/shared`
- Docker build for the consolidated image
- security audit matrix
- Alembic revision guard
- orphan migration guard
- tenant_id UUID guard
- ingestion full suite hard gate
- final `ci-status` gate

Frontend CI is separate in [.github/workflows/frontend-ci.yml](.github/workflows/frontend-ci.yml).

## Deployment

Verified deployment files:

- [Dockerfile](Dockerfile) builds the backend image, installs root `requirements.lock`, runs Alembic migrations through [scripts/run-migrations.sh](scripts/run-migrations.sh), and starts `server.main:app`.
- [railway.toml](railway.toml) points Railway at the root Dockerfile and uses `/health` as the healthcheck.
- [frontend/](frontend/) is a Next.js application with its own package lock and scripts.

## Important Limitations

These are current repo facts, not speculation:

- The codebase still contains both consolidated-monolith wiring and legacy service entrypoints.
- Legacy/orphan migration files still exist and are guarded by an allowlist. See [scripts/orphan_migrations_allowlist.txt](scripts/orphan_migrations_allowlist.txt).
- A live ORM-to-database type assertion startup check now runs during startup for
  the admin ORM/schema path; extend that coverage deliberately if more ORM
  surfaces become part of the production contract.
- Rule failures are not universally blocking unless the relevant enforcement mode is enabled and the route supports it.
- Some architecture documentation is older than the current Dockerfile/server wiring; verify against code before using docs as operational truth.
- Neo4j, Redis, Redpanda/Kafka-compatible code paths exist, but the default local dev compose file starts only PostgreSQL.
- This repository does not prove broad production adoption, paid customer status, regulatory approval, or FDA certification.

## Documentation Map

- [ARCHITECTURE.md](ARCHITECTURE.md) - current runtime shape and debt register.
- [CURRENT_SYSTEM_MAP.md](CURRENT_SYSTEM_MAP.md) - system map.
- [ASYNC_PROCESSES.md](ASYNC_PROCESSES.md) - async and background processing notes.
- [CANONICAL_OWNERSHIP.md](CANONICAL_OWNERSHIP.md) - module ownership notes.
- [SECURITY.md](SECURITY.md) - security posture.
- [CHANGELOG.md](CHANGELOG.md) - change history.
- [CONTRIBUTING.md](CONTRIBUTING.md) - contribution workflow.
- [docs/runbooks/](docs/runbooks) - operational runbooks.

## Contributing

Before changing schema, ingestion, auth, tenant isolation, or audit logic, start with:

- [docs/engineering/SCHEMA_CHANGE_POLICY.md](docs/engineering/SCHEMA_CHANGE_POLICY.md)
- [.github/agents/regengine-implementer.agent.md](.github/agents/regengine-implementer.agent.md)

Keep changes scoped. Do not treat old issue text, stale docs, or marketing copy as proof of current behavior; verify against code, tests, and GitHub Actions. If docs and code conflict, fix or call out the conflict in the PR.
