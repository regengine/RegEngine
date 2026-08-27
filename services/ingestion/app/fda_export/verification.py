"""
Hash verification and export reproducibility proof.

Extracted from fda_export_router.py — pure structural refactor.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Query

from ..authz import require_permission
from ..export_models import ExportVerifyResponse
from ..fda_export_service import _generate_csv
from ..subscription_gate import require_active_subscription
from .queries import FULL_EXPORT_TYPES, reconstruct_full_export_events

logger = logging.getLogger("fda-export")


async def verify_export_handler(
    export_id: str,
    tenant_id: str,
):
    """Verify that an export can be reproduced with the same hash.

    This is the core logic for the /export/verify endpoint.
    """
    db_session = None
    try:
        from shared.cte_persistence import CTEPersistence
        from shared.database import SessionLocal
        from sqlalchemy import text as sql_text

        db_session = SessionLocal()
        persistence = CTEPersistence(db_session)

        # Look up the original export
        row = db_session.execute(
            sql_text("""
                SELECT export_type, query_tlc, query_start_date, query_end_date,
                       record_count, export_hash, generated_at, include_pii,
                       query_event_type
                FROM fsma.fda_export_log
                WHERE id = :eid AND tenant_id = :tid
            """),
            {"eid": export_id, "tid": tenant_id},
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Export '{export_id}' not found")

        (
            export_type,
            original_tlc,
            start_date,
            end_date,
            original_count,
            original_hash,
            generated_at,
            include_pii,
            query_event_type,
        ) = row

        start = str(start_date) if start_date else None
        end = str(end_date) if end_date else None

        # Decide reproducibility BEFORE touching the event tables.
        if original_tlc:
            reconstruction = "single_tlc"
        elif export_type in FULL_EXPORT_TYPES:
            reconstruction = "full"
        else:
            # Recall exports can include product/location wildcard filters that are
            # not fully persisted in fda_export_log today.
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Export type '{export_type}' is not fully reproducible from stored "
                    "audit filters. Verify via package manifest and chain artifact."
                ),
            )

        # #2898: ``include_pii`` decides whether five columns and the
        # Additional-KDEs blob carry real values or ``[REDACTED]``, so an
        # audit row that never recorded it cannot determine the exported
        # bytes. Fail closed with the same 409 shape rather than emit a
        # tamper verdict against an export we simply cannot regenerate.
        if include_pii is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Export '{export_id}' predates PII-disclosure capture in the "
                    "audit log, so its bytes cannot be regenerated deterministically. "
                    "This is not a tamper finding. Verify via package manifest and "
                    "chain artifact."
                ),
            )
        include_pii = bool(include_pii)

        # Re-query and re-generate deterministically based on stored query scope.
        if reconstruction == "single_tlc":
            events = persistence.query_events_by_tlc(
                tenant_id=tenant_id,
                tlc=original_tlc,
                start_date=start,
                end_date=end,
            )
        else:
            # Same helper the exporter uses — one algorithm, one row order.
            events, _total = reconstruct_full_export_events(
                persistence,
                tenant_id=tenant_id,
                start_date=start,
                end_date=end,
                event_type=query_event_type,
            )

        csv_content = _generate_csv(events, include_pii=include_pii)
        regenerated_hash = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()

        match = regenerated_hash == original_hash

        return {
            "export_id": export_id,
            "original_hash": original_hash,
            "regenerated_hash": regenerated_hash,
            "hashes_match": match,
            "original_record_count": original_count,
            "current_record_count": len(events),
            "data_integrity": "VERIFIED" if match else "MISMATCH_DETECTED",
            "original_generated_at": generated_at.isoformat() if generated_at else None,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except (ImportError, ValueError, RuntimeError, OSError) as e:
        logger.error("export_verify_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Verification failed. Check server logs for details.")
    finally:
        if db_session:
            db_session.close()
