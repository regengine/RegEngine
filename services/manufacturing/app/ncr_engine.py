"""
NCR engine API for Non-Conformance Report and CAPA tracking.
Core compliance module for ISO 9001/14001/45001 triple certification.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from .models import NonConformanceReport, CorrectiveAction, SupplierQualityIssue, AuditFinding
from .db_session import get_db
from .auth import require_api_key

import sys
import uuid
# Add shared utilities
sys.path.insert(0, '/Users/christophersellers/Desktop/RegEngine/services')
from shared.middleware import get_current_tenant_id

router = APIRouter(prefix="/v1/manufacturing", tags=["manufacturing"])


# Request/Response Models
class NCRCreate(BaseModel):
    """Request body for creating NCR."""
    ncr_number: str = Field(..., min_length=1, max_length=100)
    detected_date: datetime
    detected_by: str = Field(..., min_length=1, max_length=255)
    detection_source: str = Field(..., pattern="^(INTERNAL_AUDIT|CUSTOMER_COMPLAINT|PROCESS_MONITORING|SUPPLIER_ISSUE)$")
    part_number: Optional[str] = Field(None, max_length=100)
    lot_number: Optional[str] = Field(None, max_length=100)
    quantity_affected: Optional[int] = None
    description: str = Field(..., min_length=1)
    severity: str = Field(..., pattern="^(CRITICAL|MAJOR|MINOR)$")
    containment_action: Optional[str] = None
    iso_9001_relevant: bool = True
    iso_14001_relevant: bool = False
    iso_45001_relevant: bool = False


class CAPACreate(BaseModel):
    """Request body for creating CAPA."""
    ncr_id: int
    action_type: str = Field(..., pattern="^(CORRECTIVE|PREVENTIVE)$")
    description: str = Field(..., min_length=1)
    assigned_to: str = Field(..., min_length=1, max_length=255)
    due_date: datetime
    verification_required: bool = True


class SupplierIssueCreate(BaseModel):
    """Request body for supplier quality issue (8D)."""
    supplier_name: str = Field(..., min_length=1, max_length=255)
    supplier_code: Optional[str] = Field(None, max_length=100)
    issue_date: datetime
    part_number: str = Field(..., min_length=1, max_length=100)
    lot_number: Optional[str] = Field(None, max_length=100)
    defect_description: str = Field(..., min_length=1)


class AuditFindingCreate(BaseModel):
    """Request body for audit finding."""
    audit_type: str = Field(..., pattern="^(INTERNAL|EXTERNAL_ISO_9001|EXTERNAL_ISO_14001|EXTERNAL_ISO_45001|CUSTOMER)$")
    audit_date: datetime
    auditor_name: str = Field(..., min_length=1, max_length=255)
    finding_number: str = Field(..., min_length=1, max_length=100)
    clause_reference: Optional[str] = Field(None, max_length=100)
    finding_type: str = Field(..., pattern="^(MAJOR_NC|MINOR_NC|OFI)$")
    description: str = Field(..., min_length=1)
    target_closure_date: Optional[datetime] = None


class DashboardMetrics(BaseModel):
    """Dashboard metrics for Manufacturing compliance."""
    total_ncrs: int
    open_ncrs: int
    overdue_capas: int
    open_audit_findings: int
    capa_effectiveness_rate: float


# NCR Endpoints
@router.post("/ncr", status_code=status.HTTP_201_CREATED)
async def create_ncr(
    ncr: NCRCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Create Non-Conformance Report for ISO 9001/14001/45001 compliance.
    """
    # Check for duplicate NCR number
    existing = db.query(NonConformanceReport).filter(
        NonConformanceReport.ncr_number == ncr.ncr_number,
        NonConformanceReport.tenant_id == tenant_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"NCR number {ncr.ncr_number} already exists"
        )
    
    # Create NCR
    ncr_record = NonConformanceReport(
        tenant_id=tenant_id,
        ncr_number=ncr.ncr_number,
        detected_date=ncr.detected_date,
        detected_by=ncr.detected_by,
        detection_source=ncr.detection_source,
        part_number=ncr.part_number,
        lot_number=ncr.lot_number,
        quantity_affected=ncr.quantity_affected,
        description=ncr.description,
        severity=ncr.severity,
        containment_action=ncr.containment_action,
        status="OPEN",
        iso_9001_relevant=ncr.iso_9001_relevant,
        iso_14001_relevant=ncr.iso_14001_relevant,
        iso_45001_relevant=ncr.iso_45001_relevant,
        created_at=datetime.utcnow()
    )
    
    db.add(ncr_record)
    db.commit()
    db.refresh(ncr_record)
    
    return {
        "id": ncr_record.id,
        "ncr_number": ncr_record.ncr_number,
        "severity": ncr_record.severity,
        "status": ncr_record.status,
        "created_at": ncr_record.created_at.isoformat()
    }


@router.get("/ncr/{ncr_id}")
async def get_ncr(
    ncr_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Retrieve NCR with all associated CAPAs."""
    ncr = db.query(NonConformanceReport).filter(
        NonConformanceReport.id == ncr_id,
        NonConformanceReport.tenant_id == tenant_id
    ).first()
    
    if not ncr:
        raise HTTPException(status_code=404, detail="NCR not found")
    
    # Get associated CAPAs (filtering by ncr_id implicitly filters by tenant, but explicit is better)
    capas = db.query(CorrectiveAction).filter(
        CorrectiveAction.ncr_id == ncr_id,
        CorrectiveAction.tenant_id == tenant_id
    ).all()
    
    return {
        "id": ncr.id,
        "ncr_number": ncr.ncr_number,
        "detected_date": ncr.detected_date.isoformat(),
        "detected_by": ncr.detected_by,
        "detection_source": ncr.detection_source,
        "part_number": ncr.part_number,
        "lot_number": ncr.lot_number,
        "quantity_affected": ncr.quantity_affected,
        "description": ncr.description,
        "severity": ncr.severity,
        "containment_action": ncr.containment_action,
        "containment_date": ncr.containment_date.isoformat() if ncr.containment_date else None,
        "root_cause": ncr.root_cause,
        "rca_method": ncr.rca_method,
        "status": ncr.status,
        "iso_9001_relevant": ncr.iso_9001_relevant,
        "iso_14001_relevant": ncr.iso_14001_relevant,
        "iso_45001_relevant": ncr.iso_45001_relevant,
        "capas": [
            {
                "id": capa.id,
                "action_type": capa.action_type,
                "description": capa.description,
                "assigned_to": capa.assigned_to,
                "due_date": capa.due_date.isoformat(),
                "implementation_status": capa.implementation_status,
                "verification_result": capa.verification_result
            }
            for capa in capas
        ],
        "created_at": ncr.created_at.isoformat()
    }


@router.patch("/ncr/{ncr_id}/root-cause")
async def update_root_cause(
    ncr_id: int,
    root_cause: str = Query(..., min_length=1),
    rca_method: str = Query(..., pattern="^(5_WHYS|FISHBONE|FAULT_TREE|PARETO)$"),
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Update NCR with root cause analysis results."""
    ncr = db.query(NonConformanceReport).filter(
        NonConformanceReport.id == ncr_id,
        NonConformanceReport.tenant_id == tenant_id
    ).first()
    
    if not ncr:
        raise HTTPException(status_code=404, detail="NCR not found")
    
    ncr.root_cause = root_cause
    ncr.rca_method = rca_method
    ncr.rca_completed_date = datetime.utcnow()
    ncr.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(ncr)
    
    return {
        "id": ncr.id,
        "root_cause": ncr.root_cause,
        "rca_method": ncr.rca_method,
        "rca_completed_date": ncr.rca_completed_date.isoformat()
    }


# CAPA Endpoints
@router.post("/capa", status_code=status.HTTP_201_CREATED)
async def create_capa(
    capa: CAPACreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Create Corrective or Preventive Action linked to NCR.
    """
    # Verify NCR exists
    ncr = db.query(NonConformanceReport).filter(
        NonConformanceReport.id == capa.ncr_id,
        NonConformanceReport.tenant_id == tenant_id
    ).first()
    if not ncr:
        raise HTTPException(status_code=404, detail="NCR not found")
    
    # Create CAPA
    capa_record = CorrectiveAction(
        tenant_id=tenant_id,
        ncr_id=capa.ncr_id,
        action_type=capa.action_type,
        description=capa.description,
        assigned_to=capa.assigned_to,
        assigned_date=datetime.utcnow(),
        due_date=capa.due_date,
        implementation_status="PENDING",
        verification_required=capa.verification_required,
        created_at=datetime.utcnow()
    )
    
    db.add(capa_record)
    
    # Update NCR status
    ncr.status = "CAPA_IN_PROGRESS"
    ncr.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(capa_record)
    
    return {
        "id": capa_record.id,
        "ncr_id": capa_record.ncr_id,
        "action_type": capa_record.action_type,
        "assigned_to": capa_record.assigned_to,
        "due_date": capa_record.due_date.isoformat(),
        "implementation_status": capa_record.implementation_status
    }


@router.patch("/capa/{capa_id}/verify")
async def verify_capa_effectiveness(
    capa_id: int,
    verification_result: str = Query(..., pattern="^(EFFECTIVE|NOT_EFFECTIVE|PARTIALLY_EFFECTIVE)$"),
    verified_by: str = Query(..., min_length=1),
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Verify CAPA effectiveness (ISO requirement).
    """
    capa = db.query(CorrectiveAction).filter(
        CorrectiveAction.id == capa_id,
        CorrectiveAction.tenant_id == tenant_id
    ).first()
    
    if not capa:
        raise HTTPException(status_code=404, detail="CAPA not found")
    
    capa.verification_date = datetime.utcnow()
    capa.verification_result = verification_result
    capa.verified_by = verified_by
    capa.implementation_status = "VERIFIED"
    capa.updated_at = datetime.utcnow()
    
    if notes:
        capa.implementation_notes = notes
    
    db.commit()
    db.refresh(capa)
    
    return {
        "id": capa.id,
        "verification_result": capa.verification_result,
        "verification_date": capa.verification_date.isoformat(),
        "verified_by": capa.verified_by
    }


# Supplier Quality Endpoints
@router.post("/supplier-issue", status_code=status.HTTP_201_CREATED)
async def create_supplier_issue(
    issue: SupplierIssueCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Create supplier quality issue with 8D problem solving framework.
    """
    supplier_issue = SupplierQualityIssue(
        tenant_id=tenant_id,
        supplier_name=issue.supplier_name,
        supplier_code=issue.supplier_code,
        issue_date=issue.issue_date,
        part_number=issue.part_number,
        lot_number=issue.lot_number,
        defect_description=issue.defect_description,
        status="OPEN",
        created_at=datetime.utcnow()
    )
    
    db.add(supplier_issue)
    db.commit()
    db.refresh(supplier_issue)
    
    return {
        "id": supplier_issue.id,
        "supplier_name": supplier_issue.supplier_name,
        "part_number": supplier_issue.part_number,
        "status": supplier_issue.status
    }


# Audit Finding Endpoints
@router.post("/audit-finding", status_code=status.HTTP_201_CREATED)
async def create_audit_finding(
    finding: AuditFindingCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Record internal or external audit finding for ISO compliance.
    """
    # Check for duplicate
    existing = db.query(AuditFinding).filter(
        AuditFinding.finding_number == finding.finding_number,
        AuditFinding.tenant_id == tenant_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Finding number already exists")
    
    audit_finding = AuditFinding(
        tenant_id=tenant_id,
        audit_type=finding.audit_type,
        audit_date=finding.audit_date,
        auditor_name=finding.auditor_name,
        finding_number=finding.finding_number,
        clause_reference=finding.clause_reference,
        finding_type=finding.finding_type,
        description=finding.description,
        target_closure_date=finding.target_closure_date,
        status="OPEN",
        created_at=datetime.utcnow()
    )
    
    db.add(audit_finding)
    db.commit()
    db.refresh(audit_finding)
    
    return {
        "id": audit_finding.id,
        "finding_number": audit_finding.finding_number,
        "finding_type": audit_finding.finding_type,
        "status": audit_finding.status
    }


@router.get("/dashboard", response_model=DashboardMetrics)
async def get_dashboard(
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Get dashboard metrics for Manufacturing compliance overview."""
    # Total NCRs
    total_ncrs = db.query(func.count(NonConformanceReport.id)).filter(
        NonConformanceReport.tenant_id == tenant_id
    ).scalar() or 0
    
    # Open NCRs
    open_ncrs = db.query(func.count(NonConformanceReport.id)).filter(
        NonConformanceReport.status.in_(['OPEN', 'CAPA_IN_PROGRESS', 'VERIFICATION']),
        NonConformanceReport.tenant_id == tenant_id
    ).scalar() or 0
    
    # Overdue CAPAs
    overdue_capas = db.query(func.count(CorrectiveAction.id)).filter(
        CorrectiveAction.due_date < datetime.utcnow(),
        CorrectiveAction.implementation_status.in_(['PENDING', 'IN_PROGRESS']),
        CorrectiveAction.tenant_id == tenant_id
    ).scalar() or 0
    
    # Open audit findings
    open_findings = db.query(func.count(AuditFinding.id)).filter(
        AuditFinding.status != 'CLOSED',
        AuditFinding.tenant_id == tenant_id
    ).scalar() or 0
    
    # CAPA effectiveness rate
    total_verified = db.query(func.count(CorrectiveAction.id)).filter(
        CorrectiveAction.verification_result.isnot(None),
        CorrectiveAction.tenant_id == tenant_id
    ).scalar() or 0
    
    effective = db.query(func.count(CorrectiveAction.id)).filter(
        CorrectiveAction.verification_result == 'EFFECTIVE',
        CorrectiveAction.tenant_id == tenant_id
    ).scalar() or 0
    
    effectiveness_rate = (effective / total_verified * 100) if total_verified > 0 else 100.0
    
    return DashboardMetrics(
        total_ncrs=total_ncrs,
        open_ncrs=open_ncrs,
        overdue_capas=overdue_capas,
        open_audit_findings=open_findings,
        capa_effectiveness_rate=round(effectiveness_rate, 1)
    )
