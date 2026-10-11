"""QA5 hardening tests for the remediation slice that need no live database.

DB-backed regressions for the same fixes live in
test_remediation_qa5_db.py; this file covers the pure helpers so the
behavior is pinned even where Postgres is unavailable.
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

# Mirrors conftest.py's sys.path shim so `app.remediation...` resolves the
# same way it does for the live-DB tests in this directory.
service_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(service_dir))

from app.remediation import evidence as evidence_mod  # noqa: E402
from app.remediation.router import _safe_filename  # noqa: E402
from app.remediation.service import _decode_manifest_bytes  # noqa: E402
from app.remediation.validation import build_event_from_row, snapshot_failures, validate_event  # noqa: E402

VALID_ROW = (
    "receiving,VF-BOM-01,Romaine Hearts 24ct,10,cases,2026-07-13,"
    "Fresh Distributors DC 4,Valley Farms LLC,Valley Farms Packinghouse,BOL-01"
)
HEADER = (
    "cte_type,tlc,product,quantity,uom,receive_date,receiving_location,previous_source,tlc_source,reference_document"
)


def _parse_first_row(raw: bytes) -> dict:
    text_content = _decode_manifest_bytes(raw)
    reader = csv.DictReader(io.StringIO(text_content))
    rows = list(reader)
    assert rows, "fixture must contain a data row"
    return {(k or ""): (val or "") for k, val in rows[0].items()}


def test_bom_manifest_first_column_still_maps():
    """Excel-saved (BOM-prefixed) manifests must validate like plain UTF-8."""
    raw = ("\ufeff" + HEADER + "\n" + VALID_ROW + "\n").encode("utf-8")
    clean_row = _parse_first_row(raw)
    assert "cte_type" in clean_row, clean_row.keys()
    event, _provenance, service_failures = build_event_from_row(clean_row)
    assert event.get("cte_type") == "receiving"
    kde_errors, summary = validate_event(event)
    failures, _warnings, blocking = snapshot_failures(kde_errors, summary, service_failures)
    assert not blocking, failures
    assert not any(f["issue_id"] == "kde:cte_type" for f in failures)


def test_decode_manifest_bytes_plain_utf8_unchanged():
    raw = (HEADER + "\n" + VALID_ROW + "\n").encode("utf-8")
    assert _decode_manifest_bytes(raw) == raw.decode("utf-8")


def test_decode_manifest_bytes_rejects_non_utf8():
    with pytest.raises(HTTPException) as excinfo:
        _decode_manifest_bytes(b"\xff\xfe\x00not-utf8")
    assert excinfo.value.status_code == 400


def test_safe_filename_keeps_normal_names():
    assert _safe_filename("05_missing_tlc_source.csv") == "05_missing_tlc_source.csv"
    assert _safe_filename("manifest.csv") == "manifest.csv"


def test_safe_filename_strips_header_breaking_characters():
    hostile = 'evil.csv"\r\nX-Injected: yes'
    cleaned = _safe_filename(hostile)
    assert '"' not in cleaned
    assert "\r" not in cleaned
    assert "\n" not in cleaned
    assert cleaned.startswith("evil.csv")


def test_safe_filename_strips_path_components_and_falls_back():
    assert _safe_filename("../../etc/passwd") == "passwd"
    assert _safe_filename("..\\windows\\system32") == "system32"
    assert _safe_filename("") == "manifest.csv"
    assert _safe_filename(None) == "manifest.csv"
    assert _safe_filename('"\r\n') == "manifest.csv"


def _record(cte_type: str, kdes: dict, timestamp: str = "") -> dict:
    return {
        "row_number": 1,
        "normalized_payload": {
            "cte_type": cte_type,
            "traceability_lot_code": "LOT1",
            "product_description": "Apples",
            "quantity": 5,
            "unit_of_measure": "cases",
            "timestamp": timestamp,
            "kdes": kdes,
        },
        "release_status": "released",
        "released_event_id": "e1",
    }


def _event_date_cell(record: dict) -> str:
    out = evidence_mod._accepted_csv([record])
    reader = csv.reader(io.StringIO(out))
    header = next(reader)
    row = next(reader)
    return row[header.index("event_date")]


def test_evidence_event_date_covers_all_cte_date_kdes():
    assert _event_date_cell(_record("receiving", {"receive_date": "2026-07-13"})) == "2026-07-13"
    assert _event_date_cell(_record("shipping", {"ship_date": "2026-07-14"})) == "2026-07-14"
    assert _event_date_cell(_record("harvesting", {"harvest_date": "2026-07-15"})) == "2026-07-15"
    assert _event_date_cell(_record("cooling", {"cooling_date": "2026-07-16"})) == "2026-07-16"
    assert _event_date_cell(_record("initial_packing", {"packing_date": "2026-07-17"})) == "2026-07-17"
    assert _event_date_cell(_record("first_land_based_receiving", {"landing_date": "2026-07-18"})) == "2026-07-18"
    assert _event_date_cell(_record("transformation", {"transformation_date": "2026-07-19"})) == "2026-07-19"


def test_evidence_event_date_prefers_top_level_timestamp():
    record = _record("receiving", {"receive_date": "2026-07-13"}, timestamp="2026-07-12")
    assert _event_date_cell(record) == "2026-07-12"


def test_evidence_event_date_blank_when_no_date_anywhere():
    assert _event_date_cell(_record("receiving", {})) == ""
