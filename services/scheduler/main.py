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
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
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

from app.config import get_settings
from app.circuit_breaker import CircuitBreaker, CircuitOpenError, circuit_registry
from app.kafka_producer import get_kafka_producer
from app.metrics import metrics
from app.models import EnforcementItem, EnforcementSeverity, ScrapeResult, SourceType
from app.notifications import WebhookNotifier
from app.scrapers import (
    BaseScraper,
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
        except Exception as e:
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

                # Mark as seen
                self.state_manager.mark_seen(
                    source_id=item.source_id,
                    source_type=source_type.value,
                    content=content,
                    title=item.title,
                    url=item.url,
                )

        return new_items

    def _process_new_items(
        self, items: List[EnforcementItem], source_type: SourceType
    ) -> None:
        """Process newly detected enforcement items.

        Args:
            items: List of new enforcement items
            source_type: Source type
        """
        logger.info(
            "processing_new_items",
            source_type=source_type.value,
            count=len(items),
        )

        # Emit to Kafka (enforcement events)
        try:
            success, failures = self.kafka_producer.emit_batch(items)
            logger.info(
                "kafka_events_emitted",
                success=success,
                failures=failures,
            )
        except Exception as e:
            logger.error("kafka_emission_failed", error=str(e))

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
        except Exception as e:
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
        except Exception as e:
            logger.error("webhook_notification_failed", error=str(e))

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

        logger.info(
            "scheduler_ready",
            total_jobs=3,
            scrapers=list(self.scrapers.keys()),
        )

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

    def shutdown(self) -> None:
        """Gracefully shutdown the scheduler."""
        logger.info("scheduler_shutting_down")

        try:
            self.kafka_producer.close()
        except Exception as e:
            logger.error("kafka_close_failed", error=str(e))

        logger.info("scheduler_stopped")


class HealthHandler(BaseHTTPRequestHandler):
    """HTTP handler for health checks and metrics."""

    scheduler_service: Optional[SchedulerService] = None

    def do_GET(self) -> None:
        if self.path == "/health":
            self._handle_health()
        elif self.path == "/ready":
            self._handle_ready()
        elif self.path == "/metrics":
            self._handle_metrics()
        elif self.path == "/status":
            self._handle_status()
        else:
            self.send_response(404)
            self.end_headers()

    def _get_health_check_result(self) -> dict:
        import asyncio
        from shared.health import HealthCheck
        hc = HealthCheck("scheduler")
        # Add basic dependencies if applicable
        return asyncio.run(hc.check())

    def _handle_health(self) -> None:
        """Return health status."""
        import json
        res = self._get_health_check_result()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(res).encode())

    def _handle_ready(self) -> None:
        """Return readiness status."""
        import json
        res = self._get_health_check_result()
        if res.get("status") == "healthy":
            self.send_response(200)
        else:
            self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(res).encode())

    def _handle_metrics(self) -> None:
        """Return Prometheus metrics."""
        content = metrics.get_metrics()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(content)

    def _handle_status(self) -> None:
        """Return detailed status."""
        import json

        svc = self.scheduler_service
        last_scrapes = {}
        if svc is not None and hasattr(svc, "last_results"):
            last_scrapes = {
                st.value: {
                    "success": r.success,
                    "count": r.items_found,
                    "scraped_at": r.scraped_at.isoformat(),
                    "error": r.error_message if not r.success else None
                }
                for st, r in svc.last_results.items()
            }

        status = {
            "service": "scheduler",
            "status": "running",
            "circuit_breakers": circuit_registry.get_all_status(),
            "last_scrapes": last_scrapes
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
    except Exception as e:
        logger.error("health_server_failed", error=str(e))


def main() -> None:
    """Main entry point."""
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
