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
    b"GS*SH*SENDERID*RECEIVERID*20260310*1200*1*X*004010~"
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
    b"GS*SH*SENDERID*RECEIVERID*20260310*1200*1*X*004010~"
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


# ---------------------------------------------------------------------------
# EPIC-N PR-B regression tests
# ---------------------------------------------------------------------------

# TLC that matches the FSMA 204 GTIN-14 + lot-suffix pattern enforced by
# services/shared/schemas.py:FSMAEvent.validate_tlc_format.
_VALID_FSMA_TLC = "00012345678901-LOT001"


def _build_856(
    ship_date: bytes = b"20260310",
    ship_time: bytes = b"1200",
) -> bytes:
    """Assemble a minimal valid 856 with overridable BSN date/time."""
    return (
        b"ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *260310*1200*U*00401*000000001*0*P*>~"
        b"GS*SH*SENDERID*RECEIVERID*20260310*1200*1*X*004010~"
        b"ST*856*0001~"
        b"BSN*00*ASN-12345*" + ship_date + b"*" + ship_time + b"~"
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


def test_document_ingest_fsma_strict_rejects_bad_tlc(client: TestClient) -> None:
    """#1174: EDI documents that fail FSMAEvent schema validation must
    return 422 and persist nothing. Prior behavior persisted with
    fsma_validation_status=failed, polluting the FSMA 204 graph.
    """
    response = client.post(
        "/api/v1/ingest/edi/document",
        data={
            # 'not-a-gtin-tlc' will fail FSMAEvent.validate_tlc_format.
            "traceability_lot_code": "not-a-gtin-tlc",
            "tenant_id": TEST_TENANT_ID,
        },
        files={"file": ("asn.edi", _build_856(), "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "fsma_validation_failed"
    assert detail["tlc"] == "not-a-gtin-tlc"
    assert len(detail["errors"]) >= 1


def test_document_ingest_strict_false_query_advisory(client: TestClient) -> None:
    """#1174: ?strict=false downgrades to advisory for migrations/tests."""
    response = client.post(
        "/api/v1/ingest/edi/document",
        params={"strict": "false"},
        data={
            "traceability_lot_code": "not-a-gtin-tlc",
            "tenant_id": TEST_TENANT_ID,
        },
        files={"file": ("asn.edi", _build_856(), "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )
    assert response.status_code == 201
    assert response.json()["extracted"]["fsma_validation_status"] == "failed"


def test_document_ingest_strict_passes_with_compliant_tlc(
    client: TestClient, captured_payload: dict
) -> None:
    """#1174 sanity: compliant TLC passes strict validation."""
    response = client.post(
        "/api/v1/ingest/edi/document",
        data={
            "traceability_lot_code": _VALID_FSMA_TLC,
            "tenant_id": TEST_TENANT_ID,
        },
        files={"file": ("asn.edi", _build_856(), "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )
    assert response.status_code == 201
    assert response.json()["extracted"]["fsma_validation_status"] == "passed"


def test_six_digit_yymmdd_date_accepted(client: TestClient) -> None:
    """#1167: 6-digit YYMMDD with century window is accepted, not
    silently rewritten to today's date.
    """
    response = client.post(
        "/api/v1/ingest/edi/document",
        data={
            "traceability_lot_code": _VALID_FSMA_TLC,
            "tenant_id": TEST_TENANT_ID,
        },
        # 260310 -> YY=26, pivot=50, expands to 2026-03-10.
        files={"file": ("asn.edi", _build_856(ship_date=b"260310"), "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )
    assert response.status_code == 201, response.text


def test_unparseable_date_returns_400(client: TestClient) -> None:
    """#1167: garbage in the date field must fail the request explicitly,
    not silently fall back to ``datetime.now()``.
    """
    response = client.post(
        "/api/v1/ingest/edi/document",
        data={
            "traceability_lot_code": _VALID_FSMA_TLC,
            "tenant_id": TEST_TENANT_ID,
        },
        # "ABCDE" has 0 digits after \D strip → raises ValueError
        # in _parse_edi_date_digits → HTTP 400.
        files={"file": ("asn.edi", _build_856(ship_date=b"ABCDE"), "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "invalid_edi_date"


def test_segment_cap_exceeded_returns_413(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#1171: a crafted envelope over EDI_MAX_SEGMENTS must fail fast
    rather than expanding in memory past the file-size cap.
    """
    # Our test envelope is ~15 segments; cap at 3 forces the cap hit
    # without building a multi-MB payload in-test.
    monkeypatch.setenv("EDI_MAX_SEGMENTS", "3")
    response = client.post(
        "/api/v1/ingest/edi/document",
        data={
            "traceability_lot_code": _VALID_FSMA_TLC,
            "tenant_id": TEST_TENANT_ID,
        },
        files={"file": ("asn.edi", _build_856(), "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )
    assert response.status_code == 413
    detail = response.json()["detail"]
    assert detail["error"] == "segment_count_exceeded"
    assert detail["cap"] == 3


def test_utf8_decode_preserves_latin1_bytes_as_real_chars(
    client: TestClient,
) -> None:
    """#1170: a latin-1 encoded partner name flows in. Historical bugs:
    ``errors='ignore'`` dropped the bad byte; ``errors='replace'``
    substituted U+FFFD. Both are data corruption.

    The spec-honoring fix falls back to ``latin-1`` strict (X12.5/X12.6
    Basic character set) and preserves 0xF1 as the real ñ character. The
    document still ingests and the partner name round-trips exactly.
    """
    # latin-1 "ñ" (0xF1) in partner name — invalid as UTF-8 but
    # spec-compliant X12 Basic set.
    envelope = _build_856().replace(b"Valley Fresh Farms", b"Valley Fre\xf1h Farms")
    response = client.post(
        "/api/v1/ingest/edi/document",
        data={
            "traceability_lot_code": _VALID_FSMA_TLC,
            "tenant_id": TEST_TENANT_ID,
        },
        files={"file": ("asn.edi", envelope, "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )
    # The document ingests successfully — no U+FFFD, no dropped byte,
    # the real ñ is in the decoded stream.
    assert response.status_code == 201, response.text
