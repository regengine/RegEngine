"""EDI interchange deduplication + partner allowlist (#1160, #1165).

#1165: X12 ISA[13] is the unique interchange control number. Receivers
MUST deduplicate retransmissions so a partner's ACK-timeout resend
does not double-ingest CTEs. We key dedup on
``(tenant_id, sender_id, receiver_id, isa13)`` — with the caveat that
``sender_id`` / ``receiver_id`` are taken from the GS segment
(application-level trading partner IDs) per #1160, not ISA. The tenant
is part of the key because ISA13 is only unique per sender: two tenants
receiving from one partner can see the same envelope IDs, and one must
not be refused on the strength of the other's interchange.

#1160: The GS segment identifies the actual trading partner. If the
ISA envelope claims Tenant A but the GS claims Tenant B, reject the
interchange — this is a tenant-binding smuggling attempt.

Storage: the dedup key is held in Redis with a 7-day TTL (partners
rarely retransmit later than that). If Redis is unavailable the
ingest proceeds but a warning is logged — fail-open is acceptable
because the downstream CTE hash chain will also enforce
idempotency for properly-formed events.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger("edi-dedup")

_DEDUP_KEY_PREFIX = "edi:interchange:"
_DEDUP_TTL_SECONDS = 7 * 24 * 3600  # 7 days
# Delete the key only while it still holds the caller's claim token.
_RELEASE_IF_OWNER_LUA = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0"


def _dedup_key(tenant_id: str, sender_id: Optional[str], receiver_id: Optional[str], isa13: Optional[str]) -> str:
    """Compose the Redis dedup key.

    None components are replaced with an empty string so that a partially
    malformed envelope still produces a distinct key (rather than coalescing
    to a shared null bucket).
    """
    t = tenant_id.strip()
    s = (sender_id or "").strip()
    r = (receiver_id or "").strip()
    i = (isa13 or "").strip()
    return f"{_DEDUP_KEY_PREFIX}{t}:{s}:{r}:{i}"


def _redis_client():
    """Return a sync Redis client or None if Redis is unavailable."""
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None
    try:
        import redis as redis_lib

        return redis_lib.from_url(redis_url, decode_responses=True, socket_timeout=2)
    except Exception as exc:
        logger.warning("edi_dedup_redis_unavailable error=%s", str(exc))
        return None


def check_and_record_interchange(
    tenant_id: str,
    sender_id: Optional[str],
    receiver_id: Optional[str],
    isa13: Optional[str],
    claim_token: str,
) -> tuple[bool, Optional[str]]:
    """Return ``(is_duplicate, previous_ack_id)``.

    - Returns ``(True, previous)`` if we have seen this interchange
      before: the caller should reply with HTTP 409 / idempotent-replay.
    - Returns ``(False, None)`` otherwise and records the interchange
      atomically via ``SET ... NX``, storing ``claim_token``.

    If any envelope ID is missing (malformed interchange) or Redis is
    down, returns ``(False, None)`` and the caller proceeds with
    normal ingestion. Downstream CTE-hash idempotency catches the
    degenerate cases.

    ``(False, None)`` therefore does not prove a claim was taken. The
    caller passes a ``claim_token`` unique to the request, and
    ``release_interchange`` frees the key only if it holds that token.
    """
    if not isa13 or not sender_id:
        return False, None

    client = _redis_client()
    if client is None:
        return False, None

    key = _dedup_key(tenant_id, sender_id, receiver_id, isa13)
    try:
        # SET NX EX — atomic "create if absent". Returns True iff we
        # set the key (first time we saw this interchange), False if
        # it already existed (retransmission).
        was_set = client.set(key, claim_token, nx=True, ex=_DEDUP_TTL_SECONDS)
        if was_set:
            return False, None
        previous = client.get(key)
        return True, previous
    except Exception as exc:
        logger.warning(
            "edi_dedup_redis_error tenant=%s sender=%s isa13=%s error=%s",
            tenant_id,
            sender_id,
            isa13,
            str(exc),
        )
        return False, None


def release_interchange(
    tenant_id: str,
    sender_id: Optional[str],
    receiver_id: Optional[str],
    isa13: Optional[str],
    claim_token: str,
) -> None:
    """Free an ISA13 reserved by ``check_and_record_interchange``.

    Called when the request fails after the reservation (content
    rejection, ingest error). Without it the 409 replay answer, "already
    processed — no events were ingested", would refuse the partner's
    resend for the full TTL even though nothing was stored. Best-effort:
    a Redis error is logged and the key simply expires.

    The delete applies only while the key holds ``claim_token``. A request
    that failed open on a Redis error may hold no claim, and a concurrent
    retry may own the key by then. Its claim must survive. If that failed
    ``SET`` did land, the key holds this token and is freed.
    """
    if not isa13 or not sender_id:
        return

    client = _redis_client()
    if client is None:
        return

    try:
        client.eval(_RELEASE_IF_OWNER_LUA, 1, _dedup_key(tenant_id, sender_id, receiver_id, isa13), claim_token)
    except Exception as exc:
        logger.warning(
            "edi_dedup_release_error tenant=%s sender=%s isa13=%s error=%s",
            tenant_id,
            sender_id,
            isa13,
            str(exc),
        )


# ---------------------------------------------------------------------------
# Partner allowlist — bind GS sender to tenant's configured trading partners.
# ---------------------------------------------------------------------------


def verify_trading_partner_allowed(
    tenant_id: str,
    gs_sender_id: Optional[str],
) -> bool:
    """Check whether the GS sender id is allowed for the tenant.

    Allowlist source: ``EDI_PARTNER_ALLOWLIST_{TENANT_ID}`` env var
    (comma-separated). If no allowlist is configured for the tenant,
    this returns ``True`` (permissive) — tenants only start enforcing
    once they set the env var. The global ``EDI_PARTNER_ALLOWLIST``
    (already consulted in ``utils._verify_partner_id``) is NOT used
    here because it is keyed on the ``X-Partner-ID`` header, which is
    different from the EDI trading-partner id.
    """
    if not gs_sender_id:
        return True  # nothing to check — extractor will have flagged it

    env_key = f"EDI_PARTNER_ALLOWLIST_{tenant_id.upper().replace('-', '_')}"
    raw = os.getenv(env_key, "").strip()
    if not raw:
        return True
    allowed = {item.strip() for item in raw.split(",") if item.strip()}
    return gs_sender_id.strip() in allowed
