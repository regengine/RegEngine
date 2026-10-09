"""Focused coverage for the recall-fixture loader.

Builds tiny synthetic fixture directories for edge cases and uses the real
sample fixture for the main happy-path and case-variant behavior.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from shared.recall_reconstruction import load_fixture
from shared.recall_reconstruction.labels import FindingType
from shared.recall_reconstruction.loader import parse_ts, sha256_file

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "sample_data" / "recall_fixture"

GLN_PLANT = "0861000110003"
GLN_DC = "0861000220009"
PALLET_A = "008610001100000010"
PALLET_B = "008610001100000027"

LOTS_HEADER = [
    "lot_code",
    "gtin",
    "product_description",
    "quantity",
    "unit_of_measure",
    "produced_at",
    "location_gln",
    "location_name",
]
RECEIVING_HEADER = [
    "receipt_id",
    "shipment_ref",
    "pallet_id",
    "location_gln",
    "location_name",
    "received_at",
    "counted_quantity",
    "unit_of_measure",
]
CORRECTIONS_HEADER = [
    "correction_id",
    "target_file",
    "target_record_id",
    "field",
    "value",
    "author",
    "reason",
    "evidence_ref",
    "asserted_at",
]


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _make_fixture(
    tmp_path: Path,
    *,
    lots_rows: list[list[str]] | None = None,
    receiving_rows: list[list[str]] | None = None,
    corrections_rows: list[list[str]] | None = None,
) -> Path:
    (tmp_path / "sync_manifest.json").write_text(json.dumps({"files": {}, "sources": {}}), encoding="utf-8")
    if lots_rows is not None:
        _write_csv(tmp_path / "mfg_lots.csv", LOTS_HEADER, lots_rows)
    if receiving_rows is not None:
        _write_csv(tmp_path / "dc_receiving.csv", RECEIVING_HEADER, receiving_rows)
    if corrections_rows is not None:
        _write_csv(tmp_path / "manual_corrections.csv", CORRECTIONS_HEADER, corrections_rows)
    return tmp_path


def _lot_row(**overrides: str) -> list[str]:
    row = {
        "lot_code": "LOT-1",
        "gtin": "00861000110010",
        "product_description": "Oat Beverage 12x1L",
        "quantity": "100",
        "unit_of_measure": "cases",
        "produced_at": "2026-08-03T11:00:00Z",
        "location_gln": GLN_PLANT,
        "location_name": "Plant",
    }
    row.update(overrides)
    return [row[c] for c in LOTS_HEADER]


def _receiving_row(**overrides: str) -> list[str]:
    row = {
        "receipt_id": "RCV-001",
        "shipment_ref": "BOL-1",
        "pallet_id": PALLET_A,
        "location_gln": GLN_DC,
        "location_name": "DC",
        "received_at": "2026-08-04T16:00:00Z",
        "counted_quantity": "60",
        "unit_of_measure": "cases",
    }
    row.update(overrides)
    return [row[c] for c in RECEIVING_HEADER]


def _correction_row(**overrides: str) -> list[str]:
    row = {
        "correction_id": "COR-T1",
        "target_file": "dc_receiving.csv",
        "target_record_id": "RCV-001",
        "field": "shipment_ref",
        "value": "BOL-2",
        "author": "Tester",
        "reason": "BOL was keyed wrong",
        "evidence_ref": "BOL-2.pdf",
        "asserted_at": "2026-08-20T17:10:00Z",
    }
    row.update(overrides)
    return [row[c] for c in CORRECTIONS_HEADER]


def test_complete_fixture_loads_typed_records_with_source_refs():
    rs = load_fixture(FIXTURE, "complete")

    assert len(rs.lots) == 2
    assert rs.contents and rs.shipments and rs.receipts and rs.repack_rows
    for lot in rs.lots:
        assert lot.source_ref.file == "mfg_lots.csv"
        assert lot.source_ref.file_sha256 == sha256_file(FIXTURE / "mfg_lots.csv")
    assert all(f.available for f in rs.files.values())
    assert rs.files["mfg_lots.csv"].row_count == 2

    correction = next(c for c in rs.corrections if c.correction_id == "COR-001")
    assert correction.applied is True
    receipt = next(r for r in rs.receipts if r.receipt_id == "RCV-DC-004")
    assert receipt.shipment_ref == "BOL-MFG-001"


def test_unknown_case_raises_value_error(tmp_path):
    with pytest.raises(ValueError, match="unknown case"):
        load_fixture(tmp_path, "no_such_case")


def test_missing_3pl_contents_marks_file_unavailable():
    rs = load_fixture(FIXTURE, "missing_3pl_contents")

    source_file = rs.files["3pl_repack.csv"]
    assert source_file.available is False
    assert source_file.unavailable_reason == "record not provided for this case"
    assert all(r.source_ref.file != "3pl_repack.csv" for r in rs.repack_rows)


def test_erp_unavailable_uses_retained_snapshot_and_cutoff():
    rs = load_fixture(FIXTURE, "erp_unavailable")

    assert rs.cutoffs["dc_erp"] == "2026-08-05T12:00:00Z"
    for name in ("dc_receiving.csv", "dc_repack.csv"):
        source_file = rs.files[name]
        assert source_file.available is True
        assert source_file.retained_from == f"retained/dc_erp/{name}"
        assert source_file.synced_at == "2026-08-05T12:00:00Z"
    shipping = rs.files["dc_shipping.csv"]
    assert shipping.available is False
    assert "last successful sync 2026-08-05T12:00:00Z" in (shipping.unavailable_reason or "")


def test_blank_required_value_becomes_finding_not_default(tmp_path):
    fixture = _make_fixture(tmp_path, lots_rows=[_lot_row(gtin="")])

    rs = load_fixture(fixture, "complete")

    assert rs.lots == []
    assert len(rs.load_findings) == 1
    finding = rs.load_findings[0]
    assert finding.type is FindingType.UNMATCHED_IDENTIFIER
    assert "gtin" in finding.description
    assert finding.source_refs[0].file == "mfg_lots.csv"


def test_invalid_gln_is_reported_but_row_still_loads(tmp_path):
    fixture = _make_fixture(tmp_path, lots_rows=[_lot_row(location_gln="123")])

    rs = load_fixture(fixture, "complete")

    assert len(rs.lots) == 1
    assert any(f.type is FindingType.UNMATCHED_IDENTIFIER and "GLN" in f.description for f in rs.load_findings)


def test_correction_fills_blank_shipment_ref(tmp_path):
    fixture = _make_fixture(
        tmp_path,
        receiving_rows=[_receiving_row(shipment_ref="")],
        corrections_rows=[_correction_row(value="BOL-2")],
    )

    rs = load_fixture(fixture, "complete")

    assert rs.receipts[0].shipment_ref == "BOL-2"
    assert rs.corrections[0].applied is True


def test_correction_may_not_overwrite_existing_value(tmp_path):
    fixture = _make_fixture(
        tmp_path,
        receiving_rows=[_receiving_row(shipment_ref="BOL-1")],
        corrections_rows=[_correction_row(value="BOL-2")],
    )

    rs = load_fixture(fixture, "complete")

    assert rs.receipts[0].shipment_ref == "BOL-1"
    correction = rs.corrections[0]
    assert correction.applied is False
    assert "not overwrite" in (correction.not_applied_reason or "")


def test_correction_for_missing_record_is_recorded_not_applied(tmp_path):
    fixture = _make_fixture(
        tmp_path,
        receiving_rows=[_receiving_row()],
        corrections_rows=[_correction_row(target_record_id="RCV-999")],
    )

    rs = load_fixture(fixture, "complete")

    correction = rs.corrections[0]
    assert correction.applied is False
    assert "RCV-999" in (correction.not_applied_reason or "")


def test_parse_ts_handles_z_offset_and_naive():
    assert parse_ts("2026-08-03T11:00:00Z").utcoffset() is not None
    assert parse_ts("2026-08-03T11:00:00+02:00").utcoffset() is not None
    naive = parse_ts("2026-08-03T11:00:00")
    assert naive.tzinfo is not None
    assert naive.isoformat() == "2026-08-03T11:00:00+00:00"
