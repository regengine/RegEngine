"""Static guards for the #3600 follow-up Supabase migrations."""

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"


def _read(name: str) -> str:
    return (MIGRATIONS / name).read_text()


def test_waitlist_authenticated_read_dropped_and_insert_kept():
    sql = _read("20261025100100_waitlist_leads_drop_authenticated_read.sql")
    assert 'DROP POLICY IF EXISTS "Service role can read all"' in sql
    assert "Allow anonymous inserts" not in sql
    assert "CREATE POLICY" not in sql


def test_task_queue_policy_fails_closed_on_empty_or_null_tenant():
    sql = _read("20261025100200_task_queue_fail_closed_tenant_policy.sql")
    body = sql.split("CREATE POLICY", 1)[1]
    assert "= ''" not in body
    assert body.count("IS NOT NULL") == 2
    assert "WITH CHECK" in body


def test_data_gap_check_rejects_null_hash_on_close():
    sql = _read("20261025100300_data_gap_close_receipt_not_null.sql")
    assert "closing_record_hash IS NOT NULL" in sql
