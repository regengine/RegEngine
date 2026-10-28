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
_CHAIN_LOCK_KEY_PREFIX = "partner_file_deletion:"


def _canonical_entry_payload(fields: Dict[str, Any]) -> str:
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)


def compute_entry_hash(*, prev_entry_hash: Optional[str], fields: Dict[str, Any]) -> str:
    material = _canonical_entry_payload(
        {"prev_entry_hash": prev_entry_hash, **fields}
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _lock_tenant_deletion_chain(db, *, tenant_id: str) -> None:
    """Serialize deletion-log tip updates for one tenant (multi-replica safe)."""
    db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            "SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"
        ),
        {"lock_key": f"{_CHAIN_LOCK_KEY_PREFIX}{tenant_id}"},
    )


def _latest_entry_hash(db, *, tenant_id: str) -> Optional[str]:
    """Tip of the tenant deletion chain, locked for the current transaction."""
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT entry_hash
              FROM public.partner_file_deletion_log
             WHERE tenant_id = CAST(:tenant_id AS uuid)
             ORDER BY deleted_at DESC, id DESC
             LIMIT 1
             FOR UPDATE
            """
        ),
        {"tenant_id": tenant_id},
    ).fetchone()
    return row[0] if row else None


def _list_tenant_ids(db) -> List[str]:
    """Tenant ids the runtime role can see (column-scoped SELECT on public.tenants)."""
    rows = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text("SELECT id::text FROM public.tenants ORDER BY id")
    ).fetchall()
    return [str(r[0]) for r in rows]


def _due_rows_for_tenant(
    db, *, tenant_id: str, limit: int = BATCH_LIMIT
) -> List[Dict[str, Any]]:
    """Due partner_files for one tenant. Caller must set the tenant GUC first."""
    rows = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT id, tenant_id, engagement_id, storage_bucket, storage_path,
                   content_sha256, ciphertext_sha256, byte_size, report_delivered_at,
                   delete_after
              FROM public.partner_files
             WHERE tenant_id = CAST(:tenant_id AS uuid)
               AND deleted_at IS NULL
               AND delete_after IS NOT NULL
               AND delete_after <= now()
               AND status <> 'deleted'
             ORDER BY delete_after ASC
             LIMIT :limit
             FOR UPDATE SKIP LOCKED
            """
        ),
        {"tenant_id": tenant_id, "limit": limit},
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
    """Delete storage object, append deletion_log, mark metadata deleted, audit.

    Requires object storage. Order: tenant GUC → chain advisory lock → lock tip
    → S3 delete (idempotent) → durable log/update/audit. Caller wraps in a
    savepoint so a PG error does not abort the whole batch.
    """
    from .partner_file_storage import PARTNER_UPLOADS_BUCKET
    from .remediation.audit_utils import audit_event
    from .s3_utils import delete_object, is_object_storage_configured

    if not is_object_storage_configured():
        raise RuntimeError(
            "partner file retention requires object storage; refusing to mark deleted"
        )

    tenant_id = row["tenant_id"]
    set_tenant_guc(db, tenant_id)
    _lock_tenant_deletion_chain(db, tenant_id=tenant_id)

    # Re-claim under FOR UPDATE: concurrent pass may have won already.
    claimed = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT id
              FROM public.partner_files
             WHERE id = CAST(:id AS uuid)
               AND tenant_id = CAST(:tenant_id AS uuid)
               AND deleted_at IS NULL
               AND status <> 'deleted'
             FOR UPDATE
            """
        ),
        {"id": row["id"], "tenant_id": tenant_id},
    ).fetchone()
    if claimed is None:
        return {
            "partner_file_id": row["id"],
            "skipped": True,
            "reason": "already_deleted_or_missing",
        }

    # S3 first (missing object is success on rerun), then durable DB state.
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

    return {
        "partner_file_id": row["id"],
        "deletion_log_id": log_id,
        "entry_hash": entry_hash,
        "skipped": False,
    }


def run_retention_pass(db, *, limit: int = BATCH_LIMIT) -> Dict[str, int]:
    """Process up to ``limit`` due partner files across tenants. Returns counts.

    When object storage is unconfigured the pass is a no-op: no rows are marked
    deleted and no retention audits are written.
    """
    from .s3_utils import is_object_storage_configured

    if not is_object_storage_configured():
        logger.warning("partner_file_retention_skipped_storage_unconfigured")
        return {"due": 0, "deleted": 0, "errors": 0, "skipped_unconfigured": 1}

    deleted = 0
    errors = 0
    due_total = 0
    remaining = limit

    for tenant_id in _list_tenant_ids(db):
        if remaining <= 0:
            break
        set_tenant_guc(db, tenant_id)
        rows = _due_rows_for_tenant(db, tenant_id=tenant_id, limit=remaining)
        due_total += len(rows)
        for row in rows:
            try:
                with db.begin_nested():
                    result = delete_one_due_file(db, row)
                if not result.get("skipped"):
                    deleted += 1
            except Exception as exc:  # pragma: no cover — per-row isolation
                errors += 1
                logger.exception(
                    "partner_file_retention_row_failed file=%s tenant=%s error=%s",
                    row.get("id"),
                    row.get("tenant_id"),
                    exc,
                )
            remaining -= 1

    return {"due": due_total, "deleted": deleted, "errors": errors, "skipped_unconfigured": 0}
