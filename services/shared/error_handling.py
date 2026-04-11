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


def init_sentry() -> None:
    """Initialize Sentry error tracking if SENTRY_DSN is configured.

    Call this before creating the FastAPI app in each service's main.py.
    No-op if sentry-sdk is not installed or SENTRY_DSN is not set.
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
    )
    logger.info("sentry_initialized", environment=get_environment())


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
    """Catch-all handler for unhandled exceptions."""
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"error": {"type": "internal_error", "message": "An internal error occurred"}},
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
