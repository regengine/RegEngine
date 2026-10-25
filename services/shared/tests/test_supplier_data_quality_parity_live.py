"""Summary/drilldown parity for supplier data quality, against real Postgres.

The all-facility summary and the one-facility drilldown must count the same
lots and records for a facility, with and without a facility filter. A lot
whose only recent record sits at another facility (#3597 follow-up) is the
case that broke this.

Requires a Postgres ``DATABASE_URL``. Everything runs in one transaction
with temp tables and is rolled back, so no real rows are touched.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from shared.supplier_data_quality import (
    METRIC_LATE_CTE,
    METRIC_MISSING_KDE,
    METRIC_UNLINKED_LOT,
    fetch_lot_rows,
    fetch_record_rows,
    flag_records,
    group_lots,
    summarize_facility,
    unlinked_lots,
)
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="Postgres DATABASE_URL required",
)

TENANT = "00000000-0000-4000-8000-0000000000a1"
SUPPLIER = "00000000-0000-4000-8000-0000000000b1"
OTHER_SUPPLIER = "00000000-0000-4000-8000-0000000000b2"
F_OLD = "00000000-0000-4000-8000-0000000000f1"
F_NEW = "00000000-0000-4000-8000-0000000000f2"
LOT_CROSS = "00000000-0000-4000-8000-0000000000c1"
LOT_LOCAL = "00000000-0000-4000-8000-0000000000c2"
LOT_FOREIGN = "00000000-0000-4000-8000-0000000000c3"

_SCHEMA = """
CREATE TEMP TABLE supplier_traceability_lots (
    id uuid PRIMARY KEY, tenant_id uuid, supplier_user_id uuid,
    facility_id uuid, tlc_code text
) ON COMMIT DROP;
CREATE TEMP TABLE supplier_cte_events (
    id uuid PRIMARY KEY, tenant_id uuid, supplier_user_id uuid,
    facility_id uuid, lot_id uuid, cte_type text, kde_data jsonb,
    event_time timestamptz, created_at timestamptz
) ON COMMIT DROP;
CREATE SCHEMA IF NOT EXISTS fsma;
CREATE TABLE IF NOT EXISTS fsma.transformation_links (tenant_id uuid, output_tlc text);
"""


@pytest.fixture()
def db():
    engine = create_engine(DATABASE_URL)
    conn = engine.connect()
    trans = conn.begin()
    try:
        for stmt in filter(None, (s.strip() for s in _SCHEMA.split(";"))):
            conn.execute(text(stmt))
        yield conn
    finally:
        trans.rollback()
        conn.close()
        engine.dispose()


def _seed(conn, now: datetime) -> None:
    lots = [
        (LOT_CROSS, SUPPLIER, F_OLD, "TLC-CROSS"),
        (LOT_LOCAL, SUPPLIER, F_NEW, "TLC-LOCAL"),
        (LOT_FOREIGN, SUPPLIER, F_OLD, "TLC-FOREIGN"),
    ]
    for lot_id, uid, fid, tlc in lots:
        conn.execute(
            text(
                "INSERT INTO supplier_traceability_lots VALUES "
                "(CAST(:id AS uuid), CAST(:tid AS uuid), CAST(:uid AS uuid), CAST(:fid AS uuid), :tlc)"
            ),
            {"id": lot_id, "tid": TENANT, "uid": uid, "fid": fid, "tlc": tlc},
        )
    events = [
        # Only recent record of the F_OLD lot is at F_NEW.
        ("00000000-0000-4000-8000-0000000000e1", SUPPLIER, F_NEW, LOT_CROSS, now - timedelta(hours=1)),
        ("00000000-0000-4000-8000-0000000000e2", SUPPLIER, F_NEW, LOT_LOCAL, now - timedelta(hours=2)),
        # Another supplier's record must not activate the caller's lot.
        ("00000000-0000-4000-8000-0000000000e3", OTHER_SUPPLIER, F_OLD, LOT_FOREIGN, now - timedelta(hours=1)),
    ]
    for eid, uid, fid, lot_id, created in events:
        conn.execute(
            text(
                "INSERT INTO supplier_cte_events VALUES (CAST(:id AS uuid), CAST(:tid AS uuid), "
                "CAST(:uid AS uuid), CAST(:fid AS uuid), CAST(:lot AS uuid), 'shipping', "
                "CAST('{}' AS jsonb), :t, :t)"
            ),
            {"id": eid, "tid": TENANT, "uid": uid, "fid": fid, "lot": lot_id, "t": created},
        )


def _numerators(records, lots) -> dict:
    summary = summarize_facility(records, lots, None, (0, 0))
    return {
        "records": len(records),
        "missing_kde": len(flag_records(records)),
        "lots": len(group_lots(lots)),
        "unlinked": sorted(lot["lot_id"] for lot in unlinked_lots(lots)),
        METRIC_MISSING_KDE: summary[METRIC_MISSING_KDE],
        METRIC_UNLINKED_LOT: summary[METRIC_UNLINKED_LOT],
        METRIC_LATE_CTE: summary[METRIC_LATE_CTE],
    }


def _scoped(conn, fids, since, key):
    records = [r for r in fetch_record_rows(conn, TENANT, SUPPLIER, fids, since) if str(r["facility_id"]) == key]
    lots = [r for r in fetch_lot_rows(conn, TENANT, SUPPLIER, fids, since) if str(r["facility_id"]) == key]
    return _numerators(records, lots)


@pytest.mark.parametrize("facility", [F_OLD, F_NEW])
def test_summary_equals_drilldown_with_and_without_facility_filter(db, facility):
    now = datetime.now(timezone.utc)
    _seed(db, now)
    since = now - timedelta(days=7)

    summary = _scoped(db, [F_OLD, F_NEW], since, facility)  # no filter: all owned facilities
    drilldown = _scoped(db, [facility], since, facility)  # facility filter

    assert summary == drilldown


def test_cross_facility_lot_is_counted_once_under_its_own_facility(db):
    now = datetime.now(timezone.utc)
    _seed(db, now)
    since = now - timedelta(days=7)

    old = _scoped(db, [F_OLD], since, F_OLD)
    new = _scoped(db, [F_NEW], since, F_NEW)
    assert old["unlinked"] == [LOT_CROSS]
    assert new["unlinked"] == [LOT_LOCAL]
    # The other supplier's record never activates LOT_FOREIGN.
    assert LOT_FOREIGN not in old["unlinked"] + new["unlinked"]
