"""
Shared Global Exception Handlers for RegEngine Services.

Provides a one-call installer that registers structured JSON error responses
for all unhandled exceptions, ensuring no service ever returns raw HTML 500s.

Usage:
    from shared.error_handling import install_exception_handlers
    install_exception_handlers(app)
"""

from __future__ import annotations

import traceback
from typing import Optional

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger("error_handler")


def _get_request_id(request: Request) -> Optional[str]:
    """Extract request ID from request state if available."""
    return getattr(request.state, "request_id", None)


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle HTTP exceptions with structured JSON response."""
    request_id = _get_request_id(request)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "http_error",
            "status_code": exc.status_code,
            "detail": exc.detail,
            "request_id": request_id,
        },
    )


async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle request validation errors with structured JSON response."""
    request_id = _get_request_id(request)
    # Pydantic v2 errors() can contain non-serializable objects (ValueError, etc.)
    # Convert to safe serializable form
    try:
        import json as _json
        safe_errors = _json.loads(_json.dumps(exc.errors(), default=str))
    except Exception:
        safe_errors = [{"msg": str(e)} for e in exc.errors()] if exc.errors() else [{"msg": str(exc)}]
    logger.warning(
        "validation_error",
        request_id=request_id,
        errors=safe_errors,
        path=str(request.url.path),
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "detail": safe_errors,
            "request_id": request_id,
        },
    )


async def _value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Handle ValueError as a 400 Bad Request."""
    request_id = _get_request_id(request)
    logger.warning(
        "value_error",
        request_id=request_id,
        detail=str(exc),
        path=str(request.url.path),
    )
    return JSONResponse(
        status_code=400,
        content={
            "error": "bad_request",
            "detail": str(exc),
            "request_id": request_id,
        },
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled exceptions."""
    request_id = _get_request_id(request)
    logger.error(
        "unhandled_exception",
        request_id=request_id,
        exc_type=type(exc).__name__,
        exc_message=str(exc),
        path=str(request.url.path),
        traceback=traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "detail": "An unexpected error occurred. Please try again or contact support.",
            "request_id": request_id,
        },
    )


def install_exception_handlers(app: FastAPI) -> None:
    """
    Install global exception handlers on a FastAPI application.

    Registers handlers for:
    - StarletteHTTPException → structured JSON with status code
    - RequestValidationError → 422 with field-level details
    - ValueError → 400 Bad Request
    - Exception (catch-all) → 500 with request_id for correlation

    Args:
        app: The FastAPI application instance.
    """
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(ValueError, _value_error_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
