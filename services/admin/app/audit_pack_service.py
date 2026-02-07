"""
Audit Pack Service

Generates comprehensive audit packs (JSON-based, PDF-ready) containing:
- Project summary
- Budget analysis
- Compliance findings
- Rule evaluations with source authorities
- Evidence list
"""

import structlog
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, List, Any
from uuid import UUID

logger = structlog.get_logger(__name__)


class AuditPackService:
    """
    Service for generating comprehensive audit packs.
    
    Audit packs compile all compliance-related data for a project
    into a structured format suitable for PDF generation.
    """
    
    def __init__(self, db_session, tenant_id: UUID):
        """
        Initialize the service.
        
        Args:
            db_session: SQLAlchemy database session
            tenant_id: Current tenant ID
        """
        self.db = db_session
        self.tenant_id = tenant_id
    
    def generate_audit_pack(
        self,
        project_id: UUID,
        snapshot_id: Optional[UUID] = None,
        include_evidence_list: bool = True,
        include_budget_summary: bool = True
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive audit pack for a project.
        
        Args:
            project_id: Project to generate pack for
            snapshot_id: Optional specific snapshot to use
            include_evidence_list: Include evidence inventory
            include_budget_summary: Include budget analysis
            
        Returns:
            Structured audit pack dict
        """
        from .pcos_models import (
            PCOSProjectModel,
            PCOSCompanyModel,
            PCOSComplianceSnapshotModel,
            PCOSRuleEvaluationModel,
            PCOSBudgetModel,
            PCOSBudgetLineItemModel,
            PCOSEngagementModel,
            PCOSLocationModel,
            PCOSEvidenceModel,
            PCOSTaskModel,
        )
        from sqlalchemy import select, func
        
        # Get project
        project = self.db.execute(
            select(PCOSProjectModel)
            .where(PCOSProjectModel.id == project_id)
            .where(PCOSProjectModel.tenant_id == self.tenant_id)
        ).scalar_one_or_none()
        
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        # Get company
        company = self.db.execute(
            select(PCOSCompanyModel)
            .where(PCOSCompanyModel.id == project.company_id)
            .where(PCOSCompanyModel.tenant_id == self.tenant_id)
        ).scalar_one_or_none()
        
        # Get snapshot (latest if not specified)
        if snapshot_id:
            snapshot = self.db.execute(
                select(PCOSComplianceSnapshotModel)
                .where(PCOSComplianceSnapshotModel.id == snapshot_id)
                .where(PCOSComplianceSnapshotModel.tenant_id == self.tenant_id)
            ).scalar_one_or_none()
        else:
            snapshot = self.db.execute(
                select(PCOSComplianceSnapshotModel)
                .where(PCOSComplianceSnapshotModel.project_id == project_id)
                .where(PCOSComplianceSnapshotModel.tenant_id == self.tenant_id)
                .order_by(PCOSComplianceSnapshotModel.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
        
        # Build audit pack
        pack = {
            "generated_at": datetime.utcnow().isoformat(),
            "pack_version": "1.0",
            "project": self._build_project_summary(project, company),
            "compliance_summary": self._build_compliance_summary(snapshot) if snapshot else None,
            "rule_evaluations": self._build_evaluation_summary(snapshot.id if snapshot else None),
            "findings_by_category": self._build_findings_summary(project_id),
        }
        
        if include_budget_summary:
            pack["budget_summary"] = self._build_budget_summary(project_id)
        
        if include_evidence_list:
            pack["evidence_inventory"] = self._build_evidence_inventory(project_id)
        
        pack["attestation"] = self._build_attestation_info(snapshot) if snapshot else None
        
        return pack
    
    def _build_project_summary(self, project, company) -> Dict:
        """Build project overview section."""
        return {
            "project_id": str(project.id),
            "project_name": project.name,
            "project_code": project.code,
            "project_type": project.project_type,
            "gate_state": project.gate_state,
            "risk_score": project.risk_score,
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "end_date": project.end_date.isoformat() if project.end_date else None,
            "first_shoot_date": project.first_shoot_date.isoformat() if project.first_shoot_date else None,
            "wrap_date": project.wrap_date.isoformat() if project.wrap_date else None,
            "company": {
                "name": company.name if company else None,
                "primary_contact": company.primary_contact_name if company else None,
                "address": f"{company.city}, {company.state}" if company else None
            } if company else None
        }
    
    def _build_compliance_summary(self, snapshot) -> Dict:
        """Build compliance snapshot summary."""
        return {
            "snapshot_id": str(snapshot.id),
            "snapshot_date": snapshot.created_at.isoformat(),
            "snapshot_type": snapshot.snapshot_type,
            "overall_status": snapshot.compliance_status,
            "overall_score": snapshot.overall_score,
            "metrics": {
                "total_rules_evaluated": snapshot.total_rules_evaluated,
                "passed": snapshot.rules_passed,
                "failed": snapshot.rules_failed,
                "warnings": snapshot.rules_warning,
                "pass_rate_pct": round(snapshot.rules_passed / snapshot.total_rules_evaluated * 100, 1) if snapshot.total_rules_evaluated > 0 else 0
            },
            "category_scores": snapshot.category_scores,
            "delta_from_previous": snapshot.delta_summary
        }
    
    def _build_evaluation_summary(self, snapshot_id: Optional[UUID]) -> List[Dict]:
        """Build rule evaluation summary grouped by category."""
        from .pcos_models import PCOSRuleEvaluationModel
        from sqlalchemy import select
        
        if not snapshot_id:
            return []
        
        evaluations = self.db.execute(
            select(PCOSRuleEvaluationModel)
            .where(PCOSRuleEvaluationModel.snapshot_id == snapshot_id)
            .order_by(PCOSRuleEvaluationModel.rule_category, PCOSRuleEvaluationModel.result)
        ).scalars().all()
        
        by_category = {}
        for e in evaluations:
            if e.rule_category not in by_category:
                by_category[e.rule_category] = []
            
            by_category[e.rule_category].append({
                "rule_code": e.rule_code,
                "rule_name": e.rule_name,
                "result": e.result,
                "severity": e.severity,
                "message": e.message,
                "source_authorities": e.source_authorities
            })
        
        return [
            {"category": cat, "evaluations": evals}
            for cat, evals in by_category.items()
        ]
    
    def _build_findings_summary(self, project_id: UUID) -> Dict:
        """Build summary of compliance findings/tasks."""
        from .pcos_models import PCOSTaskModel
        from sqlalchemy import select, func
        
        # Count tasks by status
        tasks = self.db.execute(
            select(PCOSTaskModel)
            .where(PCOSTaskModel.project_id == project_id)
            .where(PCOSTaskModel.tenant_id == self.tenant_id)
        ).scalars().all()
        
        by_status = {}
        by_category = {}
        for t in tasks:
            status = t.status or "unknown"
            by_status[status] = by_status.get(status, 0) + 1
            
            cat = t.task_type or "other"
            by_category[cat] = by_category.get(cat, 0) + 1
        
        open_critical = sum(
            1 for t in tasks
            if t.status not in ("completed", "resolved") and t.priority == "critical"
        )
        
        return {
            "total_findings": len(tasks),
            "by_status": by_status,
            "by_category": by_category,
            "open_critical_count": open_critical
        }
    
    def _build_budget_summary(self, project_id: UUID) -> Dict:
        """Build budget analysis summary."""
        from .pcos_models import PCOSBudgetModel, PCOSBudgetLineItemModel
        from sqlalchemy import select, func
        
        budget = self.db.execute(
            select(PCOSBudgetModel)
            .where(PCOSBudgetModel.project_id == project_id)
            .where(PCOSBudgetModel.tenant_id == self.tenant_id)
            .where(PCOSBudgetModel.is_active == True)
        ).scalar_one_or_none()
        
        if not budget:
            return {"status": "no_active_budget"}
        
        line_items = self.db.execute(
            select(PCOSBudgetLineItemModel)
            .where(PCOSBudgetLineItemModel.budget_id == budget.id)
            .where(PCOSBudgetLineItemModel.tenant_id == self.tenant_id)
        ).scalars().all()
        
        # Department breakdown
        dept_totals = {}
        for item in line_items:
            dept = item.department or "Other"
            if dept not in dept_totals:
                dept_totals[dept] = Decimal("0")
            dept_totals[dept] += item.total_cost or Decimal("0")
        
        return {
            "budget_id": str(budget.id),
            "source_file": budget.source_file_name,
            "grand_total": float(budget.grand_total) if budget.grand_total else 0,
            "line_item_count": len(line_items),
            "department_breakdown": {k: float(v) for k, v in dept_totals.items()},
            "detected_location": budget.detected_location
        }
    
    def _build_evidence_inventory(self, project_id: UUID) -> List[Dict]:
        """Build inventory of all evidence documents."""
        from .pcos_models import PCOSEvidenceModel
        from sqlalchemy import select
        
        evidence = self.db.execute(
            select(PCOSEvidenceModel)
            .where(PCOSEvidenceModel.project_id == project_id)
            .where(PCOSEvidenceModel.tenant_id == self.tenant_id)
            .order_by(PCOSEvidenceModel.created_at.desc())
        ).scalars().all()
        
        return [
            {
                "evidence_id": str(e.id),
                "title": e.title,
                "document_type": e.document_type,
                "file_name": e.file_name,
                "file_size_bytes": e.file_size,
                "uploaded_at": e.created_at.isoformat(),
                "verification_status": e.verification_status
            }
            for e in evidence
        ]
    
    def _build_attestation_info(self, snapshot) -> Dict:
        """Build attestation information."""
        return {
            "is_attested": snapshot.is_attested,
            "attested_at": snapshot.attested_at.isoformat() if snapshot.attested_at else None,
            "attestation_signature_id": snapshot.attestation_signature_id,
            "attestation_notes": snapshot.attestation_notes
        }


def generate_audit_pack(
    db_session,
    tenant_id: UUID,
    project_id: UUID,
    snapshot_id: Optional[UUID] = None
) -> Dict[str, Any]:
    """
    Convenience function to generate an audit pack.
    
    Returns structured data suitable for PDF generation.
    """
    service = AuditPackService(db_session, tenant_id)
    return service.generate_audit_pack(project_id, snapshot_id)
