# RegEngine

**FSMA 204 compliance infrastructure for food safety teams.**

RegEngine automates traceability, obligation tracking, and audit-readiness for companies navigating FDA FSMA 204 — so compliance teams can meet the 24-hour FDA records deadline without spreadsheets, paper logs, or panic.

---

## What It Does

RegEngine gives food safety and compliance teams a single system to manage FSMA 204 traceability end-to-end:

### Traceability

- **All 7 FSMA 204 CTE Types** — Harvesting, Cooling, Initial Packing, First Land-Based Receiving, Shipping, Receiving, and Transformation — with full KDE capture per FDA requirements
- **Supply Chain Tracing** — Forward and backward lot tracing across your supply chain, built on recursive CTEs for sub-second query performance
- **Multi-Source Ingestion** — Ingest traceability data via webhook API, CSV upload, XLSX upload, EPCIS 2.0, EDI, manual entry, mobile capture, or supplier portal
- **Cryptographic Audit Trail** — Every record is SHA-256 hashed and chain-verified. Dual payload preservation (raw + normalized) ensures tamper detection and full provenance tracking

### Compliance

- **78+ FDA/FSMA Obligations** — Mapped with automated status monitoring and deadline alerts
- **6-Dimensional Compliance Scoring** — Real-time scoring across Chain Integrity, KDE Completeness, CTE Completeness, Obligation Coverage, Product Coverage, and Export Readiness
- **FTL Coverage Analysis** — Instant check of your products against the FDA Food Traceability List (17 categories), with CTE and KDE breakdowns
- **Blocking Enforcement** — The compliance control plane blocks defective submissions, not just tracks them. Strict mode converts warnings to errors.

### Operations

- **24-Hour Recall Response Dashboard** — Operational SLA tracking with live countdown timer, 5-phase gate stepper (Request Received → Records Assembly → Verification → Review → FDA Submission), alerts, and one-click FDA export
- **Traceability Plan Builder** — Guided 5-step wizard generates your complete FSMA 204 traceability plan (receiving, shipping, transformation, TLC assignment, recall response, and training procedures) in minutes
- **FDA Export** — Generate FDA-compliant sortable spreadsheets in CSV, PDF, or ZIP package format with chain verification and completeness summaries
- **Drill Simulator** — Practice mock recall drills with timed scenarios and validation scoring

### Platform

- **Developer API** — REST API with key-based auth, rate limiting, and a built-in developer portal with interactive playground
- **Compliance Assessments** — Guided self-assessments with evidence collection and readiness scoring
- **NLP Extraction** — Automated extraction of regulatory requirements from uploaded documents
- **Knowledge Graph** — Relationship mapping between regulations, obligations, products, and facilities

## Architecture

RegEngine runs as a **consolidated FastAPI monolith** backed by **PostgreSQL** (via Supabase) and a **Next.js** frontend deployed on **Vercel**.

```
┌──────────────────────────────────────────────────┐
│  Next.js 15 Frontend (Vercel)                    │
│  Dashboard · Recall Response · Plan Builder      │
│  Onboarding · Tools · API Console                │
├──────────────────────────────────────────────────┤
│  FastAPI Backend Services (Railway)              │
│  ┌──────────┬──────────┬──────────────────────┐  │
│  │ Admin    │ Graph    │ Compliance           │  │
│  │ Ingest   │ NLP      │ Scheduler            │  │
│  │ SLA      │ Export   │ Rules Engine         │  │
│  └──────────┴──────────┴──────────────────────┘  │
│  Background Workers (pg_notify task queue)        │
├──────────────────────────────────────────────────┤
│  PostgreSQL 17 (Supabase)                        │
│  RLS · Row-level tenant isolation                │
│  Recursive CTE lot tracing                       │
│  Hash-chained audit log                          │
│  52+ versioned migrations                        │
└──────────────────────────────────────────────────┘
```

**Key design decisions:**

- **PostgreSQL replaces Kafka** — Async task processing via `task_queue` table with `pg_notify` triggers. Simpler to operate, zero external dependencies.
- **Recursive CTEs replace Neo4j** — Forward/backward supply chain tracing runs entirely in PostgreSQL. One fewer database to manage.
- **Row-Level Security everywhere** — Every tenant-scoped table enforces RLS policies. Multi-tenancy is enforced at the database layer, not just application code.
- **Fail-closed auth** — Rate limiting fails closed when Redis is unavailable. API key validation uses constant-time comparison. Brute-force protection on all auth endpoints.
- **Tenant settings as JSONB** — Onboarding state, workspace profiles, and feature flags stored in `tenants.settings` column. No migrations needed for new configuration.
- **Blocking compliance** — The control plane enforces compliance, it doesn't just report. Defective submissions are blocked before they enter the system.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, React 18, TypeScript, Tailwind CSS, shadcn/ui, React Query, Framer Motion |
| Backend | FastAPI (Python 3.11+), Pydantic v2, SQLAlchemy 2.0 |
| Database | PostgreSQL 17 via Supabase (RLS, pg_notify, recursive CTEs) |
| Auth | HTTP-only cookie JWT + Supabase Auth, API key store with rate limiting |
| Export | CSV, PDF (fpdf2), ZIP packages with chain verification |
| Hosting | Vercel Pro (frontend), Railway Pro (backend services), Supabase (database) |
| CI/CD | GitHub Actions — 54 checks across lint, test, security, bundle analysis, review gates |
| Code Review | CodeRabbit AI, Copilot, Vercel bot |
| Observability | Sentry, PostHog, OpenTelemetry |

## Project Structure

```
├── frontend/              # Next.js 15 frontend
│   └── src/
│       ├── app/           # App router
│       │   ├── dashboard/ # Compliance, recall response, alerts, suppliers, products
│       │   ├── compliance/# Checklists, traceability plan builder
│       │   ├── tools/     # Drill simulator, recall readiness, data import, FTL checker
│       │   └── onboarding/# Supplier flow, bulk upload
│       ├── components/    # UI components (shadcn/ui based)
│       │   └── fsma/      # Recall timer, phase gates, compliance readiness
│       ├── hooks/         # React Query hooks (use-api-query, use-sla)
│       └── lib/           # API client, auth context, utilities
├── services/
│   ├── admin/             # Tenant management, auth, onboarding, user admin
│   ├── compliance/        # Obligation tracking, validation rules (fsma_rules.json)
│   ├── graph/             # Supply chain traceability, plan builder, lot tracing
│   ├── ingestion/         # Webhook ingest, CSV/XLSX import, FDA export, SLA tracking
│   ├── nlp/               # Regulatory text analysis, document extraction
│   ├── scheduler/         # Background jobs, deadline monitoring, FDA scrapers
│   └── shared/            # Cross-service auth, canonical event model, base config
├── kernel/                # Core compliance engine and discovery
├── migrations/            # Database migrations (V001–V053, raw SQL)
├── scripts/               # Operational and dev utility scripts
├── qa/                    # QA pipeline and test fixtures
├── security/              # Security policies and audit configs
└── .github/
    └── workflows/         # CI/CD pipelines + review gates (54 checks)
```

## Core Data Model

The canonical traceability event is the single source of truth for all FSMA 204 operations:

- **Event identity** — UUID, tenant-scoped, with CTE type classification
- **Lot tracking** — Traceability Lot Code (TLC), product reference, quantity, UOM
- **Entity references** — From/to entity and facility references with GLN support
- **Key Data Elements** — Structured dict supporting all named KDEs (harvest_date, cooling_date, pack_date, ship_date, receive_date, transformation_date, landing_date, temperature, carrier, growing_area_name, etc.)
- **Dual payload** — Raw payload preserved alongside normalized canonical form
- **Provenance** — Source system, mapper version, normalization rules, extraction confidence
- **Integrity** — SHA-256 content hash, chain hash, idempotency key for deduplication
- **Amendment chain** — Corrections link to originals via supersedes_event_id

## FSMA 204 CTE Coverage

| CTE Type | Status | Key KDEs |
|----------|--------|----------|
| Growing | Supported | Growing area, location, grower name, coordinates |
| Harvesting | Supported | Harvest date, field ID, harvester name |
| Cooling | Supported | Cooling date, temperature, facility |
| Initial Packing | Supported | Pack date, input lot codes, harvester business |
| First Land-Based Receiving | Supported | Landing date, vessel/source, BOL reference |
| Shipping | Supported | Ship date, from/to locations, carrier, PO number |
| Receiving | Supported | Receive date, prior source, TLC source reference |
| Transformation | Supported | Transformation date, input/output lot linkage |

## Onboarding Flow

New users go through a streamlined 3-step workspace setup:

1. **Profile** — Role, company type, and compliance maturity
2. **Facility** — Register your first facility with supply chain role
3. **FTL Quick Check** — Select products handled to see FDA traceability coverage instantly

After setup, the dashboard shows a **Getting Started checklist** that tracks progress through first document import, team invites, and mock audit drills. State is persisted server-side in tenant settings.

## Security

RegEngine is built for regulated industries. Security is not an afterthought:

- **Tenant isolation** — RLS on all tenant-scoped tables. Invalid tenant UUIDs are rejected, never silently routed to a global fallback.
- **SQL injection defense** — Parameterized queries with whitelist assertions on dynamic clauses. CI gates scan for f-string SQL patterns.
- **Auth hardening** — Constant-time secret comparison (hmac.compare_digest), fail-closed rate limiting, per-IP brute-force protection on login/register.
- **Audit immutability** — CI review gates enforce that migrations cannot DROP audit columns or bypass hash chain integrity. Every record is SHA-256 hashed and chain-linked.
- **Supabase query patterns** — CI enforces proper error destructuring on all Supabase client calls.

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.11+
- Supabase project (or local Supabase CLI)

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Backend

```bash
cd services/admin
pip install -r requirements.txt
uvicorn main:app --reload --port 8400
```

For local development without PostgreSQL, the admin service falls back to SQLite automatically. Set `ADMIN_MASTER_KEY` to any value for local dev.

### Database

Migrations are versioned SQL files in `migrations/`. Apply with Supabase CLI:

```bash
supabase db push
```

### Docker (Full Stack)

```bash
docker compose -f docker-compose.dev.yml up
```

## Status

RegEngine is in **active development** — shipping weekly. The product is pre-revenue, deployed to production, and recruiting design partners.

**Current state:**
- Frontend deployed on Vercel (build green)
- 3 backend services on Railway (admin, ingestion, compliance — all healthy)
- 52+ database migrations applied
- 7/7 FSMA 204 CTE types implemented
- 78+ regulatory obligations tracked
- FDA export in CSV, PDF, and ZIP package formats
- 24-hour recall response dashboard operational
- Traceability plan builder live (no longer "Coming Soon")

**FSMA 204 compliance deadline: July 20, 2028**

## License

Proprietary. All rights reserved.

---

Built by [Christopher Sellers](https://regengine.co) under tight constraints with a bias toward shipping.
