"""Deep-QA regression tests for ``services/graph/app/fsma_recall``.

Covers, against the real engine with stub tracers (no Neo4j, no DATABASE_URL):

- renamed TraceResult fields surface loudly for object shapes, not silent zeroes
- FULL_TRACE drills count distinct lots and facilities once, with exact quantities
- scheduled drills fail loudly on unsupported/empty target strategies
- drill summaries flag unwired (simulated) runs
- tenant guards on engine entry points
- error paths: trace failure, export failure, bad convenience-function input
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma.types import TraceResult  # noqa: E402
from services.graph.app.fsma_recall import (  # noqa: E402
    MockRecallEngine,
    RecallResult,
    RecallStatus,
    RecallType,
    create_mock_recall,
    reset_recall_engine,
)
from services.graph.app.fsma_recall.engine import _trace_field  # noqa: E402

TENANT = "22222222-2222-2222-2222-222222222222"
OTHER_TENANT = "33333333-3333-3333-3333-333333333333"

_FAC = {"gln": "0614141000005", "name": "Start Plant", "address": "1 Way", "facility_type": "PROCESSOR"}
_LOT_S = {"tlc": "START", "product_description": "Romaine", "quantity": 10.0, "unit_of_measure": "cases"}
_LOT_D = {"tlc": "DOWN-1", "product_description": "Romaine", "quantity": 5.0, "unit_of_measure": "cases"}
_LOT_U = {"tlc": "UP-1", "product_description": "Romaine", "quantity": 7.0, "unit_of_measure": "cases"}


def _trace_result(direction, lots, facilities, rows, hops=2):
    return TraceResult(
        lot_id="START",
        direction=direction,
        facilities=facilities,
        events=[],
        lots=lots,
        total_quantity=None,
        query_time_ms=1.0,
        hop_count=hops,
        trace_rows=rows,
    )


def _overlapping_engine():
    rows_f = [
        {"lot": _LOT_S, "event": {"event_id": "e1", "type": "SHIPPING"}, "facility": _FAC},
        {"lot": _LOT_D, "event": {"event_id": "e2", "type": "RECEIVING"}, "facility": _FAC},
    ]
    rows_b = [
        {"lot": _LOT_S, "event": {"event_id": "e0", "type": "RECEIVING"}, "facility": _FAC},
        {"lot": _LOT_U, "event": {"event_id": "e-1", "type": "INITIAL_PACKING"}, "facility": _FAC},
    ]

    async def _forward(tlc, tenant_id=None):
        return _trace_result("forward", [_LOT_S, _LOT_D], [_FAC], rows_f, 2)

    async def _backward(tlc, tenant_id=None):
        return _trace_result("backward", [_LOT_S, _LOT_U], [_FAC], rows_b, 1)

    return MockRecallEngine(trace_forward_fn=_forward, trace_backward_fn=_backward)


# ---------------------------------------------------------------------------
# _trace_field: renamed fields must be loud for objects too
# ---------------------------------------------------------------------------


def test_trace_field_missing_attribute_raises_for_objects():
    """An object without the field raises instead of defaulting to a silent zero."""
    obj = SimpleNamespace(lots=[{"tlc": "A"}], facilities=[])
    with pytest.raises(AttributeError):
        _trace_field(obj, "hop_count", 0)


def test_trace_field_missing_key_raises_for_dicts():
    with pytest.raises(KeyError):
        _trace_field({"lots": []}, "hop_count", 0)


def test_trace_field_optional_defaults_still_apply():
    obj = SimpleNamespace()
    assert _trace_field(obj, "trace_rows", None, required=False) is None
    assert _trace_field({}, "trace_rows", None, required=False) is None


@pytest.mark.asyncio
async def test_drill_fails_loudly_when_tracer_shape_loses_hop_count():
    """A tracer returning an object without hop_count fails the drill loudly."""

    async def _forward(tlc, tenant_id=None):
        return SimpleNamespace(lots=[{"tlc": "A"}], facilities=[], trace_rows=[])

    engine = MockRecallEngine(trace_forward_fn=_forward)
    drill = engine.create_drill(tenant_id=TENANT, drill_type=RecallType.FORWARD_TRACE, target_lot="A")
    result = await engine.execute_drill(drill)
    assert drill.status == RecallStatus.FAILED
    assert result.success is False
    assert result.errors, "the missing field must be recorded on the drill"


# ---------------------------------------------------------------------------
# FULL_TRACE: distinct lots and facilities, exact quantities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_trace_counts_distinct_lots_once():
    engine = _overlapping_engine()
    drill = engine.create_drill(tenant_id=TENANT, drill_type=RecallType.FULL_TRACE, target_lot="START")
    result = await engine.execute_drill(drill)
    assert result.success is True
    assert result.lots_traced == 3, "START is reached from both directions and must count once"


@pytest.mark.asyncio
async def test_full_trace_counts_shared_facility_once_with_exact_quantity():
    engine = _overlapping_engine()
    drill = engine.create_drill(tenant_id=TENANT, drill_type=RecallType.FULL_TRACE, target_lot="START")
    result = await engine.execute_drill(drill)
    assert result.facilities_identified == 1
    assert len(result.affected_facilities) == 1
    facility = result.affected_facilities[0]
    assert facility.gln == "0614141000005"
    assert facility.lots_affected == ["DOWN-1", "START", "UP-1"]
    assert facility.quantity_affected == 22.0
    assert facility.unit_of_measure == "cases"
    assert result.total_quantity_affected == 22.0
    assert result.gaps_found == 0
    assert result.data_completeness_pct == 100.0


@pytest.mark.asyncio
async def test_single_direction_counts_are_unchanged():
    engine = _overlapping_engine()
    drill = engine.create_drill(tenant_id=TENANT, drill_type=RecallType.FORWARD_TRACE, target_lot="START")
    result = await engine.execute_drill(drill)
    assert result.lots_traced == 2
    assert result.facilities_identified == 1
    assert result.total_quantity_affected == 15.0


# ---------------------------------------------------------------------------
# Scheduled drills: unsupported or empty strategies fail loudly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduled_drill_unknown_strategy_raises_without_creating_drill():
    engine = MockRecallEngine()
    schedule = engine.create_schedule(tenant_id=TENANT, drill_type=RecallType.FORWARD_TRACE, target_strategy="rotating")
    with pytest.raises(ValueError, match="unsupported target_strategy"):
        await engine.execute_scheduled_drill(schedule)
    assert engine._drills.get(TENANT, []) == []
    assert schedule.last_run is None


@pytest.mark.asyncio
async def test_scheduled_drill_specific_without_targets_raises():
    engine = MockRecallEngine()
    for targets in (None, []):
        schedule = engine.create_schedule(
            tenant_id=TENANT,
            drill_type=RecallType.FORWARD_TRACE,
            target_strategy="specific",
            specific_targets=targets,
        )
        with pytest.raises(ValueError, match="specific_targets"):
            await engine.execute_scheduled_drill(schedule)
        assert engine._drills.get(TENANT, []) == []
        assert schedule.last_run is None


# ---------------------------------------------------------------------------
# Summaries must flag simulated runs
# ---------------------------------------------------------------------------


def test_result_summary_flags_simulated():
    summary = RecallResult(drill_id="d", success=False, simulated=True).get_summary()
    assert summary["simulated"] is True
    measured = RecallResult(drill_id="d", success=True, simulated=False).get_summary()
    assert measured["simulated"] is False


@pytest.mark.asyncio
async def test_create_mock_recall_without_backend_is_flagged_simulated():
    reset_recall_engine()
    outcome = await create_mock_recall(tenant_id=TENANT, drill_type="forward_trace", target_lot="LOT-1")
    assert outcome["result"]["simulated"] is True
    assert outcome["result"]["success"] is False


# ---------------------------------------------------------------------------
# Tenant guards on engine entry points
# ---------------------------------------------------------------------------


def test_create_drill_rejects_empty_tenant():
    engine = MockRecallEngine()
    for bad in ("", "   ", None):
        with pytest.raises(ValueError, match="tenant_id"):
            engine.create_drill(tenant_id=bad, drill_type=RecallType.FORWARD_TRACE)


def test_create_schedule_rejects_empty_tenant():
    engine = MockRecallEngine()
    with pytest.raises(ValueError, match="tenant_id"):
        engine.create_schedule(tenant_id="", drill_type=RecallType.FORWARD_TRACE)


def test_read_paths_reject_empty_tenant():
    engine = MockRecallEngine()
    with pytest.raises(ValueError, match="tenant_id"):
        engine.get_drill("", "drill_x")
    with pytest.raises(ValueError, match="tenant_id"):
        engine.get_drill_history("")


def test_drill_lookup_is_tenant_scoped():
    engine = MockRecallEngine()
    drill = engine.create_drill(tenant_id=TENANT, drill_type=RecallType.FORWARD_TRACE)
    assert engine.get_drill(OTHER_TENANT, drill.drill_id) is None
    assert engine.get_drill_history(OTHER_TENANT) == []


def test_cancelled_drill_keeps_tenant_and_timestamp():
    engine = MockRecallEngine()
    drill = engine.create_drill(tenant_id=TENANT, drill_type=RecallType.FORWARD_TRACE)
    assert engine.cancel_drill(drill) is True
    assert drill.status == RecallStatus.CANCELLED
    assert drill.completed_at is not None
    assert engine.cancel_drill(drill) is False


# ---------------------------------------------------------------------------
# Error paths: trace failure, export failure, bad convenience input
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trace_exception_fails_drill_with_error_recorded():
    async def _boom(tlc, tenant_id=None):
        raise RuntimeError("graph down")

    engine = MockRecallEngine(trace_forward_fn=_boom)
    drill = engine.create_drill(tenant_id=TENANT, drill_type=RecallType.FORWARD_TRACE, target_lot="LOT-1")
    result = await engine.execute_drill(drill)
    assert drill.status == RecallStatus.FAILED
    assert result.success is False
    assert result.sla_compliant is False
    assert any("graph down" in e for e in result.errors)


@pytest.mark.asyncio
async def test_export_exception_becomes_warning_not_failure():
    async def _forward(tlc, tenant_id=None):
        return _trace_result("forward", [_LOT_S], [_FAC], None, 1)

    def _boom_export(drill, facilities, tenant_id=None):
        raise RuntimeError("csv disk full")

    engine = MockRecallEngine(trace_forward_fn=_forward, export_fn=_boom_export)
    drill = engine.create_drill(tenant_id=TENANT, drill_type=RecallType.FORWARD_TRACE, target_lot="START")
    result = await engine.execute_drill(drill)
    assert drill.status == RecallStatus.COMPLETED
    assert any("csv disk full" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_create_mock_recall_rejects_unknown_drill_type():
    reset_recall_engine()
    with pytest.raises(ValueError):
        await create_mock_recall(tenant_id=TENANT, drill_type="sideways_trace")
