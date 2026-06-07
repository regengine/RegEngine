"""Shutdown signalling and the HTTP liveness probe for the NLP consumer.

Split out of the original ``app/consumer.py`` module. All names are
re-exported from ``app.consumer`` for backward compatibility.
"""

from __future__ import annotations

import http.server
import os
import socket
import threading

import structlog

logger = structlog.get_logger("nlp-consumer")

_shutdown_event = threading.Event()


def stop_consumer() -> None:
    _shutdown_event.set()


# ---------------------------------------------------------------------------
# Issue #1231 — HTTP health endpoint for the Kafka consumer
# ---------------------------------------------------------------------------
#
# Orchestrators (Railway, Kubernetes, ECS) need a way to determine whether
# the consumer process is alive. Without this, the only liveness signal is
# "process still running", which misses stuck consumers that have stopped
# polling. A background thread exposes GET /health on port 8099; it returns
# 200 {"status":"ok"} as long as _shutdown_event is not set.
#
# Uses only Python stdlib (http.server) — no new dependencies.
# ---------------------------------------------------------------------------


_HEALTH_PORT = int(os.getenv("NLP_HEALTH_PORT", "8099"))


class _HealthHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP handler for the consumer liveness probe."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/health", "/healthz"):
            if _shutdown_event.is_set():
                self.send_response(503)
                body = b'{"status":"stopping"}'
            else:
                self.send_response(200)
                body = b'{"status":"ok"}'
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: N802
        # Suppress noisy access logs; structlog handles observability.
        pass


def _start_health_server() -> None:
    """Start a background thread serving the health endpoint on _HEALTH_PORT.

    The server uses SO_REUSEADDR so a fast restart doesn't hit EADDRINUSE.
    Binds to 0.0.0.0 so container health-check probes from the host can
    reach it without loopback-only restrictions.

    Called once from run_consumer() before the Kafka consumer loop starts so
    the probe is available from process startup (before the first Kafka poll).
    """
    try:
        server = http.server.HTTPServer(("0.0.0.0", _HEALTH_PORT), _HealthHandler)
        server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except OSError as exc:
        logger.warning(
            "health_server_bind_failed",
            port=_HEALTH_PORT,
            error=str(exc),
        )
        return

    thread = threading.Thread(
        target=server.serve_forever,
        name="nlp-health-server",
        daemon=True,  # exits when the main process exits
    )
    thread.start()
    logger.info("health_server_started", port=_HEALTH_PORT, path="/health")
