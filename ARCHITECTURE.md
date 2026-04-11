# RegEngine Architecture

## Deployment Model

RegEngine runs as **6 independent microservices** behind a Next.js frontend. Each service has its own Dockerfile, Railway deployment, and test suite.

## Active Services

| Service | Port | Purpose | Tests |
|---------|------|---------|-------|
| `services/admin` | 8001 | Tenant management, API keys, user auth, bulk upload | 15 files |
| `services/ingestion` | 8002 | Webhook ingestion, CTE/KDE validation, EPCIS normalization | 31 files |
| `services/compliance` | 8500 | Compliance scoring, rule evaluation, export generation | 2 files |
| `services/graph` | 8003 | Knowledge graph, identity resolution, supply chain queries | 15 files |
| `services/nlp` | 8004 | Document ingestion, regulatory text extraction | 9 files |
| `services/scheduler` | 8005 | Cron jobs, recall drills, export scheduling | 4 files |

## Shared Code

`services/shared/` contains cross-service utilities (identity resolution, error handling, path setup). Imported by all 6 services (433 import references).

## Frontend

Next.js App Router deployed to Vercel. Proxies API calls to backend services via `next.config.js` rewrites and `/api/proxy` route.

## Infrastructure

- **Backend hosting:** Railway (per-service containers)
- **Frontend hosting:** Vercel
- **Database:** PostgreSQL (Supabase)
- **Cache:** Redis
- **Message queue:** Redpanda (Kafka-compatible)

## Target Architecture

The long-term plan is to consolidate the 6 services into a single monolith, replacing Kafka/Redis with PostgreSQL-native patterns. This consolidation has not started — all services are currently independently deployed and tested.

## Dependency Management

### Backend (Python)

Dependencies use `>=` pins for flexibility during active development.
Before production freeze, generate locked requirements with `pip-compile`:

```bash
pip install pip-tools
for svc in admin compliance graph ingestion nlp scheduler; do
  pip-compile services/$svc/requirements.txt \
    --output-file services/$svc/requirements.lock \
    --strip-extras --no-header
done
```

Current state by service:

| Service | Deps | Pinned | Notes |
|---------|------|--------|-------|
| admin | 39 | 4 (OpenTelemetry) | Largest surface after ingestion |
| ingestion | 57 | 4 (OpenTelemetry) | Most deps — webhook/EPCIS/connector breadth |
| graph | 35 | 4 (OpenTelemetry) | Neo4j driver, networkx |
| nlp | 22 | 4 (OpenTelemetry) | Document parsing, spaCy |
| compliance | 15 | 4 (OpenTelemetry) | Lean — scoring + export only |
| scheduler | 14 | 0 | Cron jobs — no OTel yet |

All services share common `>=` pins for FastAPI, SQLAlchemy, Pydantic, and Alembic.
Only OpenTelemetry packages are exact-pinned (`==`) due to cross-package version sensitivity.

### Frontend (Node.js)

Dependencies are locked via `package-lock.json` (npm).
`next`, `@sentry/nextjs`, and `@supabase/supabase-js` are pinned to exact versions
(no `^` or `~`) — bumped manually after testing due to prior production incidents.
