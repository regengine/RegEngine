from __future__ import annotations

import asyncio
import io

import pytest
from app.bulk_upload.parsers import _parse_pdf_matrix_table, parse_incoming_file
from fastapi import HTTPException
from starlette.datastructures import UploadFile


def _make_upload_file(filename: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=io.BytesIO(content),
        headers={"content-type": content_type},
    )


def test_parse_onboarding_csv_template_keeps_product_unit_and_destination():
    """The signed-out CSV template is one event row with product_name/unit
    and separate origin/destination columns. Those must survive parse so
    FDA export and the canonical bridge see the values the user typed."""
    csv_content = (
        "event_type,product_name,lot_number,event_datetime,product_code,quantity,unit,"
        "origin_facility_code,origin_facility_name,destination_facility_code,destination_facility_name\n"
        "shipping,Baby Spinach,TLC-2026-SAL-1001,2026-03-03T12:00:00Z,SPIN-24,120,cases,"
        "GLN-ORIGIN,Salinas Packhouse,GLN-DEST,Retail DC\n"
    )
    upload_file = _make_upload_file("regengine-bulk-upload-template.csv", csv_content.encode("utf-8"), "text/csv")
    parsed = asyncio.run(parse_incoming_file(upload_file))

    assert parsed["detected_format"] == "csv"
    assert len(parsed["events"]) == 1
    event = parsed["events"][0]
    assert event["cte_type"] == "shipping"
    assert event["tlc_code"] == "TLC-2026-SAL-1001"
    assert event["facility_name"] == "Salinas Packhouse"
    kde = event["kde_data"]
    assert kde["product_description"] == "Baby Spinach"
    assert kde["unit_of_measure"] == "cases"
    assert kde["quantity"] == "120"
    assert kde["destination_facility_name"] == "Retail DC"
    assert kde["destination_facility_code"] == "GLN-DEST"
    assert kde["origin_facility_code"] == "GLN-ORIGIN"
    assert "product_name" not in kde
    assert any(facility["name"] == "Salinas Packhouse" for facility in parsed["facilities"])


def test_parse_destination_only_csv_still_sets_facility_name():
    csv_content = (
        "event_type,product_name,lot_number,destination_facility_name\n"
        "receiving,Romaine Hearts,LOT-1,Fresno DC\n"
    )
    upload_file = _make_upload_file("receiving.csv", csv_content.encode("utf-8"), "text/csv")
    parsed = asyncio.run(parse_incoming_file(upload_file))

    assert len(parsed["events"]) == 1
    event = parsed["events"][0]
    assert event["facility_name"] == "Fresno DC"
    assert event["kde_data"]["destination_facility_name"] == "Fresno DC"
    assert event["kde_data"]["product_description"] == "Romaine Hearts"


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


def test_parse_pdf_matrix_table_extracts_facility_rows():
    parsed = {
        "facilities": [],
        "ftl_scopes": [],
        "tlcs": [],
        "events": [],
    }
    warnings: list[str] = []

    table = [
        [None, "KONOIKE E STREET", "KOPAC"],
        ["Storage capacity", "4.2 million cu. ft.", "3.6 million cu. ft."],
        [
            "Contact",
            "901 E. E St.\nWilmington, CA 90744\n(310) 233-7300",
            "1420 Coil Ave.\nWilmington, CA 90744\n(310) 618-1000",
        ],
        ["Additional Service", "Blast Freezing, Drayage", "Blast Freezing"],
        [
            "Special controls",
            "Humidity and Ethylene controls",
            "Ethylene monitor & controls",
        ],
    ]

    added = _parse_pdf_matrix_table(table, parsed, warnings)

    assert added == 2
    assert len(parsed["facilities"]) == 2
    assert parsed["facilities"][0]["name"] == "KONOIKE E STREET"
    assert parsed["facilities"][0]["city"] == "Wilmington"
    assert parsed["facilities"][0]["state"] == "CA"
    assert parsed["facilities"][1]["postal_code"] == "90744"
    assert warnings == []
