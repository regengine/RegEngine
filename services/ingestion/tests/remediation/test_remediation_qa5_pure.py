"""Data-free checks for remediation CSV decoding and export helpers."""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(service_dir))

from app.remediation.evidence import _accepted_csv, _event_date  # noqa: E402
from app.remediation.router import _safe_filename  # noqa: E402
from app.remediation.service import _decode_manifest_bytes  # noqa: E402

HEADER = (
    "cte_type,tlc,product,quantity,uom,receive_date,receiving_location,"
    "previous_source,tlc_source,reference_document\n"
)


def test_bom_header_first_column_still_maps_without_rows():
    raw = ("\ufeff" + HEADER).encode("utf-8")
    reader = csv.DictReader(io.StringIO(_decode_manifest_bytes(raw)))
    assert reader.fieldnames[0] == "cte_type"
    assert list(reader) == []


def test_decode_manifest_bytes_plain_utf8_unchanged():
    raw = HEADER.encode("utf-8")
    assert _decode_manifest_bytes(raw) == HEADER


def test_decode_manifest_bytes_rejects_non_utf8():
    with pytest.raises(HTTPException) as excinfo:
        _decode_manifest_bytes(b"\xff\xfe\x00")
    assert excinfo.value.status_code == 400


def test_safe_filename_keeps_normal_names():
    assert _safe_filename("manifest.csv") == "manifest.csv"


def test_safe_filename_strips_header_breaking_characters():
    hostile = 'manifest.csv"\r\nX-Injected: yes'
    cleaned = _safe_filename(hostile)
    assert '"' not in cleaned
    assert "\r" not in cleaned
    assert "\n" not in cleaned
    assert cleaned.startswith("manifest.csv")


def test_safe_filename_strips_path_components_and_falls_back():
    assert _safe_filename("../../etc/passwd") == "passwd"
    assert _safe_filename("..\\windows\\system32") == "system32"
    assert _safe_filename("") == "manifest.csv"
    assert _safe_filename(None) == "manifest.csv"
    assert _safe_filename('"\r\n') == "manifest.csv"


def test_evidence_event_date_blank_when_no_date_anywhere():
    assert _event_date({}, {}) == ""


def test_accepted_csv_without_records_has_only_headers():
    reader = csv.reader(io.StringIO(_accepted_csv([])))
    assert "event_date" in next(reader)
    assert list(reader) == []
