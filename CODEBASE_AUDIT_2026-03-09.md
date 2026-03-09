# RegEngine Codebase Audit Report
**Date**: March 9, 2026  
**Scope**: Database schema, infrastructure, Neo4j integration, background jobs, and security configuration  
**Status**: Comprehensive scan completed across all services

---

## 1. DATABASE SCHEMA

### SQLAlchemy Models Summary
**Primary Model File**: `/services/admin/app/sqlalchemy_models.py` (427 lines)

#### Tables Defined (13 total):
1. **tenants** - Multi-tenancy root of trust
   - Fields: id (UUID), name, slug (unique), status, settings (JSON)
   - Indexes: slug
   
2. **users** - Global user identity
   - Fields: id (UUID), email (unique), password_hash, mfa_secret, is_sysadmin, status
   - Indexes: email

3. **roles** - RBAC roles (system or custom per-tenant)
   - Fields: id (UUID), tenant_id (nullable), name, permissions (JSON list)
   
4. **memberships** - User-to-tenant-with-role mapping
   - Fields: user_id (FK), tenant_id (FK), role_id (FK), is_active, created_at, created_by
   - Constraints: Composite PK on (user_id, tenant_id)

5. **audit_logs** - Append-only tamper-evident audit trail (ISO 27001 12.4.1-12.4.3)
   - Fields: id (BigInt), tenant_id, timestamp, actor_id/email/ip/ua, event_type, action, severity, resource_type/id, metadata (JSON), prev_hash, integrity_hash
   - Constraints: No UPDATE/DELETE permitted
   - Implementation: Hash-chain integrity verification

6. **invites** - Pending user invitations
   - Fields: id (UUID), tenant_id (FK), email, role_id (FK), token_hash (unique), expires_at, revoked_at, accepted_at, created_at, created_by (FK)

7. **supplier_facilities** - Supplier-operated facilities for FSMA scoping
   - Fields: id (UUID), tenant_id (FK), supplier_user_id (FK), name, street, city, state, postal_code, fda_registration_number, roles (JSON)

8. **supplier_facility_ftl_categories** - FTL category assignments per facility
   - Fields: id (UUID), tenant_id (FK), facility_id (FK), category_id, category_name, required_ctes (JSON list)
   - Constraints: Unique (facility_id, category_id)

9. **supplier_traceability_lots** - Supplier-managed traceability lots (TLCs)
   - Fields: id (UUID), tenant_id (FK), supplier_user_id (FK), facility_id (FK), tlc_code, product_description, status
   - Constraints: Unique (tenant_id, tlc_code)

10. **supplier_cte_events** - Immutable CTE event log with Merkle hash chaining
    - Fields: id (UUID), tenant_id (FK), supplier_user_id (FK), facility_id (FK), lot_id (FK), cte_type, event_time, kde_data (JSON), payload_sha256, merkle_prev_hash, merkle_hash, sequence_number (BigInt), obligation_ids (JSON)
    - Constraints: Unique (tenant_id, sequence_number)

11. **supplier_funnel_events** - Lightweight onboarding funnel analytics
    - Fields: id (UUID), tenant_id (FK), supplier_user_id (FK), facility_id (FK, nullable), event_name, step, status, metadata (JSON)

12. **review_items** - Review queue items with tenant isolation
    - Fields: id (UUID), tenant_id (nullable), doc_hash, text_raw (Text), extraction (JSON), provenance (JSON), embedding (JSON), confidence_score, status, reviewer_id
    - Constraints: Unique (tenant_id, doc_hash, text_raw)

13. **sessions** - Stateful session tracking for refresh token rotation
    - Fields: id (UUID), user_id (FK), refresh_token_hash (unique), family_id, is_revoked, expires_at, created_at, last_used_at, user_agent, ip_address

#### Additional Vertical Models (Constitution 2.1):
- **vertical_projects** - Compliance projects per vertical (healthcare, finance, etc.)
- **vertical_rule_instances** - Per-project rule compliance tracking
- **evidence_logs** - Immutable Evidence Vault with SHA-256 hashing

#### Additional Service Models:
- **Compliance Service**: Fair lending regulation mapping, model registration, audit exports
- **Ingestion Service**: Document normalization, text extraction, discovery queues
- **Scheduler Service**: Enforcement items, scrape results, job executions, webhook payloads

### Migration Status
**Files**: 6 SQL migration files (758 total lines)  
**Current Approach**: Flyway-style versioned SQL (V### pattern)  
**Missing**: Alembic integration - No auto-migration between ORM models and schema  
**Risk**: Schema drift between Python models and database

---

## 2. INFRASTRUCTURE

### Dockerfiles (7 services)
- admin-api (port 8400), ingestion-service (8000), compliance-api (8500)
- graph-service (8200), nlp-service (8100), scheduler, compliance-worker
- All use Python 3.11-slim, non-root appuser (UID 1001), Railway-compatible dynamic PORT

### Docker Compose Files (5 total)
1. **docker-compose.yml** - Full dev stack (15+ services)
2. **docker-compose.prod.yml** - Minimal production (6 services with resource limits)
3. **docker-compose.monitoring.yml** - Prometheus + Grafana
4. **docker-compose.test.yml** - CI stub (incomplete)
5. **docker-compose.fsma.yml** - Minimal (unclear purpose)

### Environment Variables
**Critical Secrets** (production):
- OBJECT_STORAGE_ACCESS_KEY_ID/SECRET_ACCESS_KEY - S3/MinIO credentials
- NEO4J_PASSWORD - Graph database auth
- ADMIN_MASTER_KEY - API key (generate with openssl rand -hex 32)
- POSTGRES_PASSWORD - Database auth
- REGENGINE_INTERNAL_SECRET - Service-to-service trust
- SCHEDULER_API_KEY - Scheduler authentication

**Dev .env** (hardcoded, for dev only):
- MinIO: minioadmin/minioadmin123
- Neo4j: regengine_dev_secret
- Postgres: regengine/regengine
- Auth bypass: dev-bypass-token

---

## 3. NEO4J GRAPH DATABASE

### Supplier Graph Sync (`/services/admin/app/supplier_graph_sync.py`)
**Purpose**: Mirror supplier onboarding lineage into Neo4j (Postgres as source-of-truth)

**Key Operations**:
1. **record_invite_created()** - BuyerTenant -[:INVITED]-> PendingSupplierInvite
2. **record_invite_accepted()** - BuyerTenant -[:HAS_SUPPLIER_CONTACT]-> SupplierContact
3. **record_facility_ftl_scoping()** - Supplier -[:OPERATES]-> Facility -[:HANDLES]-> FTLCategory
4. **record_cte_event()** - CTE -[:FOR_LOT]-> TLC, CTE -[:SATISFIES]-> Obligation
5. **get_required_ctes_for_facility()** - Query facility CTEs

**Error Handling**: Best-effort with fallback to disabled state. Non-blocking failures.

**Node Types**: BuyerTenant, SupplierContact, SupplierFacility, FTLCategory, TLC, CTEEvent, Obligation, TenantControl, ControlMapping, CustomerProduct, Provision

---

## 4. BACKGROUND JOBS

### Scheduler Service (No Celery)
**Architecture**: Custom APScheduler-based scheduler

**Scheduled Jobs**:
1. FDA Warning Letters (60 min default)
2. FDA Import Alerts (120 min default)
3. FDA Recalls (30 min default)
4. Regulatory Discovery (24 hours default)

**Kafka Consumer**: compliance-worker processes schema-registry validated events

**Rate Limiting**: Redis-backed per-tenant/API-key rate limiting (100 req/min default)

**Circuit Breaker**: Custom implementation for redis, neo4j, kafka services

---

## 5. SECURITY AUDIT

### Authentication Methods
1. **API Key** - SHA-256 hashed, status tracking (ACTIVE/REVOKED/EXPIRED/SUSPENDED)
2. **JWT** - HS256, Refresh token family tracking
3. **OAuth2/Basic Auth** - Supported
4. **MFA** - Integrated

### Session Management
- Refresh token family ID for rotation
- is_revoked flag for proactive termination
- last_used_at tracking for idle timeout
- user_agent, ip_address logged

### Protected vs Public Endpoints

**Public Endpoints** (NO AUTH):
- /health - All services
- /metrics - All services  
- /docs, /redoc, /openapi.json

**Recommendation**: Protect /metrics in production (requires API key)

### CORS Configuration Issues
1. **Ingestion Service** (CRITICAL):
   - `allow_origins=["*"]` + `allow_credentials=True` (violates spec)
   
2. **Admin/Graph Services**:
   - `allow_headers=["*"]` (should restrict to specific headers)
   
3. **Graph Service** (BETTER):
   - Explicitly whitelists regengine.co, railway.app, vercel.app, localhost

**Recommendation**: Whitelist specific origins and headers for all services

### Security Headers
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- X-XSS-Protection: 1; mode=block
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy: Restrictive (no camera, geolocation, etc.)
- Content-Security-Policy: `default-src 'self'` with permitted exceptions
- Strict-Transport-Security: Optional (disabled in dev)

### Rate Limiting
- Backend: Redis (production), in-memory (dev)
- Per-tenant via TenantRateLimitMiddleware
- Headers: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset

### Hardcoded Secrets Check
**Dev Secrets Found** (expected for dev):
- Scripts with API_KEY="admin" (5 files in /scripts/)
- Docker compose: dev-bypass-token, minioadmin credentials
- .env file has hardcoded credentials

**Risk**: Low (dev only, .env should be in .gitignore)
**Mitigation**: Verify .env in .gitignore, use unique prod secrets in deployment

### Tenant Isolation
- Database: tenant_id in all tables + RLS policies
- Application: TenantContextMiddleware, get_current_tenant_id() dependency
- Graph: tenant_id in all Neo4j nodes, filtered in Cypher queries

---

## 6. UNUSED & ORPHANED CODE

### Non-Issues (Expected)
- Empty __init__.py files (proper package markers)
- Verticals subdirectories (__init__.py for energy, healthcare, finance, gaming, technology)

### Incomplete Services
- docker-compose.test.yml marked as "STUB: Not yet wired"
- Finance service removed/not yet implemented

### Placeholder Files
- /Postgres, /Neo4j, /Variables (empty marker files)

### No Unused Dependencies
All requirements.txt packages are actively imported

---

## 7. DEPLOYMENT & IaC

**Status**: Docker-only, no Terraform/Pulumi/CDK

**Platform**: Railway support (*.up.railway.app origins, dynamic PORT env var)

**Production Readiness Script**: `/scripts/verify_production_readiness.py`
- Rate limiting enforcement (Redis required)
- Auth secrets validation
- Database configuration checks
- Security headers verification

---

## 8. KEY FINDINGS

### STRENGTHS
1. Immutable hash-chained audit logs (ISO 27001)
2. Cryptographic integrity for CTEs and evidence
3. Proper multi-tenancy isolation (DB, app, graph)
4. Comprehensive security headers
5. Token rotation with family tracking
6. Per-tenant rate limiting

### CRITICAL ISSUES
1. **CORS Misconfiguration**
   - Ingestion: allow_origins=["*"] + allow_credentials=True
   - Fix: Whitelist specific origins/headers

2. **Missing Alembic Integration**
   - Manual SQL migration files only
   - Risk: Schema drift from ORM models
   - Fix: Implement Alembic for DDL management

3. **Public Metrics Endpoint**
   - /metrics exposed without auth
   - Fix: Require API key or restrict to internal network

### MEDIUM PRIORITY
1. No Celery/advanced task queue (custom APScheduler sufficient for current scope)
2. Neo4j sync is best-effort, no explicit retry policy
3. Missing TLS configuration (only nginx referenced)

### RECOMMENDATIONS
**Short-term**: Fix CORS, protect metrics, document Alembic plan
**Medium-term**: Implement Alembic, add TLS, document Neo4j resilience
**Long-term**: Service mesh (Istio), OpenTelemetry tracing, multi-region strategy

---

## 9. TABLE-TO-ENDPOINT MAPPING

**Finding**: All tables have API endpoints. No orphaned tables.

All 13 SQLAlchemy tables + 3 vertical tables are mapped to endpoints across:
- /v1/admin/* (tenants, users, roles, audit logs)
- /v1/supplier/* (facilities, lots, CTE events)
- /review/queue (review items)
- /admin/verticals/* (vertical projects, rules, evidence)
- Internal flows (sessions, invites)

---

**Audit Completed**: March 9, 2026  
**Next Review**: After major releases or quarterly security updates
