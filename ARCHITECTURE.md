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

## Production Spine vs Experimental

**Production spine** (must work, must be tested, must be monitored):
```
ingestion → canonicalization → identity resolution → compliance evaluation → audit → FDA export
```

**Experimental / non-essential** (isolated from production spine):
- `services/graph/` — Neo4j graph queries, knowledge graph. Target: consolidate into
  PostgreSQL. Do not let graph requirements shape core architecture decisions.
- `services/nlp/` — Document ingestion, regulatory text extraction. Useful but not
  required for core FSMA 204 compliance. The production spine runs without it.
- Advanced NLP entity extraction via Kafka consumers — legacy pipeline, being replaced
  by direct function calls in the monolith.

The production spine can stand on its own without graph or NLP services.

## Target Architecture

The 6 services are consolidating into a modular monolith. This is ~95% complete:
`server/main.py` already mounts 66 routers from all services into a single FastAPI app.
One inter-service HTTP call remains (Stripe billing → Admin tenant creation).
The scheduler service still runs as a separate process (APScheduler with distributed
leadership). See ASYNC_PROCESSES.md for details.

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

### Large file splits (completed)

12 of 14 monolithic files (>1,000 lines) have been split into focused subpackages.
All splits preserve backward-compatible imports via `__init__.py` re-exports.

| File | Status | Package |
|------|--------|---------|
| `rules_engine.py` | ✅ Split | `shared/rules/` (9 modules) |
| `sandbox_router.py` | ✅ Split | `ingestion/app/sandbox/` |
| `epcis_ingestion.py` | ✅ Split | `ingestion/app/epcis/` |
| `fda_export_router.py` | ✅ Split | `ingestion/app/fda_export/` |
| `fsma_utils.py` | ✅ Split | `graph/app/fsma/` |
| `canonical_persistence.py` | ✅ Split | `shared/canonical_persistence/` |
| `identity_resolution.py` | ✅ Split | `shared/identity_resolution/` |
| `audit_logging.py` | ✅ Split | `shared/audit_logging/` |
| `cte_persistence.py` | ✅ Split | `shared/cte_persistence/` |
| `edi_ingestion.py` | ✅ Split | `ingestion/app/edi_ingestion/` |
| `stripe_billing.py` | ✅ Split | `ingestion/app/stripe_billing/` |
| `fsma_recall.py` | ✅ Split | `graph/app/fsma_recall/` |
| `fsma_extractor.py` | Relocated | `nlp/app/extractors/` |
| `compliance.py` | Relocated | `graph/app/routers/fsma/` |
