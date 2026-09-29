"""A calendar-day CTE query must not depend on the PostgreSQL timezone."""

from uuid import uuid4

import pytest
from shared.cte_persistence import CTEPersistence
from sqlalchemy import text

from services.ingestion.tests.test_cte_persistence_e2e import db_session, postgres_engine  # noqa: F401
from tests.shared.test_cte_persistence_hardening_v2 import FakeSession


def _query(persistence, path, tenant_id, start_date, end_date=None):
    if path == "all":
        events, total = persistence.query_all_events(tenant_id, start_date=start_date, end_date=end_date)
        assert total == len(events)
        return events
    if path == "single":
        return persistence.query_events_by_tlc(
            tenant_id, "UTC-LOT", start_date=start_date, end_date=end_date, follow_transformations=False
        )
    return persistence.query_events_by_tlcs(
        tenant_id, ["UTC-LOT"], start_date=start_date, end_date=end_date, follow_transformations=False
    )


@pytest.mark.parametrize("path", ["single", "batch", "all"])
@pytest.mark.parametrize("start_date", ["2026-03-01", "2026-03-08", "2028-02-29"])
def test_every_read_path_binds_an_explicit_inclusive_utc_start(path, start_date):
    session = FakeSession()

    _query(CTEPersistence(session), path, str(uuid4()), start_date, "2028-03-01")

    calls = [(sql, params) for sql, params in session.calls if "FROM fsma.cte_events" in sql]
    assert calls
    for sql, params in calls:
        assert "event_timestamp >= :start_date" in sql
        assert params["start_date"] == start_date + "T00:00:00+00:00"
        assert "event_timestamp < :end_date" in sql
        assert params["end_date"] == "2028-03-02T00:00:00+00:00"


@pytest.mark.parametrize("path", ["single", "batch", "all"])
@pytest.mark.parametrize(
    "raw",
    ["20260301", "2026-W09-7", "03/01/2026", "2026-02-30", "2026-03-01T04:30:00-08:00", "not-a-date"],
)
def test_other_start_syntax_is_not_silently_reinterpreted(path, raw):
    session = FakeSession()

    _query(CTEPersistence(session), path, str(uuid4()), raw)

    calls = [params for sql, params in session.calls if "FROM fsma.cte_events" in sql]
    assert calls
    assert all(params["start_date"] == raw for params in calls)


@pytest.mark.integration
@pytest.mark.parametrize("session_timezone", ["America/Los_Angeles", "Asia/Kolkata"])
@pytest.mark.parametrize("path", ["single", "batch", "all"])
def test_real_postgres_returns_exact_utc_day_in_each_session_timezone(db_session, session_timezone, path):
    """Exercise real stored timestamptz values and both half-open bounds."""
    tenant_id = str(uuid4())
    persistence = CTEPersistence(db_session)
    for label, timestamp in [
        ("before", "2026-02-28T23:59:59.999999+00:00"),
        ("inside-start", "2026-03-01T00:00:00+00:00"),
        ("inside-end", "2026-03-01T23:59:59.999999+00:00"),
        ("after", "2026-03-02T00:00:00+00:00"),
    ]:
        persistence.store_event(
            tenant_id=tenant_id,
            event_type="shipping",
            traceability_lot_code="UTC-LOT",
            product_description=label,
            quantity=1,
            unit_of_measure="cases",
            event_timestamp=timestamp,
            source="utc-boundary-regression",
        )
    db_session.commit()
    db_session.execute(text("SELECT set_config('TimeZone', :tz, true)"), {"tz": session_timezone})

    events = _query(persistence, path, tenant_id, "2026-03-01", "2026-03-01")

    assert sorted(event["product_description"] for event in events) == ["inside-end", "inside-start"]
