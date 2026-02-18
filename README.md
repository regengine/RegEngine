# RegEngine

**Multi-tenant regulatory operating system for FDA FSMA compliance.**

RegEngine converts statutory obligations into continuously monitored, cryptographically verifiable control systems.

### Current Focus
- **FDA FSMA (21 CFR Parts 1, 11, 117, 204, etc.)** – full ingestion, codification, monitoring, and attestation pipeline.
- Production-ready kernel for future verticals (plugin architecture).

### Core Architecture
```
kernel/                  # Universal compliance engine (obligation, control, evidence, monitoring, reporting)
plugins/fsma/            # FSMA-specific grammar, mappings, report templates
services/                # ingestion, graph, scheduler, admin
shared/                  # utilities, models, observability, security
```

### Key Capabilities
- Automated regulation ingestion (PDF, API, bulk) with ethical discovery
- Neo4j knowledge graph with obligation → control → evidence mapping
- Tamper-evident evidence vault with SHA-256 hash chains
- Real-time drift detection and compliance scoring
- Multi-tenant isolation with Row-Level Security
- OpenTelemetry tracing + structured logging + Prometheus metrics
- Kafka consumers with poison-pill DLQ resilience

### Quick Start
```bash
docker-compose up -d
cd services/ingestion
uvicorn app.main:app --reload
```

See `docs/FSMA-pilot.md` for the current customer pilot workflow.

---

**Status**: Production-ready FSMA wedge. Kernel ready for additional vertical plugins once FSMA revenue is proven.
