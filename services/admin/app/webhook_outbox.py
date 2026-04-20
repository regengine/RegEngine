"""Durable per-tenant webhook delivery outbox (#1408).

Problem
-------
``services/admin/app/metrics.py::_notify_webhook`` previously:

  * Read a single global ``HALLUCINATION_WEBHOOK_URL`` env var — every
    tenant's approvals fanned out to the same URL.
  * Made HMAC signing optional — line 498 of the pre-fix code only
    signed "if WEBHOOK_SIGNING_AVAILABLE".
  * Swallowed every ``Exception`` with no retry, no outbox, no dead
    letter — a transient 5xx silently dropped the event.

Solution
--------
Transactional-outbox pattern, mirroring ``graph_outbox`` (#1398):

  1. **Enqueue.** When the caller has tried a direct dispatch and
     failed (non-2xx / timeout / connection error), or when the caller
     wants at-least-once delivery semantics, they call
     :func:`enqueue_webhook` with the tenant_id, event type, target
     URL (already SSRF-validated), and payload. A row lands in
     ``webhook_outbox`` with ``status='pending'``.

  2. **Drain.** :class:`WebhookOutboxDrainer` pulls pending rows whose
     ``next_attempt_at`` has arrived, signs the payload with the
     tenant's ``review_webhook_secret``, POSTs, and marks the row
     ``delivered`` on success. Transient failures bump ``attempts``
     and reschedule with exponential backoff; after ``max_attempts``
     the row flips to ``failed`` and surfaces to ops.

  3. **Reconcile.** :func:`reconcile_webhook_outbox` reports
     pending / failed counts + oldest-pending age so operators can
     plot ``webhook_delivery_lag_seconds``.

Design notes
------------
* The drainer looks up each row's tenant secret at dispatch time, not
  enqueue time — so a rotated secret takes effect on the next retry
  without a stranded backlog.
* We keep the drainer single-threaded row-at-a-time. If volume
  justifies it, swap in ``FOR UPDATE SKIP LOCKED`` in ``_claim_pending``
  — the table's ``idx_webhook_outbox_pending`` index is the right
  shape for multi-worker claims.
* Dedupe: callers who can provide a stable ``dedupe_key`` (e.g.
  ``review_id:status``) get upsert semantics so a retry does not
  double-dispatch.
* RLS: ``webhook_outbox`` has tenant-isolation policies (migration
  ``f8a9b0c1d2e3``). The drainer runs as the sysadmin DB role with
  ``regengine.is_sysadmin=true`` to read every tenant's rows, but
  dispatches with the row's own tenant secret.
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, Sequence, Tuple
from uuid import UUID

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = structlog.get_logger("webhook_outbox")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class OutboxStatus(str, enum.Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


#: Header name on outbound requests. Matches the value used elsewhere
#: in the codebase (shared/webhook_security.py::WEBHOOK_SIGNATURE_HEADERS).
SIGNATURE_HEADER = "X-RegEngine-Signature"

#: Default POST timeout — long enough to tolerate a cold start, short
#: enough that the drainer keeps moving.
DEFAULT_HTTP_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class OutboxRow:
    id: int
    tenant_id: str
    event_type: str
    target_url: str
    payload: dict
    attempts: int
    max_attempts: int
    dedupe_key: Optional[str]


# ---------------------------------------------------------------------------
# HMAC signing — kept local so callers don't need shared.webhook_security
# (and so the outbox stays decoupled from the singleton env-var secret).
# ---------------------------------------------------------------------------


def sign_payload(payload_bytes: bytes, secret: str, timestamp: Optional[int] = None) -> str:
    """Build the ``X-RegEngine-Signature`` header value.

    Format: ``t=<unix_seconds>,v1=<hex_hmac_sha256>``

    This is the same format as ``shared.webhook_security.generate_signature``
    — kept bit-compatible so any existing receiver that verifies RegEngine
    webhooks continues to work.
    """
    if not secret:
        raise ValueError("signing secret is required")
    ts = int(time.time()) if timestamp is None else int(timestamp)
    signed = f"{ts}.".encode("utf-8") + payload_bytes
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------


def enqueue_webhook(
    session: Session,
    *,
    tenant_id: str,
    event_type: str,
    target_url: str,
    payload: dict,
    dedupe_key: Optional[str] = None,
    max_attempts: int = 10,
    initial_delay_seconds: float = 0.0,
) -> None:
    """Insert a pending webhook delivery row.

    Runs in the caller's transaction — the caller is responsible for
    commit. This preserves atomicity for callers who enqueue alongside
    another database write (e.g. the review state change).

    Args:
      session: SQLAlchemy session. Must be the caller's session if they
        want the outbox row to live or die with the rest of their
        transaction.
      tenant_id: UUID string. REQUIRED — webhook delivery is always
        tenant-scoped.
      event_type: Short stable tag (e.g. ``"hallucination_resolved"``).
      target_url: Pre-validated HTTPS URL (SSRF-checked by the caller).
      payload: JSON-serializable dict. Serialized at enqueue time so the
        replay matches exactly what the original event described.
      dedupe_key: Stable idempotency key. Second enqueue with the same
        (event_type, dedupe_key) is a no-op.
      max_attempts: Hard cap before the row is marked ``failed``.
      initial_delay_seconds: Delay before the first drain attempt.
        Useful for callers that want "try once direct, fall back to
        outbox after N seconds".
    """
    if not tenant_id:
        raise ValueError("tenant_id is required")
    if not event_type or not isinstance(event_type, str):
        raise ValueError("event_type must be a non-empty string")
    if not target_url or not isinstance(target_url, str):
        raise ValueError("target_url must be a non-empty string")
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    payload_json = json.dumps(payload, default=_json_default, sort_keys=True)
    now = datetime.now(timezone.utc)
    next_attempt = now + timedelta(seconds=max(0.0, initial_delay_seconds))

    dialect = getattr(getattr(session, "bind", None), "dialect", None)
    is_postgres = dialect is not None and dialect.name == "postgresql"

    if is_postgres:
        session.execute(
            text("""
                INSERT INTO webhook_outbox (
                    tenant_id, event_type, target_url, payload,
                    dedupe_key, max_attempts,
                    status, attempts, enqueued_at, next_attempt_at
                ) VALUES (
                    :tenant_id, :event_type, :target_url, CAST(:payload AS JSONB),
                    :dedupe_key, :max_attempts,
                    'pending', 0, :now, :next_attempt
                )
                ON CONFLICT ON CONSTRAINT uq_webhook_outbox_dedupe
                DO NOTHING
            """),
            {
                "tenant_id": tenant_id,
                "event_type": event_type,
                "target_url": target_url,
                "payload": payload_json,
                "dedupe_key": dedupe_key,
                "max_attempts": max_attempts,
                "now": now,
                "next_attempt": next_attempt,
            },
        )
    else:
        # Test / dev fallback.
        session.execute(
            text("""
                INSERT INTO webhook_outbox (
                    tenant_id, event_type, target_url, payload,
                    dedupe_key, max_attempts,
                    status, attempts, enqueued_at, next_attempt_at
                ) VALUES (
                    :tenant_id, :event_type, :target_url, :payload,
                    :dedupe_key, :max_attempts,
                    'pending', 0, :now, :next_attempt
                )
            """),
            {
                "tenant_id": str(tenant_id),
                "event_type": event_type,
                "target_url": target_url,
                "payload": payload_json,
                "dedupe_key": dedupe_key,
                "max_attempts": max_attempts,
                "now": now.isoformat(),
                "next_attempt": next_attempt.isoformat(),
            },
        )

    logger.info(
        "webhook_outbox_enqueued",
        tenant_id=tenant_id,
        event_type=event_type,
        target_url=target_url,
        dedupe_key=dedupe_key,
    )


def _json_default(obj: Any) -> Any:
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"not JSON serializable: {type(obj).__name__}")


# ---------------------------------------------------------------------------
# Drain
# ---------------------------------------------------------------------------


#: Type of the "look up tenant settings by tenant_id" callback. Returns
#: ``(url, secret)`` or ``(None, None)`` if the tenant has no webhook
#: configured. Defined as a callable so the drainer can be unit-tested
#: without mounting the full tenants table / ORM.
TenantSecretLookup = Callable[[str], Tuple[Optional[str], Optional[str]]]


#: Type of the "HTTP POST" callback. Accepts ``(url, body_bytes,
#: headers)`` and must return ``(status_code, reason_or_body)``. The
#: drainer raises any exception the callback raises; status codes
#: outside 2xx are treated as non-transient vs. transient based on
#: :func:`_is_transient_status`.
HttpPoster = Callable[[str, bytes, dict], Tuple[int, str]]


def default_http_poster(url: str, body: bytes, headers: dict) -> Tuple[int, str]:
    """Default HTTP poster using ``httpx``.

    Raises on connection/timeout errors (the drainer treats raised
    exceptions as transient failures → reschedule). Returns the status
    code + truncated body on a successful HTTP round-trip regardless of
    status code.
    """
    with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
        resp = client.post(url, content=body, headers=headers)
        body_excerpt = (resp.text or "")[:500]
        return resp.status_code, body_excerpt


def _is_transient_status(status_code: int) -> bool:
    """Treat 408/429/5xx as transient. Everything else non-2xx is
    terminal (caller URL is bad, or the receiver is rejecting the
    payload on business grounds)."""
    if status_code == 408 or status_code == 429:
        return True
    if 500 <= status_code < 600:
        return True
    return False


class WebhookOutboxDrainer:
    """Claim-and-drain worker for ``webhook_outbox``.

    The drainer is single-threaded row-at-a-time by design — one bad
    row cannot poison the rest of the batch. Each row commits its own
    status transition.
    """

    #: Backoff schedule (seconds) indexed by attempt count. Attempt 0 =
    #: first retry after the initial failure. Matches ``graph_outbox``.
    _BACKOFF = (
        5.0,
        30.0,
        120.0,
        600.0,
        1800.0,
        3600.0,
        14400.0,
        43200.0,
        86400.0,
        86400.0,
    )

    def __init__(
        self,
        session: Session,
        *,
        secret_lookup: TenantSecretLookup,
        http_poster: Optional[HttpPoster] = None,
    ):
        self._session = session
        self._secret_lookup = secret_lookup
        self._http_poster = http_poster or default_http_poster

    def drain_once(self, batch_size: int = 100) -> dict:
        """Drain one batch.

        Returns ``{"claimed", "delivered", "failed", "rescheduled"}``.
        """
        claimed = self._claim_pending(batch_size)
        summary = {
            "claimed": len(claimed),
            "delivered": 0,
            "failed": 0,
            "rescheduled": 0,
        }
        for row in claimed:
            outcome = self._drain_one(row)
            summary[outcome] = summary.get(outcome, 0) + 1
        return summary

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _claim_pending(self, batch_size: int) -> Sequence[OutboxRow]:
        now = datetime.now(timezone.utc).isoformat()
        rows = self._session.execute(
            text("""
                SELECT id, tenant_id, event_type, target_url, payload,
                       attempts, max_attempts, dedupe_key
                FROM webhook_outbox
                WHERE status = 'pending'
                  AND next_attempt_at <= :now
                ORDER BY next_attempt_at ASC, id ASC
                LIMIT :limit
            """),
            {"now": now, "limit": batch_size},
        ).mappings().all()
        return [
            OutboxRow(
                id=r["id"],
                tenant_id=str(r["tenant_id"]),
                event_type=r["event_type"],
                target_url=r["target_url"],
                payload=_parse_payload(r["payload"]),
                attempts=r["attempts"] or 0,
                max_attempts=r["max_attempts"] or 10,
                dedupe_key=r["dedupe_key"],
            )
            for r in rows
        ]

    def _drain_one(self, row: OutboxRow) -> str:
        url, secret = self._secret_lookup(row.tenant_id)

        if not url or not secret:
            # Configuration drift: the tenant had a URL+secret at enqueue
            # time but has since removed one. Fail fast — we will not
            # dispatch an unsigned payload, and we will not dispatch to
            # a URL we can't validate.
            self._mark_failed(
                row, reason="tenant webhook url/secret no longer configured"
            )
            return "failed"

        payload_bytes = json.dumps(row.payload, default=_json_default, sort_keys=True).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            SIGNATURE_HEADER: sign_payload(payload_bytes, secret),
            "X-RegEngine-Event": row.event_type,
            "X-RegEngine-Tenant": row.tenant_id,
        }

        try:
            status_code, body_excerpt = self._http_poster(url, payload_bytes, headers)
        except Exception as exc:  # noqa: BLE001 — we classify below
            return self._on_failure(row, f"transport error: {exc}", transient=True)

        if 200 <= status_code < 300:
            self._mark_delivered(row, status_code=status_code)
            return "delivered"

        transient = _is_transient_status(status_code)
        reason = f"HTTP {status_code}: {body_excerpt}"
        return self._on_failure(row, reason, transient=transient, status_code=status_code)

    def _on_failure(
        self,
        row: OutboxRow,
        reason: str,
        *,
        transient: bool,
        status_code: Optional[int] = None,
    ) -> str:
        new_attempts = row.attempts + 1

        if not transient:
            # Terminal failure (4xx that isn't 408/429): no amount of
            # retry will help. Mark the row failed immediately so ops
            # can see the bad target URL.
            self._mark_failed(row, reason=reason, status_code=status_code)
            return "failed"

        if new_attempts >= row.max_attempts:
            self._mark_failed(
                row,
                reason=f"exhausted {new_attempts} attempts: {reason}",
                status_code=status_code,
            )
            return "failed"

        self._reschedule(row, reason, attempts=new_attempts, status_code=status_code)
        return "rescheduled"

    def _mark_delivered(self, row: OutboxRow, *, status_code: int) -> None:
        self._session.execute(
            text("""
                UPDATE webhook_outbox
                SET status = 'delivered',
                    delivered_at = :delivered_at,
                    last_status_code = :status_code,
                    last_error = NULL
                WHERE id = :id
            """),
            {
                "id": row.id,
                "delivered_at": datetime.now(timezone.utc).isoformat(),
                "status_code": status_code,
            },
        )
        self._session.commit()
        logger.info(
            "webhook_outbox_delivered",
            outbox_id=row.id,
            tenant_id=row.tenant_id,
            event_type=row.event_type,
            status_code=status_code,
        )

    def _mark_failed(
        self,
        row: OutboxRow,
        *,
        reason: str,
        status_code: Optional[int] = None,
    ) -> None:
        self._session.execute(
            text("""
                UPDATE webhook_outbox
                SET status = 'failed',
                    last_error = :reason,
                    last_status_code = :status_code
                WHERE id = :id
            """),
            {
                "id": row.id,
                "reason": reason[:4000],
                "status_code": status_code,
            },
        )
        self._session.commit()
        logger.warning(
            "webhook_outbox_failed",
            outbox_id=row.id,
            tenant_id=row.tenant_id,
            event_type=row.event_type,
            reason=reason[:200],
            status_code=status_code,
        )

    def _reschedule(
        self,
        row: OutboxRow,
        reason: str,
        *,
        attempts: int,
        status_code: Optional[int] = None,
    ) -> None:
        delay = self._BACKOFF[min(attempts - 1, len(self._BACKOFF) - 1)]
        next_attempt = datetime.now(timezone.utc) + timedelta(seconds=delay)
        self._session.execute(
            text("""
                UPDATE webhook_outbox
                SET attempts = :attempts,
                    last_error = :reason,
                    last_status_code = :status_code,
                    next_attempt_at = :next_attempt
                WHERE id = :id
            """),
            {
                "id": row.id,
                "attempts": attempts,
                "reason": reason[:4000],
                "status_code": status_code,
                "next_attempt": next_attempt.isoformat(),
            },
        )
        self._session.commit()
        logger.info(
            "webhook_outbox_rescheduled",
            outbox_id=row.id,
            tenant_id=row.tenant_id,
            event_type=row.event_type,
            attempts=attempts,
            delay_seconds=delay,
        )


def _parse_payload(raw: Any) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


# ---------------------------------------------------------------------------
# Reconcile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutboxHealth:
    pending_count: int
    failed_count: int
    oldest_pending_age_seconds: Optional[float]


def reconcile_webhook_outbox(session: Session) -> OutboxHealth:
    """Pending / failed counts + oldest-pending age for alerting.

    Counterpart of ``graph_outbox.reconcile_graph_outbox``. Exposed so
    a ``/metrics`` endpoint can emit ``webhook_delivery_lag_seconds``
    and ``webhook_delivery_failed_total``.
    """
    row = session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'pending')   AS pending_count,
                COUNT(*) FILTER (WHERE status = 'failed')    AS failed_count,
                MIN(enqueued_at) FILTER (WHERE status = 'pending') AS oldest_pending
            FROM webhook_outbox
        """)
    ).mappings().first()

    oldest = row["oldest_pending"] if row else None
    age_seconds: Optional[float] = None
    if oldest is not None:
        if isinstance(oldest, str):
            oldest = datetime.fromisoformat(oldest)
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - oldest).total_seconds()

    return OutboxHealth(
        pending_count=int(row["pending_count"]) if row else 0,
        failed_count=int(row["failed_count"]) if row else 0,
        oldest_pending_age_seconds=age_seconds,
    )


__all__ = [
    "OutboxStatus",
    "OutboxRow",
    "OutboxHealth",
    "WebhookOutboxDrainer",
    "enqueue_webhook",
    "reconcile_webhook_outbox",
    "sign_payload",
    "default_http_poster",
    "SIGNATURE_HEADER",
    "DEFAULT_HTTP_TIMEOUT_SECONDS",
]
