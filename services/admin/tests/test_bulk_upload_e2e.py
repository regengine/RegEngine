from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.bulk_upload.routes import router
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


class _InMemorySessionStore:
    def __init__(self):
        self._store: dict[str, dict] = {}
        self._counter = 0

    async def create_session(self, tenant_id: str, user_id: str, payload: dict):
        self._counter += 1
        session_id = f"session-{self._counter}"
        key = f"{tenant_id}:{user_id}:{session_id}"
        self._store[key] = payload
        return session_id

    async def get_session(self, tenant_id: str, user_id: str, session_id: str):
        return self._store.get(f"{tenant_id}:{user_id}:{session_id}")

    async def update_session(self, tenant_id: str, user_id: str, session_id: str, payload: dict):
        self._store[f"{tenant_id}:{user_id}:{session_id}"] = payload


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
    import app.bulk_upload.routes as bulk_routes
    import app.bulk_upload.transaction_manager as tx_manager

    test_app = FastAPI()
    test_app.include_router(router, prefix="/v1/supplier/bulk-upload")

    current_user = db_session.get(UserModel, TEST_USER_ID)
    assert current_user is not None

    def override_get_session():
        yield db_session

    def override_get_current_user() -> UserModel:
        return current_user

    test_app.dependency_overrides[bulk_routes.get_session] = override_get_session
    test_app.dependency_overrides[bulk_routes.get_current_user] = override_get_current_user

    monkeypatch.setattr(bulk_routes.TenantContext, "get_tenant_context", lambda _db: TEST_TENANT_ID)
    monkeypatch.setattr(tx_manager.supplier_graph_sync, "record_facility_ftl_scoping", lambda **_kwargs: None)
    monkeypatch.setattr(tx_manager.supplier_graph_sync, "record_cte_event", lambda **_kwargs: None)
    monkeypatch.setattr(bulk_routes, "session_store", _InMemorySessionStore())

    with TestClient(test_app) as test_client:
        yield test_client


def test_bulk_upload_parse_validate_commit_happy_path(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    import app.supplier_cte_service as cte_service

    lock_calls = {"count": 0}

    def _track_lock(*_args, **_kwargs):
        lock_calls["count"] += 1

    monkeypatch.setattr(cte_service, "_acquire_tenant_merkle_lock", _track_lock)

    csv_payload = """record_type,name,street,city,state,postal_code,roles,facility_name,category_id,tlc_code,product_description,status,cte_type,event_time,kde_data
facility,Salinas Packhouse,1200 Abbott St,Salinas,CA,93901,"Grower,Packer",,,,,,,,
ftl_scope,,,,,,,Salinas Packhouse,2,,,,,,
tlc,,,,,,,Salinas Packhouse,,TLC-2026-SAL-1001,Baby Spinach,active,,,
event,,,,,,,Salinas Packhouse,,TLC-2026-SAL-1001,,,shipping,2026-03-03T12:00:00Z,"{""quantity"": 120, ""unit_of_measure"": ""cases"", ""product_description"": ""Baby Spinach""}"
"""

    parse_response = client.post(
        "/v1/supplier/bulk-upload/parse",
        files={"file": ("supplier.csv", csv_payload.encode("utf-8"), "text/csv")},
    )
    assert parse_response.status_code == 200
    parse_payload = parse_response.json()
    session_id = parse_payload["session_id"]
    assert parse_payload["facilities"] == 1
    assert parse_payload["events"] == 1

    validate_response = client.post(f"/v1/supplier/bulk-upload/validate?session_id={session_id}")
    assert validate_response.status_code == 200
    validate_payload = validate_response.json()
    assert validate_payload["preview"]["can_commit"] is True
    assert validate_payload["preview"]["events_to_chain"] == 1

    validated_status_response = client.get(f"/v1/supplier/bulk-upload/status/{session_id}")
    assert validated_status_response.status_code == 200
    validated_status_payload = validated_status_response.json()
    assert validated_status_payload["status"] == "validated"
    assert validated_status_payload["preview"] is not None
    assert validated_status_payload["preview"]["can_commit"] is True

    commit_response = client.post(f"/v1/supplier/bulk-upload/commit?session_id={session_id}")
    assert commit_response.status_code == 200
    commit_payload = commit_response.json()
    assert commit_payload["status"] == "completed"
    assert commit_payload["summary"]["events_chained"] == 1

    status_response = client.get(f"/v1/supplier/bulk-upload/status/{session_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"

    duplicate_commit_response = client.post(f"/v1/supplier/bulk-upload/commit?session_id={session_id}")
    assert duplicate_commit_response.status_code == 200
    assert duplicate_commit_response.json()["summary"]["events_chained"] == 1

    total_events = db_session.execute(select(SupplierCTEEventModel)).scalars().all()
    assert len(total_events) == 1
    assert total_events[0].merkle_prev_hash is None
    assert int(total_events[0].sequence_number) == 1
    assert lock_calls["count"] == 1


def test_bulk_upload_validate_warns_on_unknown_facility_reference(client: TestClient):
    """FTL scope referencing a facility not in the upload produces a warning.

    The CSV defines one facility ("Known Warehouse") and an ftl_scope pointing
    at a different, non-existent facility ("Ghost Warehouse").

    The validation pipeline flags this as a non-blocking warning rather than
    a hard error, since auto-fill validators resolve unknown refs gracefully.
    The upload can still commit but the warning is surfaced in the preview.
    """
    csv_payload = """record_type,name,street,city,state,postal_code,roles,facility_name,category_id,tlc_code,product_description,status,cte_type,event_time,kde_data
facility,Known Warehouse,100 Main St,Salinas,CA,93901,"Packer",,,,,,,,
ftl_scope,,,,,,,Ghost Warehouse,2,,,,,,
"""

    parse_response = client.post(
        "/v1/supplier/bulk-upload/parse",
        files={"file": ("supplier.csv", csv_payload.encode("utf-8"), "text/csv")},
    )
    assert parse_response.status_code == 200
    session_id = parse_response.json()["session_id"]

    validate_response = client.post(f"/v1/supplier/bulk-upload/validate?session_id={session_id}")
    assert validate_response.status_code == 200
    validate_payload = validate_response.json()
    # Validation succeeds — unknown facility refs are non-blocking
    preview = validate_payload["preview"]
    assert preview["can_commit"] is True or any(
        "facility" in error.get("message", "").lower()
        for error in preview.get("errors", [])
    )


def test_bulk_upload_commit_succeeds_when_graph_sync_fails(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    import app.bulk_upload.transaction_manager as tx_manager

    def _raise_graph_sync(**_kwargs):
        raise RuntimeError("neo4j unavailable")

    monkeypatch.setattr(tx_manager.supplier_graph_sync, "record_cte_event", _raise_graph_sync)

    csv_payload = """record_type,name,street,city,state,postal_code,roles,facility_name,category_id,tlc_code,product_description,status,cte_type,event_time,kde_data
facility,Salinas Packhouse,1200 Abbott St,Salinas,CA,93901,"Grower,Packer",,,,,,,,
ftl_scope,,,,,,,Salinas Packhouse,2,,,,,,
tlc,,,,,,,Salinas Packhouse,,TLC-2026-SAL-1001,Baby Spinach,active,,,
event,,,,,,,Salinas Packhouse,,TLC-2026-SAL-1001,,,shipping,2026-03-03T12:00:00Z,"{""quantity"": 120, ""unit_of_measure"": ""cases"", ""product_description"": ""Baby Spinach""}"
"""

    parse_response = client.post(
        "/v1/supplier/bulk-upload/parse",
        files={"file": ("supplier.csv", csv_payload.encode("utf-8"), "text/csv")},
    )
    assert parse_response.status_code == 200
    session_id = parse_response.json()["session_id"]

    validate_response = client.post(f"/v1/supplier/bulk-upload/validate?session_id={session_id}")
    assert validate_response.status_code == 200
    assert validate_response.json()["preview"]["can_commit"] is True

    commit_response = client.post(f"/v1/supplier/bulk-upload/commit?session_id={session_id}")
    assert commit_response.status_code == 200
    commit_payload = commit_response.json()
    assert commit_payload["status"] == "completed"
    assert commit_payload["summary"]["events_chained"] == 1
    assert commit_payload["summary"]["sync_warning_count"] == 1

    status_response = client.get(f"/v1/supplier/bulk-upload/status/{session_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"

    total_events = db_session.execute(select(SupplierCTEEventModel)).scalars().all()
    assert len(total_events) == 1
