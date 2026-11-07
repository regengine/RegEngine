"""v143: EDI rejection evidence must survive deploys and stay tenant-scoped."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
V111 = REPO_ROOT / "alembic/versions/20260803_b71d9e4c2a60_v111_runtime_role_grants.py"
V143 = REPO_ROOT / "alembic/versions/20261105_056ffd2f8045_v143_edi_rejections.py"
SUPABASE = REPO_ROOT / "supabase/migrations/20261105120000_v143_edi_rejections.sql"


def _v111():
    spec = importlib.util.spec_from_file_location("regengine_v111_for_v143", V111)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inventory_keeps_rejection_grants_across_cutover() -> None:
    v111 = _v111()

    assert "edi_rejections" in v111.APPLICATION_TABLES["fsma"]
    assert set(v111.REGENGINE_TABLE_GRANTS["fsma.edi_rejections"]) == {"SELECT", "INSERT"}
    assert v111.REGENGINE_SYSADMIN_TABLE_GRANTS["fsma.edi_rejections"] == ("SELECT",)


def test_both_migrations_force_rls_and_stay_append_only() -> None:
    for path in (V143, SUPABASE):
        text = path.read_text(encoding="utf-8")
        assert "ENABLE ROW LEVEL SECURITY" in text
        assert "FORCE ROW LEVEL SECURITY" in text
        assert "public.get_tenant_context()" in text
        assert "grant select, insert on fsma.edi_rejections to regengine;" in text
        assert "grant update" not in text.lower()
        assert "grant delete" not in text.lower()
