"""RegEngine Scheduler Service — standalone local-debug entrypoint.

Hosts :class:`services.scheduler.service.SchedulerService` behind a stdlib
HTTP health/metrics server with graceful SIGTERM handling. Production does
NOT run this entrypoint: the consolidated monolith (``server.main:app``)
starts the same SchedulerService in-process via
``server/workers/embedded_scheduler.py``, with single-leader execution
enforced by the PostgreSQL advisory lock in
``services/scheduler/app/distributed.py``.
"""

from __future__ import annotations

import os

# --- Standardized Bootstrap ---
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

import structlog

_SERVICE_DIR = Path(__file__).resolve().parent
_SERVICES_DIR = _SERVICE_DIR.parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

from shared.paths import ensure_shared_importable

ensure_shared_importable()
# ------------------------------

from shared.env_validation import (
    assert_legacy_entrypoint_not_in_production,
    require_env,
)

# Production deploys must use server.main:app (the consolidated monolith,
# per the repo-root Dockerfile), which embeds the scheduler via
# server/workers/embedded_scheduler.py. This file is a local-debug
# entrypoint only — see docs/architecture/CONSOLIDATION.md.
assert_legacy_entrypoint_not_in_production("scheduler")

require_env("DATABASE_URL", "REDIS_URL")

# Sentry error tracking (must be before service initialization)
from shared.error_handling import init_sentry

init_sentry()

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

from services.scheduler.app.circuit_breaker import circuit_registry
from services.scheduler.app.config import get_settings
from services.scheduler.app.metrics import metrics
from services.scheduler.service import SchedulerService


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
        """Return detailed status.

        RE-SCH-003: this endpoint exposes circuit-breaker state and per-source
        scrape error messages — useful debugging context that should not be
        public. Gate behind ``X-Metrics-Key`` (same secret used by ``/metrics``
        and by the sibling FastAPI ``/status`` route at
        ``services/scheduler/api.py``). The basic ``/health`` endpoint stays
        unauthenticated so the k8s liveness probe (see
        ``infra/k8s/base/scheduler/deployment.yaml``) keeps working.
        """
        import json

        expected = os.environ.get("METRICS_API_KEY", "")
        provided = self.headers.get("X-Metrics-Key", "")
        if not expected or provided != expected:
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"detail":"Forbidden"}')
            return

        status = {
            "service": "scheduler",
            "status": "running",
            "circuit_breakers": circuit_registry.get_all_status(),
            "last_scrapes": {
                st.value: {
                    "success": r.success,
                    "count": r.items_found,
                    "scraped_at": r.scraped_at.isoformat(),
                    "error": r.error_message if not r.success else None,
                    # #1140: surface soft-failure warnings (e.g.
                    # parser_mismatch_suspected) to ops dashboards even
                    # when success=True.
                    "warnings": list(getattr(r, "warnings", []) or []),
                }
                for st, r in self.scheduler_service.last_results.items()
            }
            if self.scheduler_service
            else {},
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
