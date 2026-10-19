"""QA sweep: real ingestion routes, schema boundaries and CSV evidence integrity.

All persistence/auth/provider boundaries use local fakes. The only remaining
strict expected failure is BE-001 (naive timestamps); every other case in this
file is a live assertion, so an unexpected pass or fail needs a code fix, not a
marker change.
"""

from __future__ import annotations

import csv
import io
import math

import pytest
from app import csv_templates as ct
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.webhook_compat import _verify_api_key
from app.webhook_models import EventResult, IngestResponse, WebhookPayload
from app.webhook_router_v2 import routes
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st

HEADER = [
    "traceability_lot_code",
    "product_description",
    "quantity",
    "unit_of_measure",
    "harvest_date",
    "location_name",
    "reference_document",
]
ROW = ["LOT-QA-001", "Kale", "10", "lbs", "2026-04-17", "Farm QA", "REF-QA"]


def _csv(header, row):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(header)
    writer.writerow(row)
    return stream.getvalue()


@pytest.fixture
def csv_upload(monkeypatch):
    captured = []

    async def fake_ingest(payload, **kwargs):
        captured.extend(payload.events)
        return IngestResponse(
            accepted=len(payload.events),
            total=len(payload.events),
            events=[
                EventResult(traceability_lot_code=e.traceability_lot_code, cte_type=e.cte_type.value, status="accepted")
                for e in payload.events
            ],
        )

    monkeypatch.setattr(ct, "ingest_events", fake_ingest)
    app = FastAPI()
    app.include_router(ct.router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="qa-only-key-id", scopes=["*"], tenant_id="11111111-1111-1111-1111-111111111111"
    )
    with TestClient(app, raise_server_exceptions=False) as client:

        def upload(text, cte="harvesting"):
            return client.post(
                "/api/v1/ingest/csv",
                data={"cte_type": cte},
                files={"file": ("qa.csv", text if isinstance(text, bytes) else text.encode(), "text/csv")},
            )

        yield upload, captured


@pytest.fixture
def webhook_client():
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="qa-only-key-id", scopes=["*"], tenant_id="11111111-1111-1111-1111-111111111111"
    )
    for dependency in (
        routes._verify_api_key,
        routes._verify_webhook_signature,
        routes.require_active_subscription,
        routes.get_db_session,
    ):
        app.dependency_overrides[dependency] = lambda: None
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _payload(timestamp):
    return {
        "source": "qa-local",
        "events": [
            {
                "cte_type": "harvesting",
                "traceability_lot_code": "LOT-QA-001",
                "product_description": "Kale",
                "quantity": 10,
                "unit_of_measure": "lbs",
                "location_name": "Farm QA",
                "timestamp": timestamp,
            }
        ],
    }


def test_webhook_invalid_timestamp_is_a_validation_response(webhook_client):
    response = webhook_client.post(
        "/api/v1/webhooks/ingest", json=_payload("invalid"), headers={"Idempotency-Key": "qa-invalid-date"}
    )
    assert response.status_code == 422


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="BE-001: timezone-naive timestamps escape validation as TypeError / HTTP 500",
)
@pytest.mark.parametrize("timestamp", ["2026-04-17T12:00:00", "2026-04-17", "2026-04-17T00:00:00.123456"])
def test_webhook_naive_timestamp_is_a_validation_response(webhook_client, timestamp):
    response = webhook_client.post(
        "/api/v1/webhooks/ingest", json=_payload(timestamp), headers={"Idempotency-Key": "qa-naive-date"}
    )
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("quantity", ["inf", "Infinity", "1e309"])
def test_csv_rejects_nonfinite_output_quantity(csv_upload, quantity):
    upload, captured = csv_upload
    row = list(ROW)
    row[2] = quantity
    response = upload(_csv(HEADER, row))
    assert response.status_code == 400, f"status={response.status_code}; captured={len(captured)}"
    assert not captured


@pytest.mark.parametrize("quantity", ["nan", "inf", "1e309"])
def test_csv_rejects_nonfinite_input_quantity(csv_upload, quantity):
    upload, captured = csv_upload
    header = HEADER + ["input_lot_codes", "input_quantities", "input_units_of_measure"]
    row = ROW + ["INPUT-QA-001", quantity, "lbs"]
    response = upload(_csv(header, row), cte="transformation")
    assert response.status_code == 400, f"status={response.status_code}; captured={len(captured)}"
    assert not captured


@pytest.mark.parametrize("duplicate_header", ["quantity", " Quantity "])
def test_csv_rejects_conflicting_duplicate_headers(csv_upload, duplicate_header):
    upload, captured = csv_upload
    response = upload(_csv(HEADER + [duplicate_header], ROW + ["999"]))
    assert response.status_code == 400, (
        f"status={response.status_code}; ingested_quantities={[e.quantity for e in captured]}"
    )
    assert not captured


@pytest.mark.parametrize("quantity", ["0", "-1", "nan", "not-a-number", ""])
def test_csv_invalid_output_quantity_does_not_reach_persistence(csv_upload, quantity):
    upload, captured = csv_upload
    row = list(ROW)
    row[2] = quantity
    response = upload(_csv(HEADER, row))
    assert response.status_code == 400
    assert not captured


@pytest.mark.parametrize("raw", [b"\xff\xd8\xff\xe0", b"column\nCaf\xe9\n", b"\xff\xfec\x00o\x00l\x00"])
def test_csv_non_utf8_upload_returns_client_error(csv_upload, raw):
    upload, captured = csv_upload
    response = upload(raw)
    if captured:
        pytest.fail("Invalid encoding reached persistence; encoding-error reproduction no longer applies")
    assert response.status_code in (400, 415, 422), response.text


def test_csv_utf8_bom_is_accepted(csv_upload):
    upload, captured = csv_upload
    response = upload(b"\xef\xbb\xbf" + _csv(HEADER, ROW).encode())
    assert response.status_code == 200
    assert len(captured) == 1


@given(st.integers(min_value=1, max_value=1_000_000))
@settings(max_examples=60, derandomize=True, deadline=None, database=None)
def test_positive_finite_csv_quantities_round_trip(quantity):
    row = list(ROW)
    row[2] = str(quantity)
    events, errors, _ = ct.parse_csv_rows(_csv(HEADER, row), "harvesting")
    assert errors == []
    assert len(events) == 1
    assert math.isfinite(events[0].quantity)
    assert events[0].quantity == quantity


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=100))
@settings(max_examples=80, derandomize=True, deadline=None, database=None)
def test_csv_arbitrary_short_input_returns_structured_result(text):
    events, errors, warnings = ct.parse_csv_rows(text, "harvesting")
    assert isinstance(events, list) and isinstance(errors, list) and isinstance(warnings, list)


def test_openapi_batch_contract_matches_runtime_boundaries(webhook_client):
    schema = webhook_client.app.openapi()["components"]["schemas"]["WebhookPayload"]
    assert schema["properties"]["events"]["minItems"] == 1
    assert schema["properties"]["events"]["maxItems"] == 500
    payload = _payload("2026-04-17T12:00:00Z")
    assert len(WebhookPayload(**{**payload, "events": payload["events"] * 500}).events) == 500
    for events in ([], payload["events"] * 501):
        response = webhook_client.post(
            "/api/v1/webhooks/ingest",
            json={**payload, "events": events},
            headers={"Idempotency-Key": "qa-batch-boundary"},
        )
        assert response.status_code == 422
