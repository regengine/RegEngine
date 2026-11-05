"""EDI 856 events must carry the KDEs that shipping validation requires.

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
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.edi_ingestion.rejection_log as rejection_log  # noqa: E402
import app.edi_ingestion.routes as edi_ingestion_routes  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.edi_ingestion import router as edi_router  # noqa: E402
from app.webhook_models import IngestResponse, WebhookCTEType, WebhookPayload  # noqa: E402
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


def _post(route: str, data: dict[str, str]):
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test", scopes=["edi.ingest"], tenant_id=_TENANT
    )
    with TestClient(app) as client:
        return client.post(
            f"/api/v1/ingest/edi{route}",
            data=data,
            files={"file": ("asn_856.edi", _ASN_856.read_bytes(), "application/edi-x12")},
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
        assert _validate_event_kdes(event) == [
            "Missing required KDE 'tlc_source_reference' for shipping CTE"
        ]


@pytest.mark.parametrize("route", ["", "/document"])
def test_both_routes_defer_only_shipping_tlc_source_reference(route: str, monkeypatch: pytest.MonkeyPatch, captured) -> None:
    seen: list[dict] = []

    async def _capture_kwargs(payload: WebhookPayload, **kwargs) -> IngestResponse:
        seen.append(kwargs)
        return IngestResponse(accepted=0, rejected=0, total=len(payload.events), events=[])

    monkeypatch.setattr(edi_ingestion_routes, "ingest_events", _capture_kwargs)

    assert _post(route, {"traceability_lot_code": "LOT-856-KDE"}).status_code == 201
    assert seen
    for kwargs in seen:
        assert kwargs["deferred_kdes"] == {WebhookCTEType.SHIPPING: frozenset({"tlc_source_reference"})}


def _two_lot_asn() -> bytes:
    raw = _ASN_856.read_text(encoding="utf-8")
    line = "LIN**SK*ROMAINE-12CT~SN1**200*CA~"
    assert line in raw
    two_lots = raw.replace(
        line,
        "LIN**SK*ROMAINE-12CT~SN1**100*CA~REF*LT*LOT-A~LIN**SK*ROMAINE-12CT~SN1**100*CA~REF*LT*LOT-B~",
    )
    return two_lots.replace("SE*10*0001", "SE*14*0001").encode()


def _post_two_lots(route: str, data: dict[str, str]):
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test", scopes=["edi.ingest"], tenant_id=_TENANT
    )
    with TestClient(app) as client:
        return client.post(
            f"/api/v1/ingest/edi{route}",
            data=data,
            files={"file": ("asn_856.edi", _two_lot_asn(), "application/edi-x12")},
        )


@pytest.mark.parametrize("route", ["", "/document"])
def test_one_reference_cannot_cover_distinct_lots(route: str, monkeypatch: pytest.MonkeyPatch, captured) -> None:
    rejection_log.reset_edi_rejections()
    claims: list[tuple] = []

    def _claim(*args, **kwargs):
        claims.append(args)
        return False, None

    monkeypatch.setattr(edi_ingestion_routes, "check_and_record_interchange", _claim)

    response = _post_two_lots(route, {"traceability_lot_code": "LOT-856-KDE", "tlc_source_reference": "PACK-0310"})

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["error"] == "edi_tlc_source_reference_with_multiple_lots"
    assert captured == []
    assert claims == [], "a refused document must not reserve its ISA13"
    recorded = rejection_log.list_edi_rejections(_TENANT)
    assert [record["reason"] for record in recorded] == ["edi_tlc_source_reference_with_multiple_lots"]
    assert response.json()["detail"]["rejection_id"] == recorded[0]["rejection_id"]


@pytest.mark.parametrize("route", ["", "/document"])
def test_distinct_lots_without_a_reference_are_ingested(route: str, captured) -> None:
    response = _post_two_lots(route, {"traceability_lot_code": "LOT-856-KDE"})

    assert response.status_code == 201, response.text
    events = [event for payload in captured for event in payload.events]
    assert {event.traceability_lot_code for event in events} == {"LOT-A", "LOT-B"}
    assert all(event.kdes.get("tlc_source_reference") is None for event in events)


@pytest.mark.parametrize("transaction_set", ["861", "944"])
def test_multi_lot_receipt_may_share_a_reference(transaction_set: str) -> None:
    """Receiving requires the KDE, so refusing it would leave no way in."""
    edi_ingestion_routes._reject_shared_tlc_source_for_distinct_lots(
        tlc_source_reference="PACK-0310",
        transaction_sets=[(transaction_set, {"line_items": [{"lot_number": "LOT-A"}, {"lot_number": "LOT-B"}]})],
        traceability_lot_code="LOT-FORM",
        sender_tenant_id=_TENANT,
        partner_id=None,
        source="edi_inbound",
    )


def _check_945_lines(*lines: dict) -> None:
    edi_ingestion_routes._reject_shared_tlc_source_for_distinct_lots(
        tlc_source_reference="PACK-0310",
        transaction_sets=[("945", {"line_items": list(lines)})],
        traceability_lot_code="LOT-FORM",
        sender_tenant_id=_TENANT,
        partner_id=None,
        source="edi_inbound",
    )


def test_one_short_lot_on_two_gtins_is_two_tlcs() -> None:
    with pytest.raises(HTTPException) as refused:
        _check_945_lines(
            {"lot_number": "A1", "gtin": "00012345678901"},
            {"lot_number": "A1", "gtin": "00012345678902"},
        )

    assert refused.value.detail["error"] == "edi_tlc_source_reference_with_multiple_lots"


def test_one_short_lot_on_one_gtin_is_one_tlc() -> None:
    _check_945_lines(
        {"lot_number": "A1", "gtin": "00012345678901"},
        {"lot_number": "A1", "gtin": "00012345678901"},
    )
