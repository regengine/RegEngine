# RegEngine Migration Documentation

## Overview
RegEngine uses Flyway-style versioned SQL migrations across four independent databases. Each service owns its migration directory and executes sequentially on startup.

## Migration Directories

### 1. Root Migrations (`/migrations`)
**Database:** Core/shared PostgreSQL instance
**Count:** 12 files
**Execution Order:**
- V002__fsma_cte_persistence.sql
- V036__fsma_204_regulatory_seed_data.sql
- V037__obligation_cte_rules.sql
- V038__unify_compliance_alerts.sql
- V039__hash_chain_immutability.sql
- V040__obligation_cte_rules_rls_doc.sql
- V041__tenant_obligation_seeding_function.sql
- V042__tenant_feature_data_tables.sql
- assessment_submissions.sql
- finance_snapshots_dual_storage.sql
- rls_fix_namespace.sql
- rls_migration_v1.sql

**Status:** Active FSMA 204 infrastructure and compliance alerting

### 2. Admin Service (`/services/admin/migrations`)
**Database:** regengine_admin (PostgreSQL)
**Count:** 39 files (includes setup/verification scripts)
**Core Migrations (V1-V36):**
- V1__init_schema.sql (baseline schema)
- V3__tenant_isolation.sql (multi-tenancy)
- V6-V7__compliance_snapshots_and_status.sql
- V8__rls_fixes.sql
- V9__create_invites_table.sql
- V10-V11__membership_and_sessions.sql
- V12-V20__feature_expansion (budget, tax credit, forms, audit)
- V21__vertical_expansion.sql (PCOS vertical)
- V22__immutable_evidence_log.sql
- V23-V28__rls_security_hardening.sql
- V29__jwt_rls_integration.sql
- V30__audit_logs_tamper_evident.sql
- V31__fsma_204_infrastructure.sql
- V32__enforce_supplier_cte_sequence_uniqueness.sql
- V35__fix_audit_logs_constraints.sql
- V36__funnel_events.sql

**Note:** V25 migrated PCOS tables to Entertainment database (archived in Sprint 4)

### 3. Ingestion Service (`/services/ingestion/migrations`)
**Database:** regengine_ingestion (PostgreSQL)
**Count:** 1 file
**Migration:**
- V001__ingestion_schema.sql (data pipeline schema)

**Status:** Active, minimal changes post-baseline

### 4. Compliance Service (`/services/compliance/migrations`)
**Database:** regengine_compliance (PostgreSQL)
**Status:** Fair lending migration (V1) removed. FSMA compliance logic lives in ingestion service.

## Dependency Graph

```
Root Migrations
├── V002: FSMA CTE persistence baseline
├── V036-V042: FSMA 204 regulatory data & seeding
└── Additional: RLS and assessment infrastructure

Admin Migrations (Sequential execution required)
├── V1: Core schema & tenancy
├── V3: Tenant isolation
├── V6-V28: Feature and security iterations
├── V29: JWT/RLS integration
├── V30: Immutable audit logs
├── V31: FSMA 204 infrastructure
├── V32: Supplier CTE uniqueness constraints
└── V36: Funnel events

Ingestion Migrations
└── V001: Independent ingestion schema

Compliance Migrations
└── (cleared — FSMA compliance in ingestion service)
```

## Execution Model
- **Per-service:** Each service initializes its own migrations on startup
- **Sequence:** Migrations execute in numeric order within each service
- **Idempotency:** All migrations are idempotent (safe to re-run)
- **Cross-service:** No hard dependencies between services; loosely coupled via shared core migrations in `/migrations`

## Future: Alembic Migration to V2
Currently using Flyway-style manual migrations. For RegEngine V2:
- Migrate to **Alembic** (Python-native ORM migrations)
- Consolidate to single managed migration directory per service
- Enable programmatic schema generation from SQLAlchemy models
- Planned for post-FSMA 204 stabilization phase

## Notes
- Migrations are **never deleted**, only archived (see `_dead_code/`)
- Entertainment database (V25 in admin) is archived as of Sprint 4 Clean Architecture
- Non-FSMA schemas removed; FSMA 204 is the sole compliance vertical
