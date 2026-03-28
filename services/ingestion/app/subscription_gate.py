"""
Subscription Gate — FastAPI dependency for paid endpoint access control.

Checks Redis for the tenant's subscription status and rejects requests
with HTTP 402 Payment Required if no active subscription exists.

Redis key pattern: billing:tenant:{tenant_id} (hash with "status" field)
Allowed statuses: "active", "trialing"
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import Depends, Header, HTTPException, Query, Request

logger = logging.getLogger("subscription-gate")


def _get_tenant_id_from_request(request: Request) -> Optional[str]:
    """Extract tenant_id from query params, headers, or RBAC principal.

    Mirrors the tenant resolution order used elsewhere in the ingestion
    service (query param > header > principal).
    """
    # 1. Query parameter (most endpoints use this)
    tenant_id = request.query_params.get("tenant_id")
    if tenant_id:
        return tenant_id

    # 2. Header
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id:
        return tenant_id

    # 3. RBAC principal (set by require_permission / get_ingestion_principal)
    principal = getattr(request.state, "principal", None)
    if principal and getattr(principal, "tenant_id", None):
        return principal.tenant_id

    return None


def _check_subscription_in_redis(tenant_id: str) -> Optional[str]:
    """Look up subscription status from Redis.

    Returns the status string if found, or None if Redis is unavailable
    or the key does not exist.
    """
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None

    try:
        import redis as redis_lib

        client = redis_lib.from_url(redis_url, decode_responses=True)
        status = client.hget(f"billing:tenant:{tenant_id}", "status")
        return status
    except Exception as exc:
        logger.warning(
            "subscription_gate_redis_unavailable tenant_id=%s error=%s",
            tenant_id,
            str(exc),
        )
        return None


async def require_active_subscription(request: Request) -> None:
    """FastAPI dependency that gates access to paid endpoints.

    Resolution logic:
    1. Extract tenant_id from the request context.
    2. Query Redis for ``billing:tenant:{tenant_id}`` -> ``status``.
    3. Allow if status is ``active`` or ``trialing``.
    4. Return HTTP 402 if the subscription is missing, cancelled, or unpaid.
    5. Gracefully allow through if Redis is unreachable (fail-open with warning).
    """
    tenant_id = _get_tenant_id_from_request(request)
    if not tenant_id:
        # If we cannot determine the tenant, let downstream auth handle rejection.
        # This avoids blocking unauthenticated health-check probes, etc.
        return

    status = _check_subscription_in_redis(tenant_id)

    if status is None:
        # Redis unavailable or key missing — fail open to avoid blocking
        # legitimate traffic during Redis outages.  The billing webhook
        # handler will populate the key once the tenant subscribes.
        logger.debug(
            "subscription_gate_no_status tenant_id=%s (allowing through)",
            tenant_id,
        )
        return

    allowed_statuses = {"active", "trialing"}
    if status.lower() in allowed_statuses:
        return

    logger.info(
        "subscription_gate_blocked tenant_id=%s status=%s",
        tenant_id,
        status,
    )
    raise HTTPException(
        status_code=402,
        detail=(
            f"Active subscription required. Current status: '{status}'. "
            "Please subscribe or update your billing at https://regengine.co/billing."
        ),
    )
