"""DR hash-chain, export and KDE checks must run real statements — live Postgres.

Three statements in ``disaster_recovery`` named tables or columns that do not
exist, so Postgres rejected them, the function caught ``SQLAlchemyError``,
logged at DEBUG and returned its ``warn`` branch:

- ``_check_hash_chain_integrity`` read ``prev_hash`` / ``seq``; the columns of
  ``fsma.hash_chain`` are ``previous_chain_hash`` / ``sequence_num``. A tenant
  with a broken chain was never reported as ``fail``.
- ``_check_export_completeness`` read ``fsma.export_logs`` / ``created_at``;
  the table is ``fsma.fda_export_log`` and its timestamp is ``generated_at``.
- The recovery simulation's KDE check read ``AVG(kde_completeness) FROM
  fsma.events``. Neither exists. It now reuses the compliance score's
  required-KDE coverage read over ``fsma.cte_events`` / ``fsma.cte_kdes``.

The unit tests in ``test_disaster_recovery_1342.py`` run against a fake
session that never parses the SQL, so they passed throughout. This module
runs the real statements against a real cluster at alembic head. Every test
seeds a second tenant whose rows would change the result if a statement lost
its tenant filter.

Skips cleanly when no migrated Postgres is reachable, except under
``REGENGINE_REQUIRE_DB=1`` where an unreachable database fails rather than
skipping (#2530).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from shared.db_url import sync_postgres_url

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

DSN = os.environ.get(
    "REMEDIATION_TEST_SUPERUSER_DSN",
    "postgresql://regengine:regengine@localhost:55432/regengine",  # pragma: allowlist secret — throwaway scratch-DB role
)


def _schema_ready(dsn: str) -> bool:
    """True when a migrated database carrying the tables these checks read is up."""
    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(sync_postgres_url(dsn), pool_pre_ping=True)
        with engine.connect() as conn:
            found = conn.execute(
                text(
                    "SELECT to_regclass('fsma.hash_chain') IS NOT NULL "
                    "AND to_regclass('fsma.fda_export_log') IS NOT NULL "
                    "AND to_regclass('fsma.cte_kdes') IS NOT NULL"
                )
            ).scalar()
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
def conn(monkeypatch):
    """A connection whose transaction is rolled back, with the DR module's sessions bound to it.

    ``fsma.hash_chain`` and ``fsma.cte_events`` are append-only (triggers
    reject DELETE), so seeded rows cannot be cleaned up afterwards. They are
    never committed instead: each DR check runs in a savepoint of this
    transaction, sees the seeded rows, and the whole transaction is rolled
    back at teardown.
    """
    from app import disaster_recovery as dr
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(sync_postgres_url(DSN))
    with engine.connect() as connection:
        outer = connection.begin()
        monkeypatch.setattr(
            dr,
            "get_db_safe",
            sessionmaker(bind=connection, join_transaction_mode="create_savepoint"),
        )
        try:
            yield connection
        finally:
            outer.rollback()
    engine.dispose()


# ---------------------------------------------------------------------------
# _check_hash_chain_integrity
# ---------------------------------------------------------------------------


def _seed_chain(conn, tenant_id: str, previous_hashes: list) -> None:
    """One chain entry per element, numbered from 1, with that ``previous_chain_hash``."""
    from sqlalchemy import text

    conn.execute(
        text(
            """
            INSERT INTO fsma.hash_chain
                (tenant_id, cte_event_id, sequence_num, event_hash, previous_chain_hash, chain_hash)
            VALUES (:tid, :event_id, :seq, :event_hash, :prev, :chain_hash)
            """
        ),
        [
            {
                "tid": tenant_id,
                "event_id": str(uuid.uuid4()),
                "seq": seq,
                "event_hash": f"event-{seq}",
                "prev": prev,
                "chain_hash": f"chain-{seq}",
            }
            for seq, prev in enumerate(previous_hashes, start=1)
        ],
    )


@pytest.fixture()
def chains(conn):
    """An intact three-entry chain for one tenant and a two-entry chain with a gap for another."""
    intact_tenant, broken_tenant = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_chain(conn, intact_tenant, [None, "chain-1", "chain-2"])  # NULL at sequence 1 is GENESIS
    _seed_chain(conn, broken_tenant, [None, None])  # NULL at sequence 2 is a gap
    return intact_tenant, broken_tenant


def test_hash_chain_intact_for_the_tenant(chains):
    """Three linked entries pass. A lost tenant filter would report 5 entries and 1 gap."""
    from app import disaster_recovery as dr

    intact_tenant, _ = chains

    check = dr._check_hash_chain_integrity(intact_tenant)

    assert check.status == "pass", check.details
    assert check.details == "Hash chain intact — 3 entries, 0 gaps"


def test_hash_chain_gap_is_reported_as_fail(chains):
    """An entry past sequence 1 with no previous hash fails the check."""
    from app import disaster_recovery as dr

    _, broken_tenant = chains

    check = dr._check_hash_chain_integrity(broken_tenant)

    assert check.status == "fail", check.details
    assert check.details == "Hash chain has 1 gap(s) in 2 entries"


def test_hash_chain_for_a_tenant_with_no_entries_is_empty_not_an_error(chains):
    """A tenant with no rows gets the "no records" result while other tenants have chains."""
    from app import disaster_recovery as dr

    check = dr._check_hash_chain_integrity(str(uuid.uuid4()))

    assert check.status == "warn"
    assert check.details == "No hash chain records found for tenant"


# ---------------------------------------------------------------------------
# _check_export_completeness
# ---------------------------------------------------------------------------


@pytest.fixture()
def exports(conn):
    """Two recent exports and one old export for one tenant; another tenant's export is the newest."""
    from sqlalchemy import text

    now = datetime.now(timezone.utc).replace(microsecond=0)
    tenant_id, other_tenant_id, stale_tenant_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    latest = now - timedelta(days=1)
    rows = [
        {"tid": tenant_id, "at": latest},
        {"tid": tenant_id, "at": now - timedelta(days=3)},
        {"tid": tenant_id, "at": now - timedelta(days=30)},  # outside the 7-day window
        # Newer than every export above: any leak changes both the count and the latest time.
        {"tid": other_tenant_id, "at": now - timedelta(hours=1)},
        {"tid": stale_tenant_id, "at": now - timedelta(days=30)},
    ]
    conn.execute(
        text(
            """
            INSERT INTO fsma.fda_export_log (tenant_id, export_hash, generated_at)
            VALUES (:tid, 'pytest-dr-readiness', :at)
            """
        ),
        rows,
    )
    return tenant_id, stale_tenant_id, latest


def test_export_completeness_counts_the_tenants_recent_exports(exports):
    """Two exports inside 7 days pass. A lost tenant filter would report 3 and a newer latest time."""
    from app import disaster_recovery as dr

    tenant_id, _, latest = exports

    check = dr._check_export_completeness(tenant_id)

    assert check.status == "pass", check.details
    count_part, latest_part = check.details.split(", latest: ")
    assert count_part == "2 export(s) in last 7 days"
    assert datetime.fromisoformat(latest_part) == latest


def test_export_completeness_ignores_exports_older_than_seven_days(exports):
    """A tenant whose only export is 30 days old is told it has no recent export."""
    from app import disaster_recovery as dr

    _, stale_tenant_id, _ = exports

    check = dr._check_export_completeness(stale_tenant_id)

    assert check.status == "warn"
    assert check.details == "No exports in the last 7 days"


# ---------------------------------------------------------------------------
# kde_recovery_completeness (recovery simulation)
# ---------------------------------------------------------------------------

# Required shipping KDEs stored as columns of fsma.cte_events; the rest are fsma.cte_kdes rows.
EVENT_COLUMN_KDES = {"traceability_lot_code", "product_description", "quantity", "unit_of_measure"}


def _seed_shipping_event(conn, tenant_id: str, kde_keys: list) -> None:
    """One shipping event carrying the column KDEs plus a ``fsma.cte_kdes`` row per key."""
    from sqlalchemy import text

    event_id = str(uuid.uuid4())
    conn.execute(
        text(
            """
            INSERT INTO fsma.cte_events
                (id, tenant_id, event_type, traceability_lot_code, product_description,
                 quantity, unit_of_measure, event_timestamp, sha256_hash, chain_hash)
            VALUES (:id, :tid, 'shipping', 'DR-LOT-001', 'Romaine', 1, 'kg', now(), :hash, :hash)
            """
        ),
        {"id": event_id, "tid": tenant_id, "hash": uuid.uuid4().hex},
    )
    if kde_keys:
        conn.execute(
            text(
                """
                INSERT INTO fsma.cte_kdes (tenant_id, cte_event_id, kde_key, kde_value)
                VALUES (:tid, :event_id, :key, to_jsonb(CAST(:value AS text)))
                """
            ),
            [{"tid": tenant_id, "event_id": event_id, "key": key, "value": "pytest"} for key in kde_keys],
        )


@pytest.fixture()
def shipping_events(conn):
    """Two complete shipping events for one tenant; another tenant's event has column KDEs only."""
    from app.compliance_score import _required_fields_for

    required = _required_fields_for("shipping")
    row_kdes = [field for field in required if field not in EVENT_COLUMN_KDES]
    assert EVENT_COLUMN_KDES <= set(required) and row_kdes  # the seed below still matches the checklist

    complete_tenant, sparse_tenant = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_shipping_event(conn, complete_tenant, row_kdes)
    _seed_shipping_event(conn, complete_tenant, row_kdes)
    _seed_shipping_event(conn, sparse_tenant, [])
    return complete_tenant, sparse_tenant, len(required)


def _kde_check(tenant_id: str):
    from app import disaster_recovery as dr

    report = asyncio.run(dr.test_recovery(tenant_id, ctx=SimpleNamespace(tenant_id=tenant_id)))
    return next(check for check in report.checks if check.name == "kde_recovery_completeness")


def test_kde_completeness_scores_the_tenants_required_fields(shipping_events):
    """Two complete events score 100%. A lost tenant filter would pull in the sparse event."""
    complete_tenant, _, required = shipping_events

    check = _kde_check(complete_tenant)

    assert check.status == "pass", check.details
    assert check.details == f"Required KDE completeness: 100.0% ({2 * required}/{2 * required} fields present)"


def test_kde_completeness_below_threshold_warns(shipping_events):
    """An event carrying only its column KDEs is scored against the full required set."""
    _, sparse_tenant, required = shipping_events
    present = len(EVENT_COLUMN_KDES)
    assert present / required < 0.8  # the seed is below the pass threshold

    check = _kde_check(sparse_tenant)

    assert check.status == "warn", check.details
    assert check.details == (
        f"Required KDE completeness: {present / required * 100:.1f}% ({present}/{required} fields present)"
    )


def test_kde_completeness_for_a_tenant_with_no_events_is_empty_not_an_error(shipping_events):
    """A tenant with no rows gets the "no data" result while other tenants have events."""
    check = _kde_check(str(uuid.uuid4()))

    assert check.status == "warn"
    assert check.details == "No KDE completeness data available"
