"""Coverage for app/supplier_mgmt.py — supplier dashboard, portal links, health.

Issue: #1342
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
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
from app.webhook_compat import _verify_api_key, require_tenant_context
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from shared.tenant_context import TenantContext
from sqlalchemy.exc import DataError, OperationalError, ProgrammingError

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

    async def _tenant_ctx(request: Request) -> TenantContext:
        return TenantContext(
            tenant_id=request.path_params.get("tenant_id", "t1"),
            principal_kind="test",
            principal_id="supplier-mgmt-test",
        )

    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[require_tenant_context] = _tenant_ctx
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


def _ddl_columns(sql_file: str, table: str) -> set[str]:
    """Column names of ``table`` as declared in an ``alembic/sql`` file."""
    ddl = (Path(__file__).resolve().parents[3] / "alembic/sql" / sql_file).read_text()
    body = ddl.split(f"CREATE TABLE IF NOT EXISTS {table} (", 1)[1].split("\n);", 1)[0]
    return set(re.findall(r"^ {4}([a-z_]+) ", body, flags=re.MULTILINE))


def _identifiers(sql: str) -> set[str]:
    """Lower-case words of ``sql`` other than bind names. Keywords are upper-case, so these are identifiers."""
    return set(re.findall(r"\b[a-z_]+\b", re.sub(r":\w+", " ", sql)))


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
            tenant_id="t1",
            total_suppliers=0,
            active_portal_links=0,
            expired_portal_links=0,
            total_submissions=0,
            compliance_rate=0,
            suppliers=[],
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
        """Rows carry what the driver returns: uuid.UUID, datetime and lists for the TEXT[] columns.

        ``json.loads`` on those lists raised ``TypeError``, the except branch
        returned ``None`` and every tenant with a populated array saw an empty
        dashboard. ``test_supplier_mgmt_pg.py`` reads real rows back.
        """
        supplier_id = uuid.uuid4()
        session = _mock_db_session(
            rows=[
                (
                    supplier_id,
                    "Acme",
                    "a@x.com",
                    "portal-abc",
                    "active",
                    5,
                    datetime(2026, 4, 18, tzinfo=timezone.utc),
                    "compliant",
                    ["kde1", "kde2"],
                    ["Spinach"],
                ),
            ]
        )
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)
        suppliers = _db_get_suppliers("t1")
        assert len(suppliers) == 1
        s = suppliers[0]
        assert s.id == str(supplier_id)
        assert s.portal_status == "active"
        assert s.submissions_count == 5
        assert s.last_submission == "2026-04-18T00:00:00+00:00"
        assert s.missing_kdes == ["kde1", "kde2"]
        assert s.products == ["Spinach"]
        assert s.is_sample is False

    def test_null_array_columns_become_empty_lists(self, monkeypatch):
        session = _mock_db_session(
            rows=[
                (uuid.uuid4(), "Acme", "a@x.com", None, "no_link", 0, None, "unknown", None, None),
            ]
        )
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)
        suppliers = _db_get_suppliers("t1")
        assert suppliers[0].missing_kdes == []
        assert suppliers[0].products == []
        assert suppliers[0].last_submission is None

    def test_exception_returns_none_and_closes(self, monkeypatch):
        session = _mock_db_session(raise_on_execute=True)
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)
        assert _db_get_suppliers("t1") is None
        session.close.assert_called_once()

    def test_database_error_returns_none_and_closes(self, monkeypatch):
        """A statement Postgres rejects is the fallback case, not a 500: ``SQLAlchemyError`` is caught."""
        session = _mock_db_session()
        session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("connection lost"))
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)
        assert _db_get_suppliers("t1") is None
        session.close.assert_called_once()

    def test_statement_references_only_real_columns(self, monkeypatch):
        """The SELECT names ``fsma.tenant_suppliers`` columns as V042 declares them.

        The mock session never parses SQL; ``test_supplier_mgmt_pg.py`` runs
        the statement on a live cluster and this is the copy that needs no
        database.
        """
        columns = _ddl_columns("V042__tenant_feature_data_tables.sql", "fsma.tenant_suppliers")
        assert {"missing_kdes", "products"} <= columns  # the DDL parse itself still works

        session = _mock_db_session(rows=[])
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)
        _db_get_suppliers("t1")
        sql = str(session.execute.call_args[0][0])

        referenced = _identifiers(sql) - {"fsma", "tenant_suppliers"}
        assert referenced <= columns, f"not columns of fsma.tenant_suppliers: {sorted(referenced - columns)}"

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

    def test_array_columns_bound_as_lists(self, monkeypatch):
        """``missing_kdes`` and ``products`` are TEXT[]: the binds are Python lists, never JSON strings.

        ``json.dumps`` produced ``'["tlc"]'``, which Postgres rejects as a
        malformed array literal for every supplier, empty lists included.
        """
        session = _mock_db_session()
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)
        supp = _make_supplier(products=["Spinach", "Kale"], missing_kdes=["tlc"])
        _db_add_supplier("t1", supp)
        _sql, params = session.execute.call_args[0]
        assert params["kdes"] == ["tlc"]
        assert params["prods"] == ["Spinach", "Kale"]
        assert params["tid"] == "t1"
        assert params["id"] == "t1-sup-001"

    def test_exception_rolls_back_and_returns_false(self, monkeypatch):
        session = _mock_db_session(raise_on_execute=True)
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)
        assert _db_add_supplier("t1", _make_supplier()) is False
        session.rollback.assert_called_once()
        session.close.assert_called_once()

    def test_database_error_rolls_back_and_returns_false(self, monkeypatch):
        """A rejected statement returns False so the router falls back to memory instead of raising."""
        session = _mock_db_session()
        session.execute.side_effect = DataError("INSERT", {}, Exception("malformed array literal"))
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)
        assert _db_add_supplier("t1", _make_supplier()) is False
        session.rollback.assert_called_once()
        session.close.assert_called_once()

    @pytest.mark.parametrize("code_attribute", ["sqlstate", "pgcode"])
    @pytest.mark.parametrize("operation", ["execute", "commit"])
    def test_permission_failure_rolls_back_and_raises(self, monkeypatch, code_attribute, operation):
        """Driver-shaped mocks cover both psycopg versions and commit-time errors."""
        session = _mock_db_session()
        error = ProgrammingError("INSERT", {}, SimpleNamespace(**{code_attribute: "42501"}))
        getattr(session, operation).side_effect = error
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)

        with pytest.raises(HTTPException) as raised:
            _db_add_supplier("t1", _make_supplier())

        assert raised.value.status_code == 503
        assert raised.value.detail == "Supplier changes could not be saved"
        session.rollback.assert_called_once()
        session.close.assert_called_once()

    def test_statement_references_only_real_columns(self, monkeypatch):
        """The INSERT ... ON CONFLICT names ``fsma.tenant_suppliers`` columns as V042 declares them."""
        columns = _ddl_columns("V042__tenant_feature_data_tables.sql", "fsma.tenant_suppliers")

        session = _mock_db_session()
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)
        _db_add_supplier("t1", _make_supplier())
        sql = str(session.execute.call_args[0][0])

        referenced = _identifiers(sql) - {"fsma", "tenant_suppliers", "now", "false"}
        assert referenced <= columns, f"not columns of fsma.tenant_suppliers: {sorted(referenced - columns)}"


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
        assert uuid.UUID(body["supplier"]["id"]).version == 4
        assert body["supplier"]["products"] == ["Spinach"]
        assert body["supplier"]["portal_status"] == "no_link"
        assert body["supplier"]["compliance_status"] == "unknown"

    def test_add_supplier_ids_are_distinct_uuids(self, client, monkeypatch):
        """``fsma.tenant_suppliers.id`` is UUID: Postgres rejected the old ``{tenant}-sup-001`` ids."""
        written = []
        monkeypatch.setattr(sm, "_db_add_supplier", lambda tid, s: written.append(s) or True)
        ids = [
            client.post("/api/v1/suppliers/t1", json={"name": "Z", "contact_email": "z@x.com"}).json()["supplier"]["id"]
            for _ in range(2)
        ]
        assert [uuid.UUID(i).version for i in ids] == [4, 4]
        assert len(set(ids)) == 2
        assert [s.id for s in written] == ids

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
    def test_denied_write_preserves_memory_record(self, client, monkeypatch):
        supplier = _make_supplier()
        _suppliers_store["t1"] = [supplier]
        monkeypatch.setattr(sm, "_db_get_suppliers", lambda tid: None)
        session = _mock_db_session()
        session.execute.side_effect = ProgrammingError("INSERT", {}, SimpleNamespace(sqlstate="42501"))
        monkeypatch.setattr(sm, "get_db_safe", lambda: session)

        response = client.post(f"/api/v1/suppliers/t1/{supplier.id}/send-link")

        assert response.status_code == 503
        assert response.json() == {"detail": "Supplier changes could not be saved"}
        assert _suppliers_store["t1"][0].portal_status == "no_link"
        assert _suppliers_store["t1"][0].portal_link_id is None

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
            "compliant": 0,
            "partial": 0,
            "non_compliant": 0,
            "unknown": 0,
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
        monkeypatch.setattr(
            sm,
            "_db_get_suppliers",
            lambda tid: [
                _make_supplier(compliance_status="unknown"),
            ],
        )
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
