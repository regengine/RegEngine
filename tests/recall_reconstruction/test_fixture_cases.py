"""Run the recall fixture three ways and check the honesty properties end to end."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from shared.recall_reconstruction import CASES, LinkLabel, build_custody, build_worksheet, load_fixture, run_case
from shared.recall_reconstruction.labels import FindingType

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "sample_data" / "recall_fixture"
P = {n: f"0086100011{n:07d}" for n in range(1, 11)}  # prefix; full ids carry a check digit
PALLET = {
    1: "008610001100000010",
    2: "008610001100000027",
    3: "008610001100000034",
    4: "008610001100000041",
    5: "008610001100000058",
    6: "008610001100000065",
    7: "008610001100000072",
    8: "008610001100000089",
    9: "008610001100000096",
    10: "008610001100000102",
}
LOT_A, LOT_B = "HLF-215A", "HLF-215B"
DEST_A, DEST_B, THREE_PL = "0861000440001", "0861000550007", "0861000330005"


def _rows(case: str):
    rs = load_fixture(FIXTURE, case)
    custody = build_custody(rs)
    ws = build_worksheet(rs, custody, LOT_A)
    return rs, custody, ws, {(r.pallet_id, r.lot_code): r for r in ws.rows}


@pytest.mark.parametrize("case", list(CASES))
def test_every_case_reconciles_against_answer_key(case, tmp_path):
    manifest = run_case(FIXTURE, case, tmp_path / case)
    failed = [c for c in manifest["reconciliation"]["checks"] if not c["passed"]]
    assert manifest["reconciliation"]["passed"], failed
    for name in (
        "worksheet.csv",
        "worksheet.json",
        "findings.json",
        "corrections.json",
        "canonical_events.json",
        "custody.json",
        "answer_key_reconciliation.json",
        "manifest.json",
    ):
        assert (tmp_path / case / name).exists(), name


def test_complete_case_reconstructs_answer_key():
    rs, custody, ws, rows = _rows("complete")
    summary = ws.summary()
    assert summary["rows_by_label"] == {"linked": 4, "no_link_established": 3, "unresolved": 0}
    assert summary["linked_quantity_by_lot_and_destination"] == {LOT_A: {DEST_A: 150.0, DEST_B: 40.0}}
    # Identifier change: P9 carries P6's lot history.
    assert rows[(PALLET[9], LOT_A)].lineage == [PALLET[6]]
    # Consolidation at the 3PL: P10 carries both split children and their parent.
    assert rows[(PALLET[10], LOT_A)].lineage == [PALLET[7], PALLET[8], PALLET[3]]
    # Mixed pallet: LOT-B on P10 is flagged for the practitioner but not labelled linked.
    lot_b_on_p10 = rows[(PALLET[10], LOT_B)]
    assert lot_b_on_p10.label is LinkLabel.NO_LINK_ESTABLISHED
    assert lot_b_on_p10.co_palletized_with_implicated_lot is True
    # Quantity discrepancy on P2 is reported and does not block the link.
    p2 = rows[(PALLET[2], LOT_A)]
    assert p2.label is LinkLabel.LINKED
    assert p2.quantity_asserted == 60 and p2.quantity_counted_at_last_receipt == 58
    assert any("delta -2" in n for n in p2.notes)
    # Only one finding type in the complete case.
    assert {f.type for f in custody.findings} == {FindingType.QUANTITY_DISCREPANCY}
    # Every asserted connection points at source evidence.
    for row in ws.rows:
        assert row.supporting_records, row.pallet_id
        assert all(len(ref.file_sha256) == 64 for ref in row.supporting_records)


def test_manual_correction_requires_author_reason_evidence_and_is_recorded():
    rs, custody, ws, rows = _rows("complete")
    correction = next(c for c in rs.corrections if c.correction_id == "COR-001")
    assert correction.applied and correction.author and correction.reason and correction.evidence_ref
    receipt = next(r for r in rs.receipts if r.receipt_id == "RCV-DC-004")
    assert receipt.shipment_ref == "BOL-MFG-001"
    assert receipt.corrections == [correction]
    p4 = rows[(PALLET[4], LOT_B)]
    assert correction.source_ref in p4.supporting_records
    assert any("COR-001" in n and "J. Alvarez" in n for n in p4.notes)


def test_missing_3pl_contents_is_unresolved_never_excluded():
    rs, custody, ws, rows = _rows("missing_3pl_contents")
    assert rs.files["3pl_repack.csv"].available is False
    p10 = rows[(PALLET[10], None)]
    assert p10.label is LinkLabel.UNRESOLVED
    assert p10.quantity_asserted is None and p10.quantity_counted_at_last_receipt == 60
    assert p10.destination_gln == DEST_B
    # The precise record needed is named: type, custodian, GLN, window, candidate inputs.
    question = p10.unresolved_questions[0]
    for fragment in (
        "pallet contents or repack record",
        "Bluewater Logistics",
        THREE_PL,
        "2026-08-06T15:40:00+00:00",
        "2026-08-08T06:30:00+00:00",
        PALLET[7],
        PALLET[8],
    ):
        assert fragment in question, fragment
    # The possible inputs are unresolved too, with last recorded location at the 3PL.
    for pallet, lot in ((PALLET[7], LOT_A), (PALLET[8], LOT_B)):
        row = rows[(pallet, lot)]
        assert row.label is LinkLabel.UNRESOLVED
        assert row.last_recorded_location_gln == THREE_PL
    # Nothing is labelled no_link_established because of the missing record,
    # and LOT-A at destination B is not asserted as zero.
    summary = ws.summary()
    assert summary["linked_quantity_by_lot_and_destination"] == {LOT_A: {DEST_A: 150.0}}
    assert DEST_B not in summary["linked_quantity_by_lot_and_destination"][LOT_A]
    assert summary["unresolved_quantity_by_lot"] == {LOT_A: 40.0, LOT_B: 20.0}
    # Rows unaffected by the gap are identical to the complete case.
    _, _, complete_ws, complete_rows = _rows("complete")
    for key in ((PALLET[1], LOT_A), (PALLET[2], LOT_A), (PALLET[4], LOT_B), (PALLET[5], LOT_B), (PALLET[9], LOT_A)):
        assert rows[key].as_dict() == complete_rows[key].as_dict(), key


def test_erp_unavailable_states_cutoff_and_reproduces_retained_evidence():
    rs, custody, ws, rows = _rows("erp_unavailable")
    assert rs.cutoffs == {"dc_erp": "2026-08-05T12:00:00Z"}
    assert rs.files["dc_receiving.csv"].retained_from == "retained/dc_erp/dc_receiving.csv"
    assert rs.files["dc_repack.csv"].retained_from == "retained/dc_erp/dc_repack.csv"
    assert rs.files["dc_shipping.csv"].available is False
    assert "2026-08-05T12:00:00Z" in (rs.files["dc_shipping.csv"].unavailable_reason or "")
    # Everything downstream of the cutoff is unresolved, and every question names the sync time.
    assert all(r.label is LinkLabel.UNRESOLVED for r in ws.rows)
    for row in ws.rows:
        assert row.unresolved_questions
        assert all("dc_erp" in q and "2026-08-05T12:00:00+00:00" in q for q in row.unresolved_questions), row.pallet_id
    handoff = [f for f in custody.findings if f.type is FindingType.MISSING_HANDOFF_SHIPPING]
    assert len(handoff) == 7
    assert all(
        f.attributed_to_cutoff == {"source_system": "dc_erp", "last_successful_sync_at": "2026-08-05T12:00:00Z"}
        for f in handoff
    )
    # Evidence captured before the cutoff is reproduced exactly: DC receipts and repacks.
    _, complete_custody, _, _ = _rows("complete")
    for pallet in (PALLET[7], PALLET[8], PALLET[9]):
        retained = custody.timelines[pallet].contents_groups
        complete = complete_custody.timelines[pallet].contents_groups
        assert [(g.record_id, g.lots, g.derived_from) for g in retained] == [
            (g.record_id, g.lots, g.derived_from) for g in complete
        ]


def test_package_manifest_carries_sync_times_and_hashes(tmp_path):
    manifest = run_case(FIXTURE, "erp_unavailable", tmp_path)
    assert manifest["unavailable_sources"]["dc_erp"]["last_successful_sync_at"] == "2026-08-05T12:00:00Z"
    assert manifest["last_successful_sync_by_source"]["dc_erp"] == "2026-08-05T12:00:00Z"
    assert manifest["sources"]["dc_shipping.csv"]["available"] is False
    assert len(manifest["package_hash"]) == 64
    assert all(len(h) == 64 for h in manifest["files"].values())
    events = json.loads((tmp_path / "canonical_events.json").read_text())
    assert events["events"] and all(len(e["chain_hash"]) == 64 for e in events["events"])
    # The worksheet CSV opens as a plain table with one label per row.
    with open(tmp_path / "worksheet.csv", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {r["label"] for r in rows} <= {label.value for label in LinkLabel}
    assert all(r["unresolved_questions"] for r in rows)
