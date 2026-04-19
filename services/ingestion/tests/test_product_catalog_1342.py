"""Regression tests for ``services/ingestion/app/product_catalog.py``.

Part of the #1342 ingestion coverage sweep. Covers FTL catalog CRUD,
DB/memory fallback, derive-from-events, GTIN learn path, and router
endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app import product_catalog as pc
from app.product_catalog import (
    CreateProductRequest,
    FTL_CATEGORIES,
    Product,
    ProductCatalogResponse,
    _db_add_product,
    _db_get_catalog,
    _db_lookup_by_gtin,
    _derive_products_from_events,
    _fsma_row_to_product,
    _memory_learn,
    _row_to_product,
    learn_from_event,
    router,
)
from app.webhook_compat import _verify_api_key


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_store():
    pc._catalog_store.clear()
    yield
    pc._catalog_store.clear()


class _MappingRow:
    """Mimics a SQLAlchemy Row with ._mapping."""
    def __init__(self, mapping: dict):
        self._mapping = mapping


class _FakeResult:
    def __init__(self, rows=None, row=None):
        self._rows = rows or []
        self._row = row

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class _FakeSession:
    def __init__(
        self,
        responses: Optional[list] = None,
        raise_on_execute: Optional[Exception] = None,
    ):
        """responses = ordered list of _FakeResult (or tuples for raw)."""
        self.responses = list(responses or [])
        self._raise = raise_on_execute
        self.executed = 0
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, stmt, params=None):
        self.executed += 1
        if self._raise is not None:
            exc = self._raise
            # Clear so only first execute raises unless list
            if not isinstance(self._raise, list):
                self._raise = None
            raise exc
        if self.responses:
            return self.responses.pop(0)
        return _FakeResult()

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
# Models
# ---------------------------------------------------------------------------


class TestModels:
    def test_product_defaults(self):
        p = Product(id="1", name="Kale", category="Leafy Greens")
        assert p.ftl_covered is True
        assert p.suppliers == []
        assert p.facilities == []
        assert p.cte_count == 0
        assert p.last_cte is None
        assert p.is_sample is False

    def test_product_lists_independent(self):
        p1 = Product(id="1", name="Kale", category="Leafy Greens")
        p2 = Product(id="2", name="Spinach", category="Leafy Greens")
        p1.suppliers.append("A")
        assert p2.suppliers == []

    def test_catalog_response_model(self):
        r = ProductCatalogResponse(
            tenant_id="t1", total=0, ftl_covered=0, categories=[], products=[]
        )
        assert r.tenant_id == "t1"

    def test_create_product_request_defaults(self):
        req = CreateProductRequest(name="Kale", category="Leafy Greens")
        assert req.sku == ""
        assert req.suppliers == []
        assert req.facilities == []


# ---------------------------------------------------------------------------
# _row_to_product
# ---------------------------------------------------------------------------


class TestRowToProduct:
    def test_mapping_row(self):
        row = _MappingRow({
            "id": "p1", "name": "Kale", "category": "Leafy Greens",
            "ftl_covered": True, "sku": "SKU1", "gtin": "GTIN1",
            "description": "Green", "suppliers": ["A"], "facilities": ["F1"],
            "cte_count": 5, "last_cte": "2026-04-01", "created_at": "2026-01-01",
        })
        p = _row_to_product(row)
        assert p.id == "p1"
        assert p.name == "Kale"
        assert p.cte_count == 5
        assert p.last_cte == "2026-04-01"

    def test_dict_row_with_defaults(self):
        p = _row_to_product({"id": 42, "name": "Kale"})
        assert p.id == "42"
        assert p.category == ""
        assert p.ftl_covered is True
        assert p.suppliers == []
        assert p.facilities == []
        assert p.cte_count == 0

    def test_null_suppliers_become_empty(self):
        p = _row_to_product({"id": "1", "name": "x", "suppliers": None, "facilities": None})
        assert p.suppliers == []
        assert p.facilities == []


# ---------------------------------------------------------------------------
# _fsma_row_to_product
# ---------------------------------------------------------------------------


class TestFsmaRowToProduct:
    def test_mapping_row(self):
        row = _MappingRow({
            "id": "p1", "name": "Kale", "ftl_category": "Leafy Greens",
            "ftl_covered": True, "sku": "S", "gtin": "G",
            "description": "d", "unit_of_measure": "kg", "created_at": "2026-01-01",
        })
        p = _fsma_row_to_product(row)
        assert p.category == "Leafy Greens"
        assert p.sku == "S"

    def test_null_fields_coalesced_to_empty(self):
        p = _fsma_row_to_product({
            "id": "p1", "name": "x", "ftl_category": None,
            "sku": None, "gtin": None, "description": None,
        })
        assert p.category == ""
        assert p.sku == ""
        assert p.gtin == ""
        assert p.description == ""
        assert p.suppliers == []

    def test_ftl_covered_false_default(self):
        p = _fsma_row_to_product({"id": "1", "name": "x"})
        assert p.ftl_covered is False


# ---------------------------------------------------------------------------
# _derive_products_from_events
# ---------------------------------------------------------------------------


class TestDeriveProducts:
    def test_normal_rows(self):
        rows = [
            _MappingRow({
                "product_reference": "Kale",
                "cte_count": 5,
                "last_cte": "2026-04-01",
                "first_seen": "2026-01-01",
                "lot_codes": ["L1", "L2"],
            }),
            _MappingRow({
                "product_reference": "Spinach",
                "cte_count": 3,
                "last_cte": "2026-03-01",
                "first_seen": "2026-02-01",
                "lot_codes": [],
            }),
        ]
        db = _FakeSession(responses=[_FakeResult(rows=rows)])
        products = _derive_products_from_events(db, "t1")
        assert len(products) == 2
        assert products[0].name == "Kale"
        assert products[0].cte_count == 5
        assert products[0].last_cte == "2026-04-01"
        assert products[0].created_at == "2026-01-01"

    def test_null_last_and_first(self):
        rows = [_MappingRow({
            "product_reference": "Kale",
            "cte_count": 0,
            "last_cte": None,
            "first_seen": None,
            "lot_codes": None,
        })]
        db = _FakeSession(responses=[_FakeResult(rows=rows)])
        products = _derive_products_from_events(db, "t1")
        assert products[0].last_cte is None
        assert products[0].created_at == ""

    def test_sql_error_returns_empty(self):
        db = _FakeSession(raise_on_execute=SQLAlchemyError("db err"))
        products = _derive_products_from_events(db, "t1")
        assert products == []

    def test_category_filter_returns_empty(self):
        rows = [_MappingRow({
            "product_reference": "Kale",
            "cte_count": 1,
            "last_cte": None,
            "first_seen": None,
            "lot_codes": [],
        })]
        db = _FakeSession(responses=[_FakeResult(rows=rows)])
        products = _derive_products_from_events(db, "t1", category="Leafy Greens")
        assert products == []


# ---------------------------------------------------------------------------
# _db_get_catalog
# ---------------------------------------------------------------------------


def _fsma_row(**overrides):
    base = {
        "id": "p1",
        "name": "Kale",
        "description": "d",
        "gtin": "G",
        "sku": "S",
        "ftl_category": "Leafy Greens",
        "ftl_covered": True,
        "unit_of_measure": "kg",
        "created_at": "2026-01-01",
    }
    base.update(overrides)
    return _MappingRow(base)


class TestDbGetCatalog:
    def test_no_db(self, monkeypatch):
        monkeypatch.setattr(pc, "get_db_safe", lambda: None)
        assert _db_get_catalog("t1") is None

    def test_no_category(self, monkeypatch):
        session = _FakeSession(responses=[_FakeResult(rows=[_fsma_row(name="Kale")])])
        monkeypatch.setattr(pc, "get_db_safe", lambda: session)
        products = _db_get_catalog("t1")
        assert len(products) == 1
        assert products[0].name == "Kale"
        assert session.closed is True

    def test_with_category(self, monkeypatch):
        session = _FakeSession(responses=[_FakeResult(rows=[_fsma_row(name="Kale")])])
        monkeypatch.setattr(pc, "get_db_safe", lambda: session)
        products = _db_get_catalog("t1", category="Leafy Greens")
        assert len(products) == 1

    def test_empty_derives_from_events(self, monkeypatch):
        # First call returns empty products; derive fallback returns one row
        session = _FakeSession(responses=[
            _FakeResult(rows=[]),  # empty products table
            _FakeResult(rows=[_MappingRow({
                "product_reference": "Kale",
                "cte_count": 3,
                "last_cte": "2026-04-01",
                "first_seen": "2026-01-01",
                "lot_codes": [],
            })]),
        ])
        monkeypatch.setattr(pc, "get_db_safe", lambda: session)
        products = _db_get_catalog("t1")
        assert len(products) == 1
        assert products[0].name == "Kale"

    def test_sql_error_returns_none(self, monkeypatch):
        session = _FakeSession(raise_on_execute=SQLAlchemyError("boom"))
        monkeypatch.setattr(pc, "get_db_safe", lambda: session)
        assert _db_get_catalog("t1") is None
        assert session.closed is True


# ---------------------------------------------------------------------------
# _db_add_product
# ---------------------------------------------------------------------------


class TestDbAddProduct:
    def test_no_db(self, monkeypatch):
        monkeypatch.setattr(pc, "get_db_safe", lambda: None)
        prod = Product(id="1", name="Kale", category="Leafy Greens")
        assert _db_add_product("t1", prod) is False

    def test_success(self, monkeypatch):
        session = _FakeSession()
        monkeypatch.setattr(pc, "get_db_safe", lambda: session)
        prod = Product(id="1", name="Kale", category="Leafy Greens")
        assert _db_add_product("t1", prod) is True
        assert session.committed is True
        assert session.closed is True

    def test_sql_error_rolls_back(self, monkeypatch):
        session = _FakeSession(raise_on_execute=SQLAlchemyError("oops"))
        monkeypatch.setattr(pc, "get_db_safe", lambda: session)
        prod = Product(id="1", name="Kale", category="Leafy Greens")
        assert _db_add_product("t1", prod) is False
        assert session.rolled_back is True


# ---------------------------------------------------------------------------
# _db_lookup_by_gtin
# ---------------------------------------------------------------------------


class TestDbLookupByGtin:
    def test_no_db(self, monkeypatch):
        monkeypatch.setattr(pc, "get_db_safe", lambda: None)
        assert _db_lookup_by_gtin("t1", "G1") is None

    def test_found(self, monkeypatch):
        session = _FakeSession(responses=[_FakeResult(row=_fsma_row(name="Kale"))])
        monkeypatch.setattr(pc, "get_db_safe", lambda: session)
        product = _db_lookup_by_gtin("t1", "G")
        assert product is not None
        assert product.name == "Kale"

    def test_not_found(self, monkeypatch):
        session = _FakeSession(responses=[_FakeResult(row=None)])
        monkeypatch.setattr(pc, "get_db_safe", lambda: session)
        assert _db_lookup_by_gtin("t1", "G") is None

    def test_sql_error(self, monkeypatch):
        session = _FakeSession(raise_on_execute=SQLAlchemyError("err"))
        monkeypatch.setattr(pc, "get_db_safe", lambda: session)
        assert _db_lookup_by_gtin("t1", "G") is None
        assert session.closed is True


# ---------------------------------------------------------------------------
# learn_from_event
# ---------------------------------------------------------------------------


class TestLearnFromEvent:
    def test_no_gtin_early_return(self, monkeypatch):
        calls = []
        monkeypatch.setattr(pc, "get_db_safe", lambda: (_ for _ in ()).throw(AssertionError("should not be called")))
        # Call without any gtin; assert no mutation
        learn_from_event("t1", {"product_description": "Kale"})
        assert "t1" not in pc._catalog_store

    def test_gtin_from_kdes(self, monkeypatch):
        session = _FakeSession()
        monkeypatch.setattr(pc, "get_db_safe", lambda: session)
        learn_from_event("t1", {
            "kdes": {"gtin": "G1"},
            "product_description": "Kale",
        })
        assert session.committed is True

    def test_gtin_from_top_level(self, monkeypatch):
        session = _FakeSession()
        monkeypatch.setattr(pc, "get_db_safe", lambda: session)
        learn_from_event("t1", {
            "gtin": "G1",
            "product_description": "Kale",
        })
        assert session.committed is True

    def test_no_db_falls_back_to_memory(self, monkeypatch):
        monkeypatch.setattr(pc, "get_db_safe", lambda: None)
        learn_from_event("t1", {
            "gtin": "G1",
            "product_description": "Kale",
            "location_name": "Farm A",
        })
        assert len(pc._catalog_store["t1"]) == 1
        assert pc._catalog_store["t1"][0].gtin == "G1"

    def test_db_success(self, monkeypatch):
        session = _FakeSession()
        monkeypatch.setattr(pc, "get_db_safe", lambda: session)
        learn_from_event("t1", {"gtin": "G1", "product_description": "Kale"})
        assert session.committed is True
        assert session.closed is True
        # DB success does NOT also populate memory
        assert "t1" not in pc._catalog_store

    def test_db_failure_falls_back_to_memory(self, monkeypatch):
        session = _FakeSession(raise_on_execute=SQLAlchemyError("err"))
        monkeypatch.setattr(pc, "get_db_safe", lambda: session)
        learn_from_event("t1", {"gtin": "G1", "product_description": "Kale"})
        assert session.rolled_back is True
        assert len(pc._catalog_store["t1"]) == 1


# ---------------------------------------------------------------------------
# _memory_learn
# ---------------------------------------------------------------------------


class TestMemoryLearn:
    def test_new_tenant_creates_list(self):
        _memory_learn("t1", "G1", "Kale", "Farm A", "2026-01-01")
        assert len(pc._catalog_store["t1"]) == 1

    def test_appends_new_gtin(self):
        _memory_learn("t1", "G1", "Kale", "Farm A", "2026-01-01")
        _memory_learn("t1", "G2", "Spinach", "Farm B", "2026-01-02")
        assert len(pc._catalog_store["t1"]) == 2

    def test_existing_gtin_bumps_count_and_updates(self):
        _memory_learn("t1", "G1", "Kale", "Farm A", "2026-01-01")
        _memory_learn("t1", "G1", "Kale", "Farm B", "2026-01-05")
        prod = pc._catalog_store["t1"][0]
        assert prod.cte_count == 2
        assert prod.last_cte == "2026-01-05"
        assert "Farm A" in prod.facilities
        assert "Farm B" in prod.facilities

    def test_duplicate_facility_not_added(self):
        _memory_learn("t1", "G1", "Kale", "Farm A", "2026-01-01")
        _memory_learn("t1", "G1", "Kale", "Farm A", "2026-01-02")
        prod = pc._catalog_store["t1"][0]
        assert prod.facilities == ["Farm A"]

    def test_empty_facility_not_appended(self):
        _memory_learn("t1", "G1", "Kale", "", "2026-01-01")
        prod = pc._catalog_store["t1"][0]
        assert prod.facilities == []

    def test_fallback_name_when_missing(self):
        _memory_learn("t1", "G123456", "", "", "2026-01-01")
        prod = pc._catalog_store["t1"][0]
        assert prod.name == "Product G123456"
        assert prod.id.endswith("23456")


# ---------------------------------------------------------------------------
# GET /{tenant_id} endpoint
# ---------------------------------------------------------------------------


class TestCatalogGet:
    def test_db_no_category(self, monkeypatch):
        products = [
            Product(id="1", name="Kale", category="Leafy Greens", ftl_covered=True),
            Product(id="2", name="Chicken", category="Poultry", ftl_covered=False),
        ]
        calls = {"n": 0}

        def _fake(tid, cat=None):
            calls["n"] += 1
            return products

        monkeypatch.setattr(pc, "_db_get_catalog", _fake)
        client = TestClient(_build_app())
        resp = client.get("/api/v1/products/t1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["ftl_covered"] == 1
        assert "Leafy Greens" in body["categories"]
        assert "Poultry" in body["categories"]

    def test_db_with_category_filters(self, monkeypatch):
        filtered = [Product(id="1", name="Kale", category="Leafy Greens")]
        full = [
            Product(id="1", name="Kale", category="Leafy Greens"),
            Product(id="2", name="Chicken", category="Poultry", ftl_covered=False),
        ]

        def _fake(tid, cat=None):
            return filtered if cat else full

        monkeypatch.setattr(pc, "_db_get_catalog", _fake)
        client = TestClient(_build_app())
        resp = client.get("/api/v1/products/t1?category=Leafy%20Greens")
        body = resp.json()
        assert body["total"] == 1
        assert body["ftl_covered"] == 1  # from full catalog (Chicken is ftl_covered=False)
        assert "Poultry" in body["categories"]

    def test_pagination_limits_products(self, monkeypatch):
        products = [
            Product(id=str(i), name=f"P{i}", category="Leafy Greens")
            for i in range(10)
        ]
        monkeypatch.setattr(pc, "_db_get_catalog", lambda tid, cat=None: products)
        client = TestClient(_build_app())
        resp = client.get("/api/v1/products/t1?skip=2&limit=3")
        body = resp.json()
        assert body["total"] == 10
        assert len(body["products"]) == 3
        assert body["products"][0]["name"] == "P2"

    def test_memory_fallback_no_category(self, monkeypatch):
        monkeypatch.setattr(pc, "_db_get_catalog", lambda tid, cat=None: None)
        pc._catalog_store["t1"] = [
            Product(id="1", name="Kale", category="Leafy Greens"),
            Product(id="2", name="Chicken", category="Poultry", ftl_covered=False),
        ]
        client = TestClient(_build_app())
        resp = client.get("/api/v1/products/t1")
        body = resp.json()
        assert body["total"] == 2
        assert body["ftl_covered"] == 1
        assert "Leafy Greens" in body["categories"]

    def test_memory_fallback_with_category(self, monkeypatch):
        monkeypatch.setattr(pc, "_db_get_catalog", lambda tid, cat=None: None)
        pc._catalog_store["t1"] = [
            Product(id="1", name="Kale", category="Leafy Greens"),
            Product(id="2", name="Chicken", category="Poultry", ftl_covered=False),
        ]
        client = TestClient(_build_app())
        resp = client.get("/api/v1/products/t1?category=Leafy%20Greens")
        body = resp.json()
        assert body["total"] == 1
        assert body["products"][0]["name"] == "Kale"

    def test_memory_fallback_new_tenant_creates_empty(self, monkeypatch):
        monkeypatch.setattr(pc, "_db_get_catalog", lambda tid, cat=None: None)
        assert "new-tenant" not in pc._catalog_store
        client = TestClient(_build_app())
        resp = client.get("/api/v1/products/new-tenant")
        body = resp.json()
        assert body["total"] == 0
        assert "new-tenant" in pc._catalog_store


# ---------------------------------------------------------------------------
# POST /{tenant_id} endpoint
# ---------------------------------------------------------------------------


class TestAddProductEndpoint:
    def test_db_success(self, monkeypatch):
        monkeypatch.setattr(pc, "_db_add_product", lambda *a, **k: True)
        client = TestClient(_build_app())
        resp = client.post("/api/v1/products/t1", json={
            "name": "Kale", "category": "Leafy Greens",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["created"] is True
        assert body["ftl_covered"] is True

    def test_db_fail_falls_back_to_memory(self, monkeypatch):
        monkeypatch.setattr(pc, "_db_add_product", lambda *a, **k: False)
        client = TestClient(_build_app())
        resp = client.post("/api/v1/products/t1", json={
            "name": "Kale", "category": "Leafy Greens",
        })
        assert resp.status_code == 200
        assert len(pc._catalog_store["t1"]) == 1

    def test_memory_preserves_existing_tenant_list(self, monkeypatch):
        monkeypatch.setattr(pc, "_db_add_product", lambda *a, **k: False)
        pc._catalog_store["t1"] = [Product(id="x", name="existing", category="Herbs")]
        client = TestClient(_build_app())
        resp = client.post("/api/v1/products/t1", json={
            "name": "Kale", "category": "Leafy Greens",
        })
        assert resp.status_code == 200
        assert len(pc._catalog_store["t1"]) == 2

    def test_non_ftl_category_flags_not_covered(self, monkeypatch):
        monkeypatch.setattr(pc, "_db_add_product", lambda *a, **k: True)
        client = TestClient(_build_app())
        resp = client.post("/api/v1/products/t1", json={
            "name": "Widget", "category": "Industrial",
        })
        body = resp.json()
        assert body["ftl_covered"] is False

    def test_full_payload_flows_through(self, monkeypatch):
        monkeypatch.setattr(pc, "_db_add_product", lambda *a, **k: True)
        client = TestClient(_build_app())
        resp = client.post("/api/v1/products/t1", json={
            "name": "Kale",
            "category": "Leafy Greens",
            "sku": "K-1",
            "gtin": "0614141000043",
            "description": "Fresh leafy green",
            "suppliers": ["FarmA"],
            "facilities": ["DC1"],
        })
        body = resp.json()
        assert body["product"]["suppliers"] == ["FarmA"]
        assert body["product"]["facilities"] == ["DC1"]
        assert body["product"]["gtin"] == "0614141000043"


# ---------------------------------------------------------------------------
# GET /{tenant_id}/lookup endpoint
# ---------------------------------------------------------------------------


class TestLookupEndpoint:
    def test_db_hit(self, monkeypatch):
        prod = Product(id="1", name="Kale", category="Leafy Greens", gtin="G")
        monkeypatch.setattr(pc, "_db_lookup_by_gtin", lambda tid, g: prod)
        client = TestClient(_build_app())
        resp = client.get("/api/v1/products/t1/lookup?gtin=G")
        body = resp.json()
        assert body["found"] is True
        assert body["product"]["name"] == "Kale"

    def test_db_miss_memory_hit(self, monkeypatch):
        monkeypatch.setattr(pc, "_db_lookup_by_gtin", lambda tid, g: None)
        pc._catalog_store["t1"] = [
            Product(id="1", name="Kale", category="Leafy Greens", gtin="G"),
        ]
        client = TestClient(_build_app())
        resp = client.get("/api/v1/products/t1/lookup?gtin=G")
        body = resp.json()
        assert body["found"] is True

    def test_db_miss_memory_miss(self, monkeypatch):
        monkeypatch.setattr(pc, "_db_lookup_by_gtin", lambda tid, g: None)
        pc._catalog_store["t1"] = [
            Product(id="1", name="Kale", category="Leafy Greens", gtin="OTHER"),
        ]
        client = TestClient(_build_app())
        resp = client.get("/api/v1/products/t1/lookup?gtin=G")
        body = resp.json()
        assert body["found"] is False
        assert body["product"] is None

    def test_tenant_not_in_memory(self, monkeypatch):
        monkeypatch.setattr(pc, "_db_lookup_by_gtin", lambda tid, g: None)
        client = TestClient(_build_app())
        resp = client.get("/api/v1/products/nobody/lookup?gtin=G")
        body = resp.json()
        assert body["found"] is False


# ---------------------------------------------------------------------------
# GET /categories/ftl endpoint
# ---------------------------------------------------------------------------


class TestFtlCategoriesEndpoint:
    def test_returns_list(self):
        client = TestClient(_build_app())
        resp = client.get("/api/v1/products/categories/ftl")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == len(FTL_CATEGORIES)
        assert "Leafy Greens" in body["categories"]


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_prefix(self):
        assert router.prefix == "/api/v1/products"

    def test_tags(self):
        assert "Product Catalog" in router.tags

    def test_endpoints_registered(self):
        paths = {route.path for route in router.routes}
        assert "/api/v1/products/{tenant_id}" in paths
        assert "/api/v1/products/{tenant_id}/lookup" in paths
        assert "/api/v1/products/categories/ftl" in paths
