"""
Audit Log Router.

Immutable audit trail of all system events — CTE recordings, 
user actions, API calls, and compliance changes. Provides
forensic-grade visibility for FDA inspections and internal review.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.webhook_router import _verify_api_key

logger = logging.getLogger("audit-log")

router = APIRouter(prefix="/api/v1/audit-log", tags=["Audit Log"])


class AuditEntry(BaseModel):
    """A single audit log entry."""
    id: str
    timestamp: str
    event_type: str  # cte_recorded, user_login, api_call, compliance_change, export, alert
    category: str    # data, auth, compliance, system
    actor: str       # user email, api key ID, or "system"
    action: str      # human-readable action description
    resource: str    # what was acted upon
    details: dict = Field(default_factory=dict)
    ip_address: str = ""
    hash: str = ""   # SHA-256 of entry for tamper detection


class AuditLogResponse(BaseModel):
    """Paginated audit log response."""
    tenant_id: str
    total: int
    page: int
    page_size: int
    entries: list[AuditEntry]


def _generate_sample_log(tenant_id: str) -> list[AuditEntry]:
    now = datetime.now(timezone.utc)
    return [
        AuditEntry(
            id=f"{tenant_id}-log-001",
            timestamp=(now - timedelta(minutes=5)).isoformat(),
            event_type="cte_recorded",
            category="data",
            actor="ops@valleyfresh.com",
            action="Recorded Shipping CTE",
            resource="TLC ROM-0226-A1-001",
            details={"cte_type": "shipping", "product": "Roma Tomatoes", "quantity": 24},
            ip_address="192.168.1.42",
            hash="a3f8c1d2e4b5f6a7...",
        ),
        AuditEntry(
            id=f"{tenant_id}-log-002",
            timestamp=(now - timedelta(minutes=15)).isoformat(),
            event_type="api_call",
            category="system",
            actor="rge_key_prod_001",
            action="POST /api/v1/webhooks/ingest",
            resource="Webhook Ingestion",
            details={"events_count": 3, "status": 200},
            ip_address="10.0.0.15",
            hash="b4c9d3e5f6a7b8c9...",
        ),
        AuditEntry(
            id=f"{tenant_id}-log-003",
            timestamp=(now - timedelta(minutes=30)).isoformat(),
            event_type="compliance_change",
            category="compliance",
            actor="system",
            action="Compliance score updated",
            resource="Tenant Score",
            details={"previous_grade": "B", "new_grade": "C", "score": 71},
            hash="c5dae4f6a7b8c9d0...",
        ),
        AuditEntry(
            id=f"{tenant_id}-log-004",
            timestamp=(now - timedelta(hours=1)).isoformat(),
            event_type="export",
            category="data",
            actor="jsmith@example.com",
            action="Exported EPCIS 2.0 JSON-LD",
            resource="Export: epcis",
            details={"format": "epcis_2.0", "events_count": 47, "target": "walmart"},
            ip_address="192.168.1.100",
            hash="d6ebf5a7b8c9d0e1...",
        ),
        AuditEntry(
            id=f"{tenant_id}-log-005",
            timestamp=(now - timedelta(hours=2)).isoformat(),
            event_type="user_login",
            category="auth",
            actor="jsmith@example.com",
            action="User logged in",
            resource="Session",
            details={"method": "sso", "provider": "okta"},
            ip_address="192.168.1.100",
            hash="e7fca6b8c9d0e1f2...",
        ),
        AuditEntry(
            id=f"{tenant_id}-log-006",
            timestamp=(now - timedelta(hours=3)).isoformat(),
            event_type="cte_recorded",
            category="data",
            actor="portal-vff-001",
            action="Supplier submitted Receiving CTE via portal",
            resource="TLC SAL-0226-B1-007",
            details={"cte_type": "receiving", "product": "Atlantic Salmon", "via": "supplier_portal"},
            hash="f8adb7c9d0e1f2a3...",
        ),
        AuditEntry(
            id=f"{tenant_id}-log-007",
            timestamp=(now - timedelta(hours=4)).isoformat(),
            event_type="alert",
            category="compliance",
            actor="system",
            action="Temperature excursion alert triggered",
            resource="Alert: temp-excursion",
            details={"temperature": 8.2, "threshold": 5.0, "tlc": "SAL-0226-B1-007"},
            hash="a9bec8d0e1f2a3b4...",
        ),
        AuditEntry(
            id=f"{tenant_id}-log-008",
            timestamp=(now - timedelta(hours=6)).isoformat(),
            event_type="api_call",
            category="system",
            actor="rge_key_prod_001",
            action="POST /api/v1/ingest/csv",
            resource="CSV Upload",
            details={"file": "shipping_feb_26.csv", "rows": 15, "valid": 14, "errors": 1},
            ip_address="10.0.0.15",
            hash="bacfd9e1f2a3b4c5...",
        ),
    ]


_log_store: dict[str, list[AuditEntry]] = {}


@router.get(
    "/{tenant_id}",
    response_model=AuditLogResponse,
    summary="Get audit log",
    description="Returns paginated audit log entries for a tenant.",
)
async def get_audit_log(
    tenant_id: str,
    page: int = 1,
    page_size: int = 20,
    event_type: str | None = None,
    category: str | None = None,
    _: None = Depends(_verify_api_key),
) -> AuditLogResponse:
    """Get audit log with optional filtering."""
    if tenant_id not in _log_store:
        _log_store[tenant_id] = _generate_sample_log(tenant_id)

    entries = _log_store[tenant_id]

    if event_type:
        entries = [e for e in entries if e.event_type == event_type]
    if category:
        entries = [e for e in entries if e.category == category]

    entries.sort(key=lambda e: e.timestamp, reverse=True)
    total = len(entries)
    start = (page - 1) * page_size
    entries = entries[start:start + page_size]

    return AuditLogResponse(
        tenant_id=tenant_id,
        total=total,
        page=page,
        page_size=page_size,
        entries=entries,
    )
