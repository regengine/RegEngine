"""OKR weekly report must confirm a read-only role before use.

scripts/okr_pilots_ingesting_weekly.sql runs against production every
Monday morning. Its usage must point at a read-only reporting URL (never
the write-capable DATABASE_URL), the script must refuse write-capable
logins, and the report itself must run inside one read-only transaction
so the database rejects any change through that session.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / "scripts" / "okr_pilots_ingesting_weekly.sql"

WRITE_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "TRUNCATE",
    "COPY",
    "ALTER",
    "DROP",
    "CREATE",
    "GRANT",
    "REVOKE",
    "VACUUM",
    "CLUSTER",
)


def _code_text() -> str:
    """SQL with every -- comment stripped, so prose cannot trip the scan."""
    stripped = []
    for line in SQL.read_text().splitlines():
        code, _, _comment = line.partition("--")
        stripped.append(code)
    return "\n".join(stripped)


def test_usage_names_readonly_url_and_never_bare_database_url():
    text = SQL.read_text()
    assert "OKR_READONLY_DATABASE_URL" in text
    assert "$DATABASE_URL" not in text


def test_guard_refuses_write_capable_login():
    code = _code_text()
    assert re.search(r"DO\s+\$okr_guard\$", code)
    assert "RAISE EXCEPTION" in code
    assert "read-only" in code
    for role in ("regengine", "regengine_sysadmin", "postgres"):
        assert role in code
    assert "rolsuper" in code and "rolbypassrls" in code


def test_report_runs_inside_one_read_only_transaction():
    code = _code_text()
    assert re.search(r"BEGIN TRANSACTION READ ONLY;", code)
    assert code.rstrip().endswith("ROLLBACK;")


def test_report_contains_no_write_statements():
    code = _code_text()
    match = re.search(r"\b(%s)\b" % "|".join(WRITE_KEYWORDS), code, re.IGNORECASE)
    assert match is None, f"write keyword in report: {match.group(0)!r}"
