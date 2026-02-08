"""
PCOS Governance Router — Schema version, analysis runs, and corrections.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..database import get_pcos_session
from ..models import TenantContext

router = APIRouter(tags=["PCOS Governance"])


# =============================================================================
# SCHEMA GOVERNANCE ENDPOINTS
# =============================================================================

@router.get("/governance/schema-version")
def get_schema_version(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    Get current schema version and migration status.
    
    Useful for deployment verification and debugging.
    """
    from ..compliance_invariants import ComplianceInvariantsService

    tenant_id = UUID(x_tenant_id)
    TenantContext.set_tenant_context(session, tenant_id)

    service = ComplianceInvariantsService(session, tenant_id)
    return service.get_schema_version()


@router.get("/governance/active-runs")
def check_active_runs(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    Check for active analysis runs (pre-migration check).
    
    Per SCHEMA_CHANGE_POLICY.md Section 4.3, migrations should not
    be applied while long-running analyses are in progress.
    """
    from ..compliance_invariants import ComplianceInvariantsService

    tenant_id = UUID(x_tenant_id)
    TenantContext.set_tenant_context(session, tenant_id)

    service = ComplianceInvariantsService(session, tenant_id)
    return service.check_active_runs()


@router.post("/governance/analysis-runs")
def create_analysis_run(
    run_type: str,
    project_id: Optional[UUID] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[UUID] = None,
    rule_pack_version: Optional[str] = None,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    Create an analysis run before executing compliance checks.
    
    Every analysis MUST have a parent run. This is a hard invariant.
    """
    from ..compliance_invariants import ComplianceInvariantsService

    tenant_id = UUID(x_tenant_id)
    TenantContext.set_tenant_context(session, tenant_id)

    service = ComplianceInvariantsService(session, tenant_id)
    run = service.create_analysis_run(
        run_type=run_type,
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        rule_pack_version=rule_pack_version
    )

    return {
        "run_id": str(run.id),
        "run_type": run.run_type,
        "run_status": run.run_status,
        "created_at": run.created_at.isoformat()
    }


@router.post("/governance/analysis-runs/{run_id}/start")
def start_analysis_run(
    run_id: UUID,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    session: Session = Depends(get_pcos_session),
):
    """Mark an analysis run as started."""
    from ..compliance_invariants import ComplianceInvariantsService

    tenant_id = UUID(x_tenant_id)
    TenantContext.set_tenant_context(session, tenant_id)

    service = ComplianceInvariantsService(session, tenant_id)
    service.start_run(run_id)

    return {"run_id": str(run_id), "status": "running"}


@router.post("/governance/analysis-runs/{run_id}/complete")
def complete_analysis_run(
    run_id: UUID,
    pass_count: int,
    fail_count: int,
    warning_count: int = 0,
    indeterminate_count: int = 0,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    session: Session = Depends(get_pcos_session),
):
    """Mark an analysis run as completed with results."""
    from ..compliance_invariants import ComplianceInvariantsService

    tenant_id = UUID(x_tenant_id)
    TenantContext.set_tenant_context(session, tenant_id)

    service = ComplianceInvariantsService(session, tenant_id)
    service.complete_run(run_id, pass_count, fail_count, warning_count, indeterminate_count)

    return {
        "run_id": str(run_id),
        "status": "completed",
        "total": pass_count + fail_count + warning_count + indeterminate_count
    }


@router.post("/governance/corrections")
def create_correction(
    original_verdict_id: UUID,
    corrected_result: str,
    correction_reason: str,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    Create a correction for an existing verdict.
    
    Per SCHEMA_CHANGE_POLICY.md: Corrections are new versions, never updates.
    The original verdict remains immutable.
    """
    from ..compliance_invariants import ComplianceInvariantsService

    tenant_id = UUID(x_tenant_id)
    user_id = UUID(x_user_id) if x_user_id else None
    TenantContext.set_tenant_context(session, tenant_id)

    service = ComplianceInvariantsService(session, tenant_id)
    return service.create_correction(
        original_verdict_id=original_verdict_id,
        corrected_result=corrected_result,
        correction_reason=correction_reason,
        corrected_by=user_id
    )
