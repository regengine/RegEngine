# RegEngine Product Overview (FSMA-First)

Last updated: April 30, 2026
Audience: Engineering, product, solutions, and implementation teams

## 1) What RegEngine Is

RegEngine is an API-first traceability platform focused on FDA FSMA 204 compliance.

Core value:

- Preflight messy supplier data before it becomes compliance evidence.
- Convert traceability events into durable, exportable records.
- Keep records tamper-evident and tenant-scoped.
- Produce FDA-ready exports and verification evidence inside the 24-hour response window.

## 2) Who It Is For

Primary users and buyers:

- Food safety leaders
- Compliance operations teams
- Supplier onboarding teams
- Technical teams integrating ingestion/export APIs

The current product wedge in this repository is food and beverage traceability under FSMA 204.

## 3) What Is Implemented Today

### 3.1 Ingestion and Persistence

- Webhook ingestion endpoint: `POST /api/v1/webhooks/ingest`
  - Router: `services/ingestion/app/webhook_router_v2.py`
- CSV ingestion path is wired through the same persistence path.
- Persistence module: `services/shared/cte_persistence.py`
  - Stores CTE events, KDEs, chain links, and alerts.
  - Supports idempotency handling and integrity verification.

### 3.2 FDA Export and Verification

Router: `services/ingestion/app/fda_export/router.py`

Implemented export surfaces include:

- `GET /api/v1/fda/export`
- `GET /api/v1/fda/export/all`
- `GET /api/v1/fda/export/history`
- `POST /api/v1/fda/export/verify`

### 3.3 Graph Traceability Surfaces

FSMA graph routes live under:

- `services/graph/app/routers/fsma/`

These support lot-level lineage, recall-oriented traversal, and FSMA metrics/compliance query workflows.

### 3.4 Onboarding and Frontend Flows

Active frontend flows include:

- Inflow Lab workbench: `frontend/src/app/tools/inflow-lab/`
- Supplier onboarding flow: `frontend/src/app/onboarding/supplier-flow/`
- Free tooling and readiness pages: `frontend/src/app/tools/`
- Public positioning pages (FTL checker, retailer readiness, pricing, developers)

### 3.5 Inflow Workbench Operational Loop

The current design-partner wedge is the Inflow Workbench:

- Preflight Mode validates incoming supplier data before evidence persistence.
- Commit Gate blocks invalid or low-readiness data from `production_evidence`.
- Fix Queue turns validation failures into remediation tasks.
- Scenario Library saves replayable runs for demos, onboarding, and regression checks.
- Readiness Score is visible in Inflow Lab and surfaced in compliance and supplier dashboards.

Workbench state is backed by Postgres tables with tenant scoping and RLS. File-backed storage remains available for local/demo fallback only.

## 4) Core Architecture (Current)

### 4.1 Runtime Topology

- Frontend: Next.js 15 App Router (`frontend/`)
- Backend: FastAPI services (`services/`)
- Stores: PostgreSQL, Neo4j, Redis
- Typical deployment references in repo docs: Vercel + Railway

Primary service entrypoints:

- `services/admin/main.py`
- `services/ingestion/main.py`
- `services/graph/app/main.py`
- `services/nlp/main.py`
- `services/scheduler/main.py`

### 4.2 Shared Bootstrap Pattern

Cross-service path bootstrap is centralized in:

- `services/shared/paths.py`

Service entrypoints should use `ensure_shared_importable()` to keep local, test, and container imports consistent.

## 5) Security, Contracts, and Isolation

- API key contract header: `X-RegEngine-API-Key`
- Shared auth dependency: `services/shared/auth.py` (`require_api_key`)
- Tenant and request middleware lives under `services/shared/middleware/`
- Traceability persistence is designed for tamper-evident chain validation and audit reproducibility

## 6) Important Scope Note

RegEngine contains legacy and experimental surfaces across multiple directories. The active narrative and near-term execution in checked-in docs is FSMA-first.

If a proposal is not tied to FSMA traceability, onboarding, export, or compliance reliability, it should be treated as out of scope unless explicitly approved.

## 7) Known Product and Doc Alignment Gaps

- Some legacy docs still describe non-FSMA or speculative narratives and should not be treated as source-of-truth.
- Source-of-truth docs for current direction:
  - `README.md`
  - `AGENTS.md`
  - `docs/AI_ENGINEERING_STANDARDS.md`
  - `docs/ARCHITECTURE.md`
  - `docs/PRODUCT_ROADMAP.md`
  - `docs/specs/FSMA_204_MVP_SPEC.md`

## 8) Near-Term Priorities (Operational)

- Improve lead capture from free tool completion flows.
- Harden the Inflow Workbench Postgres path in staging before live supplier data is committed as evidence.
- Keep architecture and roadmap docs synchronized with implemented code.
- Add response examples to developer-facing integration docs.
- Improve conversion bridge between free usage and paid onboarding.

## 9) Glossary

- FSMA 204: FDA traceability rule requiring rapid retrieval of traceability records.
- CTE: Critical Tracking Event.
- KDE: Key Data Element.
- TLC: Traceability Lot Code.
- FTL: Food Traceability List.
