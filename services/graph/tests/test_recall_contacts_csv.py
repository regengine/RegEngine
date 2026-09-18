"""Recall contact-list CSV: real receiving records, no ``PENDING`` placeholder.

``export_recall_contacts`` used to write ``""`` for Date Received and
Quantity Received and the literal ``PENDING`` for Contact Status on every
facility row. ``TraceResult.trace_rows`` carries the receiving events the
graph actually records, so the builder fills those cells from them and leaves
them blank, never borrowed, for a facility with no receiving event on record.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.exporters.recall_contacts_csv import (  # noqa: E402
    RECALL_CONTACTS_HEADER,
    build_recall_contacts_rows,
)
from services.graph.app.fsma.types import TraceResult  # noqa: E402

FAC_PACK = {"gln": "0614141000005", "name": "Packhouse", "address": "1 Grower Way", "facility_type": "PACKER"}
FAC_DC = {"gln": "0614141000029", "name": "Regional DC", "address": "9 Dock St", "facility_type": "DISTRIBUTOR"}
FAC_STORE = {"gln": "0614141000043", "name": "Corner Store", "address": "3 Main St", "facility_type": "RETAILER"}
LOT_A = {"tlc": "LOT-A", "product_description": "Romaine", "quantity": 40, "unit_of_measure": "cases"}
LOT_B = {"tlc": "LOT-B", "product_description": "Spinach", "quantity": 18, "unit_of_measure": "cases"}
EVT_PACK = {"event_id": "evt-1", "type": "INITIAL_PACKING", "event_date": "2026-03-01"}
EVT_SHIP = {"event_id": "evt-2", "type": "SHIPPING", "event_date": "2026-03-04"}
EVT_RECV_A = {"event_id": "evt-3", "type": "RECEIVING", "event_date": "2026-03-06"}
EVT_RECV_B = {"event_id": "evt-4", "type": "receiving", "event_date": "2026-03-07"}

# The association dict carries only gln/name/address, as the tracer emits it.
_ASSOC_DC = {"gln": FAC_DC["gln"], "name": FAC_DC["name"], "address": FAC_DC["address"]}
_ASSOC_PACK = {"gln": FAC_PACK["gln"], "name": FAC_PACK["name"], "address": FAC_PACK["address"]}


def _result(trace_rows, facilities=(FAC_PACK, FAC_DC, FAC_STORE)) -> TraceResult:
    return TraceResult(
        lot_id="LOT-A",
        direction="forward",
        facilities=list(facilities),
        events=[EVT_PACK, EVT_SHIP, EVT_RECV_A, EVT_RECV_B],
        lots=[LOT_A, LOT_B],
        total_quantity=58.0,
        query_time_ms=1.0,
        hop_count=3,
        trace_rows=trace_rows,
    )


ASSOCIATIONS = [
    {"lot": LOT_A, "event": EVT_PACK, "facility": _ASSOC_PACK},
    {"lot": LOT_A, "event": EVT_SHIP, "facility": _ASSOC_PACK},
    {"lot": LOT_A, "event": EVT_RECV_A, "facility": _ASSOC_DC},
    {"lot": LOT_B, "event": EVT_RECV_B, "facility": _ASSOC_DC},
]


def _by_gln(rows):
    idx = RECALL_CONTACTS_HEADER.index("Global Location Number (GLN)")
    out: dict = {}
    for row in rows:
        out.setdefault(row[idx], []).append(dict(zip(RECALL_CONTACTS_HEADER, row)))
    return out


def test_receiving_association_fills_lot_date_quantity_and_unit():
    rows = _by_gln(build_recall_contacts_rows(_result(ASSOCIATIONS)))
    dc_rows = rows[FAC_DC["gln"]]
    assert len(dc_rows) == 2, "one row per receiving event the graph records"
    assert {
        (r["Traceability Lot Code"], r["Date Received"], r["Quantity Received"], r["Unit of Measure"]) for r in dc_rows
    } == {
        ("LOT-A", "2026-03-06", "40", "cases"),
        ("LOT-B", "2026-03-07", "18", "cases"),
    }
    # facility_type is looked up from the traversal's facility node by GLN.
    assert {r["Facility Type"] for r in dc_rows} == {"DISTRIBUTOR"}


def test_facility_without_receiving_event_is_listed_with_blank_receipt_cells():
    rows = _by_gln(build_recall_contacts_rows(_result(ASSOCIATIONS)))
    # Packhouse only packed and shipped; the store was reached via SHIPPED_TO
    # with no receiving event on record. Both stay on the list, blank.
    for gln in (FAC_PACK["gln"], FAC_STORE["gln"]):
        (row,) = rows[gln]
        assert row["Traceability Lot Code"] == ""
        assert row["Date Received"] == ""
        assert row["Quantity Received"] == ""
        assert row["Unit of Measure"] == ""
        assert row["Facility Name"]  # identity still comes from the facility node


def test_contact_status_is_never_asserted():
    rows = build_recall_contacts_rows(_result(ASSOCIATIONS))
    idx = RECALL_CONTACTS_HEADER.index("Contact Status")
    assert all(row[idx] == "" for row in rows)
    assert "PENDING" not in {cell for row in rows for cell in row}


def test_without_associations_every_facility_row_is_blank_not_inferred():
    # ``trace_rows=None`` means the tracer supplied no associations. The flat
    # events/lots lists cannot say which facility received which lot, so
    # nothing is borrowed from them.
    rows = build_recall_contacts_rows(_result(None))
    assert len(rows) == 3
    for row in rows:
        as_dict = dict(zip(RECALL_CONTACTS_HEADER, row))
        assert as_dict["Date Received"] == ""
        assert as_dict["Quantity Received"] == ""
        assert as_dict["Traceability Lot Code"] == ""


def test_association_without_facility_is_skipped():
    rows = build_recall_contacts_rows(_result([{"lot": LOT_A, "event": EVT_RECV_A, "facility": None}]))
    assert all(dict(zip(RECALL_CONTACTS_HEADER, r))["Date Received"] == "" for r in rows)


def test_cells_are_formula_neutralized():
    hostile_lot = {"tlc": '=HYPERLINK("http://x")', "quantity": 1, "unit_of_measure": "+cases"}
    hostile_fac = {"gln": "0614141000005", "name": "-Packhouse", "address": "@1 Grower Way", "facility_type": "PACKER"}
    rows = build_recall_contacts_rows(
        _result([{"lot": hostile_lot, "event": EVT_RECV_A, "facility": dict(hostile_fac)}], facilities=[hostile_fac])
    )
    for row in rows:
        for cell in row:
            assert not cell or cell[0] not in "=+-@", f"formula-prefixed cell escaped: {cell!r}"
