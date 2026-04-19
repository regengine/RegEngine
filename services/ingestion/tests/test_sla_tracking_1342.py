"""
Regression coverage for ``app/sla_tracking.py``.

21 CFR 1.1455 gives food companies 24 hours to respond to an FDA
records request. This module tracks the SLA clock and flips tenants
to OVERDUE when the deadline passes. Regressions here are directly
visible to regulators.

Tests lock in:

* FDARequest computed properties (time_remaining, is_overdue, response_hours)
* ``_refresh_overdue_statuses`` transition from open/in_progress → overdue
* ``_generate_alerts_for_request`` boundaries (> 0, 0–4h, < 0)
* ``_request_to_dict`` shape + time_remaining clamp at 0
* best-effort DB persist/load wrappers returning None / continuing on failure
* full endpoint suite (create, list, complete, dashboard, alerts)
* pagination respected on list_requests and list_alerts
* status_filter scope on list_requests

Tracks GitHub issue #1342.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import sla_tracking
from app.sla_tracking import (
    ALERT_THRESHOLD_HOURS,
    FDARequest,
    SLA_HOURS,
    SLAAlert,
    SLADashboard,
    _generate_alerts_for_request,
    _refresh_overdue_statuses,
    _request_to_dict,
    _try_load_requests,
    _try_persist_request,
    router,
)
from app.webhook_compat import _verify_api_key


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture(autouse=True)
def _reset_stores():
    """Clear the in-memory caches between tests for isolation."""
    sla_tracking._requests_store.clear()
    sla_tracking._alerts_store.clear()
    yield
    sla_tracking._requests_store.clear()
    sla_tracking._alerts_store.clear()


@pytest.fixture
def client(monkeypatch):
    """Router-only app with auth bypassed and DB calls stubbed."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None

    # Keep DB wrappers as no-ops: persist does nothing, load reports
    # DB unavailable so endpoints fall back to the in-memory store.
    monkeypatch.setattr(sla_tracking, "_try_persist_request", lambda req: None)
    monkeypatch.setattr(sla_tracking, "_try_load_requests", lambda tid: None)

    with TestClient(app) as c:
        yield c


def _mk_req(**overrides):
    base = {
        "tenant_id": "tenant-1",
        "request_type": "records_request",
        "notes": None,
    }
    base.update(overrides)
    return base


# ===========================================================================
# FDARequest computed properties
# ===========================================================================


class TestFDARequestProperties:

    def test_time_remaining_is_none_for_completed(self):
        req = FDARequest(
            tenant_id="t",
            status="completed",
            completed_at=datetime.now(timezone.utc),
        )
        assert req.time_remaining is None

    def test_time_remaining_counts_down_to_deadline(self):
        now = datetime.now(timezone.utc)
        req = FDARequest(
            tenant_id="t",
            deadline_at=now + timedelta(hours=10),
        )
        remaining = req.time_remaining
        assert remaining > timedelta(0)
        assert remaining <= timedelta(hours=10)

    def test_is_overdue_false_if_completed(self):
        req = FDARequest(
            tenant_id="t",
            status="completed",
            deadline_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        assert req.is_overdue is False

    def test_is_overdue_false_before_deadline(self):
        req = FDARequest(
            tenant_id="t",
            deadline_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert req.is_overdue is False

    def test_is_overdue_true_after_deadline(self):
        req = FDARequest(
            tenant_id="t",
            deadline_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        assert req.is_overdue is True

    def test_response_hours_is_none_if_not_completed(self):
        req = FDARequest(tenant_id="t")
        assert req.response_hours is None

    def test_response_hours_computes_duration_for_completed(self):
        now = datetime.now(timezone.utc)
        req = FDARequest(
            tenant_id="t",
            requested_at=now - timedelta(hours=3),
            completed_at=now,
        )
        assert 2.99 < req.response_hours < 3.01

    def test_default_deadline_is_24_hours_from_now(self):
        req = FDARequest(tenant_id="t")
        expected = datetime.now(timezone.utc) + timedelta(hours=SLA_HOURS)
        # Allow 1s drift from test clock.
        assert abs((req.deadline_at - expected).total_seconds()) < 1.0


# ===========================================================================
# _refresh_overdue_statuses
# ===========================================================================


class TestRefreshOverdueStatuses:

    def test_open_past_deadline_becomes_overdue(self):
        req = FDARequest(
            tenant_id="t",
            status="open",
            deadline_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        sla_tracking._requests_store[req.id] = req
        _refresh_overdue_statuses()
        assert sla_tracking._requests_store[req.id].status == "overdue"

    def test_in_progress_past_deadline_becomes_overdue(self):
        req = FDARequest(
            tenant_id="t",
            status="in_progress",
            deadline_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        sla_tracking._requests_store[req.id] = req
        _refresh_overdue_statuses()
        assert sla_tracking._requests_store[req.id].status == "overdue"

    def test_open_before_deadline_stays_open(self):
        req = FDARequest(
            tenant_id="t",
            status="open",
            deadline_at=datetime.now(timezone.utc) + timedelta(hours=10),
        )
        sla_tracking._requests_store[req.id] = req
        _refresh_overdue_statuses()
        assert sla_tracking._requests_store[req.id].status == "open"

    def test_completed_past_deadline_stays_completed(self):
        """Completion wins — even if the deadline has since passed, status
        must NOT flip back to overdue."""
        req = FDARequest(
            tenant_id="t",
            status="completed",
            completed_at=datetime.now(timezone.utc) - timedelta(hours=2),
            deadline_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        sla_tracking._requests_store[req.id] = req
        _refresh_overdue_statuses()
        assert sla_tracking._requests_store[req.id].status == "completed"


# ===========================================================================
# _generate_alerts_for_request
# ===========================================================================


class TestGenerateAlerts:

    def test_completed_generates_no_alerts(self):
        req = FDARequest(
            tenant_id="t",
            status="completed",
            completed_at=datetime.now(timezone.utc),
        )
        assert _generate_alerts_for_request(req) == []

    def test_past_deadline_generates_overdue_alert(self):
        req = FDARequest(
            tenant_id="t",
            deadline_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        alerts = _generate_alerts_for_request(req)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "overdue"
        assert "OVERDUE" in alerts[0].message

    def test_within_threshold_generates_approaching_alert(self):
        """deadline_at within 4 hours → deadline_approaching."""
        req = FDARequest(
            tenant_id="t",
            deadline_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        alerts = _generate_alerts_for_request(req)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "deadline_approaching"
        assert "deadline in" in alerts[0].message

    def test_far_from_deadline_generates_no_alert(self):
        """> 4 hours remaining → no alert."""
        req = FDARequest(
            tenant_id="t",
            deadline_at=datetime.now(timezone.utc) + timedelta(hours=10),
        )
        assert _generate_alerts_for_request(req) == []

    def test_exactly_at_threshold_generates_approaching(self):
        """Strict <= on threshold — exactly 4h remaining is still approaching."""
        req = FDARequest(
            tenant_id="t",
            deadline_at=datetime.now(timezone.utc)
            + timedelta(hours=ALERT_THRESHOLD_HOURS),
        )
        alerts = _generate_alerts_for_request(req)
        # There may be slight clock drift (millis), but < or == 4h both
        # land in "approaching" — we just check it triggered.
        assert len(alerts) == 1
        assert alerts[0].alert_type == "deadline_approaching"

    def test_alert_carries_tenant_and_request_id(self):
        req = FDARequest(
            tenant_id="tenant-xyz",
            deadline_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        alerts = _generate_alerts_for_request(req)
        assert alerts[0].tenant_id == "tenant-xyz"
        assert alerts[0].request_id == req.id


# ===========================================================================
# _request_to_dict
# ===========================================================================


class TestRequestToDict:

    def test_basic_shape(self):
        req = FDARequest(tenant_id="t", notes="example")
        d = _request_to_dict(req)
        assert d["id"] == req.id
        assert d["tenant_id"] == "t"
        assert d["request_type"] == "records_request"
        assert d["status"] == "open"
        assert d["notes"] == "example"
        assert "T" in d["requested_at"]  # ISO timestamp
        assert "T" in d["deadline_at"]
        assert d["completed_at"] is None
        assert d["export_ids"] == []
        assert isinstance(d["time_remaining_seconds"], float)
        assert d["response_hours"] is None

    def test_completed_dict_has_completed_at_iso(self):
        now = datetime.now(timezone.utc)
        req = FDARequest(
            tenant_id="t",
            status="completed",
            completed_at=now,
            requested_at=now - timedelta(hours=5),
        )
        d = _request_to_dict(req)
        assert d["completed_at"] is not None
        assert "T" in d["completed_at"]
        assert d["time_remaining_seconds"] is None
        assert d["response_hours"] is not None

    def test_past_deadline_clamps_remaining_at_zero(self):
        """Negative time_remaining is clamped to 0 for dashboard display."""
        req = FDARequest(
            tenant_id="t",
            deadline_at=datetime.now(timezone.utc) - timedelta(hours=10),
        )
        d = _request_to_dict(req)
        assert d["time_remaining_seconds"] == 0


# ===========================================================================
# Best-effort DB wrappers (failures swallowed)
# ===========================================================================


class TestBestEffortDb:

    def test_persist_swallows_import_failure(self, monkeypatch):
        """SessionLocal not available → _try_persist_request logs and returns."""
        import shared.database

        def _boom(*a, **kw):
            raise RuntimeError("no DB")

        monkeypatch.setattr(shared.database, "SessionLocal", _boom)
        req = FDARequest(tenant_id="t")
        # Should not raise.
        _try_persist_request(req)

    def test_load_returns_none_on_db_failure(self, monkeypatch):
        import shared.database

        def _boom(*a, **kw):
            raise RuntimeError("no DB")

        monkeypatch.setattr(shared.database, "SessionLocal", _boom)
        assert _try_load_requests("tenant-1") is None

    def test_persist_happy_path_executes_and_commits(self, monkeypatch):
        """Real body runs: db.execute(...) then db.commit() then db.close()."""
        from unittest.mock import MagicMock
        import shared.database

        session = MagicMock()
        session.execute = MagicMock()
        session.commit = MagicMock()
        session.close = MagicMock()
        monkeypatch.setattr(shared.database, "SessionLocal", lambda: session)

        req = FDARequest(tenant_id="t", export_ids=["exp-1", "exp-2"], notes="n")
        _try_persist_request(req)

        session.execute.assert_called_once()
        session.commit.assert_called_once()
        session.close.assert_called_once()
        # export_ids serialized as comma-joined string in params.
        params = session.execute.call_args[0][1]
        assert params["export_ids"] == "exp-1,exp-2"
        assert params["notes"] == "n"

    def test_persist_no_export_ids_sends_none(self, monkeypatch):
        from unittest.mock import MagicMock
        import shared.database

        session = MagicMock()
        monkeypatch.setattr(shared.database, "SessionLocal", lambda: session)
        req = FDARequest(tenant_id="t")
        _try_persist_request(req)
        params = session.execute.call_args[0][1]
        assert params["export_ids"] is None

    def test_persist_db_close_always_called_on_execute_failure(self, monkeypatch):
        """Even if execute() raises, finally: db.close() still fires."""
        from unittest.mock import MagicMock
        import shared.database

        session = MagicMock()
        session.execute = MagicMock(side_effect=RuntimeError("boom"))
        session.close = MagicMock()
        monkeypatch.setattr(shared.database, "SessionLocal", lambda: session)

        req = FDARequest(tenant_id="t")
        # Outer try/except swallows; session.close() still fires via finally.
        _try_persist_request(req)
        session.close.assert_called_once()

    def test_load_happy_path_returns_list(self, monkeypatch):
        """Real DB load path — rows come back and round-trip into FDARequest."""
        from unittest.mock import MagicMock
        import shared.database

        now = datetime.now(timezone.utc)
        row = MagicMock()
        row.id = "req-1"
        row.tenant_id = "t"
        row.request_type = "records_request"
        row.requested_at = now - timedelta(hours=3)
        row.deadline_at = now + timedelta(hours=21)
        row.status = "open"
        row.completed_at = None
        row.export_ids = "exp-1,exp-2"
        row.notes = "n"

        result = MagicMock()
        result.fetchall = MagicMock(return_value=[row])

        session = MagicMock()
        session.execute = MagicMock(return_value=result)
        session.close = MagicMock()
        monkeypatch.setattr(shared.database, "SessionLocal", lambda: session)

        out = _try_load_requests("t")
        assert out is not None
        assert len(out) == 1
        r = out[0]
        assert r.id == "req-1"
        assert r.tenant_id == "t"
        assert r.export_ids == ["exp-1", "exp-2"]
        assert r.status == "open"
        # Side-effect: in-memory store was populated.
        assert "req-1" in sla_tracking._requests_store

    def test_load_empty_export_ids_becomes_empty_list(self, monkeypatch):
        from unittest.mock import MagicMock
        import shared.database

        now = datetime.now(timezone.utc)
        row = MagicMock()
        row.id = "req-2"
        row.tenant_id = "t"
        row.request_type = "records_request"
        row.requested_at = now - timedelta(hours=1)
        row.deadline_at = now + timedelta(hours=23)
        row.status = "open"
        row.completed_at = None
        row.export_ids = None
        row.notes = None

        result = MagicMock()
        result.fetchall = MagicMock(return_value=[row])
        session = MagicMock()
        session.execute = MagicMock(return_value=result)
        monkeypatch.setattr(shared.database, "SessionLocal", lambda: session)

        out = _try_load_requests("t")
        assert out[0].export_ids == []

    def test_load_db_close_called_on_exception(self, monkeypatch):
        """Exception raised after SessionLocal() → still returns None."""
        from unittest.mock import MagicMock
        import shared.database

        session = MagicMock()
        session.execute = MagicMock(side_effect=RuntimeError("boom"))
        session.close = MagicMock()
        monkeypatch.setattr(shared.database, "SessionLocal", lambda: session)
        out = _try_load_requests("t")
        assert out is None
        session.close.assert_called_once()


# ===========================================================================
# POST /requests
# ===========================================================================


class TestCreateEndpoint:

    def test_creates_open_request_with_24h_deadline(self, client):
        resp = client.post("/api/v1/sla/requests", json=_mk_req())
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "created"
        req = body["request"]
        assert req["status"] == "open"
        assert req["tenant_id"] == "tenant-1"
        assert req["request_type"] == "records_request"
        # Deadline should be roughly 24h from now.
        deadline = datetime.fromisoformat(req["deadline_at"])
        requested = datetime.fromisoformat(req["requested_at"])
        delta = (deadline - requested).total_seconds() / 3600
        assert 23.9 < delta < 24.1

    def test_recall_request_type_honored(self, client):
        resp = client.post(
            "/api/v1/sla/requests", json=_mk_req(request_type="recall")
        )
        assert resp.json()["request"]["request_type"] == "recall"

    def test_inspection_request_type_honored(self, client):
        resp = client.post(
            "/api/v1/sla/requests", json=_mk_req(request_type="inspection")
        )
        assert resp.json()["request"]["request_type"] == "inspection"

    def test_invalid_request_type_rejected(self, client):
        resp = client.post(
            "/api/v1/sla/requests",
            json=_mk_req(request_type="not-a-thing"),
        )
        assert resp.status_code == 422

    def test_notes_persisted(self, client):
        resp = client.post(
            "/api/v1/sla/requests",
            json=_mk_req(notes="Walmart recall — TLC ROM-0226"),
        )
        assert resp.json()["request"]["notes"].startswith("Walmart")


# ===========================================================================
# GET /requests/{tenant_id}
# ===========================================================================


class TestListRequestsEndpoint:

    def test_empty_for_unknown_tenant(self, client):
        resp = client.get("/api/v1/sla/requests/tenant-unknown")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["requests"] == []

    def test_only_tenant_scoped_requests_returned(self, client):
        client.post("/api/v1/sla/requests", json=_mk_req(tenant_id="A"))
        client.post("/api/v1/sla/requests", json=_mk_req(tenant_id="B"))
        client.post("/api/v1/sla/requests", json=_mk_req(tenant_id="A"))

        resp_a = client.get("/api/v1/sla/requests/A")
        resp_b = client.get("/api/v1/sla/requests/B")
        assert resp_a.json()["total"] == 2
        assert resp_b.json()["total"] == 1

    def test_status_filter_narrows_results(self, client):
        """Seed an open + overdue request; filter by status."""
        # Open request
        client.post("/api/v1/sla/requests", json=_mk_req(tenant_id="A"))
        # Overdue — inject directly into store
        past = FDARequest(
            tenant_id="A",
            status="open",  # will be flipped by _refresh_overdue_statuses
            deadline_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        sla_tracking._requests_store[past.id] = past

        resp = client.get("/api/v1/sla/requests/A?status=overdue")
        assert resp.json()["total"] == 1
        assert resp.json()["requests"][0]["status"] == "overdue"

    def test_pagination_skip_and_limit(self, client):
        for _ in range(5):
            client.post("/api/v1/sla/requests", json=_mk_req(tenant_id="A"))
        resp = client.get("/api/v1/sla/requests/A?skip=1&limit=2")
        assert resp.json()["total"] == 5
        assert len(resp.json()["requests"]) == 2
        assert resp.json()["skip"] == 1
        assert resp.json()["limit"] == 2

    def test_db_load_used_when_available(self, client, monkeypatch):
        """When _try_load_requests returns rows, in-memory filter is skipped."""
        sentinel = FDARequest(tenant_id="A", notes="from-db")

        monkeypatch.setattr(
            sla_tracking, "_try_load_requests", lambda tid: [sentinel]
        )
        resp = client.get("/api/v1/sla/requests/A")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["requests"][0]["notes"] == "from-db"


# ===========================================================================
# PATCH /requests/{request_id}/complete
# ===========================================================================


class TestCompleteEndpoint:

    def test_404_for_unknown_request(self, client):
        resp = client.patch("/api/v1/sla/requests/no-such-id/complete")
        assert resp.status_code == 404

    def test_marks_request_completed(self, client):
        created = client.post(
            "/api/v1/sla/requests", json=_mk_req()
        ).json()["request"]
        resp = client.patch(
            f"/api/v1/sla/requests/{created['id']}/complete"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["request"]["status"] == "completed"
        assert body["request"]["completed_at"] is not None

    def test_completion_within_24h_sets_met_sla_true(self, client):
        created = client.post(
            "/api/v1/sla/requests", json=_mk_req()
        ).json()["request"]
        resp = client.patch(
            f"/api/v1/sla/requests/{created['id']}/complete"
        )
        assert resp.json()["met_sla"] is True

    def test_completion_past_deadline_sets_met_sla_false(self, client):
        """Inject an overdue request directly to sidestep the 24h window."""
        past = FDARequest(
            tenant_id="t",
            status="open",
            requested_at=datetime.now(timezone.utc) - timedelta(hours=30),
            deadline_at=datetime.now(timezone.utc) - timedelta(hours=6),
        )
        sla_tracking._requests_store[past.id] = past
        resp = client.patch(f"/api/v1/sla/requests/{past.id}/complete")
        assert resp.status_code == 200
        assert resp.json()["met_sla"] is False

    def test_export_ids_appended(self, client):
        created = client.post(
            "/api/v1/sla/requests", json=_mk_req()
        ).json()["request"]
        resp = client.patch(
            f"/api/v1/sla/requests/{created['id']}/complete"
            f"?export_ids=exp-1&export_ids=exp-2"
        )
        assert resp.json()["request"]["export_ids"] == ["exp-1", "exp-2"]

    def test_completion_produces_stored_alert(self, client):
        created = client.post(
            "/api/v1/sla/requests", json=_mk_req()
        ).json()["request"]
        client.patch(f"/api/v1/sla/requests/{created['id']}/complete")
        stored_alerts = [
            a for a in sla_tracking._alerts_store.values()
            if a.request_id == created["id"]
        ]
        assert len(stored_alerts) == 1
        assert stored_alerts[0].alert_type == "completed"


# ===========================================================================
# GET /dashboard/{tenant_id}
# ===========================================================================


class TestDashboardEndpoint:

    def test_empty_tenant_returns_zero_counts(self, client):
        resp = client.get("/api/v1/sla/dashboard/empty-tenant")
        body = resp.json()
        assert body["open_requests"] == 0
        assert body["overdue_requests"] == 0
        assert body["avg_response_hours"] is None
        assert body["compliance_rate_pct"] is None

    def test_counts_open_and_overdue_separately(self, client):
        # Open request
        client.post("/api/v1/sla/requests", json=_mk_req(tenant_id="A"))
        # Overdue request
        past = FDARequest(
            tenant_id="A",
            status="open",
            deadline_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        sla_tracking._requests_store[past.id] = past

        resp = client.get("/api/v1/sla/dashboard/A")
        body = resp.json()
        assert body["open_requests"] == 1
        assert body["overdue_requests"] == 1

    def test_average_and_compliance_rate(self, client):
        """Two completed — one within SLA, one over."""
        now = datetime.now(timezone.utc)
        fast = FDARequest(
            tenant_id="A",
            status="completed",
            requested_at=now - timedelta(hours=10),
            completed_at=now - timedelta(hours=5),  # 5h -> met
        )
        slow = FDARequest(
            tenant_id="A",
            status="completed",
            requested_at=now - timedelta(hours=40),
            completed_at=now - timedelta(hours=10),  # 30h -> missed
        )
        sla_tracking._requests_store[fast.id] = fast
        sla_tracking._requests_store[slow.id] = slow

        resp = client.get("/api/v1/sla/dashboard/A")
        body = resp.json()
        # avg is ~17.5h
        assert 17.0 < body["avg_response_hours"] < 18.0
        # 1 of 2 met → 50%
        assert body["compliance_rate_pct"] == 50.0

    def test_dashboard_uses_db_when_available(self, client, monkeypatch):
        sentinel = FDARequest(
            tenant_id="A",
            status="completed",
            requested_at=datetime.now(timezone.utc) - timedelta(hours=2),
            completed_at=datetime.now(timezone.utc),
        )
        monkeypatch.setattr(
            sla_tracking, "_try_load_requests", lambda tid: [sentinel]
        )
        resp = client.get("/api/v1/sla/dashboard/A")
        assert resp.status_code == 200
        assert resp.json()["compliance_rate_pct"] == 100.0


# ===========================================================================
# GET /alerts/{tenant_id}
# ===========================================================================


class TestAlertsEndpoint:

    def test_empty_tenant_zero_alerts(self, client):
        resp = client.get("/api/v1/sla/alerts/empty-tenant")
        assert resp.json()["total"] == 0

    def test_live_overdue_alert_emitted(self, client):
        past = FDARequest(
            tenant_id="A",
            status="open",
            deadline_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        sla_tracking._requests_store[past.id] = past
        resp = client.get("/api/v1/sla/alerts/A")
        alerts = resp.json()["alerts"]
        assert any(a["alert_type"] == "overdue" for a in alerts)

    def test_live_deadline_approaching_alert_emitted(self, client):
        close = FDARequest(
            tenant_id="A",
            status="open",
            deadline_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        sla_tracking._requests_store[close.id] = close
        resp = client.get("/api/v1/sla/alerts/A")
        alerts = resp.json()["alerts"]
        assert any(a["alert_type"] == "deadline_approaching" for a in alerts)

    def test_stored_completion_alert_included(self, client):
        created = client.post(
            "/api/v1/sla/requests", json=_mk_req(tenant_id="A")
        ).json()["request"]
        client.patch(f"/api/v1/sla/requests/{created['id']}/complete")
        resp = client.get("/api/v1/sla/alerts/A")
        assert any(
            a["alert_type"] == "completed"
            for a in resp.json()["alerts"]
        )

    def test_include_acknowledged_toggle(self, client):
        """Acknowledged alerts are filtered out by default, included on toggle."""
        # Seed an acknowledged completion alert.
        ack = SLAAlert(
            tenant_id="A",
            request_id="r-1",
            alert_type="completed",
            message="done",
            acknowledged=True,
        )
        sla_tracking._alerts_store[ack.id] = ack

        default = client.get("/api/v1/sla/alerts/A").json()
        toggled = client.get(
            "/api/v1/sla/alerts/A?include_acknowledged=true"
        ).json()

        default_ids = [a["id"] for a in default["alerts"]]
        toggled_ids = [a["id"] for a in toggled["alerts"]]
        assert ack.id not in default_ids
        assert ack.id in toggled_ids

    def test_pagination_respected(self, client):
        # Seed 3 live alerts.
        for _ in range(3):
            past = FDARequest(
                tenant_id="A",
                status="open",
                deadline_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            sla_tracking._requests_store[past.id] = past
        resp = client.get("/api/v1/sla/alerts/A?skip=0&limit=2")
        body = resp.json()
        assert body["total"] == 3
        assert len(body["alerts"]) == 2
        assert body["limit"] == 2

    def test_alerts_scoped_to_tenant(self, client):
        # Seed a stored alert for tenant A
        alert = SLAAlert(
            tenant_id="A",
            request_id="r-1",
            alert_type="completed",
            message="done",
        )
        sla_tracking._alerts_store[alert.id] = alert
        resp = client.get("/api/v1/sla/alerts/B")
        assert resp.json()["total"] == 0


# ===========================================================================
# Pydantic model surface
# ===========================================================================


class TestPydanticSurface:

    def test_sla_dashboard_defaults(self):
        d = SLADashboard(tenant_id="t")
        assert d.open_requests == 0
        assert d.overdue_requests == 0
        assert d.avg_response_hours is None
        assert d.compliance_rate_pct is None
        assert d.requests == []

    def test_sla_alert_default_acknowledged_false(self):
        a = SLAAlert(
            tenant_id="t",
            request_id="r",
            alert_type="completed",
            message="m",
        )
        assert a.acknowledged is False

    def test_constants_are_locked(self):
        assert SLA_HOURS == 24
        assert ALERT_THRESHOLD_HOURS == 4
