"""
Regression coverage for ``app/supplier_compliance_routes.py`` — closes the 86% gap.

All 12 missing lines are no-tenant 400 guards and invalid-UUID 400 guards
across the four compliance endpoints. Same pattern for each.

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

from app.supplier_compliance_routes import router
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


def _build_client(db_session, monkeypatch, *, tenant=TEST_TENANT_ID):
    import app.supplier_compliance_routes as comp_routes

    app = FastAPI()
    app.include_router(router, prefix="/v1")

    current_user = db_session.get(UserModel, TEST_USER_ID)

    app.dependency_overrides[comp_routes.get_session] = lambda: (yield db_session)
    app.dependency_overrides[comp_routes.get_current_user] = lambda: current_user
    monkeypatch.setattr(comp_routes.TenantContext, "get_tenant_context",
                        lambda _db: tenant)
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
# GET /compliance-score — lines 46, 52-53
# ---------------------------------------------------------------------------

class TestComplianceScore:

    def test_no_tenant_returns_400(self, client_no_tenant):
        """Line 46: no tenant → 400."""
        resp = client_no_tenant.get("/v1/supplier/compliance-score")
        assert resp.status_code == 400

    def test_invalid_facility_uuid_returns_400(self, client):
        """Lines 52-53: bad UUID → 400."""
        resp = client.get("/v1/supplier/compliance-score?facility_id=not-a-uuid")
        assert resp.status_code == 400
        assert "Invalid facility id" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /gaps — lines 80, 86-87
# ---------------------------------------------------------------------------

class TestComplianceGaps:

    def test_no_tenant_returns_400(self, client_no_tenant):
        """Line 80: no tenant → 400."""
        resp = client_no_tenant.get("/v1/supplier/gaps")
        assert resp.status_code == 400

    def test_invalid_facility_uuid_returns_400(self, client):
        """Lines 86-87: bad UUID → 400."""
        resp = client.get("/v1/supplier/gaps?facility_id=not-a-uuid")
        assert resp.status_code == 400
        assert "Invalid facility id" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /export/fda-records/preview — lines 130, 136-137
# ---------------------------------------------------------------------------

class TestFDAExportPreview:

    def test_no_tenant_returns_400(self, client_no_tenant):
        """Line 130: no tenant → 400."""
        resp = client_no_tenant.get("/v1/supplier/export/fda-records/preview")
        assert resp.status_code == 400

    def test_invalid_facility_uuid_returns_400(self, client):
        """Lines 136-137: bad UUID → 400."""
        resp = client.get("/v1/supplier/export/fda-records/preview?facility_id=not-a-uuid")
        assert resp.status_code == 400
        assert "Invalid facility id" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /export/fda-records — lines 171, 177-178
# ---------------------------------------------------------------------------

class TestFDAExportCSV:

    def test_no_tenant_returns_400(self, client_no_tenant):
        """Line 171: no tenant → 400."""
        resp = client_no_tenant.get("/v1/supplier/export/fda-records")
        assert resp.status_code == 400

    def test_invalid_facility_uuid_returns_400(self, client):
        """Lines 177-178: bad UUID → 400."""
        resp = client.get("/v1/supplier/export/fda-records?facility_id=not-a-uuid")
        assert resp.status_code == 400
        assert "Invalid facility id" in resp.json()["detail"]
