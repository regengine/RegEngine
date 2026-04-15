"""
Sandbox rate limiting — simple in-memory, per-IP.

Moved from sandbox_router.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

from fastapi import HTTPException


_rate_buckets: Dict[str, list] = {}
_SANDBOX_RATE_LIMIT = 30  # requests per minute
_SANDBOX_WINDOW = 60


def _check_sandbox_rate_limit(client_ip: str) -> None:
    """Simple per-IP rate limit for sandbox endpoint."""
    now = datetime.now(timezone.utc).timestamp()
    bucket = _rate_buckets.setdefault(client_ip, [])
    # Prune old entries
    bucket[:] = [t for t in bucket if now - t < _SANDBOX_WINDOW]
    if len(bucket) >= _SANDBOX_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Sandbox rate limit exceeded. Try again in a minute.",
        )
    bucket.append(now)
