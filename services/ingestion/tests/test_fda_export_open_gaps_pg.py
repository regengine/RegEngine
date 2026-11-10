"""The FDA export's gap lookup against real ``public.data_gap_events`` rows.

The unit tests in ``test_fda_export_open_gaps.py`` run on a fake session that
never parses the SQL. This module runs the real statement at alembic head.

Skips cleanly when no migrated Postgres is reachable, except under
``REGENGINE_REQUIRE_DB=1`` where an unreachable database fails rather than
skipping (#2530).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from shared.data_gap_tracking import fetch_gaps_open_at
from shared.db_url import sync_postgres_url
from sqlalchemy import create_engine, text

DSN = os.environ.get(
    "REMEDIATION_TEST_SUPERUSER_DSN",
    "postgresql://regengine:regengine@localhost:55432/regengine",  # pragma: allowlist secret — throwaway scratch-DB role
)
RECEIPT = "a" * 64


def _schema_ready(dsn: str) -> bool:
    try:
        engine = create_engine(sync_postgres_url(dsn), pool_pre_ping=True)
        with engine.connect() as conn:
            found = conn.execute(text("SELECT to_regclass('public.data_gap_events') IS NOT NULL")).scalar()
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
def conn():
    """A connection whose transaction is rolled back, so seeds are never committed."""
    engine = create_engine(sync_postgres_url(DSN))
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            yield connection
        finally:
            outer.rollback()
    engine.dispose()


def _seed(conn, tenant_id: str, gap_key: str, opened_at: datetime, closed_at: datetime | None = None) -> None:
    conn.execute(
        text(
            """
            INSERT INTO public.data_gap_events
                (tenant_id, supplier_key, lot_code, cte_type, gap_kind, gap_key,
                 opened_at, closed_at, closing_record_id, closing_record_hash)
            VALUES (:tid, 'unassigned', 'LOT-1', 'shipping', 'missing_kde', :key,
                    :opened, :closed, :rid, :rhash)
            """
        ),
        {
            "tid": tenant_id,
            "key": gap_key,
            "opened": opened_at,
            "closed": closed_at,
            "rid": str(uuid.uuid4()) if closed_at else None,
            "rhash": RECEIPT if closed_at else None,
        },
    )


def test_gap_state_is_read_as_of_a_moment_for_one_tenant(conn) -> None:
    now = datetime.now(timezone.utc)
    tenant_id, other_tenant_id = str(uuid.uuid4()), str(uuid.uuid4())
    as_of = now - timedelta(days=1)

    _seed(conn, tenant_id, "open_then", now - timedelta(days=2))
    _seed(conn, tenant_id, "closed_since", now - timedelta(days=2), now - timedelta(hours=1))
    _seed(conn, tenant_id, "closed_before", now - timedelta(days=3), now - timedelta(days=2))
    _seed(conn, tenant_id, "opened_after", now - timedelta(hours=1))
    _seed(conn, other_tenant_id, "other_tenant", now - timedelta(days=2))

    gaps = fetch_gaps_open_at(conn, tenant_id, ["LOT-1"], as_of)

    assert gaps == {("LOT-1", "shipping"): ("missing_kde: closed_since", "missing_kde: open_then")}


def test_writer_persists_idempotent_gaps_and_receipt_for_only_its_tenant(conn):
    """Run the real writer SQL and read back durable state in a scratch DB.

    Outer test transaction is rolled back. PR 3816's deployment grant
    inventory is separately pinned by test_v142_data_gap_runtime_grants.py.
    """
    from shared.data_gap_tracking import Gap, ValidationOutcome, record_outcomes
    from sqlalchemy.orm import Session

    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    lot = "SYNTH-GAP-PERSIST-001"
    gap = Gap("missing_kde", "reference_document")
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        failed = ValidationOutcome(order=0, lot_code=lot, cte_type="shipping", gaps=(gap,))
        record_outcomes(session, tenant, [failed, failed])
        record_outcomes(session, other, [failed])
        rows = conn.execute(
            text("SELECT tenant_id::text, closed_at FROM public.data_gap_events WHERE lot_code=:lot"),
            {"lot": lot},
        ).fetchall()
        assert sorted(rows) == sorted([(tenant, None), (other, None)])
        receipt_id = str(uuid.uuid4())
        fixed = ValidationOutcome(
            order=1, lot_code=lot, cte_type="shipping", closing_record_id=receipt_id, closing_record_hash=RECEIPT
        )
        record_outcomes(session, tenant, [fixed])
        rows = conn.execute(
            text(
                "SELECT tenant_id::text, closed_at, closing_record_id::text, closing_record_hash "
                "FROM public.data_gap_events WHERE lot_code=:lot"
            ),
            {"lot": lot},
        ).fetchall()
        by_tenant = {row[0]: row[1:] for row in rows}
        assert by_tenant[tenant][0] is not None
        assert by_tenant[tenant][1:] == (receipt_id, RECEIPT)
        assert by_tenant[other] == (None, None, None)
    finally:
        session.close()
