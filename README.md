# RegEngine

**FSMA 204 food traceability compliance for farms and food companies.**

RegEngine helps food suppliers meet FDA Food Safety Modernization Act Section 204 requirements — from CTE ingestion to FDA-ready export — without six-figure enterprise contracts or months of onboarding.

**Live at [regengine.co](https://regengine.co)**

## What RegEngine Does

- Ingest Critical Tracking Events (CTEs) via API, CSV, EDI, EPCIS, or IoT adapters
- Validate Key Data Elements (KDEs) against 21 CFR Part 1, Subpart S
- Score compliance readiness across your supply chain
- Generate FDA-compliant sortable spreadsheets within the 24-hour response window
- Trace lots forward and backward through a graph database
- Run recall simulations and drill workflows

## Pricing

| Plan | Price | CTEs/month | Locations |
|---|---|---|---|
| **Growth** | $1,299/mo ($1,079 annual) | 10,000 | 3 |
| **Scale** | $2,499/mo ($2,079 annual) | 100,000 | 10 |
| **Enterprise** | Custom | Unlimited | Unlimited |

Overage: $0.001/CTE beyond plan limits. All plans include a 14-day trial.

## FSMA 204 Compliance Date

**July 20, 2028** — extended from the original January 2026 deadline per FDA enforcement discretion and Congressional action.

## Repo Structure

Monorepo with two primary surfaces:

```text
.
├── frontend/          Next.js 15 App Router (deployed on Vercel)
├── services/
│   ├── admin/         Auth, tenants, onboarding, API keys
│   ├── ingestion/     Ingest pipelines, webhook persistence, FDA export
│   ├── compliance/    FSMA checklist, validation, compliance endpoints
│   ├── graph/         Traceability graph, recall, lineage analysis
│   ├── nlp/           Extraction and document processing
│   ├── scheduler/     Scheduled jobs and feed polling
│   └── shared/        Bootstrap, middleware, schemas, auth, observability
├── docs/              Specs, setup guides, deployment runbooks
├── scripts/           Dev and CI scripts
└── migrations/        Database migrations
```

## Tech Stack

**Frontend:** Next.js 15, React 18, TypeScript, Tailwind CSS, Radix UI, Framer Motion, TanStack Query

**Backend:** FastAPI (Python), PostgreSQL, Neo4j (graph), Kafka, Supabase

**Infrastructure:** Vercel (frontend), Railway (backend services)

## Quick Start

```bash
git clone https://github.com/PetrefiedThunder/RegEngine.git
cd RegEngine

# Backend
bash scripts/setup_dev.sh

# Frontend
cd frontend
npm install
npm run dev
```

See [`docs/LOCAL_SETUP_GUIDE.md`](docs/LOCAL_SETUP_GUIDE.md) and [`docs/ENV_SETUP_CHECKLIST.md`](docs/ENV_SETUP_CHECKLIST.md) for full setup.

## Key Specs

- [FSMA 204 MVP Spec](docs/specs/FSMA_204_MVP_SPEC.md)
- [Railway Deployment Guide](docs/FSMA_RAILWAY_DEPLOYMENT.md)

## Verification

```bash
# Backend tests
python -m pytest tests -q

# Frontend
cd frontend && npm run lint && npm run build
```

## Current Status

The repo has been refocused to FSMA 204 as the sole vertical. Some internal admin and owner dashboard surfaces still contain mock data. The public-facing product at regengine.co is live and actively deployed.

---

*Food traceability compliance for farms and food companies. Don't trust, verify.*
