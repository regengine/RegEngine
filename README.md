# RegEngine – Regulatory Intelligence Platform

[![Backend CI](https://github.com/PetrefiedThunder/RegEngine/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/PetrefiedThunder/RegEngine/actions/workflows/backend-ci.yml)
[![Frontend CI](https://github.com/PetrefiedThunder/RegEngine/actions/workflows/frontend-ci.yml/badge.svg)](https://github.com/PetrefiedThunder/RegEngine/actions/workflows/frontend-ci.yml)
[![Security](https://github.com/PetrefiedThunder/RegEngine/actions/workflows/security.yml/badge.svg)](https://github.com/PetrefiedThunder/RegEngine/actions/workflows/security.yml)
[![Nightly Resilience](https://github.com/PetrefiedThunder/RegEngine/actions/workflows/nightly-resilience-test.yml/badge.svg)](https://github.com/PetrefiedThunder/RegEngine/actions/workflows/nightly-resilience-test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**A multi-tenant, audit-grade regulatory intelligence platform** that transforms regulatory documents into actionable compliance intelligence through ML-powered extraction, human-in-the-loop validation, and knowledge graph technology.

🌐 **Live:** [regengine.co](https://regengine.co)

> 🥬 **FSMA 204 Food Traceability** – Complete supply chain compliance with 24-hour recall capability, 23 FDA food category coverage, and tamper-proof audit chains. [See details →](#-fsma-204-food-traceability)

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🔍 **Smart Extraction** | ML-powered document analysis with LLM fallback (OpenAI/Ollama) |
| 🕸️ **Knowledge Graph** | Neo4j-backed regulatory relationships and obligations |
| 🏢 **Multi-Tenant** | Complete data isolation with Row-Level Security (Double-Lock model) |
| 🥬 **FSMA 204** | FDA food traceability with forward/backward supply chain queries |
| 📊 **Audit-Grade** | Deterministic cryptographic hashing and immutable evidence chains |
| 🔐 **Enterprise Security** | API key auth, JWT-RLS, rate limiting, PII encryption |
| ⚡ **15 Industry Verticals** | Food Safety, Energy, Healthcare, Aerospace, Automotive, and more |
| 🎯 **FTL Checker** | Instant FDA Food Traceability List category compliance checks |

---

## 🏗️ Architecture

### Core Services (Python / FastAPI)

| Service | Port | Description |
|---------|------|-------------|
| **Admin API** | 8400 | Tenant management, API keys, RLS-enabled database access |
| **Ingestion** | 8300 | URL/file intake, format extraction (PDF, CSV, HTML, XML), S3 storage |
| **NLP** | 8100 | LLM extraction, confidence routing, regulatory entity recognition |
| **Graph** | 8200 | Neo4j interaction, FSMA traceability queries, supply chain analysis |
| **Energy** | 8500 | Energy market compliance, snapshot engine, mismatch detection |
| **Opportunity** | 8600 | Regulatory arbitrage and gap analysis |
| **Compliance** | — | Industry-specific checklist evaluation engine |
| **Scheduler** | — | Background job orchestration |

### Industry Verticals

Aerospace · Automotive · Construction · Energy · Entertainment · Food Safety · Gaming · Healthcare · Manufacturing

### Frontend (Next.js / React)

A modern dashboard at [regengine.co](https://regengine.co) with:
- Vertical-specific compliance dashboards
- FTL Checker with 23 FDA food categories
- Document ingestion UI (URL + file upload)
- Executive owner dashboard with analytics
- Developer API console

### Data Infrastructure

| Component | Technology |
|-----------|-----------|
| **Event Streaming** | Redpanda (Kafka-compatible) |
| **Knowledge Graph** | Neo4j Community Edition |
| **Relational DB** | PostgreSQL 15 with Row-Level Security |
| **Object Storage** | S3 (LocalStack for development) |
| **Cache** | Redis 7 |
| **LLM Inference** | Ollama (local) or OpenAI API |

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Node.js 18+ (for frontend)

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env and set required secrets:
#   NEO4J_PASSWORD     – openssl rand -base64 32
#   ADMIN_MASTER_KEY   – openssl rand -hex 32
```

### 2. Start Backend Services

```bash
docker-compose up -d
# Wait ~30-60s for services to become healthy
docker-compose ps   # verify all containers are healthy
```

### 3. Start the Frontend

```bash
cd frontend
npm ci
npm run dev
```

Access the dashboard at **http://localhost:3000**.

---

## 🥬 FSMA 204 Food Traceability

RegEngine includes a complete **FDA FSMA 204 compliance module** for food supply chain traceability:

- **Document Extraction** – Extract CTEs (Critical Tracking Events) and KDEs (Key Data Elements) from BOLs, invoices, and production logs
- **One-Up/One-Down Tracing** – Forward and backward supply chain queries in Neo4j
- **TLC Validation** – GTIN/GLN/SSCC check digit verification and pattern matching
- **FDA Export** – Sortable CSV spreadsheets for 24-hour recall compliance (21 CFR 1.1455)
- **23 FDA Categories** – Full FTL coverage including Leafy Greens, Finfish, Fresh-Cut Fruits, Cheeses, and more
- **Tamper-Proof Audit Chain** – Deterministic hashing with cryptographic proof envelopes

**API Endpoints:**
```
GET  /v1/fsma/trace/forward/{tlc}      # Find downstream customers
GET  /v1/fsma/trace/backward/{tlc}     # Find upstream suppliers
GET  /v1/fsma/export/trace/{tlc}       # FDA-compliant CSV export
POST /v1/fsma/validate/gtin            # GTIN validation with check digit
POST /v1/fsma/plan/generate            # Generate traceability plan
```

📄 **Spec:** [docs/specs/FSMA_204_MVP_SPEC.md](docs/specs/FSMA_204_MVP_SPEC.md)

---

## 🔐 Security

- **Double-Lock Tenant Isolation** – Application-layer validation + PostgreSQL Row-Level Security
- **JWT-RLS Integration** – Database sessions automatically scoped to authenticated tenant
- **Immutable Audit Chains** – Cryptographically linked evidence records
- **API Key Authentication** – Per-tenant keys with rate limiting
- **PII Encryption** – At-rest encryption for sensitive regulatory data
- **OWASP Scanning** – Semgrep SAST, Gitleaks secrets scanning, dependency auditing

---

## 🌪️ Resilience & Chaos Engineering

RegEngine is built to survive infrastructure failures. We verify this daily with our [Chaos Engineering Suite](scripts/chaos/README.md).

- **Nightly Resilience Tests** – Automated fault injection (Neo4j, Kafka, Service crashes) running every night at 2 AM UTC.
- **Zero Data Loss Guarantee** – Systems are verified to recover from outages with 100% data integrity.
- **RTO < 60s** – Services self-heal and resume processing within one minute of critical dependency recovery.

To run chaos tests locally:
```bash
./scripts/chaos/run_all_chaos_tests.sh
```

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [docs/PRODUCT_ROADMAP.md](docs/PRODUCT_ROADMAP.md) | Engineering roadmap |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Infrastructure & deployment guide |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture deep-dive |
| [docs/SOC2_CONTROL_MATRIX.md](docs/SOC2_CONTROL_MATRIX.md) | SOC 2 compliance controls |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Business roadmap (18-month horizon) |
| [docs/specs/FSMA_204_MVP_SPEC.md](docs/specs/FSMA_204_MVP_SPEC.md) | FSMA 204 specification |

---

## 🧪 Testing

```bash
# Run all backend tests (622 passing)
cd services/<service-name>
PYTHONPATH=$(pwd)/../.. python -m pytest tests/ -v

# Frontend
cd frontend
npm run test
```

**Test coverage across 11 services:** Admin, Energy, Ingestion, Graph, NLP, Shared, Automotive, Opportunity, Internal, Compliance, Scheduler.

---

## 📁 Repository Structure

```
RegEngine/
├── frontend/              # Next.js dashboard & developer portal
├── services/
│   ├── admin/             # Tenant management & API keys
│   ├── ingestion/         # Document intake & format extraction
│   ├── nlp/               # ML extraction & confidence routing
│   ├── graph/             # Neo4j & supply chain queries
│   ├── energy/            # Energy market compliance
│   ├── compliance/        # Checklist evaluation engine
│   ├── opportunity/       # Regulatory gap analysis
│   ├── scheduler/         # Background job orchestration
│   └── shared/            # Cross-service utilities
├── shared/                # Auth, validators, security modules
├── gateway/               # API gateway configuration
├── scripts/               # CLI tools & utilities
├── docs/                  # Architecture & compliance docs
├── schemas/               # Avro & data schemas
├── docker-compose.yml     # Development stack
└── docker-compose.prod.yml # Production configuration
```

---

## License

MIT – see [LICENSE](LICENSE) for details.
