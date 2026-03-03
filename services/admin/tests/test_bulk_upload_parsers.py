from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.bulk_upload.parsers import parse_incoming_file


def _make_upload_file(filename: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content), headers={"content-type": content_type})


def test_parse_csv_mixed_records():
    csv_content = """record_type,name,street,city,state,postal_code,roles,facility_name,category_id,tlc_code,cte_type,event_time,kde_data
facility,Salinas Packhouse,1200 Abbott St,Salinas,CA,93901,Grower|Packer,,,,,,
ftl_scope,,,,,,,Salinas Packhouse,2,,,,
tlc,,,,,,,Salinas Packhouse,,TLC-2026-SAL-1001,,,
event,,,,,,,Salinas Packhouse,,TLC-2026-SAL-1001,shipping,2026-03-03T12:00:00Z,"{""quantity"": 120, ""unit_of_measure"": ""cases""}"
""".replace("Grower|Packer", "Grower,Packer")

    upload_file = _make_upload_file("supplier.csv", csv_content.encode("utf-8"), "text/csv")
    parsed = asyncio.run(parse_incoming_file(upload_file))

    assert parsed["detected_format"] == "csv"
    assert len(parsed["facilities"]) == 1
    assert len(parsed["ftl_scopes"]) == 1
    assert len(parsed["tlcs"]) == 1
    assert len(parsed["events"]) == 1


def test_parse_json_sections_payload():
    payload = b"""
{
  "facilities": [
    {
      "name": "Salinas Packhouse",
      "street": "1200 Abbott St",
      "city": "Salinas",
      "state": "CA",
      "postal_code": "93901",
      "roles": ["Grower", "Packer"]
    }
  ],
  "ftl_scopes": [
    {"facility_name": "Salinas Packhouse", "category_id": "2"}
  ],
  "tlcs": [
    {"facility_name": "Salinas Packhouse", "tlc_code": "TLC-2026-SAL-1001"}
  ],
  "events": [
    {
      "facility_name": "Salinas Packhouse",
      "tlc_code": "TLC-2026-SAL-1001",
      "cte_type": "shipping",
      "event_time": "2026-03-03T12:00:00Z",
      "kde_data": {"quantity": 120}
    }
  ]
}
"""

    upload_file = _make_upload_file("supplier.json", payload, "application/json")
    parsed = asyncio.run(parse_incoming_file(upload_file))

    assert parsed["detected_format"] == "json"
    assert len(parsed["facilities"]) == 1
    assert len(parsed["ftl_scopes"]) == 1
    assert len(parsed["tlcs"]) == 1
    assert len(parsed["events"]) == 1


def test_parse_json_sections_skips_non_object_rows():
    payload = b"""
{
  "facilities": [
    123,
    {
      "name": "Salinas Packhouse",
      "street": "1200 Abbott St",
      "city": "Salinas",
      "state": "CA",
      "postal_code": "93901",
      "roles": ["Grower", "Packer"]
    }
  ],
  "ftl_scopes": [
    {"facility_name": "Salinas Packhouse", "category_id": "2"}
  ]
}
"""

    upload_file = _make_upload_file("supplier.json", payload, "application/json")
    parsed = asyncio.run(parse_incoming_file(upload_file))

    assert parsed["detected_format"] == "json"
    assert len(parsed["facilities"]) == 1
    assert len(parsed["ftl_scopes"]) == 1
    assert any("facilities section at index 1" in warning for warning in parsed["warnings"])


def test_parse_rejects_oversized_upload(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPPLIER_BULK_UPLOAD_MAX_BYTES", "16")
    upload_file = _make_upload_file("supplier.csv", b"record_type\nfacility\n", "text/csv")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(parse_incoming_file(upload_file))

    assert exc_info.value.status_code == 413
    assert "max size of 16 bytes" in str(exc_info.value.detail)
