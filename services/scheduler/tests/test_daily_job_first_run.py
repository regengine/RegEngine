"""Regression tests — daily interval jobs must get a near-boot first run.

``IntervalTrigger`` first fires at start_time + interval, and no explicit
``next_run_time`` was passed, so every ``hours=24`` job's first run was
boot + 24h. The scheduler is in-process (``server/workers/
embedded_scheduler.py``) and restarts on every Railway deploy. With deploys
landing more than once a day, the daily jobs (data_archival,
kde_retention_enforcement, inactive_account_sweep, task_queue_purge,
state_cleanup) never reached their first fire — starved indefinitely.
Verified in prod 2026-07-26: scheduler_job_runs showed data_archival last
ran 2026-07-25 despite daily deploys since.

The fix passes an explicit near-boot ``next_run_time`` (staggered per job)
for every 24h interval job. Cron jobs (fsma_nightly_sync) are untouched —
their absolute fire time already survives restarts within the misfire
grace window.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from apscheduler.triggers.interval import IntervalTrigger
from pytz import utc

DAILY_JOB_IDS = {
    "state_cleanup",
    "inactive_account_sweep",
    "kde_retention_enforcement",
    "data_archival",
    "task_queue_purge",
}

# First runs must land soon after boot — well under the daily deploy
# cadence that caused the starvation, and inside the 3600s misfire grace.
FIRST_RUN_CEILING = timedelta(minutes=30)


def _build_scheduler_service_without_init():
    """Construct SchedulerService with heavy dependencies stubbed."""
    from services.scheduler import service as scheduler_service

    with (
        patch.object(scheduler_service, "get_kafka_producer", return_value=MagicMock()),
        patch.object(scheduler_service, "WebhookNotifier", return_value=MagicMock()),
        patch.object(scheduler_service, "DistributedContext", return_value=MagicMock()),
        patch.object(scheduler_service, "StateManager", return_value=MagicMock()),
        patch.object(scheduler_service, "FDAImportAlertsScraper", return_value=MagicMock()),
        patch.object(scheduler_service, "FDARecallsScraper", return_value=MagicMock()),
        patch.object(scheduler_service, "FDAWarningLettersScraper", return_value=MagicMock()),
        patch.object(scheduler_service, "BlockingScheduler", return_value=MagicMock()),
    ):
        svc = scheduler_service.SchedulerService()
    return svc


def _scheduled_calls():
    svc = _build_scheduler_service_without_init()
    svc.scheduler = MagicMock()
    svc.schedule_jobs()
    return {call.kwargs.get("id"): call.kwargs for call in svc.scheduler.add_job.call_args_list}


def _daily_interval_calls(calls):
    return {
        job_id: kwargs
        for job_id, kwargs in calls.items()
        if isinstance(kwargs.get("trigger"), IntervalTrigger) and kwargs["trigger"].interval >= timedelta(hours=24)
    }


class TestDailyIntervalJobsFirstRun:
    def test_expected_daily_jobs_are_registered(self):
        """Guard: the assertion set below must not go vacuously green."""
        daily = _daily_interval_calls(_scheduled_calls())
        assert set(daily) == DAILY_JOB_IDS, (
            "24h interval job set changed — update DAILY_JOB_IDS and give "
            "any new daily job a near-boot next_run_time. Found: %s" % sorted(daily)
        )

    def test_every_daily_interval_job_has_near_boot_first_run(self):
        before = datetime.now(utc)
        daily = _daily_interval_calls(_scheduled_calls())
        after = datetime.now(utc)

        for job_id, kwargs in daily.items():
            first_run = kwargs.get("next_run_time")
            assert first_run is not None, (
                f"{job_id}: 24h IntervalTrigger without next_run_time first "
                "fires at boot+24h; the embedded scheduler restarts on every "
                "Railway deploy, so the job would starve indefinitely"
            )
            assert first_run.tzinfo is not None, f"{job_id}: next_run_time must be tz-aware"
            assert before < first_run <= after + FIRST_RUN_CEILING, f"{job_id}: first run {first_run} is not near boot"

    def test_first_runs_are_staggered(self):
        """No thundering herd — daily jobs must not all fire at once."""
        daily = _daily_interval_calls(_scheduled_calls())
        first_runs = [kwargs["next_run_time"] for kwargs in daily.values()]
        assert len(set(first_runs)) == len(first_runs), "daily jobs share a next_run_time — stagger their first runs"

    def test_cron_jobs_do_not_get_next_run_time_override(self):
        """fsma_nightly_sync keeps its 02:00 UTC cron semantics untouched."""
        calls = _scheduled_calls()
        assert calls["fsma_nightly_sync"].get("next_run_time") is None
