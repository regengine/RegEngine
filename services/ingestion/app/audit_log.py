"""
Audit Log Router.

Returns real audit data from Postgres instead of static sample rows.

NOTE: The audit_logs table lives in the *admin* database while CTE/export/alert
tables live in the *ingestion* database.  We maintain two session factories so
queries hit the correct database.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from shared.database import get_db_safe
from shared.tenant_context import TenantContext
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from .tenant_validation import validate_tenant_id
from .webhook_compat import require_tenant_context

logger = logging.getLogger("audit-log")

router = APIRouter(prefix="/api/v1/audit-log", tags=["Audit Log"])


class AuditEntry(BaseModel):
    id: str
    timestamp: str
    event_type: str
    category: str
    actor: str
    action: str
    resource: str
    details: dict = Field(default_factory=dict)
    ip_address: str = ""
    hash: str = ""


class AuditLogResponse(BaseModel):
    tenant_id: str
    total: int
    page: int
    page_size: int
    entries: list[AuditEntry]
    # #2864: ``total`` used to be the size of the merged, already-truncated
    # window, so a client that paged to the end was told it held the tenant's
    # complete FSMA audit trail. ``total`` is now a real row count and
    # ``truncated`` says whether this endpoint can actually reach all of it.
    truncated: bool = False


# Per-source ceiling on how many rows the four-way merge will pull. Correct
# pagination over a merge of N time-ordered sources needs the top
# ``page * page_size`` rows from *each* source; this bounds how far that can
# be pushed before the cost stops being reasonable. Beyond it the response is
# flagged ``truncated`` rather than quietly serving a wrong page.
_MAX_MERGE_WINDOW = 2000


# Lazy-init admin DB session factory — only created when first needed.
_admin_session_factory = None


_admin_url_warned = False


def _get_admin_db_session():
    """Return a session connected to the admin database (audit_logs table).

    Uses ADMIN_DATABASE_URL env var.  Returns None if not configured,
    allowing the caller to skip the admin audit query gracefully.
    """
    global _admin_session_factory, _admin_url_warned
    admin_url = os.getenv("ADMIN_DATABASE_URL")
    if not admin_url:
        if not _admin_url_warned:
            logger.warning(
                "ADMIN_DATABASE_URL is not set — admin audit logs will be incomplete. "
                "Set this env var to enable full audit trail."
            )
            _admin_url_warned = True
        return None
    if _admin_session_factory is None:
        # Convert psycopg driver URL to standard psycopg2 if needed
        conn_url = admin_url.replace("postgresql+psycopg://", "postgresql://")
        _admin_session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=create_engine(conn_url, pool_size=3, max_overflow=5, pool_pre_ping=True),
        )
    try:
        return _admin_session_factory()
    except Exception as exc:
        logger.error("audit_log_admin_db_session_failed error=%s", str(exc))
        return None


def _to_iso(value: Any) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _normalize_audit_event_type(event_type: str, event_category: str, action: str) -> str:
    et = (event_type or "").lower()
    ec = (event_category or "").lower()
    act = (action or "").lower()

    if "login" in et or ec == "authentication":
        return "user_login"
    if "export" in et or "export" in act:
        return "export"
    if "alert" in et:
        return "alert"
    if "compliance" in et or "compliance" in ec:
        return "compliance_change"
    if "cte" in et:
        return "cte_recorded"
    return "api_call"


def _normalize_category(event_type: str, event_category: str) -> str:
    normalized = _normalize_audit_event_type(event_type, event_category, "")
    if normalized == "user_login":
        return "auth"
    if normalized in {"cte_recorded", "export"}:
        return "data"
    if normalized in {"alert", "compliance_change"}:
        return "compliance"
    return "system"


def _table_exists(db_session, table_name: str, schema: str = "public") -> bool:
    row = db_session.execute(
        text("SELECT to_regclass(:table_ref)"),
        {"table_ref": f"{schema}.{table_name}"},
    ).fetchone()
    return bool(row and row[0])


def _query_admin_audit_logs(db_session, tenant_id: str, limit: int) -> list[AuditEntry]:
    if not _table_exists(db_session, "audit_logs", "public"):
        return []

    rows = db_session.execute(
        text(
            """
            SELECT
                id::text AS id,
                timestamp,
                event_type,
                event_category,
                COALESCE(actor_email, 'system') AS actor,
                action,
                COALESCE(resource_type || ':' || resource_id, resource_type, action) AS resource,
                COALESCE(metadata, '{}'::jsonb) AS details,
                COALESCE(actor_ip, '') AS ip_address,
                COALESCE(integrity_hash, '') AS integrity_hash
            FROM audit_logs
            WHERE tenant_id = :tenant_id
            ORDER BY timestamp DESC
            LIMIT :limit
            """
        ),
        {"tenant_id": tenant_id, "limit": limit},
    ).fetchall()

    entries: list[AuditEntry] = []
    for row in rows:
        normalized_type = _normalize_audit_event_type(row.event_type, row.event_category, row.action)
        entries.append(
            AuditEntry(
                id=row.id,
                timestamp=_to_iso(row.timestamp),
                event_type=normalized_type,
                category=_normalize_category(row.event_type, row.event_category),
                actor=row.actor,
                action=row.action,
                resource=row.resource or "audit",
                details=row.details if isinstance(row.details, dict) else {},
                ip_address=row.ip_address or "",
                hash=row.integrity_hash or "",
            )
        )

    return entries


def _query_cte_events(db_session, tenant_id: str, limit: int) -> list[AuditEntry]:
    rows = db_session.execute(
        text(
            """
            SELECT
                id::text AS id,
                event_timestamp,
                event_type,
                source,
                traceability_lot_code,
                product_description,
                quantity,
                sha256_hash
            FROM fsma.cte_events
            WHERE tenant_id = :tenant_id
            ORDER BY event_timestamp DESC
            LIMIT :limit
            """
        ),
        {"tenant_id": tenant_id, "limit": limit},
    ).fetchall()

    entries: list[AuditEntry] = []
    for row in rows:
        entries.append(
            AuditEntry(
                id=f"cte-{row.id}",
                timestamp=_to_iso(row.event_timestamp),
                event_type="cte_recorded",
                category="data",
                actor=row.source or "system",
                action=f"Recorded {row.event_type} CTE",
                resource=f"TLC {row.traceability_lot_code}",
                details={
                    "cte_type": row.event_type,
                    "product": row.product_description,
                    "quantity": row.quantity,
                },
                hash=row.sha256_hash or "",
            )
        )
    return entries


def _query_exports(db_session, tenant_id: str, limit: int) -> list[AuditEntry]:
    rows = db_session.execute(
        text(
            """
            SELECT
                id::text AS id,
                generated_at,
                generated_by,
                export_type,
                record_count,
                export_hash
            FROM fsma.fda_export_log
            WHERE tenant_id = :tenant_id
            ORDER BY generated_at DESC
            LIMIT :limit
            """
        ),
        {"tenant_id": tenant_id, "limit": limit},
    ).fetchall()

    entries: list[AuditEntry] = []
    for row in rows:
        entries.append(
            AuditEntry(
                id=f"export-{row.id}",
                timestamp=_to_iso(row.generated_at),
                event_type="export",
                category="data",
                actor=row.generated_by or "system",
                action="Generated FDA export",
                resource=f"Export: {row.export_type or 'fda_spreadsheet'}",
                details={"records": row.record_count},
                hash=row.export_hash or "",
            )
        )
    return entries


def _query_alert_events(db_session, tenant_id: str, limit: int) -> list[AuditEntry]:
    if not _table_exists(db_session, "compliance_alerts", "fsma"):
        return []

    columns = {
        row[0]
        for row in db_session.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'fsma' AND table_name = 'compliance_alerts'
                """
            )
        ).fetchall()
    }
    tenant_col = "tenant_id" if "tenant_id" in columns else ("org_id" if "org_id" in columns else None)
    if tenant_col is None:
        return []

    message_expr = (
        "message"
        if "message" in columns
        else ("description" if "description" in columns else ("title" if "title" in columns else "alert_type"))
    )

    rows = db_session.execute(
        text(
            """
            SELECT
                id::text AS id,
                created_at,
                severity,
                alert_type,
                COALESCE(%s, alert_type) AS message
            FROM fsma.compliance_alerts
            WHERE %s = :tenant_id
            ORDER BY created_at DESC
            LIMIT :limit
            """
            % (message_expr, tenant_col)
        ),
        {"tenant_id": tenant_id, "limit": limit},
    ).fetchall()

    entries: list[AuditEntry] = []
    for row in rows:
        entries.append(
            AuditEntry(
                id=f"alert-{row.id}",
                timestamp=_to_iso(row.created_at),
                event_type="alert",
                category="compliance",
                actor="system",
                action=f"Compliance alert ({row.alert_type})",
                resource=f"Alert: {row.alert_type}",
                details={"message": row.message, "severity": row.severity},
                hash="",
            )
        )
    return entries


def _safe_count(counter, db_session, tenant_id: str, source: str) -> int | None:
    """Count one audit source, returning ``None`` when it cannot be counted.

    A failed COUNT must never discard rows we already fetched, and must never
    be reported as a confirmed zero — "we could not look" and "there is
    nothing there" are very different claims to make about an audit trail.
    """
    try:
        return counter(db_session, tenant_id)
    except Exception as exc:
        logger.warning(
            "audit_log_count_unavailable source=%s error=%s tenant_id=%s",
            source,
            str(exc),
            tenant_id,
        )
        return None


def _scalar_count(db_session, sql: str, params: dict) -> int:
    row = db_session.execute(text(sql), params).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _count_admin_audit_logs(db_session, tenant_id: str) -> int:
    """Real row count behind :func:`_query_admin_audit_logs`."""
    if not _table_exists(db_session, "audit_logs", "public"):
        return 0
    return _scalar_count(
        db_session,
        "SELECT COUNT(*) FROM audit_logs WHERE tenant_id = :tenant_id",
        {"tenant_id": tenant_id},
    )


def _count_cte_events(db_session, tenant_id: str) -> int:
    """Real row count behind :func:`_query_cte_events`."""
    return _scalar_count(
        db_session,
        "SELECT COUNT(*) FROM fsma.cte_events WHERE tenant_id = :tenant_id",
        {"tenant_id": tenant_id},
    )


def _count_exports(db_session, tenant_id: str) -> int:
    """Real row count behind :func:`_query_exports`."""
    return _scalar_count(
        db_session,
        "SELECT COUNT(*) FROM fsma.fda_export_log WHERE tenant_id = :tenant_id",
        {"tenant_id": tenant_id},
    )


def _count_alert_events(db_session, tenant_id: str) -> int:
    """Real row count behind :func:`_query_alert_events`.

    Mirrors that helper's schema probing: the alerts table names its tenant
    column ``tenant_id`` or ``org_id`` depending on migration vintage.
    """
    if not _table_exists(db_session, "compliance_alerts", "fsma"):
        return 0

    columns = {
        row[0]
        for row in db_session.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'fsma' AND table_name = 'compliance_alerts'
                """
            )
        ).fetchall()
    }
    tenant_col = "tenant_id" if "tenant_id" in columns else ("org_id" if "org_id" in columns else None)
    if tenant_col is None:
        return 0

    # ``tenant_col`` is one of two literals chosen above, never caller input.
    return _scalar_count(
        db_session,
        "SELECT COUNT(*) FROM fsma.compliance_alerts WHERE %s = :tenant_id" % tenant_col,
        {"tenant_id": tenant_id},
    )


@router.get(
    "/{tenant_id}",
    response_model=AuditLogResponse,
    summary="Get audit log",
)
async def get_audit_log(
    tenant_id: str,
    page: int = 1,
    page_size: int = 20,
    event_type: str | None = None,
    category: str | None = None,
    ctx: TenantContext = Depends(require_tenant_context),
) -> AuditLogResponse:
    tenant_id = ctx.tenant_id
    validate_tenant_id(tenant_id)
    entries: list[AuditEntry] = []

    # #2864: the four sources used to be pulled with fixed caps
    # (200/200/100/100), so the merge could never yield more than 600 rows and
    # any page past that was empty. Merging the top ``K`` rows of each
    # time-ordered source yields exactly the true top ``K`` of the full merge,
    # so sizing the per-source window to cover the requested page makes that
    # page correct rather than approximate.
    requested = max(page, 1) * max(page_size, 1)
    window = min(requested, _MAX_MERGE_WINDOW)
    # True row counts, independent of the window. ``None`` means the source
    # was unreachable — distinct from a source that genuinely holds 0 rows,
    # so an outage is never reported as a complete-but-empty audit trail.
    source_totals: list[int | None] = []

    # Query admin audit_logs from the admin database
    try:
        admin_session = _get_admin_db_session()
        if admin_session is not None:
            try:
                entries.extend(_query_admin_audit_logs(admin_session, tenant_id, limit=window))
                source_totals.append(
                    _safe_count(_count_admin_audit_logs, admin_session, tenant_id, "audit_logs")
                )
            finally:
                admin_session.close()
        else:
            # ADMIN_DATABASE_URL unset — the admin slice of the trail is
            # simply not visible from here, which the helper already warns
            # about. Treat it as unknown, not as zero.
            source_totals.append(None)
    except Exception as exc:
        logger.warning("audit_log_admin_db_unavailable error=%s tenant_id=%s", str(exc), tenant_id)
        source_totals.append(None)

    # Query CTE events, exports, and alerts from the ingestion database
    try:
        db_session = get_db_safe()
        try:
            entries.extend(_query_cte_events(db_session, tenant_id, limit=window))
            entries.extend(_query_exports(db_session, tenant_id, limit=window))
            entries.extend(_query_alert_events(db_session, tenant_id, limit=window))
            source_totals.append(
                _safe_count(_count_cte_events, db_session, tenant_id, "cte_events")
            )
            source_totals.append(
                _safe_count(_count_exports, db_session, tenant_id, "fda_export_log")
            )
            source_totals.append(
                _safe_count(_count_alert_events, db_session, tenant_id, "compliance_alerts")
            )
        finally:
            db_session.close()
    except Exception as exc:
        logger.warning("audit_log_db_unavailable error=%s tenant_id=%s", str(exc), tenant_id)
        source_totals.extend([None, None, None])

    dedup: dict[str, AuditEntry] = {}
    for entry in entries:
        dedup[entry.id] = entry
    entries = list(dedup.values())
    entries.sort(key=lambda item: item.timestamp, reverse=True)

    # Rows actually pulled into the merge, before the Python-side filters.
    fetched = len(entries)
    # Per-source ids are namespaced (``cte-``/``export-``/``alert-``/admin
    # UUID), so the counts sum without double-counting the dedup above.
    known_totals = [count for count in source_totals if count is not None]
    any_source_unavailable = len(known_totals) != len(source_totals)
    # A total below the number of rows we just returned is never right, so an
    # uncountable source degrades to "at least what you can see" rather than
    # to a bogus zero.
    total_rows = max(sum(known_totals), fetched)

    if event_type:
        entries = [entry for entry in entries if entry.event_type == event_type]
    if category:
        entries = [entry for entry in entries if entry.category == category]

    # True whenever this response cannot account for every audit row: either a
    # source was unreachable, or the merge window did not reach the end of one.
    truncated = any_source_unavailable or total_rows > fetched

    if event_type or category:
        # The filters key off normalized values computed in Python, so they
        # cannot be pushed into the COUNT queries. Report what was actually
        # matched; ``truncated`` carries the caveat that rows outside the
        # merge window were never examined against the filter.
        total = len(entries)
    else:
        total = total_rows

    start = max((page - 1) * page_size, 0)
    paged_entries = entries[start : start + page_size]

    return AuditLogResponse(
        tenant_id=tenant_id,
        total=total,
        page=page,
        page_size=page_size,
        entries=paged_entries,
        truncated=truncated,
    )
