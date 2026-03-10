"""Tests for legacy webhook_router v1 compatibility shim."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app import webhook_router
from app.webhook_compat import _verify_api_key as compat_verify_api_key
from app.webhook_models import IngestResponse


def _sample_payload_dict() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "source": "unit-test",
        "tenant_id": "tenant-123",
        "events": [
            {
                "cte_type": "shipping",
                "traceability_lot_code": "LOT-001",
                "product_description": "Romaine Lettuce",
                "quantity": 25,
                "unit_of_measure": "cases",
                "location_name": "DC West",
                "timestamp": now,
                "kdes": {
                    "ship_date": now,
                    "ship_from_location": "Farm A",
                    "ship_to_location": "DC West",
                },
            }
        ],
    }


@pytest.mark.asyncio
async def test_ingest_events_delegates_to_v2_and_logs_once(monkeypatch) -> None:
    webhook_router._deprecation_logged = False
    fake_response = IngestResponse(accepted=1, rejected=0, total=1, events=[])
    delegated = AsyncMock(return_value=fake_response)
    warning = Mock()

    monkeypatch.setattr(webhook_router, "ingest_events_v2", delegated)
    monkeypatch.setattr(webhook_router.logger, "warning", warning)

    payload = webhook_router.WebhookPayload.model_validate(_sample_payload_dict())
    first = await webhook_router.ingest_events(payload=payload, x_regengine_api_key="key-1")
    second = await webhook_router.ingest_events(payload=payload, x_regengine_api_key="key-2")

    assert first is fake_response
    assert second is fake_response
    assert delegated.await_count == 2
    assert delegated.await_args_list[0].kwargs["x_regengine_api_key"] == "key-1"
    assert delegated.await_args_list[1].kwargs["x_regengine_api_key"] == "key-2"
    assert warning.call_count == 1


def test_ingest_endpoint_forwards_header_to_shim(monkeypatch) -> None:
    captured: dict = {}
    fake_response = IngestResponse(accepted=1, rejected=0, total=1, events=[])

    async def _fake_ingest(payload, x_regengine_api_key=None):
        captured["payload"] = payload
        captured["api_key"] = x_regengine_api_key
        return fake_response

    monkeypatch.setattr(webhook_router, "ingest_events", _fake_ingest)

    app = FastAPI()
    app.include_router(webhook_router.router)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/webhooks/ingest",
            headers={"X-RegEngine-API-Key": "reg-key-123"},
            json=_sample_payload_dict(),
        )

    assert response.status_code == 200
    assert response.json()["accepted"] == 1
    assert captured["api_key"] == "reg-key-123"
    assert captured["payload"].source == "unit-test"
    assert captured["payload"].tenant_id == "tenant-123"


def test_verify_api_key_reexport_matches_compat() -> None:
    assert webhook_router._verify_api_key is compat_verify_api_key
