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

## Known Technical Debt

### Large files (>1,000 lines)

These files work correctly but exceed recommended size thresholds. Splitting is tracked for post-funding engineering:

| File | Lines | Service | Split strategy |
|------|-------|---------|----------------|
| `sandbox_router.py` | 1,576 | Ingestion | Extract sandbox models + validation |
| `rules_engine.py` | 1,547 | Shared | Split rule types into submodules |
| `epcis_ingestion.py` | 1,365 | Ingestion | Extract EPCIS parser + validator |
| `fda_export_router.py` | 1,362 | Ingestion | Extract PDF generator + CSV builder |
| `fsma_utils.py` | 1,353 | Graph | Extract trace builder + graph queries |
| `fsma_extractor.py` | 1,344 | NLP | Extract entity resolver + classifier |
| `cte_persistence.py` | 1,284 | Shared | Extract query builder + batch ops |
| `identity_resolution.py` | 1,283 | Shared | Extract matcher + scorer |
| `fsma_recall.py` | 1,203 | Graph | Extract recall simulator + reporter |
| `stripe_billing.py` | 1,185 | Ingestion | Extract webhook handler + plan mgmt |
| `audit_logging.py` | 1,069 | Shared | Extract formatters + storage |
| `edi_ingestion.py` | 1,043 | Ingestion | Extract parser + segment mapper |
| `canonical_persistence.py` | 1,034 | Shared | Extract query layer + migrations |
| `compliance.py` | 1,008 | Graph | Extract scoring + export |

Each file is functional, tested, and production-stable. Splitting is a refactoring task, not a bug fix.
