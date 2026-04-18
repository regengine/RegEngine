"""
Shared Global Exception Handlers for RegEngine Services.

Provides a one-call installer that registers structured JSON error responses
for all unhandled exceptions, ensuring no service ever returns raw HTML 500s.

Usage:
    from shared.error_handling import install_exception_handlers
    install_exception_handlers(app)
"""

from __future__ import annotations

import os

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration
    _HAS_SENTRY = True
except ImportError:
    _HAS_SENTRY = False

logger = structlog.get_logger("error_handler")


def _sentry_before_send(event, hint):
    """Sentry before_send hook — stamp tenant_id / correlation_id on every event.

    Runs synchronously for every event Sentry is about to transmit. We read
    the current contextvar state (set by CorrelationIdMiddleware +
    TenantContextMiddleware) and attach:

    * ``tags.tenant_id`` — indexable in Sentry so operators can filter
      errors per tenant.
    * ``tags.correlation_id`` — join key back to structured logs in Datadog
      / Loki.
    * ``tags.request_id`` — joins the Sentry event to a specific HTTP
      request for in-app grep.

    The hook is tolerant of missing context (background jobs, bootstrap) —
    it returns the event unchanged rather than raising. (#1320)
    """
    try:
        from shared.observability.correlation import get_correlation_id

        cid = get_correlation_id()
        if cid:
            event.setdefault("tags", {})
            event["tags"].setdefault("correlation_id", cid)
    except Exception:
        pass

    try:
        from structlog.contextvars import get_contextvars

        ctx = get_contextvars()
        tid = ctx.get("tenant_id")
        if tid:
            event.setdefault("tags", {})
            event["tags"].setdefault("tenant_id", str(tid))
            # Also set Sentry's first-class user context so the tenant
            # filter in the Sentry UI picks it up.
            event.setdefault("user", {})
            event["user"].setdefault("tenant_id", str(tid))
        rid = ctx.get("request_id")
        if rid:
            event.setdefault("tags", {})
            event["tags"].setdefault("request_id", str(rid))
    except Exception:
        pass

    return event


def init_sentry() -> None:
    """Initialize Sentry error tracking if SENTRY_DSN is configured.

    Call this before creating the FastAPI app in each service's main.py.
    No-op if sentry-sdk is not installed or SENTRY_DSN is not set.

    Registers a ``before_send`` hook that attaches ``tenant_id``,
    ``correlation_id``, and ``request_id`` tags to every event so operators
    can filter errors per tenant and join to structured logs (#1320).
    """
    if not _HAS_SENTRY:
        logger.info("sentry_sdk not installed — skipping Sentry init")
        return

    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        logger.info("SENTRY_DSN not set — skipping Sentry init")
        return

    from shared.env import get_environment

    sentry_sdk.init(
        dsn=dsn,
        environment=get_environment(),
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.1")),
        integrations=[
            FastApiIntegration(),
            StarletteIntegration(),
        ],
        send_default_pii=False,
        before_send=_sentry_before_send,
    )
    logger.info("sentry_initialized", environment=get_environment())


def set_sentry_user_context(user_id: str | None = None, tenant_id: str | None = None) -> None:
    """Attach user / tenant context to the current Sentry scope.

    Intended to be called from ``get_current_user`` right after the user is
    resolved from the JWT / API key so subsequent Sentry events in the
    request carry the identifier. No-op if Sentry is not initialized.

    Args:
        user_id: The authenticated user UUID (stringified).
        tenant_id: The tenant UUID the user belongs to (stringified).
    """
    if not _HAS_SENTRY:
        return
    try:
        if user_id is not None:
            sentry_sdk.set_user({"id": str(user_id)})
        if tenant_id is not None:
            sentry_sdk.set_tag("tenant_id", str(tenant_id))
    except Exception as exc:
        logger.debug("sentry_scope_update_failed", error=str(exc))


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle HTTP exceptions with structured JSON response."""
    detail = exc.detail
    if isinstance(detail, dict):
        return JSONResponse(status_code=exc.status_code, content={"error": detail})
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"type": f"http_{exc.status_code}", "message": str(detail)}},
    )


async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle request validation errors with structured JSON response."""
    return JSONResponse(
        status_code=422,
        content={"error": {"type": "validation_error", "message": "Request validation failed", "details": exc.errors()}},
    )


async def _value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Handle ValueError as a 400 Bad Request."""
    logger.warning("value_error", detail=str(exc), path=str(request.url.path))
    return JSONResponse(
        status_code=400,
        content={"error": {"type": "bad_request", "message": str(exc)}},
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled exceptions.

    Includes ``correlation_id`` and ``request_id`` in the JSON error body so
    users can quote an identifier when they report the error and support
    can join it back to logs / Sentry events (#1320).
    """
    logger.exception("Unhandled exception")

    error_body: dict = {
        "type": "internal_error",
        "message": "An internal error occurred",
    }

    # Best-effort: include correlation + request IDs so users can reference
    # them in support tickets. Reads the contextvars (not request.state) so
    # it still works if the crash happens before middleware seeds state.
    try:
        from shared.observability.correlation import get_correlation_id

        cid = get_correlation_id()
        if cid:
            error_body["correlation_id"] = cid
    except Exception:
        pass

    try:
        from structlog.contextvars import get_contextvars

        ctx = get_contextvars()
        rid = ctx.get("request_id")
        if rid:
            error_body["request_id"] = str(rid)
    except Exception:
        pass

    return JSONResponse(
        status_code=500,
        content={"error": error_body},
    )


def install_exception_handlers(app: FastAPI) -> None:
    """
    Install global exception handlers on a FastAPI application.

    Registers handlers for:
    - StarletteHTTPException → structured JSON with {error: {type, message}}
    - RequestValidationError → 422 with {error: {type, message, details}}
    - ValueError → 400 with {error: {type, message}}
    - Exception (catch-all) → 500 with {error: {type, message}}

    Args:
        app: The FastAPI application instance.
    """
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(ValueError, _value_error_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
