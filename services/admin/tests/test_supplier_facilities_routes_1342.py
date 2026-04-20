"""
Regression coverage for ``app/supplier_facilities_routes.py`` — closes the
78% gap left by the existing test suite.

Missing branches targeted (all are defensive/error paths):
* Line 53   — GET /ftl-categories happy path
* Lines 63-97  — list_supplier_facilities full body
* Line 108  — create_supplier_facility: no tenant 400
* Line 146  — set_facility_ftl_categories: no tenant 400
* Lines 150-151 — set_facility_ftl_categories: invalid UUID 400
* Line 165  — set_facility_ftl_categories: unknown FTL category 400
* Line 219  — get_required_ctes: no tenant 400
* Lines 223-224 — get_required_ctes: invalid UUID 400
* Line 237  — get_required_ctes: graph_payload present (neo4j path)
* Line 277  — submit_cte_event: no tenant 400
* Lines 281-282 — submit_cte_event: invalid UUID 400
* Line 343  — create_tlc: no tenant 400
* Lines 347-348 — create_tlc: invalid UUID 400
* Line 365  — create_tlc: duplicate TLC 409
* Line 399  — list_tlcs: no tenant 400
* Lines 409-410 — list_tlcs: invalid facility_id UUID 400
* Line 432  — list_tlcs: empty result short-circuit

Tracks GitHub issue #1342.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.supplier_facilities_routes import router
from app.sqlalchemy_models import (
    SupplierCTEEventModel,
    SupplierFacilityFTLCategoryModel,
    SupplierFacilityModel,
    SupplierTraceabilityLotModel,
    TenantModel,
    UserModel,
)

TEST_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000002")


# ---------------------------------------------------------------------------
# DB fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    tables = [
        TenantModel.__table__,
        UserModel.__table__,
        SupplierFacilityModel.__table__,
        SupplierFacilityFTLCategoryModel.__table__,
        SupplierTraceabilityLotModel.__table__,
        SupplierCTEEventModel.__table__,
    ]
    for t in tables:
        t.create(bind=engine)

    SM = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                      expire_on_commit=False, future=True)
    session = SM()
    session.add(TenantModel(id=TEST_TENANT_ID, name="T", slug="t", status="active", settings={}))
    session.add(UserModel(id=TEST_USER_ID, email="u@example.com",
                          password_hash="x", status="active", is_sysadmin=False))
    session.commit()

    try:
        yield session
    finally:
        session.close()
        for t in reversed(tables):
            t.drop(bind=engine)
        engine.dispose()


# ---------------------------------------------------------------------------
# Client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def client(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import app.supplier_facilities_routes as fac_routes

    app = FastAPI()
    app.include_router(router, prefix="/v1")

    current_user = db_session.get(UserModel, TEST_USER_ID)

    def _get_session():
        yield db_session

    def _get_user():
        return current_user

    app.dependency_overrides[fac_routes.get_session] = _get_session
    app.dependency_overrides[fac_routes.get_current_user] = _get_user

    monkeypatch.setattr(fac_routes.TenantContext, "get_tenant_context",
                        lambda _db: TEST_TENANT_ID)
    monkeypatch.setattr(fac_routes.supplier_graph_sync, "record_facility_ftl_scoping",
                        lambda **_kw: None)
    monkeypatch.setattr(fac_routes.supplier_graph_sync, "record_cte_event",
                        lambda **_kw: None)
    monkeypatch.setattr(fac_routes.supplier_graph_sync, "get_required_ctes_for_facility",
                        lambda *_a, **_kw: None)

    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_no_tenant(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Client where TenantContext.get_tenant_context returns None."""
    import app.supplier_facilities_routes as fac_routes

    app = FastAPI()
    app.include_router(router, prefix="/v1")

    current_user = db_session.get(UserModel, TEST_USER_ID)

    def _get_session():
        yield db_session

    def _get_user():
        return current_user

    app.dependency_overrides[fac_routes.get_session] = _get_session
    app.dependency_overrides[fac_routes.get_current_user] = _get_user

    monkeypatch.setattr(fac_routes.TenantContext, "get_tenant_context",
                        lambda _db: None)

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_facility(db: Session, name: str = "Warehouse A") -> SupplierFacilityModel:
    f = SupplierFacilityModel(
        tenant_id=TEST_TENANT_ID,
        supplier_user_id=TEST_USER_ID,
        name=name,
        street="1 Main St",
        city="Salinas",
        state="CA",
        postal_code="93901",
        roles=["Grower"],
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


# ---------------------------------------------------------------------------
# GET /ftl-categories — line 53
# ---------------------------------------------------------------------------


class TestGetFtlCategories:
    def test_returns_categories_list(self, client: TestClient):
        """Line 53: endpoint is authenticated and returns the catalog."""
        resp = client.get("/v1/supplier/ftl-categories")
        assert resp.status_code == 200
        body = resp.json()
        assert "categories" in body
        assert isinstance(body["categories"], list)
        assert len(body["categories"]) > 0


# ---------------------------------------------------------------------------
# GET /facilities — lines 63-97
# ---------------------------------------------------------------------------


class TestListSupplierFacilities:
    def test_empty_list(self, client: TestClient):
        """Lines 63-97: no facilities → items=[], total=0."""
        resp = client.get("/v1/supplier/facilities")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_returns_facility(self, client: TestClient, db_session: Session):
        """Lines 63-97: one facility → items has one element."""
        _make_facility(db_session)
        resp = client.get("/v1/supplier/facilities")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["name"] == "Warehouse A"

    def test_pagination_params_forwarded(self, client: TestClient, db_session: Session):
        """Lines 63-97: pagination skip/limit reflected in response."""
        for i in range(3):
            _make_facility(db_session, name=f"Facility {i}")
        resp = client.get("/v1/supplier/facilities?skip=1&limit=1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["skip"] == 1
        assert body["limit"] == 1
        assert len(body["items"]) == 1

    def test_no_tenant_returns_400(self, client_no_tenant: TestClient):
        """Line 65: missing tenant → 400."""
        resp = client_no_tenant.get("/v1/supplier/facilities")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /facilities — line 108
# ---------------------------------------------------------------------------


class TestCreateSupplierFacility:
    def test_no_tenant_returns_400(self, client_no_tenant: TestClient):
        """Line 108: missing tenant → 400."""
        resp = client_no_tenant.post("/v1/supplier/facilities", json={
            "name": "Warehouse X", "street": "1 Main St", "city": "Salinas",
            "state": "CA", "postal_code": "93901", "roles": []
        })
        assert resp.status_code == 400

    def test_create_facility_happy_path(self, client: TestClient):
        """Lines 110-125: valid request creates facility and returns response."""
        resp = client.post("/v1/supplier/facilities", json={
            "name": "New Packhouse", "street": "100 Depot Rd", "city": "Salinas",
            "state": "CA", "postal_code": "93901", "roles": ["Packer"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "New Packhouse"
        assert body["state"] == "CA"
        assert "id" in body


# ---------------------------------------------------------------------------
# PUT /facilities/{id}/ftl-categories — lines 146, 150-151, 165
# ---------------------------------------------------------------------------


class TestSetFtlCategories:
    def test_no_tenant_returns_400(self, client_no_tenant: TestClient):
        """Line 146: missing tenant → 400."""
        import uuid
        fid = str(uuid.uuid4())
        resp = client_no_tenant.put(
            f"/v1/supplier/facilities/{fid}/ftl-categories",
            json={"category_ids": ["1"]},
        )
        assert resp.status_code == 400

    def test_invalid_uuid_returns_400(self, client: TestClient):
        """Lines 150-151: non-UUID facility_id → 400."""
        resp = client.put(
            "/v1/supplier/facilities/not-a-uuid/ftl-categories",
            json={"category_ids": ["1"]},
        )
        assert resp.status_code == 400
        assert "Invalid facility id" in resp.json()["detail"]

    def test_unknown_category_returns_400(self, client: TestClient, db_session: Session):
        """Line 165: unknown FTL category id → 400."""
        f = _make_facility(db_session)
        resp = client.put(
            f"/v1/supplier/facilities/{f.id}/ftl-categories",
            json={"category_ids": ["9999"]},
        )
        assert resp.status_code == 400
        assert "Unknown FTL category" in resp.json()["detail"]

    def test_valid_category_succeeds(self, client: TestClient, db_session: Session):
        """Happy path: valid category → 200."""
        f = _make_facility(db_session)
        resp = client.put(
            f"/v1/supplier/facilities/{f.id}/ftl-categories",
            json={"category_ids": ["1"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["facility_id"] == str(f.id)
        assert len(body["categories"]) == 1


# ---------------------------------------------------------------------------
# GET /facilities/{id}/required-ctes — lines 219, 223-224, 237
# ---------------------------------------------------------------------------


class TestGetRequiredCtes:
    def test_no_tenant_returns_400(self, client_no_tenant: TestClient):
        """Line 219: missing tenant → 400."""
        import uuid
        resp = client_no_tenant.get(f"/v1/supplier/facilities/{uuid.uuid4()}/required-ctes")
        assert resp.status_code == 400

    def test_invalid_uuid_returns_400(self, client: TestClient):
        """Lines 223-224: bad UUID → 400."""
        resp = client.get("/v1/supplier/facilities/bad-uuid/required-ctes")
        assert resp.status_code == 400
        assert "Invalid facility id" in resp.json()["detail"]

    def test_graph_payload_returned_when_present(
        self, client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ):
        """Line 237: when graph_sync returns a payload, use it (neo4j path)."""
        import app.supplier_facilities_routes as fac_routes

        f = _make_facility(db_session)
        graph_response = {
            "categories": [{"id": "1", "name": "Leafy Greens", "ctes": ["harvesting"]}],
            "required_ctes": ["harvesting"],
            "source": "neo4j",
        }
        monkeypatch.setattr(
            fac_routes.supplier_graph_sync,
            "get_required_ctes_for_facility",
            lambda *_a, **_kw: graph_response,
        )

        resp = client.get(f"/v1/supplier/facilities/{f.id}/required-ctes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["source"] == "neo4j"
        assert body["required_ctes"] == ["harvesting"]

    def test_falls_back_to_postgres_when_graph_returns_none(
        self, client: TestClient, db_session: Session
    ):
        """Lines 244-264: graph returns None → read from postgres."""
        f = _make_facility(db_session)
        # No FTL categories, so postgres returns empty
        resp = client.get(f"/v1/supplier/facilities/{f.id}/required-ctes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["source"] == "postgres"
        assert body["categories"] == []


# ---------------------------------------------------------------------------
# POST /facilities/{id}/cte-events — lines 277, 281-282
# ---------------------------------------------------------------------------


class TestSubmitCteEvent:
    def test_no_tenant_returns_400(self, client_no_tenant: TestClient):
        """Line 277: missing tenant → 400."""
        import uuid
        resp = client_no_tenant.post(
            f"/v1/supplier/facilities/{uuid.uuid4()}/cte-events",
            json={"cte_type": "harvesting", "tlc_code": "TLC-001",
                  "event_time": "2026-03-01T00:00:00Z", "kde_data": {}},
        )
        assert resp.status_code == 400

    def test_invalid_uuid_returns_400(self, client: TestClient):
        """Lines 281-282: bad UUID → 400."""
        resp = client.post(
            "/v1/supplier/facilities/not-a-uuid/cte-events",
            json={"cte_type": "harvesting", "tlc_code": "TLC-001",
                  "event_time": "2026-03-01T00:00:00Z", "kde_data": {}},
        )
        assert resp.status_code == 400
        assert "Invalid facility id" in resp.json()["detail"]

    def test_submit_cte_event_happy_path(self, client: TestClient, db_session: Session):
        """Lines 284-323: valid facility + existing TLC → 200 with merkle fields."""
        f = _make_facility(db_session)
        lot = SupplierTraceabilityLotModel(
            tenant_id=TEST_TENANT_ID,
            supplier_user_id=TEST_USER_ID,
            facility_id=f.id,
            tlc_code="TLC-EVENT-001",
            product_description="Baby Spinach",
            status="active",
        )
        db_session.add(lot)
        db_session.commit()

        resp = client.post(
            f"/v1/supplier/facilities/{f.id}/cte-events",
            json={
                "cte_type": "harvesting",
                "tlc_code": "TLC-EVENT-001",
                "event_time": "2026-03-01T12:00:00Z",
                "kde_data": {"quantity": 50, "unit_of_measure": "cases"},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tlc_code"] == "TLC-EVENT-001"
        assert body["cte_type"] == "harvesting"
        assert body["merkle_hash"] is not None


# ---------------------------------------------------------------------------
# POST /tlcs — lines 343, 347-348, 365
# ---------------------------------------------------------------------------


class TestCreateTlc:
    def test_no_tenant_returns_400(self, client_no_tenant: TestClient):
        """Line 343: missing tenant → 400."""
        import uuid
        resp = client_no_tenant.post("/v1/supplier/tlcs", json={
            "facility_id": str(uuid.uuid4()),
            "tlc_code": "TLC-X",
            "product_description": "Spinach",
        })
        assert resp.status_code == 400

    def test_invalid_facility_uuid_returns_400(self, client: TestClient):
        """Lines 347-348: bad facility UUID → 400."""
        resp = client.post("/v1/supplier/tlcs", json={
            "facility_id": "not-a-uuid",
            "tlc_code": "TLC-X",
            "product_description": "Spinach",
        })
        assert resp.status_code == 400
        assert "Invalid facility id" in resp.json()["detail"]

    def test_duplicate_tlc_returns_409(self, client: TestClient, db_session: Session):
        """Line 365: creating same TLC code twice → 409."""
        f = _make_facility(db_session)
        payload = {
            "facility_id": str(f.id),
            "tlc_code": "TLC-DUP-001",
            "product_description": "Baby Spinach",
        }
        r1 = client.post("/v1/supplier/tlcs", json=payload)
        assert r1.status_code == 200
        r2 = client.post("/v1/supplier/tlcs", json=payload)
        assert r2.status_code == 409
        assert "already exists" in r2.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /tlcs — lines 399, 409-410, 432
# ---------------------------------------------------------------------------


class TestListTlcs:
    def test_no_tenant_returns_400(self, client_no_tenant: TestClient):
        """Line 399: missing tenant → 400."""
        resp = client_no_tenant.get("/v1/supplier/tlcs")
        assert resp.status_code == 400

    def test_invalid_facility_uuid_returns_400(self, client: TestClient):
        """Lines 409-410: bad facility_id query param → 400."""
        resp = client.get("/v1/supplier/tlcs?facility_id=not-a-uuid")
        assert resp.status_code == 400
        assert "Invalid facility id" in resp.json()["detail"]

    def test_empty_lots_returns_early(self, client: TestClient):
        """Line 432: no TLCs → items=[], returned before count-map query."""
        resp = client.get("/v1/supplier/tlcs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_lots_with_facility_filter(self, client: TestClient, db_session: Session):
        """Lines 406-417: facility_id filter applied; also exercises count-map path."""
        f = _make_facility(db_session)
        lot = SupplierTraceabilityLotModel(
            tenant_id=TEST_TENANT_ID,
            supplier_user_id=TEST_USER_ID,
            facility_id=f.id,
            tlc_code="TLC-FILTER-001",
            product_description="Spinach",
            status="active",
        )
        db_session.add(lot)
        db_session.commit()

        resp = client.get(f"/v1/supplier/tlcs?facility_id={f.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["tlc_code"] == "TLC-FILTER-001"
        assert body["items"][0]["event_count"] == 0
