"""SchedulerService — APScheduler job orchestration for regulatory monitoring.

Extracted from ``services/scheduler/main.py`` so the consolidated monolith
(``server.main``) can run these jobs in-process via
``server/workers/embedded_scheduler.py``. The standalone entrypoint
(``services/scheduler/main.py``) remains for local debugging and imports
:class:`SchedulerService` from here.

This module is import-safe in production: it carries no
``assert_legacy_entrypoint_not_in_production`` guard, does not call
``structlog.configure`` (the host process owns logging config), and uses
fully-qualified ``services.scheduler.app`` imports so it cannot collide
with the other services' ``app`` packages on the monolith's ``sys.path``.

Features:
- FDA Warning Letters, Import Alerts, and Recalls scraping
- Circuit breaker pattern for resilient execution
- Deduplication via PostgreSQL state persistence
- Kafka event emission for downstream processing (only when
  ``EVENT_BACKBONE=kafka`` — see #1159)
- Webhook notifications for real-time alerts
- Recall→tenant compliance alerting
- Prometheus metrics for observability
- Single-leader execution via PostgreSQL advisory lock
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import structlog
from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MISSED,
)
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.base import SchedulerNotRunningError
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from pytz import utc
from shared.event_backbone import kafka_enabled
from shared.observability import setup_standalone_observability
from shared.observability.context import wrap_job_with_new_correlation
from shared.task_types import NON_WORKER_TASK_TYPES, PURGEABLE_TASK_TYPES
from sqlalchemy.exc import SQLAlchemyError

from services.scheduler.app.circuit_breaker import CircuitBreaker, CircuitOpenError, circuit_registry
from services.scheduler.app.config import get_settings
from services.scheduler.app.distributed import DistributedContext
from services.scheduler.app.fda_fsma_transformer import get_fsma_transformer
from services.scheduler.app.kafka_producer import get_kafka_producer
from services.scheduler.app.metrics import metrics
from services.scheduler.app.models import (
    EnforcementItem,
    EnforcementSeverity,
    ScrapeResult,
    SourceType,
)
from services.scheduler.app.notifications import WebhookNotifier
from services.scheduler.app.scrapers import (
    FDAImportAlertsScraper,
    FDARecallsScraper,
    FDAWarningLettersScraper,
)
from services.scheduler.app.scrapers.base import BaseScraper
from services.scheduler.app.state import StateManager

_tracer = setup_standalone_observability("scheduler")

logger = structlog.get_logger("scheduler")

# #2697: alert after this many consecutive successful-but-zero-item scrapes
# of the same source (and again at every multiple, to re-page without
# spamming every run).
_STALE_COVERAGE_ZERO_RUNS = 7


def _strict_database_role_cutover_enabled() -> bool:
    """Return whether control-plane work must be absent from DATABASE_URL."""
    environment = (
        (os.getenv("REGENGINE_ENV", "") or os.getenv("ENVIRONMENT", "") or os.getenv("ENV", "")).strip().lower()
    )
    return environment in {"staging", "production"} or os.getenv(
        "REGENGINE_REQUIRE_RLS_ENFORCEMENT", ""
    ).strip().lower() in {"1", "true", "yes", "on"}


class SchedulerService:
    """Main scheduler service orchestrating all components."""

    DEADLINE_TENANT_SCAN_LIMIT = 5000
    DEADLINE_RENOTIFY_SECONDS = 3600
    DEADLINE_ALERT_STATE_MAX = 10000

    def __init__(self):
        self._deadline_alert_state = {}
        self._deadline_alert_entries = 0
        self.settings = get_settings()
        self.state_manager = StateManager()
        # #1150 — pass the on-disk outbox path so failed deliveries
        # survive restart. Empty string → legacy in-memory-only behavior.
        self.notifier = WebhookNotifier(
            outbox_path=self.settings.webhook_outbox_path or None,
        )
        self.kafka_producer = get_kafka_producer()
        self.distributed_context = DistributedContext()

        # Fortune Top 15 Resilience Configuration
        jobstores = {"default": MemoryJobStore()}
        executors = {"default": ThreadPoolExecutor(20)}
        job_defaults = {
            "coalesce": True,  # Roll multiple missed executions into one
            "max_instances": 3,
            "misfire_grace_time": 3600,  # 1 hour grace for missed jobs (resilience)
        }

        self.scheduler = BlockingScheduler(
            jobstores=jobstores, executors=executors, job_defaults=job_defaults, timezone=utc
        )
        self.scheduler_thread = None
        self._start_time = time.time()

        # Initialize scrapers with circuit breakers.
        # NOTE: the former REGULATORY_DISCOVERY "scraper" was removed from
        # this dict — it POSTed the same /v1/ingest/all-regulations endpoint
        # the fsma_nightly_sync job covers (with credentials require_api_key
        # never accepted), so it was a broken duplicate.
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
        }
        self.last_results: Dict[SourceType, ScrapeResult] = {}
        # #2697: consecutive successful-but-empty scrapes per source. A dead
        # feed (RSS 404 + empty API fallback) reports success=True,
        # items_found=0 forever; alert when coverage looks stale.
        self._consecutive_zero_scrapes: Dict[SourceType, int] = {}

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

                # #2697: stale-coverage alert. success=True with zero items
                # is normal occasionally, but N consecutive empty runs means
                # the feed is probably dead (bot-blocked / defunct RSS) and
                # coverage has silently stopped.
                if result.items_found == 0:
                    streak = self._consecutive_zero_scrapes.get(source_type, 0) + 1
                    self._consecutive_zero_scrapes[source_type] = streak
                    if streak >= _STALE_COVERAGE_ZERO_RUNS and streak % _STALE_COVERAGE_ZERO_RUNS == 0:
                        logger.error(
                            "scrape_coverage_stale",
                            source_type=source_type.value,
                            consecutive_zero_item_runs=streak,
                            note="scraper reports success but has returned 0 items repeatedly — feed may be dead or bot-blocked",
                        )
                else:
                    self._consecutive_zero_scrapes[source_type] = 0

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

    def _filter_new_items(self, items: List[EnforcementItem], source_type: SourceType) -> List[EnforcementItem]:
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

    def _mark_items_seen(self, items: List[EnforcementItem], source_type: SourceType) -> None:
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

    def _unpersisted_webhook_count(self) -> Optional[int]:
        """Best-effort read of the notifier's unpersisted dead-letter count.

        Returns None when the notifier does not expose a real integer
        counter (stubbed notifiers in tests, future replacements), in
        which case the webhook ack gate stays out of the way.
        """
        getter = getattr(getattr(self, "notifier", None), "unpersisted_dead_letter_count", None)
        if not callable(getter):
            return None
        try:
            value = getter()
        except Exception:  # pragma: no cover — observability must not break the tick
            return None
        return value if isinstance(value, int) else None

    def _webhook_unpersisted_grew(self, before: Optional[int]) -> bool:
        """True when notify() added an unpersisted dead letter this tick."""
        if before is None:
            return False
        after = self._unpersisted_webhook_count()
        return after is not None and after > before

    def _process_new_items(self, items: List[EnforcementItem], source_type: SourceType) -> None:
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

        # #1159 — the default production event backbone is PostgreSQL;
        # Kafka emission only happens when EVENT_BACKBONE=kafka. In pg
        # mode no Kafka consumers are deployed, emitting would stall each
        # tick on broker flush timeouts, and the emit-then-ack gate below
        # would never allow items to be marked seen. Treat the skipped
        # emission as successful so webhook delivery and compliance
        # alerting still ack items.
        if not kafka_enabled():
            primary_emit_succeeded = True
            logger.info(
                "kafka_emission_skipped",
                backbone="pg",
                source_type=source_type.value,
                count=len(items),
            )
        else:
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
                    if fsma_failures > 0:
                        # #2697: fsma emission failures do not gate the
                        # seen-ack (gating risks reprocessing loops for a
                        # best-effort mirror) — but they must be loud, not
                        # an info line.
                        logger.error(
                            "fsma_events_emit_failures",
                            success=fsma_success,
                            failures=fsma_failures,
                            topic="fsma.events.extracted",
                        )
                        metrics.record_kafka_emit_failure(
                            source_type=source_type.value,
                            failure_mode="fsma_partial_batch",
                            count=fsma_failures,
                        )
                    else:
                        logger.info(
                            "fsma_events_emitted",
                            success=fsma_success,
                            failures=fsma_failures,
                            topic="fsma.events.extracted",
                        )
            except (ValueError, TypeError, KeyError, RuntimeError) as e:
                logger.error("fsma_transformation_failed", error=str(e))
                metrics.record_kafka_emit_failure(
                    source_type=source_type.value,
                    failure_mode="fsma_transform_exception",
                    count=len(items),
                )

        # Send webhook notifications. A delivery that fails with no durable
        # outbox behind it is lost on restart, so the batch must NOT be
        # marked seen: the items stay un-marked and retry next tick
        # (downstream is idempotent on source_id). Durable-outbox failures
        # keep the old behavior — the outbox drain retries them.
        webhook_unpersisted_before = self._unpersisted_webhook_count()
        try:
            results = self.notifier.notify(items)
            successful = sum(1 for r in results if r.success)
            if successful < len(results):
                logger.warning(
                    "webhooks_delivered",
                    total=len(results),
                    successful=successful,
                )
            else:
                logger.info(
                    "webhooks_delivered",
                    total=len(results),
                    successful=successful,
                )
        except (ConnectionError, TimeoutError, OSError, RuntimeError) as e:
            logger.error("webhook_notification_failed", error=str(e))
        webhook_ack_withheld = self._webhook_unpersisted_grew(webhook_unpersisted_before)
        if webhook_ack_withheld:
            logger.warning(
                "webhook_ack_withheld",
                source_type=source_type.value,
                count=len(items),
                reason="webhook_delivery_unpersisted",
            )

        # Tenant recall matching — activate ComplianceIntegration for FDA recalls.
        # #2689 follow-up: source_ids whose tenant alerting failed are excluded
        # from the seen-ack below, so exactly those items retry next tick —
        # one failing item can neither drop the others' alerts nor force the
        # succeeded ones to re-emit.
        failed_alert_source_ids: set = set()
        if source_type == SourceType.FDA_RECALL and items:
            try:
                from services.scheduler.app.compliance_integration import get_compliance_integration

                integration = get_compliance_integration()
            except Exception as e:
                # Constructing the integration (engine init / import) failed —
                # no item can be processed. Log once, not per item, and
                # withhold every ack so the whole batch retries next tick.
                logger.error(
                    "compliance_integration_unavailable",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                integration = None
                failed_alert_source_ids = {item.source_id for item in items}

            if integration is not None:
                # Per-item try/except so one bad recall does not drop alerts for
                # the rest of the batch. Previously a single exception aborted
                # the whole loop while the batch was still marked seen below
                # (pg mode acks unconditionally), permanently losing the
                # remaining tenants' alerts. Narrow exception tuple + error_type
                # mirrors the per-tenant handler in compliance_integration.py
                # (RE-SCH-002); process_enforcement_item is idempotent
                # (ON CONFLICT DO NOTHING) so a future re-run is safe.
                processed = 0
                failed = 0
                for item in items:
                    try:
                        integration.process_enforcement_item(item)
                        processed += 1
                    except (SQLAlchemyError, ValueError, KeyError, TypeError, RuntimeError) as e:
                        failed += 1
                        failed_alert_source_ids.add(item.source_id)
                        logger.error(
                            "compliance_integration_item_failed",
                            source_id=getattr(item, "source_id", None),
                            error=str(e),
                            error_type=type(e).__name__,
                        )
                if failed:
                    logger.error(
                        "compliance_integration_partial_failure",
                        processed=processed,
                        failed=failed,
                        total=len(items),
                    )
                else:
                    logger.info("compliance_integration_processed", count=processed)

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
        # #2689 follow-up: additionally withhold the ack for exactly the
        # recall items whose tenant alerting failed, so those retry next
        # tick while the succeeded items ack once (no re-storm). The retry
        # re-runs the full pipeline for withheld items — downstream is
        # idempotent on source_id (documented at-least-once contract).
        if primary_emit_succeeded:
            if webhook_ack_withheld:
                # Unpersisted webhook failure (logged above as
                # webhook_ack_withheld): the dead letter dies with the
                # process, so nothing is marked seen and the whole batch
                # is re-discovered next tick.
                pass
            elif failed_alert_source_ids:
                to_ack = [i for i in items if i.source_id not in failed_alert_source_ids]
                logger.warning(
                    "recall_alert_ack_withheld",
                    source_type=source_type.value,
                    withheld=len(items) - len(to_ack),
                    acked=len(to_ack),
                    reason="compliance_alerting_failed_for_item",
                )
                if to_ack:
                    self._mark_items_seen(to_ack, source_type)
            else:
                self._mark_items_seen(items, source_type)
        else:
            logger.warning(
                "items_not_marked_seen_will_retry",
                source_type=source_type.value,
                count=len(items),
                reason="primary_emission_failed_or_partial",
            )

    @staticmethod
    def _near_boot_first_run(minutes: int) -> datetime:
        """First fire time for daily interval jobs.

        ``IntervalTrigger`` first fires at start_time + interval, and the
        embedded scheduler restarts on every Railway deploy. With deploys
        landing more than once a day, ``hours=24`` jobs never survive to
        their first fire — they starve indefinitely unless given an
        explicit near-boot ``next_run_time``. Staggered per job so the
        daily jobs don't all land at once right after boot.
        """
        return datetime.now(utc) + timedelta(minutes=minutes)

    def _add_tracked_job(self, fn: Callable, job_id: str, **kwargs) -> None:
        """Register a job on the APScheduler instance with context propagation.

        Each execution receives a fresh ``correlation_id`` of the form
        ``job:<job_id>:<uuid4>`` so every log line emitted by the job is
        traceable back to a single run without polluting the HTTP request
        trace space. The ``tenant_id`` / ``request_id`` contextvars are also
        seeded so structlog processors include them even for timer-driven jobs
        that are not tenant-specific.

        This is a thin wrapper around :func:`wrap_job_with_new_correlation`
        from ``shared.observability.context`` -- see that module for the
        threading contract.
        """
        wrapped = wrap_job_with_new_correlation(fn, job_id=job_id)
        self.scheduler.add_job(wrapped, id=job_id, replace_existing=True, **kwargs)

    def schedule_jobs(self) -> None:
        """Schedule all scraping jobs."""
        settings = self.settings

        # FDA Warning Letters - hourly by default
        self._add_tracked_job(
            lambda: self.run_scraper(SourceType.FDA_WARNING_LETTER),
            job_id="fda_warning_letters",
            trigger=IntervalTrigger(minutes=settings.fda_warning_letters_interval),
            name="FDA Warning Letters Scraper",
        )
        logger.info(
            "job_scheduled",
            job_id="fda_warning_letters",
            interval_minutes=settings.fda_warning_letters_interval,
        )

        # FDA Import Alerts - every 2 hours by default
        self._add_tracked_job(
            lambda: self.run_scraper(SourceType.FDA_IMPORT_ALERT),
            job_id="fda_import_alerts",
            trigger=IntervalTrigger(minutes=settings.fda_import_alerts_interval),
            name="FDA Import Alerts Scraper",
        )
        logger.info(
            "job_scheduled",
            job_id="fda_import_alerts",
            interval_minutes=settings.fda_import_alerts_interval,
        )

        # FDA Recalls - every 30 minutes by default (critical for FSMA 204)
        self._add_tracked_job(
            lambda: self.run_scraper(SourceType.FDA_RECALL),
            job_id="fda_recalls",
            trigger=IntervalTrigger(minutes=settings.fda_recalls_interval),
            name="FDA Recalls Scraper",
        )
        logger.info(
            "job_scheduled",
            job_id="fda_recalls",
            interval_minutes=settings.fda_recalls_interval,
        )

        # NOTE: the former "regulatory_discovery" job was removed. It POSTed
        # the same /v1/ingest/all-regulations sweep as fsma_nightly_sync
        # (below) on the same daily cadence, authenticated with
        # SCHEDULER_API_KEY — which shared.auth.require_api_key never
        # accepted, so it could only ever 401. fsma_nightly_sync is the
        # single surviving daily sync and now runs in-process.

        # State cleanup - daily
        self._add_tracked_job(
            self.cleanup_state,
            job_id="state_cleanup",
            trigger=IntervalTrigger(hours=24),
            next_run_time=self._near_boot_first_run(minutes=4),
            name="State Cleanup (90 days)",
        )

        # Deadline monitoring — check every 5 minutes for overdue/critical cases
        self._add_tracked_job(
            self.check_request_deadlines,
            job_id="deadline_monitor",
            trigger=IntervalTrigger(minutes=5),
            name="FDA Request Deadline Monitor",
            max_instances=1,
        )
        logger.info("job_scheduled", job_id="deadline_monitor", interval_minutes=5)

        # Identity mutation belongs to the audited admin control plane.  Until
        # that dedicated job exists, strict role-cutover deployments do not
        # schedule the legacy DATABASE_URL sweep.
        if _strict_database_role_cutover_enabled():
            logger.warning(
                "job_security_disabled",
                job_id="inactive_account_sweep",
                reason="requires audited ADMIN_DATABASE_URL control-plane worker",
            )
        else:
            self._add_tracked_job(
                self.disable_inactive_accounts,
                job_id="inactive_account_sweep",
                trigger=IntervalTrigger(hours=24),
                next_run_time=self._near_boot_first_run(minutes=6),
                name="Disable Inactive Accounts (90 days)",
            )
            logger.info("job_scheduled", job_id="inactive_account_sweep", interval_hours=24)

        # KDE retention enforcement — FSMA 204 24-month minimum (#973)
        self._add_tracked_job(
            self.enforce_kde_retention,
            job_id="kde_retention_enforcement",
            trigger=IntervalTrigger(hours=24),
            next_run_time=self._near_boot_first_run(minutes=8),
            name="KDE Retention Enforcement (24-month floor)",
        )
        logger.info("job_scheduled", job_id="kde_retention_enforcement", interval_hours=24)

        # Data archival/purge — retention policy enforcement (#983)
        self._add_tracked_job(
            self.archive_expired_records,
            job_id="data_archival",
            trigger=IntervalTrigger(hours=24),
            next_run_time=self._near_boot_first_run(minutes=10),
            name="Archive Expired Records",
        )
        logger.info("job_scheduled", job_id="data_archival", interval_hours=24)

        # Task queue retention — purge completed/dead rows (#1382)
        self._add_tracked_job(
            self.purge_old_tasks,
            job_id="task_queue_purge",
            trigger=IntervalTrigger(hours=24),
            next_run_time=self._near_boot_first_run(minutes=12),
            name="Task Queue Retention (30-day purge)",
        )
        logger.info("job_scheduled", job_id="task_queue_purge", interval_hours=24)

        # Nightly FSMA source sync — Phase 29 (#1135).
        # Previously defined in app/jobs.py on an orphaned BlockingScheduler
        # that was never started; the job has been running nowhere in
        # production. Re-home it on the real scheduler here.
        self._add_tracked_job(
            self.run_fsma_nightly_sync,
            job_id="fsma_nightly_sync",
            trigger=CronTrigger(hour=2, minute=0, timezone=utc),
            name="Nightly FSMA Source Sync (02:00 UTC)",
            misfire_grace_time=300,  # 5-minute grace window
        )
        logger.info("job_scheduled", job_id="fsma_nightly_sync", cron="02:00 UTC")

        # #2257 follow-up — replay the audit_log_buffer to the primary
        # KDE_READ audit-log backend on a schedule. Cadence is env-tunable
        # via AUDIT_BUFFER_RECONCILE_INTERVAL_SECONDS (default 300s).
        try:
            from services.graph.app.audit_buffer_reconciler import (  # noqa: PLC0415
                get_interval_seconds,
                run_reconcile_tick,
            )

            audit_buffer_interval = get_interval_seconds()
            self._add_tracked_job(
                run_reconcile_tick,
                job_id="audit_buffer_reconcile",
                trigger=IntervalTrigger(seconds=audit_buffer_interval),
                name="Audit Log Buffer Reconciliation (#2257 follow-up)",
                max_instances=1,  # Never run two reconciliation passes concurrently.
            )
            logger.info(
                "job_scheduled",
                job_id="audit_buffer_reconcile",
                interval_seconds=audit_buffer_interval,
            )
        except ImportError as exc:
            # Graph package not on path (e.g. minimal scheduler image): log
            # and continue. The buffer still grows safely; ops will notice
            # the missing replays via the unreplayed gauge.
            logger.warning(
                "audit_buffer_reconcile_unavailable",
                error=str(exc),
                hint="services.graph.app.audit_buffer_reconciler not importable",
            )

        # #2510 — loud-default footgun guard. If webhooks are enabled but no
        # durable outbox path is configured, failed HIGH/CRITICAL alert
        # deliveries live only in process memory and are lost on every Railway
        # restart/deploy (the container filesystem is ephemeral — no volume in
        # railway.toml). Warn at startup so enabling WEBHOOK_URLS without
        # WEBHOOK_OUTBOX_PATH is not silent.
        if self.settings.webhook_url_list and not self.settings.webhook_outbox_path:
            logger.warning(
                "webhook_dlq_persistence_disabled",
                webhook_count=len(self.settings.webhook_url_list),
                hint=(
                    "WEBHOOK_URLS is set but WEBHOOK_OUTBOX_PATH is empty: failed "
                    "webhook deliveries are in-memory only and will NOT survive a "
                    "restart. Set WEBHOOK_OUTBOX_PATH to a path on a persistent "
                    "volume for durable dead-letter retries."
                ),
            )

        # #1150 — drain the persistent webhook outbox periodically. Only
        # register the job when an outbox path is actually configured, so
        # a scheduler with legacy (in-memory-only) delivery doesn't pay
        # the cost of a no-op tick every minute.
        if self.settings.webhook_outbox_path:
            self._add_tracked_job(
                self.drain_webhook_outbox,
                job_id="webhook_outbox_drain",
                trigger=IntervalTrigger(
                    seconds=self.settings.webhook_outbox_drain_interval_seconds,
                ),
                name="Webhook Outbox Drain (#1150)",
                max_instances=1,  # Never run two drain passes concurrently.
            )
            logger.info(
                "job_scheduled",
                job_id="webhook_outbox_drain",
                interval_seconds=self.settings.webhook_outbox_drain_interval_seconds,
                outbox_path=self.settings.webhook_outbox_path,
            )

        # Remediation notification-outbox drain — emails supplier
        # correction links queued by services/ingestion/app/remediation/
        # outbox.py. Short cadence on purpose: the product promise is
        # link delivery within seconds of the buyer issuing it.
        self._add_tracked_job(
            self.drain_remediation_notifications,
            job_id="remediation_notification_drain",
            trigger=IntervalTrigger(
                seconds=self.settings.remediation_outbox_drain_interval_seconds,
            ),
            name="Remediation Notification Outbox Drain",
            max_instances=1,  # Never run two drain passes concurrently.
        )
        logger.info(
            "job_scheduled",
            job_id="remediation_notification_drain",
            interval_seconds=self.settings.remediation_outbox_drain_interval_seconds,
        )

        # WS-8 (#2709): replay dead-lettered rule evaluations into
        # fsma.rule_evaluations so the audit trail self-heals.
        self._add_tracked_job(
            self.replay_rule_eval_deadletter,
            job_id="rule_eval_deadletter_replay",
            trigger=IntervalTrigger(
                seconds=self.settings.rule_eval_deadletter_replay_interval_seconds,
            ),
            name="Rule Evaluation Dead-Letter Replay (#2709)",
            max_instances=1,  # Never run two replay passes concurrently.
        )
        logger.info(
            "job_scheduled",
            job_id="rule_eval_deadletter_replay",
            interval_seconds=self.settings.rule_eval_deadletter_replay_interval_seconds,
        )

        logger.info(
            "scheduler_ready",
            scrapers=list(self.scrapers.keys()),
        )

    def drain_remediation_notifications(self) -> None:
        """Drain the remediation notification outbox once.

        Per-tenant claim under RLS (fsma.notification_outbox is FORCE RLS
        with no sysadmin bypass); tenant discovery iterates public.tenants
        like the deadline monitor (#2461). Per-entry failures reschedule
        with backoff inside the drainer; a tenant-level failure is logged
        and skipped so one tenant cannot poison the tick.
        """
        try:
            from shared.database import SessionLocal  # noqa: PLC0415

            from services.ingestion.app.remediation.delivery import drain_all_tenants  # noqa: PLC0415

            db = SessionLocal()
            try:
                totals = drain_all_tenants(db)
            finally:
                db.close()
        except Exception as exc:
            # #2697: log, then RE-RAISE so APScheduler fires EVENT_JOB_ERROR
            # and the #1144 listener records the failure in
            # scheduler_job_runs — swallowing here recorded success.
            logger.exception("remediation_notification_drain_failed", error=str(exc))
            raise
        if totals["claimed"]:
            logger.info("remediation_notification_drain_tick", **totals)

    def replay_rule_eval_deadletter(self) -> None:
        """Replay dead-lettered rule evaluations once (WS-8, #2709).

        Per-tenant claim under RLS (fsma.rule_evaluation_deadletter is
        FORCE RLS); tenant discovery iterates public.tenants like the
        remediation drain. Per-row failures bump replay_attempts inside
        the replayer; a tenant-level failure is logged and skipped so one
        tenant cannot poison the tick.
        """
        try:
            from shared.database import SessionLocal  # noqa: PLC0415
            from shared.rules.deadletter_replay import replay_all_tenants  # noqa: PLC0415

            db = SessionLocal()
            try:
                totals = replay_all_tenants(db)
            finally:
                db.close()
        except Exception as exc:
            # #2697 convention: log, then RE-RAISE so the #1144 listener
            # records the failure instead of a phantom success.
            logger.exception("rule_eval_deadletter_replay_failed", error=str(exc))
            raise
        if totals["attempted"]:
            logger.info("rule_eval_deadletter_replay_tick", **totals)

    def drain_webhook_outbox(self) -> None:
        """Drain the persistent webhook outbox once (#1150).

        Invoked by APScheduler on the interval configured by
        ``webhook_outbox_drain_interval_seconds``. Tolerant of per-entry
        failures; counters are emitted via ``webhook_outbox_drain`` log.
        """
        try:
            counter = self.notifier.retry_outbox_once()
        except Exception as exc:  # pragma: no cover — telemetry must not crash
            logger.exception("webhook_outbox_drain_failed", error=str(exc))
            return
        if counter["attempted"]:
            logger.info("webhook_outbox_drain_tick", **counter)

    def purge_old_tasks(self) -> None:
        """Purge completed/dead ``fsma.task_queue`` rows older than 30 days.

        Closes #1382. Without this, completed and dead rows accumulate
        forever: index bloat on ``idx_task_queue_tenant``, slower ad-hoc
        observability queries, and ever-growing storage cost on Railway
        Postgres.
        """
        try:
            from sqlalchemy import text as _sqltext

            from services.admin.app.database import (
                SessionLocal,
                arm_global_admin_context,
            )

            db = SessionLocal()
            try:
                # Cross-tenant retention is an audited control-plane action
                # and runs through ADMIN_DATABASE_URL.  The database policy
                # pins it to the exact sysadmin role.
                arm_global_admin_context(db)
                result = db.execute(
                    _sqltext(
                        """
                        DELETE FROM fsma.task_queue
                        WHERE status IN ('completed', 'dead')
                          AND task_type = ANY(:purgeable_task_types)
                          AND NOT (task_type = ANY(:protected_task_types))
                          AND COALESCE(completed_at, created_at)
                              < NOW() - INTERVAL '30 days'
                        RETURNING id, task_type
                        """
                    ),
                    {
                        "purgeable_task_types": sorted(PURGEABLE_TASK_TYPES),
                        "protected_task_types": sorted(NON_WORKER_TASK_TYPES),
                    },
                )
                rows = result.fetchall()
                db.commit()
                if rows:
                    by_type = {}
                    for row in rows:
                        kind = row[1] if len(row) > 1 else "unknown"
                        by_type[kind] = by_type.get(kind, 0) + 1
                    logger.info("task_queue_purged", rows=len(rows), by_task_type=by_type)
                else:
                    logger.debug("task_queue_purge_noop")
            finally:
                db.close()
        except (ImportError, RuntimeError, ConnectionError, ValueError) as e:
            logger.error("task_queue_purge_failed", error=str(e))

    def run_fsma_nightly_sync(self) -> None:
        """Run a full FSMA source sync in-process.

        Phase 29 / #1135. Formerly POSTed to
        ``{INGESTION_SERVICE_URL}/v1/ingest/all-regulations`` with
        ``REGENGINE_INTERNAL_SECRET`` as ``X-RegEngine-API-Key`` — but
        ``shared.auth.require_api_key`` never accepted that secret (it
        validates database-backed tenant keys only), so the
        job could not authenticate against the consolidated monolith.
        Scheduler and ingestion now share a process, so call the ingestion
        sweep directly: no HTTP hop, no credentials, and no 120s
        RequestTimeoutMiddleware ceiling on long scrapes. The ingestion
        pipeline dedupes via ETag + SHA-256, so re-running on unchanged
        sources is safe.
        """
        import asyncio

        try:
            from services.ingestion.app.routes_scraping import run_all_regulations_ingest
        except ImportError as exc:
            logger.error("fsma_nightly_sync_unavailable", error=str(exc))
            return

        logger.info("fsma_nightly_sync_started", mode="in_process")
        try:
            summary = asyncio.run(run_all_regulations_ingest())
            attempted = summary.get("sources_attempted") or 0
            failed = summary.get("failed") or 0
            log_fields = {
                "sources_attempted": attempted,
                "ingested": summary.get("ingested"),
                "unchanged": summary.get("unchanged"),
                "failed": failed,
            }
            # #2505: a sync where every source failed (e.g. Redis
            # unreachable for the ETag/content-hash dedup layer) used to log
            # at info and pass silently, so regulatory source data could
            # stop refreshing without any alert. Escalate the all-failed
            # case to error so it pages instead of being lost in info noise.
            if attempted > 0 and failed == attempted:
                logger.error("fsma_nightly_sync_all_failed", **log_fields)
            else:
                logger.info("fsma_nightly_sync_complete", **log_fields)
        except Exception as exc:
            # #2697: log, then RE-RAISE so APScheduler fires EVENT_JOB_ERROR
            # and the #1144 listener records the failure — returning
            # normally recorded EVENT_JOB_EXECUTED (success) in
            # scheduler_job_runs while the sync had crashed.
            logger.error("fsma_nightly_sync_failed", error=str(exc))
            raise

    def check_request_deadlines(self) -> None:
        """Check all tenants for overdue/critical FDA request deadlines.

        Queries all active request cases and logs warnings for any that are
        overdue or approaching their deadline (<2 hours). Designed to run
        every 5 minutes via APScheduler.
        """
        with _tracer.start_as_current_span("scheduler.check_request_deadlines"):
            self._check_request_deadlines_inner()

    def _deadline_alert_due(self, tenant_id, urgency, case_id):
        now = time.monotonic()
        key = (urgency, case_id)
        bucket = self._deadline_alert_state.get(tenant_id, {})
        previous = bucket.get(key)
        if previous is not None and now - previous < self.DEADLINE_RENOTIFY_SECONDS:
            return False, False
        # Untracked overflow is reported rather than silently suppressing a
        # breach. The cache never grows beyond the configured process bound.
        if previous is not None or self._deadline_alert_entries < self.DEADLINE_ALERT_STATE_MAX:
            if previous is None:
                self._deadline_alert_entries += 1
            self._deadline_alert_state.setdefault(tenant_id, {})[key] = now
        return True, previous is not None

    def _check_request_deadlines_inner(self) -> None:
        try:
            from shared.database import SessionLocal
            from shared.request_workflow import RequestWorkflow

            db = SessionLocal()
            try:
                workflow = RequestWorkflow(db)

                # #2461: tenant discovery must NOT scan the RLS-forced
                # fsma.request_cases cross-tenant (that query raises
                # 'app.tenant_id not set' under the least-privilege role
                # before any per-tenant GUC is set, killing the whole
                # tick). Iterate public.tenants instead (infra table,
                # permissive policy per v092) and let per-tenant
                # check_deadline_status find the active cases.
                from shared.maintenance_tenants import list_maintenance_tenant_ids  # noqa: PLC0415

                tenant_ids = list_maintenance_tenant_ids(limit=self.DEADLINE_TENANT_SCAN_LIMIT)
                if len(tenant_ids) >= self.DEADLINE_TENANT_SCAN_LIMIT:
                    logger.error("deadline_monitor_tenant_scan_truncated", limit=self.DEADLINE_TENANT_SCAN_LIMIT)

                total_overdue = 0
                total_critical = 0

                for tid in tenant_ids:
                    # Set tenant context for RLS before per-tenant queries.
                    # tenant_scope drives the #2461 begin-hook (covers every
                    # transaction, incl. after commit/rollback); the explicit
                    # set_tenant_guc stays as the idempotent legacy layer.
                    from shared.tenant_context import set_tenant_guc, tenant_scope  # noqa: PLC0415

                    with tenant_scope(tid):
                        set_tenant_guc(db, tid)
                        cases = workflow.check_deadline_status(tid)
                    overdue = [c for c in cases if c["urgency"] == "overdue"]
                    critical = [c for c in cases if c["urgency"] == "critical"]
                    total_overdue += len(overdue)
                    total_critical += len(critical)

                    active = {(c["urgency"], c["request_case_id"]) for c in overdue + critical}
                    bucket = self._deadline_alert_state.get(tid, {})
                    for key in list(bucket):
                        if key not in active:
                            del bucket[key]
                            self._deadline_alert_entries -= 1
                    if not bucket:
                        self._deadline_alert_state.pop(tid, None)

                    for case in overdue:
                        emit, renotify = self._deadline_alert_due(tid, "overdue", case["request_case_id"])
                        if not emit:
                            logger.debug("deadline_overdue_repeat", tenant_id=tid, case_id=case["request_case_id"])
                            continue
                        logger.error(
                            "deadline_overdue",
                            tenant_id=tid,
                            case_id=case["request_case_id"],
                            renotify=renotify,
                            hours_overdue=abs(case["hours_remaining"]),
                            status=case["package_status"],
                            requesting_party=case["requesting_party"],
                        )

                    for case in critical:
                        emit, renotify = self._deadline_alert_due(tid, "critical", case["request_case_id"])
                        if not emit:
                            logger.debug("deadline_critical_repeat", tenant_id=tid, case_id=case["request_case_id"])
                            continue
                        logger.warning(
                            "deadline_critical",
                            tenant_id=tid,
                            case_id=case["request_case_id"],
                            renotify=renotify,
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
        if _strict_database_role_cutover_enabled():
            logger.warning(
                "inactive_account_sweep_security_disabled",
                reason="identity mutation is not authorized through DATABASE_URL",
            )
            return
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
            from services.admin.app.database import (
                SessionLocal,
                arm_global_admin_context,
            )

            db = SessionLocal()
            try:
                # Deliberately global retention guard through the canonical
                # admin credential; the ordinary role remains tenant-bound.
                arm_global_admin_context(db)
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

        NOTE: this job used to open with ``DELETE FROM fsma.fda_exports``,
        but no migration ever created that table (added speculatively in
        #1017) — the raw SQL is invisible to the ORM drift gate, so the
        job failed with UndefinedTable on EVERY prod run and none of the
        archival below ever executed. FDA exports are generated on demand
        and streamed to the caller, never persisted server-side (object
        storage is absent — see DEMO_UNBLOCK_PRD_2026-07-24). The only
        persisted export artifact is ``fsma.fda_export_log``, which is
        audit metadata used by chain verification and must NOT be purged
        on a 1-year clock. If export payload persistence ever lands,
        re-add its retention here alongside a migration that creates the
        table.
        """
        try:
            from shared.database import SessionLocal
            from shared.tenant_context import tenant_scope  # noqa: PLC0415

            db = SessionLocal()
            try:
                # Sysadmin audit evidence is intentionally not mutable through
                # DATABASE_URL.  Retention requires a separately approved,
                # audited admin maintenance path; until then retain it.
                deleted_audit = 0
                logger.debug(
                    "sysadmin_audit_retention_deferred",
                    reason="requires audited ADMIN_DATABASE_URL maintenance",
                )

                # Archive CTE events older than 3 years. #2461:
                # fsma.cte_events is RLS-forced tenant DATA — it gets NO
                # system arm, so the sweep iterates tenants and deletes
                # under each tenant's own GUC (tenant_scope + begin-hook).
                # Under today's BYPASSRLS role the first iteration deletes
                # everything and the rest are no-ops; under the
                # least-privilege role each pass is tenant-scoped.
                # Ages on ingested_at (record creation, NOT NULL DEFAULT
                # NOW()) — cte_events has never had a created_at column;
                # the original filter was UndefinedColumn, masked by the
                # fda_exports failure above it. event_timestamp is wrong
                # here: it would purge late-ingested old events before
                # their FSMA retention clock ran.
                #
                # cte_events carries the v078 append-only trigger
                # (prevent_cte_mutation, FDA 21 CFR 1.1455), so each
                # per-tenant transaction sets the documented
                # fsma.allow_mutation break-glass GUC transaction-locally
                # (set_config is_local=true — clears at COMMIT). Retention
                # purge past the 1095-day policy is an authorized
                # mutation; the 24-month FSMA floor is guarded separately
                # by enforce_kde_retention. Deletes cascade to cte_kdes
                # and compliance_alerts (ON DELETE CASCADE, no append-only
                # triggers there).
                deleted_ctes = 0
                from shared.maintenance_tenants import list_maintenance_tenant_ids  # noqa: PLC0415

                tenant_ids = list_maintenance_tenant_ids()
                for tenant_id in tenant_ids:
                    with tenant_scope(tenant_id):
                        db.execute(
                            __import__("sqlalchemy").text("SELECT set_config('fsma.allow_mutation', 'true', true)")
                        )
                        result = db.execute(
                            __import__("sqlalchemy").text("""
                                DELETE FROM fsma.cte_events
                                WHERE ingested_at < NOW() - INTERVAL '1095 days'
                                RETURNING id
                            """)
                        )
                        deleted_ctes += len(result.fetchall())
                        db.commit()

                if deleted_ctes > 0 or deleted_audit > 0:
                    logger.info(
                        "data_archival_complete",
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
            # #1142 — register a leadership-lost handler. When the heartbeat
            # thread detects the advisory lock has been released server-side
            # (network partition, DB failover, proxy reset), this callback
            # gracefully shuts the BlockingScheduler so control returns to
            # the main thread and the orchestrator can restart us. Without
            # this hook, a zombie leader keeps running scrapers after a
            # standby has already taken over — duplicate emissions.
            self.distributed_context.wait_for_leadership(
                self._run_scheduler_workload,
                on_leadership_lost=self._on_leadership_lost,
            )
        except (KeyboardInterrupt, SystemExit):
            logger.info("scheduler_shutdown_signal_received")
            self.shutdown()

    def _on_leadership_lost(self) -> None:
        """Heartbeat-thread shutdown hook (#1142).

        Called from the leader-heartbeat thread when we've lost the
        advisory lock. MUST be safe to call from a non-main thread — all
        it does is request the BlockingScheduler to shut down so the
        main thread's ``scheduler.start()`` returns. The process then
        exits with a non-zero status (handled by the orchestrator, which
        restarts us).
        """
        logger.error(
            "leadership_lost_initiating_shutdown",
            note="heartbeat detected lost advisory lock; asking scheduler to shut down",
        )
        try:
            if getattr(self, "scheduler", None) is not None:
                # wait=False: don't block the heartbeat thread on in-flight
                # jobs; the BlockingScheduler's start() will return as soon
                # as the event loop notices the shutdown flag.
                self.scheduler.shutdown(wait=False)
        except Exception as exc:  # noqa: BLE001
            logger.error("leadership_lost_shutdown_failed", error=str(exc))

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
                        scheduled_run_time=str(getattr(event, "scheduled_run_time", "unknown")),
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

        # #1150 — release webhook HTTP session cleanly so open sockets
        # don't block the process exit.
        try:
            self.notifier.close()
        except (RuntimeError, OSError) as e:
            logger.warning("webhook_notifier_close_failed", error=str(e))

        logger.info("scheduler_stopped")
