"""Coverage for app/supplier_mgmt.py — supplier dashboard, portal links, health.

Issue: #1342
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import supplier_mgmt as sm
from app.supplier_mgmt import (
    CreateSupplierRequest,
    SupplierDashboard,
    SupplierRecord,
    _db_add_supplier,
    _db_get_suppliers,
    _suppliers_store,
    router,
)
from app.webhook_compat import _verify_api_key


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_store():
    _suppliers_store.clear()
    yield
    _suppliers_store.clear()


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def _mock_db_session(rows=None, raise_on_execute=False):
    session = MagicMock()
    if raise_on_execute:
        session.execute.side_effect = RuntimeError("boom")
    else:
        result = MagicMock()
        result.fetchall.return_value = rows or []
        session.execute.return_value = result
    return session


def _make_supplier(**overrides) -> SupplierRecord:
    defaults = dict(
        id="t1-sup-001",
        name="Acme Farms",
        contact_email="contact@acme.com",
        portal_link_id=None,
        portal_status="no_link",
        compliance_status="unknown",
    )
    defaults.update(overrides)
    return SupplierRecord(**defaults)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestPydanticModels:
    def test_supplier_record_defaults(self):
        s = _make_supplier()
        assert s.submissions_count == 0
        assert s.last_submission is None
        assert s.missing_kdes == []
        assert s.products == []
        assert s.is_sample is False

    def test_supplier_record_default_factory_independent(self):
        a = _make_supplier()
        b = _make_supplier(id="t1-sup-002")
        a.products.append("Spinach")
        a.missing_kdes.append("tlc")
        assert b.products == []
        assert b.missing_kdes == []

    def test_supplier_dashboard_schema(self):
        dash = SupplierDashboard(
            tenant_id="t1", total_suppliers=0, active_portal_links=0,
            expired_portal_links=0, total_submissions=0,
            compliance_rate=0, suppliers=[],
        )
        assert dash.total_suppliers == 0

    def test_create_supplier_request_defaults(self):
        req = CreateSupplierRequest(name="Acme", contact_email="a@x.com")
        assert req.products == []

    def test_create_supplier_request_with_products(self):
        req = CreateSupplierRequest(name="Acme", contact_email="a@x.com", products=["P1", "P2"])
        assert req.products == ["P1", "P2"]


# ---------------------------------------------------------------------------
# _db_get_suppliers
# ---------------------------------------------------------------------------


class TestDbGetSuppliers:
    def test_returns_none_when_no_db(self, monkeypatch):
        monkeypatch.setattr(sm, "get_db_safe", lambda: None)
        assert _db_get_suppliers("t1") is None

    def test_empty_rows_returns_empty_list(self, monkeypatch):
        session = _mock_db_session(rows=[])
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)
        assert _db_get_suppliers("t1") == []
        session.close.assert_called_once()

    def test_rows_mapped_to_records(self, monkeypatch):
        session = _mock_db_session(rows=[
            ("t1-sup-001", "Acme", "a@x.com", "portal-abc", "active", 5,
             "2026-04-18T00:00:00+00:00", "compliant",
             '["kde1", "kde2"]', '["Spinach"]'),
        ])
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)
        suppliers = _db_get_suppliers("t1")
        assert len(suppliers) == 1
        s = suppliers[0]
        assert s.id == "t1-sup-001"
        assert s.portal_status == "active"
        assert s.submissions_count == 5
        assert s.missing_kdes == ["kde1", "kde2"]
        assert s.products == ["Spinach"]
        assert s.is_sample is False

    def test_null_json_fields_become_empty_lists(self, monkeypatch):
        session = _mock_db_session(rows=[
            ("t1-sup-001", "Acme", "a@x.com", None, "no_link", 0,
             None, "unknown", None, None),
        ])
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)
        suppliers = _db_get_suppliers("t1")
        assert suppliers[0].missing_kdes == []
        assert suppliers[0].products == []

    def test_exception_returns_none_and_closes(self, monkeypatch):
        session = _mock_db_session(raise_on_execute=True)
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)
        assert _db_get_suppliers("t1") is None
        session.close.assert_called_once()

    def test_tid_param_passed(self, monkeypatch):
        session = _mock_db_session(rows=[])
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)
        _db_get_suppliers("tenant-xyz")
        _sql, params = session.execute.call_args[0]
        assert params == {"tid": "tenant-xyz"}


# ---------------------------------------------------------------------------
# _db_add_supplier
# ---------------------------------------------------------------------------


class TestDbAddSupplier:
    def test_returns_false_when_no_db(self, monkeypatch):
        monkeypatch.setattr(sm, "get_db_safe", lambda: None)
        assert _db_add_supplier("t1", _make_supplier()) is False

    def test_happy_path(self, monkeypatch):
        session = _mock_db_session()
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)
        result = _db_add_supplier("t1", _make_supplier(products=["Spinach"]))
        assert result is True
        session.execute.assert_called_once()
        session.commit.assert_called_once()
        session.close.assert_called_once()

    def test_json_fields_serialized(self, monkeypatch):
        session = _mock_db_session()
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)
        supp = _make_supplier(products=["Spinach", "Kale"], missing_kdes=["tlc"])
        _db_add_supplier("t1", supp)
        _sql, params = session.execute.call_args[0]
        assert params["kdes"] == '["tlc"]'
        assert params["prods"] == '["Spinach", "Kale"]'
        assert params["tid"] == "t1"
        assert params["id"] == "t1-sup-001"

    def test_exception_rolls_back_and_returns_false(self, monkeypatch):
        session = _mock_db_session(raise_on_execute=True)
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)
        assert _db_add_supplier("t1", _make_supplier()) is False
        session.rollback.assert_called_once()
        session.close.assert_called_once()


# ---------------------------------------------------------------------------
# GET /{tenant_id} — dashboard
# ---------------------------------------------------------------------------


class TestGetSupplierDashboardEndpoint:
    def test_db_hit_computes_counters(self, client, monkeypatch):
        suppliers = [
            _make_supplier(id="s1", portal_status="active", submissions_count=3, compliance_status="compliant"),
            _make_supplier(id="s2", portal_status="expired", submissions_count=1, compliance_status="partial"),
            _make_supplier(id="s3", portal_status="active", submissions_count=2, compliance_status="compliant"),
        ]
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: suppliers)
        resp = client.get("/api/v1/suppliers/t1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_suppliers"] == 3
        assert body["active_portal_links"] == 2
        assert body["expired_portal_links"] == 1
        assert body["total_submissions"] == 6
        assert body["compliance_rate"] == pytest.approx(66.7)

    def test_empty_suppliers_compliance_rate_zero(self, client, monkeypatch):
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: [])
        resp = client.get("/api/v1/suppliers/t1")
        assert resp.json()["compliance_rate"] == 0

    def test_db_none_falls_back_to_memory(self, client, monkeypatch):
        _suppliers_store["t1"] = [_make_supplier(portal_status="active", compliance_status="compliant")]
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: None)
        resp = client.get("/api/v1/suppliers/t1")
        body = resp.json()
        assert body["total_suppliers"] == 1
        assert body["active_portal_links"] == 1

    def test_db_none_empty_memory_initializes(self, client, monkeypatch):
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: None)
        resp = client.get("/api/v1/suppliers/brand-new")
        assert resp.json()["total_suppliers"] == 0
        assert "brand-new" in _suppliers_store


# ---------------------------------------------------------------------------
# POST /{tenant_id} — add supplier
# ---------------------------------------------------------------------------


class TestAddSupplierEndpoint:
    def test_add_first_supplier_db_success(self, client, monkeypatch):
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: [])
        monkeypatch.setattr(sm, "_db_add_supplier", lambda tid, s: True)
        resp = client.post(
            "/api/v1/suppliers/t1",
            json={"name": "Acme", "contact_email": "a@x.com", "products": ["Spinach"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created"] is True
        assert body["supplier"]["id"] == "t1-sup-001"
        assert body["supplier"]["products"] == ["Spinach"]
        assert body["supplier"]["portal_status"] == "no_link"
        assert body["supplier"]["compliance_status"] == "unknown"

    def test_add_supplier_id_increments(self, client, monkeypatch):
        existing = [_make_supplier(id=f"t1-sup-{i:03d}") for i in range(1, 4)]
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: existing)
        monkeypatch.setattr(sm, "_db_add_supplier", lambda tid, s: True)
        resp = client.post("/api/v1/suppliers/t1", json={"name": "Z", "contact_email": "z@x.com"})
        assert resp.json()["supplier"]["id"] == "t1-sup-004"

    def test_add_supplier_memory_fallback_when_db_unavailable(self, client, monkeypatch):
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: None)
        monkeypatch.setattr(sm, "_db_add_supplier", lambda tid, s: False)
        resp = client.post("/api/v1/suppliers/t1", json={"name": "Acme", "contact_email": "a@x.com"})
        assert resp.status_code == 200
        assert len(_suppliers_store["t1"]) == 1
        assert _suppliers_store["t1"][0].name == "Acme"

    def test_add_supplier_db_read_ok_write_fails_with_no_memory(self, client, monkeypatch):
        # DB read returns [], write fails, memory empty -> initializes and appends
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: [])
        monkeypatch.setattr(sm, "_db_add_supplier", lambda tid, s: False)
        assert "fresh" not in _suppliers_store
        resp = client.post("/api/v1/suppliers/fresh", json={"name": "Acme", "contact_email": "a@x.com"})
        assert resp.status_code == 200
        assert "fresh" in _suppliers_store
        assert len(_suppliers_store["fresh"]) == 1


# ---------------------------------------------------------------------------
# POST /{tenant_id}/{supplier_id}/send-link
# ---------------------------------------------------------------------------


class TestSendPortalLinkEndpoint:
    def test_send_link_db_success(self, client, monkeypatch):
        supp = _make_supplier(id="t1-sup-001")
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: [supp])
        monkeypatch.setattr(sm, "_db_add_supplier", lambda tid, s: True)
        resp = client.post("/api/v1/suppliers/t1/t1-sup-001/send-link")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sent"] is True
        assert body["supplier_id"] == "t1-sup-001"
        assert "portal-001-new" in body["portal_link"]
        assert body["portal_link"].startswith("https://regengine.co/portal/")
        assert "contact@acme.com" in body["message"]

    def test_send_link_memory_fallback(self, client, monkeypatch):
        supp = _make_supplier(id="t1-sup-001")
        _suppliers_store["t1"] = [supp]
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: None)
        monkeypatch.setattr(sm, "_db_add_supplier", lambda tid, s: False)
        resp = client.post("/api/v1/suppliers/t1/t1-sup-001/send-link")
        assert resp.status_code == 200
        assert resp.json()["sent"] is True
        assert _suppliers_store["t1"][0].portal_status == "active"
        assert _suppliers_store["t1"][0].portal_link_id == "portal-001-new"

    def test_send_link_db_read_ok_write_fails_with_no_memory_copy(self, client, monkeypatch):
        # DB source of truth, write fails, memory has nothing to sync — no error
        supp = _make_supplier(id="t1-sup-001")
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: [supp])
        monkeypatch.setattr(sm, "_db_add_supplier", lambda tid, s: False)
        resp = client.post("/api/v1/suppliers/t1/t1-sup-001/send-link")
        assert resp.status_code == 200
        assert resp.json()["sent"] is True
        # No memory cache was created, so _suppliers_store["t1"] doesn't exist
        assert "t1" not in _suppliers_store

    def test_send_link_unknown_supplier_returns_error(self, client, monkeypatch):
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: [])
        resp = client.post("/api/v1/suppliers/t1/does-not-exist/send-link")
        assert resp.status_code == 200
        assert resp.json() == {"sent": False, "error": "Supplier not found"}

    def test_send_link_db_none_no_memory(self, client, monkeypatch):
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: None)
        resp = client.post("/api/v1/suppliers/t1/t1-sup-001/send-link")
        assert resp.json() == {"sent": False, "error": "Supplier not found"}


# ---------------------------------------------------------------------------
# GET /{tenant_id}/health
# ---------------------------------------------------------------------------


class TestSupplierHealthEndpoint:
    def test_no_suppliers(self, client, monkeypatch):
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: [])
        resp = client.get("/api/v1/suppliers/t1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_suppliers"] == 0
        assert body["active_last_30_days"] == 0
        assert body["inactive_30_days"] == 0
        assert body["compliance_breakdown"] == {
            "compliant": 0, "partial": 0, "non_compliant": 0, "unknown": 0,
        }

    def test_active_vs_inactive_partition(self, client, monkeypatch):
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(days=5)).isoformat()
        old = (now - timedelta(days=60)).isoformat()
        suppliers = [
            _make_supplier(id="s1", last_submission=recent, compliance_status="compliant"),
            _make_supplier(id="s2", last_submission=old, compliance_status="partial"),
            _make_supplier(id="s3", last_submission=None, compliance_status="non_compliant"),
        ]
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: suppliers)
        resp = client.get("/api/v1/suppliers/t1/health")
        body = resp.json()
        assert body["total_suppliers"] == 3
        assert body["active_last_30_days"] == 1
        assert body["inactive_30_days"] == 2  # old submission + no submission
        breakdown = body["compliance_breakdown"]
        assert breakdown["compliant"] == 1
        assert breakdown["partial"] == 1
        assert breakdown["non_compliant"] == 1
        assert breakdown["unknown"] == 0

    def test_compliance_breakdown_counts_unknown(self, client, monkeypatch):
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: [
            _make_supplier(compliance_status="unknown"),
        ])
        resp = client.get("/api/v1/suppliers/t1/health")
        assert resp.json()["compliance_breakdown"]["unknown"] == 1

    def test_db_none_falls_back_to_memory_for_health(self, client, monkeypatch):
        _suppliers_store["t1"] = [_make_supplier(submissions_count=7)]
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: None)
        resp = client.get("/api/v1/suppliers/t1/health")
        assert resp.json()["total_submissions"] == 7

    def test_db_none_empty_memory_initializes_for_health(self, client, monkeypatch):
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: None)
        resp = client.get("/api/v1/suppliers/new/health")
        assert resp.status_code == 200
        assert "new" in _suppliers_store
        assert resp.json()["total_suppliers"] == 0


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_prefix_and_tags(self):
        assert router.prefix == "/api/v1/suppliers"
        assert "Supplier Management" in router.tags

    def test_registered_paths(self):
        paths = {r.path for r in router.routes}
        assert "/api/v1/suppliers/{tenant_id}" in paths
        assert "/api/v1/suppliers/{tenant_id}/{supplier_id}/send-link" in paths
        assert "/api/v1/suppliers/{tenant_id}/health" in paths
