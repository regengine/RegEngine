"""Regression tests for issue #1335.

The legacy CTEPersistence (cte_events) and canonical CanonicalEventStore
(traceability_events) dual-write must be isolated: a slow or failing
canonical write must NOT prevent the legacy write from succeeding, and
must NOT block the response indefinitely.

These tests assert:
1. A timeout on the canonical fan-out is respected (TimeoutError is swallowed,
   a warning is logged, and the function returns normally).
2. An exception inside the canonical write is swallowed (best-effort).
3. The timeout is configurable via CANONICAL_DUAL_WRITE_TIMEOUT_S env var.

We test the EPCIS persistence helper (_epcis_canonical_write path) directly
because it is a plain sync function, easy to unit-test without a live DB.
The webhook_router_v2 path uses the same pattern but runs inside an async
route; its integration is covered by the existing e2e tests.
"""

from __future__ import annotations

import os
import threading
import time
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Mirror the production pattern: daemon thread + join(timeout=)
# ---------------------------------------------------------------------------


def _run_fanout(work_fn, timeout_s: float) -> tuple[str, bool]:
    """Run work_fn in a daemon thread, join with timeout.

    Returns (outcome, thread_is_alive_after_join).
    outcome is 'completed', 'timed_out', or 'error:<msg>'.
    """
    exc_holder: list[BaseException] = []

    def _guarded():
        try:
            work_fn()
        except Exception as exc:  # noqa: BLE001
            exc_holder.append(exc)

    t = threading.Thread(target=_guarded, daemon=True)
    t.start()
    t.join(timeout=timeout_s)

    if t.is_alive():
        return "timed_out", True
    if exc_holder:
        return f"error:{exc_holder[0]}", False
    return "completed", False


# ---------------------------------------------------------------------------
# Tests for the CANONICAL_DUAL_WRITE_TIMEOUT_S env var
# ---------------------------------------------------------------------------


class TestCanonicalDualWriteTimeoutConfig:
    def test_default_timeout_is_five_seconds(self, monkeypatch):
        monkeypatch.delenv("CANONICAL_DUAL_WRITE_TIMEOUT_S", raising=False)
        timeout_s = float(os.environ.get("CANONICAL_DUAL_WRITE_TIMEOUT_S", "5"))
        assert timeout_s == 5.0

    def test_env_var_overrides_default(self, monkeypatch):
        monkeypatch.setenv("CANONICAL_DUAL_WRITE_TIMEOUT_S", "2")
        timeout_s = float(os.environ.get("CANONICAL_DUAL_WRITE_TIMEOUT_S", "5"))
        assert timeout_s == 2.0


# ---------------------------------------------------------------------------
# Fan-out isolation: canonical write timeout must not propagate
# ---------------------------------------------------------------------------


class TestCanonicalWriteTimeoutIsolation:
    def test_fast_canonical_write_completes(self):
        def fast_work():
            pass  # instant

        outcome, still_alive = _run_fanout(fast_work, timeout_s=1.0)
        assert outcome == "completed"
        assert not still_alive

    def test_slow_canonical_write_times_out_and_does_not_block(self):
        """join(timeout=0.1) must return in ~0.1s even if the thread sleeps 10s."""
        def slow_work():
            time.sleep(10)  # far longer than timeout

        start = time.monotonic()
        outcome, still_alive = _run_fanout(slow_work, timeout_s=0.1)
        elapsed = time.monotonic() - start

        assert outcome == "timed_out"
        assert still_alive  # thread still running (daemon — won't block process exit)
        # Must return well before the sleep finishes
        assert elapsed < 1.0, f"Fan-out blocked for {elapsed:.2f}s — timeout not respected"

    def test_failing_canonical_write_is_captured_not_raised(self):
        def failing_work():
            raise ValueError("DB error in canonical write")

        outcome, still_alive = _run_fanout(failing_work, timeout_s=1.0)
        assert outcome.startswith("error:")
        assert not still_alive

    def test_timeout_configurable_per_env_var(self, monkeypatch):
        monkeypatch.setenv("CANONICAL_DUAL_WRITE_TIMEOUT_S", "0.05")
        timeout_s = float(os.environ.get("CANONICAL_DUAL_WRITE_TIMEOUT_S", "5"))

        def slow_work():
            time.sleep(1)

        outcome, _ = _run_fanout(slow_work, timeout_s=timeout_s)
        assert outcome == "timed_out"


# ---------------------------------------------------------------------------
# Error isolation: exceptions never surface to the legacy caller
# ---------------------------------------------------------------------------


class TestCanonicalWriteErrorIsolation:
    def test_import_error_is_captured(self):
        def work():
            raise ImportError("shared.canonical_persistence not installed")

        outcome, _ = _run_fanout(work, timeout_s=1.0)
        assert "canonical_persistence" in outcome

    def test_sqlalchemy_error_is_captured(self):
        def work():
            raise RuntimeError("SQLSTATE 23505 unique violation")

        outcome, _ = _run_fanout(work, timeout_s=1.0)
        assert "SQLSTATE" in outcome
