"""v142: data gap writes must keep working after the per-deploy cutover.

A grant applied only by a migration is revoked by
``apply_runtime_role_cutover``, so these checks pin the v111 inventory, which
is what survives a deploy.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
V111 = REPO_ROOT / "alembic/versions/20260803_b71d9e4c2a60_v111_runtime_role_grants.py"
V142 = REPO_ROOT / "alembic/versions/20261104_9c0bfe465816_v142_data_gap_runtime_grants.py"
SUPABASE = REPO_ROOT / "supabase/migrations/20261104120000_v142_data_gap_runtime_grants.sql"
OPEN_GAP_COLUMNS = ("tenant_id", "tlc_code", "facility_id")
CLOSE_GAP_COLUMNS = ("closed_at", "closing_record_id", "closing_record_hash")


def _v111():
    spec = importlib.util.spec_from_file_location("regengine_v111_for_v142", V111)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inventory_keeps_gap_grants_across_cutover() -> None:
    v111 = _v111()

    assert "data_gap_events" in v111.APPLICATION_TABLES["public"]
    assert set(v111.REGENGINE_TABLE_GRANTS["public.data_gap_events"]) == {"SELECT", "INSERT"}
    assert v111.REGENGINE_COLUMN_GRANTS["public.data_gap_events"]["UPDATE"] == CLOSE_GAP_COLUMNS
    assert v111.REGENGINE_SYSADMIN_TABLE_GRANTS["public.data_gap_events"] == ("SELECT",)


def test_supplier_lots_stay_column_scoped_for_runtime() -> None:
    v111 = _v111()

    assert "public.supplier_traceability_lots" not in v111.REGENGINE_TABLE_GRANTS
    assert v111.REGENGINE_COLUMN_GRANTS["public.supplier_traceability_lots"] == {"SELECT": OPEN_GAP_COLUMNS}


def test_runtime_gap_update_is_column_scoped_only() -> None:
    v111 = _v111()

    assert "UPDATE" not in v111.REGENGINE_TABLE_GRANTS["public.data_gap_events"]
    assert v111.REGENGINE_COLUMN_GRANTS["public.data_gap_events"] == {"UPDATE": CLOSE_GAP_COLUMNS}
    for path in (V142, SUPABASE):
        upgrade_sql = path.read_text(encoding="utf-8").split("def downgrade")[0]
        assert "GRANT SELECT, INSERT, UPDATE ON TABLE public.data_gap_events" not in upgrade_sql, path.name


def test_gap_history_cannot_be_deleted_by_runtime() -> None:
    assert "DELETE" not in _v111().REGENGINE_TABLE_GRANTS["public.data_gap_events"]


def test_alembic_and_supabase_apply_the_same_grants() -> None:
    expected = (
        "REVOKE UPDATE ON TABLE public.data_gap_events FROM regengine;",
        "GRANT SELECT, INSERT ON TABLE public.data_gap_events TO regengine;",
        "GRANT UPDATE (closed_at, closing_record_id, closing_record_hash)\n",
        "ON TABLE public.data_gap_events TO regengine;",
        "GRANT SELECT ON TABLE public.data_gap_events TO regengine_sysadmin;",
        "GRANT SELECT (tenant_id, tlc_code, facility_id) ON TABLE public.supplier_traceability_lots TO regengine;",
    )
    for path in (V142, SUPABASE):
        sql = path.read_text(encoding="utf-8")
        for statement in expected:
            assert statement in sql, f"{path.name} is missing {statement}"
