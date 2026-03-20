# RegEngine

**FSMA 204 food traceability compliance for farms and food companies.**

RegEngine helps food suppliers meet FDA Food Safety Modernization Act Section 204 requirements — from CTE ingestion to FDA-ready export — without six-figure enterprise contracts or months of onboarding.

**Live at [regengine.co](https://regengine.co)**

## What RegEngine Does

- Ingest Critical Tracking Events (CTEs) via API, CSV, XLSX, EDI, EPCIS, or IoT adapters
- Bulk upload 10K+ rows with auto-cleaning, SHA-256 hashing, and Merkle tree chaining
- Validate Key Data Elements (KDEs) against 21 CFR Part 1, Subpart S
- Score compliance readiness across your supply chain
- Generate FDA-compliant sortable spreadsheets within the 24-hour response window
- Trace lots forward and backward through a graph database
- Run recall simulations and drill workflows
- Free compliance tools (no login required)

## Pricing

Founding Design Partners lock in 50% off for the life of their account.

| Plan | Partner Price | GA Price | Facilities |
|---|---|---|---|
| **Base** | $425/mo | $849/mo | 1 |
| **Standard** | $549/mo | $1,099/mo | 2–3 |
| **Premium** | $639/mo | $1,275/mo | 4+ |

Annual billing saves ~15%. All plans include FSMA 204 traceability workspace and FDA-ready export.

## FSMA 204 Compliance Date

**July 20, 2028** — extended from the original January 2026 deadline per FDA enforcement discretion and Congressional action. Major retailer internal deadlines are estimated ~Q1 2027.

## Repo Structure

Monorepo with two primary surfaces:

```text
.
├── frontend/              Next.js 15 App Router (Vercel)
│   ├── src/app/           Pages and API routes
│   │   ├── dashboard/     Authenticated dashboard (16 pages)
│   │   ├── pricing/       Pricing + Stripe checkout flow
│   │   ├── tools/         Free compliance tools
│   │   └── api/           Server-side proxies (admin, billing, session)
│   ├── src/components/    UI components
│   └── src/middleware.ts   Dual auth gate (RegEngine JWT + Supabase)
├── services/
│   ├── admin/             Auth, tenants, bulk upload, supplier onboarding
│   ├── ingestion/         Ingest pipelines, EPCIS, webhook, FDA export
│   ├── compliance/        Validation, compliance scoring
│   ├── graph/             Neo4j traceability graph, recall, lineage
│   ├── nlp/               Extraction and document processing
│   ├── scheduler/         Scheduled jobs and feed polling
│   └── shared/            Bootstrap, middleware, schemas, auth
├── scripts/               Dev, CI, and stress test scripts
├── migrations/            Database migrations (Flyway-style)
└── docker-compose.yml     Local dev stack (17 services)
```

## Tech Stack

**Frontend:** Next.js 15, React 18, TypeScript, Tailwind CSS, Radix UI, Framer Motion, TanStack Query, jose (JWT), Supabase Auth

**Backend:** FastAPI (Python 3.11), PostgreSQL, Neo4j (graph), Kafka (Redpanda), Redis, Stripe, defusedxml, Supabase

**Infrastructure:** Vercel Pro (frontend), Railway Pro (backend services), Supabase (auth + database)

## Quick Start

```bash
git clone https://github.com/PetrefiedThunder/RegEngine.git
cd RegEngine

# Fix macOS extended attributes (if "Operation not permitted" errors)
xattr -cr .

# Start all 17 services locally
cp .env.example .env  # Fill in required values
docker compose up -d

# Frontend
cd frontend
cp .env.local.example .env.local  # Add Supabase keys
npm install
npm run dev
```

### Required Environment Variables

```bash
# .env (backend)
POSTGRES_PASSWORD=         # Required
ADMIN_MASTER_KEY=          # Required (openssl rand -hex 32)
SCHEDULER_API_KEY=         # Required
AUTH_SECRET_KEY=           # Required
REGENGINE_INTERNAL_SECRET= # Required

# frontend/.env.local
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

See [`docs/LOCAL_SETUP_GUIDE.md`](docs/LOCAL_SETUP_GUIDE.md) for full setup.

## Running Tests

```bash
# Scheduler (local — no Docker needed)
cd services/scheduler && python -m pytest tests/ -q

# Ingestion (inside Docker)
docker compose exec ingestion-service python3 -m pytest tests/ -q

# Frontend build verification
cd frontend && npm run build

# Stress test (4,600 requests across all 6 services)
python3 scripts/stress_test.py
```

## Dashboard Pages

| Section | Pages |
|---|---|
| **Overview** | Heartbeat, Compliance, Alerts |
| **Compliance** | Recall Report, Recall Drills, Export Jobs |
| **Data** | Data Import (bulk CSV/XLSX), Field Capture, Receiving Dock, Integrations, Suppliers, Products, Audit Log |
| **Settings** | Notifications, Team, Settings |

## Bulk Upload Pipeline

CSV/XLSX → Parse → Auto-clean messy fields → Validate against FSMA 204 rules → Batch commit (500 rows/batch) → SHA-256 hash + Merkle tree chain → Dashboard display

- Handles 10K+ rows per upload
- Auto-fills empty/short facility names, invalid CTE types
- Surfaces warnings (not errors) for cleaned fields
- Graph sync capped at 100 events per commit (rest deferred to background worker)

## Recent Changes (March 2026)

### Auth & Billing (PR #175)
- Dual-strategy middleware: checks RegEngine JWT (`re_access_token` cookie) first, falls back to Supabase session
- Stripe checkout proxy at `/api/billing/checkout` — API key stays server-side
- Pricing page CTAs wired to checkout flow with graceful signup fallback
- `access_token` stored in HTTP-only cookie via `/api/session` for middleware verification
- Signup page shows plan context + payment confirmation banners post-checkout

### Security (PRs #173, #174)
- XXE vulnerability fixed: replaced `xml.etree.ElementTree` with `defusedxml` across all XML parsers
- `lxml` parsers hardened with `resolve_entities=False, no_network=True`
- `defusedxml>=0.7.1` added to ingestion and scheduler service `requirements.txt` (fixed Railway crash)

### Ingestion Hardening (PR #171 — 13 findings)
- RBAC auth on webhook endpoint via `require_permission("webhooks.ingest")`
- Chunked file uploads with size limits (10MB general, 5MB CSV/EDI) prevent OOM
- Shared modules extracted: `tenant_resolution.py`, `upload_limits.py`, `routes_health_metrics.py`
- `DISABLED_ROUTERS` env var for feature-flagging non-core routers
- All `datetime.utcnow()` replaced with `datetime.now(timezone.utc)`

### Comprehensive Audit (PR #172 — 18 findings, 5 sprints)
- **Persistence:** 5 dashboard modules rewritten to DB-first pattern (suppliers, team, settings, notifications, onboarding)
- **Accuracy:** Recall report, mock audit, and simulations query real tenant CTE data
- **Security:** 5 dead security modules archived; internal routes hidden from OpenAPI spec
- **Architecture:** 6 disabled page suites moved to `_disabled/`; entertainment artifacts archived
- **Docs:** Migration README, production env checklist (28 required + 12 security vars), security scan results

### Site & UX
- Auth-aware header/footer: logged-in users see Dashboard nav + avatar, visitors see marketing nav
- Pricing updated to Base/Standard/Premium facility-based tiers
- Retailer Readiness page: risk calculator, compliance checklist, integrations grid

### Dashboard
- All pages render for authenticated users (fixed Supabase + custom auth race condition)
- Suppliers page loads in ~1s with progressive enrichment (was 30s+)
- Products page populates from supplier TLC data

### Infrastructure
- Docker dependency cycle fixed (admin-api ↔ compliance-api)
- Vercel admin proxy maxDuration=300s (Pro plan)
- Railway Railpack builder now installs openpyxl for XLSX uploads

### Backend
- Bulk upload auto-cleans short/empty fields instead of hard-failing
- Batch processing (500 rows/batch) prevents timeout on large commits
- Graph sync capped at 100 events per commit response

## Key Specs

- [FSMA 204 MVP Spec](docs/specs/FSMA_204_MVP_SPEC.md)
- [Railway Deployment Guide](docs/FSMA_RAILWAY_DEPLOYMENT.md)

---

*Food traceability compliance for farms and food companies. Don't trust, verify.*
