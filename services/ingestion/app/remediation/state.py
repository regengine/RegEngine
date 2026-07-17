"""Remediation-case lifecycle: PRD state machine with a single guarded UPDATE.

The DB CHECK constrains the value set; transition legality lives here.
Coarse states are mirrored into fsma.exception_cases so existing buyer
dashboards stay truthful (awaiting_supplier finally gets a real user).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import text

from .audit_utils import audit_event

logger = logging.getLogger("remediation.state")

ALLOWED_TRANSITIONS = {
    "detected": {"auto_resolution_attempted", "supplier_action_required"},
    "auto_resolution_attempted": {"supplier_action_required", "released"},
    "supplier_action_required": {"notification_ready", "escalated"},
    "notification_ready": {"awaiting_supplier"},
    "awaiting_supplier": {"correction_submitted", "escalated", "notification_ready"},
    "correction_submitted": {"revalidating"},
    "revalidating": {"released", "buyer_review"},
    "buyer_review": {"notification_ready", "released", "escalated"},
    "released": set(),
    "escalated": {"notification_ready"},
}

# remediation status → exception_cases.status mirror
_EXCEPTION_MIRROR = {
    "notification_ready": "awaiting_supplier",
    "awaiting_supplier": "awaiting_supplier",
    "correction_submitted": "awaiting_supplier",
    "revalidating": "awaiting_supplier",
    "buyer_review": "in_review",
    "escalated": "in_review",
}


def transition(
    db,
    *,
    tenant_id: str,
    case_id: str,
    to_status: str,
    expected_from: str,
    actor: Optional[str] = None,
) -> None:
    """Move a remediation case between states with optimistic concurrency."""
    if to_status not in ALLOWED_TRANSITIONS.get(expected_from, set()):
        raise HTTPException(
            status_code=409,
            detail=f"E_ILLEGAL_TRANSITION: {expected_from} -> {to_status}",
        )
    result = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            UPDATE fsma.remediation_cases
            SET status = :to_status, updated_at = now()
            WHERE id = CAST(:case_id AS uuid)
              AND tenant_id = CAST(:tenant_id AS uuid)
              AND status = :expected_from
            """
        ),
        {
            "to_status": to_status,
            "case_id": case_id,
            "tenant_id": tenant_id,
            "expected_from": expected_from,
        },
    )
    if result.rowcount != 1:
        raise HTTPException(
            status_code=409,
            detail=f"E_STALE_TRANSITION: case not in '{expected_from}'",
        )
    audit_event(
        db,
        tenant_id=tenant_id,
        event_type="remediation.case.transition",
        action="remediation.case.transition",
        resource_type="remediation_case",
        resource_id=case_id,
        metadata={"from": expected_from, "to": to_status, "actor": actor},
    )
    _mirror_exception(db, tenant_id=tenant_id, case_id=case_id, to_status=to_status)


def _mirror_exception(db, *, tenant_id: str, case_id: str, to_status: str) -> None:
    mirrored = _EXCEPTION_MIRROR.get(to_status)
    if not mirrored:
        return
    try:
        db.execute(
            # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
            text(
                """
                UPDATE fsma.exception_cases
                SET status = :mirrored, updated_at = now()
                WHERE tenant_id = CAST(:tenant_id AS uuid)
                  AND case_id = (
                      SELECT exception_case_id FROM fsma.remediation_cases
                      WHERE id = CAST(:case_id AS uuid)
                        AND tenant_id = CAST(:tenant_id AS uuid)
                  )
                  AND status NOT IN ('resolved', 'waived')
                """
            ),
            {"mirrored": mirrored, "tenant_id": tenant_id, "case_id": case_id},
        )
    except Exception as exc:  # pragma: no cover — mirror is best-effort
        logger.warning("exception_mirror_failed case=%s error=%s", case_id, exc)
