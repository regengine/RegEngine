"""Tests for server/workers/embedded_scheduler.py — scheduler-in-monolith wiring.

Production runs a single Railway container (``gunicorn server.main:app``);
the standalone scheduler entrypoint is prod-blocked, so the monolith
lifespan must start SchedulerService in-process. These tests cover the
enable gate, the daemon-thread bootstrap, and failure isolation (a broken
scheduler must never take down the API).
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from server.workers.embedded_scheduler import (
    EmbeddedSchedulerRunner,
    embedded_scheduler_enabled,
    start_embedded_scheduler,
)


class TestEnableGate:
    def test_disabled_by_default_outside_production(self, monkeypatch):
        monkeypatch.delenv("SCHEDULER_EMBEDDED", raising=False)
        monkeypatch.setenv("REGENGINE_ENV", "development")
        assert embedded_scheduler_enabled() is False

    def test_enabled_by_default_in_production(self, monkeypatch):
        monkeypatch.delenv("SCHEDULER_EMBEDDED", raising=False)
        monkeypatch.setenv("REGENGINE_ENV", "production")
        assert embedded_scheduler_enabled() is True

    def test_explicit_flag_overrides_dev_default(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "development")
        monkeypatch.setenv("SCHEDULER_EMBEDDED", "1")
        assert embedded_scheduler_enabled() is True

    def test_kill_switch_overrides_production_default(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "production")
        monkeypatch.setenv("SCHEDULER_EMBEDDED", "0")
        assert embedded_scheduler_enabled() is False

    def test_start_returns_none_when_disabled(self, monkeypatch):
        monkeypatch.delenv("SCHEDULER_EMBEDDED", raising=False)
        monkeypatch.setenv("REGENGINE_ENV", "development")
        assert start_embedded_scheduler() is None


class TestRunnerLifecycle:
    def test_runner_starts_scheduler_service_in_daemon_thread(self, monkeypatch):
        monkeypatch.setenv("SCHEDULER_EMBEDDED", "1")

        started = threading.Event()
        service = MagicMock()
        service.start.side_effect = started.set

        with patch(
            "services.scheduler.service.SchedulerService",
            return_value=service,
        ):
            runner = start_embedded_scheduler()
            assert runner is not None
            assert started.wait(timeout=5), "SchedulerService.start() was never called"
            assert runner._thread is not None
            assert runner._thread.daemon, "scheduler thread must be a daemon so it never blocks process exit"
            runner.stop()
            runner._thread.join(timeout=5)

        assert not runner._thread.is_alive()

    def test_init_failure_is_contained(self):
        """A misconfigured SchedulerService (e.g. SCHEDULER_API_KEY unset in
        prod) must log and die quietly — never propagate into the lifespan."""
        runner = EmbeddedSchedulerRunner()

        with patch(
            "services.scheduler.service.SchedulerService",
            side_effect=ValueError("SCHEDULER_API_KEY must be set in production"),
        ):
            runner.start()
            runner._thread.join(timeout=5)

        assert not runner._thread.is_alive()
        assert runner._service is None
        # stop() on a runner that never built a service is a no-op.
        runner.stop()

    def test_leadership_loss_reenters_election(self, monkeypatch):
        """If SchedulerService.start() returns (heartbeat shut the scheduler
        down on leadership loss, #1142), the runner must rejoin the standby
        pool instead of silently retiring this worker as a candidate."""
        monkeypatch.setattr(EmbeddedSchedulerRunner, "_REELECTION_DELAY_SECONDS", 0.01)

        second_round = threading.Event()
        calls = {"n": 0}

        def _make_service():
            service = MagicMock()

            def _start():
                calls["n"] += 1
                if calls["n"] >= 2:
                    second_round.set()
                    # Park until the test stops us so the loop doesn't spin.
                    runner._stop_event.wait(5)

            service.start.side_effect = _start
            return service

        runner = EmbeddedSchedulerRunner()
        with patch(
            "services.scheduler.service.SchedulerService",
            side_effect=lambda: _make_service(),
        ):
            runner.start()
            assert second_round.wait(timeout=5), "runner never re-entered leadership election"
            runner.stop()
            runner._thread.join(timeout=5)

        assert not runner._thread.is_alive()

    def test_stop_shuts_down_running_scheduler(self):
        runner = EmbeddedSchedulerRunner()
        service = MagicMock()
        service.scheduler.running = True
        runner._service = service

        runner.stop()

        service.scheduler.shutdown.assert_called_once_with(wait=False)

    def test_stop_skips_standby_scheduler(self):
        """A standby worker's APScheduler never started — nothing to stop."""
        runner = EmbeddedSchedulerRunner()
        service = MagicMock()
        service.scheduler.running = False
        runner._service = service

        runner.stop()

        service.scheduler.shutdown.assert_not_called()


class TestThreadAliveProbe:
    """#2697: /readiness uses thread_alive to detect a dead scheduler thread."""

    def test_unstarted_runner_reports_not_alive(self):
        assert EmbeddedSchedulerRunner().thread_alive is False

    def test_dead_thread_reports_not_alive(self):
        runner = EmbeddedSchedulerRunner()
        with patch(
            "services.scheduler.service.SchedulerService",
            side_effect=ValueError("config error"),
        ):
            runner.start()
            runner._thread.join(timeout=5)
        assert runner.thread_alive is False

    def test_live_thread_reports_alive(self):
        import threading as _threading

        runner = EmbeddedSchedulerRunner()
        release = _threading.Event()

        service = MagicMock()
        service.start.side_effect = release.wait

        with patch(
            "services.scheduler.service.SchedulerService",
            return_value=service,
        ):
            runner.start()
            try:
                assert runner.thread_alive is True
            finally:
                release.set()
                runner.stop()
                runner._thread.join(timeout=5)
