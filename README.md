# RegEngine

**API-first FSMA 204 compliance infrastructure for recall-ready traceability.**

RegEngine converts supply-chain traceability events into structured, exportable, and independently verifiable compliance records — so when the FDA calls, you produce records within 24 hours.

## Current Focus

- **Primary wedge:** Food and Beverage (FSMA 204)
- **Core outcome:** Generate FDA-sortable traceability records inside the 24-hour response window
- **Product posture:** FSMA-first execution before broader vertical expansion

---

## Recently Shipped (March 2026)

### Postgres-Backed CTE Persistence Layer
The core compliance promise is now backed by durable, tamper-evident storage.

- `migrations/V002__fsma_cte_persistence.sql` — `fsma` schema with 5 tables: `cte_events`, `cte_kdes`, `hash_chain`, `compliance_alerts`, `fda_export_log`. Full RLS via `get_tenant_context()`, 13 indexes tuned for FDA query patterns
- `services/shared/cte_persistence.py` — `CTEPersistence` class: atomic event writes (event + KDEs + hash chain + alerts in one transaction), `verify_chain()` full walk from genesis, `query_events_by_tlc()` for FDA export, `get_unsynced_events()` for Neo4j sync
- `services/ingestion/app/webhook_router_v2.py` — drop-in V1 replacement with DB-backed storage, graceful in-memory fallback with loud warning if DB unavailable, idempotency key deduplication, Redis publish for Neo4j graph sync
- `services/ingestion/app/fda_export_router.py` — 4 endpoints: `GET /api/v1/fda/export` (TLC → CSV), `GET /api/v1/fda/export/all`, `GET /api/v1/fda/export/history`, `POST /api/v1/fda/export/verify`
- CSV upload path (`/api/v1/ingest/csv`) wired through V2 — pilot data persists across restarts

### End-to-End Test Suite
11 integration tests using a real Postgres container (testcontainers) proving the full chain:

```
ingest → hash chain → verify chain → query by TLC → FDA export → verify export hash
```

Covers: sequential chain linkage math, tamper detection, multi-tenant isolation, idempotency, export reproducibility, and the master harvest→cooling→shipping→receiving E2E path.

```bash
pytest services/ingestion/tests/test_cte_persistence_e2e.py -v -m integration
```

### Security Hardening
- Removed two hardcoded credential strings from production code paths in `shared/middleware/tenant_context.py` and `shared/auth.py` (universal API key + internal service secret, both committed to source with no env var gate)
- All auth bypass paths now require explicit env vars; fail closed if unset
- `REGENGINE_INTERNAL_SECRET`, `REGENGINE_API_KEY` / `REGENGINE_API_KEY_TENANT_ID` documented in `.env.example`

### Bug Fixes
- `kernel/obligation/engine.py` — graph persistence was accessing non-existent attributes on `ObligationEvaluationResult`; rewrote to iterate `obligation_matches` correctly (was crashing silently on every evaluation)
- `kernel/monitoring/scoring.py` — broken import from non-existent `.models` module fixed
- `kernel/graph.py` — hardcoded `model="grok-beta"` (not a valid Groq model) replaced with `GROQ_MODEL` env var, default `llama3-70b-8192`
- `kernel/obligation/models.py` + `kernel/models.py` — Pydantic v2 `min_items` → `min_length` (silent validation bypass fixed)
- `kernel/discovery.py` — HTML source type was set to `"url"`, selecting the wrong loader
- `kernel/obligation/regulation_loader.py` — hardcoded Neo4j host/user replaced with env vars
- `docker-compose.yml` — `SCHEDULER_API_KEY` and `POSTGRES_PASSWORD` now use `:?` mandatory substitution (no silent defaults)
- `services/admin/app/auth_routes.py` — refresh token flow now validates tenant `status='active'`; suspended tenants no longer issue tokens
- Scheduler: `MemoryJobStore` replaces `SQLAlchemyJobStore` (no separate DB dependency); lambda serialization crashes fixed; discovery requests now send API key header
- Shared OTel: `None`-valued K8s resource attributes no longer crash `Resource.create()`; `ENABLE_OTEL=false` gate added for local dev

---

## Architecture

### Production Topology

- **Frontend + edge:** Vercel (`regengine.co`)
- **App/API service:** Railway (admin/auth API, ingestion service)
- **Stateful services:** Railway Postgres, Neo4j, Redis

### Service Map

| Service | Port | Role |
|---------|------|------|
| `admin` | 8000 | Auth, tenants, compliance alerts, snapshots |
| `ingestion` | 8002 | FSMA 204 event ingest, CSV import, FDA export |
| `scheduler` | 8600 | Regulatory scraping (FDA recalls, warning letters) |
| `nlp` | 8100 | Document parsing and regulatory extraction |
| `compliance` | 8500 | Compliance scoring worker |
| `billing` | 8800 | Stripe billing integration |

### Kernel Modules

| Module | Role |
|--------|------|
| `kernel/obligation/` | Obligation engine, evaluator, regulation loader |
| `kernel/monitoring/` | Compliance scoring, drift detection |
| `kernel/evidence/` | Tamper-evident hash chain primitives |
| `kernel/graph.py` | LLM-powered regulatory mapping (Groq) |

### Data Flow

```
CSV / webhook / EPCIS
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

## Getting Started

### Prerequisites

- Docker + Docker Compose
- Node.js 18+ / pnpm
- Python 3.11+

### First-time setup

```bash
# Clone and set up environment
git clone https://github.com/PetrefiedThunder/RegEngine.git
cd RegEngine
./scripts/setup_dev.sh   # creates venv, installs deps, copies .env.example → .env
```

Edit `.env` and set the required secrets (see `.env.example` for generation instructions):

```
POSTGRES_PASSWORD=      # required
SCHEDULER_API_KEY=      # required
REGENGINE_INTERNAL_SECRET=  # required for service-to-service calls
NEO4J_PASSWORD=         # required
ADMIN_MASTER_KEY=       # required
```

### Start services

```bash
docker-compose up -d
```

### Start frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Frontend runs at `http://localhost:3000`.

---

## FDA Export Endpoints

Once the stack is running:

```bash
# Ingest a traceability event
POST /api/v1/webhooks/ingest
Content-Type: application/json
X-API-Key: <your-api-key>

# Generate FDA export for a lot code
GET /api/v1/fda/export?tlc=TOM-2026-001&tenant_id=<uuid>

# Verify hash chain integrity
GET /api/v1/webhooks/chain/verify?tenant_id=<uuid>

# Verify a previous export hasn't changed
POST /api/v1/fda/export/verify?export_id=<id>&tenant_id=<uuid>
```

Full API reference: `partner_api_spec.yaml`

---

## Testing

```bash
# Unit and integration tests (no Docker required)
pytest tests/ services/admin/tests/ services/ingestion/tests/ -v

# CTE persistence E2E (requires Docker)
pytest services/ingestion/tests/test_cte_persistence_e2e.py -v -m integration

# Frontend
cd frontend && pnpm vitest
cd frontend && pnpm build
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
| Upgrade plan (16-item) | `docs/UPGRADE_PLAN.md` |
| FSMA deployment runbook | `docs/FSMA_RAILWAY_DEPLOYMENT.md` |
| Env setup checklist | `docs/ENV_SETUP_CHECKLIST.md` |
| FSMA 204 MVP spec | `docs/specs/FSMA_204_MVP_SPEC.md` |
| Partner API spec | `partner_api_spec.yaml` |

---

Status: Postgres-backed CTE persistence live, 11-test E2E suite green, auth hardened, pilot-ready.
