"""Compliance service layer for the 2am Alert feature.

Handles:
- Status calculation and updates
- Alert creation and matching
- Notification dispatch
- State transitions with audit logging
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import structlog
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

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


class ComplianceService:
    """Service for managing tenant compliance status and alerts.

    This is the core of the "2am Alert" feature.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # =========================================================================
    # STATUS OPERATIONS
    # =========================================================================

    async def get_status(self, tenant_id: UUID) -> Dict[str, Any]:
        """Get current compliance status for a tenant.

        Returns the "big status widget" data with countdown.
        """
        result = await self.session.execute(
            select(TenantComplianceStatusModel).where(
                TenantComplianceStatusModel.tenant_id == tenant_id
            )
        )
        status = result.scalar_one_or_none()

        if not status:
            # Create default compliant status
            status = await self._create_default_status(tenant_id)

        # Get active alerts
        alerts_result = await self.session.execute(
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

    async def _create_default_status(self, tenant_id: UUID) -> TenantComplianceStatusModel:
        """Create a default compliant status for a new tenant."""
        status = TenantComplianceStatusModel(
            tenant_id=tenant_id,
            status=ComplianceStatus.COMPLIANT.value,
        )
        self.session.add(status)
        await self.session.commit()
        await self.session.refresh(status)
        return status

    async def recalculate_status(self, tenant_id: UUID) -> TenantComplianceStatusModel:
        """Recalculate and update compliance status based on active alerts.

        This is called after alert create/resolve to update the tenant's status.
        """
        # Get current status
        result = await self.session.execute(
            select(TenantComplianceStatusModel).where(
                TenantComplianceStatusModel.tenant_id == tenant_id
            )
        )
        status = result.scalar_one_or_none()

        if not status:
            status = await self._create_default_status(tenant_id)

        # Count active alerts by severity
        counts = await self.session.execute(
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

        # Log status change if different
        if status.status != new_status:
            await self._log_status_change(
                tenant_id=tenant_id,
                previous_status=status.status,
                new_status=new_status,
                trigger_type="recalculation",
                trigger_description=f"Recalculated: {critical_count} critical, {high_count} high, {total_active} total active",
            )
            status.status = new_status
            status.last_status_change = datetime.now(timezone.utc)

        # Update counts
        status.active_alert_count = total_active
        status.critical_alert_count = critical_count

        # Find next deadline
        next_deadline_result = await self.session.execute(
            select(ComplianceAlertModel)
            .where(
                and_(
                    ComplianceAlertModel.tenant_id == tenant_id,
                    ComplianceAlertModel.status == AlertStatus.ACTIVE.value,
                )
            )
            .order_by(ComplianceAlertModel.countdown_end)
            .limit(1)
        )
        next_alert = next_deadline_result.scalar_one_or_none()

        if next_alert:
            status.next_deadline = next_alert.countdown_end
            status.next_deadline_description = next_alert.title
        else:
            status.next_deadline = None
            status.next_deadline_description = None

        await self.session.commit()
        await self.session.refresh(status)

        logger.info(
            "status_recalculated",
            tenant_id=str(tenant_id),
            new_status=new_status,
            active_alerts=total_active,
        )

        return status

    async def _log_status_change(
        self,
        tenant_id: UUID,
        previous_status: Optional[str],
        new_status: str,
        trigger_type: str,
        trigger_alert_id: Optional[UUID] = None,
        trigger_description: Optional[str] = None,
    ) -> None:
        """Log a status transition for audit trail."""
        log_entry = ComplianceStatusLogModel(
            tenant_id=tenant_id,
            previous_status=previous_status,
            new_status=new_status,
            trigger_type=trigger_type,
            trigger_alert_id=trigger_alert_id,
            trigger_description=trigger_description,
        )
        self.session.add(log_entry)
        # Don't commit here - let caller commit

    # =========================================================================
    # ALERT OPERATIONS
    # =========================================================================

    async def create_alert(
        self,
        tenant_id: UUID,
        source_type: AlertSourceType,
        source_id: str,
        title: str,
        severity: AlertSeverity,
        summary: Optional[str] = None,
        countdown_hours: int = 24,
        required_actions: Optional[List[Dict[str, Any]]] = None,
        match_reason: Optional[Dict[str, Any]] = None,
        raw_data: Optional[Dict[str, Any]] = None,
    ) -> ComplianceAlertModel:
        """Create a new compliance alert.

        This triggers the "2am wake-up" flow.
        """
        now = datetime.now(timezone.utc)
        countdown_end = now + timedelta(hours=countdown_hours)

        # Check for existing alert with same source
        existing = await self.session.execute(
            select(ComplianceAlertModel).where(
                and_(
                    ComplianceAlertModel.tenant_id == tenant_id,
                    ComplianceAlertModel.source_type == source_type.value,
                    ComplianceAlertModel.source_id == source_id,
                )
            )
        )
        if existing.scalar_one_or_none():
            logger.info(
                "alert_already_exists",
                tenant_id=str(tenant_id),
                source_id=source_id,
            )
            # Return existing alert
            return existing.scalar_one()

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
            match_reason=match_reason,
            raw_data=raw_data,
        )

        self.session.add(alert)
        await self.session.commit()
        await self.session.refresh(alert)

        # Recalculate tenant status
        await self.recalculate_status(tenant_id)

        logger.warning(
            "compliance_alert_created",
            tenant_id=str(tenant_id),
            alert_id=str(alert.id),
            severity=severity.value,
            title=title,
            countdown_hours=countdown_hours,
        )

        return alert

    async def get_alerts(
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

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_alert(self, alert_id: UUID) -> Optional[ComplianceAlertModel]:
        """Get a single alert by ID."""
        result = await self.session.execute(
            select(ComplianceAlertModel).where(ComplianceAlertModel.id == alert_id)
        )
        return result.scalar_one_or_none()

    async def acknowledge_alert(
        self,
        alert_id: UUID,
        user_id: str,
    ) -> Optional[ComplianceAlertModel]:
        """Mark an alert as acknowledged (user has seen it)."""
        alert = await self.get_alert(alert_id)
        if not alert:
            return None

        alert.status = AlertStatus.ACKNOWLEDGED.value
        alert.acknowledged_at = datetime.now(timezone.utc)
        alert.acknowledged_by = user_id

        await self.session.commit()
        await self.session.refresh(alert)

        logger.info(
            "alert_acknowledged",
            alert_id=str(alert_id),
            user_id=user_id,
        )

        return alert

    async def resolve_alert(
        self,
        alert_id: UUID,
        user_id: str,
        notes: Optional[str] = None,
    ) -> Optional[ComplianceAlertModel]:
        """Mark an alert as resolved (action taken)."""
        alert = await self.get_alert(alert_id)
        if not alert:
            return None

        alert.status = AlertStatus.RESOLVED.value
        alert.resolved_at = datetime.now(timezone.utc)
        alert.resolved_by = user_id
        alert.resolution_notes = notes

        await self.session.commit()
        await self.session.refresh(alert)

        # Recalculate tenant status
        await self.recalculate_status(alert.tenant_id)

        logger.info(
            "alert_resolved",
            alert_id=str(alert_id),
            user_id=user_id,
            tenant_id=str(alert.tenant_id),
        )

        return alert

    # =========================================================================
    # PRODUCT PROFILE OPERATIONS
    # =========================================================================

    async def get_product_profile(
        self, tenant_id: UUID
    ) -> Optional[TenantProductProfileModel]:
        """Get tenant's product profile for alert matching."""
        result = await self.session.execute(
            select(TenantProductProfileModel).where(
                TenantProductProfileModel.tenant_id == tenant_id
            )
        )
        return result.scalar_one_or_none()

    async def update_product_profile(
        self,
        tenant_id: UUID,
        product_categories: Optional[List[str]] = None,
        supply_regions: Optional[List[str]] = None,
        supplier_identifiers: Optional[List[str]] = None,
        fda_product_codes: Optional[List[str]] = None,
        retailer_relationships: Optional[List[str]] = None,
    ) -> TenantProductProfileModel:
        """Update tenant's product profile."""
        profile = await self.get_product_profile(tenant_id)

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

        await self.session.commit()
        await self.session.refresh(profile)

        return profile

    # =========================================================================
    # ALERT MATCHING
    # =========================================================================

    async def match_recall_to_tenants(
        self,
        recall_data: Dict[str, Any],
    ) -> List[UUID]:
        """Match an FDA recall to affected tenants.

        This is called by the scheduler when a new recall is detected.
        Returns list of tenant IDs that should receive alerts.
        """
        matched_tenants = []

        # Extract recall attributes for matching
        product_description = recall_data.get("product_description", "").lower()
        recalling_firm = recall_data.get("recalling_firm", "").lower()
        state = recall_data.get("state", "").upper()
        distribution = recall_data.get("distribution_pattern", "").lower()

        # Common leafy greens keywords
        leafy_greens_keywords = [
            "lettuce", "romaine", "spinach", "kale", "arugula",
            "salad", "greens", "mesclun", "spring mix", "chard",
        ]

        # Get all product profiles
        result = await self.session.execute(select(TenantProductProfileModel))
        profiles = result.scalars().all()

        for profile in profiles:
            match_reasons = []

            # Check product category match
            if profile.product_categories:
                for category in profile.product_categories:
                    if category.lower() in product_description:
                        match_reasons.append(f"product_category:{category}")

            # Check for leafy greens (FTL item)
            for keyword in leafy_greens_keywords:
                if keyword in product_description:
                    if "leafy_greens" in [c.lower() for c in (profile.product_categories or [])]:
                        match_reasons.append(f"ftl_item:{keyword}")
                        break

            # Check region match
            if profile.supply_regions and state:
                if state in profile.supply_regions:
                    match_reasons.append(f"region:{state}")

            # Check nationwide distribution
            if "nationwide" in distribution:
                match_reasons.append("nationwide_distribution")

            # If any matches, add tenant
            if match_reasons:
                matched_tenants.append({
                    "tenant_id": profile.tenant_id,
                    "match_reasons": match_reasons,
                })

        logger.info(
            "recall_matched",
            recall_firm=recalling_firm,
            matched_tenant_count=len(matched_tenants),
        )

        return matched_tenants

    async def create_alerts_for_recall(
        self,
        recall_data: Dict[str, Any],
    ) -> List[ComplianceAlertModel]:
        """Create alerts for all tenants affected by a recall."""
        matches = await self.match_recall_to_tenants(recall_data)
        alerts = []

        # Determine severity from classification
        classification = recall_data.get("classification", "")
        if "Class I" in classification:
            severity = AlertSeverity.CRITICAL
            countdown_hours = 24
        elif "Class II" in classification:
            severity = AlertSeverity.HIGH
            countdown_hours = 24
        else:
            severity = AlertSeverity.MEDIUM
            countdown_hours = 48

        for match in matches:
            alert = await self.create_alert(
                tenant_id=match["tenant_id"],
                source_type=AlertSourceType.FDA_RECALL,
                source_id=recall_data.get("recall_number", str(uuid4())),
                title=f"FDA {classification} Recall: {recall_data.get('recalling_firm', 'Unknown')}",
                summary=recall_data.get("reason_for_recall", ""),
                severity=severity,
                countdown_hours=countdown_hours,
                required_actions=[
                    {"action": "Review affected lot codes", "completed": False},
                    {"action": "Run trace-forward analysis", "completed": False},
                    {"action": "Prepare FDA response if required", "completed": False},
                ],
                match_reason={"matched_by": match["match_reasons"]},
                raw_data=recall_data,
            )
            alerts.append(alert)

        return alerts
