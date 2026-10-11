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

_METRICS_API_KEY = os.environ.get("METRICS_API_KEY", "")

_api_key_header = APIKeyHeader(name="X-Metrics-Key", auto_error=False)


def _configured_key() -> str:
    # Read per call (falling back to the import-time value) so key
    # rotation via the environment takes effect without a restart.
    return os.environ.get("METRICS_API_KEY", _METRICS_API_KEY)


def require_metrics_key(key: str | None = Security(_api_key_header)) -> None:
    """Raise 403 unless the request carries a valid metrics API key."""
    configured = _configured_key()
    if not configured or not key or not hmac.compare_digest(key, configured):
        raise HTTPException(status_code=403, detail="Forbidden")
