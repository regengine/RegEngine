"""``total`` on GET /api/v1/audit/events is the filtered count, not the page size.

Before the fix, ``auditor_router.audit_events`` returned
``"total": len(events)``: the number of rows on the current page. An
auditor paginating a filtered evidence set to exhaustion could not tell
whether the set was complete, because every page reported its own size
as the total. The endpoint now runs a ``COUNT(*)`` over the same
``WHERE`` and ``compliance_status`` filters (without ``LIMIT``/``OFFSET``)
and returns that as ``total``.

Pure-Python. No live Postgres required: the SQLAlchemy ``execute`` call
is stubbed with a fake session that answers the page query with rows
and the count query with a scalar.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Make services/ingestion importable as the ingestion service expects.
service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import app.authz as authz  # noqa: E402
from app import auditor_router  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from shared.database import get_db_session  # noqa: E402

TENANT = "tenant-audit-total"


class _FakeResult:
    def __init__(self, row: Any):
        self._row = row

    def fetchall(self):
        if self._row is None:
            return []
        if isinstance(self._row, list):
            return self._row
        return [self._row]

    def scalar(self):
        if isinstance(self._row, list):
            return self._row[0][0] if self._row and self._row[0] else None
        if isinstance(self._row, (tuple, list)):
            return self._row[0] if self._row else None
        return self._row


class FakeSession:
    """Route ``execute()`` by SQL shape: COUNT queries get the scalar,
    the page query gets rows. Records every call for filter assertions."""

    def __init__(self, rows: List[tuple], total: int):
        self._rows = rows
        self._total = total
        self.calls: List[Tuple[str, Dict[str, Any]]] = []

    def execute(self, statement, params: Dict[str, Any] | None = None):
        sql = re.sub(r"\s+", " ", str(statement)).strip()
        self.calls.append((sql, dict(params or {})))
        # Anchored: the page query also contains "SELECT COUNT(*)" inside
        # its LATERAL rollup, so a substring match would misroute it.
        if re.match(r"SELECT COUNT\(\*\)", sql, re.IGNORECASE):
            return _FakeResult((self._total,))
        return _FakeResult(list(self._rows))


def _page_row(event_id: str = "evt-1") -> tuple:
    return (
        event_id,
        "receiving",
        "TLC-001",
        "PROD-REF",
        42.0,
        "kg",
        datetime(2026, 1, 2, tzinfo=timezone.utc),
        "SAP",
        0.95,
        "1.0",
        datetime(2026, 1, 2, 12, tzinfo=timezone.utc),
        3,
        3,
        0,
        0,
        3,
        None,
        None,
    )


@pytest.fixture(autouse=True)
def _disable_rate_limit(monkeypatch):
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))


def _build_client(session: FakeSession) -> TestClient:
    principal = IngestionPrincipal(
        key_id="test-key",
        tenant_id=TENANT,
        scopes=["audit.read"],
        auth_mode="test",
    )
    app = FastAPI()
    app.include_router(auditor_router.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: principal
    app.dependency_overrides[get_db_session] = lambda: session
    return TestClient(app)


def test_total_is_filtered_count_not_page_size():
    """A page of 2 rows out of 120 matching events must report total 120.

    On the old code ``total`` was ``len(events)`` (2), so this fails
    before the fix and passes after it.
    """
    session = FakeSession(rows=[_page_row("evt-1"), _page_row("evt-2")], total=120)
    resp = _build_client(session).get("/api/v1/audit/events?limit=2&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["events"]) == 2
    assert body["total"] == 120


def test_count_query_carries_same_filters_without_pagination():
    """The COUNT must reuse the tlc and compliance_status filters so the
    total describes the filtered set, and must not carry LIMIT/OFFSET."""
    session = FakeSession(rows=[_page_row()], total=7)
    resp = _build_client(session).get("/api/v1/audit/events?tlc=TLC-001&compliance_status=compliant&limit=1&offset=5")
    assert resp.status_code == 200
    assert resp.json()["total"] == 7

    def _is_count(sql: str) -> bool:
        return sql.startswith("SELECT COUNT(*)")

    count_calls = [(sql, params) for sql, params in session.calls if _is_count(sql)]
    assert len(count_calls) == 1
    count_sql, count_params = count_calls[0]
    # Same row filters as the page query.
    assert "e.traceability_lot_code = :tlc" in count_sql
    assert "COALESCE(eval_summary.affirmative, 0) > 0" in count_sql
    assert "LIMIT" not in count_sql and "OFFSET" not in count_sql
    assert count_params.get("tid") == TENANT
    assert count_params.get("tlc") == "TLC-001"
    assert "lim" not in count_params and "off" not in count_params

    # The page query itself is unchanged: still paginated.
    page_calls = [(sql, params) for sql, params in session.calls if not _is_count(sql)]
    assert len(page_calls) == 1
    assert "LIMIT :lim OFFSET :off" in page_calls[0][0]
    assert page_calls[0][1]["lim"] == 1
    assert page_calls[0][1]["off"] == 5
