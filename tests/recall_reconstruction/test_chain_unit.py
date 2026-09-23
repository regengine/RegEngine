"""Unit coverage for each finding type using small inline record sets."""

from __future__ import annotations

from datetime import datetime, timezone

from shared.recall_reconstruction import build_custody, build_worksheet
from shared.recall_reconstruction.labels import FindingType, LinkLabel
from shared.recall_reconstruction.records import (
    ContentsAssertion,
    Receipt,
    RecordSet,
    RepackRow,
    Shipment,
    SourceFile,
    SourceRef,
)

MFG, DC = "0861000110003", "0861000220009"
P1, P2, P3 = "008610001100000010", "008610001100000027", "008610001100000034"


def ts(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, tzinfo=timezone.utc)


def ref(file: str, row: int, record_id: str) -> SourceRef:
    return SourceRef(file=file, row_number=row, record_id=record_id, file_sha256="a" * 64, source_system="test")


def contents(pallet: str, lot: str, qty, day: int, record_id: str = "C1") -> ContentsAssertion:
    return ContentsAssertion(
        record_id=record_id,
        pallet_id=pallet,
        lot_code=lot,
        quantity=qty,
        unit_of_measure="cases",
        recorded_at=ts(day),
        location_gln=MFG,
        location_name="MFG",
        source_ref=ref("contents.csv", 2, record_id),
    )


def shipment(pallet: str, day: int, shipment_id: str = "BOL-1") -> Shipment:
    return Shipment(
        shipment_id=shipment_id,
        pallet_id=pallet,
        from_gln=MFG,
        from_name="MFG",
        to_gln=DC,
        to_name="DC",
        shipped_at=ts(day),
        source_ref=ref("shipping.csv", 2, shipment_id),
    )


def receipt(pallet: str, day: int, shipment_ref, counted, receipt_id: str = "RCV-1") -> Receipt:
    return Receipt(
        receipt_id=receipt_id,
        shipment_ref=shipment_ref,
        pallet_id=pallet,
        location_gln=DC,
        location_name="DC",
        received_at=ts(day),
        counted_quantity=counted,
        unit_of_measure="cases",
        source_ref=ref("receiving.csv", 2, receipt_id),
    )


def rs(**kwargs) -> RecordSet:
    base = RecordSet(
        case="complete", fixture_dir=".", files={"x": SourceFile(name="x", source_system="test", available=True)}
    )
    for key, value in kwargs.items():
        setattr(base, key, value)
    return base


def types(custody):
    return sorted(f.type.value for f in custody.findings)


def test_clean_chain_is_linked():
    custody = build_custody(
        rs(contents=[contents(P1, "A", 10, 1)], shipments=[shipment(P1, 2)], receipts=[receipt(P1, 3, "BOL-1", 10)])
    )
    assert types(custody) == []
    ws = build_worksheet(rs(contents=[contents(P1, "A", 10, 1)]), custody, "A")
    assert [r.label for r in ws.rows] == [LinkLabel.LINKED]


def test_other_lot_on_complete_chain_is_no_link_not_safe():
    custody = build_custody(
        rs(contents=[contents(P1, "B", 10, 1)], shipments=[shipment(P1, 2)], receipts=[receipt(P1, 3, "BOL-1", 10)])
    )
    ws = build_worksheet(rs(contents=[contents(P1, "B", 10, 1)]), custody, "A")
    assert [r.label for r in ws.rows] == [LinkLabel.NO_LINK_ESTABLISHED]
    assert "practitioner decision" in ws.summary()["statement"]


def test_missing_receiving_handoff_blocks():
    custody = build_custody(rs(contents=[contents(P1, "A", 10, 1)], shipments=[shipment(P1, 2)]))
    assert types(custody) == [FindingType.MISSING_HANDOFF_RECEIVING.value]
    finding = custody.findings[0]
    assert finding.blocking and finding.required_record.custodian == "DC"
    ws = build_worksheet(rs(contents=[contents(P1, "A", 10, 1)]), custody, "A")
    assert ws.rows[0].label is LinkLabel.UNRESOLVED
    assert ws.rows[0].destination == "DC (receipt not recorded)"


def test_receipt_without_shipment_reference_blocks():
    custody = build_custody(rs(contents=[contents(P1, "A", 10, 1)], receipts=[receipt(P1, 3, None, 10)]))
    assert types(custody) == [FindingType.MISSING_HANDOFF_SHIPPING.value]
    assert "attested correction" in custody.findings[0].required_record.detail


def test_receipt_referencing_unknown_shipment_is_unmatched_identifier():
    custody = build_custody(rs(contents=[contents(P1, "A", 10, 1)], receipts=[receipt(P1, 3, "BOL-999", 10)]))
    assert types(custody) == [FindingType.UNMATCHED_IDENTIFIER.value]


def test_unknown_shipment_after_cutoff_is_attributed_to_source():
    data = rs(
        contents=[contents(P1, "A", 10, 1)],
        receipts=[receipt(P1, 3, "BOL-999", 10)],
        cutoffs={"erp": "2026-08-02T00:00:00Z"},
    )
    custody = build_custody(data)
    assert types(custody) == sorted(
        [FindingType.MISSING_HANDOFF_SHIPPING.value, FindingType.SOURCE_UNAVAILABLE_AFTER_CUTOFF.value]
    )
    handoff = next(f for f in custody.findings if f.type is FindingType.MISSING_HANDOFF_SHIPPING)
    assert handoff.attributed_to_cutoff == {"source_system": "erp", "last_successful_sync_at": "2026-08-02T00:00:00Z"}
    assert handoff.required_record.after == ts(2)


def test_pallet_moved_without_contents_record_is_unresolved_and_names_candidates():
    data = rs(
        contents=[contents(P1, "A", 10, 1)],
        shipments=[shipment(P1, 2, "BOL-1"), shipment(P3, 5, "BOL-2")],
        receipts=[receipt(P1, 3, "BOL-1", 10, "RCV-1"), receipt(P3, 6, "BOL-2", 10, "RCV-2")],
    )
    # P3 ships from MFG; P1 was received at DC, not MFG, so it is not a candidate.
    custody = build_custody(data)
    kinds = types(custody)
    assert kinds == [FindingType.MISSING_PALLET_CONTENTS.value]
    finding = custody.findings[0]
    assert finding.pallet_id == P3 and "none identified" in finding.required_record.detail
    ws = build_worksheet(data, custody, "A")
    labels = {r.pallet_id: r.label for r in ws.rows}
    assert labels == {P1: LinkLabel.LINKED, P3: LinkLabel.UNRESOLVED}


def test_conflicting_contents_records_block():
    data = rs(
        contents=[contents(P1, "A", 10, 1, "C1"), contents(P1, "B", 10, 2, "C2")],
        shipments=[shipment(P1, 3)],
        receipts=[receipt(P1, 4, "BOL-1", 10)],
    )
    custody = build_custody(data)
    assert types(custody) == [FindingType.CONFLICTING_PALLET_CONTENTS.value]
    assert "neither is preferred" in custody.findings[0].description


def test_repack_quantity_mismatch_blocks_and_outputs_stay_as_asserted():
    repack = RepackRow(
        record_id="R1",
        process_type="split",
        input_pallet_id=P1,
        output_pallet_id=P2,
        lot_code="A",
        quantity=8,
        unit_of_measure="cases",
        performed_at=ts(2),
        location_gln=MFG,
        location_name="MFG",
        source_ref=ref("repack.csv", 2, "R1"),
    )
    data = rs(contents=[contents(P1, "A", 10, 1)], repack_rows=[repack])
    custody = build_custody(data)
    assert types(custody) == [FindingType.QUANTITY_DISCREPANCY.value]
    finding = custody.findings[0]
    assert finding.blocking and "A: in=10.0 out=8.0" in finding.description
    assert custody.timelines[P2].latest_contents.lots == {"A": 8}
    assert custody.timelines[P1].is_terminal is False
    assert custody.ancestors(P2) == [P1]


def test_receipt_count_shortfall_is_reported_but_not_blocking():
    custody = build_custody(
        rs(contents=[contents(P1, "A", 10, 1)], shipments=[shipment(P1, 2)], receipts=[receipt(P1, 3, "BOL-1", 9)])
    )
    assert types(custody) == [FindingType.QUANTITY_DISCREPANCY.value]
    assert custody.findings[0].blocking is False
    assert "delta -1" in custody.findings[0].description


def test_unknown_quantity_is_never_treated_as_zero():
    custody = build_custody(
        rs(contents=[contents(P1, "A", None, 1)], shipments=[shipment(P1, 2)], receipts=[receipt(P1, 3, "BOL-1", 10)])
    )
    assert types(custody) == []  # the loader is where a blank quantity is flagged
    assert custody.timelines[P1].latest_contents.total is None
