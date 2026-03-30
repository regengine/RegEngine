# RegEngine

**Regulatory compliance infrastructure for food safety teams.**

RegEngine automates obligation tracking, traceability, and audit-readiness for companies navigating FDA, FSMA 204, and food safety regulations — so compliance teams spend less time in spreadsheets and more time running operations.

---

## What It Does

RegEngine gives food safety and compliance teams a single system to manage regulatory obligations end-to-end:

- **Obligation Tracking** — 78+ FDA/FSMA obligations mapped, with automated status monitoring and deadline alerts
- **Supply Chain Traceability** — Forward and backward lot tracing across your supply chain, built on recursive CTEs for sub-second query performance
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
│  Dashboards · Assessments · API Console      │
├──────────────────────────────────────────────┤
│  FastAPI Monolith                            │
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

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Backend | FastAPI (Python), Pydantic v2 |
| Database | PostgreSQL via Supabase (RLS, pg_notify) |
| Auth | Supabase Auth + API key store with rate limiting |
| Hosting | Vercel (frontend), Supabase (database + edge functions) |
| CI/CD | GitHub Actions (backend CI, frontend CI, review gates, bundle analysis, test health checks) |
| Code Review | CodeRabbit AI, Codex, Vercel bot |

## Project Structure

```
├── server/              # FastAPI monolith entry point
├── services/
│   ├── admin/           # Tenant management, PCOS, user admin
│   ├── compliance/      # Obligation tracking, assessments
│   ├── graph/           # Supply chain traceability, lot tracing
│   ├── ingestion/       # Document upload, NLP extraction
│   ├── nlp/             # Regulatory text analysis
│   └── scheduler/       # Background jobs, deadline monitoring
├── src/                 # Next.js frontend
│   ├── app/             # App router pages
│   ├── components/      # UI components
│   └── lib/             # API client, utilities
├── supabase/
│   └── migrations/      # Versioned schema migrations (V001–V050)
└── .github/
    └── workflows/       # CI/CD pipelines + review gates
```

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
npm install
npm run dev
```

### Backend

```bash
cd services/<service>
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Database

Migrations are managed via Supabase CLI:

```bash
supabase db push
```

## Status

RegEngine is in **active development** — shipping weekly. Current focus areas:

- Stabilizing CI pipelines across all services
- Expanding FSMA 204 obligation coverage
- Developer API documentation and onboarding
- Waitlist and early access program

## License

Proprietary. All rights reserved.

---

Built by [Christopher Sellers](https://regengine.co) under tight constraints with a bias toward shipping.
