"""SQLAlchemy models for compliance state machine.

These models implement the "2am Alert" feature:
- Binary compliance status per tenant
- External alert triggers with countdown timers
- Status transition audit logging
"""

from __future__ import annotations

import uuid as uuid_module
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import relationship

# Import base from existing models
from .sqlalchemy_models import Base, GUID, JSONType


class ComplianceStatus(str, Enum):
    """Binary compliance status levels."""

    COMPLIANT = "COMPLIANT"
    AT_RISK = "AT_RISK"
    NON_COMPLIANT = "NON_COMPLIANT"


class AlertSeverity(str, Enum):
    """Alert severity levels mapped to urgency."""

    CRITICAL = "CRITICAL"  # 24-hour deadline, non-compliant if unresolved
    HIGH = "HIGH"  # 24-hour deadline, at-risk if unresolved
    MEDIUM = "MEDIUM"  # 48-hour deadline
    LOW = "LOW"  # Informational


class AlertSourceType(str, Enum):
    """Types of external alert sources."""

    FDA_RECALL = "FDA_RECALL"
    FDA_WARNING_LETTER = "FDA_WARNING_LETTER"
    FDA_IMPORT_ALERT = "FDA_IMPORT_ALERT"
    RETAILER_REQUEST = "RETAILER_REQUEST"
    INTERNAL_AUDIT = "INTERNAL_AUDIT"
    MANUAL = "MANUAL"


class AlertStatus(str, Enum):
    """Alert lifecycle status."""

    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    EXPIRED = "EXPIRED"


class TenantComplianceStatusModel(Base):
    """Main compliance status for a tenant.

    This is the "big status widget" - shows whether tenant is:
    - ✅ COMPLIANT: No active alerts
    - ⚠️ AT_RISK: Has HIGH severity active alerts
    - 🚨 NON_COMPLIANT: Has CRITICAL active alerts
    """

    __tablename__ = "tenant_compliance_status"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), nullable=False, unique=True)

    # Current status
    status = Column(String(50), nullable=False, default=ComplianceStatus.COMPLIANT.value)
    last_status_change = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Alert counts
    active_alert_count = Column(Integer, nullable=False, default=0)
    critical_alert_count = Column(Integer, nullable=False, default=0)

    # Completeness score (0.0 - 1.0)
    completeness_score = Column(Float, default=1.0)

    # Next deadline (for countdown display)
    next_deadline = Column(DateTime(timezone=True), nullable=True)
    next_deadline_description = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        return f"TenantComplianceStatus(tenant_id={self.tenant_id}, status={self.status})"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to API response dict."""
        now = datetime.now(timezone.utc)
        countdown_seconds = None
        countdown_display = None

        if self.next_deadline:
            delta = self.next_deadline - now
            countdown_seconds = max(0, int(delta.total_seconds()))
            hours, remainder = divmod(countdown_seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            countdown_display = f"{hours}h {minutes}m"

        return {
            "tenant_id": str(self.tenant_id),
            "status": self.status,
            "status_emoji": self._get_status_emoji(),
            "status_label": self._get_status_label(),
            "last_status_change": self.last_status_change.isoformat() if self.last_status_change else None,
            "active_alert_count": self.active_alert_count,
            "critical_alert_count": self.critical_alert_count,
            "completeness_score": self.completeness_score,
            "next_deadline": self.next_deadline.isoformat() if self.next_deadline else None,
            "next_deadline_description": self.next_deadline_description,
            "countdown_seconds": countdown_seconds,
            "countdown_display": countdown_display,
        }

    def _get_status_emoji(self) -> str:
        return {
            ComplianceStatus.COMPLIANT.value: "✅",
            ComplianceStatus.AT_RISK.value: "⚠️",
            ComplianceStatus.NON_COMPLIANT.value: "🚨",
        }.get(self.status, "❓")

    def _get_status_label(self) -> str:
        return {
            ComplianceStatus.COMPLIANT.value: "Compliant",
            ComplianceStatus.AT_RISK.value: "At Risk",
            ComplianceStatus.NON_COMPLIANT.value: "Non-Compliant",
        }.get(self.status, "Unknown")


class ComplianceAlertModel(Base):
    """External trigger alerts with countdown timers.

    This is what wakes someone up at 2am:
    - FDA announces Class I recall
    - Alert matches tenant's product profile
    - 24-hour countdown starts
    - User must take action or status degrades
    """

    __tablename__ = "compliance_alerts"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), nullable=False)

    # Alert identification
    source_type = Column(String(50), nullable=False)
    source_id = Column(String(255), nullable=False)

    # Alert details
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    severity = Column(String(50), nullable=False, default=AlertSeverity.MEDIUM.value)

    # Countdown timer
    countdown_start = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    countdown_end = Column(DateTime(timezone=True), nullable=False)
    countdown_hours = Column(Integer, nullable=False, default=24)

    # Required actions (JSONB array)
    required_actions = Column(JSONType(), nullable=False, default=list)

    # Status tracking
    status = Column(String(50), nullable=False, default=AlertStatus.ACTIVE.value)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String(255), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String(255), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Matching metadata
    match_reason = Column(JSONType(), nullable=True)
    raw_data = Column(JSONType(), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "source_type", "source_id", name="uq_alert_source"),
        Index("idx_alerts_tenant_status", "tenant_id", "status"),
        Index("idx_alerts_countdown", "countdown_end"),
        Index("idx_alerts_severity", "severity", "status"),
    )

    def __repr__(self) -> str:
        return f"ComplianceAlert(id={self.id}, severity={self.severity}, status={self.status})"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to API response dict with live countdown."""
        now = datetime.now(timezone.utc)
        countdown_seconds = 0
        countdown_display = "Expired"
        is_expired = False

        if self.countdown_end:
            delta = self.countdown_end - now
            countdown_seconds = int(delta.total_seconds())

            if countdown_seconds > 0:
                hours, remainder = divmod(countdown_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                countdown_display = f"{hours}h {minutes}m {seconds}s"
            else:
                is_expired = True
                countdown_seconds = 0

        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "source_type": self.source_type,
            "source_id": self.source_id,
            "title": self.title,
            "summary": self.summary,
            "severity": self.severity,
            "severity_emoji": self._get_severity_emoji(),
            "countdown_start": self.countdown_start.isoformat() if self.countdown_start else None,
            "countdown_end": self.countdown_end.isoformat() if self.countdown_end else None,
            "countdown_hours": self.countdown_hours,
            "countdown_seconds": countdown_seconds,
            "countdown_display": countdown_display,
            "is_expired": is_expired,
            "required_actions": self.required_actions or [],
            "status": self.status,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
            "match_reason": self.match_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def _get_severity_emoji(self) -> str:
        return {
            AlertSeverity.CRITICAL.value: "🚨",
            AlertSeverity.HIGH.value: "⚠️",
            AlertSeverity.MEDIUM.value: "📋",
            AlertSeverity.LOW.value: "ℹ️",
        }.get(self.severity, "❓")


class ComplianceStatusLogModel(Base):
    """Audit trail for status transitions.

    Records every status change for compliance auditing.
    """

    __tablename__ = "compliance_status_log"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), nullable=False)

    # Status transition
    previous_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=False)

    # Trigger information
    trigger_type = Column(String(100), nullable=False)
    trigger_alert_id = Column(GUID(), nullable=True)
    trigger_description = Column(Text, nullable=True)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_status_log_tenant", "tenant_id", "created_at"),
    )


class TenantProductProfileModel(Base):
    """Tenant's product profile for alert matching.

    Used to determine if an FDA recall/alert applies to this tenant.
    """

    __tablename__ = "tenant_product_profile"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), nullable=False, unique=True)

    # Product categories for matching
    product_categories = Column(JSONType(), nullable=False, default=list)
    # E.g., ["leafy_greens", "romaine_lettuce", "sprouts"]

    # Geographic regions
    supply_regions = Column(JSONType(), nullable=False, default=list)
    # E.g., ["CA", "AZ", "FL"]

    # Supplier identifiers
    supplier_identifiers = Column(JSONType(), nullable=False, default=list)

    # FDA product codes
    fda_product_codes = Column(JSONType(), nullable=False, default=list)

    # Retailer relationships
    retailer_relationships = Column(JSONType(), nullable=False, default=list)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": str(self.tenant_id),
            "product_categories": self.product_categories or [],
            "supply_regions": self.supply_regions or [],
            "supplier_identifiers": self.supplier_identifiers or [],
            "fda_product_codes": self.fda_product_codes or [],
            "retailer_relationships": self.retailer_relationships or [],
        }
