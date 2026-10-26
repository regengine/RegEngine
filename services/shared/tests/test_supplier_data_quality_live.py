"""Postgres regression for lot facility attribution and caller-scoped activity.

Requires a migrated Postgres DATABASE_URL. All test rows live in temporary
tables created and discarded within one rolled-back transaction.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from shared.db_url import sync_postgres_url
from shared.supplier_data_quality import METRIC_UNLINKED_LOT, fetch_lot_rows, fetch_supplier_quality, unlinked_lots
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(not DATABASE_URL.startswith("postgresql"), reason="Postgres DATABASE_URL required")


def test_lot_attributed_to_its_facility_when_callers_record_is_elsewhere() -> None:
    engine = create_engine(sync_postgres_url(DATABASE_URL))
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        try:
            tables = session.execute(
                text(
                    """
                    SELECT to_regclass('public.supplier_traceability_lots'),
                           to_regclass('public.supplier_cte_events'),
                           to_regclass('fsma.transformation_links')
                    """
                )
            ).one()
        except OperationalError:
            pytest.skip("Postgres DATABASE_URL is unavailable")
        if any(table is None for table in tables):
            pytest.skip("supplier lot, CTE, or transformation-link table is not migrated")
        link_tenant_type = session.execute(
            text(
                """
                SELECT data_type FROM information_schema.columns
                 WHERE table_schema = 'fsma'
                   AND table_name = 'transformation_links'
                   AND column_name = 'tenant_id'
                """
            )
        ).scalar_one_or_none()
        if (
            link_tenant_type != "uuid"
            or not session.execute(
                text("SELECT has_table_privilege('fsma.transformation_links', 'SELECT')")
            ).scalar_one()
        ):
            pytest.skip("UUID tenant-scoped transformation links are not readable")

        # The temp tables shadow public tables, avoiding real FK parents and RLS writes.
        session.execute(
            text(
                """
                CREATE TEMP TABLE supplier_traceability_lots (
                    id UUID, tenant_id UUID, supplier_user_id UUID,
                    facility_id UUID, tlc_code TEXT
                )
                """
            )
        )
        session.execute(
            text(
                """
                CREATE TEMP TABLE supplier_cte_events (
                    id UUID, tenant_id UUID, supplier_user_id UUID,
                    facility_id UUID, lot_id UUID, cte_type TEXT,
                    event_time TIMESTAMPTZ, kde_data JSONB, created_at TIMESTAMPTZ
                )
                """
            )
        )

        tenant_id = str(uuid.uuid4())
        caller_id = str(uuid.uuid4())
        other_supplier_id = str(uuid.uuid4())
        f_old = str(uuid.uuid4())
        f_new = str(uuid.uuid4())
        lot_id = str(uuid.uuid4())
        lot_code = str(uuid.uuid4())
        since = datetime.now(timezone.utc)
        session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_id})
        session.execute(
            text(
                """
                INSERT INTO supplier_traceability_lots
                    (id, tenant_id, supplier_user_id, facility_id, tlc_code)
                VALUES (CAST(:id AS uuid), CAST(:tid AS uuid), CAST(:uid AS uuid),
                        CAST(:fid AS uuid), :code)
                """
            ),
            {"id": lot_id, "tid": tenant_id, "uid": caller_id, "fid": f_old, "code": lot_code},
        )
        event_sql = text(
            """
            INSERT INTO supplier_cte_events
                (id, tenant_id, supplier_user_id, facility_id, lot_id,
                 cte_type, event_time, kde_data, created_at)
            VALUES (CAST(:id AS uuid), CAST(:tid AS uuid), CAST(:uid AS uuid),
                    CAST(:fid AS uuid), CAST(:lot AS uuid),
                    'shipping', :received, '{}'::jsonb, :received)
            """
        )
        session.execute(
            event_sql,
            {
                "id": str(uuid.uuid4()),
                "tid": tenant_id,
                "uid": other_supplier_id,
                "fid": f_new,
                "lot": lot_id,
                "received": datetime.now(timezone.utc),
            },
        )
        assert fetch_lot_rows(session, tenant_id, caller_id, [f_old, f_new], since) == []
        assert fetch_lot_rows(session, tenant_id, caller_id, [f_old], since) == []

        caller_record_id = str(uuid.uuid4())
        session.execute(
            event_sql,
            {
                "id": caller_record_id,
                "tid": tenant_id,
                "uid": caller_id,
                "fid": f_new,
                "lot": lot_id,
                "received": datetime.now(timezone.utc),
            },
        )
        rows = fetch_lot_rows(session, tenant_id, caller_id, [f_old, f_new], since)
        drilldown_rows = fetch_lot_rows(session, tenant_id, caller_id, [f_old], since)
        assert len(rows) == len(drilldown_rows) == len({caller_record_id})
        assert {str(row["lot_id"]) for row in rows} == {lot_id}
        assert {str(row["facility_id"]) for row in rows + drilldown_rows} == {f_old}

        summary = fetch_supplier_quality(session, tenant_id, caller_id, [f_old, f_new], since, sending_hours={})
        drilldown = unlinked_lots(drilldown_rows)
        assert [lot["lot_id"] for lot in drilldown] == [lot_id]
        assert summary[f_old][METRIC_UNLINKED_LOT]["numerator"] == len(drilldown)
        assert summary[f_old][METRIC_UNLINKED_LOT]["denominator"] == len(drilldown)
        assert summary[f_new][METRIC_UNLINKED_LOT]["numerator"] == 0
    finally:
        session.rollback()
        session.close()
        engine.dispose()
