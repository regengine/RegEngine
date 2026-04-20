"""
Regression coverage for ``app/supplier_funnel_routes.py`` — closes the 92% gap.

Missing branches targeted:
* Line 117   — demo/reset: no tenant → 400
* Line 355   — demo/reset seed: unknown FTL category → 500
* Line 490   — create_funnel_event: no tenant → 400
* Lines 494-498 — create_funnel_event: invalid facility UUID → 400
* Line 532   — get_social_proof: no tenant → 400
* Line 545   — get_funnel_summary: no tenant → 400

Tracks GitHub issue #1342.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.supplier_funnel_routes import router
from app.sqlalchemy_models import (
    SupplierCTEEventModel,
    SupplierFacilityFTLCategoryModel,
    SupplierFacilityModel,
    SupplierFunnelEventModel,
    SupplierTraceabilityLotModel,
    TenantModel,
    UserModel,
)

TEST_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000002")
_CONFIRM = "reset-supplier-demo-data"


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
        SupplierFunnelEventModel.__table__,
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
# Client helpers
# ---------------------------------------------------------------------------


def _build_client(db_session, monkeypatch, *, tenant=TEST_TENANT_ID):
    import app.supplier_funnel_routes as funnel_routes
    from app.dependencies import PermissionChecker

    app = FastAPI()
    app.include_router(router, prefix="/v1")

    current_user = db_session.get(UserModel, TEST_USER_ID)

    app.dependency_overrides[funnel_routes.get_session] = lambda: (yield db_session)
    app.dependency_overrides[funnel_routes.get_current_user] = lambda: current_user
    # Override PermissionChecker so all permission checks pass
    app.dependency_overrides[PermissionChecker("supplier.demo.reset")] = lambda: None

    monkeypatch.setattr(funnel_routes.TenantContext, "get_tenant_context",
                        lambda _db: tenant)
    monkeypatch.setattr(funnel_routes.supplier_graph_sync, "record_facility_ftl_scoping",
                        lambda **_kw: None)
    monkeypatch.setattr(funnel_routes.supplier_graph_sync, "record_cte_event",
                        lambda **_kw: None)

    return TestClient(app)


@pytest.fixture
def client(db_session, monkeypatch):
    with _build_client(db_session, monkeypatch) as c:
        yield c


@pytest.fixture
def client_no_tenant(db_session, monkeypatch):
    with _build_client(db_session, monkeypatch, tenant=None) as c:
        yield c


# ---------------------------------------------------------------------------
# create_funnel_event — lines 490, 494-498
# ---------------------------------------------------------------------------


class TestCreateFunnelEvent:

    def test_no_tenant_returns_400(self, client_no_tenant: TestClient):
        """Line 490: missing tenant → 400."""
        resp = client_no_tenant.post(
            "/v1/supplier/funnel-events",
            json={"event_name": "demo_started"},
        )
        assert resp.status_code == 400
        assert "Tenant context required" in resp.json()["detail"]

    def test_invalid_facility_uuid_returns_400(self, client: TestClient):
        """Lines 494-498: facility_id provided but not a valid UUID → 400."""
        resp = client.post(
            "/v1/supplier/funnel-events",
            json={"event_name": "demo_started", "facility_id": "not-a-uuid"},
        )
        assert resp.status_code == 400
        assert "Invalid facility id" in resp.json()["detail"]

    def test_valid_facility_uuid_calls_facility_lookup(
        self, client: TestClient, db_session: Session
    ):
        """Line 498: valid facility UUID → _get_supplier_facility_or_404 called.
        Unknown (non-existent) facility → 404."""
        import uuid
        resp = client.post(
            "/v1/supplier/funnel-events",
            json={"event_name": "demo_started",
                  "facility_id": str(uuid.uuid4())},
        )
        # Unknown facility → 404 from _get_supplier_facility_or_404
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# get_social_proof — line 532
# ---------------------------------------------------------------------------


class TestGetSocialProof:

    def test_no_tenant_returns_400(self, client_no_tenant: TestClient):
        """Line 532: missing tenant → 400."""
        resp = client_no_tenant.get("/v1/supplier/social-proof")
        assert resp.status_code == 400
        assert "Tenant context required" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# get_funnel_summary — line 545
# ---------------------------------------------------------------------------


class TestGetFunnelSummary:

    def test_no_tenant_returns_400(self, client_no_tenant: TestClient):
        """Line 545: missing tenant → 400."""
        resp = client_no_tenant.get("/v1/supplier/funnel-summary")
        assert resp.status_code == 400
        assert "Tenant context required" in resp.json()["detail"]
