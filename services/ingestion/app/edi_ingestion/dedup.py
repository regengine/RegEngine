"""EDI interchange deduplication + partner allowlist (#1160, #1165).

#1165: X12 ISA[13] is the unique interchange control number. Receivers
MUST deduplicate retransmissions so a partner's ACK-timeout resend
does not double-ingest CTEs. We key dedup on
``(tenant_id, sender_id, receiver_id, isa13)`` — with the caveat that
``sender_id`` / ``receiver_id`` are taken from the GS segment
(application-level trading partner IDs) per #1160, not ISA.

#1160: The GS segment identifies the actual trading partner. If the
ISA envelope claims Tenant A but the GS claims Tenant B, reject the
interchange — this is a tenant-binding smuggling attempt.

Storage: Redis holds completed interchanges for seven days. Checks do
not reserve an interchange: only fully accepted, committed requests
write a marker. Failed or partially rejected requests remain retryable.
Redis is advisory; concurrent first arrivals and cache outages rely on
the downstream tenant-scoped database idempotency constraints.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger("edi-dedup")

_DEDUP_KEY_PREFIX = "edi:interchange:completed:v2:"
_DEDUP_TTL_SECONDS = 7 * 24 * 3600  # 7 days


def _dedup_key(tenant_id: str, sender_id: Optional[str], receiver_id: Optional[str], isa13: Optional[str]) -> str:
    """Bind the completed marker to a tenant and an unambiguous envelope tuple."""
    identity = [tenant_id, sender_id or "", receiver_id or "", isa13 or ""]
    encoded = json.dumps([value.strip() for value in identity], separators=(",", ":"))
    return _DEDUP_KEY_PREFIX + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _redis_client():
    """Return a sync Redis client or None if Redis is unavailable."""
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None
    try:
        import redis as redis_lib

        return redis_lib.from_url(redis_url, decode_responses=True, socket_timeout=2)
    except Exception as exc:
        logger.warning("edi_dedup_redis_unavailable error_type=%s", type(exc).__name__)
        return None


def check_interchange(
    sender_id: Optional[str],
    receiver_id: Optional[str],
    isa13: Optional[str],
    *,
    tenant_id: str,
) -> tuple[bool, Optional[str]]:
    """Read a completed marker without reserving work or claiming success."""
    if not tenant_id or not isa13 or not sender_id:
        return False, None

    client = _redis_client()
    if client is None:
        return False, None

    key = _dedup_key(tenant_id, sender_id, receiver_id, isa13)
    try:
        previous = client.get(key)
        return bool(previous), previous
    except Exception as exc:
        logger.warning("edi_dedup_redis_error error_type=%s", type(exc).__name__)
        return False, None


def record_interchange(
    sender_id: Optional[str],
    receiver_id: Optional[str],
    isa13: Optional[str],
    *,
    tenant_id: str,
    ingestion_run_id: Optional[str],
) -> None:
    """Cache completion only after the caller has committed full acceptance."""
    if not tenant_id or not isa13 or not sender_id:
        return
    client = _redis_client()
    if client is None:
        return
    try:
        client.set(
            _dedup_key(tenant_id, sender_id, receiver_id, isa13),
            ingestion_run_id or "completed",
            nx=True,
            ex=_DEDUP_TTL_SECONDS,
        )
    except Exception as exc:
        logger.warning("edi_dedup_record_failed error_type=%s", type(exc).__name__)


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
