"""EDI interchange deduplication + partner allowlist (#1160, #1165).

#1165: X12 ISA[13] is the unique interchange control number. Receivers
MUST deduplicate retransmissions so a partner's ACK-timeout resend
does not double-ingest CTEs. We key dedup on
``(sender_id, receiver_id, isa13)`` — with the caveat that
``sender_id`` / ``receiver_id`` are taken from the GS segment
(application-level trading partner IDs) per #1160, not ISA.

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


def _dedup_key(sender_id: Optional[str], receiver_id: Optional[str], isa13: Optional[str]) -> str:
    """Compose the Redis dedup key.

    None components are replaced with an empty string so that a partially
    malformed envelope still produces a distinct key (rather than coalescing
    to a shared null bucket).
    """
    s = (sender_id or "").strip()
    r = (receiver_id or "").strip()
    i = (isa13 or "").strip()
    return f"{_DEDUP_KEY_PREFIX}{s}:{r}:{i}"


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
    sender_id: Optional[str],
    receiver_id: Optional[str],
    isa13: Optional[str],
) -> tuple[bool, Optional[str]]:
    """Return ``(is_duplicate, previous_ack_id)``.

    - Returns ``(True, previous)`` if we have seen this interchange
      before: the caller should reply with HTTP 409 / idempotent-replay.
    - Returns ``(False, None)`` otherwise and records the interchange
      atomically via ``SET ... NX``.

    If any envelope ID is missing (malformed interchange) or Redis is
    down, returns ``(False, None)`` and the caller proceeds with
    normal ingestion. Downstream CTE-hash idempotency catches the
    degenerate cases.
    """
    if not isa13 or not sender_id:
        return False, None

    client = _redis_client()
    if client is None:
        return False, None

    key = _dedup_key(sender_id, receiver_id, isa13)
    try:
        # SET NX EX — atomic "create if absent". Returns True iff we
        # set the key (first time we saw this interchange), False if
        # it already existed (retransmission).
        placeholder = "seen"
        was_set = client.set(key, placeholder, nx=True, ex=_DEDUP_TTL_SECONDS)
        if was_set:
            return False, None
        previous = client.get(key)
        return True, previous
    except Exception as exc:
        logger.warning(
            "edi_dedup_redis_error sender=%s isa13=%s error=%s",
            sender_id, isa13, str(exc),
        )
        return False, None


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
