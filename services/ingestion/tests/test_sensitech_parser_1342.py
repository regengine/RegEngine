"""Regression tests for issue #1342.

Background
----------
``import_sensitech`` previously tried to coerce dash-less timestamps into ISO
8601 with a naive concatenation::

    timestamp=readings[0].timestamp
        if readings[0].timestamp.count("-") >= 2
        else f"{readings[0].timestamp}T00:00:00Z"

For a bare time like ``"08:00:00"`` this produced ``"08:00:00T00:00:00Z"``,
which is not valid ISO 8601. Pydantic's ``IngestEvent`` validator then raised
``ValidationError`` mid-request, which surfaced to the caller as a 500.

The fix routes unparseable timestamps through a dedicated 400 Bad Request so
broken CSVs fail predictably rather than looking like a server outage. Compact
``YYYYMMDD`` dates remain supported and are expanded to midnight UTC.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

_services_dir = service_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

pytest.importorskip("fastapi")

import app.sensitech_parser as sensitech_parser_module
from app.sensitech_parser import router as sensitech_router
from app.webhook_compat import _verify_api_key
from app.webhook_models import EventResult, IngestResponse


TEST_TENANT_ID = "00000000-0000-0000-0000-000000001342"


def _csv_with_timestamp(ts: str) -> bytes:
    """Build a minimal 2-row Sensitech CSV using the provided timestamp."""
    return (
        "Timestamp, Temperature (°C), Alarm Status, Serial Number\n"
        f"{ts}, 2.1, OK, ST-12345\n"
        f"{ts}, 2.3, OK, ST-12345\n"
    ).encode("utf-8")


@pytest.fixture()
def captured_payload() -> dict:
    return {}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, captured_payload: dict) -> TestClient:
    app = FastAPI()
    app.include_router(sensitech_router)
    app.dependency_overrides[_verify_api_key] = lambda: None

    async def _fake_ingest_events(payload: Any, x_regengine_api_key: Any = None) -> IngestResponse:
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
                    event_id="evt-sensitech-1342",
                    sha256_hash="hash-1342",
                    chain_hash="chain-1342",
                )
            ],
        )

    monkeypatch.setattr(sensitech_parser_module, "ingest_events", _fake_ingest_events)

    with TestClient(app) as test_client:
        yield test_client


def _post_sensitech(client: TestClient, csv_bytes: bytes) -> Any:
    return client.post(
        "/api/v1/ingest/iot/sensitech",
        data={
            "traceability_lot_code": "LOT-1342-0001",
            "product_description": "Romaine Lettuce",
            "cte_type": "cooling",
            "location_name": "Metro DC Cold Room 1",
        },
        files={"file": ("temptale.csv", csv_bytes, "text/csv")},
    )


def test_timestamp_without_dashes_fallback_is_currently_broken(
    client: TestClient,
) -> None:
    """Bare-time timestamps in Sensitech CSVs must produce a 400, not a 500.

    Before the fix, the dash-count fallback naively appended ``T00:00:00Z`` to
    any timestamp with fewer than two dashes, producing malformed values like
    ``"08:00:00T00:00:00Z"`` that Pydantic rejected — surfacing as a 500.

    After the fix, ``_normalize_iso_timestamp_or_400`` recognizes bare times as
    un-date-like input and raises a 400 with a descriptive message.
    """
    response = _post_sensitech(client, _csv_with_timestamp("08:00:00"))

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "08:00:00" in detail
    assert "ISO 8601" in detail or "YYYYMMDD" in detail


def test_compact_yyyymmdd_timestamp_still_accepted(
    client: TestClient, captured_payload: dict
) -> None:
    """Compact ``YYYYMMDD`` dates must still work — that's why the fallback existed."""
    response = _post_sensitech(client, _csv_with_timestamp("20260226"))

    assert response.status_code == 200, response.text
    payload = captured_payload["payload"]
    event = payload.events[0]
    assert event.timestamp == "2026-02-26T00:00:00Z"
    assert event.kdes["cooling_date"] == "2026-02-26"


def test_standard_iso_timestamp_round_trips_unchanged(
    client: TestClient, captured_payload: dict
) -> None:
    """Baseline: dashed ISO 8601 timestamps pass through without modification.

    Note: we use an explicit-timezone form here. A separate, pre-existing bug
    in ``IngestEvent.validate_timestamp`` trips on naive datetimes ("YYYY-MM-DD
    HH:MM:SS" with no tz) via a TypeError when comparing naive vs. aware — that
    is tracked outside issue #1342.
    """
    response = _post_sensitech(client, _csv_with_timestamp("2026-02-26T08:00:00Z"))

    assert response.status_code == 200, response.text
    payload = captured_payload["payload"]
    event = payload.events[0]
    assert event.timestamp == "2026-02-26T08:00:00Z"
    assert event.kdes["cooling_date"] == "2026-02-26"


def test_empty_timestamp_produces_400(client: TestClient) -> None:
    """Whitespace-only timestamps are also rejected with 400."""
    # The parser skips rows whose first cell is empty, so this CSV has one
    # whitespace-only timestamp that survives as a valid reading.
    csv_bytes = (
        "Timestamp, Temperature (°C), Alarm Status, Serial Number\n"
        "   , 2.1, OK, ST-12345\n"
    ).encode("utf-8")
    response = _post_sensitech(client, csv_bytes)

    # Rows with empty first-cell are filtered out before reaching the
    # timestamp-normalizer, so we land on the "no readings" 400 instead.
    assert response.status_code == 400
