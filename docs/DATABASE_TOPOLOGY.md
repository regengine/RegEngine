# RegEngine — Database Topology

**Last Updated:** February 8, 2026

---

## Overview

RegEngine uses a shared PostgreSQL 15 instance with logical separation via **schemas** and **separate databases**. Row-Level Security (RLS) enforces tenant isolation at the database layer ("Double-Lock" model).

```
┌──────────────────────────────────────────────────────────────────────┐
│                     PostgreSQL 15 (port 5432)                       │
│                                                                      │
│  ┌─────────────────────┐   ┌─────────────────────────────────────┐  │
│  │  regengine (default) │   │  regengine_admin                    │  │
│  │  ┌─────────────────┐│   │  ┌───────────┐  ┌───────────────┐  │  │
│  │  │   public         ││   │  │  public    │  │  energy        │  │  │
│  │  │   (ingestion,    ││   │  │  (tenants, │  │  (snapshots,   │  │  │
│  │  │    graph events) ││   │  │   api_keys,│  │   substations) │  │  │
│  │  └─────────────────┘│   │  │   reviews) │  └───────────────┘  │  │
│  └─────────────────────┘   │  └───────────┘                      │  │
│                             │  ┌───────────────────┐              │  │
│  ┌─────────────────────┐   │  │  entertainment     │              │  │
│  │  energy (dedicated)  │   │  │  (PCOS tables)     │              │  │
│  │  CIP-013 snapshots   │   │  └───────────────────┘              │  │
│  └─────────────────────┘   └─────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                     Neo4j (bolt://neo4j:7687)                        │
│  Knowledge Graph: FSMA 204 supply chain lineage, entity resolution   │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                     Redis (port 6379)                                 │
│  Sessions, rate limiting, caching                                    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Service → Database Mapping

| Service | Database | Schema | Driver | Connection Var |
|---------|----------|--------|--------|----------------|
| **admin** | `regengine_admin` | `public` | `psycopg` (sync) | `ADMIN_DATABASE_URL` |
| **energy** | `energy` / `regengine_admin` | `energy` | `asyncpg` / `psycopg` | `DATABASE_URL` |
| **opportunity** | `regengine_admin` | `public` | `asyncpg` | `DATABASE_URL` |
| **compliance** | `regengine_admin` | `public` | `psycopg` | `DATABASE_URL` |
| **entertainment** | `regengine_admin` | `entertainment` | `psycopg` | `ENTERTAINMENT_DATABASE_URL` |
| **ingestion** | `regengine` | `public` | `psycopg` | `DATABASE_URL` |
| **graph** | Neo4j | — | `neo4j` driver | `NEO4J_URI` |
| **nlp** | — (Kafka only) | — | — | — |
| **scheduler** | `regengine_admin` | `public` | `psycopg` | `DATABASE_URL` |
| **automotive** | `regengine_admin` | `public` | `psycopg` | `DATABASE_URL` |
| **gaming** | `regengine_admin` | `public` | `psycopg` | `DATABASE_URL` |
| **aerospace** | `regengine_admin` | `public` | `psycopg` | `DATABASE_URL` |
| **construction** | `regengine_admin` | `public` | `psycopg` | `DATABASE_URL` |
| **manufacturing** | `regengine_admin` | `public` | `psycopg` | `DATABASE_URL` |

---

## Databases

### `regengine` (default)
- Created by PostgreSQL init
- Used by the ingestion pipeline for raw document storage
- Contains core event tables

### `regengine_admin`
- Created by `scripts/init-postgres.sh`
- Houses admin tables (tenants, API keys, reviews), vertical schemas
- RLS enforced via `app.tenant_id` session variable

### `energy` (standalone)
- Dedicated database for NERC CIP-013 compliance snapshots
- Uses `energy.*` schema with custom enums

---

## Row-Level Security (RLS)

All multi-tenant tables enforce RLS via the `app.tenant_id` session variable:

```sql
-- Set by application middleware before every query
SET LOCAL app.tenant_id = '<tenant-uuid>';

-- RLS policy pattern (applied to all tenant-scoped tables)
CREATE POLICY tenant_isolation ON <table>
    USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

Verified via adversarial tests: cross-tenant access returns 0 rows.

---

## Message Broker

### Redpanda / Kafka (port 9092)

| Topic | Producer | Consumer | Purpose |
|-------|----------|----------|---------|
| `ingest.normalized` | ingestion | nlp | Normalized documents for NLP extraction |
| `nlp.extracted` | nlp | graph | Extracted entities (legacy) |
| `graph.update` | nlp | graph | High-confidence extractions for graph update |
| `nlp.needs_review` | nlp | admin | Low-confidence extractions for human review |
| `nlp.extracted.dlq` | nlp | — | Dead letter queue for failed NLP processing |
| `nlp.needs_review.dlq` | admin | — | Dead letter queue for failed review processing |
| `ingest.dlq` | ingestion | — | Dead letter queue for failed ingestion jobs |

---

## Init Script

`scripts/init-postgres.sh` runs on first container start:
1. Creates `regengine_admin` database
2. Creates `energy` database
3. Grants privileges to `regengine` role
4. Creates schemas (`energy`, `entertainment`) if they don't exist
