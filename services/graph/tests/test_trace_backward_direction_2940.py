"""#2940: backward trace must walk PRODUCED/CONSUMED the way the writers point.

``FSMARelationships`` persists both transformation edges **event -> lot**::

    EVENT_PRODUCED_LOT:  MERGE (e)-[:PRODUCED]->(l)
    EVENT_CONSUMED_LOT:  MERGE (e)-[:CONSUMED]->(l)

so the inputs of a transformation hang off the event's *outgoing* ``CONSUMED``
edge. ``trace_backward`` traversed only *incoming* ``PRODUCED|CONSUMED``
edges, which reaches the producing event on hop 1 and then dead-ends: no
writer ever creates an edge pointing *into* a ``TraceEvent`` with either type.
"One step back" was structurally impossible. The supplier fallback was dead
for a second reason — it matched ``:INCLUDED``, a relationship type nothing in
the repository writes.

These tests execute the real Cypher against an in-memory graph double
(``_fsma_graph_double``) whose edges are created by parsing the repository's
own MERGE templates, and whose traversal direction is read out of the query
under test. They therefore fail both when the traversal is left as-is *and*
when a "fix" is applied in the wrong direction: the fixture deliberately
contains a downstream lot that a naive undirected traversal would return.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from _fsma_graph_double import FakeGraph, FakeNeo4jClient  # noqa: E402

from services.graph.app.fsma.tracer import trace_backward, trace_forward  # noqa: E402
from services.graph.app.models.fsma_nodes import FSMARelationships  # noqa: E402

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"

SUPPLIER_GLN = "0614141000005"
PLANT_GLN = "0614141000029"


def _build_chain() -> FakeGraph:
    """SEED-000 -> RAW-001 -> FG-001 -> PACK-001, wired via the real templates.

    Three chained transformations::

        EVT-T0: CONSUMED SEED-000, PRODUCED RAW-001
        EVT-T1: CONSUMED RAW-001,  PRODUCED FG-001    <- shipped from SUPPLIER
        EVT-T2: CONSUMED FG-001,   PRODUCED PACK-001  <- strictly downstream

    A backward trace from FG-001 must surface RAW-001 (and SEED-000 beyond it)
    and must never surface PACK-001.
    """
    g = FakeGraph()

    lots = {
        "SEED-000": "Seed stock, 50lb sack",
        "RAW-001": "Field-run romaine, bulk bin",
        "FG-001": "Organic romaine lettuce, 24ct",
        "PACK-001": "Romaine retail clamshell, 12ct",
    }
    for tlc, description in lots.items():
        g.add_node(
            tlc,
            ["Lot"],
            tlc=tlc,
            tenant_id=TENANT_A,
            product_description=description,
            quantity=100.0,
            unit_of_measure="cases",
        )

    events = {
        "EVT-T0": "2026-01-05",
        "EVT-T1": "2026-01-12",
        "EVT-T2": "2026-01-19",
    }
    for event_id, event_date in events.items():
        g.add_node(
            event_id,
            ["TraceEvent"],
            event_id=event_id,
            tenant_id=TENANT_A,
            type="TRANSFORMATION",
            event_date=event_date,
            confidence=0.99,
        )

    g.add_node(
        "FAC-SUPPLIER",
        ["Facility"],
        gln=SUPPLIER_GLN,
        tenant_id=TENANT_A,
        name="Valley Fresh Growers",
        address="1 Grower Way, Salinas CA",
        facility_type="grower",
    )
    g.add_node(
        "FAC-PLANT",
        ["Facility"],
        gln=PLANT_GLN,
        tenant_id=TENANT_A,
        name="Central Processing Plant",
        address="9 Plant Rd, Salinas CA",
        facility_type="processor",
    )

    transformations = [
        ("EVT-T0", "SEED-000", "RAW-001"),
        ("EVT-T1", "RAW-001", "FG-001"),
        ("EVT-T2", "FG-001", "PACK-001"),
    ]
    for event_id, input_tlc, output_tlc in transformations:
        # Edge direction comes from the repository's own MERGE templates.
        g.apply_writer(
            FSMARelationships.EVENT_CONSUMED_LOT,
            event_id=event_id,
            tlc=input_tlc,
            tenant_id=TENANT_A,
        )
        g.apply_writer(
            FSMARelationships.EVENT_PRODUCED_LOT,
            event_id=event_id,
            tlc=output_tlc,
            tenant_id=TENANT_A,
        )
        # The input lot also "underwent" the event — this is what the mobile
        # ingest path writes today, and what trace_forward walks.
        g.apply_writer(
            FSMARelationships.LOT_UNDERWENT_EVENT,
            event_id=event_id,
            tlc=input_tlc,
            tenant_id=TENANT_A,
        )

    g.apply_writer(
        FSMARelationships.SHIPPED_FROM,
        event_id="EVT-T1",
        from_gln=SUPPLIER_GLN,
        tenant_id=TENANT_A,
    )
    g.apply_writer(
        FSMARelationships.EVENT_OCCURRED_AT,
        event_id="EVT-T1",
        gln=PLANT_GLN,
        tenant_id=TENANT_A,
    )
    return g


def _tlcs(result) -> set:
    return {lot["tlc"] for lot in result.lots}


# ---------------------------------------------------------------------------
# The double is honest about the schema
# ---------------------------------------------------------------------------


def test_fixture_edges_point_event_to_lot_like_the_writers_do():
    """Guard the guard: the fixture must mirror EVENT_CONSUMED_LOT's direction.

    If this ever fails, every direction assertion below is meaningless.
    """
    g = _build_chain()
    assert ("CONSUMED", "EVT-T1", "RAW-001") in g.edges
    assert ("CONSUMED", "RAW-001", "EVT-T1") not in g.edges
    assert ("PRODUCED", "EVT-T1", "FG-001") in g.edges
    assert ("PRODUCED", "FG-001", "EVT-T1") not in g.edges


# ---------------------------------------------------------------------------
# #2940 — the defect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backward_trace_returns_the_upstream_source_lot():
    """One step back from FG-001 must reach RAW-001 via EVT-T1's CONSUMED edge."""
    client = FakeNeo4jClient(_build_chain())

    result = await trace_backward(client, "FG-001", max_depth=1, tenant_id=TENANT_A)

    assert "RAW-001" in _tlcs(result), (
        "#2940: backward trace found no upstream source lot. The transformation "
        "input hangs off the event's OUTGOING CONSUMED edge "
        "((e)-[:CONSUMED]->(l), see FSMARelationships.EVENT_CONSUMED_LOT); a "
        f"traversal of incoming edges only can never reach it. Got lots={result.lots!r}"
    )
    assert result.hop_count > 1, (
        f"#2940: expected a >1-hop path (Lot<-PRODUCED-Event-CONSUMED->Lot); got hop_count={result.hop_count}"
    )


@pytest.mark.asyncio
async def test_backward_trace_does_not_return_downstream_lots():
    """A wrong-direction 'fix' returns PACK-001 — downstream — and must fail."""
    client = FakeNeo4jClient(_build_chain())

    result = await trace_backward(client, "FG-001", max_depth=10, tenant_id=TENANT_A)

    assert "PACK-001" not in _tlcs(result), (
        "#2940: backward trace returned PACK-001, which FG-001 was consumed to "
        "make. Walking CONSUMED inbound (or undirected without a direction "
        "predicate) turns an upstream trace into a downstream one — a "
        f"confidently wrong recall answer. Got lots={result.lots!r}"
    )


@pytest.mark.asyncio
async def test_backward_trace_reaches_the_full_upstream_chain():
    """Two transformations back: FG-001 -> RAW-001 -> SEED-000."""
    client = FakeNeo4jClient(_build_chain())

    result = await trace_backward(client, "FG-001", max_depth=10, tenant_id=TENANT_A)

    assert _tlcs(result) == {"FG-001", "RAW-001", "SEED-000"}, (
        f"#2940: expected the start lot plus its two upstream ancestors; got {sorted(_tlcs(result))}"
    )
    assert result.hop_count == 4, (
        f"#2940: FG-001<-EVT-T1->RAW-001<-EVT-T0->SEED-000 is 4 relationships; got {result.hop_count}"
    )
    assert {e["event_id"] for e in result.events} == {"EVT-T0", "EVT-T1"}


@pytest.mark.asyncio
async def test_backward_trace_returns_the_source_facility():
    """The producing event's SHIPPED_FROM facility must reach the caller.

    The fallback query matched ``:INCLUDED`` — a relationship type no writer
    in the repository creates — so ``facilities`` was unconditionally empty.
    """
    client = FakeNeo4jClient(_build_chain())

    result = await trace_backward(client, "FG-001", max_depth=10, tenant_id=TENANT_A)

    glns = {f.get("gln") for f in result.facilities}
    assert SUPPLIER_GLN in glns, (
        "#2940: no source facility returned. The fallback matched (:TraceEvent)"
        "-[:INCLUDED]->(:Lot); nothing writes :INCLUDED, so the query returned "
        f"zero rows unconditionally. Got facilities={result.facilities!r}"
    )


@pytest.mark.asyncio
async def test_backward_trace_emits_no_dead_included_relationship():
    """`grep -rn ':INCLUDED' services/graph` must come back empty (AC #2)."""
    client = FakeNeo4jClient(_build_chain())

    await trace_backward(client, "FG-001", max_depth=10, tenant_id=TENANT_A)

    for query in client.queries:
        assert "INCLUDED" not in query, (
            f"#2940: trace_backward still references the never-written :INCLUDED relationship:\n{query}"
        )


@pytest.mark.asyncio
async def test_backward_trace_still_refuses_to_cross_tenants():
    """The direction fix must not cost the #1256 per-node tenant guard."""
    g = _build_chain()
    g.add_node(
        "RAW-B",
        ["Lot"],
        tlc="RAW-B",
        tenant_id=TENANT_B,
        product_description="another tenant's raw material",
        quantity=5.0,
    )
    g.add_node(
        "EVT-B",
        ["TraceEvent"],
        event_id="EVT-B",
        tenant_id=TENANT_B,
        type="TRANSFORMATION",
        event_date="2026-01-11",
    )
    # A pre-existing corrupt edge: tenant B's event producing tenant A's lot.
    g.add_edge("PRODUCED", "EVT-B", "FG-001")
    g.add_edge("CONSUMED", "EVT-B", "RAW-B")

    client = FakeNeo4jClient(g)
    result = await trace_backward(client, "FG-001", max_depth=10, tenant_id=TENANT_A)

    assert "RAW-B" not in _tlcs(result)
    assert "EVT-B" not in {e["event_id"] for e in result.events}


# ---------------------------------------------------------------------------
# Control: the forward trace is already correct and must stay that way
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forward_trace_still_walks_downstream():
    """Control test — passes before and after the fix.

    ``trace_forward`` walks ``-[:UNDERWENT|PRODUCED*]->``, which already agrees
    with the writers. Its passing here is also evidence that the graph double
    evaluates the real Cypher faithfully rather than rubber-stamping.
    """
    client = FakeNeo4jClient(_build_chain())

    result = await trace_forward(client, "RAW-001", max_depth=10, tenant_id=TENANT_A)

    assert _tlcs(result) == {"RAW-001", "FG-001", "PACK-001"}
    assert "SEED-000" not in _tlcs(result)
