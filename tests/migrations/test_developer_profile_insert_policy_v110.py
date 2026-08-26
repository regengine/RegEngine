"""Regression tests for the developer profile self-provisioning policy (v110).

#2880: the previous version of this module asserted that the guard TEXT was
present in the rendered SQL::

    assert "to_regclass('public.developer_profiles') IS NULL" in sql
    assert "rolname = 'authenticated'" in sql

That is the opposite of a regression test. Both of those conditions are false
on the Alembic-managed database, so the migration was a guaranteed double
no-op — and the test passed precisely BECAUSE the silent-skip guard was
there. A test that green-lights the skip cannot catch the skip.

What is asserted now:

* the no-marker path is an announced no-op that emits no policy DDL at all
  (a documented property of the revision, not an accident);
* the marker path contains no silently-returning guard — a missing table or
  role RAISEs;
* and, against a live database, the actual contents of ``pg_policies``. That
  last one is the only assertion that can catch a skip, because it looks at
  what the database ended up with rather than at what the migration text
  says it intends. It skips when no live database is designated.
"""

from __future__ import annotations

import importlib.util
import os
import re
from pathlib import Path

import pytest

from tests.migrations.rls_db import guarded_live_database_url

psycopg = pytest.importorskip("psycopg")

DATABASE_URL = guarded_live_database_url()

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260815_6f8c2d1a4b90_v110_developer_profile_insert_policy.py"
)

MARKER_ENV = "REGENGINE_SUPABASE_PORTAL_MIGRATIONS"

_POLICY = "developers_insert_own_profile"


def _load_migration():
    spec = importlib.util.spec_from_file_location("developer_profile_insert_policy_v110", _MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _render(monkeypatch, fn_name: str, marker: str) -> str:
    migration = _load_migration()
    monkeypatch.setenv(MARKER_ENV, marker)
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)
    getattr(migration, fn_name)()
    assert len(statements) == 1, f"expected exactly one statement, got {len(statements)}"
    return statements[0]


def _portal_marker_set() -> bool:
    return os.environ.get(MARKER_ENV, "0") == "1"


# --------------------------------------------------------------------------
# Static: the shape of the migration
# --------------------------------------------------------------------------


def test_without_the_portal_marker_upgrade_is_an_announced_noop(monkeypatch):
    """No policy DDL, and the skip says so out loud in the migration log."""
    sql = _render(monkeypatch, "upgrade", "0")

    assert "CREATE POLICY" not in sql
    assert "DROP POLICY" not in sql
    assert "ON public.developer_profiles" not in sql
    assert "RAISE NOTICE" in sql
    assert MARKER_ENV in sql, "the log line must name the variable that controls this decision"


def test_with_the_portal_marker_upgrade_creates_the_policy(monkeypatch):
    sql = _render(monkeypatch, "upgrade", "1")

    assert f"CREATE POLICY {_POLICY}" in sql
    assert "FOR INSERT" in sql
    assert "TO authenticated" in sql
    assert "WITH CHECK ((SELECT auth.uid()) = auth_user_id)" in sql
    assert "TO anon" not in sql


def test_with_the_portal_marker_a_missing_precondition_raises_instead_of_skipping(monkeypatch):
    """The v104 rule: a conditional CREATE POLICY is what caused that incident.

    With the marker set the operator has asserted this IS the portal
    database, so an absent table or role must abort the migration. There must
    be no bare ``RETURN`` that would let the CREATE POLICY be skipped.
    """
    sql = _render(monkeypatch, "upgrade", "1")

    assert sql.count("RAISE EXCEPTION") == 2, "both preconditions must fail loudly"
    assert re.search(r"to_regclass\('public\.developer_profiles'\) IS NULL", sql)
    assert re.search(r"rolname = 'authenticated'", sql)

    # A `RETURN;` anywhere in the upgrade path would reintroduce the silent
    # skip this revision was rewritten to remove.
    assert not re.search(r"\bRETURN\s*;", sql), (
        "upgrade() must not contain a silently-returning guard — that is the "
        "shape v104 documents as the cause of a production incident (#2880)"
    )


def test_downgrade_removes_only_the_insert_policy(monkeypatch):
    sql = _render(monkeypatch, "downgrade", "1")

    assert f"DROP POLICY IF EXISTS {_POLICY}" in sql
    assert "developers_read_own_profile" not in sql
    assert "developers_update_own_profile" not in sql


# --------------------------------------------------------------------------
# Live: what the database actually ended up with
# --------------------------------------------------------------------------


@pytest.mark.skipif(
    not DATABASE_URL,
    reason="no designated live test DB (CI DATABASE_URL or REGENGINE_MIGRATION_TEST_DB) — live DB required",
)
def test_live_policy_state_matches_the_revisions_declared_intent():
    """Assert on ``pg_policies``, not on the migration's own guard text.

    This is the assertion that can catch a skip: it compares what the
    database actually holds against what ``REGENGINE_SUPABASE_PORTAL_MIGRATIONS``
    said this run was for.
    """
    with psycopg.connect(DATABASE_URL) as conn:
        table_exists = conn.execute("SELECT to_regclass('public.developer_profiles') IS NOT NULL").fetchone()[0]
        rows = conn.execute(
            """
            SELECT cmd, roles, with_check
            FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = 'developer_profiles'
              AND policyname = %(p)s
            """,
            {"p": _POLICY},
        ).fetchall()

    if not _portal_marker_set():
        # The Alembic-managed database. v110 declares itself a no-op here, so
        # the policy must be absent — if it appeared, the revision is doing
        # something its docstring does not describe.
        assert not rows, (
            f"{_POLICY} exists on a database migrated without {MARKER_ENV}=1; "
            "v110 declares itself a no-op outside the Supabase portal project"
        )
        return

    assert table_exists, (
        f"{MARKER_ENV}=1 but public.developer_profiles is absent — v110 should "
        "have aborted this migration run rather than completing"
    )
    assert rows, (
        f"v110 ran with {MARKER_ENV}=1 but {_POLICY} is not in pg_policies. "
        "The migration skipped its own policy — this is the #2880 / v104 "
        "silent-skip regression, and no amount of asserting on the migration "
        "text would have caught it."
    )
    cmd, roles, with_check = rows[0]
    assert cmd == "INSERT", f"{_POLICY} must be an INSERT policy, got {cmd!r}"
    assert "authenticated" in list(roles), f"{_POLICY} must be granted TO authenticated, got {roles!r}"
    assert with_check and "auth_user_id" in with_check, (
        f"{_POLICY} must be owner-scoped on auth_user_id, got with_check={with_check!r}"
    )
