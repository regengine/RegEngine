"""Synchronous compliance service layer for the 2am Alert feature.

This is the sync version compatible with the existing SQLAlchemy sync session.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

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
from .pcos_models import PCOSComplianceSnapshotModel as ComplianceSnapshotModel

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
        "FDA_RECALL": "21 CFR §1.134",
        "FDA_WARNING": "21 CFR §1.401",
        "IMPORT_ALERT": "21 CFR §1.285",
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
        """Create a new compliance alert.
        
        For CRITICAL and HIGH severity alerts, automatically creates
        a bound snapshot with deadline and regulatory citation.
        """
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
        
        # Auto-create bound snapshot for CRITICAL and HIGH alerts
        if severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH):
            self._create_triggered_snapshot(
                tenant_id=tenant_id,
                alert=alert,
                countdown_end=countdown_end,
            )
        
        return alert

    def _create_triggered_snapshot(
        self,
        tenant_id: UUID,
        alert: ComplianceAlertModel,
        countdown_end: datetime,
    ) -> ComplianceSnapshotModel:
        """Create a snapshot triggered by an alert.
        
        This snapshot is bound to the alert and requires attestation
        before the alert can be resolved.
        """
        now = datetime.now(timezone.utc)
        
        # Get regulatory citation based on source type
        citation = self.REGULATORY_CITATIONS.get(
            alert.source_type, 
            "FSMA 204 - Compliance Requirement"
        )
        
        # Capture current status
        status_data = self.get_status(tenant_id)
        active_alerts = status_data.pop("active_alerts", [])
        
        # Capture current profile
        profile = self.get_product_profile(tenant_id)
        profile_data = profile.to_dict() if profile else {}
        
        # Compute integrity hash
        content_hash = ComplianceSnapshotModel.compute_hash(
            status_snapshot=status_data,
            alerts_snapshot=active_alerts,
            profile_snapshot=profile_data,
        )
        
        # Create snapshot bound to alert
        snapshot = ComplianceSnapshotModel(
            tenant_id=tenant_id,
            snapshot_name=f"Alert [{alert.severity}] — {alert.title}",
            snapshot_reason=f"Auto-created: {alert.summary or alert.title}",
            created_by="SYSTEM",
            # Trigger binding
            trigger_alert_id=alert.id,
            is_auto_created=True,
            # Deadline + citation
            deadline=countdown_end,
            regulatory_citation=citation,
            # Status
            compliance_status=status_data.get("status", "UNKNOWN"),
            active_alert_count=len(active_alerts),
            critical_alert_count=status_data.get("critical_alert_count", 0),
            completeness_score=status_data.get("completeness_score", 1.0),
            alerts_snapshot=active_alerts,
            profile_snapshot=profile_data,
            status_snapshot=status_data,
            content_hash=content_hash,
            captured_at=now,
        )
        
        self.session.add(snapshot)
        self.session.commit()
        self.session.refresh(snapshot)
        
        logger.info(
            "triggered_snapshot_created",
            tenant_id=str(tenant_id),
            snapshot_id=str(snapshot.id),
            alert_id=str(alert.id),
            deadline=countdown_end.isoformat(),
            citation=citation,
        )
        
        return snapshot


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

    # =========================================================================
    # SNAPSHOT OPERATIONS
    # =========================================================================

    def create_snapshot(
        self,
        tenant_id: UUID,
        snapshot_name: str,
        created_by: str,
        snapshot_reason: Optional[str] = None,
    ) -> ComplianceSnapshotModel:
        """Create a point-in-time compliance snapshot.
        
        Captures the current compliance state with cryptographic hash
        for audit defense.
        """
        now = datetime.now(timezone.utc)
        
        # Capture current status
        status_data = self.get_status(tenant_id)
        active_alerts = status_data.pop("active_alerts", [])
        
        # Capture current profile
        profile = self.get_product_profile(tenant_id)
        profile_data = profile.to_dict() if profile else {}
        
        # Compute integrity hash
        content_hash = ComplianceSnapshotModel.compute_hash(
            status_snapshot=status_data,
            alerts_snapshot=active_alerts,
            profile_snapshot=profile_data,
        )
        
        # Create snapshot
        snapshot = ComplianceSnapshotModel(
            tenant_id=tenant_id,
            snapshot_name=snapshot_name,
            snapshot_reason=snapshot_reason,
            created_by=created_by,
            compliance_status=status_data.get("status", "UNKNOWN"),
            active_alert_count=len(active_alerts),
            critical_alert_count=status_data.get("critical_alert_count", 0),
            completeness_score=status_data.get("completeness_score", 1.0),
            alerts_snapshot=active_alerts,
            profile_snapshot=profile_data,
            status_snapshot=status_data,
            content_hash=content_hash,
            captured_at=now,
        )
        
        self.session.add(snapshot)
        self.session.commit()
        self.session.refresh(snapshot)
        
        logger.info(
            "snapshot_created",
            tenant_id=str(tenant_id),
            snapshot_id=str(snapshot.id),
            snapshot_name=snapshot_name,
            compliance_status=snapshot.compliance_status,
            content_hash=content_hash[:16] + "...",
        )
        
        return snapshot

    def list_snapshots(
        self,
        tenant_id: UUID,
        limit: int = 50,
    ) -> List[ComplianceSnapshotModel]:
        """List snapshots for a tenant, newest first.
        
        Automatically refreshes degradation state on each retrieval.
        """
        result = self.session.execute(
            select(ComplianceSnapshotModel)
            .where(ComplianceSnapshotModel.tenant_id == tenant_id)
            .order_by(desc(ComplianceSnapshotModel.captured_at))
            .limit(limit)
        )
        snapshots = result.scalars().all()
        
        # Get current alert counts for degradation check
        status = self.get_status(tenant_id)
        current_alert_count = status.get("active_alert_count", 0)
        current_critical_count = status.get("critical_alert_count", 0)
        
        # Refresh degradation state for each snapshot
        for snapshot in snapshots:
            self._refresh_degradation(snapshot, current_alert_count, current_critical_count)
        
        return snapshots

    def _refresh_degradation(
        self,
        snapshot: ComplianceSnapshotModel,
        current_alert_count: int = 0,
        current_critical_count: int = 0,
    ) -> None:
        """Refresh snapshot degradation state."""
        new_state, reason = snapshot.calculate_degradation(
            current_alert_count, current_critical_count
        )
        
        if snapshot.snapshot_state != new_state:
            old_state = snapshot.snapshot_state
            snapshot.snapshot_state = new_state
            snapshot.degradation_reason = reason
            snapshot.last_state_check = datetime.now(timezone.utc)
            self.session.commit()
            
            logger.info(
                "snapshot_degraded",
                snapshot_id=str(snapshot.id),
                old_state=old_state,
                new_state=new_state,
                reason=reason,
            )

    def get_snapshot(self, snapshot_id: UUID) -> Optional[ComplianceSnapshotModel]:
        """Get a single snapshot by ID."""
        result = self.session.execute(
            select(ComplianceSnapshotModel).where(
                ComplianceSnapshotModel.id == snapshot_id
            )
        )
        return result.scalar_one_or_none()

    def verify_snapshot_integrity(
        self,
        snapshot_id: UUID,
        verified_by: str,
    ) -> Dict[str, Any]:
        """Verify snapshot integrity and optionally mark as verified."""
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            return {"error": "Snapshot not found"}
        
        is_valid = snapshot.verify_integrity()
        
        # Recompute hash for comparison
        recomputed_hash = ComplianceSnapshotModel.compute_hash(
            snapshot.status_snapshot or {},
            snapshot.alerts_snapshot or [],
            snapshot.profile_snapshot or {},
        )
        
        result = {
            "snapshot_id": str(snapshot_id),
            "is_valid": is_valid,
            "stored_hash": snapshot.content_hash,
            "computed_hash": recomputed_hash,
            "hash_match": snapshot.content_hash == recomputed_hash,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "verified_by": verified_by,
        }
        
        if is_valid:
            snapshot.is_verified = True
            snapshot.verified_at = datetime.now(timezone.utc)
            snapshot.verified_by = verified_by
            self.session.commit()
            
        logger.info(
            "snapshot_verified",
            snapshot_id=str(snapshot_id),
            is_valid=is_valid,
        )
        
        return result

    def export_snapshot(
        self,
        snapshot_id: UUID,
        format: str = "json",
    ) -> Dict[str, Any]:
        """Export snapshot in audit-ready format."""
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            return {"error": "Snapshot not found"}
        
        return snapshot.to_export_dict()

    def attest_snapshot(
        self,
        snapshot_id: UUID,
        attested_by: str,
        attestation_title: str,
    ) -> Dict[str, Any]:
        """Attest to a snapshot, taking owner accountability.
        
        This creates a legal binding between the person and the compliance state.
        Required before resolving alerts bound to this snapshot.
        """
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            return {"error": "Snapshot not found"}
        
        if snapshot.is_attested:
            return {
                "error": "Snapshot already attested",
                "attested_by": snapshot.attested_by,
                "attested_at": snapshot.attested_at.isoformat() if snapshot.attested_at else None,
            }
        
        now = datetime.now(timezone.utc)
        snapshot.attested_by = attested_by
        snapshot.attested_at = now
        snapshot.attestation_title = attestation_title
        
        self.session.commit()
        self.session.refresh(snapshot)
        
        logger.info(
            "snapshot_attested",
            snapshot_id=str(snapshot_id),
            attested_by=attested_by,
            attestation_title=attestation_title,
        )
        
        return {
            "snapshot_id": str(snapshot_id),
            "attested_by": attested_by,
            "attestation_title": attestation_title,
            "attested_at": now.isoformat(),
            "is_attested": True,
        }

    def get_snapshot_for_alert(self, alert_id: UUID) -> Optional[ComplianceSnapshotModel]:
        """Get the snapshot bound to a specific alert."""
        result = self.session.execute(
            select(ComplianceSnapshotModel).where(
                ComplianceSnapshotModel.trigger_alert_id == alert_id
            )
        )
        return result.scalar_one_or_none()

    def refreeze_snapshot(
        self,
        original_snapshot_id: UUID,
        created_by: str,
    ) -> ComplianceSnapshotModel:
        """Create a fresh snapshot from a stale/invalid one.
        
        Captures current state with reference to the original snapshot.
        Use when an old snapshot has degraded.
        """
        original = self.get_snapshot(original_snapshot_id)
        if not original:
            raise ValueError("Original snapshot not found")
        
        now = datetime.now(timezone.utc)
        
        # Capture current status
        status_data = self.get_status(original.tenant_id)
        active_alerts = status_data.pop("active_alerts", [])
        
        # Capture current profile
        profile = self.get_product_profile(original.tenant_id)
        profile_data = profile.to_dict() if profile else {}
        
        # Compute integrity hash
        content_hash = ComplianceSnapshotModel.compute_hash(
            status_snapshot=status_data,
            alerts_snapshot=active_alerts,
            profile_snapshot=profile_data,
        )
        
        # Create fresh snapshot
        snapshot = ComplianceSnapshotModel(
            tenant_id=original.tenant_id,
            snapshot_name=f"Re-freeze: {original.snapshot_name}",
            snapshot_reason=f"Re-frozen from degraded snapshot {str(original.id)[:8]}...",
            created_by=created_by,
            # Inherit trigger if applicable
            trigger_alert_id=original.trigger_alert_id,
            is_auto_created=False,
            # Copy deadline and citation
            deadline=original.deadline,
            regulatory_citation=original.regulatory_citation,
            # Status
            compliance_status=status_data.get("status", "UNKNOWN"),
            active_alert_count=len(active_alerts),
            critical_alert_count=status_data.get("critical_alert_count", 0),
            completeness_score=status_data.get("completeness_score", 1.0),
            alerts_snapshot=active_alerts,
            profile_snapshot=profile_data,
            status_snapshot=status_data,
            content_hash=content_hash,
            captured_at=now,
        )
        
        self.session.add(snapshot)
        self.session.commit()
        self.session.refresh(snapshot)
        
        logger.info(
            "snapshot_refrozen",
            original_id=str(original_snapshot_id),
            new_id=str(snapshot.id),
            created_by=created_by,
        )
        
        return snapshot

    def generate_fda_response(self, snapshot_id: UUID) -> Dict[str, Any]:
        """Generate regulator-grade explanation for FDA response.
        
        Returns pre-formatted text that can be pasted directly
        into a regulatory response document.
        """
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            return {"error": "Snapshot not found"}
        
        # Build alert summary
        alerts_summary = ""
        for alert in (snapshot.alerts_snapshot or []):
            alerts_summary += f"  - {alert.get('title', 'Untitled')} (Severity: {alert.get('severity', 'Unknown')})\n"
        if not alerts_summary:
            alerts_summary = "  - No active alerts at time of capture\n"
        
        # Build attestation line
        attestation_line = ""
        if snapshot.is_attested:
            attestation_line = f"""
ATTESTATION:
This compliance state was attested by {snapshot.attested_by} ({snapshot.attestation_title}) 
on {snapshot.attested_at.strftime('%B %d, %Y at %H:%M UTC') if snapshot.attested_at else 'N/A'}.
"""
        
        # Generate the response
        fda_text = f"""
================================================================================
                     COMPLIANCE STATE CERTIFICATION
================================================================================

SNAPSHOT IDENTIFIER: {str(snapshot.id)}
CAPTURE TIMESTAMP: {snapshot.captured_at.strftime('%B %d, %Y at %H:%M:%S UTC') if snapshot.captured_at else 'N/A'}
HASH (SHA-256): {snapshot.content_hash}
INTEGRITY VERIFIED: {'✓ PASS' if snapshot.verify_integrity() else '✗ FAIL'}

--------------------------------------------------------------------------------
                         COMPLIANCE STATUS
--------------------------------------------------------------------------------

STATUS: {snapshot.compliance_status} {snapshot._get_status_emoji()}
ACTIVE ALERTS: {snapshot.active_alert_count}
CRITICAL ALERTS: {snapshot.critical_alert_count}
{f'REGULATORY CITATION: {snapshot.regulatory_citation}' if snapshot.regulatory_citation else ''}

--------------------------------------------------------------------------------
                         ALERT DETAILS
--------------------------------------------------------------------------------

{alerts_summary}
{attestation_line}
--------------------------------------------------------------------------------
                         CRYPTOGRAPHIC VERIFICATION
--------------------------------------------------------------------------------

This document represents a cryptographically verified point-in-time capture
of our compliance state. The SHA-256 hash above can be independently verified
against our systems to confirm this record has not been altered.

================================================================================
                    END OF COMPLIANCE CERTIFICATION
================================================================================
"""
        
        return {
            "snapshot_id": str(snapshot_id),
            "format": "fda_response",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "text": fda_text.strip(),
            "metadata": {
                "compliance_status": snapshot.compliance_status,
                "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
                "hash": snapshot.content_hash,
                "is_attested": snapshot.is_attested,
            }
        }

    def diff_snapshots(
        self,
        snapshot_id_a: UUID,
        snapshot_id_b: UUID,
    ) -> Dict[str, Any]:
        """Compare two snapshots and return the differences.
        
        Useful for showing what changed between compliance states.
        """
        snapshot_a = self.get_snapshot(snapshot_id_a)
        snapshot_b = self.get_snapshot(snapshot_id_b)
        
        if not snapshot_a or not snapshot_b:
            return {"error": "One or both snapshots not found"}
        
        # Ensure A is older than B
        if snapshot_a.captured_at > snapshot_b.captured_at:
            snapshot_a, snapshot_b = snapshot_b, snapshot_a
        
        changes = []
        
        # Compare compliance status
        if snapshot_a.compliance_status != snapshot_b.compliance_status:
            changes.append({
                "field": "compliance_status",
                "label": "Compliance Status",
                "before": f"{snapshot_a._get_status_emoji()} {snapshot_a.compliance_status}",
                "after": f"{snapshot_b._get_status_emoji()} {snapshot_b.compliance_status}",
                "severity": "high" if snapshot_b.compliance_status == "NON_COMPLIANT" else "medium",
            })
        
        # Compare alert counts
        if snapshot_a.active_alert_count != snapshot_b.active_alert_count:
            diff = snapshot_b.active_alert_count - snapshot_a.active_alert_count
            changes.append({
                "field": "active_alert_count",
                "label": "Active Alerts",
                "before": str(snapshot_a.active_alert_count),
                "after": str(snapshot_b.active_alert_count),
                "diff": f"+{diff}" if diff > 0 else str(diff),
                "severity": "high" if diff > 0 else "low",
            })
        
        if snapshot_a.critical_alert_count != snapshot_b.critical_alert_count:
            diff = snapshot_b.critical_alert_count - snapshot_a.critical_alert_count
            changes.append({
                "field": "critical_alert_count",
                "label": "Critical Alerts",
                "before": str(snapshot_a.critical_alert_count),
                "after": str(snapshot_b.critical_alert_count),
                "diff": f"+{diff}" if diff > 0 else str(diff),
                "severity": "critical" if diff > 0 else "low",
            })
        
        # Compare alert lists (what was added/removed)
        alerts_a = {a.get("id", a.get("title", str(i))): a for i, a in enumerate(snapshot_a.alerts_snapshot or [])}
        alerts_b = {a.get("id", a.get("title", str(i))): a for i, a in enumerate(snapshot_b.alerts_snapshot or [])}
        
        added_alerts = []
        removed_alerts = []
        
        for key, alert in alerts_b.items():
            if key not in alerts_a:
                added_alerts.append(alert.get("title", "Unknown Alert"))
        
        for key, alert in alerts_a.items():
            if key not in alerts_b:
                removed_alerts.append(alert.get("title", "Unknown Alert"))
        
        if added_alerts:
            changes.append({
                "field": "alerts_added",
                "label": "New Alerts",
                "before": "-",
                "after": ", ".join(added_alerts),
                "severity": "high",
            })
        
        if removed_alerts:
            changes.append({
                "field": "alerts_removed",
                "label": "Resolved Alerts",
                "before": ", ".join(removed_alerts),
                "after": "-",
                "severity": "positive",
            })
        
        return {
            "snapshot_a": {
                "id": str(snapshot_a.id),
                "name": snapshot_a.snapshot_name,
                "captured_at": snapshot_a.captured_at.isoformat() if snapshot_a.captured_at else None,
            },
            "snapshot_b": {
                "id": str(snapshot_b.id),
                "name": snapshot_b.snapshot_name,
                "captured_at": snapshot_b.captured_at.isoformat() if snapshot_b.captured_at else None,
            },
            "changes": changes,
            "total_changes": len(changes),
            "has_critical_changes": any(c.get("severity") == "critical" for c in changes),
        }
