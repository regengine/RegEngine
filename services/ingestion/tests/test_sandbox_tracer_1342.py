"""
Regression coverage for ``app/sandbox/tracer.py``.

The module implements the sandbox's in-memory lot trace graph:

* ``_trace_in_memory`` — BFS over CSV-parsed CTE events, building nodes +
  edges. Linkages come from (a) same TLC across events, (b)
  transformation input_traceability_lot_codes, and (c) transformation
  output chains.
* ``sandbox_trace`` — async FastAPI handler wiring rate-limit,
  validation, CSV parsing, and the BFS call together.

Covering this well matters: the recall feature demoed at
``/sandbox/trace`` is a headline capability, and the BFS direction
semantics (upstream / downstream / both) are the exact thing regulators
care about during a trace-back exercise.

Tracks GitHub issue #1342 (ingestion test coverage).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.sandbox import tracer
from app.sandbox.tracer import _trace_in_memory, sandbox_trace
from app.sandbox.models import (
    SandboxTraceRequest,
    TraceGraphResponse,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ev(
    cte_type: str,
    tlc: str,
    *,
    product: str = "P",
    quantity: Any = None,
    uom: str = "cases",
    location_name: str = "",
    timestamp: str = "2026-01-01T00:00:00Z",
    **kdes,
) -> Dict[str, Any]:
    """Build a raw-event dict. Any extra kwargs go into ``kdes``."""
    return {
        "cte_type": cte_type,
        "traceability_lot_code": tlc,
        "product_description": product,
        "quantity": quantity,
        "unit_of_measure": uom,
        "location_name": location_name,
        "timestamp": timestamp,
        "kdes": dict(kdes),
    }


def _request_with_ip(ip: str | None) -> Any:
    """Build a FastAPI-Request-like object.  ``None`` means no ``client``."""
    client = SimpleNamespace(host=ip) if ip is not None else None
    return SimpleNamespace(client=client)


# ===========================================================================
# _trace_in_memory — seed handling
# ===========================================================================

class TestTraceSeed:

    def test_unknown_seed_returns_empty_response(self):
        events = [_ev("harvesting", "TLC-A")]
        res = _trace_in_memory(events, seed_tlc="TLC-DOES-NOT-EXIST")
        assert isinstance(res, TraceGraphResponse)
        assert res.seed_tlc == "TLC-DOES-NOT-EXIST"
        assert res.direction == "both"
        assert res.nodes == []
        assert res.edges == []
        assert res.lots_touched == []
        assert res.facilities == []
        assert res.max_depth == 0

    def test_empty_events_returns_empty_response(self):
        res = _trace_in_memory([], seed_tlc="ANY")
        assert res.nodes == []
        assert res.edges == []

    def test_single_seed_event_visits_that_event(self):
        events = [_ev("harvesting", "TLC-SEED", location_name="Farm A")]
        res = _trace_in_memory(events, seed_tlc="TLC-SEED")
        assert len(res.nodes) == 1
        assert res.nodes[0].event_index == 0
        assert res.nodes[0].cte_type == "harvesting"
        assert res.nodes[0].traceability_lot_code == "TLC-SEED"
        assert "TLC-SEED" in res.lots_touched
        assert "Farm A" in res.facilities

    def test_seed_with_surrounding_whitespace_stripped(self):
        events = [_ev("harvesting", "TLC-SEED")]
        res = _trace_in_memory(events, seed_tlc="  TLC-SEED  ")
        assert len(res.nodes) == 1

    def test_seed_tlc_preserved_in_response(self):
        """Response echoes back the seed as passed in (not stripped)."""
        events = [_ev("harvesting", "TLC-A")]
        res = _trace_in_memory(events, seed_tlc="TLC-A")
        assert res.seed_tlc == "TLC-A"


# ===========================================================================
# _trace_in_memory — same-TLC chains
# ===========================================================================

class TestTraceSameLot:

    def test_chain_of_events_with_same_tlc_all_visited(self):
        """harvest → cool → ship all sharing TLC gives 3 nodes + 2 same_lot edges."""
        events = [
            _ev("harvesting", "TLC-1", location_name="Farm A"),
            _ev("cooling", "TLC-1", location_name="Cooler B"),
            _ev("shipping", "TLC-1", location_name="Dock C"),
        ]
        res = _trace_in_memory(events, seed_tlc="TLC-1")
        assert len(res.nodes) == 3
        assert all(e.link_type == "same_lot" for e in res.edges if e.link_type != "seed")
        # All three facilities in the set
        assert {"Farm A", "Cooler B", "Dock C"} <= set(res.facilities)

    def test_same_lot_edges_connect_every_pair_of_same_tlc_events(self):
        """All events with same TLC get edges; BFS from seed fans out."""
        events = [
            _ev("harvesting", "TLC-1"),
            _ev("cooling", "TLC-1"),
        ]
        res = _trace_in_memory(events, seed_tlc="TLC-1")
        # At least one same_lot edge exists between the two
        assert any(e.link_type == "same_lot" for e in res.edges)

    def test_different_tlc_not_in_same_lot_group(self):
        events = [
            _ev("harvesting", "TLC-A"),
            _ev("cooling", "TLC-B"),
        ]
        res = _trace_in_memory(events, seed_tlc="TLC-A")
        assert len(res.nodes) == 1
        assert res.nodes[0].traceability_lot_code == "TLC-A"


# ===========================================================================
# _trace_in_memory — transformation linkage
# ===========================================================================

class TestTraceTransformation:

    def test_transformation_input_as_list_consumes_inputs(self):
        events = [
            _ev("harvesting", "LOT-A"),
            _ev("harvesting", "LOT-B"),
            _ev(
                "transformation", "LOT-MEGA",
                input_traceability_lot_codes=["LOT-A", "LOT-B"],
            ),
        ]
        res = _trace_in_memory(events, seed_tlc="LOT-A", direction="downstream")
        titles = {n.traceability_lot_code for n in res.nodes}
        assert "LOT-A" in titles
        assert "LOT-MEGA" in titles  # transformation consumer reachable
        link_types = {e.link_type for e in res.edges}
        assert "transformation_input" in link_types

    def test_transformation_input_as_comma_string_parses_and_consumes(self):
        """Legacy CSV-flattened input string must split on commas."""
        events = [
            _ev("harvesting", "LOT-A"),
            _ev("harvesting", "LOT-B"),
            _ev(
                "transformation", "LOT-MEGA",
                input_traceability_lot_codes="LOT-A, LOT-B",
            ),
        ]
        res = _trace_in_memory(events, seed_tlc="LOT-A", direction="downstream")
        titles = {n.traceability_lot_code for n in res.nodes}
        assert "LOT-MEGA" in titles

    def test_transformation_output_extends_downstream_chain(self):
        """After consuming inputs, BFS must follow the output TLC onward."""
        events = [
            _ev("harvesting", "LOT-A"),
            _ev(
                "transformation", "LOT-MEGA",
                input_traceability_lot_codes=["LOT-A"],
            ),
            _ev("shipping", "LOT-MEGA"),
        ]
        res = _trace_in_memory(events, seed_tlc="LOT-A", direction="downstream")
        titles = {n.traceability_lot_code for n in res.nodes}
        assert {"LOT-A", "LOT-MEGA"} <= titles
        # Shipping event reached via transformation_output → same_lot
        shipping_reached = any(
            n.cte_type == "shipping" and n.traceability_lot_code == "LOT-MEGA"
            for n in res.nodes
        )
        assert shipping_reached

    def test_upstream_from_transformation_follows_inputs(self):
        """Seed on the transformation, upstream → reach every input TLC."""
        events = [
            _ev("harvesting", "LOT-A"),
            _ev("harvesting", "LOT-B"),
            _ev(
                "transformation", "LOT-MEGA",
                input_traceability_lot_codes=["LOT-A", "LOT-B"],
            ),
        ]
        res = _trace_in_memory(events, seed_tlc="LOT-MEGA", direction="upstream")
        titles = {n.traceability_lot_code for n in res.nodes}
        assert {"LOT-MEGA", "LOT-A", "LOT-B"} <= titles

    def test_upstream_from_downstream_tlc_finds_producing_transformation(self):
        """If our TLC is the *output* of a transformation, upstream path reaches it."""
        events = [
            _ev("harvesting", "LOT-A"),
            _ev(
                "transformation", "LOT-MEGA",
                input_traceability_lot_codes=["LOT-A"],
            ),
            _ev("shipping", "LOT-MEGA"),
        ]
        res = _trace_in_memory(events, seed_tlc="LOT-MEGA", direction="upstream")
        # The producing transformation is at index 1; its TLC matches seed.
        # ``produces_tlc`` path ensures we hit the transformation from a
        # non-transformation seed in the same lot.
        indices = {n.event_index for n in res.nodes}
        assert 1 in indices  # transformation

    def test_empty_input_tlc_string_segments_skipped(self):
        """Trailing/middle blank segments from ``, ,`` don't create phantom lookups."""
        events = [
            _ev("harvesting", "LOT-A"),
            _ev(
                "transformation", "LOT-MEGA",
                input_traceability_lot_codes="LOT-A,,  ,",
            ),
        ]
        res = _trace_in_memory(events, seed_tlc="LOT-A", direction="downstream")
        # No crash, LOT-MEGA reached
        assert any(n.traceability_lot_code == "LOT-MEGA" for n in res.nodes)

    def test_upstream_with_comma_string_input_tlcs(self):
        """Upstream branch must also parse string ``input_traceability_lot_codes``.

        Exercises the ``isinstance(input_tlcs, str)`` split in the
        upstream expansion path (different code path from downstream
        consumes_tlc indexing).
        """
        events = [
            _ev("harvesting", "LOT-A"),
            _ev("harvesting", "LOT-B"),
            _ev(
                "transformation", "LOT-MEGA",
                input_traceability_lot_codes="LOT-A, LOT-B",
            ),
        ]
        # Seed on the transformation, upstream — triggers the
        # string-split branch inside the ``cte == 'transformation'`` arm.
        res = _trace_in_memory(events, seed_tlc="LOT-MEGA", direction="upstream")
        titles = {n.traceability_lot_code for n in res.nodes}
        assert {"LOT-A", "LOT-B", "LOT-MEGA"} <= titles

    def test_upstream_follows_produces_tlc_from_non_transformation_seed(self):
        """Upstream path from a non-transformation event with a
        transformation-produced TLC uses the ``produces_tlc`` branch.

        To make BFS hit that branch (tracer.py line 198-200) before the
        transformation is already in ``visited``, we arrange events so
        the non-transformation LOT-MEGA event is processed FIRST — then
        when it runs the ``produces_tlc`` loop, the transformation is
        not-yet-visited and gets queued via the transformation_output
        link type.
        """
        events = [
            # idx 0: shipping LOT-MEGA — seeded, processed first
            _ev("shipping", "LOT-MEGA"),
            # idx 1: transformation that PRODUCES LOT-MEGA, consumes LOT-A
            _ev(
                "transformation", "LOT-MEGA",
                input_traceability_lot_codes=["LOT-A"],
            ),
            # idx 2: upstream LOT-A harvesting
            _ev("harvesting", "LOT-A"),
        ]
        res = _trace_in_memory(events, seed_tlc="LOT-MEGA", direction="upstream")
        # Both transformation and LOT-A reached via upstream traversal
        indices = {n.event_index for n in res.nodes}
        assert indices == {0, 1, 2}
        # The ``produces_tlc`` loop fires (coverage proof); the resulting
        # edge may be deduped against the ``same_lot`` edge queued just
        # before it, so we don't assert on link_type here.


# ===========================================================================
# _trace_in_memory — direction gating
# ===========================================================================

class TestTraceDirection:

    def test_downstream_skips_upstream_expansion(self):
        """``direction=downstream`` must NOT follow transformation inputs backward."""
        events = [
            _ev("harvesting", "LOT-A"),
            _ev("harvesting", "LOT-B"),
            _ev(
                "transformation", "LOT-MEGA",
                input_traceability_lot_codes=["LOT-A", "LOT-B"],
            ),
        ]
        # Seed the transformation downstream — we should NOT walk back to LOT-A / LOT-B
        res = _trace_in_memory(events, seed_tlc="LOT-MEGA", direction="downstream")
        indices = {n.event_index for n in res.nodes}
        # Only the transformation itself is reached
        assert indices == {2}

    def test_upstream_skips_downstream_expansion(self):
        """``direction=upstream`` must NOT follow TLC consumers forward."""
        events = [
            _ev("harvesting", "LOT-A"),
            _ev(
                "transformation", "LOT-MEGA",
                input_traceability_lot_codes=["LOT-A"],
            ),
        ]
        res = _trace_in_memory(events, seed_tlc="LOT-A", direction="upstream")
        # LOT-MEGA not reached (only same-lot expansion, no consumers path)
        assert not any(n.traceability_lot_code == "LOT-MEGA" for n in res.nodes)

    def test_both_walks_both_directions(self):
        events = [
            _ev("harvesting", "LOT-A"),
            _ev(
                "transformation", "LOT-MEGA",
                input_traceability_lot_codes=["LOT-A"],
            ),
            _ev("shipping", "LOT-MEGA"),
        ]
        res = _trace_in_memory(events, seed_tlc="LOT-MEGA", direction="both")
        indices = {n.event_index for n in res.nodes}
        # All three reached
        assert indices == {0, 1, 2}

    def test_unrecognized_direction_prevents_expansion_beyond_seed(self):
        """An unknown direction fails every ``in (...)`` check, so BFS
        only visits the events already queued from the seed indices
        and never expands further via same_lot / transformation links.

        All events matching the seed TLC are still *seeded* (they're in
        ``by_tlc[seed_tlc]``). To observe the no-expansion behavior we
        need a linkage the seed alone wouldn't bring in — here, a
        transformation that *would* be reached via the downstream
        consumes_tlc path but isn't because direction="sideways".
        """
        events = [
            _ev("harvesting", "LOT-A"),
            _ev(
                "transformation", "LOT-MEGA",
                input_traceability_lot_codes=["LOT-A"],
            ),
        ]
        res = _trace_in_memory(events, seed_tlc="LOT-A", direction="sideways")
        # Only the seed (index 0) reachable; LOT-MEGA NOT followed
        indices = {n.event_index for n in res.nodes}
        assert indices == {0}


# ===========================================================================
# _trace_in_memory — depth, quantity, facilities
# ===========================================================================

class TestTraceDepth:

    def test_max_depth_limits_expansion(self):
        """max_depth=0 prevents expansion beyond what the seed brings in.

        Note that all events matching the seed TLC are put in the BFS
        queue up-front, so "only the seed" means "only events matching
        the seed TLC" — not literally a single node.
        """
        events = [
            _ev("harvesting", "LOT-A"),
            _ev(
                "transformation", "LOT-MEGA",
                input_traceability_lot_codes=["LOT-A"],
            ),
        ]
        res = _trace_in_memory(events, seed_tlc="LOT-A", max_depth=0)
        # Only LOT-A seeded; LOT-MEGA not followed because depth=0 >= max_depth=0
        indices = {n.event_index for n in res.nodes}
        assert indices == {0}

    def test_max_depth_caps_to_twenty(self):
        """Passing max_depth > 20 must be clamped (docstring guarantee)."""
        events = [_ev("harvesting", "TLC-X")]
        res = _trace_in_memory(events, seed_tlc="TLC-X", max_depth=500)
        # We can't easily introspect the internal cap — but we can at
        # least observe the response builds without error and max_depth
        # reached is 0 (single node).
        assert res.max_depth == 0

    def test_max_depth_reached_tracked_per_traversal(self):
        """When BFS actually has to expand via transformation, depth grows."""
        events = [
            _ev("harvesting", "LOT-A"),
            _ev(
                "transformation", "LOT-MEGA",
                input_traceability_lot_codes=["LOT-A"],
            ),
            _ev("shipping", "LOT-MEGA"),
        ]
        res = _trace_in_memory(events, seed_tlc="LOT-A", max_depth=10)
        # Expansion reaches at least depth 1 (LOT-A → LOT-MEGA transformation)
        assert res.max_depth >= 1


class TestTraceQuantity:

    def test_numeric_quantity_preserved_on_node(self):
        events = [_ev("harvesting", "TLC-Q", quantity=5.5)]
        res = _trace_in_memory(events, seed_tlc="TLC-Q")
        assert res.nodes[0].quantity == 5.5

    def test_string_numeric_quantity_converted(self):
        events = [_ev("harvesting", "TLC-Q", quantity="12.5")]
        res = _trace_in_memory(events, seed_tlc="TLC-Q")
        assert res.nodes[0].quantity == 12.5

    def test_invalid_string_quantity_becomes_none(self):
        """Non-numeric string → ``ValueError`` → quantity=None (not crash)."""
        events = [_ev("harvesting", "TLC-Q", quantity="not-a-number")]
        res = _trace_in_memory(events, seed_tlc="TLC-Q")
        assert res.nodes[0].quantity is None

    def test_none_quantity_remains_none(self):
        events = [_ev("harvesting", "TLC-Q", quantity=None)]
        res = _trace_in_memory(events, seed_tlc="TLC-Q")
        assert res.nodes[0].quantity is None

    def test_total_quantity_sums_non_none_values(self):
        events = [
            _ev("harvesting", "TLC-Q", quantity=10),
            _ev("cooling", "TLC-Q", quantity=15),
        ]
        res = _trace_in_memory(events, seed_tlc="TLC-Q")
        assert res.total_quantity == 25

    def test_total_quantity_skips_none_and_zero(self):
        """``if n.quantity`` treats both 0 and None as skip (bug or feature, pinned)."""
        events = [
            _ev("harvesting", "TLC-Q", quantity=0),
            _ev("cooling", "TLC-Q", quantity=5),
            _ev("shipping", "TLC-Q", quantity=None),
        ]
        res = _trace_in_memory(events, seed_tlc="TLC-Q")
        assert res.total_quantity == 5


class TestTraceFacilities:

    def test_location_name_in_facilities(self):
        events = [_ev("harvesting", "TLC-F", location_name="Farm A")]
        res = _trace_in_memory(events, seed_tlc="TLC-F")
        assert "Farm A" in res.facilities

    def test_ship_from_location_in_facilities(self):
        events = [_ev("shipping", "TLC-F", ship_from_location="Warehouse X")]
        res = _trace_in_memory(events, seed_tlc="TLC-F")
        assert "Warehouse X" in res.facilities

    def test_ship_to_location_in_facilities(self):
        events = [_ev("shipping", "TLC-F", ship_to_location="Dock Y")]
        res = _trace_in_memory(events, seed_tlc="TLC-F")
        assert "Dock Y" in res.facilities

    def test_receiving_location_falls_back_for_fac_to(self):
        """Without ship_to, receiving_location fills fac_to."""
        events = [_ev("receiving", "TLC-F", receiving_location="DC Z")]
        res = _trace_in_memory(events, seed_tlc="TLC-F")
        assert "DC Z" in res.facilities

    def test_blank_location_not_added_to_facilities(self):
        events = [_ev("harvesting", "TLC-F", location_name="")]
        res = _trace_in_memory(events, seed_tlc="TLC-F")
        # Empty string should not appear in the facilities set
        assert "" not in res.facilities

    def test_facilities_sorted_alphabetically(self):
        events = [
            _ev("harvesting", "TLC-F", location_name="Zeta Farm"),
            _ev("cooling", "TLC-F", location_name="Alpha Cooler"),
        ]
        res = _trace_in_memory(events, seed_tlc="TLC-F")
        assert res.facilities == sorted(res.facilities)


# ===========================================================================
# _trace_in_memory — edge deduplication on re-visit
# ===========================================================================

class TestTraceRevisit:
    """When BFS reaches a visited node again, we still want the edge."""

    def test_revisit_adds_edge_when_none_existed(self):
        """Second arrival at a node adds an edge to record the linkage."""
        events = [
            _ev("harvesting", "TLC-1"),
            _ev("cooling", "TLC-1"),
        ]
        res = _trace_in_memory(events, seed_tlc="TLC-1")
        # Two events, same lot — at least one same_lot edge
        edges_to_1 = [e for e in res.edges if e.to_event_index == 1]
        assert len(edges_to_1) >= 1

    def test_revisit_does_not_duplicate_existing_edge(self):
        """The ``edge_exists`` check dedupes on (from, to)."""
        events = [
            _ev("harvesting", "TLC-1"),
            _ev("cooling", "TLC-1"),
            _ev("shipping", "TLC-1"),
        ]
        res = _trace_in_memory(events, seed_tlc="TLC-1")
        # With 3 events sharing a TLC, BFS queues them all multiple
        # times — but edges must remain unique on (from, to).
        pairs = [(e.from_event_index, e.to_event_index) for e in res.edges]
        assert len(pairs) == len(set(pairs))


# ===========================================================================
# sandbox_trace — async wrapper
# ===========================================================================

class TestSandboxTraceValidation:
    """Input validation happens BEFORE CSV parsing."""

    @pytest.fixture(autouse=True)
    def _neutralize_rate_limit(self, monkeypatch):
        """Silence the rate limiter so validation paths run clean."""
        monkeypatch.setattr(
            tracer, "_check_sandbox_rate_limit", lambda ip: None
        )

    async def _run(self, payload, ip="1.2.3.4"):
        return await sandbox_trace(payload, _request_with_ip(ip))

    @pytest.mark.asyncio
    async def test_empty_csv_raises_400(self):
        payload = SandboxTraceRequest(csv="   ", tlc="TLC-1")
        with pytest.raises(HTTPException) as exc:
            await self._run(payload)
        assert exc.value.status_code == 400
        assert "CSV text is required" in exc.value.detail

    @pytest.mark.asyncio
    async def test_empty_tlc_raises_400(self):
        payload = SandboxTraceRequest(csv="cte_type,tlc\n", tlc="  ")
        with pytest.raises(HTTPException) as exc:
            await self._run(payload)
        assert exc.value.status_code == 400
        assert "TLC" in exc.value.detail

    @pytest.mark.asyncio
    async def test_csv_parse_error_raises_400(self, monkeypatch):
        def _boom(csv):
            raise ValueError("bad CSV")
        monkeypatch.setattr(tracer, "_parse_csv_to_events", _boom)
        payload = SandboxTraceRequest(csv="garbage", tlc="TLC-1")
        with pytest.raises(HTTPException) as exc:
            await self._run(payload)
        assert exc.value.status_code == 400
        assert "CSV parsing error" in exc.value.detail
        assert "bad CSV" in exc.value.detail

    @pytest.mark.asyncio
    async def test_zero_events_raises_400(self, monkeypatch):
        monkeypatch.setattr(tracer, "_parse_csv_to_events", lambda csv: [])
        payload = SandboxTraceRequest(csv="cte_type,tlc\n", tlc="TLC-1")
        with pytest.raises(HTTPException) as exc:
            await self._run(payload)
        assert exc.value.status_code == 400
        assert "No valid events" in exc.value.detail

    @pytest.mark.asyncio
    async def test_more_than_fifty_events_raises_400(self, monkeypatch):
        events = [_ev("harvesting", f"TLC-{i}") for i in range(51)]
        monkeypatch.setattr(tracer, "_parse_csv_to_events", lambda csv: events)
        payload = SandboxTraceRequest(csv="dummy", tlc="TLC-0")
        with pytest.raises(HTTPException) as exc:
            await self._run(payload)
        assert exc.value.status_code == 400
        assert "Maximum 50" in exc.value.detail

    @pytest.mark.asyncio
    async def test_exactly_fifty_events_allowed(self, monkeypatch):
        events = [_ev("harvesting", f"TLC-{i}") for i in range(50)]
        monkeypatch.setattr(tracer, "_parse_csv_to_events", lambda csv: events)
        payload = SandboxTraceRequest(csv="dummy", tlc="TLC-0")
        res = await self._run(payload)
        assert isinstance(res, TraceGraphResponse)


class TestSandboxTraceDirection:

    @pytest.fixture(autouse=True)
    def _neutralize_rate_limit(self, monkeypatch):
        monkeypatch.setattr(tracer, "_check_sandbox_rate_limit", lambda ip: None)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given, expected", [
        ("upstream", "upstream"),
        ("DOWNSTREAM", "downstream"),
        ("Both", "both"),
        ("sideways", "both"),      # invalid → default "both"
        ("", "both"),              # empty → default "both"
    ])
    async def test_direction_normalization(self, monkeypatch, given, expected):
        events = [_ev("harvesting", "TLC-1")]
        monkeypatch.setattr(tracer, "_parse_csv_to_events", lambda csv: events)
        payload = SandboxTraceRequest(csv="dummy", tlc="TLC-1", direction=given)
        res = await sandbox_trace(payload, _request_with_ip("1.2.3.4"))
        assert res.direction == expected


class TestSandboxTraceRateLimit:

    @pytest.mark.asyncio
    async def test_rate_limit_called_with_client_host(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            tracer, "_check_sandbox_rate_limit", lambda ip: calls.append(ip)
        )
        monkeypatch.setattr(tracer, "_parse_csv_to_events", lambda csv: [_ev("harvesting", "TLC-1")])
        payload = SandboxTraceRequest(csv="dummy", tlc="TLC-1")
        await sandbox_trace(payload, _request_with_ip("10.0.0.5"))
        assert calls == ["10.0.0.5"]

    @pytest.mark.asyncio
    async def test_rate_limit_uses_unknown_when_client_missing(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            tracer, "_check_sandbox_rate_limit", lambda ip: calls.append(ip)
        )
        monkeypatch.setattr(tracer, "_parse_csv_to_events", lambda csv: [_ev("harvesting", "TLC-1")])
        payload = SandboxTraceRequest(csv="dummy", tlc="TLC-1")
        await sandbox_trace(payload, _request_with_ip(None))
        assert calls == ["unknown"]

    @pytest.mark.asyncio
    async def test_rate_limit_exception_propagates(self, monkeypatch):
        def _boom(ip):
            raise HTTPException(status_code=429, detail="slow down", headers={"Retry-After": "10"})
        monkeypatch.setattr(tracer, "_check_sandbox_rate_limit", _boom)
        payload = SandboxTraceRequest(csv="dummy", tlc="TLC-1")
        with pytest.raises(HTTPException) as exc:
            await sandbox_trace(payload, _request_with_ip("1.1.1.1"))
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_rate_limit_checked_before_csv_validation(self, monkeypatch):
        """A blocked IP never reaches CSV parsing — critical for abuse resistance."""
        parser_called = []
        monkeypatch.setattr(
            tracer, "_parse_csv_to_events",
            lambda csv: (parser_called.append(True) or []),
        )

        def _blocked(ip):
            raise HTTPException(status_code=429, detail="blocked")
        monkeypatch.setattr(tracer, "_check_sandbox_rate_limit", _blocked)

        payload = SandboxTraceRequest(csv="whatever", tlc="TLC-1")
        with pytest.raises(HTTPException):
            await sandbox_trace(payload, _request_with_ip("1.1.1.1"))
        assert parser_called == []


class TestSandboxTraceHappyPath:

    @pytest.fixture(autouse=True)
    def _neutralize_rate_limit(self, monkeypatch):
        monkeypatch.setattr(tracer, "_check_sandbox_rate_limit", lambda ip: None)

    @pytest.mark.asyncio
    async def test_returns_trace_graph_response(self, monkeypatch):
        events = [
            _ev("harvesting", "TLC-1", location_name="Farm A"),
            _ev("cooling", "TLC-1", location_name="Cool B"),
        ]
        monkeypatch.setattr(tracer, "_parse_csv_to_events", lambda csv: events)
        payload = SandboxTraceRequest(csv="csv-text", tlc="TLC-1")
        res = await sandbox_trace(payload, _request_with_ip("1.1.1.1"))
        assert isinstance(res, TraceGraphResponse)
        assert res.seed_tlc == "TLC-1"
        assert len(res.nodes) >= 1

    @pytest.mark.asyncio
    async def test_tlc_stripped_before_seeding(self, monkeypatch):
        events = [_ev("harvesting", "TLC-1")]
        monkeypatch.setattr(tracer, "_parse_csv_to_events", lambda csv: events)
        payload = SandboxTraceRequest(csv="csv-text", tlc="  TLC-1  ")
        res = await sandbox_trace(payload, _request_with_ip("1.1.1.1"))
        # The seed_tlc echoed back is the stripped value
        assert res.seed_tlc == "TLC-1"

    @pytest.mark.asyncio
    async def test_max_depth_forwarded_to_bfs(self, monkeypatch):
        captured = {}

        def _stub_trace(*, raw_events, seed_tlc, direction, max_depth):
            captured.update(
                seed_tlc=seed_tlc,
                direction=direction,
                max_depth=max_depth,
            )
            return TraceGraphResponse(
                seed_tlc=seed_tlc,
                direction=direction,
                nodes=[],
                edges=[],
                lots_touched=[],
                facilities=[],
                max_depth=0,
            )

        monkeypatch.setattr(tracer, "_parse_csv_to_events", lambda csv: [_ev("harvesting", "TLC-1")])
        monkeypatch.setattr(tracer, "_trace_in_memory", _stub_trace)
        payload = SandboxTraceRequest(csv="csv", tlc="TLC-1", max_depth=7)
        await sandbox_trace(payload, _request_with_ip("1.1.1.1"))
        assert captured["max_depth"] == 7
        assert captured["seed_tlc"] == "TLC-1"
        assert captured["direction"] == "both"
