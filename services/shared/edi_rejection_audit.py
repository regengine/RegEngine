"""Durable storage for EDI rejections (fsma.edi_rejections).

A partner holds a ``rejection_id`` as the record of why a document was refused,
so the evidence behind it has to outlive the worker that issued it. This write
commits in its own session, independent of the request. A failure raises
EdiRejectionAuditUnavailable, and the caller must not hand out a rejection id
for a row that does not exist.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class EdiRejectionAuditUnavailable(RuntimeError):
    """An EDI rejection could not be recorded durably."""


def persist_edi_rejection(record: dict[str, Any]) -> None:
    """Insert one rejection row, scoped to the record's tenant by RLS."""
    session = None
    try:
        from shared.database import SessionLocal  # noqa: PLC0415 -- read at call time so tests can swap the session factory
        from shared.tenant_context import set_tenant_guc  # noqa: PLC0415 -- keeps module import free of database setup
        from sqlalchemy import text  # noqa: PLC0415 -- keeps module import free of database setup

        session = SessionLocal()
        set_tenant_guc(session, str(record["tenant_id"]))
        session.execute(
            # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
            text(
                """
                INSERT INTO fsma.edi_rejections (
                    rejection_id, tenant_id, transaction_set, traceability_lot_code,
                    partner_id, source, reason, needs_review, errors, extracted,
                    recorded_at
                ) VALUES (
                    :rejection_id, CAST(:tenant_id AS uuid), :transaction_set,
                    :traceability_lot_code, :partner_id, :source, :reason,
                    :needs_review, CAST(:errors AS jsonb), CAST(:extracted AS jsonb),
                    CAST(:recorded_at AS timestamptz)
                )
                """
            ),
            {
                "rejection_id": record["rejection_id"],
                "tenant_id": str(record["tenant_id"]),
                "transaction_set": record["transaction_set"],
                "traceability_lot_code": record["traceability_lot_code"],
                "partner_id": record["partner_id"],
                "source": record["source"],
                "reason": record["reason"],
                "needs_review": record["needs_review"],
                "errors": json.dumps(record["errors"], default=str),
                "extracted": json.dumps(record["extracted"], default=str),
                "recorded_at": record["recorded_at"],
            },
        )
        session.commit()
    except Exception as err:  # noqa: BLE001 -- any storage failure must become EdiRejectionAuditUnavailable
        if session is not None:
            try:
                session.rollback()
            except Exception:  # noqa: BLE001 -- cleanup must not mask the original error
                logger.debug("edi_rejection_audit_rollback_failed")
        logger.error(
            "edi_rejection_audit_failed rejection_id=%s tenant=%s error_type=%s",
            record.get("rejection_id"),
            record.get("tenant_id"),
            type(err).__name__,
        )
        raise EdiRejectionAuditUnavailable("EDI rejection storage is unavailable") from None
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:  # noqa: BLE001 -- cleanup must not mask the original error
                logger.debug("edi_rejection_audit_close_failed")
