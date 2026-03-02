from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.sqlalchemy_models import (
    SupplierCTEEventModel,
    SupplierFacilityFTLCategoryModel,
    SupplierFacilityModel,
    SupplierTraceabilityLotModel,
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
        SupplierTraceabilityLotModel.__table__,
        SupplierCTEEventModel.__table__,
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
    monkeypatch.setattr(supplier_routes.supplier_graph_sync, "record_cte_event", lambda **_kwargs: None)

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


def test_submit_cte_event_creates_hash_and_merkle_chain(client: TestClient):
    facility_id = _create_facility(client)

    first_response = client.post(
        f"/v1/supplier/facilities/{facility_id}/cte-events",
        json={
            "cte_type": "shipping",
            "tlc_code": "TLC-2026-SAL-0001",
            "kde_data": {"quantity": 100, "unit_of_measure": "cases", "product_description": "Baby Spinach"},
            "obligation_ids": ["21cfr_subpart_s_123"],
        },
    )
    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert first_payload["cte_type"] == "shipping"
    assert first_payload["merkle_sequence"] == 1
    assert first_payload["merkle_prev_hash"] is None
    assert len(first_payload["payload_sha256"]) == 64
    assert len(first_payload["merkle_hash"]) == 64

    second_response = client.post(
        f"/v1/supplier/facilities/{facility_id}/cte-events",
        json={
            "cte_type": "receiving",
            "tlc_code": "TLC-2026-SAL-0001",
            "kde_data": {"quantity": 80, "unit_of_measure": "cases", "product_description": "Baby Spinach"},
            "obligation_ids": [],
        },
    )
    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["merkle_sequence"] == 2
    assert second_payload["merkle_prev_hash"] == first_payload["merkle_hash"]


def test_submit_cte_event_rejects_bad_cte_type(client: TestClient):
    facility_id = _create_facility(client)

    response = client.post(
        f"/v1/supplier/facilities/{facility_id}/cte-events",
        json={
            "cte_type": "invalid_cte",
            "tlc_code": "TLC-2026-SAL-0001",
            "kde_data": {"quantity": 100},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported cte_type: invalid_cte"


def test_create_and_list_tlcs_with_event_counts(client: TestClient):
    facility_id = _create_facility(client)

    create_response = client.post(
        "/v1/supplier/tlcs",
        json={
            "facility_id": facility_id,
            "tlc_code": "TLC-2026-SAL-1234",
            "product_description": "Romaine Hearts",
            "status": "active",
        },
    )
    assert create_response.status_code == 200

    list_response_before = client.get(f"/v1/supplier/tlcs?facility_id={facility_id}")
    assert list_response_before.status_code == 200
    list_payload_before = list_response_before.json()
    assert len(list_payload_before) == 1
    assert list_payload_before[0]["event_count"] == 0

    submit_response = client.post(
        f"/v1/supplier/facilities/{facility_id}/cte-events",
        json={
            "cte_type": "shipping",
            "tlc_code": "TLC-2026-SAL-1234",
            "kde_data": {"quantity": 40, "unit_of_measure": "cases", "product_description": "Romaine Hearts"},
        },
    )
    assert submit_response.status_code == 200

    list_response_after = client.get(f"/v1/supplier/tlcs?facility_id={facility_id}")
    assert list_response_after.status_code == 200
    list_payload_after = list_response_after.json()
    assert len(list_payload_after) == 1
    assert list_payload_after[0]["tlc_code"] == "TLC-2026-SAL-1234"
    assert list_payload_after[0]["event_count"] == 1


def test_compliance_score_increases_after_missing_required_cte_submission(client: TestClient):
    facility_id = _create_facility(client)

    scope_response = client.put(
        f"/v1/supplier/facilities/{facility_id}/ftl-categories",
        json={"category_ids": ["1"]},
    )
    assert scope_response.status_code == 200

    receiving_response = client.post(
        f"/v1/supplier/facilities/{facility_id}/cte-events",
        json={
            "cte_type": "receiving",
            "tlc_code": "TLC-2026-SAL-9910",
            "kde_data": {"quantity": 15, "unit_of_measure": "cases", "product_description": "Spinach"},
        },
    )
    assert receiving_response.status_code == 200

    shipping_response = client.post(
        f"/v1/supplier/facilities/{facility_id}/cte-events",
        json={
            "cte_type": "shipping",
            "tlc_code": "TLC-2026-SAL-9910",
            "kde_data": {"quantity": 15, "unit_of_measure": "cases", "product_description": "Spinach"},
        },
    )
    assert shipping_response.status_code == 200

    score_before = client.get(f"/v1/supplier/compliance-score?facility_id={facility_id}")
    assert score_before.status_code == 200
    payload_before = score_before.json()
    assert payload_before["required_ctes"] == 3
    assert payload_before["covered_ctes"] == 2
    assert payload_before["missing_ctes"] == 1

    gaps_before = client.get(f"/v1/supplier/gaps?facility_id={facility_id}")
    assert gaps_before.status_code == 200
    gaps_payload_before = gaps_before.json()
    assert gaps_payload_before["high"] >= 1
    assert any(gap["cte_type"] == "transforming" and gap["reason"] == "required_cte_missing" for gap in gaps_payload_before["gaps"])

    transforming_response = client.post(
        f"/v1/supplier/facilities/{facility_id}/cte-events",
        json={
            "cte_type": "transforming",
            "tlc_code": "TLC-2026-SAL-9910",
            "kde_data": {
                "input_tlc": "TLC-2026-SAL-9910",
                "output_tlc": "TLC-2026-SAL-9911",
                "product_description": "Spinach Mix",
            },
        },
    )
    assert transforming_response.status_code == 200

    score_after = client.get(f"/v1/supplier/compliance-score?facility_id={facility_id}")
    assert score_after.status_code == 200
    payload_after = score_after.json()
    assert payload_after["required_ctes"] == 3
    assert payload_after["covered_ctes"] == 3
    assert payload_after["missing_ctes"] == 0
    assert payload_after["score"] > payload_before["score"]

    gaps_after = client.get(f"/v1/supplier/gaps?facility_id={facility_id}")
    assert gaps_after.status_code == 200
    gaps_payload_after = gaps_after.json()
    assert all(gap["reason"] != "required_cte_missing" for gap in gaps_payload_after["gaps"])


def test_compliance_score_flags_unscoped_facility(client: TestClient):
    facility_id = _create_facility(client)

    score_response = client.get(f"/v1/supplier/compliance-score?facility_id={facility_id}")
    assert score_response.status_code == 200
    score_payload = score_response.json()
    assert score_payload["score"] == 0
    assert score_payload["required_ctes"] == 0

    gaps_response = client.get(f"/v1/supplier/gaps?facility_id={facility_id}")
    assert gaps_response.status_code == 200
    gaps_payload = gaps_response.json()
    assert gaps_payload["total"] == 1
    assert gaps_payload["high"] == 1
    assert gaps_payload["gaps"][0]["reason"] == "ftl_not_scoped"
