"""Redis subscription state management."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import redis
import structlog

from app.config import get_settings

logger = structlog.get_logger("stripe-billing")

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

# #1196: When a `customer.subscription.updated` or `.deleted` event arrives
# before the corresponding `checkout.session.completed` (Stripe does not
# guarantee event ordering), there is no tenant mapping to update yet.
# We buffer the latest pending update per subscription_id and drain it
# from `_handle_checkout_completed` once the mapping exists. TTL is 72h,
# longer than Stripe's documented ~3-day retry window, so nothing can fall
# through the cracks if checkout processing itself is delayed.
_PENDING_SUB_UPDATE_TTL_SECONDS = 72 * 60 * 60


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


# ── #1196: out-of-order subscription update buffer ────────────────────────

def _pending_sub_update_key(subscription_id: str) -> str:
    return f"billing:pending_sub_update:{subscription_id}"


def _buffer_pending_subscription_update(
    subscription_id: str,
    payload: dict[str, Any],
) -> bool:
    """Store the most-recent pending status update for a subscription.

    Returns ``True`` if the buffer was written (new or newer event), ``False``
    if we discarded this payload because an existing buffered update has a
    newer ``event_created``.

    The payload MUST include ``event_created`` (epoch int) so we can reason
    about ordering when multiple out-of-order updates queue against the same
    subscription_id. Other keys are free-form (status, current_period_end,
    last_invoice_id, ...).

    Fail-open on Redis errors: we log loudly and return ``False`` so callers
    don't assume the update was safely buffered. The pending update will
    simply be lost — same blast radius as the pre-fix behavior, but bounded
    to Redis outage windows.
    """
    if not subscription_id:
        logger.warning("stripe_pending_update_missing_sub_id")
        return False

    new_event_created = int(payload.get("event_created") or 0)
    client = _redis_client()
    key = _pending_sub_update_key(subscription_id)

    try:
        existing_raw = client.get(key)
        if existing_raw:
            try:
                existing = json.loads(existing_raw)
                existing_event_created = int(existing.get("event_created") or 0)
            except (ValueError, TypeError, json.JSONDecodeError):
                existing_event_created = 0
            if existing_event_created > new_event_created:
                logger.info(
                    "stripe_pending_update_older_ignored "
                    "subscription_id=%s buffered_event_created=%s new_event_created=%s",
                    subscription_id,
                    existing_event_created,
                    new_event_created,
                )
                return False

        client.set(
            key,
            json.dumps(payload, separators=(",", ":")),
            ex=_PENDING_SUB_UPDATE_TTL_SECONDS,
        )
        return True
    except redis.RedisError as exc:
        logger.error(
            "stripe_pending_update_redis_error subscription_id=%s error=%s",
            subscription_id,
            exc,
        )
        return False


def _pop_pending_subscription_update(
    subscription_id: str,
) -> Optional[dict[str, Any]]:
    """Atomically fetch-and-delete the buffered update, if any.

    Uses ``GETDEL`` (Redis ≥ 6.2) when available, with a pipeline fallback
    for older servers. If Redis is unavailable we return ``None`` and let
    the caller skip recovery — the next webhook retry or the periodic
    reconciliation job will pick it up.
    """
    if not subscription_id:
        return None

    client = _redis_client()
    key = _pending_sub_update_key(subscription_id)

    try:
        raw = None
        # GETDEL is atomic and the preferred single round-trip.
        try:
            raw = client.getdel(key)  # type: ignore[attr-defined]
        except (AttributeError, redis.ResponseError):
            # Older redis-py or server — fall back to pipeline GET+DEL.
            pipeline_factory = getattr(client, "pipeline", None)
            if pipeline_factory is None:
                return None
            pipe = pipeline_factory()
            pipe.get(key)
            pipe.delete(key)
            results = pipe.execute()
            raw = results[0] if results else None
    except redis.RedisError as exc:
        logger.error(
            "stripe_pending_update_pop_redis_error subscription_id=%s error=%s",
            subscription_id,
            exc,
        )
        return None

    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning(
            "stripe_pending_update_corrupt subscription_id=%s error=%s",
            subscription_id,
            exc,
        )
        return None


def _clear_customer_lookup(customer_id: str) -> None:
    """Remove the ``billing:customer:{customer_id}`` → tenant binding.

    Used when Stripe notifies us of a ``customer.deleted`` event (#1189).
    We intentionally do NOT delete the per-tenant subscription hash —
    that hash is the audit trail for the tenant's past billing state and
    must survive the customer being deleted in Stripe. Clearing the
    lookup key prevents a subsequent (out-of-order) webhook for the
    stale customer_id from silently re-binding to the same tenant.
    """
    if not customer_id:
        return
    client = _redis_client()
    try:
        client.delete(_customer_lookup_key(customer_id))
    except redis.RedisError as exc:  # pragma: no cover - logged for ops
        logger.warning(
            "stripe_customer_lookup_clear_redis_error customer_id=%s error=%s",
            customer_id, exc,
        )


def _clear_subscription_lookup(subscription_id: str) -> None:
    """Remove the ``billing:subscription:{subscription_id}`` → tenant binding.

    Companion to ``_clear_customer_lookup`` for cases where a subscription
    reference becomes stale (e.g. after ``customer.deleted`` we also drop
    the subscription mapping because the customer can no longer be billed
    under that ID).
    """
    if not subscription_id:
        return
    client = _redis_client()
    try:
        client.delete(_subscription_lookup_key(subscription_id))
    except redis.RedisError as exc:  # pragma: no cover - logged for ops
        logger.warning(
            "stripe_subscription_lookup_clear_redis_error subscription_id=%s error=%s",
            subscription_id, exc,
        )
