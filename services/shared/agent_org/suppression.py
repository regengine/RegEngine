"""Email suppression list, enforced as a hard gate on outbound sends.

Backs ``agent_org.email_suppressions`` (v121 migration). The only
authorization/query surface is :func:`is_suppressed`; writes go through
:func:`record_suppression`. Both normalize the email address the same
way (:func:`_normalize_email`), matching on read what was stored on
write.

Callers must already have the tenant GUC set (``set_tenant_guc``) before
calling either function here — the explicit ``tenant_id`` predicate below
is a belt-and-suspenders addition on top of RLS, matching
``remediation.delivery``'s own query style (every statement carries an
explicit tenant predicate even though the table is FORCE RLS).
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text

#: The only reasons a suppression row may carry (mirrors the migration's
#: CHECK constraint on ``agent_org.email_suppressions.reason``).
SUPPRESSION_REASONS = frozenset({"bounce", "complaint", "manual_unsubscribe"})


def _normalize_email(email_address: str) -> str:
    return (email_address or "").strip().lower()


def is_suppressed(session: Any, *, tenant_id: str, email_address: str) -> bool:
    """True iff ``email_address`` has an active suppression row for ``tenant_id``.

    Caller must already have the tenant GUC set (``set_tenant_guc``) —
    this function adds ``tenant_id`` as a belt-and-suspenders predicate
    on top of RLS, matching ``remediation.delivery``'s own query style.
    An empty/falsy ``email_address`` is never suppressed (nothing to
    match) and short-circuits without a query.
    """
    normalized = _normalize_email(email_address)
    if not normalized:
        return False

    row = session.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT 1
            FROM agent_org.email_suppressions
            WHERE tenant_id = CAST(:tenant_id AS uuid)
              AND email_address = :email_address
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "email_address": normalized},
    ).fetchone()
    return row is not None


def record_suppression(
    session: Any,
    *,
    tenant_id: str,
    email_address: str,
    reason: str,
    source: str,
) -> None:
    """Insert one suppression row.

    No uniqueness constraint on ``(tenant_id, email_address)``: an
    address can be suppressed more than once for different reasons and
    every row is kept for audit — ``is_suppressed`` only cares whether
    *any* row matches. Raises ``ValueError`` for a ``reason`` outside
    :data:`SUPPRESSION_REASONS` before any SQL runs (the DB-side CHECK
    constraint is the backstop, not the primary signal).
    """
    if reason not in SUPPRESSION_REASONS:
        raise ValueError(f"Unknown suppression reason: {reason!r}; must be one of {sorted(SUPPRESSION_REASONS)}")

    normalized = _normalize_email(email_address)
    if not normalized:
        raise ValueError("email_address must be non-empty")

    session.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            INSERT INTO agent_org.email_suppressions
                (tenant_id, email_address, reason, source)
            VALUES
                (CAST(:tenant_id AS uuid), :email_address, :reason, :source)
            """
        ),
        {
            "tenant_id": tenant_id,
            "email_address": normalized,
            "reason": reason,
            "source": source,
        },
    )
