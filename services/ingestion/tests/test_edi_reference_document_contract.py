"""EDI source references must reach the actual required-KDE validator."""

from pathlib import Path

import pytest
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.edi_ingestion import router, routes as edi_routes
from app.edi_ingestion.extractors import _extract_fields_for_set
from app.edi_ingestion.parser import _parse_x12_segments
from app.webhook_models import EventResult, IngestResponse
from app.webhook_router_v2.validation import _validate_event_kdes
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

CORPUS = Path(__file__).parent / "fixtures" / "edi_corpus"
TENANT_ID = "00000000-0000-0000-0000-000000000123"
TLC = "00012345678901-LOT001"


def _mapped_event(fixture, transaction_set):
    segments = _parse_x12_segments((CORPUS / f"{fixture}.edi").read_text())
    extracted = _extract_fields_for_set(transaction_set, segments)
    return edi_routes._build_ingest_event_for_set(transaction_set, extracted, TLC, None, None, None, None, segments)


@pytest.mark.parametrize(
    "fixture,transaction_set,reference",
    [
        ("asn_856", "856", "BOL-9001"),
        ("po_850", "850", "PO-7788"),
        ("invoice_810", "810", "INV-4455"),
        ("receiving_861", "861", "RA-9090"),
    ],
)
def test_source_document_reference_satisfies_canonical_kde(fixture, transaction_set, reference):
    event = _mapped_event(fixture, transaction_set)

    assert event.kdes.get("reference_document") == reference
    assert event.kdes["reference_document_number"] == reference
    assert not any("'reference_document'" in error for error in _validate_event_kdes(event))


def test_absent_document_reference_is_not_synthesized():
    segments = _parse_x12_segments((CORPUS / "asn_856.edi").read_text())
    extracted = _extract_fields_for_set("856", segments)
    extracted["reference_document_number"] = None

    event = edi_routes._build_ingest_event_for_set("856", extracted, TLC, None, None, None, None, segments)

    assert "reference_document" not in event.kdes
    assert "reference_document_number" not in event.kdes
    assert "Missing required KDE 'reference_document' for shipping CTE" in _validate_event_kdes(event)


@pytest.mark.parametrize(
    "fixture,transaction_set,kde,date",
    [("asn_856", "856", "ship_date", "2026-03-10"), ("receiving_861", "861", "receive_date", "2026-03-12")],
)
def test_source_event_date_satisfies_its_exact_cte_kde(fixture, transaction_set, kde, date):
    event = _mapped_event(fixture, transaction_set)

    assert event.kdes.get(kde) == date
    assert event.kdes["event_date"] == date
    assert not any(f"'{kde}'" in error for error in _validate_event_kdes(event))


@pytest.mark.parametrize(
    "fixture,transaction_set,source_field",
    [("asn_856", "856", "ship_date_raw"), ("receiving_861", "861", "receive_date_raw")],
)
def test_missing_source_date_fails_closed_before_event_construction(fixture, transaction_set, source_field):
    segments = _parse_x12_segments((CORPUS / f"{fixture}.edi").read_text())
    extracted = _extract_fields_for_set(transaction_set, segments)
    extracted[source_field] = None

    with pytest.raises(HTTPException) as exc:
        edi_routes._build_ingest_event_for_set(transaction_set, extracted, TLC, None, None, None, None, segments)

    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "invalid_edi_date"


@pytest.mark.parametrize("fixture,transaction_set", [("po_850", "850"), ("invoice_810", "810")])
def test_order_and_invoice_dates_are_not_invented_as_shipping_dates(fixture, transaction_set):
    event = _mapped_event(fixture, transaction_set)

    assert "ship_date" not in event.kdes
    assert "Missing required KDE 'ship_date' for shipping CTE" in _validate_event_kdes(event)


@pytest.fixture
def reference_client(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="synthetic-test", scopes=["*"], auth_mode="test", tenant_id=TENANT_ID
    )
    captured = []
    recorded = []

    async def validate_events(payload, **kwargs):
        # Keep the real mapper and required-KDE validation, isolate persistence.
        captured.extend(payload.events)
        results = []
        for event in payload.events:
            errors = _validate_event_kdes(event)
            results.append(
                EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="rejected" if errors else "accepted",
                    errors=errors,
                )
            )
        rejected = sum(bool(result.errors) for result in results)
        return IngestResponse(
            accepted=len(results) - rejected,
            rejected=rejected,
            total=len(results),
            events=results,
        )

    monkeypatch.setattr(edi_routes, "ingest_events", validate_events)
    monkeypatch.setattr(edi_routes, "check_interchange", lambda *args, **kwargs: (False, None))

    monkeypatch.setattr(edi_routes, "record_interchange", lambda **kwargs: recorded.append(kwargs))
    with TestClient(app) as client:
        yield client, captured, recorded


def _upload(client, endpoint, data=None, fixture="asn_856"):
    return client.post(
        endpoint,
        files={"file": ("source.edi", (CORPUS / f"{fixture}.edi").read_bytes(), "application/edi-x12")},
        data={"traceability_lot_code": TLC, **(data or {})},
    )


@pytest.mark.parametrize("endpoint", ["/api/v1/ingest/edi", "/api/v1/ingest/edi/document"])
@pytest.mark.parametrize("tlc_source", [None, "", "   "])
def test_http_mapper_keeps_tlc_source_missing_without_misreporting_present_reference(
    reference_client, endpoint, tlc_source
):
    client, captured, recorded = reference_client
    data = {} if tlc_source is None else {"tlc_source_reference": tlc_source}
    response = _upload(client, endpoint, data)

    assert response.status_code == 422
    errors = response.json()["ingestion_result"]["events"][0]["errors"]
    assert "Missing required KDE 'reference_document' for shipping CTE" not in errors
    assert "Missing required KDE 'tlc_source_reference' for shipping CTE" in errors
    assert captured[0].kdes["reference_document"] == "BOL-9001"
    assert captured[0].kdes["reference_document_number"] == "BOL-9001"
    assert not (captured[0].kdes.get("tlc_source_reference") or "").strip()
    assert recorded == []


@pytest.mark.parametrize("endpoint", ["/api/v1/ingest/edi", "/api/v1/ingest/edi/document"])
def test_explicit_tlc_source_reaches_validator_and_allows_complete_asn(reference_client, endpoint):
    client, captured, recorded = reference_client

    response = _upload(client, endpoint, {"tlc_source_reference": "Original Packing Facility"})

    assert response.status_code == 201
    assert response.json()["ingestion_result"]["accepted"] == 1
    assert captured[0].kdes["tlc_source_reference"] == "Original Packing Facility"
    assert captured[0].kdes["ship_from_location"] == "Valley Fresh Farms"
    assert captured[0].traceability_lot_code == TLC
    assert len(recorded) == 1


def test_explicit_tlc_source_applies_to_supplied_lot_across_batch(reference_client):
    client, captured, recorded = reference_client

    response = _upload(
        client,
        "/api/v1/ingest/edi/document",
        {"tlc_source_reference": "Original Packing Facility"},
        fixture="asn_856_batch",
    )

    assert response.status_code == 201
    assert len(captured) == 3
    assert all(event.kdes["tlc_source_reference"] == "Original Packing Facility" for event in captured)
    assert all(event.traceability_lot_code == TLC for event in captured)
    assert len(recorded) == 1


@pytest.mark.parametrize("endpoint", ["/api/v1/ingest/edi", "/api/v1/ingest/edi/document"])
def test_source_system_is_not_treated_as_tlc_assigner(reference_client, endpoint):
    client, captured, recorded = reference_client

    response = _upload(client, endpoint, {"source": "Original Packing Facility"})

    assert response.status_code == 422
    assert "tlc_source_reference" not in captured[0].kdes
    assert recorded == []
