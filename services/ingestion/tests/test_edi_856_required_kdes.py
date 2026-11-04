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
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.edi_ingestion.routes as edi_ingestion_routes  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.edi_ingestion import router as edi_router  # noqa: E402
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
