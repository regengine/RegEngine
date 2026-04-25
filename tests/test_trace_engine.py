"""
Unit tests for the in-memory lot trace engine.

Tests cover:
    - Forward (downstream) tracing following same-lot + transformation links
    - Backward (upstream) tracing through input_traceability_lot_codes
    - Bidirectional tracing reaches the full graph
    - Empty / missing TLC returns empty result
    - Max depth limiting
    - Edge count and link types
"""

from __future__ import annotations

import pytest

from app.sandbox.csv_parser import _parse_csv_to_events
from app.sandbox.tracer import _trace_in_memory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MULTI_LOT_CSV = """\
cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,input_traceability_lot_codes
harvesting,LOT-A,Romaine Lettuce,1000,lbs,Farm Alpha,2026-03-10T08:00:00Z,
shipping,LOT-A,Romaine Lettuce,1000,lbs,Farm Alpha DC,2026-03-11T06:00:00Z,
receiving,LOT-A,Romaine Lettuce,1000,lbs,Processing Plant,2026-03-11T14:00:00Z,
harvesting,LOT-B,Iceberg Lettuce,500,lbs,Farm Beta,2026-03-10T09:00:00Z,
shipping,LOT-B,Iceberg Lettuce,500,lbs,Farm Beta DC,2026-03-11T07:00:00Z,
receiving,LOT-B,Iceberg Lettuce,500,lbs,Processing Plant,2026-03-11T15:00:00Z,
transformation,LOT-MEGA,Mixed Salad,1400,lbs,Processing Plant,2026-03-12T10:00:00Z,"LOT-A,LOT-B"
shipping,LOT-MEGA,Mixed Salad,1400,lbs,Processing Plant,2026-03-13T06:00:00Z,
receiving,LOT-MEGA,Mixed Salad,1400,lbs,Retailer,2026-03-13T14:00:00Z,"""

SIMPLE_CSV = """\
cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp
harvesting,LOT-001,Romaine Lettuce,2000,lbs,Valley Fresh Farms,2026-03-12T08:00:00Z
shipping,LOT-001,Romaine Lettuce,2000,lbs,Valley Fresh DC,2026-03-13T06:00:00Z
receiving,LOT-001,Romaine Lettuce,1900,lbs,FreshCo Distribution,2026-03-13T14:00:00Z"""


@pytest.fixture
def multi_lot_events():
    return _parse_csv_to_events(MULTI_LOT_CSV)


@pytest.fixture
def simple_events():
    return _parse_csv_to_events(SIMPLE_CSV)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDownstreamTrace:
    """Trace forward (downstream) from a source lot."""

    def test_downstream_from_source_reaches_transformation(self, multi_lot_events):
        result = _trace_in_memory(multi_lot_events, "LOT-A", "downstream")
        lots = set(result.lots_touched)
        assert "LOT-A" in lots
        assert "LOT-MEGA" in lots
        # Should NOT reach LOT-B (separate input)
        assert "LOT-B" not in lots

    def test_downstream_finds_all_lot_a_events(self, multi_lot_events):
        result = _trace_in_memory(multi_lot_events, "LOT-A", "downstream")
        lot_a_nodes = [n for n in result.nodes if n.traceability_lot_code == "LOT-A"]
        assert len(lot_a_nodes) == 3  # harvest, ship, receive

    def test_downstream_follows_through_to_retailer(self, multi_lot_events):
        result = _trace_in_memory(multi_lot_events, "LOT-A", "downstream")
        facilities = set(result.facilities)
        assert "Retailer" in facilities

    def test_downstream_node_count(self, multi_lot_events):
        result = _trace_in_memory(multi_lot_events, "LOT-A", "downstream")
        # LOT-A: harvest, ship, receive (3) + LOT-MEGA: transform, ship, receive (3) = 6
        assert len(result.nodes) == 6


class TestUpstreamTrace:
    """Trace backward (upstream) from a finished product."""

    def test_upstream_from_mega_reaches_both_inputs(self, multi_lot_events):
        result = _trace_in_memory(multi_lot_events, "LOT-MEGA", "upstream")
        lots = set(result.lots_touched)
        assert "LOT-A" in lots
        assert "LOT-B" in lots
        assert "LOT-MEGA" in lots

    def test_upstream_finds_all_events(self, multi_lot_events):
        result = _trace_in_memory(multi_lot_events, "LOT-MEGA", "upstream")
        assert len(result.nodes) == 9  # All events in the CSV

    def test_upstream_finds_source_farms(self, multi_lot_events):
        result = _trace_in_memory(multi_lot_events, "LOT-MEGA", "upstream")
        facilities = set(result.facilities)
        assert "Farm Alpha" in facilities
        assert "Farm Beta" in facilities


class TestBidirectionalTrace:
    """Trace in both directions."""

    def test_both_from_middle_lot_reaches_everything(self, multi_lot_events):
        result = _trace_in_memory(multi_lot_events, "LOT-A", "both")
        assert len(result.nodes) == 9
        assert len(result.lots_touched) == 3

    def test_both_has_edges(self, multi_lot_events):
        result = _trace_in_memory(multi_lot_events, "LOT-A", "both")
        assert len(result.edges) > 0
        link_types = {e.link_type for e in result.edges}
        assert "same_lot" in link_types


class TestSimpleChain:
    """Simple single-lot chain (no transformations)."""

    def test_simple_trace_finds_all_events(self, simple_events):
        result = _trace_in_memory(simple_events, "LOT-001", "both")
        assert len(result.nodes) == 3
        assert result.lots_touched == ["LOT-001"]

    def test_simple_total_quantity(self, simple_events):
        result = _trace_in_memory(simple_events, "LOT-001", "both")
        # 2000 + 2000 + 1900
        assert result.total_quantity == 5900.0


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_missing_tlc_returns_empty(self, multi_lot_events):
        result = _trace_in_memory(multi_lot_events, "NONEXISTENT", "both")
        assert len(result.nodes) == 0
        assert result.max_depth == 0

    def test_max_depth_limits_traversal(self, multi_lot_events):
        # max_depth=0 means only seed lot events, no traversal beyond them
        result = _trace_in_memory(multi_lot_events, "LOT-A", "downstream", max_depth=0)
        # Should only find LOT-A events at depth 0
        assert all(n.traceability_lot_code == "LOT-A" for n in result.nodes)
        assert len(result.nodes) == 3

    def test_empty_events_returns_empty(self):
        result = _trace_in_memory([], "LOT-A", "both")
        assert len(result.nodes) == 0

    def test_max_depth_capped_at_20(self, multi_lot_events):
        result = _trace_in_memory(multi_lot_events, "LOT-A", "both", max_depth=100)
        # Should not crash, just cap at 20
        assert result.max_depth <= 20
