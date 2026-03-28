# RegEngine

**FSMA 204 food traceability compliance for farms and food companies.**

RegEngine helps food suppliers meet FDA Food Safety Modernization Act Section 204 requirements — from CTE ingestion to FDA-ready export — without six-figure enterprise contracts or months of onboarding.

**Live at [regengine.co](https://regengine.co)** | **API Docs at [regengine.co/developer/portal](https://regengine.co/developer/portal)**

---

## What RegEngine Does

**Core loop (proven end-to-end):**
- Ingest CTEs via API, CSV, XLSX, QR/barcode scan, or supplier portal
- **Normalize all records into one canonical truth model** with dual payload preservation (raw + normalized)
- **Evaluate records against 25 versioned compliance rules** with 21 CFR citations and human-readable failure explanations
- **Block bad submissions** — critical failures, unresolved exceptions, unevaluated events, missing signoffs, and identity ambiguity all prevent package assembly
- **Run 24-hour response workflows** from request intake to SHA-256 sealed, immutable package submission
- **Amend packages** with full history — prior packages preserved, diffs tracked
- **Manage exceptions through a remediation queue** with ownership, deadlines, waivers, and signoff chains
- **Resolve entity identity** across facilities, products, and firms with alias matching and confidence scoring

**Additional capabilities (functional, less proven):**
- Bulk upload 10K+ rows with auto-cleaning, SHA-256 hashing, and Merkle tree chaining
- EDI, EPCIS 2.0, and IoT adapter ingestion paths
- Forward/backward lot tracing via Neo4j knowledge graph
- Recall simulations and audit drill workflows with tamper-evident logging
- Incident command layer with action tracking and timeline
- 5-level compliance readiness maturity assessment
- Developer portal with API keys, interactive playground, SDKs, and webhook delivery tracking
- 20 free compliance tools (no login required)

## FSMA 204 Compliance Date

**July 20, 2028** — extended from the original January 2026 deadline per FDA enforcement discretion and Congressional action. Major retailer internal deadlines are estimated ~Q1 2027.

## Pricing

Founding Design Partners lock in 50% off for the life of their account.

| Plan | Partner Price | GA Price | Facilities |
|------|--------------|----------|------------|
| **Base** | $425/mo | $849/mo | 1 |
| **Standard** | $549/mo | $1,099/mo | 2–3 |
| **Premium** | $639/mo | $1,275/mo | 4+ |

Annual billing saves ~15%. All plans include FSMA 204 traceability workspace, FDA-ready export, and tamper-evident audit trail.

---

## Architecture

### Repository Structure

```text
.
├── frontend/                    Next.js 15 App Router (Vercel)
│   ├── src/app/
│   │   ├── dashboard/           Authenticated dashboard (20 pages)
│   │   ├── developer/portal/    Developer portal (API keys, docs, playground)
│   │   ├── onboarding/          Supplier onboarding wizard + bulk upload
│   │   ├── pricing/             Pricing + Stripe checkout flow
│   │   ├── tools/               20 free compliance tools
│   │   └── api/                 Server-side proxies (admin, billing, compliance,
│   │                            fsma, ingestion, review, session, health)
│   ├── src/components/          UI component library
│   ├── src/lib/                 Auth, API client, Supabase, design tokens
│   └── src/middleware.ts        Dual auth gate (RegEngine JWT + Supabase)
├── services/
│   ├── admin/                   Auth, tenants, bulk upload, audit logs, billing
│   ├── ingestion/               Ingest pipelines, EPCIS, webhook, FDA export, control plane routers
│   ├── compliance/              FSMA 204 validation, compliance scoring, wizard
│   ├── graph/                   Neo4j traceability graph, recall, lineage, audit trail
│   ├── nlp/                     Document extraction and NLP processing
│   ├── scheduler/               Scheduled jobs, FDA feed polling, recalls
│   └── shared/                  Auth, middleware, database, canonical model, rules engine,
│                                exception queue, request workflow, identity resolution
├── kernel/reporting/            Reporting service
├── scripts/
│   ├── security/                Tenant isolation, audit chain, SAST, ZAP, gitleaks
│   └── test/                    Test database initialization
├── infra/monitoring/            Prometheus, Grafana dashboards, alert rules
├── migrations/                  Database migrations (Flyway-style)
├── gateway/                     Nginx API gateway config
├── docker-compose.yml           Local dev stack (17 services)
├── docker-compose.mvp.yml       MVP demo stack (4 services)
├── docker-compose.prod.yml      Production deployment
├── docker-compose.test.yml      CI integration test stack
├── docker-compose.monitoring.yml Prometheus + Grafana monitoring
├── docker-compose.fsma.yml      FSMA-specific overrides
└── .github/
    ├── workflows/               8 CI/CD workflows
    ├── ISSUE_TEMPLATE/          Bug report, feature request, agent task
    ├── dependabot.yml           Automated dependency updates
    ├── CODEOWNERS               Auto-reviewer assignment
    ├── labeler.yml              Auto-labeling by file path
    └── pull_request_template.md Standardized PR template
```

### Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Frontend** | Next.js 15, React 18, TypeScript, Tailwind CSS, Radix UI, Framer Motion, TanStack Query, jose (JWT), Supabase Auth, Capacitor (mobile) |
| **Backend** | FastAPI (Python 3.11), PostgreSQL 16, Neo4j 5 (graph), Kafka (Redpanda), Redis 7, Stripe, defusedxml, SQLAlchemy |
| **Infrastructure** | Vercel Pro (frontend), Railway Pro (backend services), Supabase (auth + database) |
| **Observability** | Prometheus, Grafana, OpenTelemetry, Jaeger, structlog |
| **CI/CD** | GitHub Actions (10 workflows), Dependabot, CodeQL, Semgrep, gitleaks, Trivy |
| **Security** | OWASP ZAP (DAST), pip-audit, npm audit, tenant isolation tests, audit chain verification |

### Service Architecture

```text
┌─────────────┐     ┌──────────────────────────────────────────────────────┐
│   Browser    │────▶│  Vercel (Next.js)                                   │
│   Client     │     │  /api/admin, /api/ingestion, /api/compliance,       │
└─────────────┘     │  /api/fsma, /api/review, /api/billing, /api/health  │
                    └──────┬────────┬────────┬────────┬───────────────────┘
                           │        │        │        │
                    ┌──────▼──┐ ┌───▼────┐ ┌─▼──────┐ │
                    │  Admin  │ │Ingest  │ │Comply  │ │
                    │  :8400  │ │ :8002  │ │ :8500  │ │
                    └────┬────┘ └───┬────┘ └───┬────┘ │
                         │         │           │      │
                    ┌────▼─────────▼───────────▼──┐   │
                    │       PostgreSQL 16          │   │
                    │  (RLS, audit_logs, CTE data) │   │
                    └─────────────────────────────┘   │
                                                      │
                    ┌─────────┐  ┌─────────┐  ┌──────▼──┐
                    │  Neo4j  │  │  Redis   │  │  Graph  │
                    │ (trace) │  │ (cache)  │  │  :8200  │
                    └─────────┘  └─────────┘  └─────────┘

                    ┌─────────┐  ┌───────────┐  ┌───────────┐
                    │   NLP   │  │ Scheduler │  │  Redpanda │
                    │  :8100  │  │   :8600   │  │  (Kafka)  │
                    └─────────┘  └───────────┘  └───────────┘
```

---

## Compliance Control Plane

RegEngine operates as a **request-response control plane** for FSMA 204 compliance. The core loop:

```
capture → normalize → evaluate rules → triage exceptions →
assemble response package → submit → preserve audit trail
```

**The core pipeline is proven end-to-end.** The E2E integration test (`test_e2e_fda_request.py`) runs 12 steps against a real PostgreSQL database — from messy ingestion through sealed, hashed package submission and amendment. This proves the happy path and the blocked-submission path. Scenarios not yet proven: identity ambiguity blocking, multi-tenant isolation under concurrent requests, deadline breach escalation, and graph-backed recall traversal.

### Operational Pages

| Page | Route | Purpose |
|------|-------|---------|
| **Exception Queue** | `/exceptions` | Manage compliance defects — assign, resolve, waive with approval chain |
| **Request Workflow** | `/requests` | 24-hour FDA response: intake → scope → collect → gap analysis → assemble → submit |
| **Request Detail** | `/requests/[id]` | 10-stage pipeline view with countdown timer, package history, signoff chain |
| **Canonical Records** | `/records` | Every record with provenance: what is it, where from, what rules, what failed, what next |
| **Rules Dashboard** | `/rules` | 25 versioned FSMA rules with 21 CFR citations and remediation guidance |
| **Identity Resolution** | `/identity` | Canonical entities, alias management, ambiguous match review queue |
| **Readiness Assessment** | `/readiness` | 5-level maturity wizard (Not Started → Ingesting → Validating → Operational → Audit-Ready → Compliant) |
| **Incident Command** | `/incidents` | Real-time recall coordination — actions, timeline, impact assessment |
| **Auditor Review** | `/audit` | Read-only compliance posture for FDA reviewers and auditors |

### Control Plane API

| Prefix | Endpoints | Purpose |
|--------|-----------|---------|
| `/api/v1/records` | 5 | Canonical events with provenance, amendment chain, ingestion runs |
| `/api/v1/rules` | 6 | Rule catalog, evaluate single/batch events, evaluation history, seed |
| `/api/v1/exceptions` | 9 | CRUD, assign, resolve, waive, comments, blocking count |
| `/api/v1/requests` | 11 | 10-stage request lifecycle, package assembly, submission, amendment |
| `/api/v1/identity` | 10 | Entity CRUD, aliases, fuzzy match, merge/split, review queue |
| `/api/v1/audit` | 8 | Read-only compliance summary, events, rules, exceptions, chain verification |
| `/api/v1/readiness` | 3 | Maturity assessment, checklist, gap analysis |
| `/api/v1/incidents` | 9 | Incident lifecycle, action items, timeline, impact assessment |
| `/api/v1/metrics/compliance` | 1 | PRD Section 10 KPIs (normalization rate, pass rate, median resolve time) |
| `/api/v1/fda/export/v2` | 1 | FDA export from canonical model with compliance status columns |

### Database Schema (fsma.*)

| Table Group | Tables | Purpose |
|-------------|--------|---------|
| **Canonical Model** | `traceability_events`, `evidence_attachments`, `ingestion_runs` | One truth model for all records |
| **Rules Engine** | `rule_definitions`, `rule_evaluations`, `rule_audit_log` | Versioned compliance rules as policy artifacts |
| **Exception Queue** | `exception_cases`, `exception_comments`, `exception_attachments`, `exception_signoffs` | Remediation workflow |
| **Request Workflow** | `request_cases`, `response_packages`, `submission_log`, `request_signoffs` | 24-hour response lifecycle |
| **Identity Resolution** | `canonical_entities`, `entity_aliases`, `entity_merge_history`, `identity_review_queue` | Cross-record entity identity |

All tables use Row-Level Security (RLS) for tenant isolation, GIN indexes for JSONB queries, and append-only audit patterns.

### Enforcement Layer

The control plane doesn't just track problems — it **prevents bad outcomes**.

| Check | What It Blocks | Where |
|-------|---------------|-------|
| **Critical rule failures** | Unresolved critical failures with no waiver block submission | `submit_package()` |
| **Unresolved exceptions** | Critical exception cases must be resolved or waived | `submit_package()` |
| **Unevaluated events** | Events with zero rule evaluations cannot be in a submitted package | `submit_package()` |
| **Missing signoffs** | Required signoffs (scope_approval, final_approval) must exist | `submit_package()` |
| **Identity ambiguity** | High-confidence unresolved matches (>=85%) block submission | `submit_package()` |
| **Deadline monitoring** | 5-minute cron classifies cases as overdue/critical/urgent/normal | `scheduler` |

API endpoints: `GET /api/v1/requests/{id}/blockers` (check all defects), `GET /api/v1/requests/deadlines` (urgency for all active cases).

### Canonical Pipeline

Regulated ingestion paths normalize through the canonical `TraceabilityEvent` model:

| Path | Source | Normalizes? |
|------|--------|------------|
| Webhook v2 (happy path) | REST API | Yes |
| Webhook v2 (fallback) | REST API | Yes |
| EPCIS ingestion | XML/JSON | Yes |
| Mobile field capture | QR/barcode | Yes (bridges to canonical) |
| Supplier CTE events | Portal/bulk upload | Yes (bridges to canonical) |
| Kafka consumer | NLP extraction | **Graph only — canonical pending** |

The Kafka/NLP path writes to the graph but does not yet normalize into the canonical store. All other paths hit rules evaluation and hash chain verification.

---

## Dashboard

The dashboard is organized around the operator loop, not feature categories.

**Primary workflow** — the path a compliance operator uses daily:
- **Heartbeat** → **Alerts** → **Issues & Blockers** → **Requests** → **Export Jobs**

**Control plane** — where rules, records, and identity live:
- Rules, Canonical Records, Exceptions, Identity Resolution, Review Queue

**Everything else** — data import, suppliers, products, integrations, team, settings, and 20 free compliance tools accessible without login.

---

## Security

### Authentication

- **Dual-strategy middleware**: checks RegEngine JWT (`re_access_token` cookie) first, falls back to Supabase session, then checks API credentials
- **30-day sessions**: JWT and cookies persist for 30 days — explicit logout is the session terminator (B2B SaaS, not a bank)
- **HTTP-only cookies**: credentials stored server-side, never exposed to JavaScript
- **Server-side API key injection**: proxy routes inject keys from env vars, never from client
- **Preshared + database key auth**: `require_api_key` accepts both configured master key and database-stored scoped keys
- **Path sanitization**: all proxy routes validate catch-all path segments against traversal, null bytes, and injection
- **Railway URL guard**: proxy routes detect and reject `*.railway.internal` URLs on Vercel with clear warnings
- **Row-Level Security (RLS)**: PostgreSQL enforces tenant isolation at the database layer
- **Auth-gated routes**: 25+ route prefixes require valid session (dashboard, control plane, compliance, admin, developer)

### Audit Trail

- Tamper-evident: every entry is SHA-256 chained with Merkle tree verification
- Immutable: PostgreSQL triggers prevent UPDATE and DELETE on `audit_logs`
- Compliant with 21 CFR Part 11 electronic records and SOX 7-year retention
- Cross-database: admin audit logs + CTE events + exports + compliance alerts
- ISO 27001 12.7.1 audit chain integrity verification in CI

### CI/CD Security Pipeline

| Workflow | Tool | Purpose |
|----------|------|---------|
| Secrets Scan | gitleaks | Detect committed credentials |
| SAST | Semgrep (OWASP Top 10) | Static application security testing |
| Dependency Audit | pip-audit + npm audit | Known vulnerability detection |
| Container Scan | Trivy | Docker image CVE scanning (6 services) |
| DAST | OWASP ZAP | Dynamic application security testing |
| Tenant Isolation | Custom test suite | Cross-tenant data leak prevention |
| Audit Chain | Custom verification | Tamper-evidence integrity check |
| security.txt | Expiry monitor | Ensure security contact is current |

### Vulnerability Disclosure

See [SECURITY.md](SECURITY.md) for our vulnerability disclosure policy. **Do not open public issues for security vulnerabilities.** Email security@regengine.com.

---

## Quick Start

### 5-Minute MVP Demo

The fastest way to see RegEngine work end-to-end. Requires only Docker.

```bash
git clone https://github.com/PetrefiedThunder/RegEngine.git
cd RegEngine

# Configure environment
cp .env.example .env
# Set these three values in .env:
#   ADMIN_MASTER_KEY=<any-string>
#   REGENGINE_API_KEY=<any-string>
#   POSTGRES_PASSWORD=regengine

# Start the minimal 4-service stack (Postgres, Redis, Admin, Ingestion)
docker compose -f docker-compose.mvp.yml up -d

# Run database migrations
alembic upgrade head

# Run the demo (CSV upload → normalize → hash → FDA export)
REGENGINE_API_KEY=<your-key> ./scripts/demo_mvp_flow.sh
```

The demo uploads 6 supply chain CSVs (harvest → cool → pack → ship → receive → transform), normalizes each into canonical CTE records with SHA-256 hashes and chain linkage, then generates an FDA-ready export CSV. Takes under 30 seconds.

### Full Development Setup

#### Prerequisites

- Docker and Docker Compose
- Node.js 20+ and npm
- Python 3.11+ (for running backend tests locally)

#### Setup

```bash
# Fix macOS extended attributes (if "Operation not permitted" errors)
xattr -cr .

# Configure environment
cp .env.example .env    # Fill in required values (see below)

# Start minimal dev stack (postgres, redis, neo4j, minio)
docker compose -f docker-compose.dev.yml up -d

# Or start all 17 services
docker compose up -d

# Frontend
cd frontend
npm install
npm run dev              # http://localhost:3000
```

### Required Environment Variables

```bash
# .env (backend — all required, no defaults in production)
POSTGRES_PASSWORD=              # Strong password for PostgreSQL
ADMIN_MASTER_KEY=               # Generate: openssl rand -hex 32
SCHEDULER_API_KEY=              # Generate: openssl rand -hex 32
AUTH_SECRET_KEY=                # JWT signing key
REGENGINE_INTERNAL_SECRET=      # Service-to-service trust
REGENGINE_API_KEY=              # Server-side API key for proxy routes
NEO4J_PASSWORD=                 # Neo4j graph database password
OBJECT_STORAGE_ACCESS_KEY_ID=   # MinIO/S3 access key
OBJECT_STORAGE_SECRET_ACCESS_KEY= # MinIO/S3 secret key

# frontend/.env.local
NEXT_PUBLIC_SUPABASE_URL=       # Supabase project URL
NEXT_PUBLIC_SUPABASE_ANON_KEY=  # Supabase anonymous key

# Vercel environment variables
REGENGINE_API_KEY=              # Same as backend
ADMIN_MASTER_KEY=               # Same as backend
INGESTION_PRODUCTION_URL=       # Railway ingestion service URL

# Railway (ingestion service)
ADMIN_DATABASE_URL=             # Connection string for admin database

# Monitoring stack (optional)
GRAFANA_PASSWORD=               # Required when running docker-compose.monitoring.yml
```

See [.env.example](.env.example) for the full list with descriptions.

### Seed Demo Data

```bash
# Apply control plane migrations
alembic upgrade head

# Seed 20 realistic supply chain events (4 products, 5 facilities, all 7 CTE types)
PYTHONPATH=services python3 scripts/seed_demo_data.py

# Dry run (preview without persisting)
PYTHONPATH=services python3 scripts/seed_demo_data.py --dry-run
```

The seeder creates canonical events, evaluates rules, generates exception cases, and opens a demo FDA request case with a 24-hour deadline.

### Sample Data

6 CSV files in `sample_data/` simulate a real multi-supplier romaine lettuce supply chain covering all FSMA 204 CTEs with valid GS1 GLNs, reference documents, and required KDEs. Import via Dashboard → Data Import → CSV Upload in order (01–06), or run the MVP demo script to ingest all 6 programmatically. Exercises the full chain: ingest → canonical → rules → hash chain → FDA export.

### Running Tests

```bash
# ── E2E: Full FDA 24-hour response pipeline (12 steps, 0.25s) ──
# Requires: docker compose -f docker-compose.dev.yml up -d postgres
DATABASE_URL="postgresql://regengine:regengine@localhost:5432/regengine" \
  PYTHONPATH=services pytest tests/test_e2e_fda_request.py -v

# ── Domain logic unit tests (130 tests, no DB required) ──
PYTHONPATH=services pytest \
  tests/test_rules_engine_unit.py \
  tests/test_request_workflow_unit.py \
  tests/test_identity_service_unit.py -v

# ── Control plane router tests (96 tests, mocked DB) ──
PYTHONPATH=services pytest \
  services/ingestion/tests/test_canonical_router.py \
  services/ingestion/tests/test_rules_router.py \
  services/ingestion/tests/test_exception_router.py \
  services/ingestion/tests/test_request_workflow_router.py \
  services/ingestion/tests/test_identity_router.py -v

# ── Backend service tests ──
PYTHONPATH=$(pwd):$PYTHONPATH pytest services/admin/tests/ -v
PYTHONPATH=$(pwd):$PYTHONPATH pytest services/ingestion/tests/ -v
PYTHONPATH=$(pwd):$PYTHONPATH pytest services/compliance/tests/ -v

# ── Frontend tests (55 tests) ──
cd frontend
npx vitest run           # Hook, component, and page tests
npm run build            # Full production build (131 pages)

# ── Integration test stack ──
docker compose -f docker-compose.test.yml up -d
pytest services/<service>/tests/ -v

# ── Stress test (4,600 requests across all 6 services) ──
python3 scripts/stress_test.py
```

### What's Proven by Tests

| Invariant | Test |
|-----------|------|
| Bad data normalizes into canonical store | E2E step 1–3 |
| Rules evaluate and detect failures | E2E step 4, 42 unit tests |
| Blocking defects prevent package submission | E2E step 7, router tests |
| Signoffs are required before submission | E2E step 8, workflow unit tests |
| Packages are SHA-256 hashed and immutable | E2E step 9 |
| Amendments create new packages, preserve history | E2E step 11 |
| Identity ambiguity detection works | 45 identity unit tests |
| Tenant isolation on all control plane routes | Router auth tests |

293 tests total across E2E (12), domain logic (130), HTTP routers (96), and frontend (55).

### Monitoring

```bash
# Start Prometheus + Grafana stack
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d

# Grafana: http://localhost:3001 (set GRAFANA_PASSWORD in .env)
# Prometheus: http://localhost:9090
```

---

## Bulk Upload Pipeline

```text
CSV/XLSX → Parse → Auto-clean messy fields → Validate against FSMA 204 rules
→ Batch commit (500 rows/batch) → SHA-256 hash + Merkle tree chain → Dashboard
```

- Handles 10K+ rows per upload with 300s timeout
- Auto-fills empty/short facility names, invalid CTE types
- Surfaces warnings (not errors) for cleaned fields
- Graph sync capped at 100 events per commit (rest deferred to background worker)
- File validation: 10MB general limit, 5MB for CSV/EDI

---

## API Proxy Architecture

All frontend API calls route through Next.js server-side proxies that:

- Inject API keys from environment variables (never exposed to browser)
- Validate path segments against traversal and injection attacks
- Return standardized `{ error, code?, details? }` error responses
- Support static build mode with 503 graceful degradation
- Pass through auth headers (authorization, x-api-key, x-tenant-id)

| Proxy Route | Backend Service | Port |
|-------------|----------------|------|
| `/api/admin/[...path]` | Admin API | 8400 |
| `/api/ingestion/[...path]` | Ingestion Service | 8002 |
| `/api/compliance/[...path]` | Compliance API | 8500 |
| `/api/fsma/[...path]` | Graph Service / Compliance (dynamic routing) | 8200/8500 |
| `/api/review/[...path]` | Admin API (review endpoints) | 8400 |
| `/api/billing/checkout` | Stripe via Admin API | 8400 |
| `/api/health` | Aggregated health check | All |
| `/api/session` | HTTP-only cookie management | Local |

---

## Docker Services

Local development runs 17 services via `docker-compose.yml`:

| Service | Image/Build | Port | Purpose |
|---------|-------------|------|---------|
| gateway | nginx:alpine | 80 | API gateway |
| admin-api | services/admin | 8400 | Auth, tenants, bulk upload, audit |
| ingestion-service | services/ingestion | 8002 | Data ingestion, FDA export |
| compliance-api | services/compliance | 8500 | FSMA validation, scoring |
| graph-service | services/graph | 8200 | Neo4j traceability, recall |
| nlp-service | services/nlp | 8100 | Document extraction |
| scheduler | services/scheduler | 8600 | Scheduled jobs, feed polling |
| compliance-worker | services/compliance | — | Background compliance tasks |
| postgres | postgres:16 | 5432 | Primary database (RLS-enabled) |
| neo4j | neo4j:5.24-community | 7687 | Graph database |
| redis | redis:7-alpine | 6379 | Cache and rate limiting |
| redpanda | redpanda (Kafka) | 9092 | Event streaming |
| schema-registry | — | — | Kafka schema registry |
| minio | minio | 9000 | S3-compatible object storage |
| jaeger | jaeger | 16686 | Distributed tracing |
| otel-collector | OpenTelemetry | — | Telemetry collection |
| kafka-ui | — | 8080 | Kafka topic browser |

Additional compose files:

| File | Purpose |
|------|---------|
| `docker-compose.mvp.yml` | **MVP demo** — Postgres, Redis, Admin, Ingestion (4 services, no Kafka/Neo4j) |
| `docker-compose.dev.yml` | **Dev stack** — Postgres, Redis, Neo4j, MinIO (infrastructure only) |
| `docker-compose.prod.yml` | Production deployment with image pulls from ghcr.io |
| `docker-compose.test.yml` | CI integration tests (Postgres 16, Redis, Neo4j, LocalStack) |
| `docker-compose.monitoring.yml` | Prometheus, Grafana, Node/Redis/Postgres exporters |
| `docker-compose.fsma.yml` | FSMA-specific overrides (disables OTEL) |

---

## CI/CD Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `backend-ci.yml` | Push/PR on `services/**` | Test, lint, Docker build for all 6 backend services |
| `frontend-ci.yml` | Push/PR on `frontend/**` | Build, lint, type check |
| `security.yml` | Push/PR + weekly schedule | Secrets scan, SAST, dependency audit, Trivy, DAST, audit chain |
| `test-suite-check.yml` | Push/PR on `services/**` | Unified test environment health check |
| `qa-pipeline.yml` | Push/PR | QA environment validation |
| `pr-quality.yml` | Pull request | Automated code quality checks |
| `deploy.yml` | Push to main | Deployment automation (fails on missing secrets) |
| `proxy-smoke.yml` | Push/PR on `frontend/src/app/api/**` | Proxy route smoke test — verifies routes load |
| `bundle-analysis.yml` | Push/PR on `frontend/**` | JS bundle size check (fails if >2MB) |
| `agent-sweep.yml` | Manual/scheduled | AI agent orchestration and maintenance |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, code guidelines, and PR process.

## License

Proprietary. All rights reserved. See [LICENSE](LICENSE) for details.

## Security

See [SECURITY.md](SECURITY.md) for vulnerability disclosure policy.

---

*Food traceability compliance for farms and food companies. Don't trust — verify.*
