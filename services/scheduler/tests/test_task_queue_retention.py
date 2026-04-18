"""Regression tests for #1382 — periodic task_queue retention.

`fsma.task_queue` has no TTL/partitioning in the DDL and the existing
`archive_expired_records` scheduler job does NOT touch it. Completed
and dead rows accumulate forever, bloating indexes and the Railway
storage bill.

Fix: `SchedulerService.purge_old_tasks` runs daily and removes rows
with `status IN ('completed', 'dead')` older than 30 days.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _build_scheduler_service_without_init():
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
    return svc


class TestTaskQueueRetention:
    """#1382 — scheduler must purge completed/dead task_queue rows periodically."""

    def test_purge_old_tasks_issues_delete(self):
        svc = _build_scheduler_service_without_init()

        with patch("shared.database.SessionLocal") as session_factory:
            db = MagicMock()
            db.execute.return_value.fetchall.return_value = []
            session_factory.return_value = db

            svc.purge_old_tasks()

            # Must issue at least one DELETE targeting fsma.task_queue.
            sql_issued = [
                str(call.args[0]) for call in db.execute.call_args_list if call.args
            ]
            assert any(
                "DELETE" in sql.upper() and "TASK_QUEUE" in sql.upper()
                for sql in sql_issued
            ), "purge_old_tasks must issue DELETE on fsma.task_queue"
            db.commit.assert_called()
            db.close.assert_called_once()

    def test_purge_only_targets_terminal_statuses(self):
        svc = _build_scheduler_service_without_init()

        with patch("shared.database.SessionLocal") as session_factory:
            db = MagicMock()
            db.execute.return_value.fetchall.return_value = []
            session_factory.return_value = db

            svc.purge_old_tasks()

            sql_issued = [
                str(call.args[0]).lower()
                for call in db.execute.call_args_list if call.args
            ]
            # The retention policy must be limited to terminal states —
            # otherwise we'd delete pending/processing tasks mid-flight.
            delete_sql = next(s for s in sql_issued if "delete" in s)
            assert "'completed'" in delete_sql and "'dead'" in delete_sql, (
                "Purge must only touch terminal statuses — no 'pending' or "
                "'processing' rows should ever be deleted by retention"
            )
            assert "'pending'" not in delete_sql
            assert "'processing'" not in delete_sql

    def test_purge_old_tasks_scheduled_daily(self):
        svc = _build_scheduler_service_without_init()
        svc.scheduler = MagicMock()
        svc.schedule_jobs()

        scheduled_ids = [
            call.kwargs.get("id") for call in svc.scheduler.add_job.call_args_list
        ]
        assert "task_queue_purge" in scheduled_ids, (
            "schedule_jobs must register a task_queue_purge job "
            "(interval = 24h). Scheduled: %s" % scheduled_ids
        )

    def test_purge_old_tasks_survives_db_outage(self):
        """If the DB is unavailable, log and return — do not crash the scheduler."""
        svc = _build_scheduler_service_without_init()

        with patch("shared.database.SessionLocal", side_effect=ConnectionError("pg down")):
            # Must not raise — otherwise the retention job will poison the scheduler.
            svc.purge_old_tasks()
