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


# ---------------------------------------------------------------------------
# Coverage sweep — remaining uncovered lines of app/sensitech_parser.py
# ---------------------------------------------------------------------------

from app.sensitech_parser import (  # noqa: E402
    TemperatureReading,
    _detect_excursions,
    _normalize_iso_timestamp_or_400,
    _parse_sensitech_csv,
)
from fastapi import HTTPException  # noqa: E402


class TestParseSensitechCsvEdges:
    """Covers lines 80, 90-91, 110, 126-127 in ``_parse_sensitech_csv``."""

    def test_blank_rows_skipped_during_header_detection(self) -> None:
        # Line 80: ``if not row: continue`` while hunting for the header
        # row. csv.reader emits ``[]`` for bare ``\n`` lines — the loop
        # must tolerate them and find the real header below.
        csv_text = (
            "\n"
            "\n"
            "Timestamp, Temperature (°C), Alarm Status, Serial Number\n"
            "2026-02-26T08:00:00Z, 3.1, OK, ST-1\n"
        )
        readings = _parse_sensitech_csv(csv_text)
        assert len(readings) == 1
        assert readings[0].temperature_celsius == 3.1

    def test_missing_header_defaults_to_assumed_schema(self) -> None:
        # Lines 90-91: no ``Timestamp``/``Time``/``Date`` keyword in any
        # row — parser falls through to the default column order.
        csv_text = (
            "2026-02-26T08:00:00Z,4.0,OK,ST-X\n"
            "2026-02-26T08:15:00Z,4.5,OK,ST-X\n"
        )
        readings = _parse_sensitech_csv(csv_text)
        assert len(readings) == 2
        assert readings[0].temperature_celsius == 4.0
        assert readings[1].serial_number == "ST-X"

    def test_row_shorter_than_temp_column_skipped(self) -> None:
        # Line 110: ``if not row or len(row) <= temp_idx: continue``.
        # The row ``["2026-02-26T08:00:00Z"]`` has no temperature column
        # at idx=1 → skipped silently.
        csv_text = (
            "Timestamp, Temperature (°C), Alarm Status, Serial Number\n"
            "2026-02-26T08:00:00Z\n"  # only one cell
            "2026-02-26T08:15:00Z, 5.0, OK, ST-1\n"
        )
        readings = _parse_sensitech_csv(csv_text)
        assert len(readings) == 1
        assert readings[0].timestamp == "2026-02-26T08:15:00Z"

    def test_unparseable_temperature_skipped(self) -> None:
        # Lines 126-127: ``except (ValueError, IndexError): continue`` —
        # a non-numeric temperature field must not blow up the parse.
        csv_text = (
            "Timestamp, Temperature (°C), Alarm Status, Serial Number\n"
            "2026-02-26T08:00:00Z, NOT_A_NUMBER, OK, ST-1\n"
            "2026-02-26T08:15:00Z, 6.2, OK, ST-1\n"
        )
        readings = _parse_sensitech_csv(csv_text)
        assert len(readings) == 1
        assert readings[0].temperature_celsius == 6.2


class TestNormalizeIsoTimestampOrEdges:
    """Covers lines 146 and 167-168 in ``_normalize_iso_timestamp_or_400``.

    These branches aren't reachable through the endpoint because the CSV
    pre-filter in ``_parse_sensitech_csv`` strips empty-first-cell rows
    before the normalizer sees them. So we test the helper directly.
    """

    def test_empty_string_raises_400(self) -> None:
        # Line 146: ``candidate == ""`` branch.
        with pytest.raises(HTTPException) as exc:
            _normalize_iso_timestamp_or_400("")
        assert exc.value.status_code == 400
        assert "empty timestamp" in exc.value.detail

    def test_whitespace_only_raises_400(self) -> None:
        with pytest.raises(HTTPException) as exc:
            _normalize_iso_timestamp_or_400("    ")
        assert exc.value.status_code == 400
        assert "empty timestamp" in exc.value.detail

    def test_dashed_but_unparseable_iso_raises_400(self) -> None:
        # Lines 167-168: candidate has ``>=2`` dashes (so we try to parse
        # it as ISO 8601) but ``datetime.fromisoformat`` raises. Use a
        # clearly invalid month to force the ValueError branch.
        with pytest.raises(HTTPException) as exc:
            _normalize_iso_timestamp_or_400("2026-13-99")
        assert exc.value.status_code == 400
        assert "ISO 8601" in exc.value.detail


class TestDetectExcursions:
    """Covers lines 185 (WARNING severity) and 193 (freeze branch)."""

    def test_warning_severity_for_mild_cold_excursion(self) -> None:
        # Temp above cold_threshold but within +3°C → WARNING (line 185).
        readings = [
            TemperatureReading(
                timestamp="2026-02-26T08:00:00Z",
                temperature_celsius=6.5,  # cold_threshold=5.0 → 1.5 over
                alarm_status="ALARM",
                serial_number="ST-1",
            ),
        ]
        excursions = _detect_excursions(readings, cold_threshold=5.0)
        assert len(excursions) == 1
        assert excursions[0].severity == "WARNING"

    def test_critical_severity_for_severe_cold_excursion(self) -> None:
        # Temp more than +3°C above threshold → CRITICAL.
        readings = [
            TemperatureReading(
                timestamp="2026-02-26T08:00:00Z",
                temperature_celsius=10.0,  # 5°C over → CRITICAL
                alarm_status="ALARM",
            ),
        ]
        excursions = _detect_excursions(readings, cold_threshold=5.0)
        assert excursions[0].severity == "CRITICAL"

    def test_freeze_excursion_detected(self) -> None:
        # Line 193: ``elif r.temperature_celsius < freeze_threshold``.
        readings = [
            TemperatureReading(
                timestamp="2026-02-26T08:00:00Z",
                temperature_celsius=-3.0,  # below freeze_threshold=-1.0
                serial_number="ST-1",
            ),
        ]
        excursions = _detect_excursions(readings, freeze_threshold=-1.0)
        assert len(excursions) == 1
        assert excursions[0].severity == "WARNING"
        assert excursions[0].threshold_celsius == -1.0

    def test_in_range_readings_produce_no_excursions(self) -> None:
        readings = [
            TemperatureReading(timestamp="2026-02-26T08:00:00Z", temperature_celsius=3.0),
            TemperatureReading(timestamp="2026-02-26T08:15:00Z", temperature_celsius=2.0),
        ]
        assert _detect_excursions(readings) == []


class TestCteTypeValidation:
    """Covers line 228 — invalid cte_type returns 400 at the endpoint."""

    def test_invalid_cte_type_rejected(self, client: TestClient) -> None:
        # Anything other than "cooling"/"receiving" → 400 before parsing.
        response = client.post(
            "/api/v1/ingest/iot/sensitech",
            data={
                "traceability_lot_code": "LOT-1342-0001",
                "product_description": "Romaine Lettuce",
                "cte_type": "shipping",  # invalid for IoT import
                "location_name": "Metro DC Cold Room 1",
            },
            files={
                "file": (
                    "temptale.csv",
                    _csv_with_timestamp("2026-02-26T08:00:00Z"),
                    "text/csv",
                ),
            },
        )
        assert response.status_code == 400
        assert "cte_type" in response.json()["detail"]

    def test_receiving_cte_type_accepted(
        self, client: TestClient, captured_payload: dict
    ) -> None:
        # Baseline: "receiving" is the other allowed cte_type.
        response = client.post(
            "/api/v1/ingest/iot/sensitech",
            data={
                "traceability_lot_code": "LOT-1342-0002",
                "product_description": "Romaine Lettuce",
                "cte_type": "receiving",
                "location_name": "Metro DC Cold Room 1",
            },
            files={
                "file": (
                    "temptale.csv",
                    _csv_with_timestamp("2026-02-26T08:00:00Z"),
                    "text/csv",
                ),
            },
        )
        assert response.status_code == 200, response.text
        event = captured_payload["payload"].events[0]
        assert event.cte_type.value == "receiving"
        # receiving_date KDE populated, not cooling_date.
        assert event.kdes["receiving_date"] == "2026-02-26"
