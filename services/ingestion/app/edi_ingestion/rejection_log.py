"""Durable EDI rejection evidence (#1174, #3623).

Every rejection is appended to ``fsma.rule_rejections`` in an independent
transaction before a caller receives its rejection ID. The table is tenant
isolated and INSERT-only for the runtime role. The complete record lives in
its JSONB ``reasons`` column under the fixed ``edi_rejection`` source.

The capped process-local cache remains a convenience for recent-record
inspection. Cache eviction or restart never removes the durable evidence.
Storage failures raise rather than acknowledging evidence that was lost.
"""

from __future__ import annotations

import json
import logging
import os
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger("edi-ingestion")


_EDI_REJECTION_CAP_PER_TENANT = int(os.getenv("EDI_REJECTION_CAP_PER_TENANT", "1000"))

# Tenant-scoped in-memory rejection store. Outer dict is keyed by
# ``tenant_id``; inner OrderedDict is FIFO-evicted once full.
_edi_rejection_store: dict[str, "OrderedDict[str, dict]"] = {}


class EDIRejectionUnavailable(RuntimeError):
    """Rejection evidence could not be committed; the caller must return 503."""


def _append_rejection(record: dict[str, Any]) -> None:
    """Commit evidence separately so an ingest rollback cannot remove it."""
    session = None
    try:
        from shared.database import SessionLocal
        from shared.tenant_context import set_tenant_guc
        from sqlalchemy import text

        session = SessionLocal()
        set_tenant_guc(session, record["tenant_id"])
        session.execute(
            text(
                """
                INSERT INTO fsma.rule_rejections (
                    id, tenant_id, result, reasons, source, created_at
                ) VALUES (
                    :id, :tenant_id, 'rejected', CAST(:reasons AS JSONB),
                    'edi_rejection', :created_at
                )
                """
            ),
            {
                "id": str(uuid4()),
                "tenant_id": record["tenant_id"],
                "reasons": json.dumps(record),
                "created_at": datetime.fromisoformat(record["recorded_at"]),
            },
        )
        session.commit()
    except Exception as exc:
        if session is not None:
            try:
                session.rollback()
            except Exception:
                pass
        logger.error(
            "edi_rejection_audit_failed tenant=%s error_type=%s",
            record["tenant_id"],
            type(exc).__name__,
        )
        raise EDIRejectionUnavailable("EDI rejection storage is unavailable") from None
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


def _rejection_store_for(tenant_id: str) -> "OrderedDict[str, dict]":
    return _edi_rejection_store.setdefault(tenant_id, OrderedDict())


def record_edi_rejection(
    *,
    tenant_id: str,
    transaction_set: str,
    traceability_lot_code: str | None,
    errors: list[dict[str, Any]],
    extracted: dict[str, Any] | None = None,
    partner_id: str | None = None,
    source: str | None = None,
    reason: str = "fsma_validation_failed",
    needs_review: bool = False,
    rejected_date: str | None = None,
    source_document: str | None = None,
) -> dict[str, Any]:
    """Record an EDI FSMA validation rejection.

    Returns the rejection record (dict) so the caller can surface a
    rejection_id to the client without leaking internal storage
    details. Raises EDIRejectionUnavailable if the evidence cannot be
    committed. Logs identify the rejection without including the document.
    """
    rejection_id = f"edi-rej-{uuid4().hex[:16]}"
    recorded_at = datetime.now(timezone.utc).isoformat()

    record = {
        "rejection_id": rejection_id,
        "tenant_id": tenant_id,
        "transaction_set": transaction_set,
        "traceability_lot_code": traceability_lot_code,
        "partner_id": partner_id,
        "source": source,
        "recorded_at": recorded_at,
        "errors": _scrub(errors),
        # Preserve a JSON-safe snapshot for forensic review.
        "extracted": _scrub(extracted or {}),
        "reason": reason,
        "needs_review": needs_review,
        "rejected_date": rejected_date,
        "source_document": source_document,
    }

    _append_rejection(record)

    store = _rejection_store_for(tenant_id)
    store[rejection_id] = record
    while len(store) > _EDI_REJECTION_CAP_PER_TENANT:
        store.popitem(last=False)

    logger.warning(
        "edi_fsma_rejection_recorded rejection_id=%s tenant=%s set=%s tlc=%s partner=%s errors=%d "
        "reason=%s rejected_date=%r",
        rejection_id,
        tenant_id,
        transaction_set,
        traceability_lot_code,
        partner_id,
        len(errors),
        reason,
        rejected_date,
    )

    return record


def list_edi_rejections(tenant_id: str) -> list[dict[str, Any]]:
    """Return this process's cached tenant rejections (most recent last)."""
    return list(_rejection_store_for(tenant_id).values())


def reset_edi_rejections() -> None:
    """Test helper: clear the cache; durable evidence remains unchanged."""
    _edi_rejection_store.clear()


def _scrub(value: Any) -> Any:
    """Best-effort JSON-safe scrub so the rejection record survives
    serialization. Stringifies non-serializable leaves instead of failing.
    """
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
