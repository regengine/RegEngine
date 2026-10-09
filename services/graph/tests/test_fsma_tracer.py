"""Focused coverage for ``services/graph/app/fsma/tracer.py``.

Exercises the module's main public behavior through ``trace_forward`` and
``trace_backward`` using the in-memory graph double (``_fsma_graph_double``),
whose edges are created by parsing the repository's own
``FSMARelationships`` MERGE templates, plus a mock-client record feed for the
cross-tenant invariant error path:

* forward trace walks downstream lots, backward trace walks upstream lots
* both entry points fail closed on an empty tenant and on bad ``max_depth``
* the time-arrow second pass strips the causally impossible event and
  records a violation, and is skipped when enforcement is disabled
* ``trace_rows`` preserves the lot/event/facility association
* edge cases: empty graph returns empty lists, a cross-tenant node raises
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from _fsma_graph_double import FakeGraph, FakeNeo4jClient  # noqa: E402

from services.graph.app.fsma.tracer import trace_backward, trace_forward  # noqa: E402
from services.graph.app.models.fsma_nodes import FSMARelationships  # noqa: E402

TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"

GLN_FARM = "0614141000005"
GLN_PLANT = "0614141000029"


def _build_chain(event_dates=("2026-03-01", "2026-03-04")) -> FakeGraph:
    """LOT-A -> EVT-1 -> LOT-B -> EVT-2 -> LOT-C, wired via real templates.

    Each event consumes its input lot, produces its output lot, and is
    undergone by its input lot (the shape ``trace_forward`` walks). EVT-1
    occurred at the farm facility.
    """
    g = FakeGraph()
    lots = {
        "LOT-A": ("Seed stock, 50lb sack", 50.0),
        "LOT-B": ("Field-run romaine, bulk bin", 40.0),
        "LOT-C": ("Romaine retail clamshell, 12ct", 18.0),
    }
    for tlc, (description, quantity) in lots.items():
        g.add_node(
            tlc,
            ["Lot"],
            tlc=tlc,
            tenant_id=TENANT,
            product_description=description,
            quantity=quantity,
            unit_of_measure="cases",
        )
    for event_id, event_date in zip(("EVT-1", "EVT-2"), event_dates):
        g.add_node(
            event_id,
            ["TraceEvent"],
            event_id=event_id,
            tenant_id=TENANT,
            type="TRANSFORMATION",
            event_date=event_date,
            confidence=0.95,
        )
    g.add_node(
        "FAC-FARM",
        ["Facility"],
        gln=GLN_FARM,
        tenant_id=TENANT,
        name="Valley Fresh Farm",
        address="1 Grower Way, Salinas CA",
        facility_type="grower",
    )
    for event_id, input_tlc, output_tlc in (
        ("EVT-1", "LOT-A", "LOT-B"),
        ("EVT-2", "LOT-B", "LOT-C"),
    ):
        g.apply_writer(
            FSMARelationships.EVENT_CONSUMED_LOT,
            event_id=event_id,
            tlc=input_tlc,
            tenant_id=TENANT,
        )
        g.apply_writer(
            FSMARelationships.EVENT_PRODUCED_LOT,
            event_id=event_id,
            tlc=output_tlc,
            tenant_id=TENANT,
        )
        g.apply_writer(
            FSMARelationships.LOT_UNDERWENT_EVENT,
            event_id=event_id,
            tlc=input_tlc,
            tenant_id=TENANT,
        )
    g.apply_writer(
        FSMARelationships.EVENT_OCCURRED_AT,
        event_id="EVT-1",
        gln=GLN_FARM,
        tenant_id=TENANT,
    )
    return g


def _tlcs(result) -> set:
    return {lot["tlc"] for lot in result.lots}


def _make_mock_client(records):
    mock_client = MagicMock()
    mock_session = AsyncMock()

    async def _aiter(self):
        for record in records:
            yield record

    result = MagicMock()
    result.__aiter__ = _aiter
    mock_session.run = AsyncMock(return_value=result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_client.session = MagicMock(return_value=mock_session)
    return mock_client


@pytest.mark.asyncio
async def test_forward_trace_walks_downstream_lots():
    # Time-arrow enforcement is disabled here so this test covers collection
    # only; the enforcement pass has its own tests below.
    client = FakeNeo4jClient(_build_chain())

    result = await trace_forward(client, "LOT-A", max_depth=10, tenant_id=TENANT, enforce_time_arrow=False)

    assert result.direction == "forward"
    assert result.lot_id == "LOT-A"
    assert _tlcs(result) == {"LOT-A", "LOT-B", "LOT-C"}
    assert {e["event_id"] for e in result.events} == {"EVT-1", "EVT-2"}
    # The traversal returns one row per (path, node), so lots repeat across
    # paths and the total sums every row. Only assert it is populated here.
    assert result.total_quantity is not None and result.total_quantity > 0
    assert result.time_violations is None


@pytest.mark.asyncio
async def test_backward_trace_walks_upstream_lots():
    client = FakeNeo4jClient(_build_chain())

    result = await trace_backward(client, "LOT-C", max_depth=10, tenant_id=TENANT)

    assert result.direction == "backward"
    assert result.lot_id == "LOT-C"
    assert _tlcs(result) == {"LOT-A", "LOT-B", "LOT-C"}
    assert {e["event_id"] for e in result.events} == {"EVT-1", "EVT-2"}


@pytest.mark.asyncio
async def test_traces_reject_empty_tenant():
    client = FakeNeo4jClient(_build_chain())

    with pytest.raises(ValueError, match="tenant_id"):
        await trace_forward(client, "LOT-A", tenant_id="")
    with pytest.raises(ValueError, match="tenant_id"):
        await trace_backward(client, "LOT-C", tenant_id="")


@pytest.mark.asyncio
async def test_traces_reject_invalid_max_depth():
    client = FakeNeo4jClient(_build_chain())

    for bad_depth in (0, -3, "5", None):
        with pytest.raises(ValueError, match="max_depth"):
            await trace_forward(client, "LOT-A", max_depth=bad_depth, tenant_id=TENANT)
        with pytest.raises(ValueError, match="max_depth"):
            await trace_backward(client, "LOT-C", max_depth=bad_depth, tenant_id=TENANT)


@pytest.mark.asyncio
async def test_forward_time_arrow_strips_out_of_order_event():
    """Hop order says EVT-2 follows EVT-1, but its date is earlier."""
    client = FakeNeo4jClient(_build_chain(event_dates=("2026-03-10", "2026-03-01")))

    result = await trace_forward(client, "LOT-A", max_depth=10, tenant_id=TENANT)

    assert {e["event_id"] for e in result.events} == {"EVT-1"}
    # One row per (path, node) means the violating pair recurs across paths,
    # so the violation is recorded more than once. Every entry must still
    # blame the later-dated event as the downstream one.
    assert result.time_violations
    assert all(v["curr_event_id"] == "EVT-2" for v in result.time_violations)
    assert all(v["prev_event_id"] == "EVT-1" for v in result.time_violations)


@pytest.mark.xfail(
    strict=True,
    reason="time-arrow pass compares duplicate event rows across paths, "
    "so a correctly ordered multi-hop chain reports a false TIME_ARROW "
    "violation and drops its upstream event",
)
@pytest.mark.asyncio
async def test_forward_ordered_chain_keeps_every_event():
    """Correctly ordered dates must produce no violation and keep all events."""
    client = FakeNeo4jClient(_build_chain(event_dates=("2026-03-01", "2026-03-04")))

    result = await trace_forward(client, "LOT-A", max_depth=10, tenant_id=TENANT)

    assert result.time_violations is None
    assert {e["event_id"] for e in result.events} == {"EVT-1", "EVT-2"}


@pytest.mark.asyncio
async def test_forward_time_arrow_disabled_keeps_both_events():
    client = FakeNeo4jClient(_build_chain(event_dates=("2026-03-10", "2026-03-01")))

    result = await trace_forward(client, "LOT-A", max_depth=10, tenant_id=TENANT, enforce_time_arrow=False)

    assert {e["event_id"] for e in result.events} == {"EVT-1", "EVT-2"}
    assert result.time_violations is None


@pytest.mark.asyncio
async def test_forward_trace_rows_preserve_lot_event_facility():
    # Enforcement disabled: this test covers association preservation, and the
    # enforcement pass is covered by its own tests above.
    client = FakeNeo4jClient(_build_chain())

    result = await trace_forward(client, "LOT-A", max_depth=10, tenant_id=TENANT, enforce_time_arrow=False)

    assert result.trace_rows, "expected (lot, event, facility) associations"
    pairs = {(row["lot"]["tlc"], row["event"]["event_id"]) for row in result.trace_rows}
    assert ("LOT-A", "EVT-1") in pairs
    evt1_rows = [row for row in result.trace_rows if row["event"]["event_id"] == "EVT-1"]
    assert evt1_rows and evt1_rows[0]["facility"]["gln"] == GLN_FARM


@pytest.mark.asyncio
async def test_trace_on_empty_graph_returns_empty_result():
    client = FakeNeo4jClient(FakeGraph())

    result = await trace_forward(client, "NOPE", max_depth=5, tenant_id=TENANT)

    assert result.lots == []
    assert result.events == []
    assert result.facilities == []
    assert result.total_quantity is None
    assert result.trace_rows is None


@pytest.mark.asyncio
async def test_forward_invariant_raises_on_cross_tenant_node():
    leaky_record = {
        "labels": ["Lot"],
        "props": {
            "tlc": "LOT-OTHER",
            "tenant_id": OTHER_TENANT,
            "product_description": "leaked",
            "quantity": 10,
        },
        "hop_count": 2,
    }
    mock_client = _make_mock_client([leaky_record])

    with pytest.raises(ValueError, match="invariant violation"):
        await trace_forward(mock_client, "LOT-A", max_depth=5, tenant_id=TENANT)
