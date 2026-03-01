"""API tests for EPCIS ingestion endpoints."""

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
from main import app


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


def test_validate_and_ingest_epcis_event() -> None:
    with TestClient(app) as client:
        validate_response = client.post("/api/v1/epcis/validate", json=VALID_EPCIS_EVENT)
        assert validate_response.status_code == 200
        validate_payload = validate_response.json()
        assert validate_payload["valid"] is True

        ingest_response = client.post("/api/v1/epcis/events", json=VALID_EPCIS_EVENT)
        assert ingest_response.status_code == 200
        ingest_payload = ingest_response.json()
        assert ingest_payload["cte_id"]
        assert ingest_payload["validation_status"] == "valid"

        event_id = ingest_payload["cte_id"]
        get_response = client.get(f"/api/v1/epcis/events/{event_id}")
        assert get_response.status_code == 200
        event_payload = get_response.json()
        assert event_payload["normalized_cte"]["tlc"] == "LOT-2026-ROM-0042"


def test_batch_ingest_with_mixed_validity() -> None:
    invalid_event = {
        "type": "ObjectEvent",
        "eventTime": "2026-03-01T00:00:00.000Z",
    }

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/epcis/events/batch",
            json={"events": [VALID_EPCIS_EVENT, invalid_event]},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["created"] == 1
        assert payload["failed"] == 1

        export_response = client.get("/api/v1/epcis/export")
        assert export_response.status_code == 200
        export_payload = export_response.json()
        assert export_payload["type"] == "EPCISDocument"
        assert len(export_payload["epcisBody"]["eventList"]) >= 1
