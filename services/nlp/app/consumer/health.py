"""Shutdown signalling and the HTTP liveness probe for the NLP consumer.

Split out of the original ``app/consumer.py`` module. All names are
re-exported from ``app.consumer`` for backward compatibility.
"""

from __future__ import annotations

import http.server
import json
import os
import socket
import threading
import time
from typing import Any, Optional

import structlog

logger = structlog.get_logger("nlp-consumer")

_shutdown_event = threading.Event()


def stop_consumer() -> None:
    _shutdown_event.set()


# ---------------------------------------------------------------------------
# Issue #2979 — consumer-loop liveness state
# ---------------------------------------------------------------------------
#
# The probe used to answer purely from ``_shutdown_event``: a consumer whose
# loop thread had died still returned 200 {"status":"ok"}, so no orchestrator
# could tell that message processing had stopped. The loop now reports its own
# state here and the probe answers from it.
#
# A loop that cannot poll is NOT healthy, even though the process is alive.

# How long a loop may go without a successful poll before it is stale. The
# loop polls with a 500ms timeout, so anything beyond a few seconds means it
# is wedged; the default leaves room for slow per-record processing.
_POLL_STALE_SECONDS = float(os.getenv("NLP_POLL_STALE_SECONDS", "120"))
# Consecutive failed polls after which the consumer reports unhealthy while
# still retrying (it keeps trying; the orchestrator decides what to do).
_POLL_ERROR_UNHEALTHY_THRESHOLD = int(os.getenv("NLP_POLL_ERROR_UNHEALTHY_THRESHOLD", "3"))

_state_lock = threading.Lock()
_state: dict[str, Any] = {
    "loop_started": False,
    "loop_running": False,
    "fatal_error": None,
    "last_poll_monotonic": None,
    "consecutive_poll_errors": 0,
    "last_poll_error": None,
    "topic_creation_failures": [],
}


def reset_consumer_health() -> None:
    """Clear the recorded loop state (process restart / test isolation)."""
    with _state_lock:
        _state.update(
            loop_started=False,
            loop_running=False,
            fatal_error=None,
            last_poll_monotonic=None,
            consecutive_poll_errors=0,
            last_poll_error=None,
            topic_creation_failures=[],
        )


def mark_loop_started() -> None:
    with _state_lock:
        _state["loop_started"] = True
        _state["loop_running"] = True
        _state["fatal_error"] = None


def mark_loop_stopped(error: Optional[BaseException] = None) -> None:
    """Record that the loop is no longer running, fatally or cleanly."""
    with _state_lock:
        _state["loop_running"] = False
        if error is not None:
            _state["fatal_error"] = f"{type(error).__name__}: {error}"


def record_poll_success() -> None:
    with _state_lock:
        _state["last_poll_monotonic"] = time.monotonic()
        _state["consecutive_poll_errors"] = 0
        _state["last_poll_error"] = None


def record_poll_error(error: str) -> int:
    """Record a failed poll; returns the consecutive-error count."""
    with _state_lock:
        _state["consecutive_poll_errors"] += 1
        _state["last_poll_error"] = error
        return _state["consecutive_poll_errors"]


def record_topic_creation_failure(topic: str) -> None:
    """#2979 — a swallowed topic-creation failure surfaces later as the poll
    error that used to kill the loop. Make it visible on the probe."""
    with _state_lock:
        if topic not in _state["topic_creation_failures"]:
            _state["topic_creation_failures"].append(topic)


def consumer_health() -> tuple[int, dict[str, Any]]:
    """Return ``(http_status, body)`` describing the consumer loop.

    200 only when the loop is running and polling; 503 when it is shutting
    down, dead, wedged, or unable to poll.
    """
    with _state_lock:
        state = dict(_state)
        state["topic_creation_failures"] = list(_state["topic_creation_failures"])

    body: dict[str, Any] = {
        "status": "ok",
        "topic_creation_failures": state["topic_creation_failures"],
    }
    if state["last_poll_error"]:
        body["last_poll_error"] = state["last_poll_error"]
        body["consecutive_poll_errors"] = state["consecutive_poll_errors"]

    if _shutdown_event.is_set():
        body["status"] = "stopping"
        return 503, body

    if state["fatal_error"] is not None:
        body["status"] = "consumer_dead"
        body["error"] = state["fatal_error"]
        return 503, body

    if not state["loop_started"]:
        # The probe is started before the first Kafka poll on purpose so
        # startup probes succeed (#1231).
        body["status"] = "starting"
        return 200, body

    if not state["loop_running"]:
        body["status"] = "consumer_dead"
        return 503, body

    if state["consecutive_poll_errors"] >= _POLL_ERROR_UNHEALTHY_THRESHOLD:
        body["status"] = "poll_failing"
        return 503, body

    last_poll = state["last_poll_monotonic"]
    if last_poll is not None:
        age = time.monotonic() - last_poll
        body["seconds_since_last_poll"] = round(age, 3)
        if age > _POLL_STALE_SECONDS:
            body["status"] = "poll_stale"
            return 503, body

    return 200, body


# ---------------------------------------------------------------------------
# Issue #1231 — HTTP health endpoint for the Kafka consumer
# ---------------------------------------------------------------------------
#
# Orchestrators (Railway, Kubernetes, ECS) need a way to determine whether
# the consumer process is alive. Without this, the only liveness signal is
# "process still running", which misses stuck consumers that have stopped
# polling. A background thread exposes GET /health on port 8099; it returns
# 200 only while the consumer loop is actually running and polling (#2979) —
# see consumer_health() above for the exact states.
#
# Uses only Python stdlib (http.server) — no new dependencies.
# ---------------------------------------------------------------------------


_HEALTH_PORT = int(os.getenv("NLP_HEALTH_PORT", "8099"))


class _HealthHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP handler for the consumer liveness probe."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/health", "/healthz"):
            # #2979 — answer from the loop's recorded state, not just the
            # shutdown flag: a dead or wedged loop must not report healthy.
            status_code, payload = consumer_health()
            self.send_response(status_code)
            body = json.dumps(payload).encode("utf-8")
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
