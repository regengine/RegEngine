"""Regression tests for #2864 — list endpoints reported a truncated ``total``.

Three list endpoints computed ``total`` from an already-truncated result set,
so a client that paged to the end was told the truncated view was complete:

* ``GET /api/v1/audit-log/{tenant_id}``   — ``audit_log.py``
* ``GET /api/v1/identity/entities``       — ``identity_router.py``
* ``GET /api/v1/records/ingestion-runs``  — ``canonical_router.py``

For a compliance product an over-stated completeness claim on the FSMA audit
trail is the actual harm: omitting a count signals uncertainty, but reporting
the truncated count asserts the client has everything.

These tests assert the corrected contract: ``total`` reflects a real
``COUNT(*)`` against the source table(s), never ``len(page)``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock  # noqa: F401

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.authz as authz  # noqa: E402
from app import (
    audit_log as al,  # noqa: E402
    identity_router,  # noqa: E402
)
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.canonical_router import _get_db_session, router as canonical_router  # noqa: E402
from app.webhook_compat import _verify_api_key  # noqa: E402

from services.ingestion.tests.tenant_context_overrides import (  # noqa: E402
    install_tenant_context_override,
)

TENANT_ID = "00000000-0000-0000-0000-000000000111"


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


class _Result:
    """Mimics the object returned by ``session.execute()``."""

    def __init__(self, *, row: Any = None, rows: Optional[List[Any]] = None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _SqlRoutedSession:
    """Fake session that picks a result by matching a substring of the SQL.

    Ordering-independent on purpose: the tests below assert on the *contract*
    (``total`` comes from a COUNT), not on the order in which the handler
    happens to issue its queries.
    """

    def __init__(self, routes: Dict[str, _Result], default: Optional[_Result] = None):
        self._routes = routes
        self._default = default or _Result()
        self.seen_sql: List[str] = []
        self.seen_params: List[Any] = []

    def execute(self, sql, params=None, *_a, **_kw):
        sql_text = " ".join(str(sql).split())
        self.seen_sql.append(sql_text)
        self.seen_params.append(params)
        for needle, result in self._routes.items():
            if needle in sql_text:
                return result
        return self._default

    def commit(self) -> None:  # pragma: no cover - not exercised
        pass

    def rollback(self) -> None:  # pragma: no cover - not exercised
        pass

    def close(self) -> None:
        pass


@pytest.fixture()
def principal() -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id="test-key",
        scopes=["*"],
        tenant_id=TENANT_ID,
        auth_mode="test",
    )


@pytest.fixture(autouse=True)
def _patch_rate_limit(monkeypatch):
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))


# ---------------------------------------------------------------------------
# GET /api/v1/records/ingestion-runs
# ---------------------------------------------------------------------------


def _make_run_row(run_id: str) -> tuple:
    return (
        run_id,
        "webhook",
        "file.csv",
        10,
        10,
        0,
        "completed",
        "v1",
        "tester",
        None,
        None,
    )


class TestIngestionRunsTotal:
    """``total`` must be a COUNT(*), not ``len(runs)`` capped at ``limit``."""

    def _client(self, principal: IngestionPrincipal, session) -> TestClient:
        app = FastAPI()
        app.include_router(canonical_router)
        app.dependency_overrides[get_ingestion_principal] = lambda: principal
        app.dependency_overrides[_get_db_session] = lambda: session
        return TestClient(app)

    def test_total_reports_full_count_not_page_size(self, principal) -> None:
        """250 runs exist; a 20-row page must still report total=250."""
        page = [_make_run_row(f"run-{i:03d}") for i in range(20)]
        session = _SqlRoutedSession(
            {
                "SELECT COUNT(*) FROM fsma.ingestion_runs": _Result(row=(250,)),
                "SELECT id, source_system": _Result(rows=page),
            }
        )
        c = self._client(principal, session)
        resp = c.get(
            "/api/v1/records/ingestion-runs",
            params={"tenant_id": TENANT_ID, "limit": 20},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["runs"]) == 20
        assert body["total"] == 250, (
            "total must come from COUNT(*) so a paginating client can tell "
            "there are more ingestion runs than this page (#2864)"
        )

    def test_offset_is_pushed_into_sql(self, principal) -> None:
        """An ``offset`` parameter must exist and reach the SQL."""
        session = _SqlRoutedSession(
            {
                "SELECT COUNT(*) FROM fsma.ingestion_runs": _Result(row=(250,)),
                "SELECT id, source_system": _Result(rows=[]),
            }
        )
        c = self._client(principal, session)
        resp = c.get(
            "/api/v1/records/ingestion-runs",
            params={"tenant_id": TENANT_ID, "limit": 20, "offset": 40},
        )
        assert resp.status_code == 200
        listing_sql = [s for s in session.seen_sql if s.startswith("SELECT id, source_system")]
        assert listing_sql, "expected the ingestion-runs listing query to run"
        assert "OFFSET" in listing_sql[0], "ingestion-runs must paginate in SQL, not by capping at :lim (#2864)"
        assert any(isinstance(p, dict) and p.get("off") == 40 for p in session.seen_params), (
            "the requested offset must be bound into the query (#2864)"
        )


# ---------------------------------------------------------------------------
# GET /api/v1/identity/entities
# ---------------------------------------------------------------------------


class TestIdentityEntitiesTotal:
    """``total`` must be a COUNT(*), not the hard-coded ``LIMIT 100`` slice."""

    def _client(self, principal: IngestionPrincipal, session) -> TestClient:
        app = FastAPI()
        app.include_router(identity_router.router)
        app.dependency_overrides[get_ingestion_principal] = lambda: principal
        app.dependency_overrides[identity_router._get_db_session] = lambda: session
        return TestClient(app)

    def test_total_reports_full_count_not_page_size(self, principal) -> None:
        """137 entities exist; the 100-row page must still report total=137."""
        page = [(f"ent-{i:03d}", "location", f"Facility {i}", None, None, "verified", 1.0) for i in range(100)]
        session = _SqlRoutedSession(
            {
                "SELECT COUNT(*) FROM fsma.canonical_entities": _Result(row=(137,)),
                "SELECT entity_id, entity_type": _Result(rows=page),
            }
        )
        c = self._client(principal, session)
        resp = c.get("/api/v1/identity/entities", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["entities"]) == 100
        assert body["total"] == 137, (
            "total must come from COUNT(*); returning len(entities) told the "
            "client the capped 100-row view was the whole entity list (#2864)"
        )

    def test_limit_and_offset_are_pushed_into_sql(self, principal) -> None:
        """Pagination parameters must exist and reach the SQL."""
        session = _SqlRoutedSession(
            {
                "SELECT COUNT(*) FROM fsma.canonical_entities": _Result(row=(137,)),
                "SELECT entity_id, entity_type": _Result(rows=[]),
            }
        )
        c = self._client(principal, session)
        resp = c.get(
            "/api/v1/identity/entities",
            params={"tenant_id": TENANT_ID, "limit": 25, "offset": 50},
        )
        assert resp.status_code == 200
        listing_sql = [s for s in session.seen_sql if s.startswith("SELECT entity_id, entity_type")]
        assert listing_sql, "expected the entity listing query to run"
        assert "LIMIT :lim" in listing_sql[0] and "OFFSET :off" in listing_sql[0], (
            "identity/entities must paginate in SQL rather than hard-code LIMIT 100 (#2864)"
        )
        assert any(isinstance(p, dict) and p.get("lim") == 25 and p.get("off") == 50 for p in session.seen_params), (
            "the requested limit/offset must be bound into the query (#2864)"
        )


# ---------------------------------------------------------------------------
# GET /api/v1/audit-log/{tenant_id}
# ---------------------------------------------------------------------------


class TestAuditLogTotal:
    """The FSMA audit trail must not claim a truncated view is complete."""

    @pytest.fixture()
    def client(self) -> TestClient:
        app = FastAPI()
        app.include_router(al.router)
        app.dependency_overrides[_verify_api_key] = lambda: None
        install_tenant_context_override(app)
        return TestClient(app)

    @staticmethod
    def _entries(prefix: str, count: int):
        return [
            al.AuditEntry(
                id=f"{prefix}-{i}",
                timestamp=f"2026-08-{(i % 28) + 1:02d}T{i % 24:02d}:00:00+00:00",
                event_type="api_call",
                category="system",
                actor="system",
                action="act",
                resource="res",
            )
            for i in range(count)
        ]

    @staticmethod
    def _install_sessions(monkeypatch, counts: Dict[str, int]) -> None:
        """Point both DB sessions at a fake that answers the real COUNT SQL.

        Routing by SQL text (rather than stubbing the ``_count_*`` helpers)
        keeps the production counting code — including the alerts table's
        ``tenant_id``/``org_id`` schema probe — inside the test.
        """
        routes = {
            "SELECT to_regclass": _Result(row=("present",)),
            "information_schema.columns": _Result(rows=[("tenant_id",), ("id",)]),
            "COUNT(*) FROM audit_logs": _Result(row=(counts["admin"],)),
            "COUNT(*) FROM fsma.cte_events": _Result(row=(counts["cte"],)),
            "COUNT(*) FROM fsma.fda_export_log": _Result(row=(counts["export"],)),
            "COUNT(*) FROM fsma.compliance_alerts": _Result(row=(counts["alert"],)),
        }
        monkeypatch.setattr(al, "get_db_safe", lambda: _SqlRoutedSession(routes))

    @pytest.fixture(autouse=True)
    def _saturated_sources(self, monkeypatch):
        """Every source fills the window and holds 500 rows in total.

        This is the condition the bug hid: each sub-query is capped, so the
        merged list is short while the tenant's real audit trail is far
        larger.
        """
        monkeypatch.setattr(al, "_query_admin_audit_logs", lambda s, t, limit: self._entries("admin", limit))
        monkeypatch.setattr(al, "_query_cte_events", lambda s, t, limit: self._entries("cte", limit))
        monkeypatch.setattr(al, "_query_exports", lambda s, t, limit: self._entries("exp", limit))
        monkeypatch.setattr(al, "_query_alert_events", lambda s, t, limit: self._entries("alert", limit))
        self._install_sessions(monkeypatch, {"admin": 500, "cte": 500, "export": 500, "alert": 500})
        yield

    def test_total_exceeds_returned_window(self, client: TestClient) -> None:
        """total must reflect the real row count, not the merged page."""
        resp = client.get(f"/api/v1/audit-log/{TENANT_ID}", params={"page": 1, "page_size": 20})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["entries"]) == 20
        assert body["total"] > 600, (
            "total was capped by four hard-coded sub-query limits "
            "(200+200+100+100), so a client paging to the end believed it had "
            "the tenant's complete FSMA audit trail (#2864); got "
            f"{body['total']}"
        )

    def test_response_flags_truncation(self, client: TestClient) -> None:
        """The client must be able to detect the view is incomplete."""
        resp = client.get(f"/api/v1/audit-log/{TENANT_ID}", params={"page": 1, "page_size": 20})
        body = resp.json()
        assert "truncated" in body, (
            "the audit-log response must tell the caller when the merged window does not cover every record (#2864)"
        )
        assert body["truncated"] is True

    def test_not_truncated_when_sources_fit(self, client: TestClient, monkeypatch) -> None:
        """A tenant whose whole trail fits must not be flagged truncated."""
        monkeypatch.setattr(al, "_query_admin_audit_logs", lambda s, t, limit: self._entries("admin", 3))
        monkeypatch.setattr(al, "_query_cte_events", lambda s, t, limit: self._entries("cte", 3))
        monkeypatch.setattr(al, "_query_exports", lambda s, t, limit: [])
        monkeypatch.setattr(al, "_query_alert_events", lambda s, t, limit: [])
        self._install_sessions(monkeypatch, {"admin": 3, "cte": 3, "export": 0, "alert": 0})

        resp = client.get(f"/api/v1/audit-log/{TENANT_ID}", params={"page": 1, "page_size": 20})
        body = resp.json()
        assert body["total"] == 6
        assert body["truncated"] is False

    def test_unreachable_source_is_flagged_not_counted_as_zero(self, client: TestClient, monkeypatch) -> None:
        """A database outage must never read as a complete, empty trail.

        Failing closed matters here: a silent 0 would let a caller conclude
        the tenant has no audit history when the truth is that we could not
        look.
        """
        monkeypatch.setattr(al, "_query_admin_audit_logs", lambda s, t, limit: self._entries("admin", 3))
        self._install_sessions(monkeypatch, {"admin": 3, "cte": 0, "export": 0, "alert": 0})

        def _boom():
            raise RuntimeError("ingestion database unavailable")

        monkeypatch.setattr(al, "get_db_safe", _boom)

        resp = client.get(f"/api/v1/audit-log/{TENANT_ID}", params={"page": 1, "page_size": 20})
        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]

    def test_deep_page_is_served_from_a_widened_window(self, client: TestClient) -> None:
        """A page past the old 600-row ceiling must contain rows.

        Page 31 at page_size 20 starts at offset 600 — exactly past the sum of
        the four old hard-coded caps (200+200+100+100), so the old code
        returned an empty slice while still reporting ``total`` as though the
        trail were complete.

        Taking the top ``page * page_size`` from each source and merging is
        exactly correct for the first ``page * page_size`` merged rows, so a
        later page is served from real data rather than an empty slice.
        """
        resp = client.get(f"/api/v1/audit-log/{TENANT_ID}", params={"page": 31, "page_size": 20})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["entries"]) == 20, (
            "deep pages were empty because each source was capped at a fixed "
            "limit regardless of the requested page (#2864)"
        )


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 0}, {"page_size": 201}, {"page": 501}])
def test_audit_pagination_rejects_invalid_or_unbounded_windows(params, monkeypatch):
    app = FastAPI()
    app.include_router(al.router)
    install_tenant_context_override(app)

    def unexpected_database_read():
        raise AssertionError("invalid pagination must not reach the database")

    monkeypatch.setattr(al, "get_db_safe", unexpected_database_read)
    assert TestClient(app).get(f"/api/v1/audit-log/{TENANT_ID}", params=params).status_code == 422
