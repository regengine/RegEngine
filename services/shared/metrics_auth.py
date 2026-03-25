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

import os

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

_METRICS_API_KEY = os.environ.get("METRICS_API_KEY", "")

_api_key_header = APIKeyHeader(name="X-Metrics-Key", auto_error=False)


def require_metrics_key(key: str | None = Security(_api_key_header)) -> None:
    """Raise 403 unless the request carries a valid metrics API key."""
    if not _METRICS_API_KEY or key != _METRICS_API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
