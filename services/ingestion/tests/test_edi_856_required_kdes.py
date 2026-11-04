"""EDI 856 and 861 events must carry the KDEs that validation requires.

Both EDI routes built 856 events with ``reference_document_number`` only and
never set ``tlc_source_reference``, while ``REQUIRED_KDES_BY_CTE[SHIPPING]``
requires ``reference_document`` and ``tlc_source_reference``. Every 856 was
therefore rejected in ``ingest_events``. These checks post the recorded ASN
fixture through each route and run the captured events through the real
KDE validator.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.edi_ingestion.routes as edi_ingestion_routes  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.edi_ingestion import router as edi_router  # noqa: E402
from app.edi_ingestion.extractors import _extract_861_fields  # noqa: E402
from app.edi_ingestion.parser import _parse_x12_segments  # noqa: E402
from app.webhook_models import IngestResponse, WebhookPayload  # noqa: E402
from app.webhook_router_v2 import _validate_event_kdes  # noqa: E402

_ASN_856 = Path(__file__).parent / "fixtures" / "edi_corpus" / "asn_856.edi"
_TENANT = "11111111-1111-1111-1111-111111111111"


@pytest.fixture()
def captured(monkeypatch: pytest.MonkeyPatch) -> list[WebhookPayload]:
    payloads: list[WebhookPayload] = []

    async def _capture(payload: WebhookPayload, **_kwargs) -> IngestResponse:
        payloads.append(payload)
        return IngestResponse(accepted=0, rejected=0, total=len(payload.events), events=[])

    monkeypatch.setattr(edi_ingestion_routes, "ingest_events", _capture)
    monkeypatch.setattr(edi_ingestion_routes, "_resolve_principal_tenant_id", lambda *args: _TENANT)
    monkeypatch.setattr(edi_ingestion_routes, "check_and_record_interchange", lambda *args, **kwargs: (False, None))
    monkeypatch.delenv("EDI_REQUIRE_PARTNER_ID", raising=False)
    monkeypatch.delenv("EDI_PARTNER_ALLOWLIST", raising=False)
    return payloads


def _post(route: str, data: dict[str, str], body: bytes | None = None):
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test", scopes=["edi.ingest"], tenant_id=_TENANT
    )
    with TestClient(app) as client:
        return client.post(
            f"/api/v1/ingest/edi{route}",
            data=data,
            files={"file": ("document.edi", body or _ASN_856.read_bytes(), "application/edi-x12")},
        )


@pytest.mark.parametrize("route", ["", "/document"])
def test_856_with_tlc_source_reference_passes_kde_validation(route: str, captured) -> None:
    response = _post(route, {"traceability_lot_code": "LOT-856-KDE", "tlc_source_reference": " PACK-0310 "})

    assert response.status_code == 201, response.text
    events = [event for payload in captured for event in payload.events]
    assert events
    for event in events:
        assert event.kdes["reference_document"] == "BOL-9001"
        assert event.kdes["tlc_source_reference"] == "PACK-0310"
        assert _validate_event_kdes(event) == []


@pytest.mark.parametrize("route", ["", "/document"])
def test_856_without_tlc_source_reference_only_misses_that_kde(route: str, captured) -> None:
    response = _post(route, {"traceability_lot_code": "LOT-856-KDE"})

    assert response.status_code == 201, response.text
    events = [event for payload in captured for event in payload.events]
    assert events
    for event in events:
        assert _validate_event_kdes(event) == ["Missing required KDE 'tlc_source_reference' for shipping CTE"]


def _receiving_advice_861(*ship_from: str) -> bytes:
    body = [
        "ST*861*0001",
        "BRA*RA-861-1*20260311*00",
        *ship_from,
        "N1*ST*Metro Distribution Center*92*6141410000069",
        "RCD**200*CA",
        "REF*LT*00012345678901-LOT861",
        f"SE*{len(ship_from) + 6}*0001",
    ]
    segments = [
        "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *260311*1200*U*00401*000000861*0*P*>",
        "GS*RE*SENDERID*RECEIVERID*20260311*1200*1*X*004010",
        *body,
        "GE*1*1",
        "IEA*1*000000861",
    ]
    return ("~".join(segments) + "~").encode()


@pytest.mark.parametrize(
    ("ship_from", "expected"),
    [
        ("N1*SF*Valley Fresh Farms*92*6141410000014", "Valley Fresh Farms"),
        ("N1*SF**92*6141410000014", "6141410000014"),
    ],
)
def test_861_takes_immediate_previous_source_from_ship_from(ship_from: str, expected: str, captured) -> None:
    response = _post(
        "/document",
        {"traceability_lot_code": "LOT-861-KDE", "tlc_source_reference": "PACK-0311"},
        _receiving_advice_861(ship_from),
    )

    assert response.status_code == 201, response.text
    events = [event for payload in captured for event in payload.events]
    assert events
    for event in events:
        assert event.kdes["immediate_previous_source"] == expected
        assert _validate_event_kdes(event) == []


def test_861_without_ship_from_only_misses_immediate_previous_source(captured) -> None:
    response = _post(
        "/document",
        {"traceability_lot_code": "LOT-861-KDE", "tlc_source_reference": "PACK-0311"},
        _receiving_advice_861(),
    )

    assert response.status_code == 201, response.text
    events = [event for payload in captured for event in payload.events]
    assert events
    for event in events:
        assert "immediate_previous_source" not in event.kdes
        assert _validate_event_kdes(event) == ["Missing required KDE 'immediate_previous_source' for receiving CTE"]


_SUPPLIER = "N1*SU*Fresh Supply Co*92*0614141000005"
_SHIP_FROM = "N1*SF*Valley Fresh Farms*92*6141410000014"


@pytest.mark.parametrize(
    ("parties", "expected_source", "expected_gln"),
    [
        ((_SUPPLIER, _SHIP_FROM), "Valley Fresh Farms", "6141410000014"),
        ((_SHIP_FROM, _SUPPLIER), "Valley Fresh Farms", "6141410000014"),
        ((_SUPPLIER,), "Fresh Supply Co", "0614141000005"),
        ((_SUPPLIER, "N1*SF"), "Fresh Supply Co", "0614141000005"),
    ],
)
def test_861_prefers_the_ship_from_party_over_a_supplier(
    parties: tuple[str, ...], expected_source: str, expected_gln: str, captured
) -> None:
    response = _post(
        "/document",
        {"traceability_lot_code": "LOT-861-KDE", "tlc_source_reference": "PACK-0311"},
        _receiving_advice_861(*parties),
    )

    assert response.status_code == 201, response.text
    events = [event for payload in captured for event in payload.events]
    assert events
    for event in events:
        assert event.kdes["immediate_previous_source"] == expected_source
        assert event.kdes["ship_from_location"] == expected_source
        assert _validate_event_kdes(event) == []
    assert _extract_861_fields(_parse_x12_segments(_receiving_advice_861(*parties).decode()))["ship_from_gln"] == (
        expected_gln
    )
