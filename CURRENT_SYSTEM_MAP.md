# Current System Map

**Purpose:** A survival map for a new technical leader. Not a vision doc.
Last updated: 2026-04-14.

---

## Core Modules

| Module | Location | What It Does |
|--------|----------|-------------|
| Canonical Event Model | `shared/canonical_event.py` | Defines `TraceabilityEvent` — the single source of truth for supply chain events. Fields include TLC, KDEs, hash chain, provenance, confidence score. |
| Canonical Persistence | `shared/canonical_persistence.py` (1034 lines) | Reads/writes canonical events to `fsma.traceability_events`. Handles dual-write migration logic. |
| CTE Persistence | `shared/cte_persistence.py` (1298 lines) | Legacy event storage in `fsma.cte_events` + `fsma.cte_kdes`. Batch operations, query builder. |
| Identity Resolution | `shared/identity_resolution.py` (1283 lines) | Entity matching/merging across `fsma.canonical_entities`, `fsma.entity_aliases`, `fsma.identity_review_queue`. Fuzzy matching with confidence thresholds (LOW=0.60, HIGH=0.90). |
| Rules Engine | `shared/rules/` (split from `rules_engine.py`) | Versioned FSMA rule definitions + evaluation. Stateless evaluators (field checks) and relational evaluators (cross-entity/event). Writes results to `fsma.rule_evaluations`. |
| Audit Logging | `shared/audit_logging.py` (1069 lines) | 60+ audit event types across 10 categories. Mixes application security audit (login, access) with compliance audit (data modification, export). |
| Hash Chain | `fsma.hash_chain` table + `shared/merkle_tree.py` | Tamper-evident chain: each event hash includes the previous chain hash. GENESIS block starts each tenant's chain. |
| FDA Export | `ingestion/app/fda_export_service.py` | Converts canonical events to 33-column FDA spreadsheet format. Logged in `fsma.fda_export_log` with SHA-256 of output. |

## Production Spine

```
ingestion → canonicalization → identity resolution → compliance evaluation → audit output → FDA export
```

### What runs on the spine:

1. **Ingestion** (service: ingestion, port 8002) — Accepts EPCIS XML, EDI, CSV, manual entry. Normalizes to canonical event schema. Generates SHA-256 content hash + idempotency key. Tracks batch metadata in `fsma.ingestion_runs`.

2. **Canonicalization** (module: `shared/canonical_persistence.py`) — Writes normalized events to `fsma.traceability_events` with status ACTIVE. Appends to hash chain (`fsma.hash_chain`). Deduplicates via idempotency_key unique constraint.

3. **Identity Resolution** (module: `shared/identity_resolution.py`) — Matches ingested entity references against `fsma.canonical_entities` using aliases. Confidence < 0.60 → auto-create new entity. 0.60-0.90 → queue for human review (`fsma.identity_review_queue`). > 0.90 → auto-merge. Merge history tracked in `fsma.entity_merge_history`.

4. **Compliance Evaluation** (module: `shared/rules/engine.py`) — Loads active rules from `fsma.rule_definitions` (WHERE retired_date IS NULL AND effective_date <= CURRENT_DATE). Evaluates applicable rules against each event. Writes per-rule results to `fsma.rule_evaluations`. Aggregates into EvaluationSummary (pass/fail/warn/skip counts).

5. **Audit Output** (module: `shared/audit_logging.py`) — Records data modification, compliance evaluation, and export events. Hash chain provides tamper-evidence.

6. **FDA Export** (module: `ingestion/app/fda_export_service.py`) — Generates 33-column spreadsheet (FDA_COLUMNS spec). Records export in `fsma.fda_export_log` with file hash. V2 spec adds compliance status, rule failures, trace relationships.

### What is NOT on the spine:

- **Graph service** (Neo4j) — Supply chain visualization, recall simulation. Useful but not required for core compliance.
- **NLP service** — Regulatory text extraction from documents. Feeds graph, not the compliance evaluation path.
- **Scheduler FDA scraping** — Pulls FDA warning letters, import alerts, recalls. Enrichment data, not core compliance.
- **Advanced identity resolution via Neo4j** — The PostgreSQL-based identity resolution in `shared/` is the production path.

## Source of Truth

| Concept | Table | Service That Writes | Who Reads |
|---------|-------|-------------------|-----------|
| Canonical events | `fsma.traceability_events` | ingestion (via `shared/canonical_persistence.py`) | compliance, graph, admin, export |
| Legacy CTE events | `fsma.cte_events` + `fsma.cte_kdes` | ingestion (via `shared/cte_persistence.py`) | compliance, export |
| Canonical entities | `fsma.canonical_entities` | ingestion (via `shared/identity_resolution.py`) | graph, compliance, admin |
| Entity aliases | `fsma.entity_aliases` | ingestion, admin (manual) | identity resolution |
| Rule definitions | `fsma.rule_definitions` | admin (seeded + manual) | compliance |
| Rule evaluations | `fsma.rule_evaluations` | compliance (via `shared/rules/engine.py`) | export, admin dashboard |
| Hash chain | `fsma.hash_chain` | ingestion (on canonicalization) | audit, export, integrity checks |
| Export log | `fsma.fda_export_log` | ingestion/export service | admin dashboard, monitoring |
| Audit events | Application audit log | all services | admin, security |

## Legacy State vs Target State

| Area | Current State | Target State |
|------|--------------|-------------|
| Event storage | Dual-write to `cte_events` (legacy) AND `traceability_events` (canonical) | Single write to `traceability_events` only |
| Inter-service communication | HTTP calls via `shared/resilient_http.py` + Kafka topics | Direct function calls (monolith) |
| Identity resolution | PostgreSQL-based (`shared/identity_resolution.py`) + Neo4j graph (`graph/`) | PostgreSQL only, drop Neo4j |
| Message queue | Redpanda (Kafka) for NLP pipeline + pg task queue for background jobs | PostgreSQL task queue only, drop Kafka |
| Cache/session | Redis for sessions, JWT registry, circuit breaker state, rate limiting | PostgreSQL or in-process (monolith) |
| Deployment | 6 Railway containers + Vercel frontend | 1 Railway container + Vercel frontend |
| Rules engine | Already split into `shared/rules/` subpackage | Done |

## Synchronous vs Asynchronous

### Synchronous (request-response):

- All API endpoint handlers (FastAPI routes)
- Compliance rule evaluation (called inline during ingestion or on-demand)
- Identity resolution (called inline during ingestion)
- FDA export generation (on-demand via API)
- Inter-service HTTP calls via `resilient_http.py` (timeout 30s, retry on 502/503/504)

### Asynchronous:

- **Kafka pipeline:** ingestion → `ingest.normalized` → NLP consumer → `graph.update` / `nlp.needs_review` → Graph consumer / Admin review consumer
- **PostgreSQL task queue:** `fsma.task_queue` table, polled every 2s by `server/workers/task_processor.py`. Task types: nlp_extraction, graph_update, review_item. Distributed locking via SELECT...FOR UPDATE SKIP LOCKED.
- **Scheduler jobs:** 7 APScheduler jobs (FDA scraping, FSMA nightly sync at 02:00 UTC, state cleanup, deadline monitoring, account disablement, KDE retention, data archival). Leader-elected — only one instance processes.
- **Webhook delivery:** ThreadPoolExecutor (5 workers) with 3 retries + exponential backoff. In-memory DLQ (volatile) in scheduler, persistent DLQ in `dlq.webhook_failures` table.

### DLQ topology:

```
Kafka DLQ topics: graph.update.dlq, nlp.needs_review.dlq, nlp.extracted.dlq, fsma.dead_letter
PostgreSQL DLQ: dlq.webhook_failures (persistent, multi-tenant)
In-memory DLQ: scheduler/app/notifications.py WebhookNotifier._dead_letter (volatile, lost on restart)
```

## Service Communication Map

```
                                    ┌──────────────┐
                                    │   Frontend   │
                                    │   (Vercel)   │
                                    └──────┬───────┘
                                           │ HTTP (proxy)
                                    ┌──────▼───────┐
                          ┌────────►│    Admin     │◄────────┐
                          │         │   (8001)     │         │
                          │         └──────────────┘         │
                          │                                  │
                   ┌──────┴───────┐                  ┌───────┴──────┐
                   │  Ingestion   │──── Kafka ──────►│     NLP      │
                   │   (8002)     │  ingest.normalized│   (8004)    │
                   └──────┬───────┘                  └───────┬──────┘
                          │                                  │
                     shared/                          Kafka: graph.update
                  canonical_persistence               Kafka: nlp.needs_review
                  cte_persistence                            │
                  identity_resolution                 ┌──────▼───────┐
                          │                           │    Graph     │
                          │                           │   (8003)    │
                   ┌──────▼───────┐                   └──────────────┘
                   │  Compliance  │                          │
                   │   (8500)     │                     Neo4j writes
                   └──────────────┘
                          │
                   shared/rules/engine
                   shared/audit_logging

              ┌──────────────┐
              │  Scheduler   │──── Kafka: enforcement.changes, alerts.regulatory
              │   (8005)     │──── HTTP: calls ingestion for FSMA nightly sync
              └──────────────┘
```

**All services share:** PostgreSQL (Supabase), Redis, `services/shared/` Python modules.

**Inter-service HTTP calls observed:**
- NLP → Graph (via `resilient_client(circuit_name="graph-service")`)
- Admin → Compliance API (regulatory checks)
- Scheduler → Ingestion (FSMA nightly sync)
- Frontend → All services (via Next.js proxy rewrites)

## What Is Deployed Today

All 6 services run as independent Railway containers. Each has:
- Its own Dockerfile
- Its own `requirements.txt`
- Health check endpoint at `/health`
- Structlog JSON logging
- OpenTelemetry tracing (except scheduler)

Frontend runs on Vercel with API proxy to Railway services.

Database: Single PostgreSQL instance on Supabase with `fsma` schema. RLS enforced on tenant-bearing tables.
