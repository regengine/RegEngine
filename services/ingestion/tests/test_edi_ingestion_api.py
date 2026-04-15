"""API tests for EDI 856 ingestion endpoint."""

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.authz import IngestionPrincipal, get_ingestion_principal
import app.edi_ingestion.routes as edi_ingestion_routes
from app.edi_ingestion import router as edi_router
from app.webhook_models import EventResult, IngestResponse, WebhookCTEType

TEST_TENANT_ID = "00000000-0000-0000-0000-000000000123"

VALID_856 = (
    b"ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *260310*1200*U*00401*000000001*0*P*>~"
    b"GS*SH*SENDER*RECEIVER*20260310*1200*1*X*004010~"
    b"ST*856*0001~"
    b"BSN*00*ASN-12345*20260310*1200~"
    b"HL*1**S~"
    b"N1*SF*Valley Fresh Farms*92*0614141000005~"
    b"N1*ST*Metro Distribution Center*92*0614141000006~"
    b"LIN**SK*ROMAINE-12CT~"
    b"SN1**200*CA~"
    b"REF*BM*BOL-9001~"
    b"TD5**2*ColdExpress~"
    b"SE*11*0001~"
    b"GE*1*1~"
    b"IEA*1*000000001~"
)

INVALID_DOC_TYPE = (
    b"ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *260310*1200*U*00401*000000001*0*P*>~"
    b"GS*PO*SENDER*RECEIVER*20260310*1200*1*X*004010~"
    b"ST*850*0001~"
    b"BEG*00*SA*PO-100~"
    b"PO1*1*50*CA*12.5~"
    b"SE*5*0001~"
    b"GE*1*1~"
    b"IEA*1*000000001~"
)

MISSING_REQUIRED_SEGMENT = (
    b"ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *260310*1200*U*00401*000000001*0*P*>~"
    b"GS*SH*SENDER*RECEIVER*20260310*1200*1*X*004010~"
    b"ST*856*0001~"
    b"BSN*00*ASN-12345*20260310*1200~"
    b"SE*4*0001~"
    b"GE*1*1~"
    b"IEA*1*000000001~"
)


@pytest.fixture()
def captured_payload() -> dict:
    return {}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, captured_payload: dict) -> TestClient:
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key",
        scopes=["*"],
        auth_mode="test",
    )

    async def _fake_ingest_events(payload, x_regengine_api_key=None):
        captured_payload["payload"] = payload
        event = payload.events[0]
        return IngestResponse(
            accepted=1,
            rejected=0,
            total=1,
            events=[
                EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="accepted",
                    event_id="evt-edi-1",
                    sha256_hash="hash-1",
                    chain_hash="chain-1",
                )
            ],
        )

    monkeypatch.setattr(edi_ingestion_routes, "ingest_events", _fake_ingest_events)

    with TestClient(app) as test_client:
        yield test_client


def test_ingest_edi_856_happy_path(client: TestClient, captured_payload: dict) -> None:
    response = client.post(
        "/api/v1/ingest/edi",
        data={
            "traceability_lot_code": "LOT-2026-EDI-001",
            "tenant_id": TEST_TENANT_ID,
        },
        files={"file": ("asn.edi", VALID_856, "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )
    assert response.status_code == 201

    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["document_type"] == "X12_856"
    assert payload["sender_tenant_id"] == TEST_TENANT_ID
    assert payload["partner_id"] == "WALMART"
    assert payload["extracted"]["quantity"] == 200.0
    assert payload["extracted"]["unit_of_measure"] == "cases"
    assert payload["ingestion_result"]["accepted"] == 1

    webhook_payload = captured_payload["payload"]
    assert webhook_payload.tenant_id == TEST_TENANT_ID
    assert webhook_payload.source == "edi_856_inbound"
    event = webhook_payload.events[0]
    assert event.cte_type == WebhookCTEType.SHIPPING
    assert event.traceability_lot_code == "LOT-2026-EDI-001"
    assert event.quantity == 200.0
    assert event.unit_of_measure == "cases"
    assert event.kdes["ship_from_location"] == "Valley Fresh Farms"
    assert event.kdes["ship_to_location"] == "Metro Distribution Center"


def test_ingest_rejects_non_856_transaction_set(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ingest/edi",
        data={
            "traceability_lot_code": "LOT-2026-EDI-002",
            "tenant_id": TEST_TENANT_ID,
        },
        files={"file": ("po.edi", INVALID_DOC_TYPE, "application/edi-x12")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Only X12 856 is currently supported"


def test_ingest_rejects_missing_required_segments(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ingest/edi",
        data={
            "traceability_lot_code": "LOT-2026-EDI-003",
            "tenant_id": TEST_TENANT_ID,
        },
        files={"file": ("bad.edi", MISSING_REQUIRED_SEGMENT, "application/edi-x12")},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["message"] == "EDI 856 missing required segments"
    assert "HL" in detail["missing_segments"]


def test_ingest_denied_without_edi_ingest_scope() -> None:
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="limited-key",
        scopes=["exchange.write"],
        auth_mode="test",
    )

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/ingest/edi",
            data={
                "traceability_lot_code": "LOT-2026-EDI-001",
                "tenant_id": TEST_TENANT_ID,
            },
            files={"file": ("asn.edi", VALID_856, "application/edi-x12")},
            headers={"X-Partner-ID": "WALMART"},
        )

    assert response.status_code == 403
    assert "requires 'edi.ingest'" in response.json()["detail"]
