# Archived migration files (WS-2)

Historical SQL preserved for reference — **nothing in this directory is
executable**. The Railway deploy runs Alembic only (`alembic upgrade head`).

## Why these files are here

`alembic/sql/` holds the legacy Flyway-style SQL that live Alembic revisions
still execute at `upgrade()` time (the baseline `97588ba8edf3` and the
control-plane revisions read them with `op.execute`). Files in that directory
must therefore be referenced by at least one revision — a CI guard
(`scripts/check_orphan_migrations.py`) enforces this in both directions:
no unreferenced file may sit in `alembic/sql/`, and referenced files cannot
be deleted without breaking the guard.

The files below were **companion/superseded copies** referenced by no
revision. Each one's DDL is fully covered by an executable Alembic revision:

| Archived file | Superseded by |
|---|---|
| `V053__cte_append_only_triggers.sql` | `20260505_5ac9e7b1d402_v078_orphan_migration_forward_ports.py` (creates `cte_events_append_only` + `hash_chain_append_only` triggers) |
| `V067__inflow_workbench_persistence.sql` | `20260430_b8c9d0e1f2a3_v073_inflow_workbench_postgres.py` (file header: "raw SQL companion for v073") |
| `V068__supplier_integration_profiles.sql` | `20260430_c9d0e1f2a3b4_v074_supplier_integration_profiles.py` (file header: "raw SQL companion for v074") |

Earlier consolidation history (V002–V042 baseline, the 2026-04-20
consolidation incident, orphan forward-ports) is documented in
`docs/MIGRATION_CONSOLIDATION.md`.
