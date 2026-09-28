"""v126 operator guidance must name a session that can actually see the rows.

Both tables are FORCE ROW LEVEL SECURITY and the migration owner is
NOBYPASSRLS: a plain schema-owner session errors without a tenant and, with
one, sees no ingestion_runs rows and would flag every blob as misattached.
"""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V126 = ROOT / "alembic/versions/20260928_c51d4898e0a2_v126_runtime_grants_csv_receipt_agent_worker.py"
PREDEPLOY = ROOT / "runbooks/predeploy-v126-misattached-blobs.sql"
VERIFY = ROOT / "runbooks/verify-v126-runtime-grants.sql"


def _v126():
    spec = importlib.util.spec_from_file_location("v126_operator_guidance", V126)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sql_lines(path: Path) -> list[str]:
    return [line for line in path.read_text().splitlines() if not line.lstrip().startswith("--")]


def test_refusal_names_a_session_that_sees_every_row():
    message = _v126()._misattached_blobs_refusal(3)

    assert message.startswith("v126: 3 fsma.manifest_blobs row(s)")
    assert "Nothing was changed or deleted" in message
    assert "runbooks/predeploy-v126-misattached-blobs.sql" in message and PREDEPLOY.is_file()
    assert "superuser" in message and "BYPASSRLS" in message
    # Any schema-owner route carries the NO FORCE / rollback caveat and the
    # warning that a plain owner session gives wrong per-tenant results.
    assert "review those rows as the schema owner" not in message
    assert "schema owner" in message
    assert "NO FORCE ROW LEVEL SECURITY" in message and "rolled back" in message
    assert "wrong per-tenant results" in message and "do not delete evidence" in message


def test_predeploy_runbook_is_read_only_guarded_and_lists_identifiers_only():
    sql = "\n".join(_sql_lines(PREDEPLOY))

    assert re.search(r"BEGIN TRANSACTION READ ONLY;\s*SET LOCAL search_path = pg_catalog, pg_temp;", sql)
    assert sql.rstrip().endswith("ROLLBACK;")
    # Refuses any session that cannot see every row instead of under-reporting.
    assert "rolsuper OR rolbypassrls" in sql and "RAISE EXCEPTION" in sql
    for column in ("blob.ingestion_run_id", "blob.tenant_id", "run.tenant_id"):
        assert column in sql
    assert "raw_bytes" not in sql
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|ALTER|DROP|TRUNCATE)\b", sql)


def test_verify_runbook_is_search_path_proof_and_points_at_the_predeploy_check():
    text = VERIFY.read_text()
    sql = "\n".join(_sql_lines(VERIFY))

    assert re.search(r"BEGIN TRANSACTION READ ONLY;\s*SET LOCAL search_path = pg_catalog, pg_temp;", sql)
    # Catalog text such as pg_get_constraintdef() drops the schema prefix when
    # the schema is on the caller's search_path; compare the catalog instead.
    assert "pg_get_constraintdef" not in sql
    assert "runbooks/predeploy-v126-misattached-blobs.sql" in text
