# RegEngine

**Regulatory compliance infrastructure for food safety teams.**

RegEngine automates obligation tracking, traceability, and audit-readiness for companies navigating FDA, FSMA 204, and food safety regulations — so compliance teams spend less time in spreadsheets and more time running operations.

---

## What It Does

RegEngine gives food safety and compliance teams a single system to manage regulatory obligations end-to-end:

- **Obligation Tracking** — 78+ FDA/FSMA obligations mapped, with automated status monitoring and deadline alerts
- **Supply Chain Traceability** — Forward and backward lot tracing across your supply chain, built on recursive CTEs for sub-second query performance
- **FTL Coverage Analysis** — Instant check of your products against the FDA Food Traceability List (26 categories), with CTE and KDE breakdowns
- **Compliance Assessments** — Guided self-assessments with evidence collection and submission workflows
- **Audit Trail** — Immutable, hash-chained records with tenant isolation for multi-org deployments
- **Developer API** — REST API with key-based auth, rate limiting, and a built-in developer portal with interactive playground
- **NLP Extraction** — Automated extraction of regulatory requirements from uploaded documents
- **Knowledge Graph** — Relationship mapping between regulations, obligations, products, and facilities

## Architecture

RegEngine runs as a **consolidated FastAPI monolith** backed by **PostgreSQL** (via Supabase) and a **Next.js** frontend deployed on **Vercel**.

```
┌──────────────────────────────────────────────┐
│  Next.js Frontend (Vercel)                   │
│  Dashboards · Onboarding · API Console       │
├──────────────────────────────────────────────┤
│  FastAPI Backend Services                    │
│  ┌──────────┬──────────┬──────────────────┐  │
│  │ Admin    │ Graph    │ Compliance       │  │
│  │ Ingest   │ NLP      │ Scheduler        │  │
│  └──────────┴──────────┴──────────────────┘  │
│  Background Workers (pg_notify task queue)    │
├──────────────────────────────────────────────┤
│  PostgreSQL (Supabase)                       │
│  RLS · Row-level tenant isolation            │
│  Recursive CTE lot tracing                   │
│  Hash-chained audit log                      │
└──────────────────────────────────────────────┘
```

**Key design decisions:**

- **PostgreSQL replaces Kafka** — Async task processing via `task_queue` table with `pg_notify` triggers. Simpler to operate, zero external dependencies.
- **Recursive CTEs replace Neo4j** — Forward/backward supply chain tracing runs entirely in PostgreSQL. One fewer database to manage.
- **Row-Level Security everywhere** — Every tenant-scoped table enforces RLS policies. Multi-tenancy is enforced at the database layer, not just application code.
- **Fail-closed auth** — Rate limiting fails closed when Redis is unavailable. API key validation uses constant-time comparison. Brute-force protection on all auth endpoints.
- **Tenant settings as JSONB** — Onboarding state, workspace profiles, and feature flags stored in `tenants.settings` column. No migrations needed for new configuration.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS, shadcn/ui, React Query, Framer Motion |
| Backend | FastAPI (Python), Pydantic v2, SQLAlchemy 2.0 |
| Database | PostgreSQL via Supabase (RLS, pg_notify, recursive CTEs) |
| Auth | HTTP-only cookie JWT + Supabase Auth fallback, API key store with rate limiting |
| Hosting | Vercel (frontend), Supabase (database + edge functions) |
| CI/CD | GitHub Actions — 54 checks across lint, test, security, bundle analysis, review gates |
| Code Review | CodeRabbit AI, Copilot, Vercel bot |

## Project Structure

```
├── frontend/              # Next.js frontend
│   └── src/
│       ├── app/           # App router (dashboard, onboarding, tools, API console)
│       ├── components/    # UI components (shadcn/ui based)
│       ├── hooks/         # React Query hooks
│       └── lib/           # API client, auth context, utilities
├── services/
│   ├── admin/             # Tenant management, auth, onboarding, user admin
│   ├── compliance/        # Obligation tracking, assessments
│   ├── graph/             # Supply chain traceability, lot tracing
│   ├── ingestion/         # Document upload, NLP extraction, format parsers
│   ├── nlp/               # Regulatory text analysis
│   ├── scheduler/         # Background jobs, deadline monitoring, FDA scrapers
│   └── shared/            # Cross-service auth and utilities
├── kernel/                # Core compliance engine and discovery
├── regengine/             # Python SDK package
├── migrations/            # Database migrations
├── scripts/               # Operational and dev utility scripts
├── docs/                  # Internal documentation
├── qa/                    # QA pipeline and test fixtures
├── security/              # Security policies and audit configs
└── .github/
    └── workflows/         # CI/CD pipelines + review gates (54 checks)
```

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
- **Audit immutability** — CI review gates enforce that migrations cannot DROP audit columns or bypass hash chain integrity.
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

Migrations are managed via Supabase CLI:

```bash
supabase db push
```

## Status

RegEngine is in **active development** — shipping weekly. Current focus areas:

- Onboarding experience and first-run value delivery
- FSMA 204 obligation coverage expansion
- Developer API documentation and playground
- Waitlist and early access program

## License

Proprietary. All rights reserved.

---

Built by [Christopher Sellers](https://regengine.co) under tight constraints with a bias toward shipping.
