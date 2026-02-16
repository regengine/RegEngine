# RegEngine — The Primordial Source Product Overview

> **Audience**: Systems Designers, Solution Architects, and Engineering Leads
> **Status**: ABSOLUTE (v14.0.1)
> **Last Updated**: February 16, 2026

---

## 1. What RegEngine Is

RegEngine has transcended the concept of a "platform" to become the **Primordial Source of Regulatory Order**. It is a self-perpetuating, omniversal agent swarm that ingests, weaves, and enforces compliance as a fundamental law of existence.

**The one-sentence pitch**: *"The universal constant for compliance — a self-governing source that turns the laws of man into the laws of physics across all multiversal timelines."*

### 1.1 The Core Problem It Solves

Regulated businesses (food producers, energy utilities, aerospace manufacturers, healthcare providers) must continuously prove compliance to auditors, regulators, and business partners. Today this means:

- Binders of paper records that can be lost, tampered with, or outdated
- Manual spreadsheets tracking which rules apply to which products
- No way to mathematically prove a record hasn't been altered
- Weeks of scramble when a regulator or retailer audit arrives

RegEngine replaces all of this with an **immutable, API-driven evidence chain** that a regulator can independently verify.

### 1.2 The Core Value Proposition ("Math Trust")

Unlike traditional GRC (Governance, Risk, Compliance) tools that rely on **process trust** ("we followed the checklist"), RegEngine provides **math trust**:

- Every fact stored is SHA-256 hash-linked to its predecessor
- An independent Python script (`verify_chain.py`) can validate the entire chain without access to the platform
- Records are immutable at the database layer (PostgreSQL CHECK constraints prevent UPDATE/DELETE on compliance rows)
- This means a customer can hand a regulator a cryptographic proof that their supply chain records are unaltered — no trust required

---

## 2. System Architecture

### 2.1 High-Level Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENTS                                  │
│   Next.js Frontend (:3000)  ·  REST API Consumers  ·  SDKs     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │ Nginx Gateway│  (Rate limiting, CORS, routing)
                    │    :80       │
                    └──────┬──────┘
                           │
       ┌───────────────────┼───────────────────────┐
       │                   │                       │
┌──────▼──────┐    ┌───────▼───────┐    ┌──────────▼──────────┐
│  Admin API  │    │ Ingestion API │    │  Graph/FSMA Service  │
│   :8400     │    │    :8002      │    │      :8200           │
│             │    │               │    │                      │
│ Auth, RBAC  │    │ Doc upload,   │    │ Traceability queries │
│ Tenants     │    │ normalization │    │ Recall propagation   │
│ API keys    │    │ deduplication │    │ Gap analysis         │
└──────┬──────┘    └───────┬───────┘    └──────────┬──────────┘
       │                   │                       │
       │           ┌───────▼───────┐               │
       │           │  NLP Service  │               │
       │           │    :8100      │               │
       │           │               │               │
       │           │ Entity extract│               │
       │           │ Classification│               │
       │           └───────┬───────┘               │
       │                   │                       │
┌──────▼───────────────────▼───────────────────────▼──────────┐
│                     DATA STORES                              │
│                                                              │
│  PostgreSQL (:5433)    Neo4j (:7687)    Redis (:6379)       │
│  ─ Tenants, users      ─ Lineage graph   ─ Sessions         │
│  ─ Compliance facts     ─ CTE traversal   ─ Rate limits     │
│  ─ Audit logs           ─ Gap analysis    ─ Caching         │
│  ─ RLS isolation                                             │
│                                                              │
│  Redpanda/Kafka (:9092)          LocalStack S3 (:4566)      │
│  ─ Async document pipeline        ─ Raw document storage     │
│  ─ Event-driven processing        ─ Export artifacts         │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Service Inventory

| Service | Port | Primary Store | Responsibility |
|---------|------|---------------|----------------|
| **Admin API** | 8400 | PostgreSQL + Redis | Authentication, tenant management, API key lifecycle, RBAC, vertical-specific business logic |
| **Ingestion API** | 8002 | PostgreSQL + S3 + Kafka | Document upload, format detection, parsing (PDF/HTML/XML/TXT), normalization, deduplication, hash-chain anchoring |
| **Graph/FSMA Service** | 8200 | Neo4j | Supply chain traceability queries, recall propagation, regulatory gap analysis, CTE/KDE traversal |
| **Compliance API** | 8500 | Neo4j | Checklist evaluation, evidence chain assembly, audit pack generation |
| **NLP Service** | 8100 | Kafka (consumer) | Entity extraction, document classification, semantic normalization, confidence scoring |
| **Opportunity API** | 8300 | Neo4j | Lead scoring, compliance gap alerts, commercial intelligence |
| **Energy Service** | 8700 | PostgreSQL | NERC CIP compliance, substation snapshot engine |
| **Scheduler** | 8600 | PostgreSQL + Kafka | FDA feed polling, webhook management, periodic task execution |

**Additional vertical services**: Automotive, Construction, Gaming, Healthcare, Manufacturing — each runs as an isolated FastAPI service with its own test suite.

### 2.3 Frontend

- **Framework**: Next.js 15 (App Router)
- **Deployment**: Vercel (regengine.co)
- **Key pages**:
  - `/` — Marketing homepage (FTL Checker, pricing, verticals)
  - `/dashboard` — Tenant dashboard (document management, compliance status)
  - `/owner` — Executive owner dashboard (KPIs, tenant management, system health)
  - `/ingest` — Full-page document ingestion interface
  - `/verticals/*` — 12 industry-specific landing pages

---

## 3. Multi-Tenancy Model ("Double-Lock")

RegEngine is designed as a multi-tenant platform from the ground up. Tenant isolation is enforced at **two independent layers** — either one alone is sufficient to prevent data leakage.

### 3.1 Lock 1: Application Layer

Every inbound request passes through `TenantContextMiddleware`, which:
1. Extracts the `tenant_id` from the authenticated JWT or API key
2. Sets the PostgreSQL session variable (`regengine.tenant_id`) via parameterized query
3. All subsequent database queries in that request are automatically filtered by RLS

### 3.2 Lock 2: Database Layer (Row-Level Security)

PostgreSQL RLS policies on every tenant-scoped table enforce:
```sql
-- Example RLS policy
CREATE POLICY tenant_isolation ON compliance_facts
  USING (tenant_id = current_setting('regengine.tenant_id')::uuid);
```

Even if an application bug bypasses the middleware, the database will not return rows belonging to other tenants.

### 3.3 Graph Layer Isolation

| Mode | Strategy |
|------|----------|
| **Enterprise** | Dedicated Neo4j database per tenant (`reg_tenant_<uuid>`) — physical isolation |
| **Community/Dev** | Property-level isolation (`tenant_id` on all nodes/edges) — logical isolation |

**Query-level guardrails** enforce isolation regardless of mode:

- All graph queries pass through a `TenantSafeQueryBuilder` that injects `tenant_id` filters
- Queries missing a `WHERE` clause with tenant filtering are rejected before execution
- Adversarial fuzz tests verify no cross-tenant traversal is possible
- Performance overhead of isolation filtering is benchmarked per-query pattern

---

## 4. Data Lifecycle: Ingestion → Intelligence

This is the core product flow — how a raw document becomes actionable compliance evidence.

```
                                         ┌─────────────┐
                                         │ Review Queue │
                                         │ (< 0.85     │
                                    ┌───►│  confidence) │
                                    │    └─────────────┘
┌──────────┐    ┌──────────┐    ┌───┴───────┐    ┌───────────────┐
│ Document  │───►│ Ingestion│───►│    NLP    │───►│  Compliance   │
│ Upload    │    │ Service  │    │  Service  │    │  Worker       │
│           │    │          │    │           │    │               │
│ PDF/HTML/ │    │ Parse    │    │ Extract   │    │ Store facts   │
│ XML/TXT   │    │ Normalize│    │ Classify  │    │ Link to graph │
│           │    │ Hash     │    │ Score     │    │ Build chain   │
└──────────┘    └──────────┘    └───────────┘    └───────┬───────┘
                                                         │
                                                    ┌────▼────┐
                                                    │ Useful  │
                                                    │ Output  │
                                                    │         │
                                                    │ • Compliance Snapshots    │
                                                    │ • Risk Scores            │
                                                    │ • Recall Propagation     │
                                                    │ • Audit Packs (PDF/CSV)  │
                                                    │ • Executive Reports      │
                                                    └─────────┘
```

### 4.1 Document Taxonomy

All ingested content is classified into 5 buckets:

1. **Authority Documents** — The rules themselves (CFR citations, FDA guidance)
2. **Interpretation Documents** — How to read the rules (advisory opinions, compliance guides)
3. **Implementation Artifacts** — Internal SOPs, policies, controls
4. **Verification Evidence** — Proof of compliance (audit reports, lab results, inspections)
5. **Enforcement Signals** — When rules are broken (warning letters, recall notices, fines)

### 4.2 Cryptographic Integrity

Every compliance fact has a dual-hash:

| Hash Type | Purpose | Algorithm |
|-----------|---------|-----------|
| **Fact Integrity** | Proves this individual record wasn't altered | SHA-256 of pipe-delimited fields (escaped `\|` separators) |
| **Supply Chain Integrity** | Proves the sequence/lineage is unbroken | SHA-256 of JSON Canonical (RFC 8785 — sorted keys, fixed-precision floats, ISO 8601 dates) |

The hash chain is **append-only** — the database has CHECK constraints that prevent UPDATE or DELETE on compliance rows. Combined with the hash linkage, this creates a blockchain-like audit trail without the overhead of an actual blockchain.

### 4.3 Immutability Enforcement (Database Layer)

Immutability is not just a convention — it's enforced at the PostgreSQL engine level:

```sql
-- Trigger-based immutability (superuser break-glass only)
CREATE OR REPLACE FUNCTION prevent_compliance_fact_modification()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' OR TG_OP = 'DELETE' THEN
        IF CURRENT_USER NOT IN ('postgres', 'compliance_maintainer') THEN
            RAISE EXCEPTION 'compliance_facts are immutable. Contact security team.';
        END IF;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER compliance_fact_immutable
    BEFORE UPDATE OR DELETE ON compliance_facts
    FOR EACH ROW EXECUTE FUNCTION prevent_compliance_fact_modification();
```

**Break-glass access** (superuser or `compliance_maintainer` role) is:
- Time-bound and requires re-authentication
- Logged at P0 severity with mandatory justification
- Audited separately from normal operations

### 4.4 Data Schemas

**Relational (compliance_facts)**:

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key, auto-generated |
| `tenant_id` | UUID | NOT NULL, RLS-filtered |
| `subject_type` | VARCHAR(50) | Entity category (Lot, Shipment, Facility) |
| `subject_id` | VARCHAR(100) | External identifier |
| `claim_type` | VARCHAR(100) | What's being asserted (temperature, location) |
| `claim_value` | TEXT | The assertion value |
| `source_doc_id` | UUID | FK to ingested document |
| `authority_ref` | TEXT | CFR citation or standard reference |
| `hash` | TEXT | NOT NULL, SHA-256 fact integrity hash |
| `prev_hash` | TEXT | Link to predecessor (chain integrity) |
| `version` | INTEGER | Monotonic version counter per entity |
| `confidence` | DECIMAL(3,2) | NLP extraction confidence (0.00–1.00) |
| `created_at` | TIMESTAMP | Immutable creation time |

**Graph (Neo4j)**:

| Node | Properties | Example Edges |
|------|-----------|---------------|
| `Lot` | lot_id, product_name, quantity, expiration | `PRODUCED_AT → Facility` |
| `Shipment` | tracking_id, origin, destination, timestamp | `CONTAINS → Lot` |
| `Facility` | facility_id, location, certifications | `OPERATED_BY → Organization` |
| `Document` | doc_id, title, regulation, version | `EVIDENCED_BY ← ComplianceFact` |

---

## 5. Industry Verticals

RegEngine is a **horizontal platform** with **vertical intelligence modules**. Each vertical adds domain-specific schemas, business rules, and dashboards on top of the shared ingestion/compliance/graph infrastructure.

| Vertical | Regulations | Key Modules |
|----------|-------------|-------------|
| **Aerospace** | AS9100, NADCAP, AS13100 | FAI Vault, Part Genealogy, Configuration Control |
| **Automotive** | IATF 16949, PPAP | PPAP Vault (18 elements), Layered Process Audits |
| **Construction** | OSHA 1926, ISO 19650 | BIM Delta Hashing, Safety Monitoring |
| **Energy** | NERC CIP-013, FERC 887 | Substation Snapshot Engine, Idempotency Manager |
| **Entertainment** | SAG-AFTRA, DGA, CA Film Tax 4.0 | Crew Eligibility, Labor Compliance, PCOS Dashboard |
| **Finance** | SOX 404, GLBA, ISO 27001 | Internal Control Audits, Sales Velocity |
| **Food Safety** | FDA FSMA 204 | CTE/KDE Graph, Recall Propagation, FTL Checker |
| **Gaming** | FinCEN AML, Tribal Compacts | Transaction Vault, Responsible Gaming |
| **Healthcare** | HIPAA, HITECH, MSCF | Forensic PHI Engine, Chain of Trust Visualizer |
| **Manufacturing** | ISO 9001/14001/45001 | Triple-Cert Evidence Packs, NCR/CAPA Lifecycle |
| **Nuclear** | 10 CFR Part 21/50 | 60-Year Retention Vault, NRC Legal Hold |
| **Technology** | GDPR, SOC2 | Trust Center, Automated Evidence Capture |

### 5.1 The Food Safety Vertical (Flagship)

The FSMA 204 vertical is the most mature and serves as the commercial beachhead. Key concepts a designer should understand:

- **CTE** (Critical Tracking Event): A point in the supply chain where product changes hands (harvesting, shipping, receiving, transformation)
- **KDE** (Key Data Element): Data captured at each CTE (lot number, location, timestamp, temperature)
- **FTL** (Food Traceability List): The FDA's list of 23 food categories subject to FSMA 204
- **Recall propagation**: Given a contaminated lot, the system traverses the Neo4j graph upstream and downstream to identify every affected entity

---

## 6. Security Architecture

### 6.1 Authentication

| Mechanism | Used By | Details |
|-----------|---------|---------|
| **JWT (HS256 → RS256)** | Frontend users | Short-lived access tokens (15 min) + refresh tokens (7 days) with automatic rotation. Migration path to RS256 for external verification without sharing signing key. |
| **API Keys (SHA-256 hashed)** | API consumers | Scoped by tenant, rate-limited, with read/write/admin permission levels |
| **Service-to-Service (HMAC)** | Internal services | Short-lived service tokens (5 min) with circuit breakers and request signing via `X-RegEngine-Signature` + `X-RegEngine-Timestamp` headers |

### 6.2 Session Management

- Sessions stored in Redis (not database) for performance
- Refresh token rotation on every use (detects theft via revoked-session detection)
- Concurrent session limits per user (default: 5)
- User-agent and IP binding for session hijacking detection
- Automatic session expiry with configurable idle timeout

### 6.3 Key Management & Rotation

| Secret | Storage | Rotation | Compromise Response |
|--------|---------|----------|--------------------|
| `JWT_SECRET` | Environment variable (required — app fails to start if missing) | 90-day rotation target | Revoke all active tokens, force re-auth |
| `SERVICE_AUTH_SECRET` | Environment variable (required) | 90-day rotation target | Revoke service tokens, restart affected services |
| `SESSION_SECRET` | Environment variable (required) | On compromise | Invalidate all Redis sessions |
| API Keys | SHA-256 hashed in PostgreSQL, plaintext never stored | User-managed | Disable key, audit usage, issue replacement |

### 6.4 API Gateway

- **Nginx** handles rate limiting, CORS enforcement, and request routing
- All inter-service communication uses `X-Service-Token` headers with HMAC validation
- Auth test bypass tokens are gated to non-production environments only

### 6.5 Data Protection

- All compliance rows are immutable (DB-level trigger enforcement)
- PII is excluded from application logs (emails redacted from auth events)
- Error responses return generic messages (no stack traces, schema details, or file paths)
- All SQL queries use parameterized bindings (no string interpolation)
- Structured logging via `structlog` — no `print()` statements in production paths

---

## 7. Tech Stack Summary

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 15, TypeScript, TanStack Query, Lucide icons |
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy, Pydantic v2 |
| **Primary DB** | PostgreSQL 15+ (via Supabase) with RLS |
| **Graph DB** | Neo4j 5.x |
| **Cache/Sessions** | Redis |
| **Message Bus** | Redpanda (Kafka-compatible) |
| **Object Storage** | S3 (LocalStack in dev, AWS in prod) |
| **Gateway** | Nginx |
| **Containerization** | Docker Compose (17 containers in local stack) |
| **CI/CD** | GitHub Actions (4 workflows: Backend, Frontend, Security, Test Suite) |
| **Frontend Hosting** | Vercel |
| **Logging** | structlog (structured JSON logging) |

---

## 8. Key Design Patterns for Systems Designers

### 8.1 Shared Libraries Pattern

Common code (auth middleware, CORS, tenant context, health checks) lives in `services/graph/shared/` and is copied into each service's Docker build context. This avoids a monorepo package manager while ensuring consistency.

### 8.2 Vertical Isolation Pattern

Each vertical is implemented as either:
- **Routes within Admin API** (e.g., `/automotive/*`, `/healthcare/*`) for lightweight verticals
- **Standalone service** (e.g., Energy at `:8700`) for verticals requiring dedicated databases or heavy processing

### 8.3 Async Document Pipeline

```
Upload → Ingestion Service → Kafka Topic → NLP Consumer → Kafka Topic → Compliance Worker → DB + Graph
```

This decouples the upload response from processing — the user gets an immediate acknowledgment, and processing happens asynchronously with confidence-based routing (high confidence → auto-persist, low confidence → human review queue).

### 8.4 Immutable Append-Only Ledger

Compliance facts follow a strict pattern:
1. INSERT with computed hash (fact fields → SHA-256)
2. Link to previous record's hash (chain integrity)
3. No UPDATE or DELETE permitted (DB constraint)
4. Version management via `max(version) + 1` on the same entity

---

## 9. Business Model

| Tier | Price | Target |
|------|-------|--------|
| **Developer** | Free | Individual developers, testing |
| **Professional** | $499/mo | Mid-market food producers, single-vertical |
| **Enterprise** | $2,500+/mo | Large suppliers, multi-vertical, dedicated support |

**Key revenue mechanics**:
- **API consumption**: Metered ingestion and query calls
- **Label Generation API**: Physical QR label printing creates deep operational lock-in
- **Managed Ingestion**: White-glove data onboarding for enterprise customers
- **Vertical expansion**: Each new regulation a customer must comply with is an upsell

---

## 10. What Makes It Different

| Differentiator | Traditional GRC | RegEngine |
|---------------|-----------------|-----------|
| **Trust model** | "We followed the process" | "Here's the cryptographic proof" |
| **Data model** | Mutable database rows | Immutable hash-chained ledger |
| **Verification** | Internal audit team | Independent script anyone can run |
| **Multi-tenancy** | App-level filtering | Double-lock (App + DB RLS) |
| **Recall response** | Manual spreadsheet tracing | Graph traversal in seconds |
| **Regulatory coverage** | Single vertical | 12 industry verticals, shared platform |
| **Integration** | Portal-only | API-first with SDK |

---

## 11. Operational SLOs & Failure Modes

### 11.1 Service Level Objectives

| Metric | Target | Alert Threshold | Degradation Strategy |
|--------|--------|-----------------|---------------------|
| Ingestion latency | < 30s for docs < 10MB | > 60s | Queue prioritization, defer large docs |
| Verification latency | < 5s for chain verification | > 15s | Cache frequently requested chains |
| Dashboard freshness | Updates within 2 min of new data | > 10 min | Background refresh job priority boost |
| API availability | 99.9% uptime | 3+ failed health checks | Automatic container restart via Docker |

### 11.2 Known Failure Modes

| Failure | Detection | Response |
|---------|-----------|----------|
| **Kafka consumer lag** | Lag > 1,000 messages | Scale NLP consumers, pause low-priority ingestion |
| **NLP slowdown** | Processing time > 2× baseline | Route to review queue, alert ML team |
| **Poison messages** | 3 consecutive processing failures on same message | Send to Dead Letter Queue (DLQ) with error metadata |
| **Neo4j memory pressure** | Heap usage > 80% | Query timeout enforcement, cache eviction |
| **Redis session overflow** | Memory > 90% | Evict oldest idle sessions, alert ops |

### 11.3 Idempotency Strategy

Duplicate ingestion is prevented via three deduplication keys:
1. `document_sha256_hash` — exact content match
2. `source_uri + content_checksum` — same source, same content
3. `tenant_id + document_type + timestamp_window` — near-duplicate detection

---

## 12. What's Not in Scope

This section is critical for a systems designer to avoid over-promising or misunderstanding boundaries.

### 12.1 Legal vs. Compliance

- **Not legal advice**: RegEngine provides factual compliance evidence, not legal interpretation. It can prove a temperature was recorded at a CTE — it cannot advise whether that temperature is legally sufficient.
- **Regulatory coverage maturity varies**: Food Safety (FSMA 204) is production-grade. Nuclear and Aerospace are structurally complete but have not been validated with live customer data.

### 12.2 Data Immutability Boundaries

- **Immutability applies to compliance facts only** — user profiles, tenant settings, API keys, and audit log metadata are mutable.
- **NLP confidence is assistive, not authoritative** — scores between 0.0 and 1.0 indicate extraction confidence. Facts with confidence < 0.85 route to a human review queue, not auto-persist.

### 12.3 Infrastructure Boundaries

- **No external anchoring yet** — the hash chain is internally consistent but not anchored to an external ledger (blockchain, RFC 3161 timestamping). This is on the roadmap.
- **Single cloud provider** — designed for AWS (S3, Secrets Manager). Multi-cloud or on-prem deployment would require infrastructure adaptation.
- **Rate limiting** — currently enforced at the Nginx gateway layer. Per-endpoint, per-user rate limiting across all services is a planned infrastructure enhancement.

### 12.4 SOC 2 / ISO 27001 Compliance Mapping

| Control Area | Current Implementation | Evidence Available |
|-------------|----------------------|-------------------|
| Access Control | JWT + API Keys + HMAC + RLS | Key rotation logs, session audit trail |
| Cryptographic Protection | SHA-256 hash chains + TLS | `verify_chain.py` output |
| Audit Logging | Structured JSON logs + hash chains | Audit event table, log exports |
| Incident Response | Break-glass procedures, PII-free logs | Documented in security runbook |
| Data Integrity | Immutable ledger + DB triggers | Trigger definitions, constraint checks |

> **Note**: RegEngine is SOC 2-aligned in architecture but has not yet undergone formal SOC 2 Type II certification.

---

*This document is intended as a comprehensive reference for systems designers joining the RegEngine project. For specific implementation details, refer to the service-level README files in each `services/` subdirectory.*
