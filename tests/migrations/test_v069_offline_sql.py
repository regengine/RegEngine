"""SEL-621: v069 must render under ``alembic upgrade --sql`` (offline mode).

Offline there is no bind, so the V31 ``to_regclass`` probe used to crash
with ``AttributeError: 'NoneType' object has no attribute 'scalar'``.
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
    return buf.getvalue()


def test_upgrade_renders_offline_as_skip(monkeypatch):
    sql = _run_offline(monkeypatch, "upgrade")
    assert "skipping retrofit" in sql
    assert "ALTER TABLE fsma.products" not in sql


def test_downgrade_renders_offline_without_crash(monkeypatch):
    sql = _run_offline(monkeypatch, "downgrade")
    assert "CREATE POLICY" not in sql
