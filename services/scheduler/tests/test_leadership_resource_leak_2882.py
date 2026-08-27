"""Regression tests for #2882 — leadership flaps must not strand resources.

Two halves were reported:

1. ``EmbeddedSchedulerRunner._run`` overwriting ``self._service`` without
   tearing the previous one down. **Already fixed on main** (``_retire_service``
   / ``_dispose_engines``); the tests here pin that behaviour so it cannot
   silently regress.
2. ``DistributedContext.wait_for_leadership`` returning without closing its
   dedicated advisory-lock connection. **Still live** — the ``return`` after
   the callback finishes, and the generic ``except Exception`` retry path,
   both drop the connection on the floor. This is the connection that is
   deliberately kept open for the whole leadership term with
   ``keepalives=1``, drawn from a pool the API process shares.

The tests count connections/engines across simulated flaps rather than
inspecting the source, so they fail for the real reason.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fakes that count what was opened and what was closed
# ---------------------------------------------------------------------------


class _FakeConnection:
    def __init__(self, engine, index):
        self._engine = engine
        self.index = index
        self.closed = False
        self.executed = []

    def execution_options(self, **kwargs):
        return self

    def execute(self, statement, params=None):
        sql = str(statement)
        self.executed.append(sql)
        if self.closed:
            raise AssertionError(f"execute() on a closed connection: {sql}")
        result = MagicMock()
        if "pg_try_advisory_lock" in sql:
            result.scalar.return_value = self._engine.grant_lock
        elif "pg_backend_pid" in sql:
            result.scalar.return_value = 4242
        else:
            result.scalar.return_value = None
        return result

    def close(self):
        self.closed = True
        self._engine.closed_count += 1


class _CountingEngine:
    """Stands in for the DistributedContext SQLAlchemy engine."""

    def __init__(self, grant_lock=True):
        self.grant_lock = grant_lock
        self.connections = []
        self.closed_count = 0
        self.disposed = 0

    def connect(self):
        conn = _FakeConnection(self, len(self.connections))
        self.connections.append(conn)
        return conn

    def dispose(self):
        self.disposed += 1

    @property
    def open_connections(self):
        return [c for c in self.connections if not c.closed]


def _make_context(engine):
    from services.scheduler.app.distributed import DistributedContext

    ctx = DistributedContext.__new__(DistributedContext)
    ctx.engine = engine
    ctx.database_url = "postgresql://fake/fake"
    ctx._is_leader = False
    ctx._leader_pid = None
    ctx._heartbeat_stop = threading.Event()
    ctx._heartbeat_thread = None
    return ctx


# ---------------------------------------------------------------------------
# #2882 half 2 — the advisory-lock connection
# ---------------------------------------------------------------------------


class TestAdvisoryLockConnectionIsReleased:
    def test_single_leadership_term_closes_its_connection(self):
        """One acquire → run → return must leave zero open connections."""
        engine = _CountingEngine(grant_lock=True)
        ctx = _make_context(engine)

        ctx.wait_for_leadership(callback=lambda: None, poll_interval=0)

        assert len(engine.connections) == 1, "expected exactly one election connection"
        assert engine.open_connections == [], (
            "wait_for_leadership returned without closing its dedicated "
            "advisory-lock connection — that connection is held for the whole "
            "leadership term with keepalives on, out of the pool the API shares"
        )

    @pytest.mark.parametrize("flaps", [1, 3, 10])
    def test_connections_do_not_accumulate_across_flaps(self, flaps):
        """N leadership flaps must leave 0 open connections, not N."""
        engine = _CountingEngine(grant_lock=True)

        for _ in range(flaps):
            ctx = _make_context(engine)
            ctx.wait_for_leadership(callback=lambda: None, poll_interval=0)

        assert len(engine.connections) == flaps
        assert engine.closed_count == flaps, (
            f"{flaps} leadership flap(s) opened {len(engine.connections)} "
            f"connection(s) but closed only {engine.closed_count} — each "
            "stranded connection consumes the shared DB connection budget"
        )
        assert engine.open_connections == []

    def test_crashing_callback_still_closes_the_connection(self):
        """A crashed workload must not strand the lock connection either.

        Note the ``return`` in the callback's ``finally`` block swallows the
        exception, so this exits by the same path as a clean finish — which
        is exactly why the missing ``close()`` bites on crashes too.
        """
        engine = _CountingEngine(grant_lock=True)
        ctx = _make_context(engine)

        def _boom():
            raise RuntimeError("scheduler workload crashed")

        ctx.wait_for_leadership(callback=_boom, poll_interval=0)

        assert engine.open_connections == [], "a crashed scheduler workload strands the advisory-lock connection"

    def test_unexpected_election_error_closes_the_connection_before_retrying(self):
        """The generic ``except Exception`` retry path leaks too.

        On a non-SQLAlchemyError the loop logs, sleeps, and restarts with
        ``conn = None`` — dropping the previous connection without closing
        it. Every retry strands one more.
        """
        engine = _CountingEngine(grant_lock=True)
        ctx = _make_context(engine)

        calls = {"n": 0}

        def _explode(self_conn, statement, params=None):
            calls["n"] += 1
            raise ValueError("proxy reset mid-poll")

        _FakeConnection.execute, original = _explode, _FakeConnection.execute
        try:
            # time.sleep is the only thing between the handler and the next
            # pass; raise out of it to stop after a single retry.
            with patch("services.scheduler.app.distributed.time.sleep", side_effect=StopIteration):
                with pytest.raises(StopIteration):
                    ctx.wait_for_leadership(callback=lambda: None, poll_interval=0)
        finally:
            _FakeConnection.execute = original

        assert calls["n"] >= 1, "the test did not reach the failing execute"
        assert engine.open_connections == [], (
            "the generic except-handler in the election loop drops its "
            "connection and loops back to conn = None — the old connection "
            "is never closed"
        )

    def test_unlock_is_still_issued_before_release(self):
        """Closing the connection must not skip pg_advisory_unlock."""
        engine = _CountingEngine(grant_lock=True)
        ctx = _make_context(engine)

        ctx.wait_for_leadership(callback=lambda: None, poll_interval=0)

        issued = " ".join(engine.connections[0].executed)
        assert "pg_advisory_unlock" in issued, (
            "leadership must be explicitly released, not merely dropped with "
            "the connection — a pooled connection can outlive the term"
        )

    def test_leader_flag_is_cleared_after_release(self):
        engine = _CountingEngine(grant_lock=True)
        ctx = _make_context(engine)
        ctx.wait_for_leadership(callback=lambda: None, poll_interval=0)
        assert ctx._is_leader is False


# ---------------------------------------------------------------------------
# #2882 half 1 — service teardown across flaps (already fixed; pinned here)
# ---------------------------------------------------------------------------


class TestServiceTeardownAcrossFlaps:
    def _runner_with_counted_services(self, flaps):
        from server.workers.embedded_scheduler import EmbeddedSchedulerRunner

        built = []

        def _factory():
            service = MagicMock()
            service.state_manager.engine = MagicMock()
            service.distributed_context.engine = MagicMock()
            built.append(service)
            if len(built) >= flaps:
                runner._stop_event.set()
            return service

        runner = EmbeddedSchedulerRunner()
        runner._REELECTION_DELAY_SECONDS = 0
        with patch("services.scheduler.service.SchedulerService", side_effect=_factory):
            runner._run()
        return built

    @pytest.mark.parametrize("flaps", [2, 5])
    def test_every_retired_service_is_shut_down_and_disposed(self, flaps):
        built = self._runner_with_counted_services(flaps)
        assert len(built) == flaps

        # Every service except the last (still current when the loop exits)
        # must have been shut down and had both engines disposed.
        for service in built[:-1]:
            service.shutdown.assert_called_once()
            service.state_manager.engine.dispose.assert_called_once()
            service.distributed_context.engine.dispose.assert_called_once()

    def test_stop_disposes_the_live_services_engines(self):
        from server.workers.embedded_scheduler import EmbeddedSchedulerRunner

        runner = EmbeddedSchedulerRunner()
        service = MagicMock()
        service.scheduler.running = True
        service.state_manager.engine = MagicMock()
        service.distributed_context.engine = MagicMock()
        runner._service = service

        runner.stop()

        service.state_manager.engine.dispose.assert_called_once()
        service.distributed_context.engine.dispose.assert_called_once()
