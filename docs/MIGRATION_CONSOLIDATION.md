# Migration Consolidation Plan

## Current State (3 parallel systems)

| System | Location | Count | Format |
|--------|----------|-------|--------|
| Alembic | `alembic/versions/` | 10 | Python, revision chain |
| Raw SQL (main) | `migrations/` | 28 | Flyway V-numbered |
| Raw SQL (admin) | `services/admin/migrations/` | 46 | Flyway V-numbered |

**Total: 84 migration files**, many with overlapping operations.

## Why Alembic Wins

- Alembic's baseline (`20260324_baseline_consolidate_v002_through_v042.py`) already consolidates the first 41 Flyway migrations
- Alembic has revision-chain integrity (down_revision links)
- Alembic supports both online (live DB) and offline (SQL script) modes
- Python migrations allow conditional logic (IF NOT EXISTS, data backfill)
- All new migrations since March 2026 are already Alembic

## What's Already Covered by Alembic

V002-V042 (baseline), V043-V050 (control plane + task queue), V051-V055 (RLS + tenant tables + indexes).

## What Needs Porting (raw SQL not yet in Alembic)

### High Priority — unique schema changes not in any Alembic migration

| File | Operation | Priority |
|------|-----------|----------|
| `V049__transformation_links_adjacency.sql` | Lot-to-lot ingredient traceability | HIGH |
| `V053__add_growing_cte_type.sql` | Add 'growing' to event_type CHECK | HIGH |
| `V057__ftl_cottage_cheese_exemption.sql` | FTL update | MEDIUM |
| `SQL_V048__rls_sysadmin_defense_in_depth.sql` | RLS hardening | HIGH |
| `SQL_V050__rls_reference_tables.sql` | RLS on reference tables | HIGH |
| `V054__rls_variable_standardization.sql` | Fix RLS variable names | CRITICAL |
| `V056__rls_obligations_and_ftl.sql` | Close last RLS gaps | HIGH |

### Already duplicated in Alembic (can skip)

| File | Covered by |
|------|-----------|
| `V043__canonical_traceability_events.sql` | Alembic 20260325 |
| `V044__versioned_rules_engine.sql` | Alembic 20260325 |
| `V045__exception_remediation_queue.sql` | Alembic 20260325 |
| `V046__request_response_workflow.sql` | Alembic 20260325 |
| `V047__identity_resolution.sql` | Alembic 20260325 |
| `V052__ensure_tenant_tables.sql` | Alembic 20260411 V052 |
| `V052__cte_events_composite_idempotency_key.sql` | Alembic 20260411 V052 |

### Admin migrations — disposition

- **V1-V35**: Core admin schema. These run against `ADMIN_DATABASE_URL` (separate DB). Keep as-is until admin DB is merged into main DB during monolith consolidation.
- **V36-V40**: Funnel events, password reset, tool leads, supplier portal, PCOS removal. Same — admin-DB-scoped.

## Execution Plan

### Phase 1: Port remaining raw SQL to Alembic (1 day)
Create 3 new Alembic migrations:
1. `20260415_rls_hardening_v056.py` — combines SQL_V048, SQL_V050, V054, V056
2. `20260415_transformation_links_v057.py` — ports V049
3. `20260415_schema_updates_v058.py` — ports V053, V057

### Phase 2: Validate against real database (half day)
```bash
# Against a fresh database
alembic upgrade head

# Against an existing database (stamp first)
alembic stamp head  # if migrations were already applied via Flyway
```

### Phase 3: Remove raw SQL directory (after validation)
- Delete `migrations/` directory
- Update `Dockerfile` (already done — only copies `alembic/`)
- Update `scripts/run-migrations.sh` to use `alembic upgrade head` only

### Phase 4: Admin DB merge (deferred to monolith consolidation)
- Port admin V1-V40 into main Alembic chain
- Requires merging `ADMIN_DATABASE_URL` into `DATABASE_URL`
- Depends on monolith consolidation completing first

## Status

- [x] Phase 1: Port remaining raw SQL to Alembic (3 migrations created, April 15 2026)
- [x] Phase 2: Validate against real database (Supabase, alembic upgrade head passes)
- [x] Phase 3: Remove raw SQL directory (`migrations/` deleted)
- [ ] Phase 4: Admin DB merge (deferred to monolith consolidation)
