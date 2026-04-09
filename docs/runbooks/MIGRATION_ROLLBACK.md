# Migration Rollback Runbook

**Severity:** SEV2 (failed migration blocks deploys) / SEV1 (partial migration corrupted data)
**Owner:** On-call engineer
**Last Updated:** 2026-04-08

> **Before you do anything:** Determine which migration system was involved.
> RegEngine has **two** systems running against the **same** database.
> Getting this wrong means rolling back the wrong thing (or nothing).

---

## Table of Contents

1. [The Dual Migration System](#1-the-dual-migration-system)
2. [Phase 1: Identify What Failed](#2-identify-what-failed)
3. [Phase 2: Assess the Damage](#3-assess-the-damage)
4. [Phase 3: Rollback — Alembic Migrations](#4-rollback-alembic)
5. [Phase 4: Rollback — Raw SQL Migrations](#5-rollback-raw-sql)
6. [Phase 5: Handle Partial State](#6-partial-state)
7. [Phase 6: Verify Data Integrity After Rollback](#7-verify-integrity)
8. [Phase 7: Re-attempt After Fixing](#8-reattempt)
9. [Irreversible Migrations](#9-irreversible)
10. [Migration Inventory & Risk Classification](#10-inventory)
11. [Reference](#11-reference)

---

## 1. The Dual Migration System

### System A: Alembic (Primary — Managed)

| Property | Value |
|----------|-------|
| Config | `alembic.ini`, `alembic/env.py` |
| Migration files | `alembic/versions/*.py` |
| Tracking table | `public.alembic_version` (single row with current `version_num`) |
| Runner | `alembic upgrade head` via `scripts/run-migrations.sh` |
| Rollback command | `alembic downgrade <revision>` |
| Connection | `DATABASE_URL` env var → Supabase PostgreSQL |
| ORM metadata | `services/admin/app/sqlalchemy_models.Base.metadata` |

Alembic wraps the raw SQL files — each Alembic revision reads its corresponding SQL files from `migrations/` and executes them within an Alembic-managed transaction.

**Revision chain:**
```
97588ba8edf3  — Baseline (V002–V042: CTE persistence, regulatory seed data, compliance alerts, hash chain, organizations, tenant features)
     |
a1b2c3d4e5f6  — Compliance Control Plane (V043–V047: canonical events, rules engine, exception queue, request workflow, identity resolution)
     |
b2c3d4e5f6a7  — Operational Hardening (V048: SLA tracking, chain verification log)
     |
c3d4e5f6a7b8  — Audit Trail (V049: fsma_audit_trail table)
     |
d4e5f6a7b8c9  — Task Queue (V050: pg_notify task queue replacing Kafka)
     |
e5f6a7b8c9d0  — RLS Hardening (V051: tenant table RLS + sysadmin defense-in-depth + reference table RLS)
```

### System B: Raw SQL (Legacy — Stateless)

| Property | Value |
|----------|-------|
| Migration files | `migrations/*.sql` (numbered V002–V053) |
| Service-level files | `services/admin/migrations/V1–V27.sql`, `services/ingestion/migrations/V001.sql` |
| Tracking | **None.** No tracking table. Applied via `psql -f` with `ON_ERROR_STOP=1`. |
| Runner | `scripts/railway/apply_sql_migrations.sh` |
| Rollback | **Manual.** No automated down migration. |
| Connection | `$DATABASE_URL` or `$ADMIN_DATABASE_URL` passed to `psql` |

The raw SQL runner (`apply_sql_migrations.sh`) applies files in sort order with `psql -v ON_ERROR_STOP=1`. It has **no state tracking** — it doesn't know which migrations have already been applied. Files with `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` are idempotent; others are not.

### How They Overlap

The Alembic revisions **embed** the raw SQL files. For example, revision `97588ba8edf3` reads and executes `V002.sql` through `V042.sql`. This means:

- If you applied migrations via Alembic, the SQL files were already executed.
- If you applied SQL files directly via `psql`, Alembic doesn't know — `alembic_version` won't reflect this.
- Files `V052__cte_events_composite_idempotency_key.sql` and `V053__add_growing_cte_type.sql` exist as raw SQL only — they are NOT wrapped in any Alembic revision yet.

---

## 2. Phase 1: Identify What Failed

### 2.1 Check Alembic State

```bash
# What revision is the database at?
alembic current
# Output example: e5f6a7b8c9d0 (head)

# What's the full revision history?
alembic history --verbose

# Is the database at head?
alembic check
# "No new upgrade operations detected" = at head
```

If `alembic current` returns nothing, Alembic has never managed this database (check if SQL files were applied directly).

### 2.2 Check Alembic Version Table Directly

```sql
SELECT version_num FROM alembic_version;
-- Single row. If empty or table doesn't exist, Alembic isn't tracking this DB.
```

### 2.3 Check Which Tables Actually Exist

```sql
-- FSMA schema tables (created by both Alembic and raw SQL)
SELECT tablename FROM pg_tables
WHERE schemaname = 'fsma'
ORDER BY tablename;

-- Admin tables (created by admin service migrations or ORM)
SELECT tablename FROM pg_tables
WHERE schemaname = 'public'
  AND tablename NOT LIKE 'pg_%'
ORDER BY tablename;

-- Audit schema (created by V051/SQL_V048)
SELECT tablename FROM pg_tables
WHERE schemaname = 'audit'
ORDER BY tablename;
```

### 2.4 Determine Which System Applied the Failed Migration

| Clue | System A (Alembic) | System B (Raw SQL) |
|------|--------------------|--------------------|
| Error came from `alembic upgrade head` | Yes | No |
| Error came from `psql -f migrations/V0XX.sql` | No | Yes |
| Error came from `apply_sql_migrations.sh` | No | Yes |
| `alembic_version` row matches a revision before the failure | Yes | No |
| Error references a file in `alembic/versions/` | Yes | No |
| Error references a file in `migrations/` or `services/*/migrations/` | Could be either | Yes if applied directly |
| Error occurred during Railway deployment | Check `run-migrations.sh` output — Alembic | Depends on deploy script |

---

## 3. Phase 2: Assess the Damage

### 3.1 Did the Migration Partially Apply?

Alembic runs each revision in a transaction. If the migration fails mid-execution, PostgreSQL should roll back the entire transaction. **However**, there are exceptions:

| Statement Type | Transactional? | Risk If Failed Midway |
|---------------|---------------|----------------------|
| `CREATE TABLE` | Yes | Rolled back cleanly |
| `CREATE INDEX` | Yes | Rolled back cleanly |
| `ALTER TABLE ADD COLUMN` | Yes | Rolled back cleanly |
| `CREATE INDEX CONCURRENTLY` | **No** — cannot run inside a transaction | Orphaned partial index |
| `INSERT` (seed data) | Yes | Rolled back cleanly |
| `CREATE POLICY` | Yes | Rolled back cleanly |
| `CREATE ROLE` | **Partially** — role creation commits immediately in some cases | Orphaned role |
| `CREATE SCHEMA` | Yes | Rolled back cleanly |
| Trigger/function creation | Yes | Rolled back cleanly |

**The raw SQL runner** (`apply_sql_migrations.sh`) runs each FILE through `psql -v ON_ERROR_STOP=1`. If a file has its own `BEGIN`/`COMMIT`, it's transactional. If not, each statement commits independently, and a failure mid-file leaves a partial state.

### 3.2 Check for Partial State

```sql
-- Tables that exist but might be incomplete
SELECT schemaname, tablename
FROM pg_tables
WHERE schemaname IN ('fsma', 'audit', 'public')
ORDER BY schemaname, tablename;

-- Indexes that might be orphaned from a failed CONCURRENTLY operation
SELECT schemaname, indexname, indexdef
FROM pg_indexes
WHERE NOT pg_index_from_table(indexrelid)  -- invalid indexes
  AND schemaname IN ('fsma', 'audit');

-- RLS policies that might be partially applied
SELECT schemaname, tablename, policyname, cmd, qual
FROM pg_policies
WHERE schemaname IN ('fsma', 'audit', 'public')
ORDER BY schemaname, tablename;

-- Check for the regengine_sysadmin role (created by V051)
SELECT rolname, rolcanlogin, rolinherit
FROM pg_roles
WHERE rolname = 'regengine_sysadmin';
```

### 3.3 Classify the Failure

| Situation | Severity | Next Step |
|-----------|----------|-----------|
| Alembic failed, transaction rolled back cleanly | Low | Fix the SQL, re-attempt |
| Raw SQL failed mid-file, no `BEGIN`/`COMMIT` wrapper | Medium | Determine partial state, manual cleanup |
| Migration applied to Supabase but Alembic version not updated | Medium | Stamp Alembic to correct revision |
| Raw SQL V052/V053 applied but Alembic doesn't know | Low | These are additive — stamp or ignore |
| RLS policy migration failed partially | **High** | Tenant isolation may be broken — verify immediately |
| Data migration (V036 seed data) failed partially | Medium | Seed data may be incomplete |

---

## 4. Phase 3: Rollback — Alembic Migrations

### 4.1 Rollback to a Specific Revision

```bash
# Rollback one revision
alembic downgrade -1

# Rollback to a specific revision
alembic downgrade <target_revision>

# Rollback to the baseline (WARNING: drops all tables from V043+)
alembic downgrade 97588ba8edf3

# Full rollback (WARNING: drops EVERYTHING — total data loss)
alembic downgrade base
```

### 4.2 What Each Downgrade Does

Every Alembic revision has a `downgrade()` function. Here's what each drops:

| Revision | Downgrade Action | Data Loss? |
|----------|-----------------|------------|
| `e5f6a7b8c9d0` → `d4e5f6a7b8c9` | Drops RLS policies from 8 tenant tables, drops sysadmin role/triggers/audit schema, drops reference table RLS | **No data loss** — only policy/role removal. **But tenant isolation is disabled.** |
| `d4e5f6a7b8c9` → `c3d4e5f6a7b8` | Drops `fsma.task_queue` table, notify trigger, function | **Loses queued tasks** (pending/processing) |
| `c3d4e5f6a7b8` → `b2c3d4e5f6a7` | Drops `fsma.fsma_audit_trail` table | **Loses persistent audit trail entries** |
| `b2c3d4e5f6a7` → `a1b2c3d4e5f6` | Drops `fsma.fda_sla_requests` and `fsma.chain_verification_log` | **Loses SLA tracking and verification history** |
| `a1b2c3d4e5f6` → `97588ba8edf3` | Drops V043–V047 tables: `traceability_events`, `ingestion_runs`, `evidence_attachments`, `rule_definitions`, `rule_evaluations`, `rule_audit_log`, `exception_cases`, `exception_comments/attachments/signoffs`, `request_cases`, `response_packages`, `submission_log`, `request_signoffs`, `canonical_entities`, `entity_aliases`, `entity_merge_history`, `identity_review_queue` | **MASSIVE data loss.** All canonical events, rule evaluations, exception cases, request workflows, identity resolution data. **Do NOT downgrade past this point unless you are willing to lose everything from the compliance control plane.** |
| `97588ba8edf3` → `base` | Drops ALL FSMA tables: `cte_events`, `cte_kdes`, `hash_chain`, `compliance_alerts`, `fda_export_log`, plus regulatory seed data, obligation rules, organizations, tenant feature tables | **TOTAL data loss.** Everything. |

### 4.3 Verify After Alembic Rollback

```bash
# Confirm the current revision
alembic current

# Confirm the database state matches
alembic check
```

```sql
-- Verify alembic_version matches your expectation
SELECT version_num FROM alembic_version;
```

---

## 5. Phase 4: Rollback — Raw SQL Migrations

Raw SQL migrations have **no automated rollback**. You must reverse them manually.

### 5.1 Additive Schema Migrations (Safe to Reverse)

These create new tables or add columns. Rollback = drop what was created.

**V052 — Composite idempotency key:**
```sql
-- Reverse: restore single-column constraint, drop composite
ALTER TABLE fsma.cte_events
    DROP CONSTRAINT IF EXISTS cte_events_tenant_idempotency_key;

-- Re-add the original single-column unique (if it existed before V052)
-- Note: the original was named cte_events_idempotency_key_key (auto-generated)
ALTER TABLE fsma.cte_events
    ADD CONSTRAINT cte_events_idempotency_key_key UNIQUE (idempotency_key);
```

**V053 — Add growing CTE type:**
```sql
-- Check what V053 actually changed
-- If it added 'growing' to a CHECK constraint, reverse:
ALTER TABLE fsma.cte_events
    DROP CONSTRAINT IF EXISTS cte_events_event_type_check;
ALTER TABLE fsma.cte_events
    ADD CONSTRAINT cte_events_event_type_check
    CHECK (event_type IN (
        'harvesting', 'cooling', 'initial_packing',
        'shipping', 'receiving', 'transformation'
    ));
-- WARNING: This will fail if any rows already have event_type = 'growing'.
-- You must update or supersede those rows first (see BULK_DATA_REPAIR.md).
```

### 5.2 RLS Migrations (Dangerous to Reverse)

These standalone SQL files may have been applied directly outside Alembic:

**`rls_migration_v1.sql`** — Original RLS policies on core tables:
```sql
-- Reverse: disable RLS on each table
-- WARNING: This removes ALL tenant isolation from these tables.
-- Only do this if you are immediately going to re-apply corrected policies.
ALTER TABLE tenants DISABLE ROW LEVEL SECURITY;
ALTER TABLE organizations DISABLE ROW LEVEL SECURITY;
ALTER TABLE memberships DISABLE ROW LEVEL SECURITY;
ALTER TABLE users DISABLE ROW LEVEL SECURITY;
-- ... (check the file for the complete list)
```

**`rls_fix_namespace.sql`** — Namespace fix for RLS helper functions:
```sql
-- This is typically safe to leave in place.
-- Only reverse if the function is causing errors.
```

**`SQL_V048__rls_sysadmin_defense_in_depth.sql`** — Now consolidated into Alembic V051.
**`SQL_V049__rls_obligations_and_ftl.sql`** — Now consolidated into Alembic V051.
**`SQL_V050__rls_reference_tables.sql`** — Now consolidated into Alembic V051.

If these were applied via `psql` (not via Alembic V051), reversing them requires manually dropping each policy and trigger. Use the V051 `downgrade()` function as a reference for the exact DROP statements.

### 5.3 Admin Service Migrations

Located in `services/admin/migrations/`. These target the admin database (which may be the same Supabase instance or a separate one):

```bash
# These were historically applied via:
scripts/railway/apply_sql_migrations.sh "$ADMIN_DATABASE_URL" services/admin/migrations
```

There is no automated rollback. Each must be reversed manually. The most critical ones:

| File | Creates | Reversible? |
|------|---------|-------------|
| `V1__init_schema.sql` | Core tables (tenants, users, memberships, etc.) | **Only on empty database** |
| `V12__production_compliance_init.sql` | Compliance tables | Yes (DROP TABLE) |
| `V18__audit_provenance_tables.sql` | Audit trail tables | Yes (DROP TABLE) but **loses audit data** |
| `V22__immutable_evidence_log.sql` | Evidence log table | Yes (DROP TABLE) but **loses evidence data** |
| `V24__remove_duplicate_compliance_snapshots.sql` | **Data migration** — removes duplicates | **IRREVERSIBLE** — deleted rows cannot be recovered |
| `V25__migrate_pcos_to_entertainment_db.sql` | **Data migration** — moves data between databases | **IRREVERSIBLE** without backup |

---

## 6. Phase 5: Handle Partial State (One System Applied, Other Didn't)

### Scenario A: Alembic Applied, Raw SQL Didn't

This happens when Alembic's revision wraps SQL files and succeeds, but a standalone SQL migration (V052, V053, RLS scripts) was supposed to run separately and wasn't.

**Diagnosis:**
```sql
-- Check Alembic state
SELECT version_num FROM alembic_version;
-- If this shows the latest revision, Alembic is fine

-- Check if V052/V053 tables/constraints exist
SELECT conname FROM pg_constraint
WHERE conrelid = 'fsma.cte_events'::regclass
  AND conname LIKE '%idempotency%';
-- If cte_events_tenant_idempotency_key exists → V052 was applied
-- If only cte_events_idempotency_key_key exists → V052 was NOT applied
```

**Fix:** Apply the missing SQL migration:
```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/V052__cte_events_composite_idempotency_key.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/V053__add_growing_cte_type.sql
```

### Scenario B: Raw SQL Applied, Alembic Doesn't Know

This happens when someone applied SQL files directly via `psql` without going through Alembic.

**Diagnosis:**
```bash
alembic current
# Shows an older revision than expected, even though the tables exist
```

**Fix:** Stamp Alembic to the correct revision:
```bash
# If all migrations through V051 are applied in the database:
alembic stamp e5f6a7b8c9d0

# If only through V047 (compliance control plane):
alembic stamp a1b2c3d4e5f6
```

> **Do NOT run `alembic upgrade head` if the tables already exist.** The SQL uses `CREATE TABLE IF NOT EXISTS`, but some operations (constraints, triggers, policies) are not idempotent. Stamp first, then upgrade.

### Scenario C: Alembic Failed Mid-Revision, Transaction Rolled Back, But One Table Was Created

This shouldn't happen with Alembic's transaction management, but can occur if:
- The migration uses `CREATE INDEX CONCURRENTLY` (can't run in a transaction)
- The `op.execute()` call ran DDL that auto-committed

**Diagnosis:**
```sql
-- Find tables that exist but shouldn't (based on where the revision stopped)
-- Compare against the _SQL_FILES list in the Alembic revision
SELECT tablename FROM pg_tables WHERE schemaname = 'fsma'
EXCEPT
SELECT tablename FROM (VALUES
    -- Tables that should exist at the current Alembic revision:
    ('cte_events'), ('cte_kdes'), ('hash_chain'), ('compliance_alerts'),
    ('fda_export_log')  -- ... add tables for your current revision
) AS expected(tablename);
```

**Fix:** Drop the orphaned objects, then re-attempt:
```sql
-- Drop the partially-created table
DROP TABLE IF EXISTS fsma.<orphaned_table> CASCADE;
```

### Scenario D: V041 Dual File Conflict

There are TWO files with the V041 prefix:
- `V041__extend_organizations_schema.sql`
- `V041__tenant_obligation_seeding_function.sql`

The raw SQL runner sorts by filename, so `extend_organizations` runs before `tenant_obligation_seeding`. But only one can match the "V041" version slot. If one was applied and the other wasn't:

```sql
-- Check if organizations schema was extended
SELECT column_name FROM information_schema.columns
WHERE table_name = 'organizations' AND table_schema = 'fsma'
ORDER BY ordinal_position;

-- Check if the tenant obligation seeding function exists
SELECT proname FROM pg_proc
WHERE proname LIKE '%seed%obligation%' OR proname LIKE '%obligation%seed%';
```

**Fix:** Apply the missing file manually.

---

## 7. Phase 6: Verify Data Integrity After Rollback

### 7.1 Hash Chain Verification

Any rollback that touches `fsma.cte_events`, `fsma.hash_chain`, or `fsma.traceability_events` requires a chain integrity check:

```python
from shared.cte_persistence import CTEPersistence
from shared.database import SessionLocal

session = SessionLocal()
persistence = CTEPersistence(session)

# Get all tenants
tenants = session.execute(text(
    "SELECT DISTINCT tenant_id FROM fsma.cte_events"
)).fetchall()

for (tenant_id,) in tenants:
    result = persistence.verify_chain(tenant_id=str(tenant_id))
    if not result.valid:
        print(f"BROKEN CHAIN for tenant {tenant_id}: {result.errors}")
    else:
        print(f"OK: tenant {tenant_id}, chain length {result.chain_length}")
session.close()
```

### 7.2 RLS Verification

Any rollback that touches RLS policies requires immediate tenant isolation verification:

```sql
-- Check RLS is enabled on all critical tables
SELECT schemaname, tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'fsma'
ORDER BY tablename;
-- rowsecurity should be 'true' for all tenant-scoped tables

-- Test isolation: set tenant context and verify no cross-tenant leakage
SET ROLE regengine;
SELECT set_config('regengine.tenant_id', '<tenant_A_id>', true);

-- This MUST return 0
SELECT count(*) FROM fsma.cte_events
WHERE tenant_id != '<tenant_A_id>'::uuid;

RESET ROLE;
```

### 7.3 Referential Integrity

```sql
-- Foreign key violations (tables that reference dropped objects)
SELECT tc.table_schema, tc.table_name, tc.constraint_name,
       ccu.table_schema AS ref_schema, ccu.table_name AS ref_table
FROM information_schema.table_constraints tc
JOIN information_schema.constraint_column_usage ccu
    ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema IN ('fsma', 'public', 'audit')
  AND NOT EXISTS (
      SELECT 1 FROM pg_tables
      WHERE tablename = ccu.table_name
        AND schemaname = ccu.table_schema
  );
-- Should return 0 rows. Any results = dangling foreign keys.
```

### 7.4 Application Health Check

After any rollback, verify all services can start and connect:

```bash
# Check each service health endpoint
curl http://localhost:8400/health  # Admin
curl http://localhost:8000/health  # Ingestion
curl http://localhost:8500/health  # Compliance

# Run the core test suites
pytest tests/data_integrity/ -v
pytest tests/security/test_tenant_isolation.py -v
```

---

## 8. Phase 7: Re-attempt After Fixing

### 8.1 Fix the Migration

Common fixes:

| Error | Fix |
|-------|-----|
| `relation already exists` | Add `IF NOT EXISTS` to `CREATE TABLE` |
| `column already exists` | Wrap in `DO $$ ... IF NOT EXISTS ... END $$` |
| `duplicate key value` (seed data) | Add `ON CONFLICT DO NOTHING` to `INSERT` |
| `permission denied` | Check role — may need `SET ROLE postgres` or correct grants |
| `function get_tenant_context() does not exist` | Apply RLS helper function migration first |
| `type check violation` | Data in the table doesn't match the new constraint — fix data first |

### 8.2 Re-attempt via Alembic

```bash
# After fixing the migration file:
alembic upgrade head

# If you need to re-run a specific revision:
alembic upgrade <target_revision>
```

### 8.3 Re-attempt via Raw SQL

```bash
# After fixing the SQL file:
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/<fixed_file>.sql
```

### 8.4 After Successful Re-attempt

```bash
# Verify Alembic state
alembic current
alembic check

# Run health checks
pytest tests/data_integrity/ -v

# If this was a production rollback+re-attempt, run the full E2E test
pytest tests/test_e2e_fda_request.py -v
```

---

## 9. Irreversible Migrations

Some migrations make changes that cannot be undone without a backup.

### Schema Migrations (Reversible)

These create or alter structure. Rollback = drop the structure. Safe as long as you accept losing data in the affected tables.

### Data Migrations (Irreversible Without Backup)

| Migration | What It Does | Why Irreversible |
|-----------|-------------|------------------|
| `V036__fsma_204_regulatory_seed_data.sql` (77KB) | Inserts 78+ FDA/FSMA obligations, obligation-CTE rules, food traceability list categories | If rolled back (DELETE), the seed data is gone. Re-applying re-inserts, but any tenant-specific modifications to obligation records are lost. |
| `V037__obligation_cte_rules.sql` (28KB) | Inserts rule definitions for each CTE type | Same — rule customizations lost on rollback. |
| `V041__tenant_obligation_seeding_function.sql` | Creates a function that seeds obligations per tenant | Function is reversible, but any tenant data it already seeded is not (without re-running). |
| `V024__remove_duplicate_compliance_snapshots.sql` (admin) | Deletes duplicate rows | **Truly irreversible** — deleted rows are gone. |
| `V025__migrate_pcos_to_entertainment_db.sql` (admin) | Moves data between databases | **Truly irreversible** — source data deleted after copy. |

### RLS Policy Migrations (Reversible but Dangerous)

| Migration | Risk if Reversed |
|-----------|-----------------|
| `rls_migration_v1.sql` | Disabling RLS = no tenant isolation. Any query returns all tenants' data. |
| `SQL_V048__rls_sysadmin_defense_in_depth.sql` | Removing sysadmin audit triggers = no logging of admin bypass. |
| `V051 (Alembic e5f6a7b8c9d0)` | Reverses RLS on 8 tenant tables + reference tables + sysadmin hardening. Multi-surface tenant isolation regression. |

### Hash Chain Immutability (V039)

`V039__hash_chain_immutability.sql` adds protections to the hash chain table. **If rolled back**, the hash chain loses its immutability guarantees — UPDATE and DELETE become possible, which undermines the entire tamper-evident audit trail.

```sql
-- Check if V039 protections are in place
SELECT tgname FROM pg_trigger
WHERE tgrelid = 'fsma.hash_chain'::regclass;
-- Should include immutability trigger(s)
```

### Supabase Point-in-Time Recovery

If you need to reverse an irreversible data migration, Supabase provides point-in-time recovery (PITR):

1. Go to Supabase Dashboard → Database → Backups
2. Select a recovery point **before** the migration was applied
3. Restore to a new project (does NOT overwrite current)
4. Extract the needed data from the restored database
5. Apply it to the current database

**Recovery objectives from `docs/DISASTER_RECOVERY.md`:**
- RPO: 15 minutes (Supabase WAL archiving)
- RTO: 4 hours target, 8 hours maximum

---

## 10. Migration Inventory & Risk Classification

### Alembic-Managed Revisions

| Revision | Name | SQL Files | Type | Rollback Risk |
|----------|------|-----------|------|---------------|
| `97588ba8edf3` | Baseline (V002–V042) | 8 files | Schema + Data | **Extreme** — drops all FSMA tables |
| `a1b2c3d4e5f6` | Control Plane (V043–V047) | 5 files | Schema + RLS | **Extreme** — drops canonical events, rules, requests |
| `b2c3d4e5f6a7` | Ops Hardening (V048) | Inline | Schema + RLS | Low — drops SLA tracking and chain verification log |
| `c3d4e5f6a7b8` | Audit Trail (V049) | Inline | Schema + RLS | Medium — loses persistent audit trail |
| `d4e5f6a7b8c9` | Task Queue (V050) | Inline | Schema + Trigger | Low — loses queued tasks, removes pg_notify |
| `e5f6a7b8c9d0` | RLS Hardening (V051) | Inline | RLS + Roles | **High** — disables tenant isolation on 20+ tables |

### Raw SQL Only (Not in Alembic)

| File | Type | Rollback Risk |
|------|------|---------------|
| `V052__cte_events_composite_idempotency_key.sql` | Schema (constraint change) | Low — restore original constraint |
| `V053__add_growing_cte_type.sql` | Schema (CHECK constraint) | Medium — must handle existing 'growing' events first |
| `rls_migration_v1.sql` | RLS | **High** — disables tenant isolation |
| `rls_fix_namespace.sql` | RLS helper function | Low |
| `assessment_submissions.sql` | Schema | Low |
| `finance_graph_schema.cypher` | Neo4j (not PostgreSQL) | N/A for PostgreSQL rollback |
| `finance_snapshots_dual_storage.sql` | Schema | Low |

### Admin Service Migrations

| Range | Type | Rollback Risk |
|-------|------|---------------|
| `V1–V9` | Core schema (tenants, users, memberships) | **Extreme** — application can't function |
| `V10–V17` | Feature tables (memberships, compliance, tax, forms) | Medium |
| `V18–V22` | Audit, provenance, evidence | Medium — data loss |
| `V23–V27` | Cleanup, data migrations, deprecations | **Irreversible** (V24, V25) |

---

## 11. Reference

### Commands Quick Reference

```bash
# Alembic
alembic current                           # Show current revision
alembic history --verbose                 # Full revision chain
alembic check                             # Verify at head
alembic upgrade head                      # Apply all pending
alembic upgrade <revision>                # Apply up to specific revision
alembic downgrade -1                      # Roll back one step
alembic downgrade <revision>              # Roll back to specific revision
alembic stamp <revision>                  # Mark DB as being at revision (no DDL)
alembic stamp head                        # Mark DB as fully migrated (no DDL)

# Raw SQL
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f <file.sql>
bash scripts/railway/apply_sql_migrations.sh "$DATABASE_URL" migrations "V*.sql"

# Migration runner (handles Alembic stamp/upgrade logic)
DATABASE_URL=<url> ./scripts/run-migrations.sh
```

### Key Files

| File | Role |
|------|------|
| `alembic.ini` | Alembic configuration (script location, logging) |
| `alembic/env.py` | Database connection (reads `DATABASE_URL`), ORM metadata |
| `alembic/versions/*.py` | Alembic revisions with `upgrade()` and `downgrade()` functions |
| `migrations/*.sql` | Raw SQL migration source files |
| `services/admin/migrations/*.sql` | Admin service schema migrations |
| `services/ingestion/migrations/V001.sql` | Ingestion service bootstrap |
| `scripts/run-migrations.sh` | Idempotent Alembic runner (stamp if needed, then upgrade) |
| `scripts/railway/apply_sql_migrations.sh` | Raw SQL runner (psql with ON_ERROR_STOP) |
| `scripts/utilities/deploy_migrations.py` | Legacy deployment script for specific migrations |
| `scripts/deploy_rls.sh` / `scripts/deploy_rls.py` | RLS deployment helpers |
| `migrations/CONSOLIDATION_PLAN.md` | Plan to merge dual system into Alembic-only |

### Related Runbooks

- [BULK_DATA_REPAIR.md](BULK_DATA_REPAIR.md) — Repairing data corrupted by a bad migration
- [FDA_RECALL_RESPONSE.md](FDA_RECALL_RESPONSE.md) — If migration failure impacts recall capability
- [incident-response.md](incident-response.md) — Escalation paths
- [disaster-recovery.md](disaster-recovery.md) — Supabase PITR for irreversible damage
