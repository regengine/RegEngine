"""Hash-at-rest remediation tokens + short-lived case-scoped sessions.

Follows the invite-token pattern (secrets.token_urlsafe(32), sha256 hash
stored, raw token never persisted, uniform anti-enumeration errors). The
bootstrap lookup for an unauthenticated supplier goes through the
SECURITY DEFINER functions created in migration v095; every query after
that carries the explicit tenant/case predicates on top of RLS.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from shared.tenant_context import set_tenant_guc
from sqlalchemy import text

from .audit_utils import audit_event

TOKEN_TTL_HOURS_DEFAULT = 24
SESSION_TTL_MINUTES = 30
# Single-use at exchange: the emailed link can mint exactly one session.
# If the 30-minute session lapses before submit, recovery is a buyer
# reissue (POST /cases/{id}/link revokes live tokens and mints a fresh one).
MAX_EXCHANGES = 1

# Uniform anti-enumeration responses (same body for every failure mode).
TOKEN_NOT_USABLE = HTTPException(status_code=400, detail="Remediation link is not usable")
SESSION_NOT_VALID = HTTPException(status_code=401, detail="Session is not valid")


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_token(
    db,
    *,
    tenant_id: str,
    case_id: str,
    supplier_email: Optional[str],
    created_by: Optional[str],
    expires_hours: int = TOKEN_TTL_HOURS_DEFAULT,
    superseded_token_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Mint a new token for a case. Returns the raw token exactly once."""
    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            INSERT INTO fsma.remediation_tokens
                (tenant_id, case_id, token_hash, expires_at, supplier_email, created_by)
            VALUES
                (CAST(:tenant_id AS uuid), CAST(:case_id AS uuid), :token_hash,
                 :expires_at, :supplier_email, :created_by)
            RETURNING id
            """
        ),
        {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "token_hash": _hash(raw_token),
            "expires_at": expires_at,
            "supplier_email": supplier_email,
            "created_by": created_by,
        },
    ).fetchone()
    token_id = str(row[0])
    if superseded_token_id:
        db.execute(
            # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
            text(
                """
                UPDATE fsma.remediation_tokens
                SET superseded_by = CAST(:new_id AS uuid)
                WHERE id = CAST(:old_id AS uuid)
                  AND tenant_id = CAST(:tenant_id AS uuid)
                """
            ),
            {"new_id": token_id, "old_id": superseded_token_id, "tenant_id": tenant_id},
        )
    audit_event(
        db,
        tenant_id=tenant_id,
        event_type="remediation.token.issue",
        action="remediation.token.issue",
        actor_id=created_by,
        resource_type="remediation_token",
        resource_id=token_id,
        metadata={
            "case_id": case_id,
            "expires_at": expires_at.isoformat(),
            **({"reissue_of": superseded_token_id} if superseded_token_id else {}),
        },
    )
    return {"token_id": token_id, "token": raw_token, "expires_at": expires_at}


def revoke_tokens_for_case(db, *, tenant_id: str, case_id: str, actor: Optional[str]) -> List[str]:
    rows = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            UPDATE fsma.remediation_tokens
            SET revoked_at = now(), session_token_hash = NULL, session_expires_at = NULL
            WHERE tenant_id = CAST(:tenant_id AS uuid)
              AND case_id = CAST(:case_id AS uuid)
              AND revoked_at IS NULL
            RETURNING id
            """
        ),
        {"tenant_id": tenant_id, "case_id": case_id},
    ).fetchall()
    revoked = [str(r[0]) for r in rows]
    for token_id in revoked:
        audit_event(
            db,
            tenant_id=tenant_id,
            event_type="remediation.token.revoke",
            action="remediation.token.revoke",
            actor_id=actor,
            resource_type="remediation_token",
            resource_id=token_id,
            metadata={"case_id": case_id},
        )
    return revoked


def _lookup(db, fn: str, raw: str) -> Optional[Dict[str, Any]]:
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — SECURITY DEFINER function, parameterized hash
        text(
            f"""
            SELECT id, tenant_id, case_id, expires_at, revoked_at, superseded_by,
                   session_token_hash, session_expires_at, exchange_count
            FROM fsma.{fn}(:p_hash)
            """
        ),
        {"p_hash": _hash(raw)},
    ).fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "tenant_id": str(row[1]),
        "case_id": str(row[2]),
        "expires_at": row[3],
        "revoked_at": row[4],
        "superseded_by": str(row[5]) if row[5] else None,
        "session_token_hash": row[6],
        "session_expires_at": row[7],
        "exchange_count": row[8],
    }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _deny(db, token_row: Optional[Dict[str, Any]], reason: str, exc: HTTPException) -> None:
    """Uniform external response; the real reason lands in the audit log."""
    if token_row:
        # The deny fires before any tenant context exists; without the GUC
        # the RLS-guarded audit INSERT would silently fail and the denial
        # would never be recorded.
        try:
            set_tenant_guc(db, token_row["tenant_id"])
        except Exception:  # pragma: no cover — audit stays best-effort
            pass
        audit_event(
            db,
            tenant_id=token_row["tenant_id"],
            event_type="remediation.token.denied",
            action="remediation.token.deny",
            severity="warning",
            resource_type="remediation_token",
            resource_id=token_row["id"],
            metadata={"reason": reason},
        )
    raise exc


def resolve_active_token(db, raw_token: str) -> Dict[str, Any]:
    """Token-hash bootstrap: resolve, enforce usability, bind tenant context.

    tenant_id comes only from the token row (server-side value); the GUC is
    set from it and every later query still carries explicit predicates.
    """
    token_row = _lookup(db, "get_remediation_token_by_hash", raw_token)
    if not token_row:
        raise TOKEN_NOT_USABLE
    if token_row["revoked_at"] is not None:
        _deny(db, token_row, "revoked", TOKEN_NOT_USABLE)
    if token_row["expires_at"] <= _now():
        _deny(db, token_row, "expired", TOKEN_NOT_USABLE)
    set_tenant_guc(db, token_row["tenant_id"])
    return token_row


def exchange_for_session(db, token_row: Dict[str, Any]) -> Dict[str, Any]:
    """Explicit user action: mint the case-scoped 30-minute session (single-use)."""
    if token_row["exchange_count"] >= MAX_EXCHANGES:
        _deny(db, token_row, "already_exchanged", TOKEN_NOT_USABLE)
    raw_session = secrets.token_urlsafe(32)
    session_expires = _now() + timedelta(minutes=SESSION_TTL_MINUTES)
    result = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            UPDATE fsma.remediation_tokens
            SET session_token_hash = :session_hash,
                session_expires_at = :session_expires,
                exchange_count = exchange_count + 1
            WHERE id = CAST(:token_id AS uuid)
              AND tenant_id = CAST(:tenant_id AS uuid)
              AND revoked_at IS NULL
              AND exchange_count < :max_exchanges
            """
        ),
        {
            "session_hash": _hash(raw_session),
            "session_expires": session_expires,
            "token_id": token_row["id"],
            "tenant_id": token_row["tenant_id"],
            "max_exchanges": MAX_EXCHANGES,
        },
    )
    if result.rowcount != 1:
        _deny(db, token_row, "exchange_race", TOKEN_NOT_USABLE)
    audit_event(
        db,
        tenant_id=token_row["tenant_id"],
        event_type="remediation.token.exchange",
        action="remediation.token.exchange",
        resource_type="remediation_token",
        resource_id=token_row["id"],
        metadata={"case_id": token_row["case_id"], "exchange_count": token_row["exchange_count"] + 1},
    )
    return {"session_token": raw_session, "expires_at": session_expires}


def resolve_active_session(db, raw_session: str) -> Dict[str, Any]:
    """Session-hash lookup with the same fail-closed semantics."""
    token_row = _lookup(db, "get_remediation_token_by_session_hash", raw_session)
    if not token_row:
        raise SESSION_NOT_VALID
    if token_row["revoked_at"] is not None:
        _deny(db, token_row, "session_revoked", SESSION_NOT_VALID)
    if token_row["expires_at"] <= _now():
        _deny(db, token_row, "token_expired", SESSION_NOT_VALID)
    if not token_row["session_expires_at"] or token_row["session_expires_at"] <= _now():
        _deny(db, token_row, "session_expired", SESSION_NOT_VALID)
    set_tenant_guc(db, token_row["tenant_id"])
    return token_row
