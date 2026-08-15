"""Regression tests for the developer profile self-provisioning policy."""

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260815_6f8c2d1a4b90_v110_developer_profile_insert_policy.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("developer_profile_insert_policy_v110", _MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_adds_owner_scoped_authenticated_insert_policy(monkeypatch):
    migration = _load_migration()
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    assert len(statements) == 1
    sql = statements[0]
    assert "CREATE POLICY developers_insert_own_profile" in sql
    assert "FOR INSERT" in sql
    assert "TO authenticated" in sql
    assert "WITH CHECK ((SELECT auth.uid()) = auth_user_id)" in sql
    assert "to_regclass('public.developer_profiles') IS NULL" in sql
    assert "rolname = 'authenticated'" in sql
    assert "TO anon" not in sql


def test_downgrade_removes_only_the_insert_policy(monkeypatch):
    migration = _load_migration()
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.downgrade()

    assert len(statements) == 1
    sql = statements[0]
    assert "DROP POLICY IF EXISTS developers_insert_own_profile" in sql
    assert "developers_read_own_profile" not in sql
    assert "developers_update_own_profile" not in sql
