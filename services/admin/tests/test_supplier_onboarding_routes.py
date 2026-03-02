from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.sqlalchemy_models import (
    SupplierFacilityFTLCategoryModel,
    SupplierFacilityModel,
    TenantModel,
    UserModel,
)
from app.supplier_onboarding_routes import router


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
    table_bindings = [
        TenantModel.__table__,
        UserModel.__table__,
        SupplierFacilityModel.__table__,
        SupplierFacilityFTLCategoryModel.__table__,
    ]
    for table in table_bindings:
        table.create(bind=engine)

    session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )
    session = session_local()

    session.add(
        TenantModel(
            id=TEST_TENANT_ID,
            name="Test Tenant",
            slug="test-tenant",
            status="active",
            settings={},
        )
    )
    session.add(
        UserModel(
            id=TEST_USER_ID,
            email="supplier@example.com",
            password_hash="hashed-password",
            status="active",
            is_sysadmin=False,
        )
    )
    session.commit()

    try:
        yield session
    finally:
        session.close()
        for table in reversed(table_bindings):
            table.drop(bind=engine)
        engine.dispose()


@pytest.fixture
def client(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import app.supplier_onboarding_routes as supplier_routes

    test_app = FastAPI()
    test_app.include_router(router, prefix="/v1")

    current_user = db_session.get(UserModel, TEST_USER_ID)

    def override_get_session():
        yield db_session

    def override_get_current_user() -> UserModel:
        assert current_user is not None
        return current_user

    test_app.dependency_overrides[supplier_routes.get_session] = override_get_session
    test_app.dependency_overrides[supplier_routes.get_current_user] = override_get_current_user

    monkeypatch.setattr(supplier_routes.TenantContext, "get_tenant_context", lambda _db: TEST_TENANT_ID)
    monkeypatch.setattr(supplier_routes.supplier_graph_sync, "record_facility_ftl_scoping", lambda **_kwargs: None)
    monkeypatch.setattr(supplier_routes.supplier_graph_sync, "get_required_ctes_for_facility", lambda _facility_id: None)

    with TestClient(test_app) as test_client:
        yield test_client


def _create_facility(client: TestClient) -> str:
    response = client.post(
        "/v1/supplier/facilities",
        json={
            "name": "Salinas Packhouse",
            "street": "1200 Abbott St",
            "city": "Salinas",
            "state": "CA",
            "postal_code": "93901",
            "fda_registration_number": "12345678901",
            "roles": ["Grower", "Packer"],
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_required_ctes_happy_path_two_categories(client: TestClient):
    facility_id = _create_facility(client)

    scope_response = client.put(
        f"/v1/supplier/facilities/{facility_id}/ftl-categories",
        json={"category_ids": ["1", "5"]},
    )
    assert scope_response.status_code == 200

    response = client.get(f"/v1/supplier/facilities/{facility_id}/required-ctes")

    assert response.status_code == 200
    payload = response.json()
    assert payload["facility_id"] == facility_id
    assert payload["source"] == "postgres"
    assert {category["id"] for category in payload["categories"]} == {"1", "5"}
    assert payload["required_ctes"] == [
        "receiving",
        "transforming",
        "shipping",
        "harvesting",
        "cooling",
        "initial_packing",
    ]


def test_required_ctes_empty_when_no_categories_set(client: TestClient):
    facility_id = _create_facility(client)

    response = client.get(f"/v1/supplier/facilities/{facility_id}/required-ctes")

    assert response.status_code == 200
    payload = response.json()
    assert payload["facility_id"] == facility_id
    assert payload["source"] == "postgres"
    assert payload["categories"] == []
    assert payload["required_ctes"] == []


def test_required_ctes_returns_404_for_unknown_facility(client: TestClient):
    unknown_facility_id = str(uuid4())

    response = client.get(f"/v1/supplier/facilities/{unknown_facility_id}/required-ctes")

    assert response.status_code == 404
    assert response.json()["detail"] == "Facility not found"
