# RegEngine

FSMA-first compliance infrastructure for food traceability, supplier onboarding, and FDA-ready record export.

## What This Repo Is

RegEngine is a monorepo with two primary code surfaces:

- `services/` for FastAPI services and shared Python modules
- `frontend/` for the Next.js App Router product UI

The checked-in product narrative is FSMA 204 first. The active implementation is centered on:

- supplier onboarding and buyer-to-supplier flows
- traceability event ingest via webhook, CSV, EDI, EPCIS, and IoT adapters
- FSMA compliance scoring, traceability review, and FDA export workflows
- graph-backed traceability, recall, and FSMA analysis endpoints

## Active Service Surface

These are the main service directories the current product depends on:

| Service | Path | Default local port | Primary role |
|---|---|---:|---|
| Admin API | `services/admin` | 8400 | auth, tenants, onboarding, API keys, review/admin flows |
| Ingestion Service | `services/ingestion` | 8000 | ingest pipelines, webhook persistence, FDA export, supplier/team/product APIs |
| Compliance API | `services/compliance` | 8500 | FSMA checklist, validation, compliance endpoints |
| Graph Service | `services/graph` | 8200 | traceability graph, recall, lineage, FSMA graph analysis |
| NLP Service | `services/nlp` | 8100 | extraction and document processing |
| Scheduler | `services/scheduler` | 8600 | scheduled jobs and feed polling |
| Shared Modules | `services/shared` | n/a | shared bootstrap, middleware, schemas, auth, observability |

Service bootstrapping is standardized around [`services/shared/paths.py`](/Users/sellers/RegEngine/services/shared/paths.py), especially `ensure_shared_importable()`.

## Frontend

The frontend lives in `frontend/` and uses:

- Next.js 15
- React 18
- TypeScript
- Tailwind CSS
- Radix UI
- Framer Motion
- TanStack Query

Key product areas in the current app include:

- `/checkout`, `/pricing`, `/signup`, `/login`
- `/dashboard`, `/compliance`, `/trace`, `/review`
- `/onboarding` and `/onboarding/supplier-flow`
- `/tools/*` FSMA tool surfaces
- `/admin`, `/settings`, `/api-keys`

Some frontend pages are fully wired to backend APIs, but the repo still contains demo-data surfaces and fallback/mock behavior in a few areas. The README should not be read as a claim that every UI path is fully live-backed.

## FSMA Focus

The current wedge is FSMA 204 food traceability:

- Critical Tracking Events and Key Data Elements
- Traceability Lot Code workflows
- one-up/one-down traceability and recall readiness
- FDA 24-hour record production and export

Primary spec:

- [`docs/specs/FSMA_204_MVP_SPEC.md`](/Users/sellers/RegEngine/docs/specs/FSMA_204_MVP_SPEC.md)

Related setup and deployment docs:

- [`docs/LOCAL_SETUP_GUIDE.md`](/Users/sellers/RegEngine/docs/LOCAL_SETUP_GUIDE.md)
- [`docs/ENV_SETUP_CHECKLIST.md`](/Users/sellers/RegEngine/docs/ENV_SETUP_CHECKLIST.md)
- [`docs/FSMA_RAILWAY_DEPLOYMENT.md`](/Users/sellers/RegEngine/docs/FSMA_RAILWAY_DEPLOYMENT.md)

## Repo Layout

```text
.
├── services/
│   ├── admin/
│   ├── compliance/
│   ├── graph/
│   ├── ingestion/
│   ├── nlp/
│   ├── scheduler/
│   └── shared/
├── frontend/
├── docs/
├── scripts/
├── kernel/
├── migrations/
└── tests/
```

There are additional legacy or experimental directories in the repo, but the paths above are the main surfaces to use for current product work.

## Local Setup

Start with the detailed runbooks:

- [`docs/LOCAL_SETUP_GUIDE.md`](/Users/sellers/RegEngine/docs/LOCAL_SETUP_GUIDE.md)
- [`docs/ENV_SETUP_CHECKLIST.md`](/Users/sellers/RegEngine/docs/ENV_SETUP_CHECKLIST.md)

At a high level:

```bash
git clone https://github.com/PetrefiedThunder/RegEngine.git
cd RegEngine
bash scripts/setup_dev.sh
```

The repo includes:

- `docker-compose.yml`
- `docker-compose.fsma.yml`
- `scripts/start-fsma.sh`
- `scripts/stop-fsma.sh`

Frontend startup:

```bash
cd frontend
npm install
npm run dev
```

## Common Verification Commands

From repo root:

```bash
python -m pytest tests -q
python -m pytest services/<service>/tests -q
bash scripts/test-all.sh --quick
```

From `frontend/`:

```bash
npm install
npm run lint
npm run test:run
npm run build
```

## Deployment Posture

- Frontend is configured for Vercel deployment
- Backend services are documented around Railway deployment

The current backend deployment reference is:

- [`docs/FSMA_RAILWAY_DEPLOYMENT.md`](/Users/sellers/RegEngine/docs/FSMA_RAILWAY_DEPLOYMENT.md)

## API References

- [`partner_api_spec.yaml`](/Users/sellers/RegEngine/partner_api_spec.yaml)
- [`regengine-partner-gateway-openapi.yaml`](/Users/sellers/RegEngine/regengine-partner-gateway-openapi.yaml)

## Current Caveats

- The repo has been heavily refocused toward FSMA-first execution, but some internal, owner/admin, and legacy surfaces still exist.
- Security/dependency posture is actively being tightened; see `.github/workflows/security.yml` and service-level requirements files.
- Local verification can vary by service because some tests require Docker, external services, or environment variables.
