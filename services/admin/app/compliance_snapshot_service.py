"""
Compliance Snapshot Service

Creates point-in-time compliance snapshots by running all available
rule evaluations and storing the aggregate results.
"""

import structlog
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, List, Any, Tuple
from uuid import UUID

logger = structlog.get_logger(__name__)


class ComplianceSnapshotService:
    """
    Service for creating and comparing compliance snapshots.
    
    A snapshot captures the compliance state of a project at a point in time
    by running all applicable rule evaluations and storing the results.
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
    
    def create_snapshot(
        self,
        project_id: UUID,
        snapshot_type: str = "manual",
        snapshot_name: Optional[str] = None,
        triggered_by: Optional[UUID] = None,
        trigger_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new compliance snapshot for a project.
        
        Args:
            project_id: Project to snapshot
            snapshot_type: 'manual', 'pre_greenlight', 'scheduled', 'post_wrap'
            snapshot_name: Optional name for the snapshot
            triggered_by: User who triggered the snapshot
            trigger_reason: Reason for creating snapshot
            
        Returns:
            Snapshot summary dict
        """
        from .pcos_models import (
            PCOSProjectModel,
            PCOSComplianceSnapshotModel,
            PCOSRuleEvaluationModel,
            PCOSBudgetModel,
            PCOSEngagementModel,
            PCOSLocationModel,
        )
        from sqlalchemy import select
        
        # Get project
        project = self.db.execute(
            select(PCOSProjectModel)
            .where(PCOSProjectModel.id == project_id)
            .where(PCOSProjectModel.tenant_id == self.tenant_id)
        ).scalar_one_or_none()
        
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        # Get previous snapshot for delta calculation
        previous = self.db.execute(
            select(PCOSComplianceSnapshotModel)
            .where(PCOSComplianceSnapshotModel.project_id == project_id)
            .where(PCOSComplianceSnapshotModel.tenant_id == self.tenant_id)
            .order_by(PCOSComplianceSnapshotModel.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        
        # Run all rule evaluations
        evaluations = self._run_all_evaluations(project_id)
        
        # Calculate category scores
        category_scores = {}
        for eval_data in evaluations:
            cat = eval_data["rule_category"]
            if cat not in category_scores:
                category_scores[cat] = {"evaluated": 0, "passed": 0, "failed": 0, "warning": 0}
            
            category_scores[cat]["evaluated"] += 1
            if eval_data["result"] == "pass":
                category_scores[cat]["passed"] += 1
            elif eval_data["result"] == "fail":
                category_scores[cat]["failed"] += 1
            elif eval_data["result"] == "warning":
                category_scores[cat]["warning"] += 1
        
        # Calculate per-category scores
        for cat in category_scores:
            data = category_scores[cat]
            if data["evaluated"] > 0:
                data["score"] = int((data["passed"] / data["evaluated"]) * 100)
        
        # Aggregate totals
        total_evaluated = len(evaluations)
        total_passed = sum(1 for e in evaluations if e["result"] == "pass")
        total_failed = sum(1 for e in evaluations if e["result"] == "fail")
        total_warning = sum(1 for e in evaluations if e["result"] == "warning")
        
        overall_score = int((total_passed / total_evaluated) * 100) if total_evaluated > 0 else 0
        
        # Determine compliance status
        if total_failed == 0 and total_warning == 0:
            compliance_status = "compliant"
        elif total_failed == 0:
            compliance_status = "partial"
        else:
            compliance_status = "non_compliant"
        
        # Calculate delta from previous
        delta_summary = None
        if previous:
            delta_summary = {
                "new_failures": max(0, total_failed - previous.rules_failed),
                "resolved_failures": max(0, previous.rules_failed - total_failed),
                "score_change": overall_score - (previous.overall_score or 0)
            }
        
        # Capture project state
        project_state = {
            "name": project.name,
            "gate_state": project.gate_state,
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "end_date": project.end_date.isoformat() if project.end_date else None,
            "risk_score": project.risk_score,
        }
        
        # Create snapshot
        snapshot = PCOSComplianceSnapshotModel(
            tenant_id=self.tenant_id,
            project_id=project_id,
            snapshot_type=snapshot_type,
            snapshot_name=snapshot_name or f"Snapshot {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
            triggered_by=triggered_by,
            trigger_reason=trigger_reason,
            total_rules_evaluated=total_evaluated,
            rules_passed=total_passed,
            rules_failed=total_failed,
            rules_warning=total_warning,
            overall_score=overall_score,
            compliance_status=compliance_status,
            category_scores=category_scores,
            previous_snapshot_id=previous.id if previous else None,
            delta_summary=delta_summary,
            project_state=project_state
        )
        self.db.add(snapshot)
        self.db.flush()  # Get snapshot ID
        
        # Store rule evaluations with snapshot reference
        for eval_data in evaluations:
            rule_eval = PCOSRuleEvaluationModel(
                tenant_id=self.tenant_id,
                project_id=project_id,
                entity_type=eval_data["entity_type"],
                entity_id=eval_data["entity_id"],
                rule_code=eval_data["rule_code"],
                rule_name=eval_data["rule_name"],
                rule_category=eval_data["rule_category"],
                rule_version=eval_data.get("rule_version", "1.0"),
                result=eval_data["result"],
                score=eval_data.get("score"),
                severity=eval_data.get("severity", "medium"),
                evaluation_input=eval_data.get("input", {}),
                evaluation_output=eval_data.get("output", {}),
                message=eval_data.get("message"),
                source_authorities=eval_data.get("source_authorities", []),
                snapshot_id=snapshot.id,
                evaluated_by=triggered_by
            )
            self.db.add(rule_eval)
        
        self.db.commit()
        
        return {
            "snapshot_id": str(snapshot.id),
            "project_id": str(project_id),
            "snapshot_type": snapshot_type,
            "snapshot_name": snapshot.snapshot_name,
            "compliance_status": compliance_status,
            "overall_score": overall_score,
            "total_evaluated": total_evaluated,
            "passed": total_passed,
            "failed": total_failed,
            "warnings": total_warning,
            "category_scores": category_scores,
            "delta_from_previous": delta_summary,
            "created_at": snapshot.created_at.isoformat()
        }
    
    def _run_all_evaluations(self, project_id: UUID) -> List[Dict]:
        """Run all available rule evaluations for a project."""
        from .pcos_models import (
            PCOSBudgetModel,
            PCOSBudgetLineItemModel,
            PCOSEngagementModel,
            PCOSLocationModel,
        )
        from sqlalchemy import select
        
        evaluations = []
        
        # 1. Budget rate compliance
        budgets = self.db.execute(
            select(PCOSBudgetModel)
            .where(PCOSBudgetModel.project_id == project_id)
            .where(PCOSBudgetModel.tenant_id == self.tenant_id)
            .where(PCOSBudgetModel.is_active == True)
        ).scalars().all()
        
        for budget in budgets:
            evaluations.append({
                "entity_type": "budget",
                "entity_id": budget.id,
                "rule_code": "BUDGET_EXISTS",
                "rule_name": "Active Budget Exists",
                "rule_category": "budget_compliance",
                "result": "pass",
                "message": f"Budget '{budget.source_file_name}' is active",
                "source_authorities": [{"type": "internal_policy", "name": "Project Setup Requirements"}]
            })
            
            # Check fringe allocation
            if budget.grand_total and float(budget.grand_total) > 0:
                evaluations.append({
                    "entity_type": "budget",
                    "entity_id": budget.id,
                    "rule_code": "BUDGET_TOTAL_SET",
                    "rule_name": "Budget Total Defined",
                    "rule_category": "budget_compliance",
                    "result": "pass",
                    "score": 100,
                    "input": {"grand_total": float(budget.grand_total)},
                    "source_authorities": []
                })
        
        if not budgets:
            evaluations.append({
                "entity_type": "project",
                "entity_id": project_id,
                "rule_code": "BUDGET_EXISTS",
                "rule_name": "Active Budget Exists",
                "rule_category": "budget_compliance",
                "result": "fail",
                "severity": "high",
                "message": "No active budget found for project",
                "source_authorities": []
            })
        
        # 2. Engagement classification
        engagements = self.db.execute(
            select(PCOSEngagementModel)
            .where(PCOSEngagementModel.project_id == project_id)
            .where(PCOSEngagementModel.tenant_id == self.tenant_id)
        ).scalars().all()
        
        for eng in engagements:
            if eng.classification_memo_signed:
                evaluations.append({
                    "entity_type": "engagement",
                    "entity_id": eng.id,
                    "rule_code": "CLASSIFICATION_MEMO",
                    "rule_name": "Classification Memo Signed",
                    "rule_category": "classification",
                    "result": "pass",
                    "message": f"Classification memo signed for {eng.role_title}",
                    "source_authorities": [{"type": "statute", "code": "CA Labor Code §2775", "section": "Worker Classification"}]
                })
            else:
                evaluations.append({
                    "entity_type": "engagement",
                    "entity_id": eng.id,
                    "rule_code": "CLASSIFICATION_MEMO",
                    "rule_name": "Classification Memo Signed",
                    "rule_category": "classification",
                    "result": "warning",
                    "severity": "medium",
                    "message": f"Classification memo not signed for {eng.role_title}",
                    "source_authorities": [{"type": "statute", "code": "CA Labor Code §2775"}]
                })
            
            # Check required documents
            if eng.classification == "employee":
                if eng.w4_received and eng.i9_received:
                    evaluations.append({
                        "entity_type": "engagement",
                        "entity_id": eng.id,
                        "rule_code": "EMPLOYEE_DOCS",
                        "rule_name": "Employee Documents Complete",
                        "rule_category": "paperwork",
                        "result": "pass",
                        "source_authorities": [
                            {"type": "regulation", "code": "IRS W-4", "section": "Employee Withholding"},
                            {"type": "regulation", "code": "USCIS I-9", "section": "Employment Eligibility"}
                        ]
                    })
                else:
                    missing = []
                    if not eng.w4_received:
                        missing.append("W-4")
                    if not eng.i9_received:
                        missing.append("I-9")
                    evaluations.append({
                        "entity_type": "engagement",
                        "entity_id": eng.id,
                        "rule_code": "EMPLOYEE_DOCS",
                        "rule_name": "Employee Documents Complete",
                        "rule_category": "paperwork",
                        "result": "fail",
                        "severity": "high",
                        "message": f"Missing documents: {', '.join(missing)}",
                        "source_authorities": [{"type": "regulation", "code": "IRS/USCIS Requirements"}]
                    })
            elif eng.classification == "contractor":
                if eng.w9_received:
                    evaluations.append({
                        "entity_type": "engagement",
                        "entity_id": eng.id,
                        "rule_code": "CONTRACTOR_DOCS",
                        "rule_name": "Contractor W-9 Received",
                        "rule_category": "paperwork",
                        "result": "pass",
                        "source_authorities": [{"type": "regulation", "code": "IRS W-9", "section": "Taxpayer ID"}]
                    })
                else:
                    evaluations.append({
                        "entity_type": "engagement",
                        "entity_id": eng.id,
                        "rule_code": "CONTRACTOR_DOCS",
                        "rule_name": "Contractor W-9 Received",
                        "rule_category": "paperwork",
                        "result": "fail",
                        "severity": "medium",
                        "message": "W-9 not received for contractor",
                        "source_authorities": [{"type": "regulation", "code": "IRS W-9"}]
                    })
        
        # 3. Location permits
        locations = self.db.execute(
            select(PCOSLocationModel)
            .where(PCOSLocationModel.project_id == project_id)
            .where(PCOSLocationModel.tenant_id == self.tenant_id)
        ).scalars().all()
        
        for loc in locations:
            if loc.permit_required:
                if loc.permit_packet_id:
                    evaluations.append({
                        "entity_type": "location",
                        "entity_id": loc.id,
                        "rule_code": "PERMIT_OBTAINED",
                        "rule_name": "Filming Permit Obtained",
                        "rule_category": "permits",
                        "result": "pass",
                        "message": f"Permit packet exists for {loc.name}",
                        "source_authorities": [{"type": "municipal", "authority": "FilmL.A.", "requirement": "Permit Required"}]
                    })
                else:
                    evaluations.append({
                        "entity_type": "location",
                        "entity_id": loc.id,
                        "rule_code": "PERMIT_OBTAINED",
                        "rule_name": "Filming Permit Obtained",
                        "rule_category": "permits",
                        "result": "fail",
                        "severity": "critical",
                        "message": f"No permit for {loc.name} - filming may be blocked",
                        "source_authorities": [{"type": "municipal", "authority": "FilmL.A."}]
                    })
        
        return evaluations
    
    def compare_snapshots(
        self,
        snapshot_id_1: UUID,
        snapshot_id_2: UUID
    ) -> Dict[str, Any]:
        """Compare two snapshots and return differences."""
        from .pcos_models import PCOSComplianceSnapshotModel, PCOSRuleEvaluationModel
        from sqlalchemy import select
        
        snap1 = self.db.execute(
            select(PCOSComplianceSnapshotModel)
            .where(PCOSComplianceSnapshotModel.id == snapshot_id_1)
            .where(PCOSComplianceSnapshotModel.tenant_id == self.tenant_id)
        ).scalar_one_or_none()
        
        snap2 = self.db.execute(
            select(PCOSComplianceSnapshotModel)
            .where(PCOSComplianceSnapshotModel.id == snapshot_id_2)
            .where(PCOSComplianceSnapshotModel.tenant_id == self.tenant_id)
        ).scalar_one_or_none()
        
        if not snap1 or not snap2:
            raise ValueError("One or both snapshots not found")
        
        # Get evaluations for each
        evals1 = self.db.execute(
            select(PCOSRuleEvaluationModel)
            .where(PCOSRuleEvaluationModel.snapshot_id == snapshot_id_1)
        ).scalars().all()
        
        evals2 = self.db.execute(
            select(PCOSRuleEvaluationModel)
            .where(PCOSRuleEvaluationModel.snapshot_id == snapshot_id_2)
        ).scalars().all()
        
        # Build rule result maps
        results1 = {(e.rule_code, str(e.entity_id)): e.result for e in evals1}
        results2 = {(e.rule_code, str(e.entity_id)): e.result for e in evals2}
        
        # Find changes
        new_failures = []
        resolved = []
        unchanged_failures = []
        
        for key, result in results2.items():
            prev_result = results1.get(key)
            if result == "fail":
                if prev_result != "fail":
                    new_failures.append(key)
                else:
                    unchanged_failures.append(key)
        
        for key, result in results1.items():
            if result == "fail" and results2.get(key) != "fail":
                resolved.append(key)
        
        return {
            "snapshot_1": {
                "id": str(snap1.id),
                "created_at": snap1.created_at.isoformat(),
                "score": snap1.overall_score,
                "status": snap1.compliance_status
            },
            "snapshot_2": {
                "id": str(snap2.id),
                "created_at": snap2.created_at.isoformat(),
                "score": snap2.overall_score,
                "status": snap2.compliance_status
            },
            "score_change": (snap2.overall_score or 0) - (snap1.overall_score or 0),
            "new_failures_count": len(new_failures),
            "resolved_count": len(resolved),
            "unchanged_failures_count": len(unchanged_failures),
            "new_failures": new_failures[:10],  # Limit for response size
            "resolved": resolved[:10]
        }
