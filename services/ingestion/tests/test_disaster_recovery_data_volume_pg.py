"""DR data-volume check must read the canonical event store — live Postgres.

``disaster_recovery._check_data_volume`` sizes a tenant's data for the
recovery-time estimate. Its statement read ``fsma.events`` — a table no
migration creates — and aggregated ``MAX(event_time)`` / ``MIN(event_time)``,
a column the canonical store ``fsma.traceability_events`` does not have (the
timestamp column is ``event_timestamp``). Postgres raised ``UndefinedTable``
(SQLSTATE 42P01), the function caught ``SQLAlchemyError``, logged at DEBUG
and returned its ``warn`` branch, so the check never reported real numbers.

The unit tests in ``test_disaster_recovery_1342.py`` run against a fake
session that never parses the SQL, so they passed throughout. This module
runs the real statement against a real cluster at alembic head.

Skips cleanly when no migrated Postgres is reachable, except under
``REGENGINE_REQUIRE_DB=1`` where an unreachable database fails rather than
skipping (#2530).
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from shared.db_url import sync_postgres_url

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

DSN = os.environ.get(
    "REMEDIATION_TEST_SUPERUSER_DSN",
    "postgresql://regengine:regengine@localhost:55432/regengine",  # pragma: allowlist secret — throwaway scratch-DB role
)

FIRST_EVENT = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
SPAN_DAYS = 10


def _schema_ready(dsn: str) -> bool:
    """True when a migrated database carrying the canonical event store is up."""
    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(sync_postgres_url(dsn), pool_pre_ping=True)
        with engine.connect() as conn:
            found = conn.execute(text("SELECT to_regclass('fsma.traceability_events') IS NOT NULL")).scalar()
        engine.dispose()
        return bool(found)
    except Exception:
        return False


_DB_READY = _schema_ready(DSN)

if not _DB_READY and os.environ.get("REGENGINE_REQUIRE_DB") == "1":
    raise RuntimeError(f"REGENGINE_REQUIRE_DB=1 but no migrated Postgres is reachable at {DSN!r} — refusing to skip.")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _DB_READY, reason="migrated Postgres with fsma schema not available"),
]


@pytest.fixture()
def seeded_tenants():
    """Three events over two lots for one tenant, one event for another, then clean up."""
    from sqlalchemy import create_engine, text

    engine = create_engine(sync_postgres_url(DSN))
    tenant_id, other_tenant_id = str(uuid.uuid4()), str(uuid.uuid4())
    last_event = FIRST_EVENT + timedelta(days=SPAN_DAYS)
    rows = [
        {"tid": tenant_id, "ts": FIRST_EVENT, "tlc": "DR-LOT-001"},
        {"tid": tenant_id, "ts": FIRST_EVENT + timedelta(days=1), "tlc": "DR-LOT-001"},
        {"tid": tenant_id, "ts": last_event, "tlc": "DR-LOT-002"},
        # Outside the tenant's lots and date range: any leak changes every number.
        {"tid": other_tenant_id, "ts": last_event + timedelta(days=90), "tlc": "DR-LOT-OTHER"},
    ]

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO fsma.traceability_events
                    (tenant_id, source_system, event_type, event_timestamp,
                     traceability_lot_code, quantity, unit_of_measure)
                VALUES (:tid, 'pytest', 'receiving', :ts, :tlc, 1, 'kg')
                """
            ),
            rows,
        )

    try:
        yield engine, tenant_id
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM fsma.traceability_events WHERE tenant_id IN (:tid, :other)"),
                {"tid": tenant_id, "other": other_tenant_id},
            )
        engine.dispose()


def test_data_volume_counts_the_tenants_canonical_events(seeded_tenants, monkeypatch):
    """Three events, two lots, ten days: the check passes with exactly those numbers.

    The other tenant's event sits on a third lot 90 days later, so a
    statement that lost its tenant filter would report 4 / 3 / 100.
    """
    from app import disaster_recovery as dr
    from sqlalchemy.orm import sessionmaker

    engine, tenant_id = seeded_tenants
    monkeypatch.setattr(dr, "get_db_safe", sessionmaker(bind=engine))

    check, info = dr._check_data_volume(tenant_id)

    assert check.status == "pass", check.details
    assert info == {"total_events": 3, "total_tlcs": 2, "date_range_days": SPAN_DAYS}


def test_data_volume_for_a_tenant_with_no_events_is_empty_not_an_error(seeded_tenants, monkeypatch):
    """A tenant with no rows gets the "no events" result while other tenants have data."""
    from app import disaster_recovery as dr
    from sqlalchemy.orm import sessionmaker

    engine, _ = seeded_tenants
    monkeypatch.setattr(dr, "get_db_safe", sessionmaker(bind=engine))

    check, info = dr._check_data_volume(str(uuid.uuid4()))

    assert check.status == "warn"
    assert check.details == "No events found for tenant"
    assert info == {"total_events": 0, "total_tlcs": 0, "date_range_days": 0}
