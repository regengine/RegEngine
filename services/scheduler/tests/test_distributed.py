"""Focused tests for services/scheduler/app/distributed.py.

Covers the main public behavior of the leader-election module that the
issue-scoped suites (test_leadership_flag, test_leader_heartbeat_1142,
test_leadership_resource_leak_2882) do not: the ``leadership_claim``
context manager (standby polling, acquisition, release, DB-error retry),
the ``wait_for_leadership`` standby and crash paths, the
``_release_election_connection`` teardown helper, and the
``_signal_leadership_lost`` ordering guarantee.

All engines are in-memory fakes. No network, no database, no sleeps
beyond ``time.sleep(0)``; the heartbeat thread is parked on a long
interval so it never probes during these tests.
"""

from __future__ import annotations

import threading
from typing import Any, List
from unittest.mock import MagicMock

from app.distributed import (
    SCHEDULER_LEADER_LOCK_ID,
    DistributedContext,
    _release_election_connection,
)
from sqlalchemy.exc import SQLAlchemyError

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _ScriptedResult:
    def __init__(self, script: List[Any]):
        self._script = script

    def scalar(self):
        if not self._script:
            return None
        entry = self._script.pop(0)
        if isinstance(entry, BaseException):
            raise entry
        return entry


class _ScriptedConnection:
    """One advisory-lock connection with a scripted scalar() sequence."""

    def __init__(self, script: List[Any]):
        self._script = list(script)
        self.executed: List[str] = []
        self.closed = False

    def execution_options(self, **_kwargs):
        return self

    def execute(self, statement, params=None):
        sql = str(statement)
        self.executed.append(sql)
        return _ScriptedResult(self._script)

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


class _ScriptedEngine:
    """Engine whose connect() serves queued connections or raises queued errors."""

    def __init__(self, effects: List[Any]):
        self._effects = list(effects)
        self.connect_count = 0

    def connect(self):
        self.connect_count += 1
        effect = self._effects.pop(0)
        if isinstance(effect, BaseException):
            raise effect
        return effect


def _make_ctx(engine) -> DistributedContext:
    """Build a DistributedContext around a fake engine (no settings I/O)."""
    ctx = DistributedContext.__new__(DistributedContext)
    ctx.database_url = "postgresql://fake/fake"
    ctx.engine = engine
    ctx._is_leader = False
    ctx._leader_pid = None
    ctx._heartbeat_stop = threading.Event()
    ctx._heartbeat_thread = None
    return ctx


def _election_conn(*scalar_script: Any) -> _ScriptedConnection:
    return _ScriptedConnection(list(scalar_script))


# ---------------------------------------------------------------------------
# Module constant
# ---------------------------------------------------------------------------


class TestLeaderLockConstant:
    def test_lock_id_is_max_uint32(self):
        # Pinned so a casual edit cannot collide with other advisory locks.
        assert SCHEDULER_LEADER_LOCK_ID == 4294967295


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestDistributedContextInit:
    def test_init_builds_engine_and_starts_as_standby(self):
        # create_engine is lazy, so a Postgres URL connects to nothing.
        ctx = DistributedContext(database_url="postgresql://fake:fake@localhost:5432/fake")
        try:
            assert ctx.database_url == "postgresql://fake:fake@localhost:5432/fake"
            assert ctx.engine is not None
            assert ctx._is_leader is False
            assert ctx._leader_pid is None
            assert ctx._heartbeat_thread is None
        finally:
            ctx.engine.dispose()


# ---------------------------------------------------------------------------
# _release_election_connection
# ---------------------------------------------------------------------------


class TestReleaseElectionConnection:
    def test_none_is_a_noop(self):
        _release_election_connection(None)

    def test_close_is_called(self):
        conn = MagicMock()
        _release_election_connection(conn)
        conn.close.assert_called_once_with()

    def test_close_failure_is_swallowed(self):
        """Teardown must not become the failure (edge case)."""
        conn = MagicMock()
        conn.close.side_effect = RuntimeError("pool already disposed")
        _release_election_connection(conn)


# ---------------------------------------------------------------------------
# leadership_claim
# ---------------------------------------------------------------------------


class TestLeadershipClaim:
    def test_acquire_yields_true_and_releases_on_exit(self):
        conn = _election_conn(True)
        ctx = _make_ctx(_ScriptedEngine([conn]))

        with ctx.leadership_claim(poll_interval=0) as leader:
            assert leader is True
            assert ctx._is_leader is True

        assert ctx._is_leader is False
        assert conn.closed is True
        assert any("pg_advisory_unlock" in sql for sql in conn.executed)

    def test_standby_poll_then_acquire(self):
        """First poll loses the lock (yields False), second wins it."""
        conn = _election_conn(False, True)
        ctx = _make_ctx(_ScriptedEngine([conn]))

        # leadership_claim is a @contextmanager, so drive the raw generator
        # to observe the intermediate standby yield.
        gen = ctx.leadership_claim(poll_interval=0).gen
        try:
            assert next(gen) is False
            assert ctx._is_leader is False
            assert next(gen) is True
            assert ctx._is_leader is True
        finally:
            gen.close()

        assert ctx._is_leader is False
        assert conn.closed is True

    def test_db_error_on_connect_retries_and_acquires(self):
        """A transient DB outage on connect must not kill the election loop."""
        conn = _election_conn(True)
        engine = _ScriptedEngine([SQLAlchemyError("connection down"), conn])
        ctx = _make_ctx(engine)

        gen = ctx.leadership_claim(poll_interval=0).gen
        try:
            assert next(gen) is True
        finally:
            gen.close()

        assert engine.connect_count == 2
        assert ctx._is_leader is False
        assert conn.closed is True


# ---------------------------------------------------------------------------
# wait_for_leadership
# ---------------------------------------------------------------------------


class TestWaitForLeadership:
    def test_standby_then_runs_callback_as_leader(self):
        """A standby poll (lock busy) is followed by acquisition and callback."""
        conn = _election_conn(False, True, 777, None)
        ctx = _make_ctx(_ScriptedEngine([conn]))
        observed = {}

        def _callback():
            observed["leader_during_callback"] = ctx._is_leader
            observed["pid_during_callback"] = ctx._leader_pid

        ctx.wait_for_leadership(_callback, poll_interval=0, heartbeat_interval_seconds=3600)

        assert observed["leader_during_callback"] is True
        assert observed["pid_during_callback"] == 777
        assert ctx._is_leader is False
        assert ctx._leader_pid is None
        assert conn.closed is True

    def test_crashing_callback_clears_flag_and_releases(self):
        """Error case: a crashing workload still tears the term down.

        The ``return`` in the callback ``finally`` block swallows the
        exception (pre-existing quirk); what matters is the flag is
        cleared, the lock is unlocked, and the connection is closed.
        """

        def _boom():
            raise RuntimeError("scheduler workload crashed")

        conn = _election_conn(True, 4242, None)
        ctx = _make_ctx(_ScriptedEngine([conn]))

        ctx.wait_for_leadership(_boom, poll_interval=0, heartbeat_interval_seconds=3600)

        assert ctx._is_leader is False
        assert conn.closed is True
        assert any("pg_advisory_unlock" in sql for sql in conn.executed)

    def test_connect_outage_retries_until_lock_acquired(self):
        """SQLAlchemy outage before acquisition retries instead of exiting."""
        conn = _election_conn(True, 4242, None)
        engine = _ScriptedEngine([SQLAlchemyError("db unreachable"), conn])
        ctx = _make_ctx(engine)
        ran = []

        ctx.wait_for_leadership(lambda: ran.append(True), poll_interval=0, heartbeat_interval_seconds=3600)

        assert ran == [True]
        assert engine.connect_count == 2
        assert conn.closed is True


# ---------------------------------------------------------------------------
# _signal_leadership_lost
# ---------------------------------------------------------------------------


class TestSignalLeadershipLost:
    def test_clears_flag_before_invoking_callback(self):
        ctx = _make_ctx(_ScriptedEngine([]))
        ctx._is_leader = True
        flag_at_callback = {}

        def _on_lost():
            flag_at_callback["value"] = ctx._is_leader

        ctx._signal_leadership_lost(_on_lost, leader_pid=99)

        assert flag_at_callback["value"] is False
        assert ctx._is_leader is False

    def test_none_callback_only_clears_flag(self):
        ctx = _make_ctx(_ScriptedEngine([]))
        ctx._is_leader = True

        ctx._signal_leadership_lost(None, leader_pid=99)

        assert ctx._is_leader is False

    def test_failing_callback_is_swallowed(self):
        """A broken shutdown hook must not crash the heartbeat thread."""

        def _bad_hook():
            raise RuntimeError("shutdown hook broken")

        ctx = _make_ctx(_ScriptedEngine([]))
        ctx._is_leader = True

        ctx._signal_leadership_lost(_bad_hook, leader_pid=99)

        assert ctx._is_leader is False
