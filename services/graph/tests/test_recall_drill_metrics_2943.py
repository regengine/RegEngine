"""#2943: recall drills recorded 0 lots traced and 0 trace depth.

``MockRecallEngine.execute_drill`` read ``result.get("lots_count")`` and
``result.get("max_depth")`` out of the trace result. Neither key exists:
``TraceResult`` (``services/graph/app/fsma/types.py``) has ``lots`` and
``hop_count``. Both ``.get()`` calls fell through to their ``0`` default on
every real trace, and the zeroes were persisted onto the drill record — the
artifact a firm hands FDA to evidence 24-hour traceability.

The unwired fallback branch hardcoded 5/3 and 3/2, so a drill with no graph
backend reported *more* reach than one that actually queried the graph.

These tests run entirely in-process: the engine is driven with stub trace
functions returning real ``TraceResult`` instances, so no Neo4j is involved.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma.types import TraceResult  # noqa: E402
from services.graph.app.fsma_recall import MockRecallEngine, RecallType  # noqa: E402

TENANT = "11111111-1111-1111-1111-111111111111"

ENGINE_SOURCE = Path(__file__).resolve().parents[1] / "app" / "fsma_recall" / "engine.py"


def _trace_result(direction: str, lot_count: int, hop_count: int) -> TraceResult:
    return TraceResult(
        lot_id="LOT-START",
        direction=direction,
        facilities=[{"gln": "0614141000005", "name": "Valley Fresh", "type": direction}],
        events=[{"event_id": f"evt-{i}", "type": "SHIPPING"} for i in range(hop_count)],
        lots=[
            {
                "tlc": f"{direction.upper()}-LOT-{i}",
                "product_description": "Romaine",
                "quantity": 10.0,
                "unit_of_measure": "cases",
            }
            for i in range(lot_count)
        ],
        total_quantity=float(lot_count * 10),
        query_time_ms=1.5,
        hop_count=hop_count,
    )


def _engine_with(forward: TraceResult = None, backward: TraceResult = None) -> MockRecallEngine:
    async def _forward(tlc, tenant_id=None):
        return forward

    async def _backward(tlc, tenant_id=None):
        return backward

    return MockRecallEngine(
        trace_forward_fn=_forward if forward is not None else None,
        trace_backward_fn=_backward if backward is not None else None,
    )


# ---------------------------------------------------------------------------
# The metrics the drill record actually stores
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forward_drill_records_real_lot_count_and_depth():
    """AC #1: 4 lots and hop_count=3 must land as 4 and 3, not 0 and 0."""
    engine = _engine_with(forward=_trace_result("forward", lot_count=4, hop_count=3))
    drill = engine.create_drill(
        tenant_id=TENANT,
        drill_type=RecallType.FORWARD_TRACE,
        target_lot="LOT-START",
    )

    result = await engine.execute_drill(drill)

    assert result.lots_traced == 4, (
        "#2943: the engine read the non-existent key 'lots_count'; TraceResult's "
        f"field is 'lots'. Recorded lots_traced={result.lots_traced}"
    )
    assert result.max_depth_forward == 3, (
        "#2943: the engine read the non-existent key 'max_depth'; TraceResult's "
        f"field is 'hop_count'. Recorded max_depth_forward={result.max_depth_forward}"
    )


@pytest.mark.asyncio
async def test_backward_drill_records_real_lot_count_and_depth():
    engine = _engine_with(backward=_trace_result("backward", lot_count=2, hop_count=5))
    drill = engine.create_drill(
        tenant_id=TENANT,
        drill_type=RecallType.BACKWARD_TRACE,
        target_lot="LOT-START",
    )

    result = await engine.execute_drill(drill)

    assert result.lots_traced == 2
    assert result.max_depth_backward == 5


@pytest.mark.asyncio
async def test_full_trace_sums_both_directions():
    engine = _engine_with(
        forward=_trace_result("forward", lot_count=4, hop_count=3),
        backward=_trace_result("backward", lot_count=2, hop_count=5),
    )
    drill = engine.create_drill(
        tenant_id=TENANT,
        drill_type=RecallType.FULL_TRACE,
        target_lot="LOT-START",
    )

    result = await engine.execute_drill(drill)

    assert result.lots_traced == 6
    assert result.max_depth_forward == 3
    assert result.max_depth_backward == 5


@pytest.mark.asyncio
async def test_metrics_survive_a_dict_shaped_trace_result():
    """Legacy callers hand the engine ``TraceResult.__dict__``; keep working."""
    payload = _trace_result("forward", lot_count=4, hop_count=3).__dict__

    async def _forward(tlc, tenant_id=None):
        return payload

    engine = MockRecallEngine(trace_forward_fn=_forward)
    drill = engine.create_drill(
        tenant_id=TENANT,
        drill_type=RecallType.FORWARD_TRACE,
        target_lot="LOT-START",
    )

    result = await engine.execute_drill(drill)

    assert result.lots_traced == 4
    assert result.max_depth_forward == 3


@pytest.mark.asyncio
async def test_facilities_are_extracted_from_a_trace_result_object():
    """``_extract_facilities`` must read the object, not only a dict."""
    engine = _engine_with(forward=_trace_result("forward", lot_count=4, hop_count=3))
    drill = engine.create_drill(
        tenant_id=TENANT,
        drill_type=RecallType.FORWARD_TRACE,
        target_lot="LOT-START",
    )

    result = await engine.execute_drill(drill)

    assert [f.gln for f in result.affected_facilities] == ["0614141000005"]


# ---------------------------------------------------------------------------
# The simulated fallback must announce itself (AC #3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unwired_drill_is_flagged_as_simulated():
    """With no trace function wired the drill cannot produce trace evidence."""
    engine = MockRecallEngine()
    drill = engine.create_drill(
        tenant_id=TENANT,
        drill_type=RecallType.FULL_TRACE,
        target_lot="LOT-START",
    )

    result = await engine.execute_drill(drill)

    assert result.simulated is True, (
        "#2943: an unwired drill emits hardcoded demo counts (5/3 and 3/2) that "
        "look healthier than a real trace. The stored record must mark itself simulated."
    )
    assert result.lots_traced == 0
    assert result.affected_facilities == []
    assert not result.success
    assert any("unavailable" in w.lower() for w in result.warnings), (
        f"#2943: expected an unavailable-trace warning on the drill record; got warnings={result.warnings!r}"
    )
    assert result.to_dict()["simulated"] is True


@pytest.mark.asyncio
async def test_real_trace_is_not_flagged_as_simulated():
    engine = _engine_with(forward=_trace_result("forward", lot_count=4, hop_count=3))
    drill = engine.create_drill(
        tenant_id=TENANT,
        drill_type=RecallType.FORWARD_TRACE,
        target_lot="LOT-START",
    )

    result = await engine.execute_drill(drill)

    assert result.simulated is False
    assert not any("simulated" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# AC #2 — the bad keys must be gone from the source
# ---------------------------------------------------------------------------


def test_engine_no_longer_reads_lots_count_or_max_depth_keys():
    """Parsed, not grepped — so prose about the old bug doesn't trip it."""
    tree = ast.parse(ENGINE_SOURCE.read_text(encoding="utf-8"))

    offenders = [
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value in {"lots_count", "max_depth"}
    ]
    assert not offenders, (
        f"#2943: engine.py still reads TraceResult keys that do not exist: {offenders}. "
        "The real fields are 'lots' and 'hop_count'."
    )
