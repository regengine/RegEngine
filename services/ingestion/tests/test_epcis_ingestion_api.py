"""API tests for EPCIS ingestion endpoints.

Data-free: no EPCIS documents, events, GS1 identifiers, or lot codes.
"""

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.epcis.persistence import _epcis_idempotency_index, _epcis_store
from app.epcis.router import router as epcis_ingestion_router
from app.webhook_compat import _verify_api_key

from services.ingestion.tests.tenant_context_overrides import install_tenant_context_override

TEST_TENANT_ID = str(uuid4())


def _assert_no_traceback(response) -> None:
    text = response.text
    assert "Traceback" not in text
    assert 'File "' not in text


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(epcis_ingestion_router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    install_tenant_context_override(app, default_tenant=TEST_TENANT_ID)
    _epcis_store.clear()
    _epcis_idempotency_index.clear()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def claims_client() -> TestClient:
    """Same app, but a query or header tenant that disagrees with the
    authenticated tenant is rejected."""
    app = FastAPI()
    app.include_router(epcis_ingestion_router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    install_tenant_context_override(app, default_tenant=TEST_TENANT_ID, enforce_claims=True)
    _epcis_store.clear()
    _epcis_idempotency_index.clear()
    with TestClient(app) as test_client:
        yield test_client


def test_batch_ingest_rejects_empty_body(client: TestClient) -> None:
    response = client.post(
        "/api/v1/epcis/events/batch",
        headers={"X-Tenant-ID": TEST_TENANT_ID},
        json={"events": []},
    )
    assert response.status_code == 400
    detail = response.json().get("detail", "")
    assert isinstance(detail, str)
    assert "at least one event" in detail
    _assert_no_traceback(response)


def test_unknown_event_id_returns_404(client: TestClient) -> None:
    response = client.get(
        f"/api/v1/epcis/events/{uuid4()}",
        headers={"X-Tenant-ID": TEST_TENANT_ID},
    )
    assert response.status_code == 404
    detail = response.json().get("detail", "")
    assert isinstance(detail, str)
    assert "not found" in detail.lower()
    _assert_no_traceback(response)


def test_events_reject_non_json_content_type(client: TestClient) -> None:
    response = client.post(
        "/api/v1/epcis/events",
        headers={"X-Tenant-ID": TEST_TENANT_ID, "Content-Type": "text/plain"},
        content=b"not-json",
    )
    assert response.status_code == 422
    _assert_no_traceback(response)


def test_tenant_query_override_rejected(claims_client: TestClient) -> None:
    response = claims_client.get(
        "/api/v1/epcis/export",
        params={"tenant_id": str(uuid4())},
        headers={"X-Tenant-ID": TEST_TENANT_ID},
    )
    assert response.status_code == 409
    detail = response.json().get("detail", {})
    assert isinstance(detail, dict)
    assert detail.get("code") == "E_TENANT_MISMATCH"
    _assert_no_traceback(response)


def test_empty_export_and_filter_keep_metadata_field(client: TestClient) -> None:
    product_id = f"urn:uuid:{uuid4()}"
    response = client.get(
        "/api/v1/epcis/export",
        params={"product_id": product_id},
        headers={"X-Tenant-ID": TEST_TENANT_ID},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["epcisBody"]["eventList"] == []
    assert body["regengine:metadata"]["regengine:event_count"] == 0
    assert body["regengine:metadata"]["regengine:filters"]["regengine:product_id"] == product_id
