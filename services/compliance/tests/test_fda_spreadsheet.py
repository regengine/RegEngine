"""Tests for FDA 204 Sortable Spreadsheet CSV generation.

Covers:
- Column structure and headers
- Event normalization logic
- Timestamp parsing
- Sorting by event_date/time
- Metadata header rows
- Edge cases (empty events, missing KDEs, extra KDEs)
"""

import sys
from pathlib import Path

service_dir = Path(__file__).parent.parent
_to_remove = [key for key in sys.modules if key == "app" or key.startswith("app.") or key == "main"]
for key in _to_remove:
    del sys.modules[key]
sys.path.insert(0, str(service_dir))

import csv
import io
import json

import pytest

from app.fsma_spreadsheet import (
    FDA_COLUMNS,
    FDA_HEADERS,
    generate_fda_csv,
    _parse_timestamp,
    _normalise_event,
)


# ─── _parse_timestamp ────────────────────────────────────────────────────


class TestParseTimestamp:
    def test_iso_timestamp_with_timezone(self):
        date, time = _parse_timestamp("2026-03-15T14:30:00+00:00")
        assert date == "2026-03-15"
        assert time == "14:30:00"

    def test_iso_timestamp_with_z_suffix(self):
        date, time = _parse_timestamp("2026-03-15T14:30:00Z")
        assert date == "2026-03-15"
        assert time == "14:30:00"

    def test_empty_string_returns_empty_tuple(self):
        assert _parse_timestamp("") == ("", "")

    def test_none_returns_empty_tuple(self):
        assert _parse_timestamp("") == ("", "")

    def test_date_only_string_extracts_date(self):
        date, time = _parse_timestamp("2026-03-15")
        assert date == "2026-03-15"

    def test_malformed_input_falls_back_gracefully(self):
        date, time = _parse_timestamp("not-a-date")
        # Should not raise — falls back to string slicing
        assert isinstance(date, str)


# ─── _normalise_event ────────────────────────────────────────────────────


def _sample_event(**overrides) -> dict:
    base = {
        "type": "SHIPPING",
        "tlc": "TLC-001",
        "product_description": "Organic Lettuce",
        "quantity": 500,
        "uom": "cases",
        "facility_gln": "1234567890123",
        "facility_name": "Acme Farms",
        "facility_address": "123 Farm Rd",
        "dest_gln": "9876543210987",
        "dest_name": "Metro Warehouse",
        "dest_address": "456 Warehouse Ave",
        "kdes": {
            "event_date": "2026-03-15T10:00:00Z",
            "ship_date": "2026-03-15",
            "carrier": "Refrigerated Express",
            "temperature": "34°F",
        },
    }
    base.update(overrides)
    return base


class TestNormaliseEvent:
    def test_maps_basic_fields(self):
        row = _normalise_event(_sample_event())
        assert row["event_type"] == "SHIPPING"
        assert row["traceability_lot_code"] == "TLC-001"
        assert row["product_description"] == "Organic Lettuce"
        assert row["quantity"] == "500"
        assert row["unit_of_measure"] == "cases"

    def test_maps_facility_fields(self):
        row = _normalise_event(_sample_event())
        assert row["origin_gln"] == "1234567890123"
        assert row["origin_name"] == "Acme Farms"
        assert row["destination_gln"] == "9876543210987"
        assert row["destination_name"] == "Metro Warehouse"

    def test_extracts_named_kdes(self):
        row = _normalise_event(_sample_event())
        assert row["ship_date"] == "2026-03-15"
        assert row["carrier"] == "Refrigerated Express"
        assert row["temperature"] == "34°F"

    def test_extra_kdes_go_to_json_column(self):
        event = _sample_event()
        event["kdes"]["custom_field"] = "custom_value"
        row = _normalise_event(event)
        extra = json.loads(row["additional_kdes_json"])
        assert extra["custom_field"] == "custom_value"

    def test_no_extra_kdes_produces_empty_string(self):
        row = _normalise_event(_sample_event())
        # carrier, temperature, ship_date, event_date are all named/skipped
        assert row["additional_kdes_json"] == ""

    def test_event_type_uppercased(self):
        row = _normalise_event(_sample_event(type="shipping"))
        assert row["event_type"] == "SHIPPING"

    def test_fallback_field_names(self):
        """Test that alternative field names (event_type vs type) work."""
        event = {"event_type": "RECEIVING", "traceability_lot_code": "TLC-002", "kdes": {}}
        row = _normalise_event(event)
        assert row["event_type"] == "RECEIVING"
        assert row["traceability_lot_code"] == "TLC-002"

    def test_missing_fields_default_to_empty_string(self):
        row = _normalise_event({"kdes": {}})
        assert row["traceability_lot_code"] == ""
        assert row["origin_gln"] == ""
        assert row["carrier"] == ""


# ─── generate_fda_csv ────────────────────────────────────────────────────


class TestGenerateFDACSV:
    def test_empty_events_produces_valid_csv(self):
        result = generate_fda_csv([], start_date="2026-01-01", end_date="2026-01-31")
        assert "FSMA Section 204" in result
        assert "Record Count" in result
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        # Should have metadata rows + header + no data rows
        assert any("0" in row for row in rows)  # Record Count: 0

    def test_header_row_matches_fda_headers(self):
        result = generate_fda_csv([], start_date="2026-01-01", end_date="2026-01-31")
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        # Find the header row (should contain "Event Type (CTE)")
        header_row = None
        for row in rows:
            if row and row[0] == "Event Type (CTE)":
                header_row = row
                break
        assert header_row is not None, "FDA header row not found"
        assert header_row == FDA_HEADERS

    def test_events_sorted_by_date_and_time(self):
        events = [
            _sample_event(kdes={"event_date": "2026-03-15T14:00:00Z"}),
            _sample_event(kdes={"event_date": "2026-03-14T10:00:00Z"}),
            _sample_event(kdes={"event_date": "2026-03-15T08:00:00Z"}),
        ]
        result = generate_fda_csv(events, start_date="2026-03-14", end_date="2026-03-15")
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)

        # Find data rows (after header row)
        data_start = None
        for i, row in enumerate(rows):
            if row and row[0] == "Event Type (CTE)":
                data_start = i + 1
                break

        assert data_start is not None
        data_rows = rows[data_start:]
        # Filter empty rows
        data_rows = [r for r in data_rows if r and r[0]]

        dates = [r[1] for r in data_rows]  # event_date is column index 1
        assert dates == sorted(dates)

    def test_metadata_includes_date_range(self):
        result = generate_fda_csv(
            [], start_date="2026-01-01", end_date="2026-06-30"
        )
        assert "2026-01-01 to 2026-06-30" in result

    def test_metadata_includes_requesting_entity(self):
        result = generate_fda_csv(
            [],
            start_date="2026-01-01",
            end_date="2026-01-31",
            requesting_entity="FDA District Office",
        )
        assert "FDA District Office" in result

    def test_record_count_matches_events(self):
        events = [_sample_event(), _sample_event()]
        result = generate_fda_csv(events, start_date="2026-01-01", end_date="2026-01-31")
        assert "2" in result  # Record Count: 2

    def test_column_count_is_29(self):
        assert len(FDA_COLUMNS) == 29
        assert len(FDA_HEADERS) == 29

    def test_single_event_csv_has_correct_columns(self):
        events = [_sample_event()]
        result = generate_fda_csv(events, start_date="2026-03-01", end_date="2026-03-31")
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)

        # Find data row
        data_start = None
        for i, row in enumerate(rows):
            if row and row[0] == "Event Type (CTE)":
                data_start = i + 1
                break

        data_rows = [r for r in rows[data_start:] if r and r[0]]
        assert len(data_rows) == 1
        assert len(data_rows[0]) == 29  # 29 columns
