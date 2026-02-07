# RegEngine – Regulatory Intelligence Platform

[![Glass Box Audit](https://github.com/PetrefiedThunder/RegEngine/actions/workflows/provenance_audit.yml/badge.svg)](https://github.com/PetrefiedThunder/RegEngine/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.x-green.svg)](https://neo4j.com/)

**A multi-tenant, audit-grade regulatory intelligence platform** that transforms regulatory documents into actionable compliance intelligence through ML-powered extraction, human-in-the-loop validation, and knowledge graph technology.

> 🥬 **NEW: FDA FSMA 204 Food Traceability** – Complete supply chain compliance with 24-hour recall capability. [See demo →](#-fsma-204-food-traceability)

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🔍 **Smart Extraction** | ML-powered document analysis with LLM fallback (OpenAI/Ollama) |
| 🕸️ **Knowledge Graph** | Neo4j-backed regulatory relationships and obligations |
| 🏢 **Multi-Tenant** | Complete data isolation with Row-Level Security |
| 🥬 **FSMA 204** | FDA food traceability with forward/backward supply chain queries |
| 📊 **Audit-Grade** | Full provenance tracking and "Glass Box" transparency |
| 🔐 **Enterprise Security** | API key auth, rate limiting, PII encryption |

---

## 📚 **Documentation Hub**

**Start Here:**
- **[PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)** – Complete engineering roadmap for production deployment
- **[DEPLOYMENT.md](DEPLOYMENT.md)** – AWS deployment and infrastructure guide
- **[AUTHENTICATION.md](AUTHENTICATION.md)** – API key management and security
- **[COMMERCIALIZATION_SUMMARY.md](COMMERCIALIZATION_SUMMARY.md)** – Business model and go-to-market strategy

**Launch & Sales:**
- **[launch_orchestrator/](launch_orchestrator/)** – Complete go-to-market bundle (investors, design partners, legal)
- **[docs/ROADMAP.md](docs/ROADMAP.md)** – Business roadmap (18-month planning horizon)
- **[docs/POSITIONING.md](docs/POSITIONING.md)** – Market positioning and messaging

**For Developers & AI Agents:**
- **[AGENTS.md](AGENTS.md)** – Guidelines for AI coding agents (GitHub Copilot)
- **[.github/copilot-instructions.md](.github/copilot-instructions.md)** – Repository-specific coding conventions and patterns

## 🟢 Verified Implementation Status (December 2025)

> This section describes the **currently running and verified** capabilities of the codebase.

| Component | Status | Verified Capability |
| --- | --- | --- |
| **Infrastructure** | 🟢 **Healthy** | Full Docker Compose stack (Postgres, Redis, Neo4j, Redpanda, LocalStack, Ollama) boots successfully. Services communicate via internal network. |
| **Admin API** | 🟢 **Live** | Running on port 8400. Database migrations (including RLS) apply automatically on startup. Healthchecks passing. |
| **Frontend** | 🟢 **Live** | Next.js 15.5.6 Dashboard running on port 3000. Developer Portal accessible. Verified compatible with React 18.3 and all installed plugins. |
| **CLI Tool** | 🟢 **Live** | `regctl` Python CLI installed and verified. Supports system management and ingestion triggers. |
| **Ingestion** | 🟢 **Live** | `POST /ingest/url` accepts URLs, fetches content (SSRF protected), normalizes to text, and emits to Kafka. |
| **NLP Pipeline** | 🟢 **Live** | Service is healthy (Port 8100). LLM extraction configured for OpenAI/Ollama fallback. FSMA 204 extractor implemented. |
| **Graph DB** | 🟢 **Live** | Neo4j (Port 7474) running. Graph service (Port 8200) consuming events. FSMA traceability queries supported. |
| **FSMA 204** | 🟢 **Complete** | Full FDA Food Safety compliance: TLC validation, forward/backward tracing, FDA spreadsheet export, plan builder. |
| **Kafka UI** | 🟢 **Live** | Management UI running on port 8080 for inspecting topics (`ingest.normalized`, `graph.update`). |

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Node.js 18+ (for Frontend)

### 1. Configure Environment Variables
```bash
# Copy the environment template
cp .env.example .env

# Edit .env and set REQUIRED secrets:
# - NEO4J_PASSWORD: Generate with `openssl rand -base64 32`
# - ADMIN_MASTER_KEY: Generate with `openssl rand -hex 32`
# - AWS credentials are pre-set to "test" for LocalStack (local development)
```

### 2. Start the Stack
```bash
# Start all backend services and infrastructure
make up
```
*Wait for services to become healthy (approx 30-60s).*

### 3. Start the Frontend
```bash
cd frontend
npm ci
npm run dev
```
Access the dashboard at **http://localhost:3000**.

### 4. Use the CLI
To manage tenants and trigger ingestion, set up the `regctl` CLI tool:

```bash
# 1. Install CLI-specific dependencies
pip install -r scripts/regctl/requirements.txt

# 2. Run the CLI
# Ensure you are in the root directory
python scripts/regctl/tenant.py --help

# Example: Create a demo tenant
python scripts/regctl/tenant.py create "Demo Corp" --demo-mode
```

## 🎯 System Capabilities

The repo currently supports a concrete ingestion → extraction → graph workflow:

1. **API-key gated access** – Every FastAPI service depends on `shared.auth.require_api_key`.
2. **Document ingestion** – `POST /ingest/url` validates external URLs, downloads the bytes with SSRF guards, normalizes PDFs/JSON, writes artifacts to S3 (LocalStack), and emits a `NormalizedEvent` to Kafka.
3. **LLM or heuristic extraction** – `services/nlp` produces `ExtractionPayload` items using configured LLMs (Ollama/OpenAI) or rule-based fallbacks.
4. **Confidence-aware routing** – High-confidence extractions (≥0.85) route to `graph.update`; low-confidence items route to `nlp.needs_review`.
5. **Graph + overlay writes** – `services/graph` consumes events and upserts tenant-scoped data into Neo4j.
6. **Analytics + checklist APIs** – Opportunity and Compliance services provide analysis endpoints against the graph and industry checklists.

## 🥬 FSMA 204 Food Traceability

RegEngine includes a complete **FDA FSMA 204 compliance module** for food supply chain traceability:

**Features:**
- **Document Extraction** – Extract CTEs (Critical Tracking Events) and KDEs (Key Data Elements) from BOLs, invoices, and production logs
- **One-Up/One-Down Tracing** – Forward and backward supply chain queries in Neo4j
- **TLC Validation** – GTIN/GLN/SSCC check digit verification and pattern matching
- **FDA Export** – Sortable CSV spreadsheets for 24-hour recall compliance
- **Plan Builder** – Generate FSMA 204 traceability plans from templates

**API Endpoints:**
```bash
GET  /v1/fsma/trace/forward/{tlc}      # Find downstream customers
GET  /v1/fsma/trace/backward/{tlc}     # Find upstream suppliers
GET  /v1/fsma/export/trace/{tlc}       # FDA-compliant CSV export
POST /v1/fsma/validate/gtin            # GTIN validation with check digit
POST /v1/fsma/plan/generate            # Generate traceability plan
```

**Run the Demo:**
```bash
./scripts/demo/fsma_mock_recall.sh     # Run mock recall demonstration
```

📄 **Spec:** [docs/specs/FSMA_204_MVP_SPEC.md](docs/specs/FSMA_204_MVP_SPEC.md)

## 🏗️ **Architecture Overview**

### **Core Services (Python/FastAPI)**

- **Admin API** (`services/admin/`) – Tenant management, API keys, and RLS-enabled database access.
- **Ingestion Service** (`services/ingestion/`) – URL fetching, PDF normalization, S3 storage.
- **NLP Service** (`services/nlp/`) – LLM extraction and confidence routing.
- **Graph Service** (`services/graph/`) – Neo4j interaction and graph projection.
- **Opportunity API** (`services/opportunity/`) – Regulatory arbitrage and gap analysis.
- **Compliance Engine** (`services/compliance/`) – Industry-specific checklist evaluation.

### **Frontend (Next.js/React)**

- **Dashboard UI** (`frontend/`) – Modern React-based interface for compliance officers.
- **Developer Portal** – Integrated documentation and API exploration.

### **Data Infrastructure**

- **Event Streaming** – Redpanda (Kafka compatible) on port 9092.
- **Knowledge Graph** – Neo4j Community Edition on ports 7474/7687.
- **Relational DB** – PostgreSQL 15 with Row-Level Security (RLS).
- **Object Storage** – LocalStack (S3 compatible).
- **LLM Inference** – Ollama (local Llama 3) or OpenAI API.

### **Shared Components**

- **Auth & Rate Limiting** (`shared/auth.py`) – Centralized API key enforcement.
- **Security Modules** (`shared/`) – Comprehensive security hardening (Input validation, PII encryption, Audit logging).
