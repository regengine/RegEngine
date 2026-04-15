"""Redis subscription state management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import redis

from app.config import get_settings


def _redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.from_url(settings.redis_url, decode_responses=True)


def _tenant_subscription_key(tenant_id: str) -> str:
    return f"billing:tenant:{tenant_id}"


def _subscription_lookup_key(subscription_id: str) -> str:
    return f"billing:subscription:{subscription_id}"


def _customer_lookup_key(customer_id: str) -> str:
    return f"billing:customer:{customer_id}"


def _session_lookup_key(session_id: str) -> str:
    return f"billing:session:{session_id}"


def _store_subscription_mapping(tenant_id: str, payload: dict[str, str]) -> None:
    client = _redis_client()
    key = _tenant_subscription_key(tenant_id)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()

    client.hset(key, mapping=payload)

    subscription_id = payload.get("subscription_id")
    if subscription_id:
        client.set(_subscription_lookup_key(subscription_id), tenant_id)

    customer_id = payload.get("customer_id")
    if customer_id:
        client.set(_customer_lookup_key(customer_id), tenant_id)

    session_id = payload.get("session_id")
    if session_id:
        client.set(_session_lookup_key(session_id), tenant_id)


def _get_subscription_mapping(tenant_id: str) -> dict[str, str]:
    client = _redis_client()
    return client.hgetall(_tenant_subscription_key(tenant_id))


def _find_tenant_id(subscription_id: Optional[str], customer_id: Optional[str]) -> Optional[str]:
    client = _redis_client()

    if subscription_id:
        tenant_id = client.get(_subscription_lookup_key(subscription_id))
        if tenant_id:
            return tenant_id

    if customer_id:
        tenant_id = client.get(_customer_lookup_key(customer_id))
        if tenant_id:
            return tenant_id

    return None
