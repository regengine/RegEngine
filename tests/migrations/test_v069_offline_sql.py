"""SEL-621: v069 must render correctly under ``alembic upgrade --sql``.

Offline there is no bind to probe for the Flyway V31 artifacts.  The
migration must neither crash nor silently skip the tenant-isolation
retrofit: it emits a single ``DO`` block that checks for V31 at execution
time, applies the retrofit when present, and raises the skip NOTICE when
absent.  Online behavior (live probes, statement-by-statement execution)
is unchanged.
"""

import importlib.util
import io
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = _REPO_ROOT / "alembic" / "versions" / "20260424_abc565b7dc47_v069_v31_fsma_tenant_id_rls.py"


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("migration_v069", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_offline(monkeypatch, fn_name):
    module = _load_migration_module()
    monkeypatch.setattr(module.context, "is_offline_mode", lambda: True, raising=False)
    buf = io.StringIO()
    ctx = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": buf},
    )
    with Operations.context(ctx):
        getattr(module, fn_name)()
    return module, buf.getvalue()


def test_upgrade_offline_emits_conditional_retrofit(monkeypatch):
    module, sql = _run_offline(monkeypatch, "upgrade")

    # Gated on the V31 canary, evaluated by the target database.
    assert "DO $v069$" in sql
    assert "IF to_regclass('fsma.products') IS NOT NULL THEN" in sql

    # Present branch: the full retrofit is emitted, not skipped.
    for marker in (
        "ALTER TABLE fsma.products ADD COLUMN IF NOT EXISTS tenant_id UUID",
        "ALTER TABLE fsma.products FORCE ROW LEVEL SECURITY",
        "CREATE POLICY tenant_isolation_products ON fsma.products",
        "CREATE POLICY tenant_isolation_kdes ON fsma.key_data_elements",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_fsma_products_tenant_gtin",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_fsma_compliance_snapshots_tenant_date",
        "get_tenant_context()::uuid",
    ):
        assert marker in sql, marker

    # Every retrofit statement is inside the block, run via EXECUTE.
    stmts = module._upgrade_statements()
    assert sql.count("EXECUTE $v069s$") == len(stmts)

    # Absent branch: the same skip NOTICE the online path emits.
    assert "ELSE" in sql
    assert "RAISE NOTICE 'v069: Flyway V31 tables not present" in sql
    assert "skipping retrofit" in sql


def test_downgrade_offline_emits_conditional_revert(monkeypatch):
    module, sql = _run_offline(monkeypatch, "downgrade")

    assert "IF to_regclass('fsma.products') IS NOT NULL AND to_regprocedure('fsma.current_org_id()') IS NOT NULL THEN" in sql
    assert "CREATE POLICY fsma_org_isolation_products ON fsma.products" in sql
    assert "ALTER TABLE fsma.products DROP COLUMN IF EXISTS tenant_id" in sql
    assert sql.count("EXECUTE $v069s$") == len(module._downgrade_statements())
    assert "RAISE NOTICE 'v069 downgrade: Flyway V31 schema not present" in sql


class _RecordingOp:
    def __init__(self):
        self.executed = []

    def execute(self, sql):
        self.executed.append(sql)


def _run_online(monkeypatch, fn_name, *, v31, helper=True):
    module = _load_migration_module()
    rec = _RecordingOp()
    monkeypatch.setattr(module.context, "is_offline_mode", lambda: False, raising=False)
    monkeypatch.setattr(module, "op", rec)
    monkeypatch.setattr(module, "_v31_present", lambda: v31)
    monkeypatch.setattr(module, "_v31_helper_fn_present", lambda: helper)
    getattr(module, fn_name)()
    return module, rec.executed


def test_upgrade_online_runs_statements_individually_when_v31_present(monkeypatch):
    module, executed = _run_online(monkeypatch, "upgrade", v31=True)
    assert executed == module._upgrade_statements()
    assert not any("DO $v069$" in s for s in executed)


def test_upgrade_online_skips_when_v31_absent(monkeypatch):
    _, executed = _run_online(monkeypatch, "upgrade", v31=False)
    assert len(executed) == 1
    assert "skipping retrofit" in executed[0]


def test_downgrade_online_skips_without_helper_fn(monkeypatch):
    _, executed = _run_online(monkeypatch, "downgrade", v31=True, helper=False)
    assert len(executed) == 1
    assert "nothing to revert" in executed[0]
