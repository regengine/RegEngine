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
- **Full-text search** across codified sections and obligations (`/v1/regulations/search`)
- Tamper-evident evidence vault with SHA-256/Merkle hash chains
- **Compliance score engine** (obligation coverage × control effectiveness × evidence freshness)
- Real-time drift detection and compliance scoring
- Multi-tenant isolation with Row-Level Security
- OpenTelemetry tracing + structured logging + Prometheus metrics
- Kafka consumers with poison-pill DLQ resilience
- **Nightly FSMA sync** job (02:00 UTC, leader-guarded, deduplication via ETag + SHA-256)

### FSMA 204 V2 Wizard API (public, no auth required)
| Endpoint | Description |
|----------|-------------|
| `GET  /v1/fsma/wizard/ftl-categories` | All 23 Food Traceability List categories + exemption definitions |
| `POST /v1/fsma/wizard/applicability`  | Evaluate selected FTL categories |
| `POST /v1/fsma/wizard/exemptions`     | Evaluate answers to the 6 exemption questions |

### Pilot Dashboard
Visit `/fsma/dashboard` for the operator-facing compliance summary:
- Animated compliance score ring (obligation coverage / control effectiveness / evidence freshness)
- Live counts of obligations, mapped controls, and evidence items
- Quick links to FTL Checker, Readiness Assessment, and Traceability Dashboard
- Demo mode when no graph data exists (always useful from day one)

### Quick Start
```bash
docker-compose up -d
cd services/ingestion
uvicorn app.main:app --reload
```

### Running Tests
```bash
# FSMA engine + wizard routes (62 tests)
python3 -m pytest tests/test_fsma_applicability_engine.py services/graph/tests/test_fsma_wizard_routes.py -v

# Run Neo4j FTS migration (once, against live instance)
# cypher-shell -f migrations/fts_index.cypher
```

See `docs/FSMA-operations.md` for the current FSMA compliance workflow.

---

**Status**: Production-ready FSMA wedge · Phase 29 complete · Kernel ready for additional vertical plugins once FSMA revenue is proven.
