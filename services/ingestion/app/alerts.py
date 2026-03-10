"""
Alerts Router.

Reads real tenant alerts from Postgres instead of static demo payloads.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.webhook_compat import _verify_api_key

logger = logging.getLogger("alerts")

router = APIRouter(prefix="/api/v1/alerts", tags=["Alerts & Notifications"])


class AlertRule(BaseModel):
    id: str
    name: str
    category: str
    severity: str
    description: str
    enabled: bool = True
    notify_email: bool = True
    notify_webhook: bool = False
    threshold: Optional[str] = None


class Alert(BaseModel):
    id: str
    rule_id: str
    rule_name: str
    severity: str
    category: str
    title: str
    message: str
    triggered_at: str
    acknowledged: bool = False
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class AlertsResponse(BaseModel):
    tenant_id: str
    total: int
    unacknowledged: int
    alerts: list[Alert]


DEFAULT_RULES: list[AlertRule] = [
    AlertRule(
        id="kde-missing",
        name="Missing Key Data Elements",
        category="compliance",
        severity="warning",
        description="Triggered when a CTE event is missing required KDEs per 21 CFR 1.1325-1.1350",
    ),
    AlertRule(
        id="cte-overdue",
        name="Overdue CTE Entry",
        category="compliance",
        severity="warning",
        description="Triggered when expected CTE entries are not recorded within the configured time window",
        threshold="4 hours",
    ),
    AlertRule(
        id="temp-excursion",
        name="Temperature Excursion",
        category="temperature",
        severity="critical",
        description="Triggered when IoT temperature data exceeds safe thresholds for the product type",
        threshold="5°C",
    ),
    AlertRule(
        id="chain-integrity",
        name="Hash Chain Break",
        category="chain",
        severity="critical",
        description="Triggered when hash-chain verification detects a mismatch",
    ),
    AlertRule(
        id="portal-expiry",
        name="Supplier Portal Link Expiring",
        category="deadline",
        severity="info",
        description="Triggered before a supplier portal link expires",
        threshold="48 hours",
    ),
    AlertRule(
        id="fda-deadline",
        name="FDA Records Request Deadline",
        category="deadline",
        severity="critical",
        description="Triggered when a mock audit drill approaches the 24-hour response deadline",
        threshold="4 hours",
    ),
]


def _get_db_session():
    try:
        from shared.database import SessionLocal

        db = SessionLocal()
    except Exception as exc:
        logger.error("alerts_db_session_init_failed", error=str(exc))
        raise HTTPException(status_code=503, detail="Database unavailable")
    return db


def _load_alert_columns(db_session) -> set[str]:
    rows = db_session.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'fsma'
              AND table_name = 'compliance_alerts'
            """
        )
    ).fetchall()
    return {row[0] for row in rows}


def _category_for_alert_type(alert_type: str) -> str:
    normalized = (alert_type or "").lower()
    if "temp" in normalized:
        return "temperature"
    if "deadline" in normalized or "expiry" in normalized:
        return "deadline"
    if "chain" in normalized:
        return "chain"
    return "compliance"


def _rule_name(alert_type: str) -> str:
    if not alert_type:
        return "Compliance Alert"
    return alert_type.replace("_", " ").strip().title()


def _to_iso(value: Any) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _fetch_alerts_from_db(db_session, tenant_id: str) -> list[Alert]:
    columns = _load_alert_columns(db_session)
    if not columns:
        return []

    tenant_col = "tenant_id" if "tenant_id" in columns else ("org_id" if "org_id" in columns else None)
    if tenant_col is None:
        logger.warning("alerts_table_missing_tenant_scope_column")
        return []

    alert_type_col = "alert_type" if "alert_type" in columns else None
    message_col = "message" if "message" in columns else ("description" if "description" in columns else None)
    title_col = "title" if "title" in columns else None
    resolved_col = "resolved" if "resolved" in columns else ("acknowledged" if "acknowledged" in columns else None)
    resolved_at_col = "resolved_at" if "resolved_at" in columns else ("acknowledged_at" if "acknowledged_at" in columns else None)
    resolved_by_col = "resolved_by" if "resolved_by" in columns else ("acknowledged_by" if "acknowledged_by" in columns else None)
    details_col = "details" if "details" in columns else ("metadata" if "metadata" in columns else None)
    event_ref_col = next(
        (name for name in ("cte_event_id", "event_id", "entity_id") if name in columns),
        None,
    )

    sql = f"""
        SELECT
            id::text AS alert_id,
            {alert_type_col if alert_type_col else "NULL"} AS alert_type,
            severity,
            {title_col if title_col else "NULL"} AS title,
            {message_col if message_col else "NULL"} AS message,
            created_at,
            {resolved_col if resolved_col else "false"} AS resolved,
            {resolved_at_col if resolved_at_col else "NULL"} AS resolved_at,
            {resolved_by_col if resolved_by_col else "NULL"} AS resolved_by,
            {details_col if details_col else "NULL"} AS details,
            {event_ref_col if event_ref_col else "NULL"}::text AS event_ref
        FROM fsma.compliance_alerts
        WHERE {tenant_col} = :tenant_id
        ORDER BY created_at DESC
        LIMIT 200
    """

    rows = db_session.execute(text(sql), {"tenant_id": tenant_id}).fetchall()

    alerts: list[Alert] = []
    for row in rows:
        details = row.details if isinstance(row.details, dict) else {}
        if row.event_ref:
            details = {**details, "event_id": row.event_ref}

        alert_type = row.alert_type or "compliance_alert"
        rule_id = alert_type
        rule_name = _rule_name(alert_type)
        message = row.message or row.title or rule_name

        alerts.append(
            Alert(
                id=row.alert_id,
                rule_id=rule_id,
                rule_name=rule_name,
                severity=row.severity or "warning",
                category=_category_for_alert_type(alert_type),
                title=row.title or rule_name,
                message=message,
                triggered_at=_to_iso(row.created_at),
                acknowledged=bool(row.resolved),
                acknowledged_at=_to_iso(row.resolved_at) if row.resolved_at else None,
                acknowledged_by=str(row.resolved_by) if row.resolved_by else None,
                metadata=details,
            )
        )

    return alerts


@router.get(
    "/{tenant_id}",
    response_model=AlertsResponse,
    summary="Get alerts for a tenant",
)
async def get_alerts(
    tenant_id: str,
    severity: Optional[str] = None,
    category: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    _: None = Depends(_verify_api_key),
) -> AlertsResponse:
    db_session = _get_db_session()
    try:
        alerts = _fetch_alerts_from_db(db_session, tenant_id)
    finally:
        db_session.close()

    if severity:
        alerts = [alert for alert in alerts if alert.severity == severity]
    if category:
        alerts = [alert for alert in alerts if alert.category == category]
    if acknowledged is not None:
        alerts = [alert for alert in alerts if alert.acknowledged == acknowledged]

    unack = sum(1 for alert in alerts if not alert.acknowledged)

    return AlertsResponse(
        tenant_id=tenant_id,
        total=len(alerts),
        unacknowledged=unack,
        alerts=alerts,
    )


@router.post(
    "/{tenant_id}/{alert_id}/acknowledge",
    summary="Acknowledge an alert",
)
async def acknowledge_alert(
    tenant_id: str,
    alert_id: str,
    _: None = Depends(_verify_api_key),
):
    db_session = _get_db_session()
    try:
        columns = _load_alert_columns(db_session)
        tenant_col = "tenant_id" if "tenant_id" in columns else ("org_id" if "org_id" in columns else None)
        if tenant_col is None:
            raise HTTPException(status_code=500, detail="Alerts table does not expose tenant scope")
        if "resolved" not in columns:
            raise HTTPException(status_code=501, detail="Alert acknowledgement is not supported by this schema")

        update_sql = f"""
            UPDATE fsma.compliance_alerts
            SET resolved = true,
                resolved_at = NOW()
            WHERE id = :alert_id
              AND {tenant_col} = :tenant_id
              AND (resolved IS NULL OR resolved = false)
            RETURNING id
        """
        row = db_session.execute(
            text(update_sql),
            {"alert_id": alert_id, "tenant_id": tenant_id},
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Alert not found")

        db_session.commit()
        return {"acknowledged": True, "alert_id": alert_id}
    finally:
        db_session.close()


@router.get(
    "/{tenant_id}/rules",
    summary="Get alert rules",
)
async def get_alert_rules(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
):
    return {"tenant_id": tenant_id, "rules": [rule.model_dump() for rule in DEFAULT_RULES]}


@router.get(
    "/{tenant_id}/summary",
    summary="Get alert summary",
)
async def get_alert_summary(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
):
    db_session = _get_db_session()
    try:
        alerts = _fetch_alerts_from_db(db_session, tenant_id)
    finally:
        db_session.close()

    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    unack = 0
    for alert in alerts:
        by_severity[alert.severity] = by_severity.get(alert.severity, 0) + 1
        by_category[alert.category] = by_category.get(alert.category, 0) + 1
        if not alert.acknowledged:
            unack += 1

    return {
        "tenant_id": tenant_id,
        "total": len(alerts),
        "unacknowledged": unack,
        "by_severity": by_severity,
        "by_category": by_category,
    }
