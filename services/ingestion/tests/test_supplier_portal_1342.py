"""Regression tests for ``services/ingestion/app/supplier_portal.py``.

Part of the #1342 ingestion coverage sweep. Covers link creation,
listing, revocation, link-scoped detail lookup, and supplier submission
with DB / in-memory fallback and expiry handling.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import supplier_portal as sp
from app.supplier_portal import (
    CreatePortalLinkRequest,
    PortalLinkResponse,
    SubmissionResult,
    SupplierSubmission,
    _db_get_portal_link,
    _db_store_portal_link,
    _db_update_portal_link_status,
    _get_active_portal_link,
    router,
)
from app.webhook_compat import _verify_api_key
from app.webhook_models import EventResult, IngestResponse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_portal_links():
    sp._portal_links.clear()
    yield
    sp._portal_links.clear()


class _FakeResult:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _FakeSession:
    def __init__(
        self,
        row=None,
        rows=None,
        raise_on_execute: Optional[Exception] = None,
    ):
        self._row = row
        self._rows = rows or []
        self._raise = raise_on_execute
        self.executed: list[tuple] = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), dict(params or {})))
        if self._raise:
            raise self._raise
        return _FakeResult(self._row, self._rows)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    return app


# ---------------------------------------------------------------------------
# _db_store_portal_link
# ---------------------------------------------------------------------------


class TestDbStorePortalLink:
    def test_no_db(self, monkeypatch):
        monkeypatch.setattr(sp, "get_db_safe", lambda: None)
        ok = _db_store_portal_link("tok", {
            "tenant_id": "t1",
            "supplier_name": "S",
            "created_at": "2026-04-17",
            "expires_at": "2026-05-17",
        })
        assert ok is False

    def test_success(self, monkeypatch):
        session = _FakeSession()
        monkeypatch.setattr(sp, "get_db_safe", lambda: session)
        ok = _db_store_portal_link("tok", {
            "tenant_id": "t1",
            "supplier_name": "S",
            "created_at": "2026-04-17",
            "expires_at": "2026-05-17",
        })
        assert ok is True
        assert session.committed is True
        assert session.closed is True

    def test_failure_rolls_back(self, monkeypatch):
        session = _FakeSession(raise_on_execute=RuntimeError("boom"))
        monkeypatch.setattr(sp, "get_db_safe", lambda: session)
        ok = _db_store_portal_link("tok", {
            "tenant_id": "t1",
            "supplier_name": "S",
            "created_at": "2026-04-17",
            "expires_at": "2026-05-17",
        })
        assert ok is False
        assert session.rolled_back is True
        assert session.closed is True


# ---------------------------------------------------------------------------
# _db_get_portal_link
# ---------------------------------------------------------------------------


class TestDbGetPortalLink:
    def test_no_db(self, monkeypatch):
        monkeypatch.setattr(sp, "get_db_safe", lambda: None)
        assert _db_get_portal_link("tok") is None

    def test_no_row(self, monkeypatch):
        session = _FakeSession(row=None)
        monkeypatch.setattr(sp, "get_db_safe", lambda: session)
        assert _db_get_portal_link("tok") is None
        assert session.closed is True

    def test_found_with_timestamps(self, monkeypatch):
        now = datetime(2026, 4, 17, 10, 0, tzinfo=timezone.utc)
        exp = now + timedelta(days=30)
        session = _FakeSession(row=("t1", "S", "tok", "active", now, exp))
        monkeypatch.setattr(sp, "get_db_safe", lambda: session)
        link = _db_get_portal_link("tok")
        assert link is not None
        assert link["tenant_id"] == "t1"
        assert link["supplier_name"] == "S"
        assert link["allowed_cte_types"] == ["shipping"]
        assert link["expires_at"] == exp.isoformat()
        assert link["created_at"] == now.isoformat()

    def test_found_with_null_timestamps(self, monkeypatch):
        session = _FakeSession(row=("t1", "S", "tok", "active", None, None))
        monkeypatch.setattr(sp, "get_db_safe", lambda: session)
        link = _db_get_portal_link("tok")
        assert link is not None
        assert link["expires_at"] is None
        assert link["created_at"] is None

    def test_exception_returns_none(self, monkeypatch):
        session = _FakeSession(raise_on_execute=RuntimeError("err"))
        monkeypatch.setattr(sp, "get_db_safe", lambda: session)
        assert _db_get_portal_link("tok") is None
        assert session.closed is True


# ---------------------------------------------------------------------------
# _db_update_portal_link_status
# ---------------------------------------------------------------------------


class TestDbUpdateStatus:
    def test_no_db(self, monkeypatch):
        monkeypatch.setattr(sp, "get_db_safe", lambda: None)
        assert _db_update_portal_link_status("tok", "revoked") is False

    def test_success(self, monkeypatch):
        session = _FakeSession()
        monkeypatch.setattr(sp, "get_db_safe", lambda: session)
        assert _db_update_portal_link_status("tok", "revoked") is True
        assert session.committed is True

    def test_failure_rolls_back(self, monkeypatch):
        session = _FakeSession(raise_on_execute=RuntimeError("oops"))
        monkeypatch.setattr(sp, "get_db_safe", lambda: session)
        assert _db_update_portal_link_status("tok", "revoked") is False
        assert session.rolled_back is True


# ---------------------------------------------------------------------------
# _get_active_portal_link
# ---------------------------------------------------------------------------


class TestGetActivePortalLink:
    def test_missing_everywhere_raises_404(self, monkeypatch):
        monkeypatch.setattr(sp, "_db_get_portal_link", lambda _pid: None)
        with pytest.raises(Exception) as exc:
            _get_active_portal_link("missing")
        assert exc.value.status_code == 404

    def test_falls_back_to_memory(self, monkeypatch):
        future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        sp._portal_links["tok"] = {
            "tenant_id": "t1",
            "supplier_name": "S",
            "allowed_cte_types": ["shipping"],
            "expires_at": future,
        }
        monkeypatch.setattr(sp, "_db_get_portal_link", lambda _pid: None)
        link = _get_active_portal_link("tok")
        assert link["supplier_name"] == "S"

    def test_missing_expires_at_raises(self, monkeypatch):
        sp._portal_links["tok"] = {"tenant_id": "t1", "supplier_name": "S"}
        monkeypatch.setattr(sp, "_db_get_portal_link", lambda _pid: None)
        with pytest.raises(Exception) as exc:
            _get_active_portal_link("tok")
        assert exc.value.status_code == 404

    def test_invalid_expiry_raises_400(self, monkeypatch):
        sp._portal_links["tok"] = {
            "tenant_id": "t1",
            "supplier_name": "S",
            "expires_at": "not-a-date",
        }
        monkeypatch.setattr(sp, "_db_get_portal_link", lambda _pid: None)
        with pytest.raises(Exception) as exc:
            _get_active_portal_link("tok")
        assert exc.value.status_code == 400

    def test_expired_link_returns_404_and_updates_db(self, monkeypatch):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        sp._portal_links["tok"] = {
            "tenant_id": "t1",
            "supplier_name": "S",
            "expires_at": past,
        }
        monkeypatch.setattr(sp, "_db_get_portal_link", lambda _pid: None)
        status_updates: list = []
        monkeypatch.setattr(
            sp, "_db_update_portal_link_status",
            lambda pid, status: status_updates.append((pid, status)) or True,
        )
        with pytest.raises(Exception) as exc:
            _get_active_portal_link("tok")
        assert exc.value.status_code == 404
        assert ("tok", "expired") in status_updates
        assert "tok" not in sp._portal_links

    def test_z_suffix_expiry_parsed(self, monkeypatch):
        future = (datetime.now(timezone.utc) + timedelta(days=5)).replace(microsecond=0)
        iso_z = future.isoformat().replace("+00:00", "Z")
        sp._portal_links["tok"] = {
            "tenant_id": "t1",
            "supplier_name": "S",
            "allowed_cte_types": ["shipping"],
            "expires_at": iso_z,
        }
        monkeypatch.setattr(sp, "_db_get_portal_link", lambda _pid: None)
        link = _get_active_portal_link("tok")
        assert link is not None


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestModels:
    def test_create_portal_link_defaults(self):
        req = CreatePortalLinkRequest(tenant_id="t1", supplier_name="S")
        assert req.allowed_cte_types == ["shipping"]
        assert req.expires_days == 90
        assert req.supplier_email is None
        assert req.integration_profile_id is None

    def test_create_portal_link_rejects_bad_expiry(self):
        with pytest.raises(Exception):
            CreatePortalLinkRequest(tenant_id="t1", supplier_name="S", expires_days=0)
        with pytest.raises(Exception):
            CreatePortalLinkRequest(tenant_id="t1", supplier_name="S", expires_days=999)

    def test_supplier_submission_tlc_minlength(self):
        with pytest.raises(Exception):
            SupplierSubmission(
                traceability_lot_code="ab",  # < 3
                product_description="p",
                quantity=1.0,
                unit_of_measure="cases",
                ship_date="2026-04-17",
                ship_from_location="F1",
                ship_to_location="F2",
            )

    def test_supplier_submission_positive_quantity(self):
        with pytest.raises(Exception):
            SupplierSubmission(
                traceability_lot_code="TLC123",
                product_description="p",
                quantity=0,
                unit_of_measure="cases",
                ship_date="2026-04-17",
                ship_from_location="F1",
                ship_to_location="F2",
            )

    def test_submission_result_defaults(self):
        r = SubmissionResult(
            status="accepted",
            message="ok",
            supplier_name="S",
            submitted_at="t",
        )
        assert r.event_id is None
        assert r.sha256_hash is None


# ---------------------------------------------------------------------------
# POST /links
# ---------------------------------------------------------------------------


class TestCreatePortalLink:
    def test_db_success_stores_both_places(self, monkeypatch):
        monkeypatch.setattr(sp, "_db_store_portal_link", lambda *a, **k: True)
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/portal/links",
            json={"tenant_id": "t1", "supplier_name": "Acme"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "t1"
        assert body["supplier_name"] == "Acme"
        assert body["portal_url"].startswith("https://regengine.co/portal/")
        assert body["allowed_cte_types"] == ["shipping"]
        assert body["portal_id"] in sp._portal_links

    def test_db_failure_falls_back_to_memory(self, monkeypatch):
        monkeypatch.setattr(sp, "_db_store_portal_link", lambda *a, **k: False)
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/portal/links",
            json={"tenant_id": "t1", "supplier_name": "Acme", "expires_days": 30},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Memory fallback still populates _portal_links
        assert body["portal_id"] in sp._portal_links
        assert sp._portal_links[body["portal_id"]]["supplier_name"] == "Acme"

    def test_custom_cte_types_and_email(self, monkeypatch):
        monkeypatch.setattr(sp, "_db_store_portal_link", lambda *a, **k: True)
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/portal/links",
            json={
                "tenant_id": "t1",
                "supplier_name": "Acme",
                "supplier_email": "s@example.com",
                "allowed_cte_types": ["shipping", "receiving"],
                "integration_profile_id": "prof_csv_1",
            },
        )
        body = resp.json()
        assert body["allowed_cte_types"] == ["shipping", "receiving"]
        assert body["integration_profile_id"] == "prof_csv_1"
        stored = sp._portal_links[body["portal_id"]]
        assert stored["supplier_email"] == "s@example.com"
        assert stored["integration_profile_id"] == "prof_csv_1"


# ---------------------------------------------------------------------------
# GET /links/list
# ---------------------------------------------------------------------------


class TestListPortalLinks:
    def test_db_rows_with_expiry_status_transition(self, monkeypatch):
        now = datetime.now(timezone.utc)
        past = now - timedelta(days=1)
        future = now + timedelta(days=10)
        rows = [
            ("id1", "t1", "ActiveCo", "tok1", "active", now, future),   # active
            ("id2", "t1", "StaleCo", "tok2", "active", now, past),       # will auto-expire
            ("id3", "t1", "RevokedCo", "tok3", "revoked", now, past),    # stays revoked
        ]
        session = _FakeSession(rows=rows)
        monkeypatch.setattr(sp, "get_db_safe", lambda: session)

        client = TestClient(_build_app())
        resp = client.get("/api/v1/portal/links/list?tenant_id=t1")
        assert resp.status_code == 200
        body = resp.json()
        statuses = {l["portal_id"]: l["status"] for l in body["links"]}
        assert statuses["tok1"] == "active"
        assert statuses["tok2"] == "expired"
        assert statuses["tok3"] == "revoked"
        assert body["total"] == 3

    def test_supplement_with_memory_when_token_missing(self, monkeypatch):
        session = _FakeSession(rows=[])
        monkeypatch.setattr(sp, "get_db_safe", lambda: session)
        future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        sp._portal_links["mem1"] = {
            "tenant_id": "t1",
            "supplier_name": "MemCo",
            "expires_at": future,
            "created_at": "2026-04-17T10:00:00+00:00",
        }
        # Different-tenant link should be filtered out
        sp._portal_links["other"] = {
            "tenant_id": "t2",
            "supplier_name": "Other",
            "expires_at": future,
        }

        client = TestClient(_build_app())
        resp = client.get("/api/v1/portal/links/list?tenant_id=t1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["links"][0]["portal_id"] == "mem1"
        assert body["links"][0]["supplier_name"] == "MemCo"

    def test_memory_expired_link_marked_expired(self, monkeypatch):
        session = _FakeSession(rows=[])
        monkeypatch.setattr(sp, "get_db_safe", lambda: session)
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        sp._portal_links["mem1"] = {
            "tenant_id": "t1",
            "supplier_name": "MemCo",
            "expires_at": past,
        }

        client = TestClient(_build_app())
        resp = client.get("/api/v1/portal/links/list?tenant_id=t1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["links"][0]["status"] == "expired"

    def test_memory_invalid_expiry_stays_active(self, monkeypatch):
        session = _FakeSession(rows=[])
        monkeypatch.setattr(sp, "get_db_safe", lambda: session)
        sp._portal_links["mem1"] = {
            "tenant_id": "t1",
            "supplier_name": "MemCo",
            "expires_at": "not-a-date",
        }

        client = TestClient(_build_app())
        resp = client.get("/api/v1/portal/links/list?tenant_id=t1")
        body = resp.json()
        # Invalid date falls through ValueError → stays 'active'
        assert body["links"][0]["status"] == "active"

    def test_memory_without_expiry_key(self, monkeypatch):
        session = _FakeSession(rows=[])
        monkeypatch.setattr(sp, "get_db_safe", lambda: session)
        sp._portal_links["mem1"] = {"tenant_id": "t1", "supplier_name": "MemCo"}

        client = TestClient(_build_app())
        resp = client.get("/api/v1/portal/links/list?tenant_id=t1")
        body = resp.json()
        assert body["links"][0]["status"] == "active"
        assert body["links"][0]["expires_at"] is None

    def test_db_unavailable_uses_only_memory(self, monkeypatch):
        monkeypatch.setattr(sp, "get_db_safe", lambda: None)
        future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        sp._portal_links["mem1"] = {
            "tenant_id": "t1",
            "supplier_name": "MemCo",
            "expires_at": future,
        }

        client = TestClient(_build_app())
        resp = client.get("/api/v1/portal/links/list?tenant_id=t1")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_db_execute_failure_falls_back_to_memory(self, monkeypatch):
        session = _FakeSession(raise_on_execute=RuntimeError("boom"))
        monkeypatch.setattr(sp, "get_db_safe", lambda: session)
        future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        sp._portal_links["mem1"] = {
            "tenant_id": "t1",
            "supplier_name": "MemCo",
            "expires_at": future,
        }
        client = TestClient(_build_app())
        resp = client.get("/api/v1/portal/links/list?tenant_id=t1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert session.closed is True

    def test_pagination(self, monkeypatch):
        now = datetime.now(timezone.utc)
        future = now + timedelta(days=10)
        rows = [
            ("id%d" % i, "t1", "S%d" % i, "tok%d" % i, "active", now, future)
            for i in range(10)
        ]
        session = _FakeSession(rows=rows)
        monkeypatch.setattr(sp, "get_db_safe", lambda: session)

        client = TestClient(_build_app())
        resp = client.get("/api/v1/portal/links/list?tenant_id=t1&skip=3&limit=2")
        body = resp.json()
        assert body["total"] == 10
        assert len(body["links"]) == 2
        assert body["skip"] == 3
        assert body["limit"] == 2

    def test_memory_null_timestamp_columns(self, monkeypatch):
        session = _FakeSession(rows=[
            ("id1", "t1", "S", "tok1", "active", None, None),
        ])
        monkeypatch.setattr(sp, "get_db_safe", lambda: session)

        client = TestClient(_build_app())
        resp = client.get("/api/v1/portal/links/list?tenant_id=t1")
        body = resp.json()
        assert body["links"][0]["created_at"] is None
        assert body["links"][0]["expires_at"] is None


# ---------------------------------------------------------------------------
# PATCH /links/{portal_id}/revoke
# ---------------------------------------------------------------------------


class TestRevokePortalLink:
    def test_db_success(self, monkeypatch):
        monkeypatch.setattr(sp, "_db_update_portal_link_status", lambda *a, **k: True)
        sp._portal_links["tok"] = {"tenant_id": "t1", "supplier_name": "S"}
        client = TestClient(_build_app())
        resp = client.patch("/api/v1/portal/links/tok/revoke")
        assert resp.status_code == 200
        assert resp.json() == {"status": "revoked", "portal_id": "tok"}
        assert "tok" not in sp._portal_links

    def test_db_failure_still_removes_memory(self, monkeypatch):
        monkeypatch.setattr(sp, "_db_update_portal_link_status", lambda *a, **k: False)
        sp._portal_links["tok"] = {"tenant_id": "t1", "supplier_name": "S"}
        client = TestClient(_build_app())
        resp = client.patch("/api/v1/portal/links/tok/revoke")
        assert resp.status_code == 200
        assert "tok" not in sp._portal_links


# ---------------------------------------------------------------------------
# GET /{portal_id}
# ---------------------------------------------------------------------------


class TestGetPortalDetails:
    def test_active_link_returned(self, monkeypatch):
        future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        sp._portal_links["tok"] = {
            "tenant_id": "t1",
            "supplier_name": "Acme",
            "allowed_cte_types": ["shipping"],
            "expires_at": future,
        }
        monkeypatch.setattr(sp, "_db_get_portal_link", lambda _pid: None)

        client = TestClient(_build_app())
        resp = client.get("/api/v1/portal/tok")
        assert resp.status_code == 200
        body = resp.json()
        assert body["supplier_name"] == "Acme"
        assert body["allowed_cte_types"] == ["shipping"]
        assert body["status"] == "active"

    def test_missing_returns_404(self, monkeypatch):
        monkeypatch.setattr(sp, "_db_get_portal_link", lambda _pid: None)
        client = TestClient(_build_app())
        resp = client.get("/api/v1/portal/missing")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /{portal_id}/preflight
# ---------------------------------------------------------------------------


class TestPreflightSupplierData:
    def _seed_link(self, tok="tok"):
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        sp._portal_links[tok] = {
            "tenant_id": "t1",
            "supplier_name": "Acme",
            "allowed_cte_types": ["shipping"],
            "expires_at": future,
        }

    def _payload(self) -> dict:
        return {
            "traceability_lot_code": "TLC123",
            "product_description": "lettuce",
            "quantity": 10.0,
            "unit_of_measure": "cases",
            "ship_date": "2026-04-17",
            "ship_from_location": "Farm A",
            "ship_to_location": "DC 1",
        }

    def test_preflight_returns_readiness_and_commit_gate(self, monkeypatch):
        self._seed_link()
        monkeypatch.setattr(sp, "_db_get_portal_link", lambda _pid: None)

        client = TestClient(_build_app())
        resp = client.post("/api/v1/portal/tok/preflight", json=self._payload())

        assert resp.status_code == 200
        body = resp.json()
        assert body["supplier_name"] == "Acme"
        assert body["readiness"]["score"] >= 0
        assert body["commit_gate"]["mode"] == "preflight"
        assert body["result"]["total_events"] == 1


# ---------------------------------------------------------------------------
# POST /{portal_id}/submit
# ---------------------------------------------------------------------------


def _make_ingest_response(accepted: int, errors: Optional[list] = None) -> IngestResponse:
    event = EventResult(
        traceability_lot_code="TLC123",
        cte_type="shipping",
        status="accepted" if accepted else "rejected",
        event_id="evt-1",
        sha256_hash="deadbeef",
        errors=errors or [],
    )
    return IngestResponse(
        accepted=accepted,
        rejected=0 if accepted else 1,
        total=1,
        events=[event],
    )


class TestSubmitSupplierData:
    def _seed_link(self, tok="tok"):
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        sp._portal_links[tok] = {
            "tenant_id": "t1",
            "supplier_name": "Acme",
            "allowed_cte_types": ["shipping"],
            "expires_at": future,
        }

    def _payload(self) -> dict:
        return {
            "traceability_lot_code": "TLC123",
            "product_description": "lettuce",
            "quantity": 10.0,
            "unit_of_measure": "cases",
            "ship_date": "2026-04-17",
            "ship_from_location": "Farm A",
            "ship_to_location": "DC 1",
        }

    def test_minimal_payload_accepted(self, monkeypatch):
        self._seed_link()
        monkeypatch.setattr(sp, "_db_get_portal_link", lambda _pid: None)

        async def _fake_ingest(payload):
            return _make_ingest_response(accepted=1)

        monkeypatch.setattr(sp, "ingest_events", _fake_ingest)

        client = TestClient(_build_app())
        resp = client.post("/api/v1/portal/tok/submit", json=self._payload())
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["event_id"] == "evt-1"
        assert body["sha256_hash"] == "deadbeef"
        assert body["supplier_name"] == "Acme"

    def test_full_payload_builds_all_kdes(self, monkeypatch):
        self._seed_link()
        monkeypatch.setattr(sp, "_db_get_portal_link", lambda _pid: None)
        captured: dict = {}

        async def _fake_ingest(payload):
            captured["payload"] = payload
            return _make_ingest_response(accepted=1)

        monkeypatch.setattr(sp, "ingest_events", _fake_ingest)

        data = self._payload()
        data.update({
            "ship_from_gln": "0614141000043",
            "ship_to_gln": "0614141999996",
            "carrier_name": "FreshTrans",
            "po_number": "PO-123",
            "temperature_celsius": 4.2,
            "notes": "Keep refrigerated",
        })
        client = TestClient(_build_app())
        resp = client.post("/api/v1/portal/tok/submit", json=data)
        assert resp.status_code == 200

        payload = captured["payload"]
        assert payload.source == "supplier_portal"
        assert payload.tenant_id == "t1"
        event = payload.events[0]
        kdes = event.kdes
        assert kdes["carrier_name"] == "FreshTrans"
        assert kdes["po_number"] == "PO-123"
        assert kdes["temperature_celsius"] == 4.2
        assert kdes["notes"] == "Keep refrigerated"
        assert kdes["portal_id"] == "tok"
        assert kdes["submission_source"] == "supplier_portal"
        assert kdes["reference_document"] == "PO-123"
        assert kdes["tlc_source_reference"] == "Acme"
        assert kdes["ftl_covered"] is True

    def test_rejected_returns_error_with_joined_errors(self, monkeypatch):
        self._seed_link()
        monkeypatch.setattr(sp, "_db_get_portal_link", lambda _pid: None)

        async def _fake_ingest(payload):
            return _make_ingest_response(
                accepted=0, errors=["bad_tlc", "no_gln"]
            )

        monkeypatch.setattr(sp, "ingest_events", _fake_ingest)

        client = TestClient(_build_app())
        resp = client.post("/api/v1/portal/tok/submit", json=self._payload())
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "error"
        assert "bad_tlc" in body["message"]
        assert "no_gln" in body["message"]

    def test_rejected_with_no_events_uses_unknown_error(self, monkeypatch):
        self._seed_link()
        monkeypatch.setattr(sp, "_db_get_portal_link", lambda _pid: None)

        async def _fake_ingest(payload):
            return IngestResponse(accepted=0, rejected=1, total=1, events=[])

        monkeypatch.setattr(sp, "ingest_events", _fake_ingest)

        client = TestClient(_build_app())
        resp = client.post("/api/v1/portal/tok/submit", json=self._payload())
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "error"
        assert "Unknown error" in body["message"]

    def test_missing_link_returns_404(self, monkeypatch):
        monkeypatch.setattr(sp, "_db_get_portal_link", lambda _pid: None)
        client = TestClient(_build_app())
        resp = client.post("/api/v1/portal/missing/submit", json=self._payload())
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_prefix(self):
        assert router.prefix == "/api/v1/portal"

    def test_tags(self):
        assert "Supplier Portal" in router.tags

    def test_endpoints_registered(self):
        paths = {route.path for route in router.routes}
        assert "/api/v1/portal/links" in paths
        assert "/api/v1/portal/links/list" in paths
        assert "/api/v1/portal/links/{portal_id}/revoke" in paths
        assert "/api/v1/portal/{portal_id}" in paths
        assert "/api/v1/portal/{portal_id}/preflight" in paths
        assert "/api/v1/portal/{portal_id}/submit" in paths
