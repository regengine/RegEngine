"""Integration between scheduler and compliance service.

This module connects the regulatory scrapers to the compliance state machine,
creating alerts for tenants when recalls match their product profile.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from uuid import UUID

import structlog
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker, Session

# Standardized path discovery via shared utility
from shared.paths import ensure_shared_importable
ensure_shared_importable()

from scheduler.app.models import EnforcementItem, EnforcementSeverity, SourceType
from scheduler.app.config import get_settings

logger = structlog.get_logger("compliance.integration")


class ComplianceIntegration:
    """Bridges scheduler scrapers to compliance service.
    
    When the scheduler detects a new FDA recall, this integration:
    1. Queries all tenant product profiles
    2. Matches recall to affected tenants
    3. Creates compliance alerts with countdown timers
    4. Triggers notifications
    """
    
    def __init__(self, database_url: Optional[str] = None):
        settings = get_settings()
        self.database_url = database_url or settings.database_url
        self.engine = create_engine(self.database_url)
        self.Session = sessionmaker(bind=self.engine)
    
    def process_enforcement_item(self, item: EnforcementItem) -> List[UUID]:
        """Process an enforcement item and create alerts for affected tenants.
        
        Args:
            item: The enforcement item from a scraper
            
        Returns:
            List of tenant IDs that received alerts
        """
        if item.source_type not in [SourceType.FDA_RECALL, SourceType.FDA_WARNING_LETTER]:
            logger.debug("skipping_non_alert_item", source_type=item.source_type.value)
            return []
        
        with self.Session() as session:
            # Find matching tenants
            matching_tenants = self._find_matching_tenants(session, item)
            
            if not matching_tenants:
                logger.info(
                    "no_matching_tenants",
                    source_type=item.source_type.value,
                    source_id=item.source_id,
                )
                return []
            
            # Create alerts for each matching tenant
            alerted_tenants = []
            for match in matching_tenants:
                try:
                    alert_id = self._create_alert(session, match["tenant_id"], item, match["reasons"])
                    if alert_id:
                        alerted_tenants.append(match["tenant_id"])
                        logger.warning(
                            "compliance_alert_created",
                            tenant_id=str(match["tenant_id"]),
                            source_id=item.source_id,
                            severity=item.severity.value,
                        )
                except Exception as e:
                    logger.error(
                        "alert_creation_failed",
                        tenant_id=str(match["tenant_id"]),
                        error=str(e),
                    )
            
            session.commit()
            return alerted_tenants
    
    def _find_matching_tenants(
        self, session: Session, item: EnforcementItem
    ) -> List[Dict]:
        """Find tenants whose product profile matches the enforcement item.

        Matching tiers (highest confidence first):
          Tier 1 — exact lot-code match against fsma.traceability_events
          Tier 2 — supplier name containment from tenant_product_profile
          Tier 3 — product category / FTL keyword overlap
        """
        # ------------------------------------------------------------------
        # Tier 1: Exact lot-code match against traceability events
        # ------------------------------------------------------------------
        tier1_tenants: Dict[str, List[str]] = {}  # tenant_id str -> reasons

        code_info = (item.raw_data or {}).get("code_info", "")
        if code_info:
            raw_tokens = re.split(r"[,;\n]+", code_info)
            lot_codes = [t.strip() for t in raw_tokens if t.strip()]

            if lot_codes:
                try:
                    tlc_rows = session.execute(
                        text(
                            """
                            SELECT DISTINCT tenant_id
                            FROM fsma.traceability_events
                            WHERE traceability_lot_code = ANY(:lot_codes)
                            """
                        ),
                        {"lot_codes": lot_codes},
                    )
                    for row in tlc_rows:
                        tid = str(row[0])
                        tier1_tenants[tid] = ["match_tier:lot_code"]
                    if tier1_tenants:
                        logger.info(
                            "tier1_lot_code_matches",
                            count=len(tier1_tenants),
                            lot_codes_checked=len(lot_codes),
                        )
                except Exception as e:
                    logger.warning("tier1_lot_code_query_failed", error=str(e))

        # ------------------------------------------------------------------
        # Tier 2 / 3: Profile-based matching via tenant_product_profile
        # ------------------------------------------------------------------
        # Query tenant product profiles
        result = session.execute(
            "SELECT tenant_id, product_categories, supply_regions, supplier_identifiers FROM tenant_product_profile LIMIT 1000"
        )

        matching = []

        # Build matching keywords from item
        item_text = f"{item.title} {item.summary or ''}"
        item_text_lower = item_text.lower()
        
        # Common FTL (Food Traceability List) keywords
        ftl_keywords = [
            "lettuce", "romaine", "spinach", "leaf", "salad", "greens",
            "pepper", "tomato", "cucumber", "cheese", "nut butter",
            "sprout", "finfish", "shellfish", "egg",
        ]
        
        for row in result:
            tenant_id = row[0]
            categories = row[1] or []
            regions = row[2] or []
            suppliers = row[3] or []
            
            match_reasons = []
            
            # Check product category overlap
            for category in categories:
                if category.lower() in item_text_lower:
                    match_reasons.append(f"product:{category}")
            
            # Check FTL keywords
            for keyword in ftl_keywords:
                if keyword in item_text_lower:
                    if any(k in cat.lower() for cat in categories for k in [keyword, "greens", "produce"]):
                        match_reasons.append(f"ftl_item:{keyword}")
                        break
            
            # Check region overlap
            for company in (item.affected_companies or []):
                for region in regions:
                    if region.upper() in company.upper():
                        match_reasons.append(f"region:{region}")
            
            # Check supplier name match
            for company in (item.affected_companies or []):
                for supplier in suppliers:
                    if supplier.lower() in company.lower() or company.lower() in supplier.lower():
                        match_reasons.append(f"supplier:{supplier}")
            
            # Merge with Tier 1 reasons if this tenant already matched on lot code
            tid_str = str(tenant_id)
            if tid_str in tier1_tenants:
                match_reasons = tier1_tenants.pop(tid_str) + match_reasons

            if match_reasons:
                matching.append({
                    "tenant_id": tenant_id,
                    "reasons": match_reasons,
                })

        # Any Tier 1 tenants not in tenant_product_profile still get an alert
        for tid_str, reasons in tier1_tenants.items():
            matching.append({"tenant_id": tid_str, "reasons": reasons})

        return matching
    
    def _create_alert(
        self,
        session: Session,
        tenant_id: UUID,
        item: EnforcementItem,
        match_reasons: List[str],
    ) -> Optional[str]:
        """Create a compliance alert for a tenant."""
        import json
        from uuid import uuid4
        
        # Determine countdown based on severity
        if item.severity == EnforcementSeverity.CRITICAL:
            countdown_hours = 24
        elif item.severity == EnforcementSeverity.HIGH:
            countdown_hours = 24
        else:
            countdown_hours = 48
        
        # Map source type
        source_type_map = {
            SourceType.FDA_RECALL: "FDA_RECALL",
            SourceType.FDA_WARNING_LETTER: "FDA_WARNING_LETTER",
            SourceType.FDA_IMPORT_ALERT: "FDA_IMPORT_ALERT",
        }
        source_type = source_type_map.get(item.source_type, "FDA_RECALL")
        
        # Map severity
        severity_map = {
            EnforcementSeverity.CRITICAL: "CRITICAL",
            EnforcementSeverity.HIGH: "HIGH",
            EnforcementSeverity.MEDIUM: "MEDIUM",
            EnforcementSeverity.LOW: "LOW",
        }
        severity = severity_map.get(item.severity, "MEDIUM")
        
        alert_id = str(uuid4())
        now = datetime.now(timezone.utc)
        
        required_actions = [
            {"action": "Review affected lot codes", "completed": False},
            {"action": "Run trace-forward analysis", "completed": False},
            {"action": "Prepare FDA response if required", "completed": False},
        ]
        
        match_reason = {"matched_by": match_reasons}
        
        # Insert alert
        session.execute(
            """
            INSERT INTO public.compliance_alerts 
            (id, tenant_id, source_type, source_id, title, summary, severity,
             countdown_start, countdown_end, countdown_hours, required_actions,
             status, match_reason, raw_data, created_at, updated_at)
            VALUES 
            (:id, :tenant_id, :source_type, :source_id, :title, :summary, :severity,
             :countdown_start, :countdown_end, :countdown_hours, :required_actions,
             :status, :match_reason, :raw_data, :created_at, :updated_at)
            ON CONFLICT (tenant_id, source_type, source_id) DO NOTHING
            """,
            {
                "id": alert_id,
                "tenant_id": str(tenant_id),
                "source_type": source_type,
                "source_id": item.source_id,
                "title": item.title,
                "summary": item.summary,
                "severity": severity,
                "countdown_start": now,
                "countdown_end": now + timedelta(hours=countdown_hours),
                "countdown_hours": countdown_hours,
                "required_actions": json.dumps(required_actions),
                "status": "ACTIVE",
                "match_reason": json.dumps(match_reason),
                "raw_data": json.dumps(item.raw_data) if item.raw_data else None,
                "created_at": now,
                "updated_at": now,
            }
        )
        
        # Update tenant status
        self._update_tenant_status(session, tenant_id)
        
        return alert_id
    
    def _update_tenant_status(self, session: Session, tenant_id: UUID) -> None:
        """Recalculate and update tenant compliance status."""
        # Count active alerts
        result = session.execute(
            """
            SELECT 
                COUNT(*) FILTER (WHERE severity = 'CRITICAL' AND status = 'ACTIVE') as critical,
                COUNT(*) FILTER (WHERE severity = 'HIGH' AND status = 'ACTIVE') as high,
                COUNT(*) FILTER (WHERE status = 'ACTIVE') as total
            FROM public.compliance_alerts
            WHERE tenant_id = :tenant_id
            """,
            {"tenant_id": str(tenant_id)}
        ).fetchone()
        
        critical_count = result[0] or 0
        high_count = result[1] or 0
        total_active = result[2] or 0
        
        # Determine status
        if critical_count > 0:
            new_status = "NON_COMPLIANT"
        elif high_count > 0 or total_active > 0:
            new_status = "AT_RISK"
        else:
            new_status = "COMPLIANT"
        
        # Get next deadline
        deadline_result = session.execute(
            """
            SELECT countdown_end, title
            FROM public.compliance_alerts
            WHERE tenant_id = :tenant_id AND status = 'ACTIVE'
            ORDER BY countdown_end ASC
            LIMIT 1
            """,
            {"tenant_id": str(tenant_id)}
        ).fetchone()
        
        next_deadline = deadline_result[0] if deadline_result else None
        next_description = deadline_result[1] if deadline_result else None
        
        now = datetime.now(timezone.utc)
        
        # Upsert status
        session.execute(
            """
            INSERT INTO tenant_compliance_status 
            (id, tenant_id, status, last_status_change, active_alert_count, 
             critical_alert_count, next_deadline, next_deadline_description, created_at, updated_at)
            VALUES 
            (gen_random_uuid(), :tenant_id, :status, :now, :active_count, 
             :critical_count, :next_deadline, :next_description, :now, :now)
            ON CONFLICT (tenant_id) DO UPDATE SET
                status = EXCLUDED.status,
                last_status_change = CASE 
                    WHEN tenant_compliance_status.status != EXCLUDED.status 
                    THEN EXCLUDED.last_status_change 
                    ELSE tenant_compliance_status.last_status_change 
                END,
                active_alert_count = EXCLUDED.active_alert_count,
                critical_alert_count = EXCLUDED.critical_alert_count,
                next_deadline = EXCLUDED.next_deadline,
                next_deadline_description = EXCLUDED.next_deadline_description,
                updated_at = EXCLUDED.updated_at
            """,
            {
                "tenant_id": str(tenant_id),
                "status": new_status,
                "now": now,
                "active_count": total_active,
                "critical_count": critical_count,
                "next_deadline": next_deadline,
                "next_description": next_description,
            }
        )


# Add missing import
from datetime import timedelta


# Singleton for use in scheduler
_integration: Optional[ComplianceIntegration] = None


def get_compliance_integration() -> ComplianceIntegration:
    """Get or create the compliance integration singleton."""
    global _integration
    if _integration is None:
        _integration = ComplianceIntegration()
    return _integration
