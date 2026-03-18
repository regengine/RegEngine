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
- 18 free compliance tools (no login required)

## Pricing

Founding Design Partners lock in 50% off for their entire first year.

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
│   │   ├── tools/         Free compliance tools
│   │   └── api/admin/     Proxy to Railway admin API
│   └── src/components/    UI components
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

**Frontend:** Next.js 15, React 18, TypeScript, Tailwind CSS, Radix UI, Framer Motion, TanStack Query, Supabase Auth

**Backend:** FastAPI (Python 3.11), PostgreSQL, Neo4j (graph), Kafka (Redpanda), Redis, Supabase

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

### Site & UX
- Auth-aware header/footer: logged-in users see Dashboard nav + avatar, visitors see marketing nav
- Countdown timer fix: consistent 855 days (was randomizing on each load)
- Pricing updated to Base/Standard/Premium facility-based tiers
- Checklist label visibility fix (hardcoded dark bg with theme variable colors)
- Retailer Readiness page: risk calculator, compliance checklist, integrations grid

### Dashboard
- All pages render for authenticated users (fixed Supabase + custom auth race condition)
- System Health shows "Healthy" (ConnectErrors reported as "unavailable" not "unhealthy")
- Hash Chain shows "Valid" (falls back to supplier Merkle chain when ingestion unreachable)
- Products page populates from supplier TLC data
- Audit Log supplements with bulk upload facility events
- Suppliers page loads in ~1s with progressive enrichment (was 30s+)

### Infrastructure
- Docker dependency cycle fixed (admin-api ↔ compliance-api)
- Missing env vars added (AUTH_SECRET_KEY, REGENGINE_INTERNAL_SECRET, SCHEDULER_API_KEY)
- Vercel admin proxy maxDuration=300s (Pro plan)
- Railway Railpack builder now installs openpyxl for XLSX uploads
- Frontend .env.local with Supabase keys for production builds

### Backend
- Bulk upload auto-cleans short/empty fields instead of hard-failing
- Batch processing (500 rows/batch) prevents timeout on large commits
- Graph sync capped at 100 events per commit response
- System metrics query supplier tables (admin DB) as fallback
- EPCIS test TLC format updated to GTIN-14 pattern

## Key Specs

- [FSMA 204 MVP Spec](docs/specs/FSMA_204_MVP_SPEC.md)
- [Railway Deployment Guide](docs/FSMA_RAILWAY_DEPLOYMENT.md)

---

*Food traceability compliance for farms and food companies. Don't trust, verify.*
