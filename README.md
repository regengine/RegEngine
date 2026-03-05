# RegEngine

[![Backend CI](https://github.com/PetrefiedThunder/RegEngine/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/PetrefiedThunder/RegEngine/actions/workflows/backend-ci.yml)
[![Frontend CI](https://github.com/PetrefiedThunder/RegEngine/actions/workflows/frontend-ci.yml/badge.svg)](https://github.com/PetrefiedThunder/RegEngine/actions/workflows/frontend-ci.yml)
[![Security](https://github.com/PetrefiedThunder/RegEngine/actions/workflows/security.yml/badge.svg)](https://github.com/PetrefiedThunder/RegEngine/actions/workflows/security.yml)

**API-first FSMA 204 compliance infrastructure for recall-ready traceability.**

RegEngine converts supply-chain traceability events into structured, exportable, and independently verifiable compliance records — built to meet the FDA's 24-hour response window for food recall events.

## Why FSMA 204

The FDA's Food Safety Modernization Act Section 204 requires companies across the food supply chain to maintain records that can be produced within 24 hours of an FDA request. RegEngine automates the obligation mapping, evidence collection, and export workflow so that compliance teams spend their time on operations, not spreadsheets.

## Production Topology

| Layer | Service | Host |
|---|---|---|
| Frontend + edge | Next.js 14 on Vercel | `regengine.co` |
| App / API | FastAPI on Railway | `RegEngine` service |
| Relational DB | PostgreSQL 16 | Railway managed |
| Graph DB | Neo4j 5 Community | Railway managed |
| Cache / sessions | Redis 7 | Railway managed |

This 5-service runtime is intentionally minimal.

## Core Capabilities

- **FSMA obligation mapping** — regulation-to-control-to-evidence graph in Neo4j
- **Tamper-evident evidence model** — SHA-256 hash-chain primitives on every record
- **Compliance scoring** — coverage x effectiveness x freshness, computed per obligation
- **Multi-tenant enforcement** — row-level security with database-enforced isolation
- **Audit logging** — immutable event stream for every tenant action
- **Supplier onboarding** — guided wizard and bulk-upload ingestion for supply-chain partners
- **Free FSMA utilities** — FTL checker, readiness assessment, recall simulation tools

## Supplier Onboarding Flow

1. Buyer invite
2. Supplier signup
3. Facility registration
4. FTL category scoping
5. CTE/KDE capture
6. TLC management
7. Supplier compliance dashboard
8. FDA export

Route: `/onboarding/supplier-flow`

## Tech Stack

**Backend:** Python 3.11, FastAPI, SQLAlchemy 2, Neo4j driver, Redis, Kafka
**Frontend:** Next.js 14, React, Tailwind CSS, Vitest
**Infrastructure:** Docker, Railway, Vercel
**Observability:** OpenTelemetry, Prometheus, Sentry

## Local Development

Start core services:

```bash
docker-compose up -d
```

Start the backend (example for the admin service):

```bash
cd services/admin
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Start the frontend:

```bash
cd frontend
npm ci
npm run dev
```

## Running Tests

Backend (per-service):

```bash
cd services/admin
pytest tests/ -v --cov=app
```

Frontend:

```bash
cd frontend
npm run test:run        # single run
npm run lint            # eslint
npm run build           # production build check
```

## Deployment Notes

- Vercel-hosted frontend must use a **public** admin API base URL.
- Set `NEXT_PUBLIC_ADMIN_URL=https://<railway-public-domain>` on Vercel.
- Do not rely on private/internal hostnames from Vercel runtime routes.

## Reference Docs

| Document | Path |
|---|---|
| FSMA deployment runbook | `docs/FSMA_RAILWAY_DEPLOYMENT.md` |
| Env setup checklist | `docs/ENV_SETUP_CHECKLIST.md` |
| FSMA 204 MVP spec | `docs/specs/FSMA_204_MVP_SPEC.md` |
| Architecture overview | `docs/ARCHITECTURE.md` |
| Disaster recovery | `docs/DISASTER_RECOVERY.md` |
| Incident response | `docs/security/INCIDENT_RESPONSE.md` |

---

Status: Active FSMA wedge execution with production auth stabilized and supplier onboarding V1 live.
