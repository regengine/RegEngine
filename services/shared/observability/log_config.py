"""Shared structured JSON logging configuration for all RegEngine services (#556).

Every service calls configure_logging(service_name, log_level) early in main.py.
This replaces ad-hoc per-service logging setups with a single canonical config.

Output format (JSON, one line per record):
  {
    "timestamp": "2026-04-04T12:00:00.000Z",   # ISO-8601 UTC
    "level":     "info",
    "service":   "ingestion-service",
    "message":   "...",
    "request_id": "...",                         # set by RequestIDMiddleware
    "tenant_id":  "...",                         # set by TenantContextMiddleware
    ...extra structlog bind() fields...
  }

Development mode (REGENGINE_ENV=development):
  Uses structlog ConsoleRenderer for human-readable output instead of JSON.
"""

from __future__ import annotations

import logging
import os
import sys

import structlog
from contextvars import ContextVar

# ---------------------------------------------------------------------------
# Per-request context variables
# Set by RequestIDMiddleware / TenantContextMiddleware on every request so
# that all log records automatically carry request_id and tenant_id.
# ---------------------------------------------------------------------------
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
_tenant_id_ctx: ContextVar[str] = ContextVar("tenant_id", default="")


def set_request_context(*, request_id: str = "", tenant_id: str = "") -> None:
    """Set per-request logging context (called by middleware)."""
    if request_id:
        _request_id_ctx.set(request_id)
    if tenant_id:
        _tenant_id_ctx.set(tenant_id)


def _inject_context(logger: object, method: str, event_dict: dict) -> dict:
    """Structlog processor: inject service context into every log record."""
    # service name is set once at configure_logging() time via os.environ
    event_dict.setdefault("service", os.getenv("SERVICE_NAME", "regengine"))
    rid = _request_id_ctx.get("")
    if rid:
        event_dict.setdefault("request_id", rid)
    tid = _tenant_id_ctx.get("")
    if tid:
        event_dict.setdefault("tenant_id", tid)
    return event_dict


def configure_logging(service_name: str, log_level: str = "INFO") -> None:
    """Configure structlog for a RegEngine service.

    Args:
        service_name: Human-readable service identifier included in every log
                      record (e.g. "admin-service", "ingestion-service").
        log_level:    Standard log-level string. Falls back to INFO on invalid
                      values. Can also be overridden at runtime via LOG_LEVEL env.

    Side effects:
        - Sets SERVICE_NAME env var so _inject_context can read it
        - Configures both structlog and stdlib logging
        - Writes to stdout only
    """
    # Allow runtime override via env var
    resolved_level_str = os.getenv("LOG_LEVEL", log_level).upper()
    numeric_level = getattr(logging, resolved_level_str, logging.INFO)

    # Publish service name for _inject_context processor
    os.environ.setdefault("SERVICE_NAME", service_name)

    is_dev = os.getenv("REGENGINE_ENV", "").lower() == "development"

    shared_processors: list = [
        # Merge structlog contextvars (bind() fields) into the event dict
        structlog.contextvars.merge_contextvars,
        # Add stdlib log level name
        structlog.processors.add_log_level,
        # ISO-8601 UTC timestamp
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        # Inject service / request_id / tenant_id
        _inject_context,
        # Format exceptions into the event dict
        structlog.processors.format_exc_info,
    ]

    if is_dev:
        # Human-readable for local development
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # Machine-readable JSON for production / staging
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Mirror config to stdlib so third-party libraries (uvicorn, sqlalchemy, etc.)
    # honour the same level and write to stdout.
    logging.basicConfig(
        format="%(message)s",
        level=numeric_level,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    structlog.get_logger(service_name).info(
        "logging_configured",
        service=service_name,
        level=resolved_level_str,
        renderer="console" if is_dev else "json",
    )
