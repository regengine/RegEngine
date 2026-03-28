"""Subscription gating middleware for paid API endpoints.

Checks Redis for an active Stripe subscription before allowing access.
Subscription state is kept in sync by the Stripe webhook handler.
"""

import logging
import os

import redis
from fastapi import HTTPException, Request

from shared.circuit_breaker import CircuitOpenError, redis_circuit

logger = logging.getLogger(__name__)

_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(_redis_url, decode_responses=True)
    return _redis_client


async def require_active_subscription(request: Request) -> bool:
    """FastAPI dependency that blocks requests without an active subscription.

    Checks the Redis key ``subscription:{tenant_id}:status`` which is set by
    the Stripe webhook handler on checkout.session.completed /
    customer.subscription.updated / customer.subscription.deleted events.

    Allowed statuses: ``active``, ``trialing``.

    Raises:
        HTTPException 401 if no tenant ID is provided.
        HTTPException 402 if no active subscription exists.
    """
    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="X-Tenant-ID header required")

    try:
        redis_circuit._check_state()  # raises CircuitOpenError if open
        r = _get_redis()
        sub_status = r.get(f"subscription:{tenant_id}:status")
        redis_circuit._record_success()
    except CircuitOpenError:
        raise HTTPException(
            status_code=503,
            detail="Billing system temporarily unavailable. Please try again shortly.",
        )
    except redis.RedisError as exc:
        redis_circuit._record_failure(exc)
        logger.exception("subscription_check_redis_error tenant=%s", tenant_id)
        return True

    if sub_status in ("active", "trialing"):
        return True

    raise HTTPException(
        status_code=402,
        detail={
            "error": "subscription_required",
            "message": "An active subscription is required. Visit /pricing to subscribe.",
            "upgrade_url": "/pricing",
        },
    )
