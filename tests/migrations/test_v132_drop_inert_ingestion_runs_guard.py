"""Offline check for the v132 ingestion_runs policy repair."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

V132 = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/20261017_a9ea09050a30_v132_drop_inert_ingestion_runs_guard.py"
)


def test_upgrade_drops_guard_only_without_client_roles(monkeypatch) -> None:
    spec = importlib.util.spec_from_file_location(V132.stem, V132)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "0a329588b824"  # pragma: allowlist secret

    statements = []
    monkeypatch.setattr(migration, "op", SimpleNamespace(execute=statements.append))
    migration.upgrade()

    assert len(statements) == 1
    sql = statements[0]
    assert "DROP POLICY v128_client_guard_ingestion_runs ON fsma.ingestion_runs" in sql
    assert "rolname IN ('anon', 'authenticated')" in sql
    assert "to_regclass('fsma.ingestion_runs')" in sql
    assert "AND NOT EXISTS (" in sql
