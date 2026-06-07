import importlib.util
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = _REPO_ROOT / "alembic" / "versions" / "20260505_5ac9e7b1d402_v078_orphan_migration_forward_ports.py"
_FSMA_TABLES = (
    "products",
    "locations",
    "suppliers",
    "critical_tracking_events",
    "audit_log",
    "recall_assessments",
    "compliance_snapshots",
    "compliance_alerts",
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("migration_v078", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fsma_tenant_backfills_are_guarded_by_org_id_presence(monkeypatch):
    module = _load_migration_module()
    executed_sql = []
    monkeypatch.setattr(module.op, "execute", executed_sql.append)

    module._fsma_infrastructure_tables()

    assert len(executed_sql) == 1
    sql = executed_sql[0]

    for table in _FSMA_TABLES:
        pattern = re.compile(
            rf"""
            DO \s+ \$mig\$ \s+
            BEGIN \s+
                IF \s+ EXISTS \s* \(
                    \s* SELECT \s+ 1
                    \s+ FROM \s+ information_schema\.columns
                    \s+ WHERE \s+ table_schema \s* = \s* 'fsma'
                    \s+ AND \s+ table_name \s* = \s* '{table}'
                    \s+ AND \s+ column_name \s* = \s* 'org_id'
                    \s* \) \s+ THEN
                    \s+ EXECUTE \s+ 'UPDATE \s+ fsma\.{table} \s+ SET \s+ tenant_id \s* = \s* org_id \s+ WHERE \s+ tenant_id \s+ IS \s+ NULL';
                \s+ END \s+ IF;
            \s+ END;
            \s+ \$mig\$;
            """,
            re.VERBOSE | re.DOTALL,
        )
        assert pattern.search(sql), f"expected guarded tenant backfill for fsma.{table}"


def test_tenant_rls_handles_legacy_text_tenant_ids(monkeypatch):
    module = _load_migration_module()
    executed_sql = []
    monkeypatch.setattr(module.op, "execute", executed_sql.append)

    module._tenant_rls("fsma.compliance_alerts", "tenant_id", "tenant_isolation_alerts")

    assert len(executed_sql) == 1
    sql = executed_sql[0]
    assert "table_schema = 'fsma'" in sql
    assert "table_name = 'compliance_alerts'" in sql
    assert "column_name = 'tenant_id'" in sql
    assert "column_type IN ('text', 'character varying')" in sql
    assert "predicate := 'tenant_id = get_tenant_context()::text';" in sql
    assert "predicate := 'tenant_id = get_tenant_context()';" in sql
    assert "CREATE POLICY tenant_isolation_alerts ON fsma.compliance_alerts" in sql
