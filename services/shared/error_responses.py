"""Standardized error response helpers for all RegEngine services.

Usage:
    from shared.error_responses import error_response, raise_error

    # Return a JSONResponse with consistent shape
    return error_response(404, "Tenant not found", error_type="tenant_not_found")

    # Raise an HTTPException with consistent detail shape
    raise_error(403, "Insufficient permissions", error_type="forbidden")
"""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse


def error_response(
    status_code: int,
    message: str,
    error_type: str | None = None,
    details: dict | None = None,
) -> JSONResponse:
    """Return a JSONResponse with the standard RegEngine error shape."""
    body: dict = {
        "error": {
            "type": error_type or f"http_{status_code}",
            "message": message,
        }
    }
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


def raise_error(
    status_code: int,
    message: str,
    error_type: str | None = None,
) -> None:
    """Raise an HTTPException whose detail is the standard error dict."""
    raise HTTPException(
        status_code=status_code,
        detail={"type": error_type or f"http_{status_code}", "message": message},
    )
