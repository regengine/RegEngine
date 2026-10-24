"""EPCIS document receipts: ``fsma.epcis_document_receipts``.

One row per EPCIS document an ingest route receives, accepted or rejected,
keyed by the SHA-256 of the raw request body. ``error_summary`` is built by
:func:`summarize_error` and never carries payload content: only the exception
class, the HTTP status, and the machine error code of a dict ``detail``. Free
text details are dropped, because messages can interpolate payload values. A
failed event count may be added by the caller.

Receipts are tenant scoped. An EPCIS upload is not linked to a supplier
facility, so the supplier data quality ``epcis_failed`` metric is a tenant
wide share (see ``shared.supplier_data_quality``).

Writing a receipt is fail open: :func:`record_epcis_receipt` never raises, so
a receipt failure cannot change an ingest response.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Callable, Mapping, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

RECEIPT_ACCEPTED = "accepted"
RECEIPT_REJECTED = "rejected"
RECEIPT_STATUSES = (RECEIPT_ACCEPTED, RECEIPT_REJECTED)
# Matches the error_summary length check in alembic v136.
MAX_ERROR_SUMMARY_LENGTH = 200

# A machine error code such as ``batch_validation_failed``. The EPCIS ingest
# path sets ``detail["error"]`` from string literals only.
_SAFE_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

_INSERT_SQL = text(
    """
    INSERT INTO fsma.epcis_document_receipts (tenant_id, document_sha256, status, error_summary)
    VALUES (CAST(:tenant_id AS uuid), :document_sha256, :status, :error_summary)
    """
)

_COUNTS_SQL = text(
    """
    SELECT count(*) FILTER (WHERE status = 'rejected') AS rejected,
           count(*) AS total
      FROM fsma.epcis_document_receipts
     WHERE tenant_id = CAST(:tid AS uuid)
       AND received_at >= :since
    """
)


def document_sha256(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def _truncate(summary: str) -> str:
    return summary[:MAX_ERROR_SUMMARY_LENGTH]


def summarize_error(exc: BaseException) -> str:
    """Exception class, HTTP status and the dict detail's error code.

    ``str(exc)`` and string details are never used: either can quote the
    payload.
    """
    parts = [type(exc).__name__]
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        parts.append(str(status_code))
    detail = getattr(exc, "detail", None)
    code = detail.get("error") if isinstance(detail, Mapping) else None
    if isinstance(code, str) and _SAFE_CODE.match(code):
        parts.append(code)
    return _truncate(" ".join(parts))


def summarize_failed_events(failed: int, total: int) -> str:
    return _truncate(f"{failed} of {total} events failed")


def record_epcis_receipt(
    tenant_id: Any,
    raw_body: bytes,
    status: str,
    error_summary: Optional[str] = None,
    session_factory: Optional[Callable[[], Any]] = None,
) -> bool:
    """Insert one receipt in its own transaction. Never raises.

    Returns True when the row was committed. A tenant id that is not a UUID
    is skipped: the column is uuid and the RLS check casts the tenant GUC.
    """
    try:
        tenant = str(uuid.UUID(str(tenant_id)))
    except (ValueError, AttributeError, TypeError):
        logger.warning("epcis_receipt_skipped reason=tenant_not_uuid")
        return False
    if status not in RECEIPT_STATUSES:
        logger.warning("epcis_receipt_skipped reason=unknown_status")
        return False

    session = None
    try:
        if session_factory is None:
            from shared.database import get_db_safe  # noqa: PLC0415 (no engine setup at import)

            session_factory = get_db_safe
        session = session_factory()
        if session is None:
            logger.warning("epcis_receipt_write_failed tenant=%s error_class=NoSession", tenant)
            return False
        from shared.tenant_context import set_tenant_guc  # noqa: PLC0415

        set_tenant_guc(session, tenant)
        session.execute(
            _INSERT_SQL,
            {
                "tenant_id": tenant,
                "document_sha256": document_sha256(raw_body),
                "status": status,
                "error_summary": _truncate(error_summary) if error_summary else None,
            },
        )
        session.commit()
        return True
    except Exception as exc:  # noqa: BLE001 -- receipts must never change the ingest response
        logger.warning("epcis_receipt_write_failed tenant=%s error_class=%s", tenant, type(exc).__name__)
        if session is not None:
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
        return False
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                pass


def fetch_receipt_counts(db_session: Any, tenant_id: str, since: datetime) -> Optional[tuple[int, int]]:
    """(rejected, total) receipts for the tenant since ``since``.

    Runs in a savepoint and returns None when the table cannot be read (for
    example before alembic v136 is applied), so the caller's transaction and
    the other metrics are unaffected.
    """
    try:
        with db_session.begin_nested():
            row = db_session.execute(_COUNTS_SQL, {"tid": tenant_id, "since": since}).mappings().one()
    except Exception as exc:  # noqa: BLE001 -- one unreadable metric must not fail the summary
        logger.warning("epcis_receipt_counts_failed error_class=%s", type(exc).__name__)
        return None
    return int(row["rejected"]), int(row["total"])
