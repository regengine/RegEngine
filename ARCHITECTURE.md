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
