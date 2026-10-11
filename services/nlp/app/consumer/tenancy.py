"""Tenant resolution and tenant-scoped key helpers for the NLP consumer.

Split out of the original ``app/consumer.py`` module. All names are
re-exported from ``app.consumer`` for backward compatibility.
"""

from __future__ import annotations

import uuid
from typing import Optional


def _resolve_tenant_id(
    header_tenant_id: Optional[str],
    payload_tenant_id: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Determine the authoritative tenant_id for an inbound NLP message (#1176).

    Authority:

    * **Payload ``tenant_id`` field** — the ONLY trusted source. The Kafka
      message body is covered by the HMAC signature applied by
      ``services/shared/kafka_auth.sign_event``; verifying that signature
      (the consumer does so before this function is called) means the
      payload tenant_id is bound to the producer's identity.
    * **Kafka header ``X-RegEngine-Tenant-ID``** — advisory ONLY. Kafka
      headers are NOT covered by the HMAC; a network-adjacent attacker who
      captures one signed envelope can rewrite the header without
      invalidating the body signature. Preferring the header would let any
      capture+replay swap tenants — exactly the cross-tenant primitive the
      signature was designed to prevent (RE-SEC-001). The header is
      retained here only so we can defensively detect mismatches and so it
      keeps flowing through correlation/trace logs.

    Validation:

    * Must be a well-formed UUID. ``"default"``, empty string, and other
      sentinel values are rejected (they were the root cause of #1268-style
      bypasses).
    * If header AND payload both present and **disagree**, the message is
      treated as hostile (someone's trying to smuggle into another tenant)
      and rejected to the FSMA DLQ. This is defense-in-depth on top of the
      signature check — the body is authoritative regardless.

    Returns ``(resolved_tenant_id, rejection_reason)``. ``resolved`` is the
    validated UUID string when the message should be processed. When
    ``resolved`` is ``None``, ``rejection_reason`` explains why and the
    caller **must** route the message to the DLQ — the consumer **must
    not** continue processing messages without a valid tenant.
    """
    header_tid = str(header_tenant_id).strip() if header_tenant_id else None
    payload_tid = str(payload_tenant_id).strip() if payload_tenant_id else None
    # Treat empty / sentinel strings as absent so they can't satisfy the
    # "present" check further down. The header is advisory-only (unsigned),
    # so a sentinel there is not a tenant claim and must not trigger the
    # hostile-mismatch path against a valid signed payload.
    if not header_tid or header_tid.lower() in {"default", "none", "null"}:
        header_tid = None
    if not payload_tid or payload_tid.lower() in {"default", "none", "null"}:
        payload_tid = None

    # Both missing → producer didn't set tenant context. Fail-fast.
    if not header_tid and not payload_tid:
        return None, "no_tenant_id_in_header_or_payload"

    # F-NLP-8: explicit early-return when the body is missing/sentinel.
    # The body is the ONLY trusted source (see RE-SEC-001); a present
    # header cannot rescue a missing/sentinel body. Without this guard the
    # function fell through to ``uuid.UUID(None)``, raising AttributeError
    # that was caught and remapped — correct behavior, but implicit.
    # Making the rejection explicit removes a fragile control-flow edge.
    if payload_tid is None:
        return None, "no_tenant_id_in_payload"

    # Both present but disagree → hostile or broken producer. Reject.
    # Case-insensitive compare because UUIDs are case-insensitive per RFC4122.
    if (
        header_tid
        and payload_tid
        and header_tid.lower() != payload_tid.lower()
    ):
        return None, (
            f"tenant_id_mismatch header={header_tid!r} payload={payload_tid!r}"
        )

    # Authoritative tenant claim is the SIGNED body field. Kafka headers
    # are not covered by the HMAC signature applied in
    # ``services/shared/kafka_auth.sign_event``; preferring them over the
    # body would let any envelope capture+rewrite swap tenants
    # (RE-SEC-001). The header is retained for cross-trace correlation
    # only; the mismatch check above is defense-in-depth.
    resolved = payload_tid

    # Must be a valid UUID — rejects the "default" sentinel from #1268 and
    # any other non-UUID string that somehow made it past the producer.
    try:
        uuid.UUID(resolved)  # type: ignore[arg-type]
    except (ValueError, AttributeError, TypeError):
        return None, f"invalid_tenant_id_format value={resolved!r}"

    return resolved, None


def _kafka_key_for(tenant_id: Optional[str], doc_id: str) -> str:
    """Build the tenant-scoped Kafka partition key (#1122).

    Format: ``"{tenant_id}:{doc_id}"``. This is used for every
    outbound producer.send() in the NLP consumer so that two
    different tenants publishing documents with identical doc_ids
    cannot:

    * Interleave on the same partition (downstream consumers see
      cross-tenant events ordered by offset with no way to tell
      them apart by key alone).
    * Share a retry-count bucket in :data:`_retry_counts` — that
      cache key used to be the raw doc_id, which meant tenant A's
      3rd retry DLQ'd tenant B's first attempt.

    If ``tenant_id`` is falsy (which should never happen at this
    point — the consumer loop DLQ'd well before this call), we
    still emit a safe sentinel that is GUARANTEED not to match a
    legitimate key, so the message hits the DLQ deterministically
    instead of silently joining tenant A's partition.
    """
    safe_tenant = str(tenant_id).strip() if tenant_id else "NO_TENANT"
    return f"{safe_tenant}:{doc_id}"


def _retry_key_for(tenant_id: Optional[str], doc_id: str) -> str:
    """Build the tenant-scoped ``_retry_counts`` cache key (#1122).

    Before this fix the cache was keyed by raw ``doc_id``, which meant
    that two tenants who happened to emit messages carrying the same
    ``doc_id`` shared a retry bucket. Tenant B's first processing
    attempt could trigger tenant A's DLQ threshold and vice versa.
    This helper centralizes the format so every read and write stays
    in sync — a future refactor that changes the key scheme only
    needs to touch this one function.
    """
    safe_tenant = str(tenant_id).strip() if tenant_id else "NO_TENANT"
    return f"{safe_tenant}:{doc_id}"
