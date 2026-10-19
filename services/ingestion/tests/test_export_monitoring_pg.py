"""Export monitoring reads real export-log columns and the required-KDE measure — live Postgres.

Two statements in ``export_monitoring`` named columns that do not exist, so
Postgres rejected them, the broad ``except`` returned ``None`` or a
``warning`` result, and the endpoints never reported real data:

- ``_query_export_logs`` read ``export_time_ms``, ``created_at`` and
  ``format`` from ``fsma.fda_export_log``. The timestamp is ``generated_at``;
  no column records an export's duration or file format. The metrics
  endpoint reported zero exports for every tenant and the stale-export
  alert never fired.
- ``_check_kde_completeness`` read ``kde_data`` from ``fsma.cte_events``.
  KDEs are ``fsma.cte_kdes`` rows. It now reuses the compliance score's
  required-KDE coverage read (#2962), as ``disaster_recovery`` does.

The unit tests in ``test_export_monitoring_1342.py`` run against a fake
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
                    "SELECT to_regclass('fsma.fda_export_log') IS NOT NULL AND to_regclass('fsma.cte_kdes') IS NOT NULL"
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
    """A connection whose transaction is rolled back, with the module's sessions bound to it.

    ``fsma.cte_events`` is append-only (a trigger rejects DELETE), so seeded
    rows cannot be cleaned up afterwards. They are never committed instead:
    each check runs in a savepoint of this transaction, sees the seeded rows,
    and the whole transaction is rolled back at teardown. ``export_monitoring``
    imports ``SessionLocal`` from ``shared.database`` at call time, so the
    attribute is patched there.
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


# ---------------------------------------------------------------------------
# _query_export_logs, GET /exports/{tenant_id}, GET /alerts/{tenant_id}
# ---------------------------------------------------------------------------


@pytest.fixture()
def exports(conn):
    """Three exports for one tenant (12 hours, 3 days and 30 days old); another tenant's export is the newest."""
    from sqlalchemy import text

    now = datetime.now(timezone.utc).replace(microsecond=0)
    tenant_id, other_tenant_id, stale_tenant_id = (str(uuid.uuid4()) for _ in range(3))
    latest = now - timedelta(hours=12)
    rows = [
        {"tid": tenant_id, "etype": "fda_spreadsheet", "count": 10, "at": latest},
        {"tid": tenant_id, "etype": "fda_export_all", "count": 20, "at": now - timedelta(days=3)},
        {"tid": tenant_id, "etype": "fda_spreadsheet", "count": 0, "at": now - timedelta(days=30)},
        # Newer than every export above: any leak changes the counts, the types and the latest time.
        {"tid": other_tenant_id, "etype": "recall", "count": 99, "at": now - timedelta(hours=1)},
        {"tid": stale_tenant_id, "etype": "fda_spreadsheet", "count": 1, "at": now - timedelta(days=30)},
    ]
    conn.execute(
        text(
            """
            INSERT INTO fsma.fda_export_log (tenant_id, export_type, record_count, export_hash, generated_at)
            VALUES (:tid, :etype, :count, 'pytest-export-monitoring', :at)
            """
        ),
        rows,
    )
    return tenant_id, stale_tenant_id, latest


def test_query_export_logs_returns_the_tenants_exports_newest_first(exports):
    """Three rows in generated_at order. A lost tenant filter would return 5 with another tenant's first."""
    from app import export_monitoring as em

    tenant_id, _, latest = exports

    logs = em._query_export_logs(tenant_id)

    assert logs is not None
    assert [log["export_type"] for log in logs] == ["fda_spreadsheet", "fda_export_all", "fda_spreadsheet"]
    assert [log["record_count"] for log in logs] == [10, 20, 0]
    assert {log["tenant_id"] for log in logs} == {tenant_id}
    assert datetime.fromisoformat(logs[0]["generated_at"]) == latest
    assert set(logs[0]) == {"id", "tenant_id", "export_type", "record_count", "generated_at"}


def _metrics(tenant_id: str) -> dict:
    from app import export_monitoring as em

    return asyncio.run(em.export_metrics(tenant_id, ctx=SimpleNamespace(tenant_id=tenant_id)))


def test_export_metrics_counts_the_tenants_exports(exports):
    """Counts, windows, average and type breakdown come from the tenant's three real rows."""
    tenant_id, _, latest = exports

    body = _metrics(tenant_id)

    assert body["total_exports"] == 3
    assert body["exports_last_24h"] == 1
    assert body["exports_last_7d"] == 2
    assert body["avg_record_count"] == 15.0  # a record_count of 0 is excluded
    assert datetime.fromisoformat(body["last_export_at"]) == latest
    assert body["export_types"] == {"fda_spreadsheet": 2, "fda_export_all": 1}


def test_export_metrics_for_a_tenant_with_no_exports_is_empty_not_an_error(exports):
    """A tenant with no rows gets zero metrics while other tenants have exports."""
    body = _metrics(str(uuid.uuid4()))

    assert body["total_exports"] == 0
    assert body["last_export_at"] is None
    assert body["export_types"] == {}


def _stub_other_checks(monkeypatch) -> None:
    """Keep the alert endpoint on the stale-export path only."""
    from app import export_monitoring as em

    def healthy(name: str) -> em.HealthCheckResult:
        return em.HealthCheckResult(name=name, status="healthy", message="ok")

    monkeypatch.setattr(em, "_check_db_connectivity", lambda: healthy("db_connectivity"))
    monkeypatch.setattr(em, "_check_chain_integrity", lambda tid: healthy("chain_integrity"))
    monkeypatch.setattr(em, "_check_export_readiness", lambda tid: healthy("export_readiness"))
    monkeypatch.setattr(em, "_check_kde_completeness", lambda tid: healthy("kde_completeness"))


def _alerts(tenant_id: str) -> dict:
    from app import export_monitoring as em

    return asyncio.run(em.monitoring_alerts(tenant_id, ctx=SimpleNamespace(tenant_id=tenant_id)))


def test_monitoring_alerts_flag_a_tenant_whose_last_export_is_stale(exports, monkeypatch):
    """A 30-day-old last export raises the stale alert. A lost tenant filter would see the 1-hour-old export."""
    _, stale_tenant_id, _ = exports
    _stub_other_checks(monkeypatch)

    body = _alerts(stale_tenant_id)

    assert [alert["alert_type"] for alert in body["alerts"]] == ["stale_exports"]
    assert body["alerts"][0]["severity"] == "warning"


def test_monitoring_alerts_stay_quiet_for_a_tenant_with_a_recent_export(exports, monkeypatch):
    tenant_id, _, _ = exports
    _stub_other_checks(monkeypatch)

    body = _alerts(tenant_id)

    assert body["alerts"] == []


# ---------------------------------------------------------------------------
# _check_kde_completeness
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
            VALUES (:id, :tid, 'shipping', 'MON-LOT-001', 'Romaine', 1, 'kg', now(), :hash, :hash)
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


def test_kde_completeness_scores_the_tenants_required_fields(shipping_events):
    """Two complete events score 100%. A lost tenant filter would pull in the sparse event."""
    from app import export_monitoring as em

    complete_tenant, _, required = shipping_events

    check = em._check_kde_completeness(complete_tenant)

    assert check.status == "healthy", check.message
    assert check.details == {
        "required_fields": 2 * required,
        "present_fields": 2 * required,
        "events_unchecked_type": 0,
        "completeness_pct": 100.0,
    }


def test_kde_completeness_below_threshold_warns(shipping_events):
    """An event carrying only its column KDEs is scored against the full required set."""
    from app import export_monitoring as em

    _, sparse_tenant, required = shipping_events
    present = len(EVENT_COLUMN_KDES)
    assert present / required < 0.8  # the seed is below the pass threshold

    check = em._check_kde_completeness(sparse_tenant)

    assert check.status == "warning", check.message
    assert check.details["required_fields"] == required
    assert check.details["present_fields"] == present
    assert check.details["completeness_pct"] == round(present / required * 100, 1)


def test_kde_completeness_for_a_tenant_with_no_events_is_empty_not_an_error(shipping_events):
    """A tenant with no rows gets the "no events" result while other tenants have events."""
    from app import export_monitoring as em

    check = em._check_kde_completeness(str(uuid.uuid4()))

    assert check.status == "warning"
    assert check.message == "No CTE events found for this tenant."
    assert check.details["completeness_pct"] is None
