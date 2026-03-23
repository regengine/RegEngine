# RegEngine

**FSMA 204 food traceability compliance for farms and food companies.**

RegEngine helps food suppliers meet FDA Food Safety Modernization Act Section 204 requirements — from CTE ingestion to FDA-ready export — without six-figure enterprise contracts or months of onboarding.

**Live at [regengine.co](https://regengine.co)** | **API Docs at [regengine.co/developer/portal](https://regengine.co/developer/portal)**

---

## What RegEngine Does

- Ingest Critical Tracking Events (CTEs) via API, CSV, XLSX, EDI, EPCIS 2.0, QR/barcode scan, or IoT adapters
- Bulk upload 10K+ rows with auto-cleaning, SHA-256 hashing, and Merkle tree chaining
- Validate 102+ Key Data Elements (KDEs) against 21 CFR Part 1, Subpart S
- Score compliance readiness across your entire supply chain
- Generate FDA-compliant sortable spreadsheets within the 24-hour response window
- Trace lots forward and backward through a Neo4j knowledge graph
- Run recall simulations and audit drill workflows with tamper-evident logging
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
│   ├── ingestion/               Ingest pipelines, EPCIS, webhook, FDA export, audit log
│   ├── compliance/              FSMA 204 validation, compliance scoring, wizard
│   ├── graph/                   Neo4j traceability graph, recall, lineage, audit trail
│   ├── nlp/                     Document extraction and NLP processing
│   ├── scheduler/               Scheduled jobs, FDA feed polling, recalls
│   └── shared/                  Auth, middleware, database, resilient HTTP, audit logging
├── kernel/reporting/            Reporting service
├── scripts/
│   ├── security/                Tenant isolation, audit chain, SAST, ZAP, gitleaks
│   └── test/                    Test database initialization
├── infra/monitoring/            Prometheus, Grafana dashboards, alert rules
├── migrations/                  Database migrations (Flyway-style)
├── gateway/                     Nginx API gateway config
├── docker-compose.yml           Local dev stack (17 services)
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
| **Frontend** | Next.js 15, React 18, TypeScript, Tailwind CSS, Radix UI, Framer Motion, TanStack Query, jose (JWT), Supabase Auth |
| **Backend** | FastAPI (Python 3.11), PostgreSQL 16, Neo4j 5 (graph), Kafka (Redpanda), Redis 7, Stripe, defusedxml, SQLAlchemy |
| **Infrastructure** | Vercel Pro (frontend), Railway Pro (backend services), Supabase (auth + database) |
| **Observability** | Prometheus, Grafana, OpenTelemetry, Jaeger, structlog |
| **CI/CD** | GitHub Actions (8 workflows), Dependabot, CodeQL, Semgrep, gitleaks, Trivy |
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

## Dashboard

| Section | Pages |
|---------|-------|
| **Overview** | Heartbeat, Compliance Score, Alerts |
| **Compliance** | Recall Report, Recall Drills, Export Jobs |
| **Data** | Data Import (bulk CSV/XLSX), Field Capture, Receiving Dock, Scan, Integrations, Suppliers, Products, Audit Log |
| **Settings** | Notifications, Team, Settings |

### Free Compliance Tools (20)

FTL Coverage Checker, KDE Checker, CTE Mapper, Retailer Readiness Assessment, ROI Calculator, Recall Readiness, Label Scanner, Drill Simulator, Anomaly Simulator, Notice Validator, Obligation Scanner, Knowledge Graph Explorer, FDA Export Preview, SOP Generator, TLC Validator, FSMA Unified Dashboard, Data Import, Ask (AI assistant), and QR/Barcode Scan.

---

## Security

### Authentication

- **Dual-strategy middleware**: checks RegEngine JWT (`re_access_token` cookie) first, falls back to Supabase session
- **HTTP-only cookies**: credentials stored server-side, never exposed to JavaScript
- **Server-side API key injection**: proxy routes inject keys from env vars, never from client
- **Path sanitization**: all proxy routes validate catch-all path segments against traversal, null bytes, and injection
- **Row-Level Security (RLS)**: PostgreSQL enforces tenant isolation at the database layer
- **Sysadmin verification**: database-level check of `is_sysadmin` flag for privileged operations

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

### Prerequisites

- Docker and Docker Compose
- Node.js 18+ and npm
- Python 3.11+ (for running backend tests locally)

### Setup

```bash
git clone https://github.com/PetrefiedThunder/RegEngine.git
cd RegEngine

# Fix macOS extended attributes (if "Operation not permitted" errors)
xattr -cr .

# Configure environment
cp .env.example .env    # Fill in required values (see below)

# Start all services
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

### Running Tests

```bash
# Backend services (from repo root)
PYTHONPATH=$(pwd):$PYTHONPATH pytest services/admin/tests/ -v
PYTHONPATH=$(pwd):$PYTHONPATH pytest services/ingestion/tests/ -v
PYTHONPATH=$(pwd):$PYTHONPATH pytest services/compliance/tests/ -v

# Frontend
cd frontend
npm run build            # Full production build (130 pages)
npm run lint             # ESLint

# Integration test stack
docker compose -f docker-compose.test.yml up -d
pytest services/<service>/tests/ -v

# Stress test (4,600 requests across all 6 services)
python3 scripts/stress_test.py
```

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
| `deploy.yml` | Push to main | Deployment automation |
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
