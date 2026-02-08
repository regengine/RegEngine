"""
PPAP vault API for cryptographic PPAP package tracking.
Core compliance module for IATF 16949 and OEM requirements.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import List, Optional
from pathlib import Path
from pydantic import BaseModel, Field
import hashlib
import json
import os

from .models import PPAPSubmission, PPAPElement, LPAAudit
from .db_session import get_db
from .auth import require_api_key

import sys
import uuid
# Add shared utilities
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from shared.middleware import get_current_tenant_id

router = APIRouter(prefix="/v1/automotive", tags=["automotive"])


# Request/Response Models
class PPAPSubmissionCreate(BaseModel):
    """Request body for creating PPAP submission."""
    part_number: str = Field(..., min_length=1, max_length=100)
    part_name: str = Field(..., min_length=1, max_length=255)
    submission_level: int = Field(..., ge=1, le=5)
    oem_customer: str = Field(..., min_length=1, max_length=255)
    customer_part_number: Optional[str] = Field(None, max_length=100)
    submission_date: datetime
    metadata: Optional[dict] = None


class PPAPSubmissionResponse(BaseModel):
    """Response body for PPAP submission."""
    id: int
    part_number: str
    submission_level: int
    oem_customer: str
    approval_status: str
    elements_uploaded: int
    elements_required: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class PPAPElementResponse(BaseModel):
    """Response body for PPAP element upload."""
    id: int
    element_type: str
    content_hash: str
    file_size_bytes: int
    uploaded_at: datetime
    
    class Config:
        from_attributes = True


class LPAAuditCreate(BaseModel):
    """Request body for LPA audit record."""
    layer: str = Field(..., pattern="^(EXECUTIVE|MANAGEMENT|FRONTLINE)$")
    part_number: Optional[str] = Field(None, max_length=100)
    process_step: str = Field(..., min_length=1, max_length=255)
    question: str = Field(..., min_length=1)
    result: str = Field(..., pattern="^(PASS|FAIL|NA)$")
    auditor_name: str = Field(..., min_length=1, max_length=255)
    corrective_action: Optional[str] = None
    audit_date: Optional[datetime] = None


class DashboardMetrics(BaseModel):
    """Dashboard metrics for Automotive compliance."""
    total_ppap_submissions: int
    pending_approvals: int
    approved_this_month: int
    lpa_pass_rate_30d: float
    open_corrective_actions: int


# PPAP Endpoints
@router.post("/ppap", response_model=PPAPSubmissionResponse, status_code=status.HTTP_201_CREATED)
async def create_ppap_submission(
    submission: PPAPSubmissionCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Initialize PPAP submission with cryptographic tracking.
    Returns submission_id for uploading 18 required elements.
    
    **Compliance Standards:**
    - IATF 16949:2016
    - AIAG PPAP Manual 4th Edition
    - VDA Volume 2 (German OEMs)
    """
    ppap = PPAPSubmission(
        tenant_id=tenant_id,
        part_number=submission.part_number,
        part_name=submission.part_name,
        submission_level=submission.submission_level,
        oem_customer=submission.oem_customer,
        customer_part_number=submission.customer_part_number,
        submission_date=submission.submission_date,
        approval_status="PENDING",
        metadata_=submission.metadata,
        created_at=datetime.utcnow()
    )
    
    db.add(ppap)
    db.commit()
    db.refresh(ppap)
    
    # Determine number of elements required based on submission level
    elements_required = {
        1: 1,   # PSW only
        2: 10,  # PSW + limited data
        3: 18,  # PSW + complete data
        4: 18,  # PSW + complete data at supplier
        5: 18   # PSW + complete data at designated location
    }.get(submission.submission_level, 18)
    
    return PPAPSubmissionResponse(
        id=ppap.id,
        part_number=ppap.part_number,
        submission_level=ppap.submission_level,
        oem_customer=ppap.oem_customer,
        approval_status=ppap.approval_status,
        elements_uploaded=0,
        elements_required=elements_required,
        created_at=ppap.created_at
    )


@router.post("/ppap/{submission_id}/element", response_model=PPAPElementResponse, status_code=status.HTTP_201_CREATED)
async def upload_ppap_element(
    submission_id: int,
    element_type: str = Query(..., description="One of the 18 PPAP element types"),
    file: UploadFile = File(...),
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Upload individual PPAP element with SHA-256 verification.
    """
    # Verify submission exists and belongs to tenant
    submission = db.query(PPAPSubmission).filter(
        PPAPSubmission.id == submission_id,
        PPAPSubmission.tenant_id == tenant_id
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail="PPAP submission not found")
    
    # Validate element type
    if element_type not in PPAPElement.VALID_ELEMENT_TYPES:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid element type. Must be one of: {', '.join(PPAPElement.VALID_ELEMENT_TYPES)}"
        )
    
    # Read file and calculate hash
    content = await file.read()
    content_hash = hashlib.sha256(content).hexdigest()
    
    # Check for duplicate (prevent re-upload of same file)
    existing = db.query(PPAPElement).filter(
        PPAPElement.submission_id == submission_id,
        PPAPElement.element_type == element_type,
        PPAPElement.tenant_id == tenant_id
    ).order_by(PPAPElement.version.desc()).first()
    
    version = 1 if not existing else existing.version + 1
    
    # Store element metadata
    element = PPAPElement(
        tenant_id=tenant_id,
        submission_id=submission_id,
        element_type=element_type,
        filename=file.filename or "unnamed",
        content_hash=content_hash,
        file_size_bytes=len(content),
        mime_type=file.content_type,
        version=version,
        notes=notes,
        uploaded_at=datetime.utcnow()
    )
    
    db.add(element)
    db.commit()
    db.refresh(element)
    
    # Store file to local vault (S3-backed in production)
    storage_root = os.environ.get("PPAP_STORAGE_ROOT", "/var/lib/regengine/ppap_vault")
    storage_dir = os.path.join(
        storage_root, str(tenant_id), str(submission_id)
    )
    os.makedirs(storage_dir, exist_ok=True)
    safe_name = f"{element_type}_v{version}"
    storage_path = os.path.join(storage_dir, safe_name)
    with open(storage_path, "wb") as f:
        f.write(content)

    # Verify write integrity
    with open(storage_path, "rb") as f:
        verify_hash = hashlib.sha256(f.read()).hexdigest()
    if verify_hash != content_hash:
        os.remove(storage_path)
        raise HTTPException(status_code=500, detail="File integrity check failed after write")

    return PPAPElementResponse(
        id=element.id,
        element_type=element.element_type,
        content_hash=element.content_hash,
        file_size_bytes=element.file_size_bytes,
        uploaded_at=element.uploaded_at
    )


@router.get("/ppap/{submission_id}")
async def get_ppap_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Retrieve PPAP submission with element status."""
    submission = db.query(PPAPSubmission).filter(
        PPAPSubmission.id == submission_id,
        PPAPSubmission.tenant_id == tenant_id
    ).first()
    
    if not submission:
        raise HTTPException(status_code=404, detail="PPAP submission not found")
    
    # Count uploaded elements
    elements = db.query(PPAPElement).filter(
        PPAPElement.submission_id == submission_id,
        PPAPElement.tenant_id == tenant_id
    ).all()
    
    # Group by element type (latest version only)
    element_status = {}
    for element in elements:
        if element.element_type not in element_status or element.version > element_status[element.element_type]['version']:
            element_status[element.element_type] = {
                'uploaded': True,
                'version': element.version,
                'filename': element.filename,
                'content_hash': element.content_hash,
                'uploaded_at': element.uploaded_at.isoformat()
            }
    
    # Determine required elements based on level
    elements_required = {
        1: ["PART_SUBMISSION_WARRANT"],
        2: ["PART_SUBMISSION_WARRANT", "DIMENSIONAL_RESULTS", "MATERIAL_TEST_RESULTS", 
            "CONTROL_PLAN", "PROCESS_FLOW_DIAGRAM", "PFMEA", "CUSTOMER_ENGINEERING_APPROVAL",
            "DESIGN_RECORDS", "ENGINEERING_CHANGE_DOCUMENTS", "CUSTOMER_SPECIFIC_REQUIREMENTS"],
        3: PPAPElement.VALID_ELEMENT_TYPES,  # All 18
        4: PPAPElement.VALID_ELEMENT_TYPES,
        5: PPAPElement.VALID_ELEMENT_TYPES
    }.get(submission.submission_level, PPAPElement.VALID_ELEMENT_TYPES)
    
    completeness_pct = len(element_status) / len(elements_required) * 100 if elements_required else 0
    
    return {
        "id": submission.id,
        "part_number": submission.part_number,
        "part_name": submission.part_name,
        "submission_level": submission.submission_level,
        "oem_customer": submission.oem_customer,
        "customer_part_number": submission.customer_part_number,
        "submission_date": submission.submission_date.isoformat(),
        "approval_status": submission.approval_status,
        "approval_date": submission.approval_date.isoformat() if submission.approval_date else None,
        "completeness_pct": round(completeness_pct, 1),
        "elements_required": len(elements_required),
        "elements_uploaded": len(element_status),
        "element_status": element_status,
        "created_at": submission.created_at.isoformat()
    }


@router.patch("/ppap/{submission_id}/approve")
async def approve_ppap_submission(
    submission_id: int,
    approval_status: str = Query(..., pattern="^(APPROVED|REJECTED|INTERIM)$"),
    approval_notes: Optional[str] = None,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Update PPAP approval status.
    Typically done by OEM customer or quality manager.
    """
    submission = db.query(PPAPSubmission).filter(
        PPAPSubmission.id == submission_id,
        PPAPSubmission.tenant_id == tenant_id
    ).first()
    
    if not submission:
        raise HTTPException(status_code=404, detail="PPAP submission not found")
    
    submission.approval_status = approval_status
    submission.approval_date = datetime.utcnow()
    submission.approval_notes = approval_notes
    submission.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(submission)
    
    return {
        "id": submission.id,
        "approval_status": submission.approval_status,
        "approval_date": submission.approval_date.isoformat(),
        "approval_notes": submission.approval_notes
    }


# LPA Endpoints
@router.post("/lpa", status_code=status.HTTP_201_CREATED)
async def create_lpa_audit(
    audit: LPAAuditCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Record Layered Process Audit (LPA) result.
    """
    lpa = LPAAudit(
        tenant_id=tenant_id,
        audit_date=audit.audit_date or datetime.utcnow(),
        layer=audit.layer,
        part_number=audit.part_number,
        process_step=audit.process_step,
        question=audit.question,
        result=audit.result,
        auditor_name=audit.auditor_name,
        corrective_action=audit.corrective_action,
        created_at=datetime.utcnow()
    )
    
    db.add(lpa)
    db.commit()
    db.refresh(lpa)
    
    return {
        "id": lpa.id,
        "audit_date": lpa.audit_date.isoformat(),
        "layer": lpa.layer,
        "result": lpa.result,
        "status": "recorded"
    }


@router.get("/dashboard", response_model=DashboardMetrics)
async def get_dashboard(
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Get dashboard metrics for Automotive compliance overview."""
    # Total PPAP submissions
    total_ppap = db.query(func.count(PPAPSubmission.id)).filter(
        PPAPSubmission.tenant_id == tenant_id
    ).scalar() or 0
    
    # Pending approvals
    pending = db.query(func.count(PPAPSubmission.id)).filter(
        PPAPSubmission.approval_status == "PENDING",
        PPAPSubmission.tenant_id == tenant_id
    ).scalar() or 0
    
    # Approved this month
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    approved_this_month = db.query(func.count(PPAPSubmission.id)).filter(
        PPAPSubmission.approval_status == "APPROVED",
        PPAPSubmission.approval_date >= month_start,
        PPAPSubmission.tenant_id == tenant_id
    ).scalar() or 0
    
    # LPA pass rate (last 30 days)
    from datetime import timedelta
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    total_lpa = db.query(func.count(LPAAudit.id)).filter(
        LPAAudit.audit_date >= thirty_days_ago,
        LPAAudit.tenant_id == tenant_id
    ).scalar() or 0
    
    passed_lpa = db.query(func.count(LPAAudit.id)).filter(
        LPAAudit.audit_date >= thirty_days_ago,
        LPAAudit.result == "PASS",
        LPAAudit.tenant_id == tenant_id
    ).scalar() or 0
    
    pass_rate = (passed_lpa / total_lpa * 100) if total_lpa > 0 else 100.0
    
    # Open corrective actions
    open_ca = db.query(func.count(LPAAudit.id)).filter(
        LPAAudit.result == "FAIL",
        LPAAudit.corrective_action_status != "COMPLETE",
        LPAAudit.tenant_id == tenant_id
    ).scalar() or 0
    
    return DashboardMetrics(
        total_ppap_submissions=total_ppap,
        pending_approvals=pending,
        approved_this_month=approved_this_month,
        lpa_pass_rate_30d=round(pass_rate, 1),
        open_corrective_actions=open_ca
    )
