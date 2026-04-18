"""Regression tests for #1144 — persist last-run-at and alert on misfires.

Before the fix APScheduler was configured with
``misfire_grace_time=3600`` and ``coalesce=True``, and ``last_run_at``
was only held in `self.last_results` (an in-process dict). On restart
the history was wiped and any missed run older than 1h was dropped
silently.

Fix:
1. Add ``scheduler_job_runs (job_id, last_run_at, last_success_at,
   last_status, last_error)`` table via state.py's initializer.
2. `StateManager.record_job_run(job_id, success, error)` upserts.
3. APScheduler listener wires EVENT_JOB_EXECUTED / EVENT_JOB_ERROR /
   EVENT_JOB_MISSED into the recorder and logs `scheduler_job_missed`
   at ERROR level on miss.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestRecordJobRun:
    """Unit tests for StateManager.record_job_run."""

    def test_record_job_run_persists_success(self):
        from app.state import StateManager

        sm = StateManager.__new__(StateManager)
        sm._initialized = True
        session = MagicMock()
        sm.SessionLocal = MagicMock(return_value=session)

        sm.record_job_run("fda_recalls", success=True)

        assert session.execute.called
        params = session.execute.call_args.args[1]
        assert params["job_id"] == "fda_recalls"
        assert params["success"] is True
        assert params["status"] == "ok"
        session.commit.assert_called_once()
        session.close.assert_called_once()

    def test_record_job_run_persists_error(self):
        from app.state import StateManager

        sm = StateManager.__new__(StateManager)
        sm._initialized = True
        session = MagicMock()
        sm.SessionLocal = MagicMock(return_value=session)

        sm.record_job_run("fda_recalls", success=False, error="boom")

        params = session.execute.call_args.args[1]
        assert params["success"] is False
        assert params["status"] == "error"
        assert params["err"] == "boom"

    def test_record_job_run_survives_db_error(self):
        """A logging path must never crash the scheduler."""
        from app.state import StateManager

        sm = StateManager.__new__(StateManager)
        sm._initialized = True
        session = MagicMock()
        session.execute.side_effect = RuntimeError("pg down")
        sm.SessionLocal = MagicMock(return_value=session)

        # Must not raise — telemetry is best-effort.
        sm.record_job_run("fda_recalls", success=True)
        session.close.assert_called_once()


class TestJobRunListener:
    """Integration of the listener with the APScheduler events."""

    def _mk_scheduler_with_listener(self):
        import main as scheduler_main

        with patch.object(scheduler_main, "get_kafka_producer", return_value=MagicMock()), \
             patch.object(scheduler_main, "WebhookNotifier", return_value=MagicMock()), \
             patch.object(scheduler_main, "DistributedContext", return_value=MagicMock()), \
             patch.object(scheduler_main, "StateManager", return_value=MagicMock()), \
             patch.object(scheduler_main, "FDAImportAlertsScraper", return_value=MagicMock()), \
             patch.object(scheduler_main, "FDARecallsScraper", return_value=MagicMock()), \
             patch.object(scheduler_main, "FDAWarningLettersScraper", return_value=MagicMock()), \
             patch.object(scheduler_main, "InternalDiscoveryScraper", return_value=MagicMock()), \
             patch.object(scheduler_main, "BlockingScheduler", return_value=MagicMock()):
            svc = scheduler_main.SchedulerService()
        svc.scheduler = MagicMock()
        return svc

    def test_listener_is_registered_for_executed_error_missed(self):
        from apscheduler.events import (
            EVENT_JOB_ERROR,
            EVENT_JOB_EXECUTED,
            EVENT_JOB_MISSED,
        )

        svc = self._mk_scheduler_with_listener()
        svc._install_job_run_listener()

        svc.scheduler.add_listener.assert_called_once()
        mask = svc.scheduler.add_listener.call_args.args[1]
        assert mask & EVENT_JOB_EXECUTED
        assert mask & EVENT_JOB_ERROR
        assert mask & EVENT_JOB_MISSED

    def test_listener_records_on_executed(self):
        from apscheduler.events import EVENT_JOB_EXECUTED

        svc = self._mk_scheduler_with_listener()
        svc._install_job_run_listener()
        listener = svc.scheduler.add_listener.call_args.args[0]

        event = MagicMock()
        event.code = EVENT_JOB_EXECUTED
        event.job_id = "fda_recalls"

        listener(event)

        svc.state_manager.record_job_run.assert_called_once()
        kwargs = svc.state_manager.record_job_run.call_args.kwargs
        # record_job_run may be called positionally too — normalize.
        if not kwargs:
            assert svc.state_manager.record_job_run.call_args.args[0] == "fda_recalls"
        else:
            assert kwargs.get("success") is True

    def test_listener_records_on_missed(self):
        from apscheduler.events import EVENT_JOB_MISSED

        svc = self._mk_scheduler_with_listener()
        svc._install_job_run_listener()
        listener = svc.scheduler.add_listener.call_args.args[0]

        event = MagicMock()
        event.code = EVENT_JOB_MISSED
        event.job_id = "fda_recalls"
        event.scheduled_run_time = "2026-04-17T02:00:00+00:00"

        listener(event)

        # Must record the run so observability queries see the miss.
        svc.state_manager.record_job_run.assert_called_once()
