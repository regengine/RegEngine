import structlog
import logging
import sys
import os
from contextvars import ContextVar
from opentelemetry import trace

# ---------------------------------------------------------------------------
# Context variables for multi-tenant isolation audit fields.
# Middleware (TenantContextMiddleware / RequestIDMiddleware) should set these
# per-request so every log line carries tenant_id and request_id.
# ---------------------------------------------------------------------------
_tenant_id_ctx: ContextVar[str] = ContextVar("tenant_id", default="unknown")
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="unknown")


def set_tenant_context(tenant_id: str, request_id: str) -> None:
    """Set per-request tenant and request identifiers for structured logging."""
    _tenant_id_ctx.set(tenant_id)
    _request_id_ctx.set(request_id)


def _inject_service_context(logger_instance, method_name, event_dict):
    """Inject service name, tenant_id, and request_id into every log record.

    These fields are required for multi-tenant isolation audit compliance.
    """
    event_dict.setdefault("service", os.getenv("SERVICE_NAME", "regengine"))
    event_dict.setdefault("tenant_id", _tenant_id_ctx.get("unknown"))
    event_dict.setdefault("request_id", _request_id_ctx.get("unknown"))
    return event_dict


# Configure base structlog processors with JSON output and audit fields
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        _inject_service_context,
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger("regengine")

# Safely import OTel logging components
try:
    from opentelemetry.sdk._logs import LoggingHandler
    from opentelemetry import _logs as logs
    OTEL_LOGGING_AVAILABLE = True
except ImportError:
    OTEL_LOGGING_AVAILABLE = False

def setup_logging():
    """Setup basic logging configuration and return the global logger."""
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)

    # 1. Stdout listener
    handlers = [logging.StreamHandler(sys.stdout)]

    # 2. OTel Bridge (only when explicitly opted-in via ENABLE_OTEL=true)
    enable_otel = os.getenv("ENABLE_OTEL", "false").lower() == "true"
    if OTEL_LOGGING_AVAILABLE and enable_otel:
        handlers.append(LoggingHandler(logger_provider=logs.get_logger_provider()))

    logging.basicConfig(
        format="%(message)s",
        level=level,
        handlers=handlers
    )
    return logger

def get_logger(name: str):
    """Compatibility alias for setup_logging().get_logger()"""
    return structlog.get_logger(name)

# OTel context + sampling flag injection
def otel_context_processor(logger, method_name, event_dict):
    current_span = trace.get_current_span()
    if current_span is not None and current_span.get_span_context().is_valid:
        ctx = current_span.get_span_context()
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
        event_dict["trace_sampled"] = bool(ctx.trace_flags.sampled)
    else:
        event_dict["trace_sampled"] = False
    return event_dict

# Sampling-aware filter (drops INFO/DEBUG for sampled-out traces when disabled)
def sampling_aware_filter(logger, method_name, event_dict):
    if os.getenv("LOG_ALL_SAMPLED_OUT", "true").lower() == "false":
        if event_dict.get("trace_sampled") is False and method_name not in ("error", "critical", "warning"):
            raise structlog.DropEvent
    return event_dict

# Inject finalized processors into the configuration
structlog.configure(
    processors=[otel_context_processor, sampling_aware_filter] + structlog.get_config()["processors"]
)
