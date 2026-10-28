"""30-day partner-file retention job (SEL-549 first-file).

Deletes objects whose ``partner_files.delete_after`` has passed, writes an
append-only ``partner_file_deletion_log`` row (hash-chained), marks the
metadata row deleted, and emits an audit event. Synthetic fixtures only
until SEL-590 clears; do not invent partner payloads.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text

from shared.tenant_context import set_tenant_guc

logger = logging.getLogger("partner_file_retention")

ACTOR = "retention_job"
REASON = "retention_30d"
BATCH_LIMIT = 100


def _canonical_entry_payload(fields: Dict[str, Any]) -> str:
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)


def compute_entry_hash(*, prev_entry_hash: Optional[str], fields: Dict[str, Any]) -> str:
    material = _canonical_entry_payload(
        {"prev_entry_hash": prev_entry_hash, **fields}
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _latest_entry_hash(db, *, tenant_id: str) -> Optional[str]:
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT entry_hash
              FROM public.partner_file_deletion_log
             WHERE tenant_id = CAST(:tenant_id AS uuid)
             ORDER BY deleted_at DESC, id DESC
             LIMIT 1
            """
        ),
        {"tenant_id": tenant_id},
    ).fetchone()
    return row[0] if row else None


def _due_rows(db, *, limit: int = BATCH_LIMIT) -> List[Dict[str, Any]]:
    rows = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT id, tenant_id, engagement_id, storage_bucket, storage_path,
                   content_sha256, ciphertext_sha256, byte_size, report_delivered_at,
                   delete_after
              FROM public.partner_files
             WHERE deleted_at IS NULL
               AND delete_after IS NOT NULL
               AND delete_after <= now()
               AND status <> 'deleted'
             ORDER BY delete_after ASC
             LIMIT :limit
            """
        ),
        {"limit": limit},
    ).fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": str(r[0]),
                "tenant_id": str(r[1]),
                "engagement_id": str(r[2]) if r[2] is not None else None,
                "storage_bucket": r[3],
                "storage_path": r[4],
                "content_sha256": r[5],
                "ciphertext_sha256": r[6],
                "byte_size": r[7],
                "report_delivered_at": r[8],
                "delete_after": r[9],
            }
        )
    return out


def delete_one_due_file(db, row: Dict[str, Any]) -> Dict[str, Any]:
    """Delete storage object, append deletion_log, mark metadata deleted, audit."""
    from .partner_file_storage import PARTNER_UPLOADS_BUCKET
    from .remediation.audit_utils import audit_event
    from .s3_utils import delete_object, is_object_storage_configured

    tenant_id = row["tenant_id"]
    set_tenant_guc(db, tenant_id)

    if is_object_storage_configured():
        delete_object(row["storage_bucket"] or PARTNER_UPLOADS_BUCKET, row["storage_path"])

    prev = _latest_entry_hash(db, tenant_id=tenant_id)
    deleted_at = datetime.now(timezone.utc)
    log_id = str(uuid4())
    fields = {
        "partner_file_id": row["id"],
        "tenant_id": tenant_id,
        "engagement_id": row["engagement_id"],
        "storage_bucket": row["storage_bucket"],
        "storage_path": row["storage_path"],
        "content_sha256": row["content_sha256"],
        "ciphertext_sha256": row["ciphertext_sha256"],
        "byte_size": row["byte_size"],
        "report_delivered_at": row["report_delivered_at"],
        "deleted_at": deleted_at.isoformat(),
        "actor": ACTOR,
        "reason": REASON,
    }
    entry_hash = compute_entry_hash(prev_entry_hash=prev, fields=fields)

    db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            INSERT INTO public.partner_file_deletion_log (
                id, partner_file_id, tenant_id, engagement_id,
                storage_bucket, storage_path, content_sha256, ciphertext_sha256,
                byte_size, report_delivered_at, deleted_at, actor, reason,
                entry_hash, prev_entry_hash
            ) VALUES (
                CAST(:id AS uuid),
                CAST(:partner_file_id AS uuid),
                CAST(:tenant_id AS uuid),
                CAST(NULLIF(:engagement_id, '') AS uuid),
                :storage_bucket,
                :storage_path,
                :content_sha256,
                :ciphertext_sha256,
                :byte_size,
                :report_delivered_at,
                :deleted_at,
                :actor,
                :reason,
                :entry_hash,
                :prev_entry_hash
            )
            """
        ),
        {
            "id": log_id,
            "partner_file_id": row["id"],
            "tenant_id": tenant_id,
            "engagement_id": row["engagement_id"],
            "storage_bucket": row["storage_bucket"],
            "storage_path": row["storage_path"],
            "content_sha256": row["content_sha256"],
            "ciphertext_sha256": row["ciphertext_sha256"],
            "byte_size": row["byte_size"],
            "report_delivered_at": row["report_delivered_at"],
            "deleted_at": deleted_at,
            "actor": ACTOR,
            "reason": REASON,
            "entry_hash": entry_hash,
            "prev_entry_hash": prev,
        },
    )

    db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            UPDATE public.partner_files
               SET status = 'deleted',
                   deleted_at = :deleted_at
             WHERE id = CAST(:id AS uuid)
               AND tenant_id = CAST(:tenant_id AS uuid)
               AND deleted_at IS NULL
            """
        ),
        {"id": row["id"], "tenant_id": tenant_id, "deleted_at": deleted_at},
    )

    audit_event(
        db,
        tenant_id=tenant_id,
        event_type="partner_file.retention_delete",
        action="partner_file.retention_delete",
        severity="info",
        actor_id=None,
        resource_type="partner_file",
        resource_id=row["id"],
        metadata={
            "actor_label": ACTOR,
            "reason": REASON,
            "storage_bucket": row["storage_bucket"],
            "storage_path": row["storage_path"],
            "content_sha256": row["content_sha256"],
            "delete_after": str(row["delete_after"]),
            "deletion_log_id": log_id,
            "entry_hash": entry_hash,
        },
    )

    return {"partner_file_id": row["id"], "deletion_log_id": log_id, "entry_hash": entry_hash}


def run_retention_pass(db, *, limit: int = BATCH_LIMIT) -> Dict[str, int]:
    """Process up to ``limit`` due partner files. Returns counts."""
    due = _due_rows(db, limit=limit)
    deleted = 0
    errors = 0
    for row in due:
        try:
            delete_one_due_file(db, row)
            deleted += 1
        except Exception as exc:  # pragma: no cover — per-row isolation
            errors += 1
            logger.exception(
                "partner_file_retention_row_failed file=%s tenant=%s error=%s",
                row.get("id"),
                row.get("tenant_id"),
                exc,
            )
    return {"due": len(due), "deleted": deleted, "errors": errors}
