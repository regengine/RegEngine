"""Offline check for the v133 sysadmin tenant-name grant."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

V133 = (
    Path(__file__).resolve().parents[2] / "alembic/versions/20261019_c4d8f1a2b6e7_v133_sysadmin_tenant_name_update.py"
)


def _load():
    spec = importlib.util.spec_from_file_location(V133.stem, V133)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_upgrade_grants_only_name_column_to_sysadmin(monkeypatch) -> None:
    migration = _load()
    assert migration.down_revision == "a9ea09050a30"  # pragma: allowlist secret

    statements = []
    monkeypatch.setattr(migration, "op", SimpleNamespace(execute=statements.append))
    migration.upgrade()

    assert len(statements) == 1
    assert "GRANT UPDATE (name) ON TABLE public.tenants TO regengine_sysadmin" in statements[0]
    assert "regengine," not in statements[0]


def test_downgrade_revokes_the_same_grant(monkeypatch) -> None:
    migration = _load()
    statements = []
    monkeypatch.setattr(migration, "op", SimpleNamespace(execute=statements.append))
    migration.downgrade()

    assert len(statements) == 1
    assert "REVOKE UPDATE (name) ON TABLE public.tenants FROM regengine_sysadmin" in statements[0]
