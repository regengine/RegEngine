from __future__ import annotations

import csv
import io
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
    SupplierFunnelEventModel,
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
        SupplierFunnelEventModel.__table__,
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


def _create_sample_supplier_event(client: TestClient, facility_id: str, tlc_code: str = "TLC-2026-SAL-7777") -> None:
    scope_response = client.put(
        f"/v1/supplier/facilities/{facility_id}/ftl-categories",
        json={"category_ids": ["1"]},
    )
    assert scope_response.status_code == 200

    event_response = client.post(
        f"/v1/supplier/facilities/{facility_id}/cte-events",
        json={
            "cte_type": "shipping",
            "tlc_code": tlc_code,
            "kde_data": {
                "quantity": 480,
                "unit_of_measure": "cases",
                "reference_document": "BOL-9921",
                "product_description": "Baby Spinach",
            },
        },
    )
    assert event_response.status_code == 200


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


def test_fda_export_preview_returns_live_rows(client: TestClient):
    facility_id = _create_facility(client)
    _create_sample_supplier_event(client, facility_id, tlc_code="TLC-2026-SAL-8800")

    response = client.get(f"/v1/supplier/export/fda-records/preview?facility_id={facility_id}&limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] >= 1
    row = payload["rows"][0]
    assert row["tlc_code"] == "TLC-2026-SAL-8800"
    assert row["reference_document"] == "BOL-9921"
    assert len(row["payload_sha256"]) == 64


def test_fda_export_csv_contains_sha256_column(client: TestClient):
    facility_id = _create_facility(client)
    _create_sample_supplier_event(client, facility_id, tlc_code="TLC-2026-SAL-8801")

    response = client.get(f"/v1/supplier/export/fda-records?format=csv&facility_id={facility_id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert ".csv" in response.headers["content-disposition"]

    csv_text = response.content.decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == 1
    assert rows[0]["Traceability Lot Code"] == "TLC-2026-SAL-8801"
    assert rows[0]["Reference Document"] == "BOL-9921"
    assert len(rows[0]["SHA-256"]) == 64


def test_fda_export_xlsx_returns_spreadsheet_payload(client: TestClient):
    facility_id = _create_facility(client)
    _create_sample_supplier_event(client, facility_id, tlc_code="TLC-2026-SAL-8802")

    response = client.get(f"/v1/supplier/export/fda-records?format=xlsx&facility_id={facility_id}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert ".xlsx" in response.headers["content-disposition"]
    assert response.headers["x-fda-record-count"] == "1"
    assert response.content[:2] == b"PK"


def test_demo_reset_seeds_chain_and_focus_gap(client: TestClient):
    response = client.post("/v1/supplier/demo/reset")

    assert response.status_code == 200
    payload = response.json()
    assert payload["seeded_facilities"] == 4
    assert payload["seeded_tlcs"] >= 3
    assert len(payload["seeded_tlc_codes"]) == payload["seeded_tlcs"]
    assert payload["seeded_events"] >= 10
    assert "shipping" in payload["seeded_cte_types"]
    assert "transforming" in payload["seeded_cte_types"]
    assert payload["dashboard_score"] < 100
    assert payload["open_gap_count"] >= 1
    assert payload["focus_facility_name"] == "Salinas Packhouse"
    assert payload["focus_gap_cte"] == "transforming"
    assert payload["focus_gap_reason"] == "required_cte_missing"
    assert "Missing required transforming event" in payload["focus_gap_issue"]
    assert "transforming" in payload["focus_required_ctes"]

    focus_facility_id = payload["focus_facility_id"]

    score_response = client.get(f"/v1/supplier/compliance-score?facility_id={focus_facility_id}")
    assert score_response.status_code == 200
    score_payload = score_response.json()
    assert score_payload["score"] == payload["dashboard_score"]

    gaps_response = client.get(f"/v1/supplier/gaps?facility_id={focus_facility_id}")
    assert gaps_response.status_code == 200
    gaps_payload = gaps_response.json()
    assert any(gap["reason"] == "required_cte_missing" for gap in gaps_payload["gaps"])
    assert any(gap["cte_type"] == "transforming" for gap in gaps_payload["gaps"])


def test_funnel_events_and_social_proof_counts(client: TestClient):
    initial_response = client.get("/v1/supplier/social-proof")
    assert initial_response.status_code == 200
    initial_payload = initial_response.json()

    event_response = client.post(
        "/v1/supplier/funnel-events",
        json={
            "event_name": "fda_export_downloaded",
            "step": "fda_export",
            "status": "success",
            "metadata": {"format": "csv"},
        },
    )
    assert event_response.status_code == 200
    event_payload = event_response.json()
    assert event_payload["event_name"] == "fda_export_downloaded"

    social_proof_response = client.get("/v1/supplier/social-proof")
    assert social_proof_response.status_code == 200
    social_proof_payload = social_proof_response.json()
    assert social_proof_payload["fda_exports_generated"] == initial_payload["fda_exports_generated"] + 1


def test_funnel_summary_aggregates_views_and_completions(client: TestClient):
    events = [
        {"event_name": "step_viewed", "step": "facility_setup", "status": "viewed"},
        {"event_name": "step_viewed", "step": "facility_setup", "status": "viewed"},
        {"event_name": "step_completed", "step": "facility_setup", "status": "success"},
        {"event_name": "step_viewed", "step": "ftl_scoping", "status": "viewed"},
        {"event_name": "step_completed", "step": "ftl_scoping", "status": "success"},
        {"event_name": "step_completed", "step": "ftl_scoping", "status": "success"},
        {"event_name": "demo_reset_completed", "step": "overview", "status": "success"},
        {"event_name": "fda_export_downloaded", "step": "fda_export", "status": "success"},
    ]
    for payload in events:
        response = client.post("/v1/supplier/funnel-events", json=payload)
        assert response.status_code == 200

    summary_response = client.get("/v1/supplier/funnel-summary")
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()

    assert summary_payload["total_step_views"] == 3
    assert summary_payload["total_step_completions"] == 3
    assert summary_payload["fda_exports_generated"] == 1
    assert summary_payload["demo_resets_completed"] == 1

    steps_by_name = {row["step"]: row for row in summary_payload["steps"]}
    assert steps_by_name["facility_setup"]["viewed"] == 2
    assert steps_by_name["facility_setup"]["completed"] == 1
    assert steps_by_name["facility_setup"]["completion_rate_pct"] == 50.0
    assert steps_by_name["ftl_scoping"]["viewed"] == 1
    assert steps_by_name["ftl_scoping"]["completed"] == 2
    assert steps_by_name["ftl_scoping"]["completion_rate_pct"] == 200.0
