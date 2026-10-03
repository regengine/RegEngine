"""Audit export trail reads real fda_export_log columns — live Postgres.

``audit_export_log._query_exports`` read ``sha256_hash``, ``created_at``,
``traceability_lot_code`` and ``format`` from ``fsma.fda_export_log`` and
filtered and ordered on ``created_at``. The columns are ``export_hash``,
``generated_at`` and ``query_tlc`` (V002; no migration renamed them), and no
column records a file format. Postgres raised ``UndefinedColumn``, the broad
``except`` logged a warning and returned ``None``, and the export audit trail
and the activity feed showed no exports for any tenant.

The unit tests in ``test_audit_export_log_1342.py`` run against a fake
session that never parses the SQL, so they passed throughout. This module
runs the real statement against a real cluster at alembic head. Every test
seeds a second tenant whose newest export would change the result if the
statement lost its tenant filter.

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
    """True when a migrated database carrying the export log is up."""
    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(sync_postgres_url(dsn), pool_pre_ping=True)
        with engine.connect() as conn:
            found = conn.execute(text("SELECT to_regclass('fsma.fda_export_log') IS NOT NULL")).scalar()
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
    """A connection whose transaction is rolled back, with the module's sessions bound to it.

    Seeds are never committed: every read runs in a savepoint of this
    transaction and the whole transaction is rolled back at teardown.
    ``audit_export_log`` imports ``SessionLocal`` from ``shared.database`` at
    call time, so the attribute is patched there.
    """
    import shared.database as db_mod
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(sync_postgres_url(DSN))
    with engine.connect() as connection:
        outer = connection.begin()
        monkeypatch.setattr(
            db_mod,
            "SessionLocal",
            sessionmaker(bind=connection, join_transaction_mode="create_savepoint"),
        )
        try:
            yield connection
        finally:
            outer.rollback()
    engine.dispose()


@pytest.fixture()
def exports(conn):
    """Three exports for one tenant at 1, 3 and 30 days old; another tenant's export is the newest."""
    from sqlalchemy import text

    now = datetime.now(timezone.utc).replace(microsecond=0)
    tenant_id, other_tenant_id = str(uuid.uuid4()), str(uuid.uuid4())
    times = [now - timedelta(days=1), now - timedelta(days=3), now - timedelta(days=30)]
    rows = [
        {"tid": tenant_id, "etype": "fda_spreadsheet", "count": 10, "hash": "hash-1", "tlc": "LOT-A", "at": times[0]},
        {"tid": tenant_id, "etype": "fda_export_all", "count": 20, "hash": "hash-2", "tlc": None, "at": times[1]},
        {"tid": tenant_id, "etype": "fda_spreadsheet", "count": 0, "hash": "hash-3", "tlc": "LOT-B", "at": times[2]},
        # Newer than every export above: any leak puts it first and changes every count.
        {
            "tid": other_tenant_id,
            "etype": "recall",
            "count": 99,
            "hash": "hash-other",
            "tlc": "LOT-X",
            "at": now - timedelta(hours=1),
        },
    ]
    conn.execute(
        text(
            """
            INSERT INTO fsma.fda_export_log
                (tenant_id, export_type, record_count, export_hash, query_tlc, generated_at)
            VALUES (:tid, :etype, :count, :hash, :tlc, :at)
            """
        ),
        rows,
    )
    return tenant_id, times


def test_query_exports_returns_the_tenants_exports_newest_first(exports):
    """Three rows in generated_at order with hash, lot code and count from the real columns."""
    from app import audit_export_log as ael

    tenant_id, times = exports

    rows = ael._query_exports(tenant_id, None, None, 50)

    assert rows is not None
    assert [row["sha256_hash"] for row in rows] == ["hash-1", "hash-2", "hash-3"]
    assert [row["traceability_lot_code"] for row in rows] == ["LOT-A", None, "LOT-B"]
    assert [row["record_count"] for row in rows] == [10, 20, 0]
    assert [row["export_type"] for row in rows] == ["fda_spreadsheet", "fda_export_all", "fda_spreadsheet"]
    assert [datetime.fromisoformat(row["created_at"]) for row in rows] == times
    assert {row["tenant_id"] for row in rows} == {tenant_id}
    assert set(rows[0]) == {
        "id",
        "tenant_id",
        "export_type",
        "record_count",
        "sha256_hash",
        "created_at",
        "traceability_lot_code",
    }


def test_query_exports_date_filters_bound_generated_at(exports):
    """A 5-day-to-2-day window keeps only the 3-day-old export."""
    from app import audit_export_log as ael

    tenant_id, _ = exports
    now = datetime.now(timezone.utc)

    rows = ael._query_exports(
        tenant_id,
        (now - timedelta(days=5)).isoformat(),
        (now - timedelta(days=2)).isoformat(),
        50,
    )

    assert [row["sha256_hash"] for row in rows] == ["hash-2"]


def test_query_exports_honours_the_limit(exports):
    """Limit 1 returns the tenant's newest export, not the other tenant's 1-hour-old one."""
    from app import audit_export_log as ael

    tenant_id, _ = exports

    rows = ael._query_exports(tenant_id, None, None, 1)

    assert [row["sha256_hash"] for row in rows] == ["hash-1"]


def test_query_exports_for_a_tenant_with_no_exports_is_empty_not_none(exports):
    """A tenant with no rows gets an empty list (a real answer), not the "db unavailable" None."""
    from app import audit_export_log as ael

    assert ael._query_exports(str(uuid.uuid4()), None, None, 50) == []


def test_export_audit_trail_endpoint_serializes_the_rows(exports):
    """The endpoint builds ``ExportRecord`` rows from the real columns (UUIDs rendered as strings)."""
    from app import audit_export_log as ael

    tenant_id, times = exports

    response = asyncio.run(
        ael.query_export_audit_trail(
            tenant_id,
            request=ael.ExportQueryRequest(limit=2),
            ctx=SimpleNamespace(tenant_id=tenant_id),
        )
    )

    assert response.total == 2
    assert [record.sha256_hash for record in response.exports] == ["hash-1", "hash-2"]
    assert response.exports[0].tenant_id == tenant_id
    assert uuid.UUID(response.exports[0].id)
    assert datetime.fromisoformat(response.exports[0].created_at) == times[0]


def test_activity_feed_lists_the_tenants_exports(exports):
    """The combined feed carries one export entry per real row, newest first."""
    from app import audit_export_log as ael

    tenant_id, _ = exports

    feed = asyncio.run(ael.get_activity_feed(tenant_id, page=1, page_size=50, ctx=SimpleNamespace(tenant_id=tenant_id)))

    entries = [entry for entry in feed.activities if entry.activity_type == "export"]
    assert [entry.details["sha256_hash"] for entry in entries] == ["hash-1", "hash-2", "hash-3"]
    assert entries[0].summary == "FDA export: fda_spreadsheet — 10 records"
    assert entries[0].details["traceability_lot_code"] == "LOT-A"
