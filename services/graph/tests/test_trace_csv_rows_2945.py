"""#2945: the FDA trace CSV emitted a lot x event cartesian product.

``export_trace_csv`` looped ``for lot in result.lots: for event in
result.events:`` with **no join key**, so a trace of 6 lots and 20 events
produced 120 rows, each asserting that this lot underwent this event. Every
row was then stamped with ``next((f for f in result.facilities if
f.get("gln")), {})`` — the *first* GLN-bearing facility in a flat list —
regardless of where the event actually happened.

For a spreadsheet the endpoint advertises as an FDA recall submission, that is
fabrication rather than omission: it asserts specific lots were handled at
specific locations on specific dates when the graph says otherwise.

The root cause is upstream of the writer: ``TraceResult.facilities/.events/
.lots`` are three independent flat lists, so the lot<->event<->facility
association present in the graph path is discarded before any exporter can see
it. The fix therefore has two halves, both covered here:

1. ``TraceResult.trace_rows`` — the tracer now returns the real associations.
2. ``services/graph/app/exporters/trace_csv.build_trace_csv_rows`` — a shared
   row builder that emits one row per *observed* association and never borrows
   another row's facility.

All of these tests run in-process; the tracer half uses the in-memory graph
double rather than a Neo4j server.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from _fsma_graph_double import FakeGraph, FakeNeo4jClient  # noqa: E402

from services.graph.app.exporters.trace_csv import (  # noqa: E402
    TRACE_CSV_HEADER,
    build_trace_csv_rows,
)
from services.graph.app.fsma.tracer import trace_forward  # noqa: E402
from services.graph.app.fsma.types import TraceResult  # noqa: E402
from services.graph.app.models.fsma_nodes import FSMARelationships  # noqa: E402

TENANT = "11111111-1111-1111-1111-111111111111"

GLN_PACKHOUSE = "0614141000005"
GLN_DC = "0614141000029"

LOT_A = {"tlc": "LOT-A", "product_description": "Romaine, 24ct", "quantity": 40, "unit_of_measure": "CASE"}
LOT_B = {"tlc": "LOT-B", "product_description": "Spinach, 12ct", "quantity": 18, "unit_of_measure": "CASE"}

EVT_1 = {"event_id": "evt-1", "type": "HARVESTING", "event_date": "2026-03-01", "confidence": 0.97}
EVT_2 = {"event_id": "evt-2", "type": "SHIPPING", "event_date": "2026-03-04", "confidence": 0.91}
EVT_3 = {"event_id": "evt-3", "type": "RECEIVING", "event_date": "2026-03-06", "confidence": 0.88}

FAC_PACKHOUSE = {"gln": GLN_PACKHOUSE, "name": "Valley Fresh Packhouse", "address": "1 Grower Way"}
FAC_DC = {"gln": GLN_DC, "name": "Regional DC", "address": "9 Dock St"}

# The truth in the graph: LOT-A was harvested then shipped; LOT-B was received.
TRUE_ASSOCIATIONS = [
    {"lot": LOT_A, "event": EVT_1, "facility": FAC_PACKHOUSE},
    {"lot": LOT_A, "event": EVT_2, "facility": FAC_PACKHOUSE},
    {"lot": LOT_B, "event": EVT_3, "facility": FAC_DC},
]

TRUE_PAIRS = {("LOT-A", "HARVESTING"), ("LOT-A", "SHIPPING"), ("LOT-B", "RECEIVING")}

_COL = {name: idx for idx, name in enumerate(TRACE_CSV_HEADER)}


def _result(trace_rows=None) -> TraceResult:
    return TraceResult(
        lot_id="LOT-A",
        direction="forward",
        facilities=[FAC_PACKHOUSE, FAC_DC],
        events=[EVT_1, EVT_2, EVT_3],
        lots=[LOT_A, LOT_B],
        total_quantity=58.0,
        query_time_ms=2.0,
        hop_count=4,
        trace_rows=trace_rows,
    )


def _cell(row, column):
    return row[_COL[column]]


# ---------------------------------------------------------------------------
# Row count: the cartesian product is gone (AC #1)
# ---------------------------------------------------------------------------


def test_two_lots_and_three_events_produce_three_rows_not_six():
    rows = build_trace_csv_rows(_result(TRUE_ASSOCIATIONS), "LOT-A")

    assert len(rows) == 3, (
        "#2945: expected one row per observed lot/event association. The old "
        "writer nested `for event in result.events` inside `for lot in "
        f"result.lots` with no join key, giving len(lots)*len(events) rows. Got {len(rows)} rows: {rows!r}"
    )


def test_no_row_pairs_a_lot_with_an_event_it_did_not_undergo():
    """AC #2 (half 1): every emitted pairing must exist in the fixture graph."""
    rows = build_trace_csv_rows(_result(TRUE_ASSOCIATIONS), "LOT-A")

    emitted = {(_cell(r, "Traceability Lot Code (TLC)"), _cell(r, "Event Type")) for r in rows}
    assert emitted == TRUE_PAIRS, (
        f"#2945: the CSV asserts lot/event pairings the graph does not contain. Emitted {sorted(emitted)}, "
        f"graph has {sorted(TRUE_PAIRS)}"
    )


def test_no_row_borrows_another_rows_facility():
    """AC #2 (half 2): the facility must be the one linked to *that* event."""
    rows = build_trace_csv_rows(_result(TRUE_ASSOCIATIONS), "LOT-A")

    by_event = {_cell(r, "Event Type"): _cell(r, "Facility GLN") for r in rows}
    assert by_event == {
        "HARVESTING": GLN_PACKHOUSE,
        "SHIPPING": GLN_PACKHOUSE,
        "RECEIVING": GLN_DC,
    }, (
        "#2945: rows were stamped with `next((f for f in result.facilities if "
        f"f.get('gln')), {{}})` — the first facility in a flat list. Got {by_event!r}"
    )


def test_header_keeps_the_documented_eleven_column_shape():
    assert TRACE_CSV_HEADER == [
        "Traceability Lot Code (TLC)",
        "Product Description",
        "Quantity",
        "Unit of Measure",
        "Event Type",
        "Event Date",
        "Event Time",
        "Facility Name",
        "Facility GLN",
        "Facility Address",
        "Confidence Score",
    ]
    for row in build_trace_csv_rows(_result(TRUE_ASSOCIATIONS), "LOT-A"):
        assert len(row) == len(TRACE_CSV_HEADER)


def test_lot_with_no_association_still_gets_a_row_with_blank_event_cells():
    """A lot the trace found but could not pair must not vanish — or be faked."""
    rows = build_trace_csv_rows(_result(TRUE_ASSOCIATIONS[:2]), "LOT-A")

    lot_b_rows = [r for r in rows if _cell(r, "Traceability Lot Code (TLC)") == "LOT-B"]
    assert len(lot_b_rows) == 1
    assert _cell(lot_b_rows[0], "Event Type") == ""
    assert _cell(lot_b_rows[0], "Facility GLN") == ""


# ---------------------------------------------------------------------------
# Degraded mode: associations unavailable -> blank, never borrowed
# ---------------------------------------------------------------------------


def test_without_associations_rows_are_capped_at_one_per_event():
    rows = build_trace_csv_rows(_result(trace_rows=None), "LOT-A")

    assert len(rows) == 3, f"expected one row per event when associations are unavailable; got {len(rows)}"


def test_without_associations_facility_cells_are_blank_not_borrowed():
    rows = build_trace_csv_rows(_result(trace_rows=None), "LOT-A")

    for row in rows:
        assert _cell(row, "Facility GLN") == "", (
            "#2945: with no association data the exporter must leave the facility "
            f"blank rather than borrow the first one in the list. Got {row!r}"
        )
        assert _cell(row, "Facility Name") == ""
        assert _cell(row, "Traceability Lot Code (TLC)") == "", (
            f"#2945: the lot column must be blank when the pairing is unknown. Got {row!r}"
        )


def test_single_lot_trace_is_unambiguous_so_the_tlc_is_filled():
    result = TraceResult(
        lot_id="LOT-A",
        direction="forward",
        facilities=[FAC_PACKHOUSE],
        events=[EVT_1, EVT_2],
        lots=[LOT_A],
        total_quantity=40.0,
        query_time_ms=1.0,
        hop_count=2,
    )

    rows = build_trace_csv_rows(result, "LOT-A")

    assert len(rows) == 2
    assert {_cell(r, "Traceability Lot Code (TLC)") for r in rows} == {"LOT-A"}


def test_events_only_trace_still_emits_rows():
    result = TraceResult(
        lot_id="LOT-A",
        direction="forward",
        facilities=[],
        events=[EVT_1],
        lots=[],
        total_quantity=None,
        query_time_ms=1.0,
        hop_count=1,
    )

    rows = build_trace_csv_rows(result, "LOT-A")

    assert len(rows) == 1
    assert _cell(rows[0], "Traceability Lot Code (TLC)") == "LOT-A"
    assert _cell(rows[0], "Event Type") == "HARVESTING"


def test_cells_are_formula_neutralized():
    hostile_lot = dict(LOT_A, tlc="=cmd|'/c calc'!A1")
    rows = build_trace_csv_rows(
        _result([{"lot": hostile_lot, "event": EVT_1, "facility": FAC_PACKHOUSE}]),
        "LOT-A",
    )

    assert _cell(rows[0], "Traceability Lot Code (TLC)").startswith("'=")


# ---------------------------------------------------------------------------
# The tracer half: associations must survive the query (root cause)
# ---------------------------------------------------------------------------


def _linear_chain() -> FakeGraph:
    g = FakeGraph()
    g.add_node("LOT-A", ["Lot"], tlc="LOT-A", tenant_id=TENANT, product_description="Romaine, 24ct", quantity=40)
    g.add_node("LOT-B", ["Lot"], tlc="LOT-B", tenant_id=TENANT, product_description="Romaine case", quantity=40)
    g.add_node("evt-1", ["TraceEvent"], event_id="evt-1", tenant_id=TENANT, type="HARVESTING", event_date="2026-03-01")
    g.add_node("evt-2", ["TraceEvent"], event_id="evt-2", tenant_id=TENANT, type="SHIPPING", event_date="2026-03-04")
    g.add_node(
        "fac-pack",
        ["Facility"],
        gln=GLN_PACKHOUSE,
        tenant_id=TENANT,
        name="Valley Fresh Packhouse",
        address="1 Grower Way",
    )
    g.add_node("fac-dc", ["Facility"], gln=GLN_DC, tenant_id=TENANT, name="Regional DC", address="9 Dock St")

    g.apply_writer(FSMARelationships.LOT_UNDERWENT_EVENT, tlc="LOT-A", event_id="evt-1", tenant_id=TENANT)
    g.apply_writer(FSMARelationships.EVENT_PRODUCED_LOT, event_id="evt-1", tlc="LOT-B", tenant_id=TENANT)
    g.apply_writer(FSMARelationships.LOT_UNDERWENT_EVENT, tlc="LOT-B", event_id="evt-2", tenant_id=TENANT)
    g.apply_writer(FSMARelationships.EVENT_OCCURRED_AT, event_id="evt-1", gln=GLN_PACKHOUSE, tenant_id=TENANT)
    g.apply_writer(FSMARelationships.EVENT_OCCURRED_AT, event_id="evt-2", gln=GLN_DC, tenant_id=TENANT)
    return g


@pytest.mark.asyncio
async def test_tracer_returns_lot_event_facility_associations():
    client = FakeNeo4jClient(_linear_chain())

    result = await trace_forward(client, "LOT-A", max_depth=10, tenant_id=TENANT)

    assert result.trace_rows, (
        "#2945: TraceResult still discards the lot<->event<->facility pairing "
        "present in the path, so no exporter can reconstruct it."
    )
    triples = {
        (row["lot"]["tlc"], row["event"]["type"], (row.get("facility") or {}).get("gln")) for row in result.trace_rows
    }
    assert triples == {
        ("LOT-A", "HARVESTING", GLN_PACKHOUSE),
        ("LOT-B", "HARVESTING", GLN_PACKHOUSE),
        ("LOT-B", "SHIPPING", GLN_DC),
    }, f"unexpected associations: {sorted(triples)}"


@pytest.mark.asyncio
async def test_csv_rows_built_from_a_real_trace_are_not_a_cartesian_product():
    client = FakeNeo4jClient(_linear_chain())

    result = await trace_forward(client, "LOT-A", max_depth=10, tenant_id=TENANT)
    rows = build_trace_csv_rows(result, "LOT-A")

    assert len(rows) < len(result.lots) * len(result.events)
    for row in rows:
        tlc, event_type, gln = (
            _cell(row, "Traceability Lot Code (TLC)"),
            _cell(row, "Event Type"),
            _cell(row, "Facility GLN"),
        )
        assert (tlc, event_type, gln) in {
            ("LOT-A", "HARVESTING", GLN_PACKHOUSE),
            ("LOT-B", "HARVESTING", GLN_PACKHOUSE),
            ("LOT-B", "SHIPPING", GLN_DC),
        }
