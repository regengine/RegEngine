"""Column aliases must be restricted and every remap must surface a warning.

Regression tests for the audit finding: the bulk-upload alias map used to
silently collapse directional or generic headers (source, destination,
sender_name, timestamp, ...) into canonical event fields, rewriting what
an event means without telling the uploader.
"""

from __future__ import annotations

import asyncio
import io

from app.bulk_upload.parsers import (
    COLUMN_ALIASES,
    RETIRED_AMBIGUOUS_COLUMNS,
    _normalize_row,
    parse_incoming_file,
)
from starlette.datastructures import UploadFile


def _make_upload_file(filename: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=io.BytesIO(content),
        headers={"content-type": content_type},
    )


def test_directional_and_generic_aliases_are_not_mapped():
    for header in [
        "source",
        "destination",
        "origin_facility_name",
        "destination_facility_name",
        "sender_name",
        "receiver_name",
        "timestamp",
    ]:
        assert header not in COLUMN_ALIASES, f"{header} must not be a silent alias"
        assert header in RETIRED_AMBIGUOUS_COLUMNS, f"{header} must be reported, not dropped"


def test_unambiguous_aliases_still_map():
    assert COLUMN_ALIASES["lot_code"] == "tlc_code"
    assert COLUMN_ALIASES["event_type"] == "cte_type"
    assert COLUMN_ALIASES["location_name"] == "facility_name"


def test_retired_headers_are_kept_as_is_with_warning():
    warnings: list[str] = []
    normalized = _normalize_row({"source": "Plant A", "destination": "Plant B"}, warnings)
    assert normalized.get("source") == "Plant A"
    assert normalized.get("destination") == "Plant B"
    assert "facility_name" not in normalized
    assert any("source" in warning and "facility_name" in warning for warning in warnings)
    assert any("destination" in warning and "facility_name" in warning for warning in warnings)


def test_timestamp_header_is_kept_as_is_with_warning():
    warnings: list[str] = []
    normalized = _normalize_row({"timestamp": "2026-03-03T12:00:00Z"}, warnings)
    assert normalized.get("timestamp") == "2026-03-03T12:00:00Z"
    assert normalized.get("event_time") is None
    assert any("timestamp" in warning and "event_time" in warning for warning in warnings)


def test_live_alias_remap_warns():
    warnings: list[str] = []
    normalized = _normalize_row({"lot_code": "LOT-1", "event_type": "shipping"}, warnings)
    assert normalized["tlc_code"] == "LOT-1"
    assert normalized["cte_type"] == "shipping"
    assert any("lot_code" in warning and "tlc_code" in warning for warning in warnings)
    assert any("event_type" in warning and "cte_type" in warning for warning in warnings)


def test_conflicting_values_warn_on_drop():
    warnings: list[str] = []
    normalized = _normalize_row({"facility_name": "Plant A", "location_name": "Plant B"}, warnings)
    assert normalized["facility_name"] == "Plant A"
    assert any("dropped" in warning and "facility_name" in warning for warning in warnings)


def test_warnings_do_not_repeat_per_row():
    warnings: list[str] = []
    _normalize_row({"lot_code": "LOT-1"}, warnings)
    _normalize_row({"lot_code": "LOT-2"}, warnings)
    assert sum("lot_code" in warning for warning in warnings) == 1


def test_csv_upload_surfaces_alias_warnings():
    csv_content = (
        "record_type,location_name,lot_code,event_type,event_datetime\n"
        "event,Salinas Packhouse,LOT-9,shipping,2026-03-03T12:00:00Z\n"
    )
    upload_file = _make_upload_file("supplier.csv", csv_content.encode("utf-8"), "text/csv")
    parsed = asyncio.run(parse_incoming_file(upload_file))
    assert len(parsed["events"]) == 1
    assert parsed["events"][0]["facility_name"] == "Salinas Packhouse"
    assert any("location_name" in warning for warning in parsed["warnings"])
    assert any("lot_code" in warning for warning in parsed["warnings"])


def test_csv_upload_with_source_headers_does_not_invent_facility():
    csv_content = (
        "record_type,source,destination,tlc_code,cte_type,event_time\n"
        "event,Plant A,Plant B,LOT-9,shipping,2026-03-03T12:00:00Z\n"
    )
    upload_file = _make_upload_file("supplier.csv", csv_content.encode("utf-8"), "text/csv")
    parsed = asyncio.run(parse_incoming_file(upload_file))
    assert len(parsed["events"]) == 1
    assert parsed["events"][0]["facility_name"] == ""
    assert any("source" in warning for warning in parsed["warnings"])
