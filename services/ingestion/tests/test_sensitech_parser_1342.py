"""
Regression coverage for ``app/sensitech_parser.py``.

Sensitech TempTale CSV → FSMA 204 Cooling/Receiving CTE events.
Temperature excursions feed directly into recall determinations,
so parser regressions can silently suppress safety alerts or fabricate
spurious ones. These tests pin:

* header auto-detection (timestamp/time/date + temp/°C/celsius/reading
  column aliases)
* default-column fallback when no header is found
* comment/blank/unparseable-row skipping
* °C / °F suffix stripping
* excursion detection — cold-threshold WARNING/CRITICAL boundary and
  freeze-threshold WARNING
* /sensitech endpoint wiring — validation, upload, CTE event
  construction, ingestion delegation

Tracks GitHub issue #1342.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import sensitech_parser
from app.sensitech_parser import (
    SensitechImportResponse,
    TemperatureExcursion,
    TemperatureReading,
    _detect_excursions,
    _parse_sensitech_csv,
    router,
)
from app.webhook_compat import _verify_api_key
from app.webhook_models import IngestResponse


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def client(monkeypatch):
    """Router-only app with auth bypassed and ingest_events stubbed."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None

    async def _fake_ingest(payload, x_regengine_api_key=None):
        # Capture for assertion
        _fake_ingest.last_payload = payload
        return IngestResponse(accepted=len(payload.events), rejected=0, errors=[])

    _fake_ingest.last_payload = None
    monkeypatch.setattr(sensitech_parser, "ingest_events", _fake_ingest)

    with TestClient(app) as c:
        c._fake_ingest = _fake_ingest
        yield c


# ===========================================================================
# _parse_sensitech_csv — header detection
# ===========================================================================


class TestParseCsvHeaderDetection:

    def test_standard_temptale_header(self):
        csv = (
            "Timestamp, Temperature (°C), Alarm Status, Serial Number\n"
            "2026-02-26 08:00:00,2.1,OK,ST-12345\n"
            "2026-02-26 08:15:00,2.3,OK,ST-12345\n"
        )
        readings = _parse_sensitech_csv(csv)
        assert len(readings) == 2
        assert readings[0].timestamp == "2026-02-26 08:00:00"
        assert readings[0].temperature_celsius == 2.1
        assert readings[0].alarm_status == "OK"
        assert readings[0].serial_number == "ST-12345"

    def test_time_keyword_header_recognised(self):
        csv = "Time,Temp\n2026-02-26T08:00:00Z,5.0\n"
        readings = _parse_sensitech_csv(csv)
        assert len(readings) == 1
        assert readings[0].temperature_celsius == 5.0

    def test_date_keyword_header_recognised(self):
        csv = "Date,Reading\n2026-02-26,3.3\n"
        readings = _parse_sensitech_csv(csv)
        assert len(readings) == 1
        assert readings[0].temperature_celsius == 3.3

    def test_no_header_uses_default_columns(self):
        """Straight data rows — parser falls back to positional defaults.

        Default column order is [timestamp, temperature, alarm, serial].
        """
        csv = "2026-02-26T08:00:00Z,4.1,OK,ST-1\n"
        readings = _parse_sensitech_csv(csv)
        assert len(readings) == 1
        assert readings[0].temperature_celsius == 4.1
        assert readings[0].alarm_status == "OK"
        assert readings[0].serial_number == "ST-1"

    def test_header_device_keyword_recognised(self):
        csv = "Timestamp,Temp,Alert,Device\n2026-02-26T08:00:00Z,5.0,OK,DEV-99\n"
        readings = _parse_sensitech_csv(csv)
        assert readings[0].serial_number == "DEV-99"

    def test_header_sensor_keyword_recognised(self):
        csv = "Timestamp,Celsius,Status,Sensor\n2026-02-26T08:00:00Z,5.0,OK,SNSR-1\n"
        readings = _parse_sensitech_csv(csv)
        assert readings[0].serial_number == "SNSR-1"

    def test_header_alarm_alias_alert(self):
        csv = "Timestamp,Temp,Alert\n2026-02-26T08:00:00Z,5.0,ALARM\n"
        readings = _parse_sensitech_csv(csv)
        assert readings[0].alarm_status == "ALARM"

    def test_header_temp_degree_symbol(self):
        csv = "Timestamp,°C\n2026-02-26T08:00:00Z,5.0\n"
        readings = _parse_sensitech_csv(csv)
        assert readings[0].temperature_celsius == 5.0

    def test_blank_row_before_header_is_skipped(self):
        """The header-detection loop skips empty rows (line 79-80)."""
        csv = "\nTimestamp,Temp\n2026-02-26T08:00:00Z,4.2\n"
        readings = _parse_sensitech_csv(csv)
        assert len(readings) == 1
        assert readings[0].temperature_celsius == 4.2


# ===========================================================================
# _parse_sensitech_csv — value parsing / coercion
# ===========================================================================


class TestParseCsvValueParsing:

    def test_celsius_suffix_stripped(self):
        csv = "Timestamp,Temp\n2026-02-26T08:00:00Z,5.5°C\n"
        readings = _parse_sensitech_csv(csv)
        assert readings[0].temperature_celsius == 5.5

    def test_fahrenheit_suffix_stripped(self):
        """°F suffix is stripped — not converted. The field is named
        ``temperature_celsius`` so a value that arrives with °F attached
        is treated as *already in Celsius* after the suffix is dropped.
        This is a quirk of the source code — documented in the regression
        so a future refactor doesn't change behavior silently."""
        csv = "Timestamp,Temp\n2026-02-26T08:00:00Z,5.5°F\n"
        readings = _parse_sensitech_csv(csv)
        assert readings[0].temperature_celsius == 5.5

    def test_unparseable_temperature_row_skipped(self):
        csv = (
            "Timestamp,Temp\n"
            "2026-02-26T08:00:00Z,NOTANUMBER\n"
            "2026-02-26T08:15:00Z,5.0\n"
        )
        readings = _parse_sensitech_csv(csv)
        assert len(readings) == 1
        assert readings[0].temperature_celsius == 5.0

    def test_short_row_skipped(self):
        """Row with fewer columns than temp_idx — skipped."""
        csv = "Timestamp,Temp\n2026-02-26T08:00:00Z\n2026-02-26T08:15:00Z,5.0\n"
        readings = _parse_sensitech_csv(csv)
        assert len(readings) == 1

    def test_empty_first_cell_row_skipped(self):
        csv = "Timestamp,Temp\n2026-02-26T08:00:00Z,5.0\n   ,3.0\n"
        readings = _parse_sensitech_csv(csv)
        assert len(readings) == 1

    def test_comment_row_skipped(self):
        csv = (
            "Timestamp,Temp\n"
            "# this is a comment\n"
            "2026-02-26T08:00:00Z,5.0\n"
        )
        readings = _parse_sensitech_csv(csv)
        assert len(readings) == 1

    def test_missing_optional_alarm_defaults_to_ok(self):
        """No alarm column → defaults to 'OK'."""
        csv = "Timestamp,Temp\n2026-02-26T08:00:00Z,5.0\n"
        readings = _parse_sensitech_csv(csv)
        assert readings[0].alarm_status == "OK"

    def test_missing_optional_serial_defaults_to_none(self):
        csv = "Timestamp,Temp\n2026-02-26T08:00:00Z,5.0\n"
        readings = _parse_sensitech_csv(csv)
        assert readings[0].serial_number is None

    def test_empty_content_returns_empty_list(self):
        assert _parse_sensitech_csv("") == []

    def test_header_only_returns_empty_list(self):
        assert _parse_sensitech_csv("Timestamp,Temp\n") == []

    def test_blank_rows_between_data_skipped(self):
        csv = (
            "Timestamp,Temp\n"
            "2026-02-26T08:00:00Z,5.0\n"
            "\n"
            "2026-02-26T08:15:00Z,6.0\n"
        )
        readings = _parse_sensitech_csv(csv)
        assert len(readings) == 2


# ===========================================================================
# _detect_excursions — threshold semantics
# ===========================================================================


class TestDetectExcursions:

    @staticmethod
    def _r(temp):
        return TemperatureReading(
            timestamp="2026-02-26T08:00:00Z",
            temperature_celsius=temp,
            alarm_status="OK",
            serial_number="SER-1",
        )

    def test_no_excursions_when_all_in_range(self):
        readings = [self._r(1.0), self._r(2.0), self._r(3.0), self._r(4.5)]
        assert _detect_excursions(readings) == []

    def test_exactly_at_cold_threshold_is_safe(self):
        """Strict greater-than for hot excursion."""
        readings = [self._r(5.0)]
        assert _detect_excursions(readings, cold_threshold=5.0) == []

    def test_one_over_cold_threshold_is_warning(self):
        """5.0 is safe; 5.1 is WARNING; 8.1 is CRITICAL."""
        readings = [self._r(5.1)]
        exc = _detect_excursions(readings, cold_threshold=5.0)
        assert len(exc) == 1
        assert exc[0].severity == "WARNING"
        assert exc[0].threshold_celsius == 5.0

    def test_three_over_cold_threshold_is_critical(self):
        readings = [self._r(8.1)]
        exc = _detect_excursions(readings, cold_threshold=5.0)
        assert len(exc) == 1
        assert exc[0].severity == "CRITICAL"

    def test_exactly_three_over_is_warning(self):
        """Strict greater-than on the CRITICAL boundary.

        threshold+3 == 8.0 is WARNING; 8.01 is CRITICAL.
        """
        readings = [self._r(8.0)]
        exc = _detect_excursions(readings, cold_threshold=5.0)
        assert exc[0].severity == "WARNING"

    def test_freeze_threshold_triggers_cold_warning(self):
        readings = [self._r(-1.5)]
        exc = _detect_excursions(readings, freeze_threshold=-1.0)
        assert len(exc) == 1
        assert exc[0].severity == "WARNING"
        assert exc[0].threshold_celsius == -1.0

    def test_exactly_at_freeze_threshold_is_safe(self):
        readings = [self._r(-1.0)]
        exc = _detect_excursions(readings, freeze_threshold=-1.0)
        assert exc == []

    def test_mixed_hot_and_cold_excursions(self):
        readings = [self._r(-2.0), self._r(3.0), self._r(7.0), self._r(15.0)]
        exc = _detect_excursions(readings)
        # -2 → cold, 3 → safe, 7 → WARNING, 15 → CRITICAL
        assert len(exc) == 3
        assert exc[0].temperature_celsius == -2.0  # freeze
        assert exc[1].temperature_celsius == 7.0  # WARNING
        assert exc[2].temperature_celsius == 15.0  # CRITICAL

    def test_excursion_carries_serial_number(self):
        readings = [self._r(15.0)]
        exc = _detect_excursions(readings)
        assert exc[0].serial_number == "SER-1"


# ===========================================================================
# /sensitech endpoint — validation + happy path
# ===========================================================================


def _form(cte_type="cooling", **overrides):
    data = {
        "traceability_lot_code": "ROM-0226-F1-001",
        "product_description": "Romaine",
        "cte_type": cte_type,
        "location_name": "Salinas CA Cold Room",
        "cold_threshold": "5.0",
    }
    data.update(overrides)
    return data


def _good_csv():
    return (
        "Timestamp,Temperature (°C),Alarm Status,Serial Number\n"
        "2026-02-26T08:00:00Z,2.1,OK,ST-1\n"
        "2026-02-26T08:15:00Z,2.3,OK,ST-1\n"
        "2026-02-26T08:30:00Z,6.8,ALARM,ST-1\n"
    )


class TestSensitechEndpointValidation:

    def test_invalid_cte_type_rejected(self, client):
        resp = client.post(
            "/api/v1/ingest/iot/sensitech",
            data=_form(cte_type="shipping"),
            files={"file": ("temp.csv", _good_csv(), "text/csv")},
        )
        assert resp.status_code == 400
        assert "cte_type" in resp.json()["detail"]

    def test_empty_csv_rejected_400(self, client):
        resp = client.post(
            "/api/v1/ingest/iot/sensitech",
            data=_form(),
            files={"file": ("temp.csv", "", "text/csv")},
        )
        assert resp.status_code == 400
        assert "No temperature readings" in resp.json()["detail"]

    def test_header_only_csv_rejected_400(self, client):
        resp = client.post(
            "/api/v1/ingest/iot/sensitech",
            data=_form(),
            files={"file": ("temp.csv", "Timestamp,Temp\n", "text/csv")},
        )
        assert resp.status_code == 400


class TestSensitechEndpointHappyPath:

    def test_happy_path_returns_summary(self, client):
        resp = client.post(
            "/api/v1/ingest/iot/sensitech",
            data=_form(),
            files={"file": ("temp.csv", _good_csv(), "text/csv")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["readings_parsed"] == 3
        assert body["events_created"] == 1
        # 6.8 > 5.0 → WARNING excursion.
        assert body["excursions_detected"] == 1
        assert body["min_temperature"] == 2.1
        assert body["max_temperature"] == 6.8
        assert body["avg_temperature"] == round((2.1 + 2.3 + 6.8) / 3, 2)

    def test_happy_path_computes_duration(self, client):
        """30-min window → 0.5 hour."""
        resp = client.post(
            "/api/v1/ingest/iot/sensitech",
            data=_form(),
            files={"file": ("temp.csv", _good_csv(), "text/csv")},
        )
        assert resp.json()["duration_hours"] == 0.5

    def test_duration_is_none_for_non_iso_last_timestamp(self, client):
        """Source catches ValueError and leaves duration_hours at None.

        First timestamp must be valid ISO (it flows into the IngestEvent
        construction — Pydantic enforces ISO 8601 there) — but the LAST
        timestamp is only used for duration, so we can send a dashed-but-
        not-ISO string and force the ``fromisoformat`` ValueError path."""
        csv = (
            "Timestamp,Temp\n"
            "2026-02-26T08:00:00Z,5.0\n"
            "2026-02-abc,6.0\n"
        )
        resp = client.post(
            "/api/v1/ingest/iot/sensitech",
            data=_form(),
            files={"file": ("temp.csv", csv, "text/csv")},
        )
        assert resp.status_code == 200
        assert resp.json()["duration_hours"] is None

    def test_utf8_bom_is_tolerated(self, client):
        """UploadFile.read() returns bytes; endpoint decodes with utf-8-sig."""
        body = "\ufeff" + _good_csv()
        resp = client.post(
            "/api/v1/ingest/iot/sensitech",
            data=_form(),
            files={"file": ("temp.csv", body.encode("utf-8"), "text/csv")},
        )
        assert resp.status_code == 200
        assert resp.json()["readings_parsed"] == 3

    def test_cooling_cte_type_passes_through(self, client):
        resp = client.post(
            "/api/v1/ingest/iot/sensitech",
            data=_form(cte_type="cooling"),
            files={"file": ("temp.csv", _good_csv(), "text/csv")},
        )
        assert resp.status_code == 200
        payload = client._fake_ingest.last_payload
        assert payload.events[0].cte_type.value == "cooling"

    def test_receiving_cte_type_passes_through(self, client):
        resp = client.post(
            "/api/v1/ingest/iot/sensitech",
            data=_form(cte_type="receiving"),
            files={"file": ("temp.csv", _good_csv(), "text/csv")},
        )
        assert resp.status_code == 200
        payload = client._fake_ingest.last_payload
        assert payload.events[0].cte_type.value == "receiving"

    def test_cte_type_case_insensitive(self, client):
        resp = client.post(
            "/api/v1/ingest/iot/sensitech",
            data=_form(cte_type="COOLING"),
            files={"file": ("temp.csv", _good_csv(), "text/csv")},
        )
        assert resp.status_code == 200

    def test_event_kdes_carry_temperature_stats(self, client):
        resp = client.post(
            "/api/v1/ingest/iot/sensitech",
            data=_form(),
            files={"file": ("temp.csv", _good_csv(), "text/csv")},
        )
        assert resp.status_code == 200
        event = client._fake_ingest.last_payload.events[0]
        kdes = event.kdes
        assert kdes["temperature_min_celsius"] == 2.1
        assert kdes["temperature_max_celsius"] == 6.8
        assert kdes["temperature_readings_count"] == 3
        assert kdes["temperature_excursions_count"] == 1
        assert kdes["data_source"] == "sensitech_temptale"
        assert kdes["sensor_serial"] == "ST-1"

    def test_event_has_cte_specific_date_kde(self, client):
        """Cooling → ``cooling_date``; receiving → ``receiving_date``."""
        # cooling
        resp = client.post(
            "/api/v1/ingest/iot/sensitech",
            data=_form(cte_type="cooling"),
            files={"file": ("temp.csv", _good_csv(), "text/csv")},
        )
        kdes = client._fake_ingest.last_payload.events[0].kdes
        assert "cooling_date" in kdes
        assert kdes["cooling_date"].startswith("2026-02-26")
        # receiving
        resp = client.post(
            "/api/v1/ingest/iot/sensitech",
            data=_form(cte_type="receiving"),
            files={"file": ("temp.csv", _good_csv(), "text/csv")},
        )
        kdes = client._fake_ingest.last_payload.events[0].kdes
        assert "receiving_date" in kdes

    def test_quantity_equals_reading_count(self, client):
        """Each reading counts as 1 unit-of-measure=readings."""
        resp = client.post(
            "/api/v1/ingest/iot/sensitech",
            data=_form(),
            files={"file": ("temp.csv", _good_csv(), "text/csv")},
        )
        event = client._fake_ingest.last_payload.events[0]
        assert event.quantity == 3
        assert event.unit_of_measure == "readings"

    def test_location_name_and_gln_passed_through(self, client):
        resp = client.post(
            "/api/v1/ingest/iot/sensitech",
            data=_form(
                location_name="Yuma AZ Cold Room",
                location_gln="0123456789012",
            ),
            files={"file": ("temp.csv", _good_csv(), "text/csv")},
        )
        event = client._fake_ingest.last_payload.events[0]
        assert event.location_name == "Yuma AZ Cold Room"
        assert event.location_gln == "0123456789012"

    def test_custom_cold_threshold_changes_excursion_count(self, client):
        """Raise the threshold so 6.8 is no longer an excursion."""
        resp = client.post(
            "/api/v1/ingest/iot/sensitech",
            data=_form(cold_threshold="10.0"),
            files={"file": ("temp.csv", _good_csv(), "text/csv")},
        )
        assert resp.json()["excursions_detected"] == 0

    def test_timestamp_without_dashes_fallback_is_currently_broken(self, monkeypatch):
        """Document a latent bug on line 228.

        When ``readings[0].timestamp.count('-') < 2`` the endpoint appends
        ``T00:00:00Z`` to try to synthesize an ISO 8601 value. For a
        bare time like ``"08:00:00"`` this produces ``"08:00:00T00:00:00Z"``
        — IngestEvent's validator rejects that and the endpoint raises
        ValidationError. The fallback appears to be intended for
        ``YYYYMMDD`` inputs but never handled the bare-time case.

        Test documents the current behavior (server-side ValidationError).
        See the spawned follow-up task for the fix.
        """
        from pydantic import ValidationError
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[_verify_api_key] = lambda: None

        async def _fake_ingest(payload, x_regengine_api_key=None):
            return IngestResponse(accepted=len(payload.events), rejected=0, errors=[])

        monkeypatch.setattr(sensitech_parser, "ingest_events", _fake_ingest)

        # raise_server_exceptions=False makes TestClient convert uncaught
        # exceptions to 500 responses instead of re-raising.
        with TestClient(app, raise_server_exceptions=False) as c:
            csv = (
                "Timestamp,Temp\n"
                "08:00:00,5.0\n"
                "08:15:00,5.5\n"
            )
            resp = c.post(
                "/api/v1/ingest/iot/sensitech",
                data=_form(),
                files={"file": ("temp.csv", csv, "text/csv")},
            )
            # Currently 500 — IngestEvent validator rejects synthesized timestamp.
            assert resp.status_code == 500


# ===========================================================================
# Pydantic surface
# ===========================================================================


class TestPydanticModels:

    def test_temperature_reading_defaults(self):
        r = TemperatureReading(
            timestamp="2026-02-26T08:00:00Z",
            temperature_celsius=5.0,
        )
        assert r.alarm_status == "OK"
        assert r.serial_number is None

    def test_temperature_excursion_defaults(self):
        e = TemperatureExcursion(
            timestamp="2026-02-26T08:00:00Z",
            temperature_celsius=7.0,
            threshold_celsius=5.0,
        )
        assert e.severity == "WARNING"

    def test_sensitech_response_defaults(self):
        r = SensitechImportResponse()
        assert r.readings_parsed == 0
        assert r.events_created == 0
        assert r.excursions_detected == 0
        assert r.excursions == []
        assert r.ingestion_result is None
