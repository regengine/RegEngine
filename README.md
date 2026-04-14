# RegEngine

Supply chain traceability infrastructure for food companies. Respond to FDA recall requests in minutes, satisfy Walmart and Kroger supplier requirements, and build the visibility your brand depends on.

## What is RegEngine?

RegEngine is an FSMA 204 compliance platform built for mid-market food companies. It validates traceability data against all 25 FSMA 204 rules, covers all 7 Critical Tracking Event (CTE) types with per-event Key Data Element (KDE) validation, and produces cryptographically verified audit trails ready for FDA submission.

**Key capabilities:**
- CSV and API-based data ingestion with real-time validation
- EPCIS 2.0 native data model
- SHA-256 hashed regulatory exports
- Retailer-specific compliance (Walmart ASN, Kroger EDI 856)
- 24-hour FDA records request readiness

## Architecture

```
frontend/          Next.js 16 (Vercel)
services/
  admin/           Auth, tenants, API keys, billing (FastAPI)
  ingestion/       Data intake, normalization, validation (FastAPI)
  compliance/      Rule engine, audit trails, exports (FastAPI)
  graph/           Supply chain graph queries (FastAPI)
  nlp/             Document parsing, entity extraction (FastAPI + spaCy)
  scheduler/       Cron jobs, background tasks (FastAPI + APScheduler)
  shared/          Shared models, utilities, middleware
kernel/            Core business logic (Python)
migrations/        Alembic database migrations
infra/             Terraform modules (VPC, EKS, Kafka, Neo4j)
scripts/           Dev tooling, seed data, utilities
tests/             Integration and e2e tests
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 16, React 18, TypeScript, Tailwind CSS, Radix UI |
| Backend | FastAPI, SQLAlchemy, Pydantic, Python 3.11+ |
| Database | PostgreSQL (primary), Neo4j (graph, being migrated to PG) |
| Cache | Redis |
| Messaging | Kafka / Redpanda |
| Object Storage | MinIO (dev), S3-compatible (prod) |
| Auth | Supabase Auth + JWT |
| Observability | OpenTelemetry, Prometheus, Sentry |
| Analytics | PostHog |

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker and Docker Compose
- Poetry (Python dependency management)

### Setup

```bash
# Clone and configure environment
cp .env.example .env
# Fill in all REPLACE_ME values — see .env.example for guidance

# Validate environment
python scripts/validate_env.py

# Start infrastructure (Postgres, Neo4j, Redis, Kafka, MinIO)
docker compose up -d

# Install backend dependencies
poetry install

# Run database migrations
alembic upgrade head

# Seed demo data
python scripts/seed_demo_data.py

# Install frontend dependencies and start dev server
cd frontend
npm install
npm run dev
```

### Running Tests

```bash
# Backend
pytest

# Frontend
cd frontend
npm run test          # Unit tests
npm run test:e2e      # Playwright e2e tests
```

## Deployment

| Component | Platform |
|-----------|----------|
| Frontend | Vercel (SFO region) |
| Backend services | Railway (Docker containers) |
| CI/CD | GitHub Actions |

Backend services are containerized via Docker and deployed to Railway. The frontend deploys to Vercel automatically on push to `main`.

## FSMA 204 Compliance Deadline

The FDA enforcement deadline is **July 20, 2028** (extended from the original January 2026 date). Major retailers have already begun enforcement — Kroger required EDI 856 compliance by June 2025 and Walmart required ASN compliance by August 2025.

## License

Proprietary. Copyright (c) 2024-2026 RegEngine Inc. All rights reserved. See [LICENSE](LICENSE) for details.
