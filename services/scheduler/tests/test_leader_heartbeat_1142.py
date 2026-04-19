"""Regression tests for #1142 — leader-heartbeat / zombie-leader prevention.

Before the fix, ``DistributedContext.wait_for_leadership`` acquired a
PostgreSQL advisory lock then invoked ``callback()`` (typically
``BlockingScheduler.start()``) for the lifetime of the process with no
periodic re-check. If the connection was silently broken (network
partition, DB failover, proxy reset, long GC pause on the leader) PG
released the lock server-side, a standby acquired it, and both nodes ran
scrapers concurrently until the old node's TCP stack noticed.

The fix spawns a daemon heartbeat thread that probes ``pg_locks`` from a
SEPARATE short-lived connection using the leader's captured backend pid.
After ``heartbeat_max_failures`` consecutive failures we:
  1. Clear ``_is_leader``
  2. Call ``on_leadership_lost`` (the scheduler's shutdown hook)
  3. Exit the heartbeat thread

These tests drive ``wait_for_leadership`` with MagicMock engines that
script specific ``pg_locks`` query results, asserting:

1. Heartbeat probes start after lock acquisition with the correct pid/lock.
2. Lock-still-held result → heartbeat keeps quiet, callback runs.
3. Lock-missing for max_failures consecutive → on_leadership_lost fires.
4. Transient heartbeat DB error (once) then recovery → no shutdown.
5. Persistent heartbeat DB errors → on_leadership_lost fires.
6. Heartbeat stops cleanly when callback returns.
7. ``_is_leader`` is cleared BEFORE on_leadership_lost runs.
8. No on_leadership_lost callback → heartbeat logs and exits.
9. Recovery resets the consecutive-failure counter.
"""
from __future__ import annotations

import threading
import time
from typing import List
from unittest.mock import MagicMock

import pytest

from app.distributed import (
    SCHEDULER_LEADER_LOCK_ID,
    DistributedContext,
)


# ---------------------------------------------------------------------------
# Scripted engine — per-connect response sequence + invocation tracking.
# ---------------------------------------------------------------------------


class _ScriptedEngine:
    """Minimal MagicMock-like engine whose ``.connect()`` returns
    connections that honor a scripted ``scalar()`` sequence.

    Each call to ``execute(...).scalar()`` pops the next scripted result
    (value or exception). The connect() itself can also be scripted to
    raise (for "heartbeat can't reach DB" cases).
    """

    def __init__(self):
        # Connections for the MAIN wait_for_leadership loop.
        self._main_connect_script: List = []
        # Per-connection scripts of scalar results — each sub-list feeds
        # one connection's queries in order.
        self._main_scalar_scripts: List[List] = []
        # Scripts for heartbeat short-lived connections (new conn per probe).
        self._heartbeat_scripts: List = []
        self.heartbeat_connect_count = 0

        self._main_conn_index = 0

    # --- main-session scripting ------------------------------------------
    def queue_main_session(self, scalar_results: List) -> None:
        """Queue a main session whose execute(...).scalar() returns each
        value in order.

        Values may be plain (int/bool) or exceptions (raised from scalar)."""
        self._main_connect_script.append("conn")
        self._main_scalar_scripts.append(list(scalar_results))

    # --- heartbeat scripting ---------------------------------------------
    def queue_heartbeat_probes(self, results: List) -> None:
        """Each entry becomes one heartbeat probe result:
          - int 1   → lock still held
          - int 0   → lock missing (counts as failure)
          - Exception instance → connect raises (counts as failure)
          - "hang" → connect returns a conn whose scalar never completes
                    (not used in these tests but reserved)
        """
        self._heartbeat_scripts.extend(results)

    # --- hooks called by DistributedContext ------------------------------
    def connect(self):  # pragma: no cover trivial
        # Decide whether this is a main or heartbeat connect by which
        # thread we're on. The heartbeat runs in a thread named
        # "scheduler-leader-heartbeat".
        current = threading.current_thread().name
        if current.startswith("scheduler-leader-heartbeat"):
            return self._make_heartbeat_connect()
        return self._make_main_connect()

    def _make_main_connect(self):
        idx = self._main_conn_index
        self._main_conn_index += 1
        scalar_results = self._main_scalar_scripts[idx] if idx < len(self._main_scalar_scripts) else []
        return _ScriptedConnection(scalar_results)

    def _make_heartbeat_connect(self):
        self.heartbeat_connect_count += 1
        if not self._heartbeat_scripts:
            # No script left — block forever to simulate never-terminating
            # heartbeat (tests should always set stop before getting here).
            return _ScriptedConnection([1])  # always healthy
        entry = self._heartbeat_scripts.pop(0)
        if isinstance(entry, BaseException):
            raise entry
        return _ScriptedConnection([entry])


class _ScriptedConnection:
    def __init__(self, scalar_script):
        self._script = list(scalar_script)
        self.executed_queries: List[tuple] = []

    def execution_options(self, **_kw):
        return self

    def execute(self, query, params=None):
        self.executed_queries.append((str(query), params or {}))
        result = MagicMock()
        if not self._script:
            result.scalar.return_value = None
        else:
            entry = self._script.pop(0)
            if isinstance(entry, BaseException):
                result.scalar.side_effect = entry
            else:
                result.scalar.return_value = entry
        return result

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def _make_ctx(engine) -> DistributedContext:
    """Construct a DistributedContext with our scripted engine."""
    ctx = DistributedContext.__new__(DistributedContext)
    ctx.database_url = "postgresql://fake"
    ctx._is_leader = False
    ctx._leader_pid = None
    ctx._heartbeat_stop = threading.Event()
    ctx._heartbeat_thread = None
    ctx.engine = engine
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHeartbeatAcquisition_Issue1142:
    def test_leader_pid_stashed_after_acquisition(self):
        engine = _ScriptedEngine()
        # Main session: [got_lock=True, pid=12345, unlock=None]
        engine.queue_main_session([True, 12345, None])
        engine.queue_heartbeat_probes([1])  # one healthy probe

        ctx = _make_ctx(engine)
        observed = {"pid_at_cb": None, "flag_at_cb": None}

        def cb():
            observed["pid_at_cb"] = ctx._leader_pid
            observed["flag_at_cb"] = ctx._is_leader
            # Give the heartbeat thread a chance to start and verify.
            time.sleep(0.05)

        ctx.wait_for_leadership(
            cb,
            heartbeat_interval_seconds=0.01,
            heartbeat_max_failures=5,
        )

        assert observed["pid_at_cb"] == 12345
        assert observed["flag_at_cb"] is True
        # After callback returns, state is torn down.
        assert ctx._leader_pid is None
        assert ctx._is_leader is False

    def test_heartbeat_disabled_if_pid_fetch_fails(self):
        """If we can't determine our backend pid at acquisition, we log
        loudly and skip the heartbeat — better than asserting leadership
        we can't verify."""
        engine = _ScriptedEngine()
        engine.queue_main_session([True, RuntimeError("pid fetch broke"), None])
        # No heartbeat probes should be issued.

        ctx = _make_ctx(engine)

        def cb():
            # Heartbeat thread should NOT be running.
            assert ctx._heartbeat_thread is None

        ctx.wait_for_leadership(
            cb,
            heartbeat_interval_seconds=0.01,
        )
        # Heartbeat never probed.
        assert engine.heartbeat_connect_count == 0


class TestHeartbeatHealthyPath_Issue1142:
    def test_heartbeat_allows_callback_to_complete_when_lock_held(self):
        engine = _ScriptedEngine()
        engine.queue_main_session([True, 12345, None])
        # Flood the heartbeat with healthy probes.
        engine.queue_heartbeat_probes([1] * 200)

        ctx = _make_ctx(engine)

        loss_calls = []

        def on_lost():
            loss_calls.append(1)

        def cb():
            # Let several heartbeats fire.
            time.sleep(0.1)

        ctx.wait_for_leadership(
            cb,
            on_leadership_lost=on_lost,
            heartbeat_interval_seconds=0.01,
            heartbeat_max_failures=3,
        )

        assert loss_calls == []
        assert engine.heartbeat_connect_count >= 2


class TestHeartbeatLockMissing_Issue1142:
    def test_on_leadership_lost_fires_after_max_failures(self):
        engine = _ScriptedEngine()
        engine.queue_main_session([True, 12345, None])
        # Every probe returns 0 — the lock is gone.
        engine.queue_heartbeat_probes([0, 0, 0, 0, 0])

        ctx = _make_ctx(engine)

        shutdown_event = threading.Event()
        leader_flag_at_shutdown = {"value": None}

        def on_lost():
            # Record the leader flag AT THE MOMENT of shutdown — it must
            # already be False (we clear it before calling on_lost).
            leader_flag_at_shutdown["value"] = ctx._is_leader
            shutdown_event.set()

        def cb():
            # Wait for the heartbeat to declare lost, then exit.
            shutdown_event.wait(timeout=2.0)

        ctx.wait_for_leadership(
            cb,
            on_leadership_lost=on_lost,
            heartbeat_interval_seconds=0.01,
            heartbeat_max_failures=3,
        )

        assert shutdown_event.is_set(), "on_leadership_lost was never called"
        # Leader flag was cleared BEFORE on_lost ran.
        assert leader_flag_at_shutdown["value"] is False


class TestHeartbeatTransientFailure_Issue1142:
    def test_single_failure_then_recovery_does_not_shutdown(self):
        engine = _ScriptedEngine()
        engine.queue_main_session([True, 12345, None])
        # First probe fails, next two succeed, rest healthy.
        engine.queue_heartbeat_probes([
            RuntimeError("transient DB blip"),
            1,
            1,
            1,
            1,
        ])

        ctx = _make_ctx(engine)

        loss_calls = []

        def on_lost():
            loss_calls.append(1)

        def cb():
            # Let several probes run.
            time.sleep(0.1)

        ctx.wait_for_leadership(
            cb,
            on_leadership_lost=on_lost,
            heartbeat_interval_seconds=0.01,
            heartbeat_max_failures=3,
        )

        assert loss_calls == [], (
            "one transient heartbeat failure followed by recovery should NOT "
            "trigger shutdown"
        )

    def test_persistent_db_errors_trigger_shutdown(self):
        engine = _ScriptedEngine()
        engine.queue_main_session([True, 12345, None])
        engine.queue_heartbeat_probes([
            RuntimeError("db down 1"),
            RuntimeError("db down 2"),
            RuntimeError("db down 3"),
            RuntimeError("db down 4"),
        ])

        ctx = _make_ctx(engine)

        shutdown_event = threading.Event()

        def on_lost():
            shutdown_event.set()

        def cb():
            shutdown_event.wait(timeout=2.0)

        ctx.wait_for_leadership(
            cb,
            on_leadership_lost=on_lost,
            heartbeat_interval_seconds=0.01,
            heartbeat_max_failures=3,
        )

        assert shutdown_event.is_set(), (
            "3 consecutive heartbeat query errors must trigger shutdown"
        )


class TestHeartbeatCleanShutdown_Issue1142:
    def test_heartbeat_thread_exits_when_callback_returns(self):
        engine = _ScriptedEngine()
        engine.queue_main_session([True, 12345, None])
        engine.queue_heartbeat_probes([1] * 100)

        ctx = _make_ctx(engine)

        hb_ref = {}

        def cb():
            # Capture the heartbeat thread reference.
            hb_ref["thread"] = ctx._heartbeat_thread
            time.sleep(0.05)

        ctx.wait_for_leadership(
            cb,
            heartbeat_interval_seconds=0.01,
        )

        # After wait_for_leadership returns, the heartbeat thread must
        # have been joined and cleared.
        assert ctx._heartbeat_thread is None
        assert hb_ref["thread"] is not None
        # The captured thread should no longer be alive.
        assert not hb_ref["thread"].is_alive()


class TestHeartbeatNoCallback_Issue1142:
    def test_heartbeat_without_on_lost_does_not_crash(self):
        engine = _ScriptedEngine()
        engine.queue_main_session([True, 12345, None])
        engine.queue_heartbeat_probes([0, 0, 0, 0])  # lost immediately

        ctx = _make_ctx(engine)

        lost_detected = threading.Event()

        def cb():
            # Wait a bit for the heartbeat to notice; without on_lost it
            # won't signal us, so we just poll the leader flag.
            for _ in range(200):
                if not ctx._is_leader:
                    lost_detected.set()
                    return
                time.sleep(0.01)

        ctx.wait_for_leadership(
            cb,
            # NO on_leadership_lost
            heartbeat_interval_seconds=0.005,
            heartbeat_max_failures=3,
        )

        # Heartbeat cleared the flag even without a shutdown callback.
        assert lost_detected.is_set(), (
            "Without on_leadership_lost, the heartbeat should still clear "
            "_is_leader so readers see the right state"
        )


class TestHeartbeatRecoveryResetsCounter_Issue1142:
    def test_recovery_resets_failure_counter(self):
        engine = _ScriptedEngine()
        engine.queue_main_session([True, 12345, None])
        # Two failures, then recovery, then two more failures —
        # should NOT trigger shutdown because the counter reset.
        engine.queue_heartbeat_probes([
            RuntimeError("blip1"),
            RuntimeError("blip2"),
            1,  # recovery
            RuntimeError("blip3"),
            RuntimeError("blip4"),
            1,  # healthy again
            1,
            1,
        ])

        ctx = _make_ctx(engine)

        loss_calls = []

        def on_lost():
            loss_calls.append(1)

        def cb():
            time.sleep(0.15)

        ctx.wait_for_leadership(
            cb,
            on_leadership_lost=on_lost,
            heartbeat_interval_seconds=0.01,
            heartbeat_max_failures=3,
        )

        assert loss_calls == [], (
            "recovery between failure bursts should keep the counter under "
            "the threshold"
        )
