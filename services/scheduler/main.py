"""RegEngine Scheduler Service.

Production-grade job scheduler for automated regulatory change monitoring.

Features:
- FDA Warning Letters, Import Alerts, and Recalls scraping
- Circuit breaker pattern for resilient execution
- Deduplication via PostgreSQL state persistence
- Kafka event emission for downstream processing
- Webhook notifications for real-time alerts
- Prometheus metrics for observability
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional

import structlog
from apscheduler.events import (
    EVENT_JOB_EXECUTED,
    EVENT_JOB_ERROR,
    EVENT_JOB_MISSED,
)
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.base import SchedulerNotRunningError
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from pytz import utc

# --- Standardized Bootstrap ---
import sys
from pathlib import Path
_SERVICE_DIR = Path(__file__).resolve().parent
_SERVICES_DIR = _SERVICE_DIR.parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

from shared.paths import ensure_shared_importable
ensure_shared_importable()
# ------------------------------

from shared.env_validation import require_env
require_env("DATABASE_URL", "REDIS_URL")

# Sentry error tracking (must be before service initialization)
from shared.error_handling import init_sentry
init_sentry()

# OpenTelemetry (standalone — no FastAPI)
from shared.observability import setup_standalone_observability
_tracer = setup_standalone_observability("scheduler")

from app.config import get_settings
from app.circuit_breaker import CircuitBreaker, CircuitOpenError, circuit_registry
from app.kafka_producer import get_kafka_producer
from app.metrics import metrics
from app.models import EnforcementItem, EnforcementSeverity, ScrapeResult, SourceType
from app.notifications import WebhookNotifier
from app.scrapers import (
    FDAImportAlertsScraper,
    FDARecallsScraper,
    FDAWarningLettersScraper,
    InternalDiscoveryScraper,
)
from app.state import StateManager
from app.fda_fsma_transformer import get_fsma_transformer
from app.distributed import DistributedContext

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logger = structlog.get_logger("scheduler")


class SchedulerService:
    """Main scheduler service orchestrating all components."""

    def __init__(self):
        self.settings = get_settings()
        self.state_manager = StateManager()
        self.notifier = WebhookNotifier()
        self.kafka_producer = get_kafka_producer()
        self.distributed_context = DistributedContext()
        
        # Fortune Top 15 Resilience Configuration
        jobstores = {
            'default': MemoryJobStore()
        }
        executors = {
            'default': ThreadPoolExecutor(20)
        }
        job_defaults = {
            'coalesce': True,            # Roll multiple missed executions into one
            'max_instances': 3,
            'misfire_grace_time': 3600   # 1 hour grace for missed jobs (resilience)
        }
        
        self.scheduler = BlockingScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=utc
        )
        self.scheduler_thread = None
        self._start_time = time.time()

        # Initialize scrapers with circuit breakers
        self.scrapers: Dict[SourceType, tuple[BaseScraper, CircuitBreaker]] = {
            SourceType.FDA_WARNING_LETTER: (
                FDAWarningLettersScraper(),
                circuit_registry.get_or_create(
                    "fda_warning_letters",
                    failure_threshold=self.settings.circuit_breaker_failure_threshold,
                    recovery_timeout=self.settings.circuit_breaker_recovery_timeout,
                ),
            ),
            SourceType.FDA_IMPORT_ALERT: (
                FDAImportAlertsScraper(),
                circuit_registry.get_or_create(
                    "fda_import_alerts",
                    failure_threshold=self.settings.circuit_breaker_failure_threshold,
                    recovery_timeout=self.settings.circuit_breaker_recovery_timeout,
                ),
            ),
            SourceType.FDA_RECALL: (
                FDARecallsScraper(),
                circuit_registry.get_or_create(
                    "fda_recalls",
                    failure_threshold=self.settings.circuit_breaker_failure_threshold,
                    recovery_timeout=self.settings.circuit_breaker_recovery_timeout,
                ),
            ),
            SourceType.REGULATORY_DISCOVERY: (
                InternalDiscoveryScraper(),
                circuit_registry.get_or_create(
                    "regulatory_discovery",
                    failure_threshold=3,
                    recovery_timeout=self.settings.circuit_breaker_recovery_timeout,
                ),
            ),
        }
        self.last_results: Dict[SourceType, ScrapeResult] = {}

    def initialize(self) -> None:
        """Initialize all components."""
        logger.info("scheduler_initializing")

        # Initialize state manager (creates tables if needed)
        try:
            self.state_manager.initialize()
            logger.info("state_manager_ready")
        except (RuntimeError, ConnectionError, OSError) as e:
            logger.error("state_manager_init_failed", error=str(e))
            # Continue without state management - will process duplicates

        # Set metrics info
        metrics.set_info(version="1.0.0", environment=os.getenv("ENVIRONMENT", "development"))

        logger.info("scheduler_initialized")

    def run_scraper(self, source_type: SourceType) -> None:
        """Execute a scraper with circuit breaker protection.

        Args:
            source_type: The type of source to scrape
        """
        scraper, circuit_breaker = self.scrapers[source_type]

        with _tracer.start_as_current_span(
            "scheduler.run_scraper",
            attributes={"source_type": source_type.value, "scraper": scraper.name},
        ) as span:
            self._run_scraper_inner(source_type, scraper, circuit_breaker, span)

    def _run_scraper_inner(self, source_type, scraper, circuit_breaker, span) -> None:
        logger.info(
            "scraper_starting",
            source_type=source_type.value,
            scraper=scraper.name,
        )

        # Check circuit breaker
        if not circuit_breaker.can_execute():
            logger.warning(
                "circuit_open_skipping",
                source_type=source_type.value,
                state=circuit_breaker.state.value,
            )
            metrics.record_circuit_state(source_type.value, circuit_breaker.state.value)
            return

        try:
            # Execute scrape
            start_time = time.time()
            result = scraper.scrape()
            duration_seconds = time.time() - start_time

            if result.success:
                circuit_breaker.record_success()

                # Process new items
                new_items = self._filter_new_items(result.items, source_type)

                logger.info(
                    "scraper_completed",
                    source_type=source_type.value,
                    items_found=result.items_found,
                    items_new=len(new_items),
                    duration_ms=duration_seconds * 1000,
                )

                # Record metrics
                metrics.record_scrape(
                    source_type=source_type.value,
                    success=True,
                    duration_seconds=duration_seconds,
                    items_found=result.items_found,
                    items_new=len(new_items),
                )

                # Process new items
                if new_items:
                    self._process_new_items(new_items, source_type)

            else:
                circuit_breaker.record_failure()
                metrics.record_circuit_failure(source_type.value)

                logger.error(
                    "scraper_failed",
                    source_type=source_type.value,
                    error=result.error_message,
                )

                metrics.record_scrape(
                    source_type=source_type.value,
                    success=False,
                    duration_seconds=duration_seconds,
                )
            
            # Update last results for health reporting
            self.last_results[source_type] = result

        except CircuitOpenError:
            logger.warning(
                "circuit_open",
                source_type=source_type.value,
            )

        except Exception as e:
            circuit_breaker.record_failure()
            metrics.record_circuit_failure(source_type.value)

            logger.exception(
                "scraper_exception",
                source_type=source_type.value,
                error=str(e),
            )

        finally:
            metrics.record_circuit_state(source_type.value, circuit_breaker.state.value)

    def _filter_new_items(
        self, items: List[EnforcementItem], source_type: SourceType
    ) -> List[EnforcementItem]:
        """Filter out previously seen items.

        NOTE: This method INTENTIONALLY does not call ``mark_seen``. Marking an
        item as seen before it has been successfully emitted downstream causes
        permanent data loss on a broker outage (issue #1136). Call
        :meth:`_mark_items_seen` only after successful emission.

        Args:
            items: List of enforcement items
            source_type: Source type for state tracking

        Returns:
            List of new items only
        """
        new_items = []

        for item in items:
            # Create content for hashing (title + summary + url)
            content = f"{item.title}|{item.summary or ''}|{item.url}"

            if self.state_manager.is_new(item.source_id, content):
                new_items.append(item)

        return new_items

    def _mark_items_seen(
        self, items: List[EnforcementItem], source_type: SourceType
    ) -> None:
        """Persist the ``seen`` mark for items that have been emitted.

        Used as the second half of an at-least-once emit-then-ack flow
        (see #1136). If ``mark_seen`` itself fails mid-loop, the remaining
        items stay un-marked and will be retried on the next scheduler tick
        (downstream consumers must be idempotent on ``source_id``).
        """
        for item in items:
            content = f"{item.title}|{item.summary or ''}|{item.url}"
            try:
                self.state_manager.mark_seen(
                    source_id=item.source_id,
                    source_type=source_type.value,
                    content=content,
                    title=item.title,
                    url=item.url,
                )
            except Exception as e:  # pragma: no cover — logged, retried next tick
                logger.error(
                    "mark_seen_failed",
                    source_id=item.source_id,
                    source_type=source_type.value,
                    error=str(e),
                )
                # Stop marking; remaining items will be re-attempted next run.
                return

    def _process_new_items(
        self, items: List[EnforcementItem], source_type: SourceType
    ) -> None:
        """Process newly detected enforcement items.

        Emits first, then marks items as seen only if the primary emission
        succeeded without exception. This is the at-least-once path that
        closes issue #1136: a Kafka outage leaves items un-seen so they
        are re-attempted on the next tick rather than silently dropped.
        Downstream consumers must be idempotent on ``source_id``.

        Args:
            items: List of new enforcement items
            source_type: Source type
        """
        logger.info(
            "processing_new_items",
            source_type=source_type.value,
            count=len(items),
        )

        # Emit to Kafka (enforcement events). This is the authoritative
        # emission: if it raises, items stay un-marked and will be retried.
        primary_emit_succeeded = False
        try:
            success, failures = self.kafka_producer.emit_batch(items)
            logger.info(
                "kafka_events_emitted",
                source_type=source_type.value,
                success=success,
                failures=failures,
            )
            # Any hard failure means "not safe to mark seen" — retry next tick.
            # (Partial per-item failures from emit_batch() are tracked by its
            # own retry/DLQ; see #1147 follow-up.)
            primary_emit_succeeded = failures == 0
            if failures > 0:
                metrics.record_kafka_emit_failure(
                    source_type=source_type.value,
                    failure_mode="partial_batch",
                    count=failures,
                )
        except (ConnectionError, TimeoutError, OSError, RuntimeError) as e:
            logger.error(
                "kafka_emission_failed",
                source_type=source_type.value,
                count=len(items),
                error=str(e),
            )
            metrics.record_kafka_emit_failure(
                source_type=source_type.value,
                failure_mode="hard_exception",
                count=len(items),
            )

        # Transform FDA recalls to FSMA events and emit to graph consumer
        try:
            transformer = get_fsma_transformer()
            fsma_events = transformer.transform_batch(items)

            if fsma_events:
                fsma_success, fsma_failures = self.kafka_producer.emit_fsma_batch(fsma_events)
                logger.info(
                    "fsma_events_emitted",
                    success=fsma_success,
                    failures=fsma_failures,
                    topic="fsma.events.extracted",
                )
        except (ValueError, TypeError, KeyError, RuntimeError) as e:
            logger.error("fsma_transformation_failed", error=str(e))

        # Send webhook notifications
        try:
            results = self.notifier.notify(items)
            successful = sum(1 for r in results if r.success)
            logger.info(
                "webhooks_delivered",
                total=len(results),
                successful=successful,
            )
        except (ConnectionError, TimeoutError, OSError, RuntimeError) as e:
            logger.error("webhook_notification_failed", error=str(e))

        # Tenant recall matching — activate ComplianceIntegration for FDA recalls
        if source_type == SourceType.FDA_RECALL and items:
            try:
                from app.compliance_integration import get_compliance_integration
                integration = get_compliance_integration()
                for item in items:
                    integration.process_enforcement_item(item)
                logger.info("compliance_integration_processed", count=len(items))
            except Exception as e:
                logger.error("compliance_integration_failed", error=str(e))

        # Log high-priority items
        for item in items:
            if item.severity in [EnforcementSeverity.CRITICAL, EnforcementSeverity.HIGH]:
                logger.warning(
                    "high_priority_enforcement_detected",
                    source_type=source_type.value,
                    severity=item.severity.value,
                    title=item.title,
                    url=item.url,
                )

        # FINAL: mark items seen only if the primary emission succeeded
        # cleanly. If Kafka was down the items stay un-marked and the next
        # scheduler tick will re-discover and re-emit them (#1136).
        if primary_emit_succeeded:
            self._mark_items_seen(items, source_type)
        else:
            logger.warning(
                "items_not_marked_seen_will_retry",
                source_type=source_type.value,
                count=len(items),
                reason="primary_emission_failed_or_partial",
            )

    def schedule_jobs(self) -> None:
        """Schedule all scraping jobs."""
        settings = self.settings

        # FDA Warning Letters - hourly by default
        self.scheduler.add_job(
            self.run_scraper,
            args=[SourceType.FDA_WARNING_LETTER],
            trigger=IntervalTrigger(minutes=settings.fda_warning_letters_interval),
            id="fda_warning_letters",
            name="FDA Warning Letters Scraper",
            replace_existing=True,
        )
        logger.info(
            "job_scheduled",
            job_id="fda_warning_letters",
            interval_minutes=settings.fda_warning_letters_interval,
        )

        # FDA Import Alerts - every 2 hours by default
        self.scheduler.add_job(
            self.run_scraper,
            args=[SourceType.FDA_IMPORT_ALERT],
            trigger=IntervalTrigger(minutes=settings.fda_import_alerts_interval),
            id="fda_import_alerts",
            name="FDA Import Alerts Scraper",
            replace_existing=True,
        )
        logger.info(
            "job_scheduled",
            job_id="fda_import_alerts",
            interval_minutes=settings.fda_import_alerts_interval,
        )

        # FDA Recalls - every 30 minutes by default (critical for FSMA 204)
        self.scheduler.add_job(
            self.run_scraper,
            args=[SourceType.FDA_RECALL],
            trigger=IntervalTrigger(minutes=settings.fda_recalls_interval),
            id="fda_recalls",
            name="FDA Recalls Scraper",
            replace_existing=True,
        )
        logger.info(
            "job_scheduled",
            job_id="fda_recalls",
            interval_minutes=settings.fda_recalls_interval,
        )

        # Regulatory Discovery - daily (Nightly)
        self.scheduler.add_job(
            self.run_scraper,
            args=[SourceType.REGULATORY_DISCOVERY],
            trigger=IntervalTrigger(minutes=settings.regulatory_discovery_interval),
            id="regulatory_discovery",
            name="Regulatory Discovery Bulk Sync",
            replace_existing=True,
        )
        logger.info(
            "job_scheduled",
            job_id="regulatory_discovery",
            interval_minutes=settings.regulatory_discovery_interval,
        )

        # State cleanup - daily
        self.scheduler.add_job(
            self.cleanup_state,
            trigger=IntervalTrigger(hours=24),
            id="state_cleanup",
            name="State Cleanup (90 days)",
            replace_existing=True,
        )

        # Deadline monitoring — check every 5 minutes for overdue/critical cases
        self.scheduler.add_job(
            self.check_request_deadlines,
            trigger=IntervalTrigger(minutes=5),
            id="deadline_monitor",
            name="FDA Request Deadline Monitor",
            replace_existing=True,
        )
        logger.info("job_scheduled", job_id="deadline_monitor", interval_minutes=5)

        # Inactive account disablement — NIST AC-2(3) (#974)
        self.scheduler.add_job(
            self.disable_inactive_accounts,
            trigger=IntervalTrigger(hours=24),
            id="inactive_account_sweep",
            name="Disable Inactive Accounts (90 days)",
            replace_existing=True,
        )
        logger.info("job_scheduled", job_id="inactive_account_sweep", interval_hours=24)

        # KDE retention enforcement — FSMA 204 24-month minimum (#973)
        self.scheduler.add_job(
            self.enforce_kde_retention,
            trigger=IntervalTrigger(hours=24),
            id="kde_retention_enforcement",
            name="KDE Retention Enforcement (24-month floor)",
            replace_existing=True,
        )
        logger.info("job_scheduled", job_id="kde_retention_enforcement", interval_hours=24)

        # Data archival/purge — retention policy enforcement (#983)
        self.scheduler.add_job(
            self.archive_expired_records,
            trigger=IntervalTrigger(hours=24),
            id="data_archival",
            name="Archive Expired Records",
            replace_existing=True,
        )
        logger.info("job_scheduled", job_id="data_archival", interval_hours=24)

        # Task queue retention — purge completed/dead rows (#1382)
        self.scheduler.add_job(
            self.purge_old_tasks,
            trigger=IntervalTrigger(hours=24),
            id="task_queue_purge",
            name="Task Queue Retention (30-day purge)",
            replace_existing=True,
        )
        logger.info("job_scheduled", job_id="task_queue_purge", interval_hours=24)

        # Nightly FSMA source sync — Phase 29 (#1135).
        # Previously defined in app/jobs.py on an orphaned BlockingScheduler
        # that was never started; the job has been running nowhere in
        # production. Re-home it on the real scheduler here.
        self.scheduler.add_job(
            self.run_fsma_nightly_sync,
            trigger=CronTrigger(hour=2, minute=0, timezone=utc),
            id="fsma_nightly_sync",
            name="Nightly FSMA Source Sync (02:00 UTC)",
            misfire_grace_time=300,  # 5-minute grace window
            replace_existing=True,
        )
        logger.info("job_scheduled", job_id="fsma_nightly_sync", cron="02:00 UTC")

        logger.info(
            "scheduler_ready",
            total_jobs=9,
            scrapers=list(self.scrapers.keys()),
        )

    def purge_old_tasks(self) -> None:
        """Purge completed/dead ``fsma.task_queue`` rows older than 30 days.

        Closes #1382. Without this, completed and dead rows accumulate
        forever: index bloat on ``idx_task_queue_tenant``, slower ad-hoc
        observability queries, and ever-growing storage cost on Railway
        Postgres.
        """
        try:
            from shared.database import SessionLocal
            from sqlalchemy import text as _sqltext

            db = SessionLocal()
            try:
                result = db.execute(
                    _sqltext(
                        """
                        DELETE FROM fsma.task_queue
                        WHERE status IN ('completed', 'dead')
                          AND COALESCE(completed_at, created_at)
                              < NOW() - INTERVAL '30 days'
                        RETURNING id
                        """
                    )
                )
                rows = result.fetchall()
                db.commit()
                if rows:
                    logger.info("task_queue_purged", rows=len(rows))
                else:
                    logger.debug("task_queue_purge_noop")
            finally:
                db.close()
        except (ImportError, RuntimeError, ConnectionError, ValueError) as e:
            logger.error("task_queue_purge_failed", error=str(e))

    def run_fsma_nightly_sync(self) -> None:
        """Trigger a full FSMA source sync via the ingestion service.

        Phase 29 / #1135. Formerly defined in ``app/jobs.py`` on a module-
        level :class:`BlockingScheduler` that was never started. The
        ingestion endpoint handles deduplication (ETag + SHA-256), so
        re-running on unchanged sources is safe.
        """
        import httpx
        from app.config import get_settings as _get_settings

        settings = _get_settings()
        ingestion_url = os.getenv(
            "INGESTION_SERVICE_URL", settings.ingestion_service_url
        )

        # #1063 — fail loudly if the internal auth secret is missing or
        # empty rather than sending a blank X-RegEngine-API-Key header
        # that will 401 silently.
        api_key = os.getenv("REGENGINE_INTERNAL_SECRET", "").strip()
        if not api_key:
            logger.error(
                "fsma_nightly_sync_skipped_missing_secret",
                hint="Set REGENGINE_INTERNAL_SECRET to a non-empty value",
            )
            return

        logger.info("fsma_nightly_sync_started", ingestion_url=ingestion_url)
        try:
            response = httpx.post(
                f"{ingestion_url}/v1/ingest/all-regulations",
                headers={"X-RegEngine-API-Key": api_key},
                timeout=120.0,
            )
            response.raise_for_status()
            summary = response.json() if response.content else {}
            logger.info(
                "fsma_nightly_sync_complete",
                sources_attempted=summary.get("sources_attempted"),
                ingested=summary.get("ingested"),
                unchanged=summary.get("unchanged"),
                failed=summary.get("failed"),
            )
        except httpx.HTTPError as exc:
            logger.error("fsma_nightly_sync_http_failed", error=str(exc))
        except Exception as exc:
            logger.error("fsma_nightly_sync_failed", error=str(exc))

    def check_request_deadlines(self) -> None:
        """Check all tenants for overdue/critical FDA request deadlines.

        Queries all active request cases and logs warnings for any that are
        overdue or approaching their deadline (<2 hours). Designed to run
        every 5 minutes via APScheduler.
        """
        with _tracer.start_as_current_span("scheduler.check_request_deadlines"):
            self._check_request_deadlines_inner()

    def _check_request_deadlines_inner(self) -> None:
        try:
            from shared.database import SessionLocal
            from shared.request_workflow import RequestWorkflow

            db = SessionLocal()
            try:
                workflow = RequestWorkflow(db)

                # Get all distinct tenant IDs with active cases
                result = db.execute(
                    __import__("sqlalchemy").text("""
                        SELECT DISTINCT tenant_id
                        FROM fsma.request_cases
                        WHERE package_status NOT IN ('submitted', 'amended')
                          AND response_due_at IS NOT NULL
                    """)
                )
                tenant_ids = [str(r[0]) for r in result.fetchall()]

                total_overdue = 0
                total_critical = 0

                for tid in tenant_ids:
                    # Set tenant context for RLS before per-tenant queries
                    db.execute(__import__("sqlalchemy").text(
                        "SET LOCAL app.tenant_id = :tid"
                    ), {"tid": tid})
                    cases = workflow.check_deadline_status(tid)
                    overdue = [c for c in cases if c["urgency"] == "overdue"]
                    critical = [c for c in cases if c["urgency"] == "critical"]
                    total_overdue += len(overdue)
                    total_critical += len(critical)

                    for case in overdue:
                        logger.error(
                            "deadline_overdue",
                            tenant_id=tid,
                            case_id=case["request_case_id"],
                            hours_overdue=abs(case["hours_remaining"]),
                            status=case["package_status"],
                            requesting_party=case["requesting_party"],
                        )

                    for case in critical:
                        logger.warning(
                            "deadline_critical",
                            tenant_id=tid,
                            case_id=case["request_case_id"],
                            hours_remaining=case["hours_remaining"],
                            status=case["package_status"],
                        )

                if total_overdue > 0 or total_critical > 0:
                    logger.warning(
                        "deadline_monitor_summary",
                        total_overdue=total_overdue,
                        total_critical=total_critical,
                        tenants_checked=len(tenant_ids),
                    )
                else:
                    logger.debug(
                        "deadline_monitor_ok",
                        tenants_checked=len(tenant_ids),
                    )
            finally:
                db.close()
        except (ImportError, RuntimeError, ConnectionError, ValueError) as e:
            logger.error("deadline_monitor_failed", error=str(e))

    def disable_inactive_accounts(self) -> None:
        """Disable accounts with no login for 90+ days — NIST AC-2(3) (#974)."""
        try:
            from shared.database import SessionLocal

            db = SessionLocal()
            try:
                result = db.execute(
                    __import__("sqlalchemy").text("""
                        UPDATE users
                        SET status = 'disabled'
                        WHERE status = 'active'
                          AND last_login_at IS NOT NULL
                          AND last_login_at < NOW() - INTERVAL '90 days'
                        RETURNING id, email
                    """)
                )
                disabled = result.fetchall()
                db.commit()

                if disabled:
                    logger.warning(
                        "inactive_accounts_disabled",
                        count=len(disabled),
                        user_ids=[str(r[0]) for r in disabled],
                    )
                else:
                    logger.debug("inactive_account_sweep_ok", disabled_count=0)
            finally:
                db.close()
        except (ImportError, RuntimeError, ConnectionError, ValueError) as e:
            logger.error("inactive_account_sweep_failed", error=str(e))

    def enforce_kde_retention(self) -> None:
        """Verify no KDE records younger than 24 months have been deleted — FSMA 204 (#973).

        This is a compliance guard: it checks that the minimum record count
        for recent months hasn't dropped (which would indicate premature deletion).
        """
        try:
            from shared.database import SessionLocal

            db = SessionLocal()
            try:
                # Check that audit trail records within the 24-month window exist
                result = db.execute(
                    __import__("sqlalchemy").text("""
                        SELECT COUNT(*) as cnt
                        FROM fsma.fsma_audit_trail
                        WHERE created_at >= NOW() - INTERVAL '24 months'
                    """)
                )
                row = result.fetchone()
                count = row[0] if row else 0
                if count == 0:
                    logger.warning(
                        "kde_retention_warning",
                        message="No audit trail records found within 24-month retention window",
                    )
                else:
                    logger.debug("kde_retention_ok", records_in_window=count)
            finally:
                db.close()
        except (ImportError, RuntimeError, ConnectionError, ValueError) as e:
            logger.error("kde_retention_check_failed", error=str(e))

    def archive_expired_records(self) -> None:
        """Archive records past retention limits — NIST AU-4 (#983).

        Retention defaults (from ingestion settings):
        - CTE events: 1095 days (3 years)
        - Audit logs: 2555 days (7 years)
        - FDA exports: 365 days (1 year)
        """
        try:
            from shared.database import SessionLocal

            db = SessionLocal()
            try:
                # Archive FDA exports older than 1 year
                result = db.execute(
                    __import__("sqlalchemy").text("""
                        DELETE FROM fsma.fda_exports
                        WHERE created_at < NOW() - INTERVAL '365 days'
                        RETURNING id
                    """)
                )
                deleted_exports = len(result.fetchall())

                # Archive CTE events older than 3 years
                result = db.execute(
                    __import__("sqlalchemy").text("""
                        DELETE FROM fsma.cte_events
                        WHERE created_at < NOW() - INTERVAL '1095 days'
                        RETURNING id
                    """)
                )
                deleted_ctes = len(result.fetchall())

                # Archive sysadmin access logs older than 7 years (NIST AU-4, #1009)
                deleted_audit = 0
                try:
                    result = db.execute(
                        __import__("sqlalchemy").text("""
                            DELETE FROM audit.sysadmin_access_log
                            WHERE accessed_at < NOW() - INTERVAL '2555 days'
                            RETURNING id
                        """)
                    )
                    deleted_audit = len(result.fetchall())
                except Exception:
                    pass  # Table may not exist on all databases

                db.commit()

                if deleted_exports > 0 or deleted_ctes > 0 or deleted_audit > 0:
                    logger.info(
                        "data_archival_complete",
                        deleted_exports=deleted_exports,
                        deleted_ctes=deleted_ctes,
                        deleted_audit_logs=deleted_audit,
                    )
                else:
                    logger.debug("data_archival_noop", message="No expired records to archive")
            finally:
                db.close()
        except (ImportError, RuntimeError, ConnectionError, ValueError) as e:
            logger.error("data_archival_failed", error=str(e))

    def run_initial_scrape(self) -> None:
        """Run all scrapers immediately on startup."""
        logger.info("running_initial_scrape")

        for source_type in self.scrapers.keys():
            try:
                self.run_scraper(source_type)
            except Exception as e:
                logger.error(
                    "initial_scrape_failed",
                    source_type=source_type.value,
                    error=str(e),
                )

    def start(self) -> None:
        """Start the scheduler service with distributed leadership."""
        self.initialize()
        
        logger.info("scheduler_joining_cluster")
        
        # Calculate robust lock ID based on service name if needed, 
        # but DistributedContext uses a constant.
        
        try:
            # This blocks until leadership is acquired, then runs local scheduler
            self.distributed_context.wait_for_leadership(self._run_scheduler_workload)
        except (KeyboardInterrupt, SystemExit):
            logger.info("scheduler_shutdown_signal_received")
            self.shutdown()

    def _run_scheduler_workload(self) -> None:
        """The workload to run when this instance is the Leader."""
        logger.info("leadership_acquired_initializing_workload")

        # #1144 — persisted last-run tracking + missed-run alerting.
        # Install the APScheduler event listener BEFORE scheduling jobs so
        # the very first execution is recorded.
        self._install_job_run_listener()

        # We only schedule/update jobs if we are the leader
        self.schedule_jobs()

        # Run initial scrape (on promotion to leader)
        self.run_initial_scrape()

        logger.info("scheduler_starting_mainloop")
        try:
            # BlockingScheduler.start() is blocking, so this holds the leader lock
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            pass
        except Exception as e:
            logger.error("scheduler_crashed", error=str(e))
            raise e
            
    def cleanup_state(self) -> None:
        """Wrapper for state cleanup to avoid lambda serialization issues."""
        self.state_manager.cleanup_old_items(days=90)

    def _install_job_run_listener(self) -> None:
        """Attach APScheduler listeners for EXECUTED / ERROR / MISSED (#1144).

        Persists ``(job_id, last_run_at, last_success_at, last_status)``
        to ``scheduler_job_runs`` on every run and logs `job_missed` at
        ERROR on misfire — the old code silently dropped missed runs if
        they were older than ``misfire_grace_time=3600``.
        """
        try:
            state_manager = self.state_manager
        except AttributeError:  # pragma: no cover
            return

        def _listener(event):
            try:
                if event.code == EVENT_JOB_EXECUTED:
                    state_manager.record_job_run(event.job_id, success=True)
                elif event.code == EVENT_JOB_ERROR:
                    state_manager.record_job_run(
                        event.job_id,
                        success=False,
                        error=str(getattr(event, "exception", "")),
                    )
                elif event.code == EVENT_JOB_MISSED:
                    logger.error(
                        "scheduler_job_missed",
                        job_id=event.job_id,
                        scheduled_run_time=str(
                            getattr(event, "scheduled_run_time", "unknown")
                        ),
                    )
                    state_manager.record_job_run(
                        event.job_id,
                        success=False,
                        error="MISSED",
                    )
            except Exception:  # pragma: no cover — telemetry must not crash
                logger.exception("job_run_listener_error", job_id=getattr(event, "job_id", "?"))

        self.scheduler.add_listener(
            _listener,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED,
        )
        logger.info("job_run_listener_installed")

    def shutdown(self) -> None:
        """Gracefully shutdown the scheduler."""
        logger.info("scheduler_shutting_down")

        try:
            self.scheduler.shutdown(wait=True)
        except (RuntimeError, SchedulerNotRunningError) as e:
            logger.warning("scheduler_shutdown_skipped", error=str(e))

        try:
            self.kafka_producer.close()
        except (RuntimeError, ConnectionError, OSError) as e:
            logger.error("kafka_close_failed", error=str(e))

        logger.info("scheduler_stopped")


class HealthHandler(BaseHTTPRequestHandler):
    """HTTP handler for health checks and metrics."""

    scheduler_service: Optional[SchedulerService] = None

    def do_GET(self) -> None:
        if self.path == "/health":
            self._handle_health()
        elif self.path == "/metrics":
            self._handle_metrics()
        elif self.path == "/status":
            self._handle_status()
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_health(self) -> None:
        """Return health status."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"healthy","service":"scheduler"}')

    def _handle_metrics(self) -> None:
        """Return Prometheus metrics (requires X-Metrics-Key header)."""
        expected = os.environ.get("METRICS_API_KEY", "")
        provided = self.headers.get("X-Metrics-Key", "")
        if not expected or provided != expected:
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"detail":"Forbidden"}')
            return
        content = metrics.get_metrics()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(content)

    def _handle_status(self) -> None:
        """Return detailed status."""
        import json

        status = {
            "service": "scheduler",
            "status": "running",
            "circuit_breakers": circuit_registry.get_all_status(),
            "last_scrapes": {
                st.value: {
                    "success": r.success,
                    "count": r.items_found,
                    "scraped_at": r.scraped_at.isoformat(),
                    "error": r.error_message if not r.success else None
                }
                for st, r in self.scheduler_service.last_results.items()
            } if self.scheduler_service else {}
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(status).encode())

    def log_message(self, format: str, *args) -> None:
        """Suppress default logging."""
        pass


def start_health_server(port: int) -> None:
    """Start the health check HTTP server."""
    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        logger.info("health_server_started", port=port)
        server.serve_forever()
    except (OSError, RuntimeError) as e:
        logger.error("health_server_failed", error=str(e))


def _install_graceful_shutdown_handlers() -> None:
    """Translate SIGTERM / SIGINT to :class:`KeyboardInterrupt` on the main thread.

    Railway and Kubernetes send **SIGTERM** (not SIGINT) when rolling a
    deploy. Python's default SIGTERM disposition terminates the process
    without unwinding — `SchedulerService.shutdown()` never runs,
    `BlockingScheduler.shutdown(wait=True)` never gets to cancel
    in-flight jobs, and `kafka_producer.close()` never flushes. Any
    Kafka producer buffer at the moment of the kill is lost (#1255).

    By raising :class:`KeyboardInterrupt` from our SIGTERM handler we
    hit the existing ``try/except (KeyboardInterrupt, SystemExit):``
    block in ``SchedulerService.start`` which cleanly shuts the
    BlockingScheduler and the Kafka producer.
    """
    import signal

    def _sigterm_handler(signum, frame):
        logger.info("scheduler_received_signal", signum=int(signum))
        raise KeyboardInterrupt()

    # Only install in the main thread (signal.signal is a main-thread-only API).
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, _sigterm_handler)
        signal.signal(signal.SIGINT, _sigterm_handler)
        logger.info("sigterm_handler_installed")


def main() -> None:
    """Main entry point."""
    # #1255 — translate SIGTERM/SIGINT into KeyboardInterrupt so our
    # existing shutdown path runs on Railway rolling deploys.
    _install_graceful_shutdown_handlers()

    settings = get_settings()

    # Start health server in background thread
    health_thread = threading.Thread(
        target=start_health_server,
        args=(settings.health_port,),
        daemon=True,
    )
    health_thread.start()

    # Create and start scheduler service
    service = SchedulerService()
    HealthHandler.scheduler_service = service
    service.start()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Use basic logging as fallback if structlog fails
        import logging
        logging.error(f"Critical scheduler failure: {e}", exc_info=True)
        sys.exit(1)
