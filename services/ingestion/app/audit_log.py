"""
Audit Log Router.

Returns real audit data from Postgres instead of static sample rows.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.webhook_compat import _verify_api_key

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


def _get_db_session():
    try:
        from shared.database import SessionLocal

        db = SessionLocal()
    except Exception as exc:
        logger.error("audit_log_db_session_init_failed", error=str(exc))
        raise
    return db


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

    message_expr = "message" if "message" in columns else ("description" if "description" in columns else ("title" if "title" in columns else "alert_type"))

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
            """ % (message_expr, tenant_col)
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
    _: None = Depends(_verify_api_key),
) -> AuditLogResponse:
    entries: list[AuditEntry] = []
    try:
        db_session = _get_db_session()
        try:
            entries.extend(_query_admin_audit_logs(db_session, tenant_id, limit=200))
            entries.extend(_query_cte_events(db_session, tenant_id, limit=200))
            entries.extend(_query_exports(db_session, tenant_id, limit=100))
            entries.extend(_query_alert_events(db_session, tenant_id, limit=100))
        finally:
            db_session.close()
    except Exception as exc:
        logger.warning("audit_log_db_unavailable error=%s tenant_id=%s", str(exc), tenant_id)

    dedup: dict[str, AuditEntry] = {}
    for entry in entries:
        dedup[entry.id] = entry
    entries = list(dedup.values())
    entries.sort(key=lambda item: item.timestamp, reverse=True)

    if event_type:
        entries = [entry for entry in entries if entry.event_type == event_type]
    if category:
        entries = [entry for entry in entries if entry.category == category]

    total = len(entries)
    start = max((page - 1) * page_size, 0)
    paged_entries = entries[start:start + page_size]

    return AuditLogResponse(
        tenant_id=tenant_id,
        total=total,
        page=page,
        page_size=page_size,
        entries=paged_entries,
    )
