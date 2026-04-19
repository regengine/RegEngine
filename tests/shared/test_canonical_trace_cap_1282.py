"""
Regression tests for #1282 — ``trace_forward`` / ``trace_backward``
used to accumulate BFS results without a ceiling. ``visited`` bounded
node revisits so the BFS eventually terminated, but ``results`` itself
had no cap: a wide transformation tree (depth × fan-out) could blow
up memory and OOM the worker. A malicious or misconfigured tenant
could DoS the service just by creating many transformations.

The fix adds an explicit ``max_results`` parameter (default 10_000)
and returns ``(links, truncated)``. ``truncated=True`` signals the BFS
stopped early; callers must surface the flag (or fail-closed if
completeness is required for compliance).

These tests drive the writer with a mocked session so we assert the
cap semantics without touching Postgres.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from shared.canonical_persistence.writer import CanonicalEventStore


# ---------------------------------------------------------------------------
# Helpers — mimic a transformation graph via a scripted session.
# ---------------------------------------------------------------------------


class _ScriptedRows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _GraphSession:
    """A FakeSession that serves trace queries from an in-memory
    adjacency map. ``adjacency[(direction, tenant, tlc)]`` -> list of
    child TLCs. 'direction' is ``"fwd"`` for ``input_tlc=`` queries,
    ``"bwd"`` for ``output_tlc=`` queries.
    """

    def __init__(self, forward: Dict[str, List[str]] | None = None,
                 backward: Dict[str, List[str]] | None = None):
        self.forward = forward or {}
        self.backward = backward or {}
        self.call_count = 0

    def execute(self, stmt, params=None):
        self.call_count += 1
        sql = str(getattr(stmt, "text", stmt))
        params = params or {}
        tlc = params.get("tlc")
        if "input_tlc = :tlc" in sql:
            children = self.forward.get(tlc, [])
            rows = [
                (c, str(uuid4()), "commingling", 1.0, "CS", 1.0)
                for c in children
            ]
        elif "output_tlc = :tlc" in sql:
            children = self.backward.get(tlc, [])
            rows = [
                (c, str(uuid4()), "commingling", 1.0, "CS", 1.0)
                for c in children
            ]
        else:
            rows = []
        return _ScriptedRows(rows)


# ---------------------------------------------------------------------------
# #1282 — return type contract
# ---------------------------------------------------------------------------


class TestTraceReturnsTruncationFlag_Issue1282:
    """Before the fix callers got ``List[Dict]``. Now they get
    ``(List[Dict], bool)``. The tuple return is load-bearing: a caller
    that ignores it and just writes ``links = store.trace_forward(...)``
    will be obviously wrong at type-check time."""

    def test_trace_forward_returns_tuple(self):
        session = _GraphSession(forward={"L0": ["L1"], "L1": []})
        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)

        result = store.trace_forward("tenant-1", "L0", max_depth=5)
        assert isinstance(result, tuple)
        assert len(result) == 2
        links, truncated = result
        assert isinstance(links, list)
        assert isinstance(truncated, bool)

    def test_trace_backward_returns_tuple(self):
        session = _GraphSession(backward={"L2": ["L1"], "L1": ["L0"], "L0": []})
        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)

        result = store.trace_backward("tenant-1", "L2", max_depth=5)
        assert isinstance(result, tuple)
        links, truncated = result
        assert links
        assert truncated is False


# ---------------------------------------------------------------------------
# #1282 — max_results cap enforcement
# ---------------------------------------------------------------------------


class TestMaxResultsCap_Issue1282:
    def test_trace_forward_caps_at_max_results(self):
        """A single node with 1000 children: with ``max_results=50`` the
        call must return exactly 50 links and ``truncated=True``."""
        fan_out = [f"L{i}" for i in range(1000)]
        session = _GraphSession(forward={"ROOT": fan_out, **{c: [] for c in fan_out}})
        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)

        links, truncated = store.trace_forward("tenant-1", "ROOT", max_results=50)
        assert len(links) == 50
        assert truncated is True

    def test_trace_backward_caps_at_max_results(self):
        fan_in = [f"L{i}" for i in range(1000)]
        session = _GraphSession(backward={"ROOT": fan_in, **{c: [] for c in fan_in}})
        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)

        links, truncated = store.trace_backward("tenant-1", "ROOT", max_results=50)
        assert len(links) == 50
        assert truncated is True

    def test_trace_forward_does_not_truncate_when_under_cap(self):
        session = _GraphSession(forward={"L0": ["L1"], "L1": ["L2"], "L2": []})
        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)

        links, truncated = store.trace_forward("tenant-1", "L0", max_results=100)
        assert truncated is False
        assert len(links) == 2  # L0→L1, L1→L2

    def test_truncation_stops_further_db_queries(self):
        """Once we hit the cap, the BFS should break immediately — no
        reason to keep hitting Postgres to discover rows we'll just
        throw away. Proves the fix also defends the DB from the blast
        radius, not just worker memory."""
        # Two levels of 1000 children each. Cap at 5.
        session = _GraphSession(
            forward={
                "ROOT": [f"A{i}" for i in range(1000)],
                **{f"A{i}": [f"B{j}" for j in range(1000)] for i in range(1000)},
                **{f"B{j}": [] for j in range(1000)},
            }
        )
        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)

        links, truncated = store.trace_forward("tenant-1", "ROOT", max_depth=10, max_results=5)
        assert len(links) == 5
        assert truncated is True
        # 1 query to expand ROOT, hit the cap while reading its children,
        # break out. Should NOT have issued thousands of queries for A0..A999.
        assert session.call_count == 1

    def test_default_cap_is_10000(self):
        """The default cap is 10_000 — documented and tested so the
        value doesn't drift via a stray default-arg change."""
        # Simulate exactly 10_001 children to exceed the default cap.
        fan_out = [f"L{i}" for i in range(10_001)]
        session = _GraphSession(forward={"ROOT": fan_out, **{c: [] for c in fan_out}})
        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)

        links, truncated = store.trace_forward("tenant-1", "ROOT", max_depth=2)
        assert len(links) == 10_000
        assert truncated is True


# ---------------------------------------------------------------------------
# #1282 — cycle handling preserved (regression guard)
# ---------------------------------------------------------------------------


class TestCyclePreservation_Issue1282:
    """The pre-fix ``visited`` cycle guard must still work. We add a
    result cap but do NOT weaken cycle detection — an adversary who
    plants a cycle must still not be able to make the BFS loop."""

    def test_cycle_does_not_loop_forever(self):
        # L0 -> L1 -> L2 -> L0 (cycle)
        session = _GraphSession(forward={"L0": ["L1"], "L1": ["L2"], "L2": ["L0"]})
        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)

        links, truncated = store.trace_forward("tenant-1", "L0", max_depth=20, max_results=1000)
        # BFS visits each node once: L0, L1, L2 — emits 3 links then stops.
        assert len(links) == 3
        # The traversal completed naturally, not via the cap.
        assert truncated is False


# ---------------------------------------------------------------------------
# #1282 — max_depth still bounds traversal independently of max_results
# ---------------------------------------------------------------------------


class TestMaxDepthUnchanged_Issue1282:
    def test_max_depth_default_is_5(self):
        """Regression guard: the ``max_depth`` default is part of the
        documented contract (see #1282 "Document and test the
        max_depth default")."""
        import inspect
        sig = inspect.signature(CanonicalEventStore.trace_forward)
        assert sig.parameters["max_depth"].default == 5

    def test_max_depth_stops_before_max_results(self):
        """A deep chain with fan-out of 1 per level, capped at depth 3:
        should return exactly 3 links regardless of max_results."""
        chain = {f"L{i}": [f"L{i+1}"] for i in range(20)}
        chain["L20"] = []
        session = _GraphSession(forward=chain)
        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)

        links, truncated = store.trace_forward("tenant-1", "L0", max_depth=3, max_results=1000)
        assert len(links) == 3
        assert truncated is False
