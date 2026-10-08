"""Tenant-scoped rate limiting for webhook ingest and read endpoints.

Code moved verbatim from the original ``webhook_router_v2.py``.
``consume_tenant_rate_limit`` / ``rate_limit_reset_epoch`` and the
sibling helpers are resolved through the package namespace (``_pkg``)
at call time so tests that monkeypatch
``app.webhook_router_v2.consume_tenant_rate_limit`` keep working.
"""

from __future__ import annotations

import os
import sys

from fastapi import HTTPException, Request

_pkg = sys.modules[__package__]


# ---------------------------------------------------------------------------
# Rate Limiting (Redis-backed with in-memory fallback via shared module)
# ---------------------------------------------------------------------------

def _positive_int_env(name: str, default: int) -> int:
    """Read a positive-int rate-limit setting, falling back to ``default``.

    A garbage value (``"abc"``, empty, negative) must never crash the
    module import: these constants are evaluated at import time, so an
    unguarded ``int(os.getenv(...))`` takes the whole service down on a
    single operator typo. Floor at 1 so a zero/negative value cannot
    disable the bucket or invert the window.
    """
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (ValueError, TypeError):
        return default


_WEBHOOK_RATE_LIMIT_RPM = _positive_int_env("WEBHOOK_INGEST_RATE_LIMIT_RPM", 120)
_WEBHOOK_RATE_LIMIT_WINDOW_SECS = _positive_int_env("WEBHOOK_INGEST_RATE_LIMIT_WINDOW_SECONDS", 60)

# F-4 (re-audit): tighter, separate bucket for read endpoints (/recent,
# /chain/verify). These are dashboard-facing reads, not partner ingestion,
# so they should be rate-limited away from the ingest budget and capped
# lower to make scraping/oracle-style probing visible.
_WEBHOOK_READ_RATE_LIMIT_RPM = _positive_int_env("WEBHOOK_READ_RATE_LIMIT_RPM", 30)
_WEBHOOK_READ_RATE_LIMIT_WINDOW_SECS = _positive_int_env("WEBHOOK_READ_RATE_LIMIT_WINDOW_SECONDS", 60)


def _store_rate_limit_state(
    request: Request | None,
    *,
    limit: int,
    remaining: int,
    tenant_id: str,
    scope: str,
    window: int,
) -> None:
    if request is None:
        return
    request.state.rate_limit_limit = limit
    request.state.rate_limit_remaining = remaining
    request.state.rate_limit_reset = str(_pkg.rate_limit_reset_epoch(window))
    request.state.rate_limit_tenant = tenant_id
    request.state.rate_limit_scope = scope


def _check_read_rate_limit(tenant_id: str, scope: str, request: Request | None = None) -> None:
    """Tenant-scoped sliding-window limit for webhook READ endpoints.

    Distinct from ``_check_rate_limit`` (ingest): smaller default budget,
    different bucket key per scope so /recent and /chain/verify do not
    starve each other.
    """
    allowed, remaining = _pkg.consume_tenant_rate_limit(
        tenant_id=tenant_id,
        bucket_suffix=f"webhooks.read.{scope}",
        limit=_pkg._WEBHOOK_READ_RATE_LIMIT_RPM,
        window=_pkg._WEBHOOK_READ_RATE_LIMIT_WINDOW_SECS,
    )
    if not allowed:
        reset = str(_pkg.rate_limit_reset_epoch(_pkg._WEBHOOK_READ_RATE_LIMIT_WINDOW_SECS))
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded for tenant '{tenant_id}' "
                f"({_pkg._WEBHOOK_READ_RATE_LIMIT_RPM}/{_pkg._WEBHOOK_READ_RATE_LIMIT_WINDOW_SECS}s)"
            ),
            headers={
                "Retry-After": str(_pkg._WEBHOOK_READ_RATE_LIMIT_WINDOW_SECS),
                "X-RateLimit-Limit": str(_pkg._WEBHOOK_READ_RATE_LIMIT_RPM),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": reset,
                "X-RateLimit-Tenant": tenant_id,
                "X-RateLimit-Scope": f"webhooks.read.{scope}",
            },
        )
    _pkg._store_rate_limit_state(
        request,
        limit=_pkg._WEBHOOK_READ_RATE_LIMIT_RPM,
        remaining=remaining,
        tenant_id=tenant_id,
        scope=f"webhooks.read.{scope}",
        window=_pkg._WEBHOOK_READ_RATE_LIMIT_WINDOW_SECS,
    )
    _pkg.logger.debug(
        "webhook_read_rate_limit_allow tenant_id=%s scope=%s remaining=%s",
        tenant_id,
        scope,
        remaining,
    )


def _check_rate_limit(tenant_id: str, request: Request | None = None) -> None:
    """Tenant-scoped sliding-window limit for webhook ingestion."""
    allowed, remaining = _pkg.consume_tenant_rate_limit(
        tenant_id=tenant_id,
        bucket_suffix="webhooks.ingest",
        limit=_pkg._WEBHOOK_RATE_LIMIT_RPM,
        window=_pkg._WEBHOOK_RATE_LIMIT_WINDOW_SECS,
    )
    if not allowed:
        reset = str(_pkg.rate_limit_reset_epoch(_pkg._WEBHOOK_RATE_LIMIT_WINDOW_SECS))
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded for tenant '{tenant_id}' "
                f"({_pkg._WEBHOOK_RATE_LIMIT_RPM}/{_pkg._WEBHOOK_RATE_LIMIT_WINDOW_SECS}s)"
            ),
            headers={
                "Retry-After": str(_pkg._WEBHOOK_RATE_LIMIT_WINDOW_SECS),
                "X-RateLimit-Limit": str(_pkg._WEBHOOK_RATE_LIMIT_RPM),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": reset,
                "X-RateLimit-Tenant": tenant_id,
                "X-RateLimit-Scope": "webhooks.ingest",
            },
        )
    _pkg._store_rate_limit_state(
        request,
        limit=_pkg._WEBHOOK_RATE_LIMIT_RPM,
        remaining=remaining,
        tenant_id=tenant_id,
        scope="webhooks.ingest",
        window=_pkg._WEBHOOK_RATE_LIMIT_WINDOW_SECS,
    )
    _pkg.logger.debug(
        "webhook_rate_limit_allow tenant_id=%s remaining=%s",
        tenant_id,
        remaining,
    )
