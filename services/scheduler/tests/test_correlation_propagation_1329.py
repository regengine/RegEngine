"""Tests for #1329 — correlation_id and tenant_id propagation into APScheduler jobs.

Before the fix, APScheduler's ThreadPoolExecutor launched jobs in a fresh OS
thread where all contextvars were reset to their defaults. Any log line emitted
by a job had ``correlation_id=None`` and ``tenant_id="unknown"`` regardless of
what was set in the calling context.

Fix: wrap every job callable with ``wrap_job_with_new_correlation`` (from
``shared.observability.context``), which snapshots the tenant context at
schedule-time and generates a stable, job-keyed correlation_id on each run.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# shared.observability.context unit tests
# ---------------------------------------------------------------------------

class TestWrapJobWithNewCorrelation:
    """Unit tests for the wrapping helper that provides thread-local context."""

    def _import_helpers(self):
        """Import helpers after sys.path has been set up by conftest."""
        from shared.observability.context import (
            _capture_observability_context,
            _restore_observability_context,
            wrap_job_with_new_correlation,
        )
        from shared.observability.correlation import correlation_id_ctx
        from shared.observability.context import _tenant_id_ctx, _request_id_ctx
        return (
            _capture_observability_context,
            _restore_observability_context,
            wrap_job_with_new_correlation,
            correlation_id_ctx,
            _tenant_id_ctx,
            _request_id_ctx,
        )

    def test_wrapped_job_gets_correlation_id(self):
        """A wrapped job executed in a new thread has a non-None correlation_id."""
        (
            _,
            _,
            wrap_job_with_new_correlation,
            correlation_id_ctx,
            _tenant_id_ctx,
            _request_id_ctx,
        ) = self._import_helpers()

        observed = {}

        def _job():
            observed["correlation_id"] = correlation_id_ctx.get()

        wrapped = wrap_job_with_new_correlation(_job, job_id="test_job")

        t = threading.Thread(target=wrapped)
        t.start()
        t.join()

        assert observed["correlation_id"] is not None
        assert observed["correlation_id"].startswith("job:test_job:")

    def test_each_execution_gets_unique_correlation_id(self):
        """Two executions of the same wrapped job produce different correlation_ids."""
        (
            _,
            _,
            wrap_job_with_new_correlation,
            correlation_id_ctx,
            _,
            _,
        ) = self._import_helpers()

        results = []

        def _job():
            results.append(correlation_id_ctx.get())

        wrapped = wrap_job_with_new_correlation(_job, job_id="my_job")

        for _ in range(2):
            t = threading.Thread(target=wrapped)
            t.start()
            t.join()

        assert len(results) == 2
        assert results[0] != results[1], "Each run must get a unique correlation_id"

    def test_wrapped_job_seeds_tenant_id_in_structlog(self):
        """Structlog contextvars contain correlation_id after the wrapper runs."""
        import structlog
        (
            _,
            _,
            wrap_job_with_new_correlation,
            correlation_id_ctx,
            _tenant_id_ctx,
            _,
        ) = self._import_helpers()

        # Seed a known tenant_id in the outer context.
        _tenant_id_ctx.set("tenant-abc")

        observed_structlog = {}

        def _job():
            # Inside the job thread, structlog's context vars should be bound.
            ctx = structlog.contextvars.get_contextvars()
            observed_structlog.update(ctx)

        wrapped = wrap_job_with_new_correlation(_job, job_id="job_with_tenant")

        t = threading.Thread(target=wrapped)
        t.start()
        t.join()

        assert "correlation_id" in observed_structlog
        assert observed_structlog["correlation_id"].startswith("job:job_with_tenant:")
        # tenant_id seeded from snapshot taken at wrap time
        assert observed_structlog.get("tenant_id") == "tenant-abc"

    def test_wrapping_preserves_function_name(self):
        """functools.wraps should preserve __name__ on the wrapper."""
        from shared.observability.context import wrap_job_with_new_correlation

        def my_important_job():
            pass

        wrapped = wrap_job_with_new_correlation(my_important_job, job_id="x")
        assert wrapped.__name__ == "my_important_job"

    def test_wrapping_propagates_return_value(self):
        """The wrapped callable should return whatever the original returns."""
        from shared.observability.context import wrap_job_with_new_correlation

        def _fn():
            return 42

        wrapped = wrap_job_with_new_correlation(_fn, job_id="rv_test")
        assert wrapped() == 42


class TestMakeJobContextWrapper:
    """Unit tests for make_job_context_wrapper (inherits parent context)."""

    def test_inherits_parent_correlation_id(self):
        """A job wrapped with make_job_context_wrapper gets the parent's correlation_id."""
        from shared.observability.context import make_job_context_wrapper
        from shared.observability.correlation import correlation_id_ctx, set_correlation_id

        # Set a known correlation_id in the current context.
        token = set_correlation_id("parent-cid-xyz")
        try:
            observed = {}

            def _job():
                observed["cid"] = correlation_id_ctx.get()

            wrapped = make_job_context_wrapper(_job)
            t = threading.Thread(target=wrapped)
            t.start()
            t.join()
        finally:
            correlation_id_ctx.reset(token)

        assert observed["cid"] == "parent-cid-xyz"


# ---------------------------------------------------------------------------
# Integration: SchedulerService._add_tracked_job uses the wrapper
# ---------------------------------------------------------------------------

class TestSchedulerServiceContextPropagation:
    """Integration tests confirming schedule_jobs wraps callables."""

    def _make_scheduler_service(self):
        """Build a SchedulerService with all heavy dependencies mocked out."""
        with (
            patch("shared.env_validation.require_env"),
            patch("shared.error_handling.init_sentry"),
            patch("shared.observability.setup_standalone_observability"),
            patch("app.config.get_settings") as mock_settings,
            patch("app.state.StateManager"),
            patch("app.notifications.WebhookNotifier"),
            patch("app.kafka_producer.get_kafka_producer"),
            patch("app.distributed.DistributedContext"),
            patch("app.circuit_breaker.circuit_registry"),
            patch("app.scrapers.FDAWarningLettersScraper"),
            patch("app.scrapers.FDAImportAlertsScraper"),
            patch("app.scrapers.FDARecallsScraper"),
            patch("app.scrapers.InternalDiscoveryScraper"),
        ):
            settings = MagicMock()
            settings.webhook_outbox_path = None
            settings.fda_warning_letters_interval = 60
            settings.fda_import_alerts_interval = 120
            settings.fda_recalls_interval = 30
            settings.regulatory_discovery_interval = 1440
            settings.circuit_breaker_failure_threshold = 3
            settings.circuit_breaker_recovery_timeout = 300
            mock_settings.return_value = settings

            # Import here so sys.path set up by conftest is used.
            import sys
            from pathlib import Path
            _svc_dir = Path(__file__).resolve().parent.parent
            _svcs_dir = _svc_dir.parent
            for d in (str(_svc_dir), str(_svcs_dir)):
                if d not in sys.path:
                    sys.path.insert(0, d)
            from shared.paths import ensure_shared_importable
            ensure_shared_importable()

            from main import SchedulerService
            return SchedulerService()

    def test_add_tracked_job_wraps_callable(self):
        """_add_tracked_job stores a wrapper (not the raw fn) on the scheduler."""
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        svc = self._make_scheduler_service()

        sentinel = []

        def _raw_job():
            sentinel.append("called")

        svc._add_tracked_job(
            _raw_job,
            job_id="test_wrap",
            trigger=IntervalTrigger(hours=99),
            name="test",
        )

        jobs = svc.scheduler.get_jobs()
        assert len(jobs) == 1
        job = jobs[0]

        # The registered func should NOT be the raw function — it's a wrapper.
        assert job.func is not _raw_job, (
            "add_job should store a wrapper, not the original callable"
        )

    def test_wrapped_job_sets_correlation_id(self):
        """Executing the wrapped job produces a job:-prefixed correlation_id."""
        from apscheduler.triggers.interval import IntervalTrigger
        from shared.observability.correlation import correlation_id_ctx

        svc = self._make_scheduler_service()
        observed = {}

        def _raw_job():
            observed["cid"] = correlation_id_ctx.get()

        svc._add_tracked_job(
            _raw_job,
            job_id="my_tracked_job",
            trigger=IntervalTrigger(hours=99),
            name="test",
        )

        job = svc.scheduler.get_jobs()[0]
        # Call the wrapped fn directly (no scheduler thread needed).
        job.func()

        assert observed["cid"] is not None
        assert observed["cid"].startswith("job:my_tracked_job:")
