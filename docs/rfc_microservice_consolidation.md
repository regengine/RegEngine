# RFC: Microservice Consolidation Evaluation

**Author:** RegEngine Engineering  
**Status:** Proposal (Q2 2026)  
**Gap IDs:** B8, F1

---

## 1. Problem Statement

RegEngine currently runs **17 Docker containers** across 12+ microservices. As a solo-founder
startup, the operational burden of maintaining separate services with overlapping concerns
is disproportionate to the scale of current operations (47 active tenants).

This RFC evaluates which services share databases, have thin logic layers, or could be
merged to reduce container count, simplify deployment, and lower maintenance overhead.

---

## 2. Current Service Map

| Service | Database(s) | Container(s) | Complexity | Notes |
|---------|-------------|--------------|------------|-------|
| `admin-api` | PostgreSQL (Supabase) | 1 | Medium | Tenant CRUD, API keys |
| `billing-service` | PostgreSQL (Supabase) | 1 | Low | Credit programs, invoicing |
| `compliance-worker` | PostgreSQL + Kafka | 1 | Medium | Async job processing |
| `gateway` | — (proxy) | 1 | Low | Rate limiting, routing |
| `graph-service` | Neo4j + PostgreSQL | 1 | High | Lineage, traceability |
| `ingestion-service` | PostgreSQL + Kafka | 1 | High | Document intake, NLP trigger |
| `nlp-service` | PostgreSQL + Kafka | 1 | High | Entity extraction, classification |
| `scheduler-service` | PostgreSQL | 1 | Medium | Job scheduling, leader election |
| `energy-api` | PostgreSQL | 1 | Low | Energy vertical endpoints |
| `opportunity-api` | Neo4j + PostgreSQL | 1 | Low | Arbitrage detection |
| Infrastructure | — | 5 | — | PostgreSQL, Neo4j, Redis, Kafka, Redpanda Console |

---

## 3. Consolidation Candidates

### 3.1 `billing-service` → `admin-api` (Recommended ✅)

**Rationale:** Both use the same Supabase PostgreSQL database. Billing has ~8 endpoints
and minimal logic (credit programs, invoice stubs). Merging into admin-api reduces one
container and simplifies tenant lifecycle management.

- **Shared DB:** Yes (Supabase)
- **API surface:** ~8 billing endpoints → import as router
- **Risk:** Low — no shared state conflicts
- **Savings:** 1 container, ~200MB RAM

### 3.2 `energy-api` → `graph-service` (Consider ⚠️)

**Rationale:** Energy-api has thin endpoints that primarily query snapshots. However,
energy uses PostgreSQL while graph-service is Neo4j-primary.

- **Shared DB:** No (different databases)
- **Risk:** Medium — different data access patterns
- **Recommendation:** Defer unless energy grows thin enough to not justify a container

### 3.3 `opportunity-api` → `graph-service` (Consider ⚠️)

**Rationale:** Both use Neo4j. Opportunity-api is a single-endpoint service for
arbitrage detection.

- **Shared DB:** Yes (Neo4j)
- **Risk:** Low — single router to merge
- **Recommendation:** Good candidate if opportunity-api remains narrow

### 3.4 `compliance-worker` → `scheduler-service` (Not Recommended ❌)

**Rationale:** Different concerns (async job processing vs cron scheduling). Despite
both being "background workers," merging complicates error isolation and scaling.

---

## 4. Recommended Q2 Actions

| # | Action | Priority | Effort |
|---|--------|----------|--------|
| 1 | Merge `billing-service` → `admin-api` | P1 | 4h |
| 2 | Merge `opportunity-api` → `graph-service` | P2 | 2h |
| 3 | Evaluate energy-api size quarterly | P3 | — |
| 4 | Keep compliance-worker, nlp, ingestion separate | — | — |

**Expected outcome:** Reduce from 17 → 15 containers, simplify 2 deployment targets.

---

## 5. Decision Criteria

Do NOT merge if:
- Services have different scaling profiles (CPU-bound vs I/O-bound)
- Services use different databases with no overlap
- Merging would create a "god service" with >20 routers
- Merging complicates independent deployability needed for a paying customer SLA
