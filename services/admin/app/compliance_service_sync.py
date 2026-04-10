"""Synchronous compliance service layer for the 2am Alert feature.

This is the sync version compatible with the existing SQLAlchemy sync session.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from .compliance_models import (
    AlertSeverity,
    AlertSourceType,
    AlertStatus,
    ComplianceAlertModel,
    ComplianceStatus,
    ComplianceStatusLogModel,
    TenantComplianceStatusModel,
    TenantProductProfileModel,
)

logger = structlog.get_logger("compliance.service")


class ComplianceServiceSync:
    """Synchronous service for managing tenant compliance status and alerts."""

    def __init__(self, session: Session):
        self.session = session

    def get_status(self, tenant_id: UUID) -> Dict[str, Any]:
        """Get current compliance status for a tenant."""
        result = self.session.execute(
            select(TenantComplianceStatusModel).where(
                TenantComplianceStatusModel.tenant_id == tenant_id
            )
        )
        status = result.scalar_one_or_none()

        if not status:
            status = self._create_default_status(tenant_id)

        # Get active alerts
        alerts_result = self.session.execute(
            select(ComplianceAlertModel)
            .where(
                and_(
                    ComplianceAlertModel.tenant_id == tenant_id,
                    ComplianceAlertModel.status == AlertStatus.ACTIVE.value,
                )
            )
            .order_by(ComplianceAlertModel.severity, ComplianceAlertModel.countdown_end)
        )
        active_alerts = alerts_result.scalars().all()

        return {
            **status.to_dict(),
            "active_alerts": [alert.to_dict() for alert in active_alerts],
        }

    def _create_default_status(self, tenant_id: UUID) -> TenantComplianceStatusModel:
        """Create a default compliant status for a new tenant."""
        now = datetime.now(timezone.utc)
        status = TenantComplianceStatusModel(
            tenant_id=tenant_id,
            status=ComplianceStatus.COMPLIANT.value,
            last_status_change=now,
        )
        self.session.add(status)
        self.session.commit()
        self.session.refresh(status)
        return status

    def get_alerts(
        self,
        tenant_id: UUID,
        status_filter: Optional[str] = None,
        limit: int = 50,
    ) -> List[ComplianceAlertModel]:
        """Get alerts for a tenant."""
        query = select(ComplianceAlertModel).where(
            ComplianceAlertModel.tenant_id == tenant_id
        )

        if status_filter:
            query = query.where(ComplianceAlertModel.status == status_filter)

        query = query.order_by(
            desc(ComplianceAlertModel.created_at)
        ).limit(limit)

        result = self.session.execute(query)
        return result.scalars().all()

    def get_alert(self, alert_id: UUID) -> Optional[ComplianceAlertModel]:
        """Get a single alert by ID."""
        result = self.session.execute(
            select(ComplianceAlertModel).where(ComplianceAlertModel.id == alert_id)
        )
        return result.scalar_one_or_none()

    def acknowledge_alert(
        self,
        alert_id: UUID,
        user_id: str,
    ) -> Optional[ComplianceAlertModel]:
        """Mark an alert as acknowledged."""
        alert = self.get_alert(alert_id)
        if not alert:
            return None

        alert.status = AlertStatus.ACKNOWLEDGED.value
        alert.acknowledged_at = datetime.now(timezone.utc)
        alert.acknowledged_by = user_id

        self.session.commit()
        self.session.refresh(alert)
        return alert

    def resolve_alert(
        self,
        alert_id: UUID,
        user_id: str,
        notes: Optional[str] = None,
    ) -> Optional[ComplianceAlertModel]:
        """Mark an alert as resolved."""
        alert = self.get_alert(alert_id)
        if not alert:
            return None

        alert.status = AlertStatus.RESOLVED.value
        alert.resolved_at = datetime.now(timezone.utc)
        alert.resolved_by = user_id
        alert.resolution_notes = notes

        self.session.commit()
        self.session.refresh(alert)

        # Recalculate status
        self._recalculate_status(alert.tenant_id)
        return alert

    def _recalculate_status(self, tenant_id: UUID) -> None:
        """Recalculate tenant compliance status."""
        result = self.session.execute(
            select(TenantComplianceStatusModel).where(
                TenantComplianceStatusModel.tenant_id == tenant_id
            )
        )
        status = result.scalar_one_or_none()

        if not status:
            status = self._create_default_status(tenant_id)

        # Count active alerts
        counts = self.session.execute(
            select(
                ComplianceAlertModel.severity,
                func.count(ComplianceAlertModel.id).label("count"),
            )
            .where(
                and_(
                    ComplianceAlertModel.tenant_id == tenant_id,
                    ComplianceAlertModel.status == AlertStatus.ACTIVE.value,
                )
            )
            .group_by(ComplianceAlertModel.severity)
        )
        severity_counts = {row[0]: row[1] for row in counts.fetchall()}

        critical_count = severity_counts.get(AlertSeverity.CRITICAL.value, 0)
        high_count = severity_counts.get(AlertSeverity.HIGH.value, 0)
        total_active = sum(severity_counts.values())

        # Determine new status
        if critical_count > 0:
            new_status = ComplianceStatus.NON_COMPLIANT.value
        elif high_count > 0 or total_active > 0:
            new_status = ComplianceStatus.AT_RISK.value
        else:
            new_status = ComplianceStatus.COMPLIANT.value

        status.status = new_status
        status.active_alert_count = total_active
        status.critical_alert_count = critical_count

        self.session.commit()

    # Regulatory citations for different alert types
    REGULATORY_CITATIONS = {
        "FDA_RECALL": "21 CFR \u00a71.134",
        "FDA_WARNING": "21 CFR \u00a71.401",
        "IMPORT_ALERT": "21 CFR \u00a71.285",
        "REGULATORY_CHANGE": "21 CFR Part 1 Subpart S",
        "MANUAL": "FSMA 204 - Internal Policy",
    }

    def create_alert(
        self,
        tenant_id: UUID,
        source_type: AlertSourceType,
        source_id: str,
        title: str,
        severity: AlertSeverity,
        summary: Optional[str] = None,
        countdown_hours: int = 24,
        required_actions: Optional[List[Dict[str, Any]]] = None,
    ) -> ComplianceAlertModel:
        """Create a new compliance alert."""
        now = datetime.now(timezone.utc)
        countdown_end = now + timedelta(hours=countdown_hours)

        alert = ComplianceAlertModel(
            tenant_id=tenant_id,
            source_type=source_type.value,
            source_id=source_id,
            title=title,
            summary=summary,
            severity=severity.value,
            countdown_start=now,
            countdown_end=countdown_end,
            countdown_hours=countdown_hours,
            required_actions=required_actions or [],
            status=AlertStatus.ACTIVE.value,
        )

        self.session.add(alert)
        self.session.commit()
        self.session.refresh(alert)

        self._recalculate_status(tenant_id)

        return alert

    def get_product_profile(self, tenant_id: UUID) -> Optional[TenantProductProfileModel]:
        """Get tenant's product profile."""
        result = self.session.execute(
            select(TenantProductProfileModel).where(
                TenantProductProfileModel.tenant_id == tenant_id
            )
        )
        return result.scalar_one_or_none()

    def update_product_profile(
        self,
        tenant_id: UUID,
        product_categories: Optional[List[str]] = None,
        supply_regions: Optional[List[str]] = None,
        supplier_identifiers: Optional[List[str]] = None,
        fda_product_codes: Optional[List[str]] = None,
        retailer_relationships: Optional[List[str]] = None,
    ) -> TenantProductProfileModel:
        """Update tenant's product profile."""
        profile = self.get_product_profile(tenant_id)

        if not profile:
            profile = TenantProductProfileModel(tenant_id=tenant_id)
            self.session.add(profile)

        if product_categories is not None:
            profile.product_categories = product_categories
        if supply_regions is not None:
            profile.supply_regions = supply_regions
        if supplier_identifiers is not None:
            profile.supplier_identifiers = supplier_identifiers
        if fda_product_codes is not None:
            profile.fda_product_codes = fda_product_codes
        if retailer_relationships is not None:
            profile.retailer_relationships = retailer_relationships

        self.session.commit()
        self.session.refresh(profile)
        return profile
