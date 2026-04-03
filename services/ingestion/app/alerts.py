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
from app.tenant_validation import validate_tenant_id

logger = logging.getLogger("alerts")

# Strict allowlist of column names permitted in dynamic SQL for compliance_alerts.
# Any column name from information_schema is intersected with this set before
# being interpolated into query text, preventing SQL injection.
_ALLOWED_ALERT_COLUMNS: frozenset[str] = frozenset(
    {
        "id",
        "alert_type",
        "severity",
        "title",
        "message",
        "description",
        "created_at",
        "resolved",
        "acknowledged",
        "resolved_at",
        "acknowledged_at",
        "resolved_by",
        "acknowledged_by",
        "details",
        "metadata",
        "tenant_id",
        "org_id",
        "cte_event_id",
        "event_id",
        "entity_id",
    }
)

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
    AlertRule(
        id="fda-recall",
        name="FDA Recall Alert",
        category="fda_recall",
        severity="critical",
        description="Triggered when an FDA food recall matches a supplier, lot code, or product category in your supply chain",
    ),
]


def _get_db_session():
    try:
        from shared.database import SessionLocal

        db = SessionLocal()
    except (ImportError, RuntimeError, OSError) as exc:
        logger.error("alerts_db_session_init_failed error=%s", str(exc))
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
    # Intersect with allowlist so only known-safe identifiers are used in SQL
    return {row[0] for row in rows} & _ALLOWED_ALERT_COLUMNS


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


def _severity_for_classification(classification: str) -> str:
    """Map FDA recall classification to alert severity."""
    if "Class I" in classification:
        return "critical"
    if "Class II" in classification:
        return "high"
    return "warning"


def _fetch_fda_recall_alerts(db_session, tenant_id: str) -> list[Alert]:
    """Fetch FDA recall alerts from public.compliance_alerts.

    ComplianceIntegration writes recall-matched alerts to public.compliance_alerts
    with source_type='FDA_RECALL'. This function reads them and maps to the Alert
    response model with recall-specific metadata (recall number, classification,
    countdown timer, match tier, FDA enforcement link).
    """
    try:
        # Check if public.compliance_alerts exists
        exists = db_session.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'compliance_alerts'
                """
            )
        ).fetchone()
        if not exists:
            return []

        rows = db_session.execute(
            text(
                """
                SELECT
                    id::text,
                    source_type,
                    source_id,
                    title,
                    summary,
                    severity,
                    countdown_start,
                    countdown_end,
                    countdown_hours,
                    required_actions,
                    status,
                    match_reason,
                    raw_data,
                    created_at,
                    acknowledged_at,
                    acknowledged_by,
                    resolved_at
                FROM public.compliance_alerts
                WHERE tenant_id = :tenant_id
                  AND source_type = 'FDA_RECALL'
                ORDER BY created_at DESC
                LIMIT 200
                """
            ),
            {"tenant_id": tenant_id},
        ).fetchall()
    except Exception as exc:
        logger.warning("fda_recall_alerts_query_failed error=%s", str(exc))
        return []

    alerts: list[Alert] = []
    for row in rows:
        raw = row.raw_data if isinstance(row.raw_data, dict) else {}
        match = row.match_reason if isinstance(row.match_reason, dict) else {}

        # Extract recall-specific fields for metadata
        classification = raw.get("classification", "")
        recall_number = raw.get("recall_number", "")
        recalling_firm = raw.get("recalling_firm", "")
        if not recalling_firm and row.title:
            # Title format is "[Class X] FirmName - product..."
            parts = row.title.split("] ", 1)
            if len(parts) > 1:
                firm_part = parts[1].split(" - ", 1)
                recalling_firm = firm_part[0]

        # Determine match tier from match_reason
        matched_by = match.get("matched_by", [])
        match_tier = "category"
        for reason in matched_by:
            if "lot_code" in str(reason):
                match_tier = "lot_code"
                break
            if "supplier" in str(reason):
                match_tier = "supplier"

        # Build FDA enforcement link
        fda_url = ""
        if recall_number:
            fda_url = (
                f"https://www.accessdata.fda.gov/scripts/ires/index.cfm"
                f"?event=ires.dspBriefRecallNumber&RecallNumber={recall_number}"
            )

        metadata = {
            "source_type": "FDA_RECALL",
            "recall_number": recall_number,
            "classification": classification,
            "recalling_firm": recalling_firm,
            "match_tier": match_tier,
            "match_reasons": matched_by,
            "fda_url": fda_url,
            "countdown_start": _to_iso(row.countdown_start) if row.countdown_start else None,
            "countdown_end": _to_iso(row.countdown_end) if row.countdown_end else None,
            "countdown_hours": row.countdown_hours,
            "distribution_pattern": raw.get("distribution_pattern", ""),
            "code_info": raw.get("code_info", ""),
        }

        # Map severity from uppercase DB values to lowercase API values
        severity = (row.severity or "MEDIUM").lower()

        is_acknowledged = row.status in ("ACKNOWLEDGED", "RESOLVED") or row.acknowledged_at is not None

        alerts.append(
            Alert(
                id=row[0],  # id::text
                rule_id="fda-recall",
                rule_name="FDA Recall Alert",
                severity=severity,
                category="fda_recall",
                title=row.title or "FDA Recall",
                message=row.summary or row.title or "FDA Recall Alert",
                triggered_at=_to_iso(row.created_at),
                acknowledged=is_acknowledged,
                acknowledged_at=_to_iso(row.acknowledged_at) if row.acknowledged_at else None,
                acknowledged_by=str(row.acknowledged_by) if row.acknowledged_by else None,
                metadata=metadata,
            )
        )

    return alerts


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

    # All column identifiers below are guaranteed to be members of
    # _ALLOWED_ALERT_COLUMNS (via _load_alert_columns) or literal "NULL"/"false".
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
    validate_tenant_id(tenant_id)
    alerts: list[Alert] = []
    try:
        db_session = _get_db_session()
        try:
            # Fetch from both alert tables and merge
            fsma_alerts = _fetch_alerts_from_db(db_session, tenant_id)
            fda_recall_alerts = _fetch_fda_recall_alerts(db_session, tenant_id)

            # Merge and deduplicate by id
            seen_ids: set[str] = set()
            for alert in fda_recall_alerts + fsma_alerts:
                if alert.id not in seen_ids:
                    alerts.append(alert)
                    seen_ids.add(alert.id)

            # Sort by triggered_at descending (most recent first)
            alerts.sort(key=lambda a: a.triggered_at, reverse=True)
        finally:
            db_session.close()
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except (RuntimeError, OSError, AttributeError) as exc:
        logger.warning("alerts_db_unavailable error=%s tenant_id=%s", str(exc), tenant_id)

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
        # Try public.compliance_alerts first (FDA recall alerts)
        try:
            public_row = db_session.execute(
                text(
                    """
                    UPDATE public.compliance_alerts
                    SET status = 'ACKNOWLEDGED',
                        acknowledged_at = NOW(),
                        acknowledged_by = :tenant_id,
                        updated_at = NOW()
                    WHERE id = :alert_id
                      AND tenant_id = :tenant_id
                      AND status = 'ACTIVE'
                    RETURNING id
                    """
                ),
                {"alert_id": alert_id, "tenant_id": tenant_id},
            ).fetchone()
            if public_row:
                db_session.commit()
                return {"acknowledged": True, "alert_id": alert_id}
        except Exception:
            db_session.rollback()

        # Fall back to fsma.compliance_alerts
        columns = _load_alert_columns(db_session)
        tenant_col = "tenant_id" if "tenant_id" in columns else ("org_id" if "org_id" in columns else None)
        if tenant_col is None:
            raise HTTPException(status_code=500, detail="Alerts table does not expose tenant scope")
        if "resolved" not in columns:
            raise HTTPException(status_code=501, detail="Alert acknowledgement is not supported by this schema")

        # tenant_col is validated against _ALLOWED_ALERT_COLUMNS via _load_alert_columns
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
        fsma_alerts = _fetch_alerts_from_db(db_session, tenant_id)
        fda_recall_alerts = _fetch_fda_recall_alerts(db_session, tenant_id)

        # Merge and deduplicate
        seen_ids: set[str] = set()
        alerts: list[Alert] = []
        for alert in fda_recall_alerts + fsma_alerts:
            if alert.id not in seen_ids:
                alerts.append(alert)
                seen_ids.add(alert.id)
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
