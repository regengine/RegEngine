# Migration Consolidation Plan

## Problem

Migrations are scattered across 4 directories with no runner enforcing order:

| Directory | Files | Notes |
|-----------|-------|-------|
| `migrations/` | V002, V036–V040 + 4 unnumbered | Root-level FSMA migrations |
| `services/admin/migrations/` | V1–V36 + 5 unnumbered | Admin service migrations |
| `services/compliance/migrations/` | (removed) | Legacy fair lending migration deleted |
| `services/ingestion/migrations/` | V001 | Ingestion bootstrap |

### Issues
- **No migration runner** — no Flyway, Alembic, or equivalent to enforce ordering
- **Overlapping version numbers** — V002 in `migrations/` vs V1–V36 in `admin/migrations/`
- **Unnumbered files** — `rls_migration_v1.sql`, `assessment_submissions.sql`, etc.
- **`Base.metadata.create_all()`** in `admin/database.py:init_db()` can conflict with SQL migrations
- **Schema conflicts** — e.g. `compliance_alerts` defined in both V002 and V31 (fixed by V038)

## Proposed Solution

1. **Adopt Alembic** as the single migration runner
2. **Consolidate** all SQL migrations into `migrations/` with a single global sequence
3. **Rename** admin migrations with a prefix (e.g., `V100__` through `V136__`) to avoid collisions
4. **Add checksum tracking** to detect manual edits to applied migrations
5. **Remove** `Base.metadata.create_all()` from `init_db()` — let Alembic own schema creation

## Estimated Effort
4–6 hours for initial consolidation + testing against a fresh database.

## Status
**Deferred** — tracked here for the next infrastructure sprint. The immediate schema conflict (compliance_alerts) is resolved by V038.
