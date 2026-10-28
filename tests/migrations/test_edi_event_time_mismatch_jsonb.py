"""Run the EDI event-time mismatch query against a real JSONB ``kde_value``.

``fsma.cte_kdes.kde_value`` has been JSONB since migration v078, so the
query in ``scripts/check_edi_event_time_mismatch.py`` must extract the scalar
text (``#>> '{}'``) before its regex match and date cast. This test builds a
minimal events/kdes pair with a JSONB column in a disposable Postgres
(``rls_postgres_or_skip``: the CI service container or a testcontainers
Postgres), runs ``MISMATCH_SQL`` / ``INVALID_DATE_SQL`` inside a transaction
and rolls it back. It never runs the script itself and never touches a real
database.

Tables are created under a unique schema (not ``fsma``) so the assertions
still run when the connected database already has ``fsma.cte_kdes`` from a
prior migration step. The SQL under test is rewritten only for that schema
name; the predicate and cast logic are unchanged.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.migrations.rls_db import rls_postgres_or_skip

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_edi_event_time_mismatch.py"
_spec = importlib.util.spec_from_file_location("check_edi_event_time_mismatch", _SCRIPT)
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)  # type: ignore[union-attr]


def _sql_for_schema(sql: str, schema: str) -> str:
    """Point the diagnostic SQL at a disposable schema instead of ``fsma``."""
    return sql.replace("fsma.", f"{schema}.")


def test_mismatch_sql_extracts_jsonb_scalar_text() -> None:
    sql = check.MISMATCH_SQL
    assert "#>> '{}'" in sql
    assert "CAST(k.kde_value" not in sql
    assert "k.kde_value ~" not in sql
    assert "e.source LIKE 'edi%'" in sql
    assert "to_date" not in sql
    assert "CASE WHEN" in sql
    assert "to_date" not in check.INVALID_DATE_SQL


def test_mismatch_sql_counts_against_real_jsonb_column() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    day = (now - timedelta(days=10)).date()
    day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    tenant = uuid.uuid4()
    schema = f"edi_mismatch_{uuid.uuid4().hex[:12]}"
    mismatch_sql = _sql_for_schema(check.MISMATCH_SQL, schema)
    invalid_sql = _sql_for_schema(check.INVALID_DATE_SQL, schema)
    with rls_postgres_or_skip() as (_url, engine):
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                conn.execute(text(f"CREATE SCHEMA {schema}"))
                conn.execute(
                    text(
                        f"CREATE TABLE {schema}.cte_events (id uuid PRIMARY KEY, tenant_id uuid NOT NULL,"
                        " event_timestamp timestamptz NOT NULL, source text NOT NULL)"
                    )
                )
                conn.execute(
                    text(
                        f"CREATE TABLE {schema}.cte_kdes (cte_event_id uuid NOT NULL, tenant_id uuid NOT NULL,"
                        " kde_key text NOT NULL, kde_value jsonb)"
                    )
                )

                def add(ts: datetime, kdes: dict, source: str = "edi_inbound") -> None:
                    eid = uuid.uuid4()
                    conn.execute(
                        text(f"INSERT INTO {schema}.cte_events VALUES (:i, :t, :ts, :s)"),
                        {"i": eid, "t": tenant, "ts": ts, "s": source},
                    )
                    for k, v in kdes.items():
                        conn.execute(
                            text(f"INSERT INTO {schema}.cte_kdes VALUES (:i, :t, :k, CAST(:v AS jsonb))"),
                            {"i": eid, "t": tenant, "k": k, "v": json.dumps(v)},
                        )

                iso = day.isoformat()
                # Agrees: timestamp inside the event day.
                add(day_start + timedelta(hours=12), {"ship_date": iso})
                # Disagrees by ingest-time drift; both date KDEs -> counted once.
                add(now, {"ship_date": iso, "event_date": iso})
                # Disagrees, event_date only.
                add(day_start - timedelta(days=3), {"event_date": iso})
                # Non-EDI source with a mismatch must not inflate the EDI count.
                add(now, {"ship_date": iso}, source="webhook")
                # Calendar-invalid ISO-looking date must be counted as invalid, not abort.
                add(now, {"ship_date": "2026-02-30"})
                add(now, {"event_date": "2024-02-30"})  # also invalid
                add(now, {"ship_date": "1900-02-29"})  # century non-leap
                # Non-date JSONB values are ignored, not cast errors.
                add(now, {"ship_date": "not-a-date"})
                add(now, {"event_date": {"nested": iso}})
                add(now, {"ship_date": None})

                count = conn.execute(text(mismatch_sql)).scalar()
                assert count == 2
                invalid = conn.execute(text(invalid_sql)).scalar()
                assert invalid == 3
                # Valid leap day must not be counted as invalid, and must not abort.
                leap = uuid.uuid4()
                conn.execute(
                    text(f"INSERT INTO {schema}.cte_events VALUES (:i, :t, :ts, :s)"),
                    {"i": leap, "t": tenant, "ts": now, "s": "edi_inbound"},
                )
                conn.execute(
                    text(f"INSERT INTO {schema}.cte_kdes VALUES (:i, :t, :k, CAST(:v AS jsonb))"),
                    {"i": leap, "t": tenant, "k": "ship_date", "v": json.dumps("2024-02-29")},
                )
                assert conn.execute(text(invalid_sql)).scalar() == 3
                # Python-side helper still agrees for a single valid ship_date row.
                rows = conn.execute(
                    text(
                        f"SELECT e.event_timestamp, "
                        f"(CASE WHEN {check._CALENDAR_VALID_ISO_DATE} "
                        f"THEN ((k.kde_value #>> '{{}}')::date) ELSE NULL END) "
                        f"FROM {schema}.cte_events e"
                        f" JOIN {schema}.cte_kdes k ON k.cte_event_id = e.id AND k.kde_key = 'ship_date'"
                        f" WHERE e.source LIKE 'edi%'"
                        f" AND {check._CALENDAR_VALID_ISO_DATE}"
                    )
                ).all()
                # One agreeing ship_date event + one disagreeing (ingest drift) + leap disagreeing.
                assert check.count_mismatches(rows) >= 1
            finally:
                trans.rollback()
