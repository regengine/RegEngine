"""Redis subscription state management."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import redis

from app.config import get_settings

logger = logging.getLogger("stripe-billing")

# #1076: Stripe retries any webhook that doesn't ack within ~a few seconds,
# and continues retrying for up to 3 days on 5xx/timeouts. Without a dedup
# gate, a slow handler (e.g. network blip talking to admin service during
# tenant provisioning) causes the SAME event to be delivered multiple times,
# and every handler that mutates state (tenant provisioning, funnel events,
# subscription status flips) runs more than once per real-world event.
#
# We key on the webhook event id, which Stripe guarantees is stable across
# retries of the same event. TTL is 24h — long enough to span any realistic
# Stripe retry burst (their published retry window is shorter), short enough
# that Redis memory doesn't grow unboundedly if key eviction is disabled.
_EVENT_DEDUP_TTL_SECONDS = 24 * 60 * 60


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


def _event_dedup_key(event_id: str) -> str:
    """Redis key used to dedup a Stripe webhook event by its event.id.

    See the module-level TTL constant for the retention rationale (#1076).
    """
    return f"billing:stripe:event:seen:{event_id}"


def _mark_event_seen(event_id: str) -> bool:
    """Atomically claim ``event_id`` for first-writer-wins processing.

    Returns ``True`` if this caller is the first to see the event
    (i.e. the handler should run), ``False`` if the event was already
    processed (or a concurrent request claimed it first).

    Uses Redis ``SET NX EX`` for a single round-trip check-and-set —
    this is the standard idempotency-gate pattern for webhook consumers.

    #1076 design note: if Redis itself is unavailable we log loudly and
    fail OPEN (return ``True``). Fail-closed would reject every Stripe
    webhook during a Redis outage, which is a strictly worse failure
    mode — Stripe would keep retrying, at-least-once delivery becomes
    at-least-once-with-amplification, and the tenant may eventually be
    marked past_due for a legitimate payment. We accept the at-most-
    once-duplicate risk during an outage and let the handlers' own
    per-event consistency (e.g. the server-side session binding in
    ``_handle_checkout_completed``) limit blast radius.
    """
    if not event_id:
        # Stripe always populates event.id; treat missing as non-idempotent
        # to avoid crashing on malformed test payloads, but log loudly so
        # the gap is discoverable.
        logger.warning("stripe_webhook_dedup_missing_event_id")
        return True

    client = _redis_client()
    try:
        # SET NX EX 86400: first writer wins, 24h TTL.
        # decode_responses=True means we get True/None from redis-py.
        claimed = client.set(
            _event_dedup_key(event_id),
            "1",
            nx=True,
            ex=_EVENT_DEDUP_TTL_SECONDS,
        )
    except redis.RedisError as exc:
        logger.error(
            "stripe_webhook_dedup_redis_error event_id=%s error=%s",
            event_id,
            exc,
        )
        # Fail open — see design note above.
        return True

    return bool(claimed)


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
