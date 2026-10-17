# Held migrations

Files here are **not** on the upgrade path. Alembic scans only
`alembic/versions/` (`alembic.ini` sets no `version_locations` and
`recursive_version_locations` is off), so nothing in this directory runs on
deploy.

## 20261016_c4f0a7b6f8ee_v129_drop_unused_indexes.py

Drops 155 indexes that one catalog export reported as unused. It was held
in PR #3397 because `pg_stat_database.stats_reset` is NULL, so the
`idx_scan = 0` observation window is unknown. It reached `alembic/versions/`
anyway and, together with the two v128 heads, broke `alembic upgrade head`
on Railway (INC-2). It was moved here so it cannot run.

Before it goes back into `alembic/versions/`:

1. Owner approval (Christopher) after `idx_scan = 0` is re-verified over at
   least 14 days.
2. Re-parent it: set `down_revision` (and the `Revises:` docstring line) to
   the current head at that time. Its `down_revision` still names
   `93eb33f262a1`, which may no longer be the head.
3. Re-check the index list against indexes added since, including the
   `idx_<table>_tenant_id` indexes from the 2026-10-17 hand migration.
