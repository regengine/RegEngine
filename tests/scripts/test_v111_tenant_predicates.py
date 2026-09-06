"""v111's identity bootstrap exception must remain explicitly fail-closed."""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("tenant_guard", ROOT / "scripts/check_tenant_id_uuid_only.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_v111_tenant_gucs_are_nullif_guarded():
    source = (ROOT / "alembic/versions/20260803_b71d9e4c2a60_v111_runtime_role_grants.py").read_text()
    guc = r"current_setting\(\s*'app\.tenant_id'\s*,\s*true\s*\)"
    guarded = r"NULLIF\(\s*" + guc + r"\s*,\s*''\s*\)"
    assert re.findall(guc, source)
    assert not re.findall(guc, re.sub(guarded, "GUARDED_CONTEXT", source))


def test_new_migrations_still_reject_direct_tenant_guc(tmp_path):
    migration = tmp_path / "new.py"
    migration.write_text("CREATE POLICY unsafe ON t USING (tenant_id::text = current_setting('app.tenant_id', true));")
    assert guard.check_policy_predicates(migration)
