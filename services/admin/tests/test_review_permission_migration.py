"""Data-only migration contract for curator role permissions.

The dedicated migration owner is intentionally ``NOBYPASSRLS``.  v113 may
therefore relax ``FORCE RLS`` only inside the same atomic PostgreSQL statement
that performs the backfill, and it must restore ``FORCE RLS`` before success.
If duplicate canonical roles raise, PostgreSQL rolls the entire ``DO``
statement back, including the temporary ``NO FORCE`` change.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_migration():
    path = (
        Path(__file__).parents[3]
        / "alembic"
        / "versions"
        / "20260826_228275bfe7e1_v113_review_permissions.py"
    )
    spec = importlib.util.spec_from_file_location("review_permissions_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_is_atomic_and_only_updates_canonical_system_roles():
    migration = _load_migration()
    statements: list[str] = []
    migration.op = SimpleNamespace(execute=statements.append)

    migration.upgrade()

    assert len(statements) == 1
    sql = statements[0]
    assert "tenant_id IS NULL" in sql
    assert "name IN ('Owner', 'Admin')" in sql
    assert "review.read" in sql
    assert "review.decide" in sql
    assert "duplicate canonical system role" in sql
    upper_sql = sql.upper()
    no_force = "ALTER TABLE PUBLIC.ROLES NO FORCE ROW LEVEL SECURITY"
    restore_force = "ALTER TABLE PUBLIC.ROLES FORCE ROW LEVEL SECURITY"
    assert upper_sql.count(no_force) == 1
    assert upper_sql.count(restore_force) == 1
    assert upper_sql.index(no_force) < upper_sql.index("UPDATE ROLES")
    assert upper_sql.index("UPDATE ROLES") < upper_sql.index(restore_force)
    assert upper_sql.strip().startswith("DO $$")
    assert upper_sql.strip().endswith("END $$;")

    # These are the only table-shape statements permitted. Keeping both
    # toggles inside the one DO statement gives failure-path restoration via
    # PostgreSQL statement atomicity.
    alter_lines = [line.strip() for line in upper_sql.splitlines() if "ALTER TABLE" in line]
    assert alter_lines == [f"{no_force};", f"{restore_force};"]
    assert "CREATE TABLE" not in sql.upper()
    assert "DROP TABLE" not in sql.upper()
