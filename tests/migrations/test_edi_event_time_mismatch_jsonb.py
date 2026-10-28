"""Run the EDI event-time mismatch query against a real JSONB ``kde_value``.

``fsma.cte_kdes.kde_value`` has been JSONB since migration v078, so the
query in ``scripts/check_edi_event_time_mismatch.py`` must extract the scalar
text (``#>> '{}'``) before its regex match and date cast. This test builds a
minimal ``fsma.cte_events`` / ``fsma.cte_kdes`` pair with a JSONB column in a
disposable Postgres (``rls_postgres_or_skip``: the CI service container or a
testcontainers Postgres), runs ``MISMATCH_SQL`` inside a transaction and rolls
it back. It never runs the script itself and never touches a real database.
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


def test_mismatch_sql_extracts_jsonb_scalar_text() -> None:
    sql = check.MISMATCH_SQL
    assert "#>> '{}'" in sql
    assert "CAST(k.kde_value" not in sql
    assert "k.kde_value ~" not in sql
    assert "e.source LIKE 'edi%'" in sql
    assert "to_date" in sql


def test_mismatch_sql_counts_against_real_jsonb_column() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    day = (now - timedelta(days=10)).date()
    day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    tenant = uuid.uuid4()
    with rls_postgres_or_skip() as (_url, engine):
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                exists = conn.execute(text("SELECT to_regclass('fsma.cte_kdes')")).scalar()
                if exists is not None:
                    pytest.skip("fsma.cte_kdes already exists in this database; not seeding a shared schema")
                conn.execute(text("CREATE SCHEMA fsma"))
                conn.execute(
                    text(
                        "CREATE TABLE fsma.cte_events (id uuid PRIMARY KEY, tenant_id uuid NOT NULL,"
                        " event_timestamp timestamptz NOT NULL, source text NOT NULL)"
                    )
                )
                conn.execute(
                    text(
                        "CREATE TABLE fsma.cte_kdes (cte_event_id uuid NOT NULL, tenant_id uuid NOT NULL,"
                        " kde_key text NOT NULL, kde_value jsonb)"
                    )
                )

                def add(ts: datetime, kdes: dict, source: str = "edi_inbound") -> None:
                    eid = uuid.uuid4()
                    conn.execute(
                        text("INSERT INTO fsma.cte_events VALUES (:i, :t, :ts, :s)"),
                        {"i": eid, "t": tenant, "ts": ts, "s": source},
                    )
                    for k, v in kdes.items():
                        conn.execute(
                            text("INSERT INTO fsma.cte_kdes VALUES (:i, :t, :k, CAST(:v AS jsonb))"),
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
                # Calendar-invalid ISO-looking date must be skipped, not abort.
                add(now, {"ship_date": "2026-02-30"})
                # Non-date JSONB values are ignored, not cast errors.
                add(now, {"ship_date": "not-a-date"})
                add(now, {"event_date": {"nested": iso}})
                add(now, {"ship_date": None})

                count = conn.execute(text(check.MISMATCH_SQL)).scalar()
                assert count == 2
                invalid = conn.execute(text(check.INVALID_DATE_SQL)).scalar()
                assert invalid == 1
                rows = conn.execute(
                    text(
                        "SELECT e.event_timestamp, to_date((k.kde_value #>> '{}'), 'YYYY-MM-DD') "
                        "FROM fsma.cte_events e"
                        " JOIN fsma.cte_kdes k ON k.cte_event_id = e.id AND k.kde_key = 'ship_date'"
                        " WHERE e.source LIKE 'edi%'"
                        " AND (k.kde_value #>> '{}') ~ '^\\d{4}-\\d{2}-\\d{2}$'"
                        " AND to_char(to_date((k.kde_value #>> '{}'), 'YYYY-MM-DD'), 'YYYY-MM-DD')"
                        "     = (k.kde_value #>> '{}')"
                    )
                ).all()
                assert check.count_mismatches(rows) == 1
            finally:
                trans.rollback()
