"""Offline checks for the v128 FSMA policy repair; no database connection."""

import importlib.util
import re
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
V111 = ROOT / "alembic/versions/20260803_b71d9e4c2a60_v111_runtime_role_grants.py"
V128 = ROOT / "alembic/versions/20261016_a5e7c9b2d341_v128_fsma_rls_policy_repair.py"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sql(module, operation: str) -> list[str]:
    with patch.object(module.op, "execute") as execute:
        getattr(module, operation)()
    return [call.args[0] for call in execute.call_args_list]


def test_policy_scope_matches_runtime_acl() -> None:
    grants = _load(V111)
    repair = _load(V128)
    assert repair.down_revision == "ed902d03df45"
    assert len(repair._TABLES) == 22
    assert len(repair._RUNTIME_ACCESS) == 18
    for table, operations in repair._RUNTIME_ACCESS.items():
        assert operations == grants.REGENGINE_TABLE_GRANTS[f"fsma.{table}"]
    for table in repair._CLOSED_TABLES:
        assert f"fsma.{table}" not in grants.REGENGINE_TABLE_GRANTS
        assert f"fsma.{table}" not in grants.REGENGINE_SYSADMIN_TABLE_GRANTS
    assert {
        table: grants.REGENGINE_SYSADMIN_TABLE_GRANTS[f"fsma.{table}"]
        for table in repair._TABLES
        if f"fsma.{table}" in grants.REGENGINE_SYSADMIN_TABLE_GRANTS
    } == {"ingestion_runs": ("SELECT",)}


def test_upgrade_denies_client_roles_and_limits_runtime_commands() -> None:
    repair = _load(V128)
    statements = _sql(repair, "upgrade")
    assert len(statements) == 22
    for table, sql in zip(repair._TABLES, statements, strict=True):
        if table == "cte_kdes_backfill_log_v059":
            assert re.search(r"IF to_regclass\('fsma.cte_kdes_backfill_log_v059'\) IS NULL THEN\s+RETURN;", sql)
        else:
            assert f"Expected fsma.{table} at v128" in sql
        assert f"CREATE POLICY v128_client_guard_{table}" in sql
        assert "AS RESTRICTIVE FOR ALL TO PUBLIC" in sql
        assert "USING ((tenant_id = get_tenant_context()) AND current_user NOT IN" in sql
        assert "current_user NOT IN ('anon', 'authenticated'" in sql
        assert "GRANT " not in sql
        assert sql.count("JOIN pg_roles r") == len(repair._app_operations(table))
        for command in repair._RUNTIME_ACCESS.get(table, ()):
            policy = sql.split(f"CREATE POLICY v128_{table}_{command.lower()}_regengine", 1)[1].split("$policy$", 1)[0]
            assert f"FOR {command} TO regengine" in policy
            if command != "INSERT":
                assert "USING (tenant_id = get_tenant_context())" in policy
            if command in ("INSERT", "UPDATE"):
                assert "WITH CHECK (tenant_id = get_tenant_context())" in policy
        if table in repair._CLOSED_TABLES:
            assert "'regengine', 'regengine_sysadmin'" in sql
            assert f"CREATE POLICY v128_{table}_" not in sql
    assert "FOR SELECT TO regengine_sysadmin" in statements[repair._TABLES.index("ingestion_runs")]
    assert "FOR DELETE TO regengine" in statements[repair._TABLES.index("cte_events")]
    assert "FOR DELETE TO regengine" not in statements[repair._TABLES.index("hash_chain")]


def test_downgrade_removes_only_v128_policies() -> None:
    repair = _load(V128)
    statements = _sql(repair, "downgrade")
    assert len(statements) == 22
    names = [name for sql in statements for name in re.findall(r"DROP POLICY IF EXISTS (\w+)", sql)]
    assert len(names) == 22 + sum(map(len, repair._RUNTIME_ACCESS.values())) + 1
    assert all(name.startswith("v128_") for name in names)
