from __future__ import annotations

import asyncio
import contextvars
import functools
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from typing import Any, Callable, Coroutine, Optional, TypeVar

import structlog
from opentelemetry import trace

_F = TypeVar("_F", bound=Callable[..., Any])

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


# ---------------------------------------------------------------------------
# Context propagation helpers for background tasks and APScheduler jobs.
#
# Python's contextvars are NOT automatically inherited by threads or
# asyncio tasks created after the current frame — each gets a snapshot of
# the context at the time it was started, not a live view. APScheduler's
# ThreadPoolExecutor spawns a new OS thread per job, so context is lost.
#
# The two primitives below capture the live context at *enqueue* time and
# re-seed it inside the worker so every log line emitted by a background
# job carries the same correlation_id / tenant_id as the HTTP request that
# triggered it.
# ---------------------------------------------------------------------------

def _capture_observability_context() -> dict:
    """Snapshot the current correlation_id and tenant context.

    Returns a plain dict so it can be pickled / serialised if needed.
    The dict is also passed as ``**kwargs`` to
    :func:`_restore_observability_context`.
    """
    # Import lazily to avoid circular imports at module load.
    from shared.observability.correlation import correlation_id_ctx, generate_correlation_id

    cid = correlation_id_ctx.get()
    if cid is None:
        cid = generate_correlation_id()

    return {
        "correlation_id": cid,
        "tenant_id": _tenant_id_ctx.get("unknown"),
        "request_id": _request_id_ctx.get("unknown"),
    }


def _restore_observability_context(
    *,
    correlation_id: str,
    tenant_id: str,
    request_id: str,
) -> None:
    """Re-seed correlation / tenant context inside a worker thread or task.

    Binds both the raw ContextVars (so that :func:`get_correlation_id` /
    :func:`_inject_service_context` work) and the structlog contextvars (so
    that processors configured with
    ``structlog.contextvars.merge_contextvars`` pick them up automatically).
    """
    from shared.observability.correlation import correlation_id_ctx

    correlation_id_ctx.set(correlation_id)
    _tenant_id_ctx.set(tenant_id)
    _request_id_ctx.set(request_id)

    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        request_id=request_id,
    )


def make_job_context_wrapper(fn: _F) -> _F:
    """Wrap a *synchronous* callable so it re-seeds observability context on entry.

    Intended for APScheduler jobs executed via :class:`ThreadPoolExecutor`.
    Capture the current context at *call time* (i.e. when ``add_job`` /
    ``schedule_jobs`` runs) so that the job inherits the correlation_id of
    whatever trigger (HTTP request, startup code, etc.) registered it.

    Usage::

        scheduler.add_job(
            make_job_context_wrapper(self.run_scraper),
            args=[SourceType.FDA_WARNING_LETTER],
            ...
        )

    Or, equivalently, generate a fresh correlation_id for each *execution* by
    calling :func:`wrap_job_with_new_correlation` instead.
    """
    ctx_snapshot = _capture_observability_context()

    @functools.wraps(fn)
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        _restore_observability_context(**ctx_snapshot)
        return fn(*args, **kwargs)

    return _wrapper  # type: ignore[return-value]


def wrap_job_with_new_correlation(fn: _F, *, job_id: str = "") -> _F:
    """Wrap a *synchronous* callable so each execution gets a **fresh** correlation_id.

    Use this for APScheduler jobs that are timer-driven (not triggered by an
    HTTP request) — they should still emit a consistent correlation_id for
    the duration of a single run, but there is no parent request to inherit
    from. The generated ID is prefixed with ``job:`` so it is easy to
    distinguish from HTTP-originated IDs in log queries.

    The ``tenant_id`` / ``request_id`` are re-seeded from the context that
    was live when ``schedule_jobs()`` ran (typically ``unknown``) — this is
    intentional for timer-driven jobs that are not tenant-specific.
    """
    base_snapshot = _capture_observability_context()
    effective_job_id = job_id or getattr(fn, "__name__", "anon")

    @functools.wraps(fn)
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        fresh_cid = f"job:{effective_job_id}:{uuid.uuid4()}"
        ctx = {**base_snapshot, "correlation_id": fresh_cid}
        _restore_observability_context(**ctx)
        return fn(*args, **kwargs)

    return _wrapper  # type: ignore[return-value]


async def spawn_tracked(
    coro: Coroutine[Any, Any, Any],
    *,
    name: Optional[str] = None,
) -> "asyncio.Task[Any]":
    """Schedule *coro* as an asyncio Task, propagating the current observability context.

    ``asyncio.create_task`` copies the *contextvars snapshot* from the current
    task automatically. However, structlog's contextvars (stored separately via
    ``structlog.contextvars.bind_contextvars``) are *not* thread-local — they
    live in contextvars too, so they ARE inherited. This function is a
    documented, explicit wrapper that makes the intent clear in call-sites and
    generates a child correlation_id so each spawned task is independently
    traceable while still referencing the parent.

    For *sync* background work running in a ``ThreadPoolExecutor``, use
    :func:`make_job_context_wrapper` instead.
    """
    from shared.observability.correlation import correlation_id_ctx, generate_correlation_id

    parent_cid = correlation_id_ctx.get() or generate_correlation_id()
    child_cid = f"{parent_cid}:child:{uuid.uuid4().hex[:8]}"

    async def _wrapped() -> Any:
        # Re-bind child correlation_id so the task's logs are distinguishable
        # from the parent while still sharing the same root ID prefix.
        from shared.observability.correlation import correlation_id_ctx as _ctx
        _ctx.set(child_cid)
        structlog.contextvars.bind_contextvars(correlation_id=child_cid)
        return await coro

    task = asyncio.create_task(_wrapped(), name=name)
    return task


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
