"""
FAI vault API for AS9102 First Article Inspection tracking.
Configuration baseline management for 30-year aerospace lifecycle.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import hashlib
import json
import sys
import uuid
from pathlib import Path

# Add shared utilities (portable path resolution)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.middleware import get_current_tenant_id, get_optional_tenant_id

from .models import FAIReport, ConfigurationBaseline, NADCAPEvidence
from .db_session import get_db
from .auth import require_api_key

router = APIRouter(prefix="/v1/aerospace", tags=["aerospace"])


# Request/Response Models
class FAIReportCreate(BaseModel):
    """Request body for creating AS9102 FAI report."""
    part_number: str = Field(..., min_length=1, max_length=100)
    part_name: str = Field(..., min_length=1, max_length=255)
    drawing_number: str = Field(..., min_length=1, max_length=100)
    drawing_revision: str = Field(..., min_length=1, max_length=50)
    customer_name: str = Field(..., min_length=1, max_length=255)
    customer_part_number: Optional[str] = Field(None, max_length=100)
    
    form1_data: Dict[str, Any]  # AS9102 Form 1
    form2_data: List[Dict[str, Any]]  # AS9102 Form 2 (array)
    form3_data: List[Dict[str, Any]]  # AS9102 Form 3 (array)
    
    inspection_method: str = Field(..., pattern="^(ACTUAL|DELTA|BASELINE)$")
    inspection_date: datetime
    inspector_name: str = Field(..., min_length=1, max_length=255)
    metadata: Optional[Dict[str, Any]] = None


class FAIReportResponse(BaseModel):
    """Response body for FAI report."""
    id: int
    part_number: str
    drawing_revision: str
    content_hash: str
    approval_status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class ConfigurationBaselineCreate(BaseModel):
    """Request body for configuration baseline."""
    assembly_id: str = Field(..., min_length=1, max_length=100)
    assembly_name: str = Field(..., min_length=1, max_length=255)
    serial_number: Optional[str] = Field(None, max_length=100)
    baseline_data: List[Dict[str, Any]]  # Component list with part numbers, revisions
    manufacturing_date: datetime
    fai_report_id: Optional[int] = None
    notes: Optional[str] = None


class ConfigurationBaselineResponse(BaseModel):
    """Response body for configuration baseline."""
    id: int
    assembly_id: str
    serial_number: Optional[str]
    baseline_hash: str
    lifecycle_status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class NADCAPEvidenceCreate(BaseModel):
    """Request body for NADCAP special process evidence."""
    process_type: str = Field(..., pattern="^(HEAT_TREAT|WELDING|NDT|CHEMICAL)$")
    part_number: str = Field(..., min_length=1, max_length=100)
    lot_number: Optional[str] = Field(None, max_length=100)
    process_parameters: Dict[str, Any]
    process_results: Dict[str, Any]
    operator_name: str = Field(..., min_length=1, max_length=255)
    equipment_id: str = Field(..., min_length=1, max_length=100)
    calibration_due_date: Optional[datetime] = None
    process_date: datetime
    nadcap_certification_number: Optional[str] = None
    certification_expiry: Optional[datetime] = None


class DashboardMetrics(BaseModel):
    """Dashboard metrics for Aerospace compliance."""
    total_fai_reports: int
    pending_fai_approvals: int
    active_configurations: int
    nadcap_expiring_soon: int
    avg_fai_approval_days: float


# FAI Endpoints
@router.post("/fai", response_model=FAIReportResponse, status_code=status.HTTP_201_CREATED)
async def create_fai_report(
    fai: FAIReportCreate,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Create AS9102 First Article Inspection report with cryptographic seal.
    
    **Compliance Standards:**
    - AS9102 Rev B (First Article Inspection)
    - AS9100 Rev D (Quality Management System)
    - NADCAP requirements (if applicable)
    
    **AS9102 Forms:**
    - Form 1: Part Number Accountability
    - Form 2: Product Accountability
    - Form 3: Characteristic Accountability
    """
    # Serialize all forms for hashing
    full_report = {
        "form_1": fai.form1_data,
        "form_2": fai.form2_data,
        "form_3": fai.form3_data,
        "part_number": fai.part_number,
        "drawing_revision": fai.drawing_revision,
        "inspection_date": fai.inspection_date.isoformat()
    }
    
    # Calculate integrity hash
    report_json = json.dumps(full_report, sort_keys=True)
    content_hash = hashlib.sha256(report_json.encode()).hexdigest()
    
    # Check for duplicate (idempotency) - scoped to tenant
    existing = db.query(FAIReport).filter(
        FAIReport.content_hash == content_hash,
        FAIReport.tenant_id == tenant_id
    ).first()
    if existing:
        return FAIReportResponse(
            id=existing.id,
            part_number=existing.part_number,
            drawing_revision=existing.drawing_revision,
            content_hash=existing.content_hash,
            approval_status=existing.approval_status,
            created_at=existing.created_at
        )
    
    # Create FAI record with tenant_id
    fai_report = FAIReport(
        tenant_id=tenant_id,
        part_number=fai.part_number,
        part_name=fai.part_name,
        drawing_number=fai.drawing_number,
        drawing_revision=fai.drawing_revision,
        customer_name=fai.customer_name,
        customer_part_number=fai.customer_part_number,
        form1_data=fai.form1_data,
        form2_data=fai.form2_data,
        form3_data=fai.form3_data,
        inspection_method=fai.inspection_method,
        inspection_date=fai.inspection_date,
        inspector_name=fai.inspector_name,
        content_hash=content_hash,
        approval_status="PENDING",
        fai_metadata=fai.metadata,
        created_at=datetime.utcnow()
    )
    
    db.add(fai_report)
    db.commit()
    db.refresh(fai_report)
    
    return FAIReportResponse(
        id=fai_report.id,
        part_number=fai_report.part_number,
        drawing_revision=fai_report.drawing_revision,
        content_hash=fai_report.content_hash,
        approval_status=fai_report.approval_status,
        created_at=fai_report.created_at
    )


@router.get("/fai/{fai_id}")
async def get_fai_report(
    fai_id: int,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Retrieve FAI report with all forms and integrity verification."""
    fai = db.query(FAIReport).filter(
        FAIReport.id == fai_id,
        FAIReport.tenant_id == tenant_id
    ).first()
    
    if not fai:
        raise HTTPException(status_code=404, detail="FAI report not found")
    
    return {
        "id": fai.id,
        "part_number": fai.part_number,
        "part_name": fai.part_name,
        "drawing_number": fai.drawing_number,
        "drawing_revision": fai.drawing_revision,
        "customer_name": fai.customer_name,
        "customer_part_number": fai.customer_part_number,
        "form1_data": fai.form1_data,
        "form2_data": fai.form2_data,
        "form3_data": fai.form3_data,
        "inspection_method": fai.inspection_method,
        "inspection_date": fai.inspection_date.isoformat(),
        "inspector_name": fai.inspector_name,
        "content_hash": fai.content_hash,
        "approval_status": fai.approval_status,
        "approval_date": fai.approval_date.isoformat() if fai.approval_date else None,
        "approval_notes": fai.approval_notes,
        "created_at": fai.created_at.isoformat()
    }


@router.patch("/fai/{fai_id}/approve")
async def approve_fai_report(
    fai_id: int,
    request: Request,
    approval_status: str = Query(..., pattern="^(APPROVED|REJECTED)$"),
    approval_notes: Optional[str] = None,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Update FAI approval status (typically by customer quality engineer)."""
    fai = db.query(FAIReport).filter(
        FAIReport.id == fai_id,
        FAIReport.tenant_id == tenant_id
    ).first()
    
    if not fai:
        raise HTTPException(status_code=404, detail="FAI report not found")
    
    fai.approval_status = approval_status
    fai.approval_date = datetime.utcnow()
    fai.approval_notes = approval_notes
    fai.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(fai)
    
    return {
        "id": fai.id,
        "approval_status": fai.approval_status,
        "approval_date": fai.approval_date.isoformat(),
        "approval_notes": fai.approval_notes
    }


# Configuration Baseline Endpoints
@router.post("/config-baseline", response_model=ConfigurationBaselineResponse, status_code=status.HTTP_201_CREATED)
async def create_configuration_baseline(
    baseline: ConfigurationBaselineCreate,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Create SHA-256 configuration baseline for 30-year lifecycle tracking.
    
    **Purpose:**
    - Track exact component revisions in each assembly
    - Support field service and repairs decades after production
    - Maintain part genealogy for recalls and investigations
    """
    # Serialize baseline data
    baseline_json = json.dumps({
        "assembly_id": baseline.assembly_id,
        "serial_number": baseline.serial_number,
        "components": baseline.baseline_data,
        "manufacturing_date": baseline.manufacturing_date.isoformat()
    }, sort_keys=True)
    
    baseline_hash = hashlib.sha256(baseline_json.encode()).hexdigest()
    
    # Check for duplicate - scoped to tenant
    existing = db.query(ConfigurationBaseline).filter(
        ConfigurationBaseline.baseline_hash == baseline_hash,
        ConfigurationBaseline.tenant_id == tenant_id
    ).first()
    
    if existing:
        return ConfigurationBaselineResponse(
            id=existing.id,
            assembly_id=existing.assembly_id,
            serial_number=existing.serial_number,
            baseline_hash=existing.baseline_hash,
            lifecycle_status=existing.lifecycle_status,
            created_at=existing.created_at
        )
    
    # Create baseline with tenant_id
    config_baseline = ConfigurationBaseline(
        tenant_id=tenant_id,
        assembly_id=baseline.assembly_id,
        assembly_name=baseline.assembly_name,
        serial_number=baseline.serial_number,
        baseline_data=baseline.baseline_data,
        baseline_hash=baseline_hash,
        fai_report_id=baseline.fai_report_id,
        manufacturing_date=baseline.manufacturing_date,
        lifecycle_status="ACTIVE",
        notes=baseline.notes,
        created_at=datetime.utcnow()
    )
    
    db.add(config_baseline)
    db.commit()
    db.refresh(config_baseline)
    
    return ConfigurationBaselineResponse(
        id=config_baseline.id,
        assembly_id=config_baseline.assembly_id,
        serial_number=config_baseline.serial_number,
        baseline_hash=config_baseline.baseline_hash,
        lifecycle_status=config_baseline.lifecycle_status,
        created_at=config_baseline.created_at
    )


@router.get("/config-baseline/{baseline_id}")
async def get_configuration_baseline(
    baseline_id: int,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Retrieve configuration baseline with full component list."""
    baseline = db.query(ConfigurationBaseline).filter(
        ConfigurationBaseline.id == baseline_id,
        ConfigurationBaseline.tenant_id == tenant_id
    ).first()
    
    if not baseline:
        raise HTTPException(status_code=404, detail="Configuration baseline not found")
    
    return {
        "id": baseline.id,
        "assembly_id": baseline.assembly_id,
        "assembly_name": baseline.assembly_name,
        "serial_number": baseline.serial_number,
        "baseline_data": baseline.baseline_data,
        "baseline_hash": baseline.baseline_hash,
        "fai_report_id": baseline.fai_report_id,
        "manufacturing_date": baseline.manufacturing_date.isoformat(),
        "end_of_life_date": baseline.end_of_life_date.isoformat() if baseline.end_of_life_date else None,
        "lifecycle_status": baseline.lifecycle_status,
        "notes": baseline.notes,
        "created_at": baseline.created_at.isoformat()
    }


# NADCAP Evidence Endpoints
@router.post("/nadcap-evidence", status_code=status.HTTP_201_CREATED)
async def create_nadcap_evidence(
    evidence: NADCAPEvidenceCreate,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Record NADCAP special process evidence with pyrometry logs, heat treat data, etc.
    
    **NADCAP Process Types:**
    - HEAT_TREAT: Temperature, time, atmosphere, pyrometry logs
    - WELDING: Parameters, weld maps, NDT results
    - NDT: Inspection results, technician certification
    - CHEMICAL: Chemistry, immersion time, tank certification
    """
    # Create content hash
    content = json.dumps({
        "process_type": evidence.process_type,
        "part_number": evidence.part_number,
        "process_parameters": evidence.process_parameters,
        "process_results": evidence.process_results,
        "process_date": evidence.process_date.isoformat()
    }, sort_keys=True)
    
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    
    # Create evidence record with tenant_id
    nadcap = NADCAPEvidence(
        tenant_id=tenant_id,
        process_type=evidence.process_type,
        part_number=evidence.part_number,
        lot_number=evidence.lot_number,
        process_parameters=evidence.process_parameters,
        process_results=evidence.process_results,
        operator_name=evidence.operator_name,
        equipment_id=evidence.equipment_id,
        calibration_due_date=evidence.calibration_due_date,
        process_date=evidence.process_date,
        content_hash=content_hash,
        nadcap_certification_number=evidence.nadcap_certification_number,
        certification_expiry=evidence.certification_expiry,
        created_at=datetime.utcnow()
    )
    
    db.add(nadcap)
    db.commit()
    db.refresh(nadcap)
    
    return {
        "id": nadcap.id,
        "process_type": nadcap.process_type,
        "part_number": nadcap.part_number,
        "content_hash": nadcap.content_hash,
        "status": "recorded"
    }


@router.get("/dashboard", response_model=DashboardMetrics)
async def get_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Get dashboard metrics for Aerospace compliance overview."""
    # Total FAI reports for this tenant
    total_fai = db.query(func.count(FAIReport.id)).filter(
        FAIReport.tenant_id == tenant_id
    ).scalar() or 0
    
    # Pending FAI approvals for this tenant
    pending_fai = db.query(func.count(FAIReport.id)).filter(
        FAIReport.approval_status == "PENDING",
        FAIReport.tenant_id == tenant_id
    ).scalar() or 0
    
    # Active configurations for this tenant
    active_configs = db.query(func.count(ConfigurationBaseline.id)).filter(
        ConfigurationBaseline.lifecycle_status == "ACTIVE",
        ConfigurationBaseline.tenant_id == tenant_id
    ).scalar() or 0
    
    # NADCAP certifications expiring in next 90 days for this tenant
    ninety_days = datetime.utcnow() + timedelta(days=90)
    nadcap_expiring = db.query(func.count(NADCAPEvidence.id)).filter(
        NADCAPEvidence.certification_expiry.isnot(None),
        NADCAPEvidence.certification_expiry <= ninety_days,
        NADCAPEvidence.tenant_id == tenant_id
    ).scalar() or 0
    
    # Average FAI approval time for this tenant
    approved_fai = db.query(
        func.avg(
            func.extract('epoch', FAIReport.approval_date - FAIReport.created_at) / 86400
        )
    ).filter(
        FAIReport.approval_status == "APPROVED",
        FAIReport.approval_date.isnot(None),
        FAIReport.tenant_id == tenant_id
    ).scalar()
    
    avg_approval_days = float(approved_fai) if approved_fai else 0.0
    
    return DashboardMetrics(
        total_fai_reports=total_fai,
        pending_fai_approvals=pending_fai,
        active_configurations=active_configs,
        nadcap_expiring_soon=nadcap_expiring,
        avg_fai_approval_days=round(avg_approval_days, 1)
    )
