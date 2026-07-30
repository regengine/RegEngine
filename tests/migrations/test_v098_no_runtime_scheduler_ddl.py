"""v098 regression guard — no runtime DDL in the scheduler state manager.

v098 (PR #2645) removed every CREATE TABLE / CREATE INDEX from
``StateManager.initialize()`` (services/scheduler/app/state.py) and moved
the objects into migrations. Two reasons the runtime DDL must never come
back:

1. **Multi-worker boot race** — Postgres's ``IF NOT EXISTS`` is not
   concurrency-safe. When gunicorn's 4 workers booted the embedded
   scheduler simultaneously, the losers crashed with
   ``UniqueViolation: duplicate key value violates unique constraint
   "pg_class_relname_nsp_index"`` and only recovered via the 30s
   re-election retry (Railway prod boot, 2026-07-17T15:51:53Z).
2. **Least-privilege cutover (#2461)** — the prod app role
   (``regengine``) has CREATE revoked on the schema, so reintroduced
   runtime DDL would fail at boot with insufficient_privilege — i.e.
   exactly the crash/re-election incident mode again.

Tables and indexes belong in alembic/versions/ (v093 created
``scheduler_seen_items``; v098 owns its two indexes and
``scheduler_job_runs``), applied single-flight by
scripts/run-migrations.sh before any worker boots.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = REPO_ROOT / "services" / "scheduler" / "app" / "state.py"
V098_PATH = REPO_ROOT / "alembic" / "versions" / "20260725_8b2f4e6a9c31_v098_runtime_ddl_into_migrations.py"

BANNED = ("CREATE TABLE", "CREATE INDEX")


def test_state_manager_has_no_runtime_ddl():
    source = STATE_PATH.read_text(encoding="utf-8")

    offending = [
        (lineno, line.strip())
        for lineno, line in enumerate(source.splitlines(), start=1)
        if not line.lstrip().startswith("#") and any(banned in line.upper() for banned in BANNED)
    ]
    assert not offending, (
        "Runtime DDL reintroduced into services/scheduler/app/state.py at "
        f"{offending}. CREATE TABLE / CREATE INDEX must live in an alembic "
        "migration: IF NOT EXISTS races across gunicorn workers "
        "(UniqueViolation on pg_class_relname_nsp_index), and the prod app "
        "role has no CREATE privilege since #2461."
    )


def test_v098_migration_owns_the_scheduler_state_objects():
    """The objects state.py used to create at boot are owned by v098."""
    source = V098_PATH.read_text(encoding="utf-8")

    assert "CREATE INDEX IF NOT EXISTS idx_seen_items_source_type" in source
    assert "CREATE INDEX IF NOT EXISTS idx_seen_items_last_seen" in source
    assert "CREATE TABLE IF NOT EXISTS public.scheduler_job_runs" in source
