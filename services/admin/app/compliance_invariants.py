"""
Compliance Invariants Service

Enforces the hard runtime invariants from SCHEMA_CHANGE_POLICY.md:
1. Every analysis has an AnalysisRun
2. Every verdict records rule_version_id, fact_version_ids, authority_pointer_ids
3. Missing data → INDETERMINATE
4. Corrections are new versions, never updates
"""

import hashlib
import structlog
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, List, Any, Tuple
from uuid import UUID

from .pcos_models import PCOSAnalysisRunModel  # noqa: F811 – needed for type annotation

logger = structlog.get_logger(__name__)


class VerdictResult:
    """Verdict result with provenance chain."""
    
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    INDETERMINATE = "indeterminate"
    
    def __init__(
        self,
        result: str,
        rule_version_id: Optional[UUID] = None,
        fact_version_ids: Optional[List[UUID]] = None,
        authority_ids: Optional[List[UUID]] = None,
        reason: Optional[str] = None,
        missing_data: Optional[List[str]] = None
    ):
        self.result = result
        self.rule_version_id = rule_version_id
        self.fact_version_ids = fact_version_ids or []
        self.authority_ids = authority_ids or []
        self.reason = reason
        self.missing_data = missing_data or []
    
    @property
    def is_complete(self) -> bool:
        """Check if verdict has complete provenance."""
        return (
            self.rule_version_id is not None and
            len(self.fact_version_ids) > 0 and
            len(self.authority_ids) > 0
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "result": self.result,
            "rule_version_id": str(self.rule_version_id) if self.rule_version_id else None,
            "fact_version_ids": [str(f) for f in self.fact_version_ids],
            "authority_ids": [str(a) for a in self.authority_ids],
            "reason": self.reason,
            "missing_data": self.missing_data,
            "is_complete": self.is_complete
        }


class ComplianceInvariantsService:
    """
    Enforces schema governance invariants at runtime.
    
    This service is the application-level enforcement layer for
    the immutability and completeness constraints defined in V20.
    """
    
    def __init__(self, db_session, tenant_id: UUID):
        self.db = db_session
        self.tenant_id = tenant_id
    
    # =========================================================================
    # Invariant 1: Every Analysis Has a Run
    # =========================================================================
    
    def create_analysis_run(
        self,
        run_type: str,
        project_id: Optional[UUID] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[UUID] = None,
        parameters: Optional[Dict] = None,
        rule_pack_version: Optional[str] = None
    ) -> "PCOSAnalysisRunModel":
        """
        Create an analysis run before executing any compliance checks.
        
        This is MANDATORY. No verdicts can be created without a parent run.
        """
        from .pcos_models import PCOSAnalysisRunModel
        
        run = PCOSAnalysisRunModel(
            tenant_id=self.tenant_id,
            run_type=run_type,
            run_status="pending",
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            run_parameters=parameters or {},
            rule_pack_version=rule_pack_version,
            fact_snapshot_time=datetime.now(timezone.utc)
        )
        
        self.db.add(run)
        self.db.commit()
        
        logger.info(
            "analysis_run_created",
            run_id=str(run.id),
            run_type=run_type,
            project_id=str(project_id) if project_id else None
        )
        
        return run
    
    def start_run(self, run_id: UUID) -> None:
        """Mark an analysis run as started."""
        from .pcos_models import PCOSAnalysisRunModel
        from sqlalchemy import select
        
        run = self.db.execute(
            select(PCOSAnalysisRunModel)
            .where(PCOSAnalysisRunModel.id == run_id)
            .where(PCOSAnalysisRunModel.tenant_id == self.tenant_id)
        ).scalar_one_or_none()
        
        if not run:
            raise ValueError(f"Analysis run {run_id} not found")
        
        run.mark_running()
        self.db.commit()
        
        logger.info("analysis_run_started", run_id=str(run_id))
    
    def complete_run(
        self,
        run_id: UUID,
        pass_count: int,
        fail_count: int,
        warning_count: int,
        indeterminate_count: int
    ) -> None:
        """Mark an analysis run as completed with results."""
        from .pcos_models import PCOSAnalysisRunModel
        from sqlalchemy import select
        
        run = self.db.execute(
            select(PCOSAnalysisRunModel)
            .where(PCOSAnalysisRunModel.id == run_id)
            .where(PCOSAnalysisRunModel.tenant_id == self.tenant_id)
        ).scalar_one_or_none()
        
        if not run:
            raise ValueError(f"Analysis run {run_id} not found")
        
        run.mark_completed(pass_count, fail_count, warning_count, indeterminate_count)
        self.db.commit()
        
        logger.info(
            "analysis_run_completed",
            run_id=str(run_id),
            total=run.total_evaluations,
            pass_count=pass_count,
            fail_count=fail_count,
            execution_time_ms=run.execution_time_ms
        )
    
    def fail_run(self, run_id: UUID, error: str) -> None:
        """Mark an analysis run as failed."""
        from .pcos_models import PCOSAnalysisRunModel
        from sqlalchemy import select
        
        run = self.db.execute(
            select(PCOSAnalysisRunModel)
            .where(PCOSAnalysisRunModel.id == run_id)
            .where(PCOSAnalysisRunModel.tenant_id == self.tenant_id)
        ).scalar_one_or_none()
        
        if not run:
            raise ValueError(f"Analysis run {run_id} not found")
        
        run.mark_failed(error)
        self.db.commit()
        
        logger.error(
            "analysis_run_failed",
            run_id=str(run_id),
            error=error
        )
    
    # =========================================================================
    # Invariant 2: Verdict Completeness
    # =========================================================================
    
    def validate_verdict(
        self,
        rule_version_id: Optional[UUID],
        fact_version_ids: Optional[List[UUID]],
        authority_ids: Optional[List[UUID]]
    ) -> VerdictResult:
        """
        Validate that a verdict has complete provenance.
        
        If any required data is missing, returns INDETERMINATE.
        """
        missing = []
        
        if rule_version_id is None:
            missing.append("rule_version_id")
        
        if not fact_version_ids:
            missing.append("fact_version_ids")
        
        if not authority_ids:
            missing.append("authority_ids")
        
        if missing:
            return VerdictResult(
                result=VerdictResult.INDETERMINATE,
                rule_version_id=rule_version_id,
                fact_version_ids=fact_version_ids or [],
                authority_ids=authority_ids or [],
                reason=f"Missing required provenance: {', '.join(missing)}",
                missing_data=missing
            )
        
        # All required data present - actual verdict will be determined by rule logic
        return VerdictResult(
            result=None,  # To be filled by caller
            rule_version_id=rule_version_id,
            fact_version_ids=fact_version_ids,
            authority_ids=authority_ids
        )
    
    def create_verdict(
        self,
        analysis_run_id: UUID,
        result: str,
        rule_version_id: UUID,
        fact_version_ids: List[UUID],
        authority_ids: List[UUID],
        rule_code: str,
        entity_type: str,
        entity_id: UUID,
        input_data: Optional[Dict] = None,
        output_details: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create a verdict with enforced provenance chain.
        
        This is the ONLY way to create verdicts - ensures all invariants are met.
        """
        from .pcos_models import PCOSRuleEvaluationModel, PCOSAnalysisRunModel
        from sqlalchemy import select
        
        # Verify run exists and is running
        run = self.db.execute(
            select(PCOSAnalysisRunModel)
            .where(PCOSAnalysisRunModel.id == analysis_run_id)
            .where(PCOSAnalysisRunModel.tenant_id == self.tenant_id)
        ).scalar_one_or_none()
        
        if not run:
            raise ValueError("Analysis run not found - verdicts require a parent run")
        
        if run.run_status not in ("pending", "running"):
            raise ValueError(f"Cannot add verdict to {run.run_status} run")
        
        # Validate completeness
        validation = self.validate_verdict(rule_version_id, fact_version_ids, authority_ids)
        
        if validation.result == VerdictResult.INDETERMINATE:
            result = VerdictResult.INDETERMINATE
            output_details = output_details or {}
            output_details["indeterminate_reason"] = validation.reason
            output_details["missing_data"] = validation.missing_data
        
        # Create evaluation record
        evaluation = PCOSRuleEvaluationModel(
            tenant_id=self.tenant_id,
            analysis_run_id=analysis_run_id,
            rule_code=rule_code,
            entity_type=entity_type,
            entity_id=entity_id,
            evaluation_result=result,
            rule_version_id=rule_version_id,
            fact_version_ids=[str(f) for f in fact_version_ids],
            authority_ids=[str(a) for a in authority_ids],
            input_data=input_data or {},
            output_details=output_details or {},
            source_authorities=[
                {"authority_id": str(a)} for a in authority_ids
            ]
        )
        
        self.db.add(evaluation)
        self.db.commit()
        
        logger.info(
            "verdict_created",
            evaluation_id=str(evaluation.id),
            run_id=str(analysis_run_id),
            result=result,
            rule_code=rule_code
        )
        
        return {
            "evaluation_id": str(evaluation.id),
            "result": result,
            "is_complete": validation.is_complete if validation.result != VerdictResult.INDETERMINATE else False,
            "provenance": {
                "rule_version_id": str(rule_version_id) if rule_version_id else None,
                "fact_count": len(fact_version_ids),
                "authority_count": len(authority_ids)
            }
        }
    
    # =========================================================================
    # Invariant 4: Corrections as New Versions
    # =========================================================================
    
    def create_correction(
        self,
        original_verdict_id: UUID,
        corrected_result: str,
        correction_reason: str,
        corrected_by: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Create a correction for an existing verdict.
        
        NEVER updates the original - creates a new version with supersedes_id.
        """
        from .pcos_models import PCOSRuleEvaluationModel
        from sqlalchemy import select
        
        # Get original verdict
        original = self.db.execute(
            select(PCOSRuleEvaluationModel)
            .where(PCOSRuleEvaluationModel.id == original_verdict_id)
            .where(PCOSRuleEvaluationModel.tenant_id == self.tenant_id)
        ).scalar_one_or_none()
        
        if not original:
            raise ValueError(f"Original verdict {original_verdict_id} not found")
        
        # Create a new run for the correction
        correction_run = self.create_analysis_run(
            run_type="correction",
            project_id=None,  # Will be linked via entity
            entity_type=original.entity_type,
            entity_id=original.entity_id,
            parameters={"correcting_verdict_id": str(original_verdict_id)}
        )
        
        self.start_run(correction_run.id)
        
        # Create corrected verdict
        corrected = PCOSRuleEvaluationModel(
            tenant_id=self.tenant_id,
            analysis_run_id=correction_run.id,
            rule_code=original.rule_code,
            entity_type=original.entity_type,
            entity_id=original.entity_id,
            evaluation_result=corrected_result,
            rule_version_id=original.rule_version_id,
            supersedes_id=original.id,  # Link to original
            input_data=original.input_data,
            output_details={
                **(original.output_details or {}),
                "correction_reason": correction_reason,
                "corrected_by": str(corrected_by) if corrected_by else None,
                "original_result": original.evaluation_result
            },
            source_authorities=original.source_authorities
        )
        
        self.db.add(corrected)
        
        # Complete the correction run
        result_counts = {
            "pass": 1 if corrected_result == "pass" else 0,
            "fail": 1 if corrected_result == "fail" else 0,
            "warning": 1 if corrected_result == "warning" else 0,
            "indeterminate": 1 if corrected_result == "indeterminate" else 0
        }
        
        self.complete_run(
            correction_run.id,
            result_counts["pass"],
            result_counts["fail"],
            result_counts["warning"],
            result_counts["indeterminate"]
        )
        
        logger.info(
            "correction_created",
            original_id=str(original_verdict_id),
            corrected_id=str(corrected.id),
            original_result=original.evaluation_result,
            corrected_result=corrected_result,
            reason=correction_reason
        )
        
        return {
            "corrected_verdict_id": str(corrected.id),
            "original_verdict_id": str(original_verdict_id),
            "original_result": original.evaluation_result,
            "corrected_result": corrected_result,
            "correction_run_id": str(correction_run.id)
        }
    
    # =========================================================================
    # Schema Version Check
    # =========================================================================
    
    def get_schema_version(self) -> Dict[str, Any]:
        """Get current schema version and status."""
        from .pcos_models import SchemaVersionModel
        from sqlalchemy import select, desc
        
        latest = self.db.execute(
            select(SchemaVersionModel)
            .order_by(desc(SchemaVersionModel.applied_at))
            .limit(1)
        ).scalar_one_or_none()
        
        if not latest:
            return {"version": "unknown", "applied_at": None}
        
        return {
            "version": latest.version,
            "checksum": latest.checksum,
            "git_sha": latest.git_sha,
            "applied_at": latest.applied_at.isoformat() if latest.applied_at else None,
            "success": latest.success
        }
    
    def check_active_runs(self) -> Dict[str, Any]:
        """Check for active analysis runs (pre-migration check)."""
        from .pcos_models import PCOSAnalysisRunModel
        from sqlalchemy import select, func
        
        active_count = self.db.execute(
            select(func.count(PCOSAnalysisRunModel.id))
            .where(PCOSAnalysisRunModel.run_status == "running")
        ).scalar()
        
        return {
            "active_runs": active_count,
            "safe_to_migrate": active_count == 0,
            "warning": "Long-running analyses in progress" if active_count > 0 else None
        }
