"""Metrics endpoint authentication.

Protects /metrics endpoints with a shared API key so Prometheus metrics
are not publicly accessible.  Set METRICS_API_KEY in the environment;
if unset, the endpoint returns 403 unconditionally.

Usage (FastAPI):
    from shared.metrics_auth import require_metrics_key

    @router.get("/metrics", dependencies=[Depends(require_metrics_key)])
    def metrics(): ...
"""

from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

_api_key_header = APIKeyHeader(name="X-Metrics-Key", auto_error=False)


def _get_metrics_api_key() -> str:
    """Read the metrics key from the environment on every call.

    The key is deliberately not cached at import time so key rotation
    takes effect without restarting the process.
    """
    return os.environ.get("METRICS_API_KEY", "")


def require_metrics_key(key: str | None = Security(_api_key_header)) -> None:
    """Raise 403 unless the request carries a valid metrics API key."""
    expected = _get_metrics_api_key()
    if not expected or not key or not hmac.compare_digest(key, expected):
        raise HTTPException(status_code=403, detail="Forbidden")
