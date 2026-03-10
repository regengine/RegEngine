# RegEngine

**API-first FSMA 204 compliance infrastructure for recall-ready traceability.**

RegEngine converts supply-chain traceability events into structured, exportable, and independently verifiable compliance records — so when the FDA calls, you produce records within 24 hours.

## Current Focus

- **Primary wedge:** Food and Beverage (FSMA 204 / 21 CFR Part 1 Subpart S)
- **Core outcome:** Generate FDA-sortable traceability records inside the 24-hour response window
- **Product posture:** FSMA-first execution before broader vertical expansion

---

## Recently Shipped (March 2026)

### Full Frontend → Backend Wiring
All dashboard pages now call real backend APIs — zero mock data remaining in the production UI.

**8 pages wired to live endpoints:**
- Supplier Dashboard → `GET /v1/supplier/facilities`, compliance scores, TLC lists, FDA export
- Trace Page → `GET /v1/supplier/export/fda-records/preview` with TLC code filtering
- Compliance Dashboard → `GET /api/v1/compliance/score/{tenant_id}` (real-time scoring with breakdown)
- Alerts → `GET /api/v1/alerts/{tenant_id}` + `POST .../acknowledge`
- Audit Log → `GET /api/v1/audit-log/{tenant_id}` with pagination
- Team Management → `GET /api/v1/team/{tenant_id}` + invite + role management
- Product Catalog → `GET /api/v1/products/{tenant_id}` + create
- Notification Preferences → `GET/PUT /api/v1/notifications/{tenant_id}/preferences`

Every page includes auth gating, loading states, error handling, and refresh controls.

### Security Hardening (Round 2)
- Removed hardcoded `regengine-universal-test-key-2026` from `api-client.ts` and `auth-context.tsx`
- API key now sourced exclusively from `NEXT_PUBLIC_API_KEY` env var
- CORS on ingestion service validated (falls back to allowlist if wildcard detected)

### Codebase Cleanup
- Removed entire investor demo flow (29 files, ~11k lines): DemoProgress, DemoIngestion, BlueprintFlow, InvestorDemoPanel, TourProvider, demo routes, demo scripts, demo seed data
- Cleaned up provider tree (removed DemoProgressProvider + TourProvider wrappers)

### Postgres-Backed CTE Persistence Layer
- `fsma` schema with 5 tables: `cte_events`, `cte_kdes`, `hash_chain`, `compliance_alerts`, `fda_export_log`
- Full RLS via `get_tenant_context()`, 13 indexes tuned for FDA query patterns
- `CTEPersistence` class: atomic writes, `verify_chain()` full walk, `query_events_by_tlc()`, `get_unsynced_events()`
- Webhook V2 router with DB-backed storage, idempotency deduplication, Redis publish for Neo4j sync
- CSV upload path wired through V2 — pilot data persists across restarts

### End-to-End Test Suite
11 integration tests (testcontainers + real Postgres) proving the full chain:

```
ingest → hash chain → verify chain → query by TLC → FDA export → verify export hash
```

```bash
pytest services/ingestion/tests/test_cte_persistence_e2e.py -v -m integration
```

---

## Architecture

### Production Topology

- **Frontend:** Vercel (`regengine.co`)
- **Backend services:** Railway (admin-api, ingestion-service, scheduler)
- **Data stores:** Railway Postgres, Neo4j, Redis

### Service Map

| Service | Port | Role |
|---------|------|------|
| `admin-api` | 8400 | Auth, tenants, supplier onboarding, snapshots, compliance alerts |
| `ingestion-service` | 8002 | FSMA 204 event ingest, CSV import, FDA export, alerts, team, billing, notifications |
| `scheduler` | 8600 | Regulatory scraping (FDA recalls, warning letters) |
| `nlp-service` | 8100 | Document parsing and regulatory extraction |
| `compliance-api` | 8500 | Compliance scoring and policy APIs |
| `graph-service` | 8200 | Graph operations and FSMA trace endpoints |

### Backend Endpoints (200+)

**Admin Service** — 74 endpoints covering auth, tenants, supplier onboarding, facility management, compliance scoring, TLC management, FDA export, and snapshots.

**Ingestion Service** — 130+ endpoints across 22 route modules:

| Prefix | Module | Purpose |
|--------|--------|---------|
| `/api/v1/alerts` | alerts.py | Alert rules, triggers, acknowledgement |
| `/api/v1/audit-log` | audit_log.py | Immutable SHA-256 verified event log |
| `/api/v1/billing` | stripe_billing.py | Plans, checkout, subscriptions |
| `/api/v1/compliance` | compliance_score.py | Real-time scoring with breakdown |
| `/api/v1/epcis` | epcis_ingestion.py | GS1 EPCIS 2.0 JSON-LD ingestion |
| `/api/v1/exchange` | exchange_api.py | B2B shipping KDE package send/receive |
| `/api/v1/export` | epcis_export.py | EPCIS export (Walmart, Kroger formats) |
| `/api/v1/fda` | fda_export_router.py | FDA traceability package (ZIP) + CSV export |
| `/api/v1/ingest/edi` | edi_ingestion.py | Partner-authenticated EDI 856 inbound ingest |
| `/api/v1/ingest/iot` | sensitech_parser.py | IoT sensor data (SensiTech) |
| `/api/v1/notifications` | notification_prefs.py | Channels, quiet hours, escalation |
| `/api/v1/onboarding` | onboarding.py | Guided setup steps |
| `/api/v1/products` | product_catalog.py | FTL product catalog management |
| `/api/v1/recall` | recall_report.py | Recall readiness reports |
| `/api/v1/simulations` | recall_simulations.py | Mock recall drills and export artifacts |
| `/api/v1/sop` | sop_generator.py | AI-generated SOPs |
| `/api/v1/suppliers` | supplier_mgmt.py | Supplier management |
| `/api/v1/team` | team_mgmt.py | Team members, invites, roles |
| `/api/v1/webhooks` | webhook_router_v2.py | CTE event ingestion (V2, DB-backed) |

### Kernel Modules

| Module | Role |
|--------|------|
| `kernel/obligation/` | Obligation engine, evaluator, regulation loader |
| `kernel/monitoring/` | Compliance scoring, drift detection |
| `kernel/evidence/` | Tamper-evident hash chain primitives |
| `kernel/graph.py` | LLM-powered regulatory mapping (Groq) |

### Data Flow

```
CSV / webhook / EPCIS / IoT
        ↓
  webhook_router_v2
        ↓
  CTEPersistence (Postgres fsma.*)
        ↓
  hash_chain (append-only ledger)
        ↓
  Redis → Neo4j graph sync
        ↓
  fda_export_router → CSV download
```

---

## Frontend

Next.js 18+ app with 30+ routes. Key pages:

| Section | Routes |
|---------|--------|
| **Dashboard** | `/dashboard` (overview), `/dashboard/compliance`, `/dashboard/alerts`, `/dashboard/audit-log`, `/dashboard/team`, `/dashboard/products`, `/dashboard/notifications`, `/dashboard/suppliers` |
| **Tools** | `/ingest` (document ingestion), `/trace` (supply chain trace), `/ftl-checker`, `/tools/*` (drill simulator, data import) |
| **Compliance** | `/compliance` (status), `/review` (HITL curator), `/opportunities` (gap analysis), `/controls` |
| **Supplier Portal** | `/portal`, `/onboarding` (8-step supplier flow) |
| **Admin** | `/admin`, `/api-keys`, `/settings`, `/integrations` |

### Tech Stack
- **Framework:** Next.js 18+, React, TypeScript
- **UI:** Radix UI, Tailwind CSS, Framer Motion
- **State:** React Query, custom auth/tenant context providers
- **Auth:** Supabase Auth + API key dual-auth pattern
- **API clients:** Axios (admin service), fetch (ingestion service)

---

## Getting Started

### Prerequisites

- Docker + Docker Compose
- Node.js 18+ / npm
- Python 3.11+

### First-time setup

```bash
git clone https://github.com/PetrefiedThunder/RegEngine.git
cd RegEngine
./scripts/setup_dev.sh   # creates venv, installs deps, copies .env.example → .env
```

Edit `.env` and set the required secrets (see `.env.example` for generation instructions):

```
POSTGRES_PASSWORD=          # required
SCHEDULER_API_KEY=          # required
REGENGINE_INTERNAL_SECRET=  # required for service-to-service calls
NEO4J_PASSWORD=             # required
ADMIN_MASTER_KEY=           # required
NEXT_PUBLIC_API_KEY=        # required for frontend API calls
```

### Start services (FSMA mode)

```bash
./scripts/start-fsma.sh
```

This starts the pilot-focused stack: `postgres`, `redis`, `admin-api`, and `ingestion-service`.
For the full stack, run `docker compose up -d`.

### Start frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:3000`.

---

## FDA Export Endpoints

```bash
# Ingest a traceability event
POST /api/v1/webhooks/ingest
Content-Type: application/json
X-RegEngine-API-Key: <your-api-key>

# Generate FDA verifiable package for a lot code (default format)
GET /api/v1/fda/export?tlc=TOM-2026-001&tenant_id=<uuid>

# Generate FDA CSV explicitly (legacy-compatible)
GET /api/v1/fda/export?tlc=TOM-2026-001&tenant_id=<uuid>&format=csv

# Verify hash chain integrity
GET /api/v1/webhooks/chain/verify?tenant_id=<uuid>

# Verify a previous export hasn't changed
POST /api/v1/fda/export/verify?export_id=<id>&tenant_id=<uuid>
```

Full API reference: `partner_api_spec.yaml`

### Ingestion RBAC Scopes (Phase 3 Minimal Rollout)

Scoped API keys can now enforce permissions on Phase 2 traceability endpoints:

- `exchange.write` / `exchange.read` -> `/api/v1/exchange/send`, `/api/v1/exchange/receive`
- `edi.ingest` -> `POST /api/v1/ingest/edi`
- `simulations.read` / `simulations.write` / `simulations.export` -> `/api/v1/simulations/*`
- `fda.export` / `fda.read` / `fda.verify` -> `/api/v1/fda/export*`

Legacy master `API_KEY` remains supported and maps to full access.

---

## Testing

```bash
# Unit and integration tests (no Docker required)
python -m pytest tests -q

# CTE persistence E2E (requires Docker)
python -m pytest services/ingestion/tests/test_cte_persistence_e2e.py -v -m integration

# Full quick sweep
bash scripts/test-all.sh --quick
```

```bash
# Frontend (from frontend/)
npm run lint
npm run test:run
npm run build
```

---

## Supplier Onboarding Flow

Route: `/onboarding/supplier-flow`

1. Buyer invite
2. Supplier signup
3. Facility registration
4. FTL category scoping
5. CTE/KDE capture
6. TLC management
7. Supplier compliance dashboard
8. FDA export

---

## Reference Docs

| Doc | Path |
|-----|------|
| FSMA 204 MVP spec | `docs/specs/FSMA_204_MVP_SPEC.md` |
| FSMA deployment runbook | `docs/FSMA_RAILWAY_DEPLOYMENT.md` |
| Env setup checklist | `docs/ENV_SETUP_CHECKLIST.md` |
| Product roadmap | `docs/PRODUCT_ROADMAP.md` |
| Content ingestion guide | `docs/CONTENT_INGESTION.md` |
| Partner API spec | `partner_api_spec.yaml` |
| Architecture diagrams | `docs/architecture/` |

---

All dashboard pages wired to live APIs. Zero mock data in production UI. Pilot-ready.
