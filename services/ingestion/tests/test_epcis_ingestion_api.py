"""API tests for EPCIS ingestion endpoints."""

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.epcis_ingestion import _epcis_idempotency_index, _epcis_store, router as epcis_ingestion_router
from app.webhook_router import _verify_api_key


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(epcis_ingestion_router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    _epcis_store.clear()
    _epcis_idempotency_index.clear()
    with TestClient(app) as test_client:
        yield test_client


VALID_EPCIS_EVENT = {
    "@context": ["https://ref.gs1.org/standards/epcis/2.0.0/epcis-context.jsonld"],
    "type": "ObjectEvent",
    "eventTime": "2026-02-28T09:30:00.000-05:00",
    "eventTimeZoneOffset": "-05:00",
    "action": "OBSERVE",
    "bizStep": "urn:epcglobal:cbv:bizstep:receiving",
    "bizLocation": {"id": "urn:epc:id:sgln:0614141.00002.0"},
    "sourceList": [
        {
            "type": "urn:epcglobal:cbv:sdt:possessing_party",
            "source": "urn:epc:id:sgln:0614141.00001.0",
        }
    ],
    "destinationList": [
        {
            "type": "urn:epcglobal:cbv:sdt:possessing_party",
            "destination": "urn:epc:id:sgln:0614141.00002.0",
        }
    ],
    "ilmd": {
        "cbvmda:lotNumber": "ROM-0042",
        "fsma:traceabilityLotCode": "LOT-2026-ROM-0042",
    },
}


def test_validate_and_ingest_epcis_event(client: TestClient) -> None:
    validate_response = client.post("/api/v1/epcis/validate", json=VALID_EPCIS_EVENT)
    assert validate_response.status_code == 200
    validate_payload = validate_response.json()
    assert validate_payload["valid"] is True

    ingest_response = client.post("/api/v1/epcis/events", json=VALID_EPCIS_EVENT)
    assert ingest_response.status_code == 201
    ingest_payload = ingest_response.json()
    assert ingest_payload["cte_id"]
    assert ingest_payload["validation_status"] == "valid"
    assert ingest_payload["idempotent"] is False

    second_ingest = client.post("/api/v1/epcis/events", json=VALID_EPCIS_EVENT)
    assert second_ingest.status_code == 200
    second_payload = second_ingest.json()
    assert second_payload["cte_id"] == ingest_payload["cte_id"]
    assert second_payload["idempotent"] is True

    event_id = ingest_payload["cte_id"]
    get_response = client.get(f"/api/v1/epcis/events/{event_id}")
    assert get_response.status_code == 200
    event_payload = get_response.json()
    assert event_payload["normalized_cte"]["tlc"] == "LOT-2026-ROM-0042"


def test_batch_ingest_with_mixed_validity(client: TestClient) -> None:
    invalid_event = {
        "type": "ObjectEvent",
        "eventTime": "2026-03-01T00:00:00.000Z",
    }

    response = client.post(
        "/api/v1/epcis/events/batch",
        json={"events": [VALID_EPCIS_EVENT, invalid_event]},
    )
    assert response.status_code == 207
    payload = response.json()
    assert payload["created"] >= 0
    assert payload["failed"] == 1

    empty_batch_response = client.post("/api/v1/epcis/events/batch", json={"events": []})
    assert empty_batch_response.status_code == 400

    export_response = client.get("/api/v1/epcis/export")
    assert export_response.status_code == 200
    export_payload = export_response.json()
    assert export_payload["type"] == "EPCISDocument"
    assert len(export_payload["epcisBody"]["eventList"]) >= 1

    filtered_response = client.get("/api/v1/epcis/export", params={"product_id": "non-existent"})
    assert filtered_response.status_code == 200
    filtered_payload = filtered_response.json()
    assert filtered_payload["metadata"]["filters"]["product_id"] == "non-existent"
