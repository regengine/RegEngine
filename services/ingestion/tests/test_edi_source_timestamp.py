"""EDI event identity must use source time, never the import wall clock."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.edi_ingestion import router, routes as edi_routes
from app.edi_ingestion.extractors import _extract_fields_for_set
from app.edi_ingestion.parser import _parse_x12_segments
from app.edi_ingestion.routes import _build_ingest_event_for_set
from app.edi_ingestion.utils import _ship_timestamp_and_date
from app.webhook_models import IngestEvent
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from shared.canonical_event import normalize_webhook_event

CORPUS = Path(__file__).parent / "fixtures" / "edi_corpus"
TENANT_ID = "00000000-0000-0000-0000-000000000123"
TLC = "00012345678901-LOT001"


@pytest.mark.parametrize(
    ("source_date", "source_time", "timestamp", "date"),
    [
        ("20200310", "1200", "2020-03-10T12:00:00+00:00", "2020-03-10"),
        ("20260310", "1200", "2026-03-10T12:00:00+00:00", "2026-03-10"),
        ("260310", "1200", "2026-03-10T12:00:00+00:00", "2026-03-10"),
        ("20200310", None, "2020-03-10T00:00:00+00:00", "2020-03-10"),
        ("20200310", "", "2020-03-10T00:00:00+00:00", "2020-03-10"),
    ],
)
def test_timestamp_and_event_date_preserve_source_fact(source_date, source_time, timestamp, date):
    assert _ship_timestamp_and_date(source_date, source_time) == (timestamp, date)


def test_current_source_date_keeps_its_supplied_time():
    today = datetime.now(timezone.utc).date()

    timestamp, date = _ship_timestamp_and_date(today.strftime("%Y%m%d"), "1200")

    assert timestamp == today.isoformat() + "T12:00:00+00:00"
    assert date == today.isoformat()


@pytest.mark.parametrize("source_date", [None, "", "  ", "not-a-date", "20261310"])
def test_missing_or_invalid_source_date_rejects_instead_of_using_now(source_date):
    with pytest.raises(HTTPException) as exc:
        _ship_timestamp_and_date(source_date, "1200")

    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "invalid_edi_date"


@pytest.mark.parametrize("source_time", ["2500", "1260"])
def test_invalid_source_time_remains_rejected(source_time):
    with pytest.raises(HTTPException) as exc:
        _ship_timestamp_and_date("20200310", source_time)

    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "invalid_edi_time"


@pytest.mark.parametrize(
    ("fixture", "transaction_set", "timestamp"),
    [
        ("asn_856", "856", "2026-03-10T12:00:00+00:00"),
        ("asn_856_multi_line", "856", "2026-03-10T12:00:00+00:00"),
        ("po_850", "850", "2026-03-09T00:00:00+00:00"),
        ("invoice_810", "810", "2026-03-11T00:00:00+00:00"),
        ("receiving_861", "861", "2026-03-12T00:00:00+00:00"),
    ],
)
def test_reimported_source_retains_timestamp_and_canonical_identity(fixture, transaction_set, timestamp):
    segments = _parse_x12_segments((CORPUS / f"{fixture}.edi").read_text())
    extracted = _extract_fields_for_set(transaction_set, segments)
    canonical = []

    for _ in range(2):
        event = _build_ingest_event_for_set(transaction_set, extracted, TLC, None, None, None, None, segments)
        assert event.timestamp == timestamp
        canonical.append(normalize_webhook_event(event, TENANT_ID, source="edi"))

    assert canonical[0].idempotency_key == canonical[1].idempotency_key


def test_existing_webhook_model_still_rejects_future_source_timestamp():
    with pytest.raises(ValidationError, match="more than 24 hours in the future"):
        IngestEvent(
            cte_type="shipping",
            traceability_lot_code=TLC,
            product_description="Romaine lettuce",
            timestamp="9999-01-01T12:00:00+00:00",
        )


def test_future_source_timestamp_rejects_without_becoming_now():
    with pytest.raises(HTTPException) as exc:
        _ship_timestamp_and_date("99990101", "1200")

    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "invalid_edi_date"


@pytest.mark.parametrize("path", ["/api/v1/ingest/edi", "/api/v1/ingest/edi/document"])
def test_future_source_date_returns_safe_http_error_without_ingesting(monkeypatch, path):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="synthetic-test", scopes=["*"], auth_mode="test", tenant_id=TENANT_ID
    )
    ingested = []
    receipts = []

    async def ingest(payload, **kwargs):
        ingested.append(payload)
        raise AssertionError("future EDI must not reach canonical ingestion")

    monkeypatch.setattr(edi_routes, "ingest_events", ingest)
    monkeypatch.setattr(edi_routes, "check_interchange", lambda *args, **kwargs: (False, None))
    monkeypatch.setattr(edi_routes, "record_interchange", lambda **kwargs: receipts.append(kwargs))
    raw = (CORPUS / "asn_856.edi").read_bytes().replace(b"BSN*00*ASN-12345*20260310*", b"BSN*00*ASN-12345*99990101*")
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            path,
            data={"traceability_lot_code": TLC, "tenant_id": TENANT_ID},
            files={"file": ("future.edi", raw, "application/edi-x12")},
            headers={"X-Partner-ID": "WALMART"},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_edi_date"
    assert ingested == []
    assert receipts == []
