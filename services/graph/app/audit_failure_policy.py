"""KDE_READ audit-log failure policy (RE-SEC-006).

When the primary audit-log backend is unavailable, FSMA 204 / NIST AU-2
require we either:

    (a) fail closed -- return 503 to the caller, denying access until the
        audit backend is reachable again. Strictest interpretation; appropriate
        for regulated tenants where read-without-log is unacceptable.

    (b) buffer -- write the audit event to a durable secondary store
        (currently: a Postgres ``audit_log_buffer`` table; could later be
        Kafka) and return success to the caller. A reconciliation job replays
        buffered events to the primary backend once available.

Configured via env var ``KDE_READ_AUDIT_FAILURE_POLICY`` (``"buffered"``
default, or ``"fail_closed"``).

Use this from EVERY KDE_READ audit emission site::

    try:
        get_audit_log().log(...)
    except Exception as exc:
        handle_audit_failure(
            tenant_id=tenant_id,
            actor=actor,
            event_type="kde_read",
            payload={...},
            error=exc,
        )
        # If policy is fail_closed, handle_audit_failure raises HTTPException(503).
        # If policy is buffered, handle_audit_failure persists to the buffer
        # table and returns; caller continues.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import HTTPException

logger = structlog.get_logger("audit_failure_policy")

POLICY_ENV = "KDE_READ_AUDIT_FAILURE_POLICY"
POLICY_BUFFERED = "buffered"
POLICY_FAIL_CLOSED = "fail_closed"
DEFAULT_POLICY = POLICY_BUFFERED


def _current_policy() -> str:
    """Return the currently configured failure policy.

    Reads the env var on every call so operators can change behavior
    without a restart (e.g. via a config-reloading sidecar). Invalid
    values fall back to the safe default and emit a warning.
    """
    raw = os.getenv(POLICY_ENV, DEFAULT_POLICY).strip().lower()
    if raw not in (POLICY_BUFFERED, POLICY_FAIL_CLOSED):
        logger.warning(
            "invalid_audit_failure_policy",
            value=raw,
            defaulting_to=DEFAULT_POLICY,
        )
        return DEFAULT_POLICY
    return raw


def handle_audit_failure(
    *,
    tenant_id: str,
    actor: str,
    event_type: str,
    payload: dict[str, Any],
    error: Exception,
) -> None:
    """Handle a primary-audit-log write failure.

    Per the configured policy, either (a) raises ``HTTPException(503)`` to
    fail the caller's request, or (b) writes the event to the durable buffer
    table and returns. ALWAYS logs the failure for observability.

    If the policy is buffered AND the buffer write also fails, raises
    ``HTTPException(503)``. Double-failure is the only condition under which
    buffered policy denies the request -- otherwise the caller continues.
    """
    policy = _current_policy()
    logger.error(
        "kde_read_audit_primary_failed",
        tenant_id=tenant_id,
        actor=actor,
        event_type=event_type,
        policy=policy,
        error=str(error),
        error_type=type(error).__name__,
    )

    if policy == POLICY_FAIL_CLOSED:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "audit_log_unavailable",
                "message": ("Audit logging is unavailable; request denied per audit policy."),
            },
        )

    # POLICY_BUFFERED: persist to the durable buffer.
    try:
        _persist_audit_buffer(
            tenant_id=tenant_id,
            actor=actor,
            event_type=event_type,
            payload=payload,
            originally_failed_at=datetime.now(timezone.utc),
            primary_error=str(error),
        )
    except Exception as buffer_exc:
        # Both primary AND buffer failed -- this is a hard fail. Always raise.
        logger.error(
            "kde_read_audit_buffer_also_failed",
            tenant_id=tenant_id,
            actor=actor,
            event_type=event_type,
            primary_error=str(error),
            buffer_error=str(buffer_exc),
            buffer_error_type=type(buffer_exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "audit_log_double_failure",
                "message": "Audit logging is unavailable; request denied.",
            },
        ) from buffer_exc


def _persist_audit_buffer(
    *,
    tenant_id: str,
    actor: str,
    event_type: str,
    payload: dict[str, Any],
    originally_failed_at: datetime,
    primary_error: str,
) -> None:
    """Write to the ``audit_log_buffer`` table.

    Schema (created in alembic migration v079)::

        CREATE TABLE audit_log_buffer (
            id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id            uuid NOT NULL,
            actor                text NOT NULL,
            event_type           text NOT NULL,
            payload              jsonb NOT NULL,
            originally_failed_at timestamptz NOT NULL,
            primary_error        text,
            replayed_at          timestamptz NULL,
            created_at           timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_audit_log_buffer_unreplayed
            ON audit_log_buffer (created_at)
            WHERE replayed_at IS NULL;

    The buffer write uses a separate session from the primary audit log so a
    failure mode that affects the primary path does not cascade. If the
    buffer table does not exist (migration not yet applied), this raises;
    the caller (``handle_audit_failure``) treats that as a double-failure
    and returns 503.
    """
    # Imported lazily so importing this module does not require a DB.
    from shared.database import get_db_safe  # type: ignore
    from sqlalchemy import text

    session = get_db_safe()
    if session is None:
        raise RuntimeError("audit_log_buffer: no DB session available")

    try:
        session.execute(
            text(
                """
                INSERT INTO audit_log_buffer (
                    tenant_id, actor, event_type, payload,
                    originally_failed_at, primary_error
                ) VALUES (
                    :tenant_id, :actor, :event_type, CAST(:payload AS jsonb),
                    :originally_failed_at, :primary_error
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "actor": actor,
                "event_type": event_type,
                "payload": json.dumps(payload, default=str),
                "originally_failed_at": originally_failed_at,
                "primary_error": primary_error,
            },
        )
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:  # pragma: no cover - rollback best-effort
            pass
        raise
    finally:
        try:
            session.close()
        except Exception:  # pragma: no cover - close best-effort
            pass
