"""
BIM tracking and OSHA safety API.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import hashlib

from .models import BIMChangeRecord, OSHASafetyInspection, SubcontractorCertification
from .db_session import get_db
from .auth import require_api_key

import sys
import uuid
from pathlib import Path

# Add shared utilities (portable path resolution)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.middleware import get_current_tenant_id

router = APIRouter(prefix="/v1/construction", tags=["construction"])


class BIMChangeCreate(BaseModel):
    """Request body for creating BIM change record."""
    project_id: str = Field(..., description="Unique project identifier")
    project_name: str = Field(..., description="Name of the construction project")
    change_number: str = Field(..., description="Unique change control number")
    change_type: str = Field(..., pattern="^(RFI|SUBMITTAL|CHANGE_ORDER|DESIGN_REVISION)$", description="Type of BIM change: RFI (Request for Information), SUBMITTAL, CHANGE_ORDER, or DESIGN_REVISION")
    description: str = Field(..., description="Detailed description of the change")
    file_name: str = Field(..., description="Name of the BIM file")
    file_version: str = Field(..., description="Version number of the BIM file")
    file_content: str = Field(..., description="Base64-encoded content of the BIM file")
    submitted_by: str = Field(..., description="Name or ID of the person submitting the change")


class OSHAInspectionCreate(BaseModel):
    """Request body for creating OSHA safety inspection record."""
    project_id: str = Field(..., description="Unique project identifier")
    inspection_date: datetime = Field(..., description="Date and time of the safety inspection")
    inspector_name: str = Field(..., description="Name of the OSHA inspector")
    inspection_type: str = Field(..., pattern="^(WEEKLY|MONTHLY|INCIDENT|OSHA_VISIT)$", description="Type of inspection: WEEKLY, MONTHLY, INCIDENT, or OSHA_VISIT")
    violations_found: int = Field(0, description="Number of safety violations found during inspection")
    violation_description: str = Field(None, description="Detailed description of any violations found")


@router.post("/bim-change", status_code=status.HTTP_201_CREATED)
async def create_bim_change(
    change: BIMChangeCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Create BIM change record with SHA-256 versioning.
    
    Tracks design changes, submittals, RFIs, and change orders with cryptographic integrity.
    Essential for construction document control and audit trails.
    
    **Change Types:**
    - RFI: Request for Information
    - SUBMITTAL: Material/equipment submittals
    - CHANGE_ORDER: Approved design modifications
    - DESIGN_REVISION: Drawing revisions
    """
    file_hash = hashlib.sha256(change.file_content.encode()).hexdigest()
    
    bim_change = BIMChangeRecord(
        tenant_id=tenant_id,
        project_id=change.project_id,
        project_name=change.project_name,
        change_number=change.change_number,
        change_type=change.change_type,
        description=change.description,
        file_name=change.file_name,
        file_version=change.file_version,
        file_hash=file_hash,
        submitted_by=change.submitted_by,
        submission_date=datetime.utcnow(),
        status="PENDING"
    )
    
    db.add(bim_change)
    db.commit()
    db.refresh(bim_change)
    
    return {"id": bim_change.id, "change_number": bim_change.change_number, "file_hash": file_hash}


@router.post("/osha-inspection", status_code=status.HTTP_201_CREATED)
async def create_osha_inspection(
    inspection: OSHAInspectionCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Record OSHA safety inspection per 29 CFR 1926 (Construction Standards).
    
    **Compliance Standards:**
    - 29 CFR 1926 (OSHA Construction Standards)
    - Required weekly/monthly jobsite inspections
    - Incident investigation documentation
    - OSHA visit documentation
    
    **Inspection Types:**
    - WEEKLY: Regular jobsite safety walks
    - MONTHLY: Comprehensive site inspections
    - INCIDENT: Post-accident investigations
    - OSHA_VISIT: Official OSHA inspector visits
    """
    osha_inspection = OSHASafetyInspection(
        tenant_id=tenant_id,
        project_id=inspection.project_id,
        inspection_date=inspection.inspection_date,
        inspector_name=inspection.inspector_name,
        inspection_type=inspection.inspection_type,
        violations_found=inspection.violations_found,
        violation_description=inspection.violation_description,
        status="OPEN" if inspection.violations_found > 0 else "CLOSED"
    )
    
    db.add(osha_inspection)
    db.commit()
    db.refresh(osha_inspection)
    
    return {"id": osha_inspection.id, "violations_found": osha_inspection.violations_found}


@router.get("/dashboard")
async def get_dashboard(
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Construction compliance dashboard metrics.
    
    Provides real-time overview of BIM change control and OSHA safety status
    for project managers and compliance officers.
    """
    total_changes = db.query(func.count(BIMChangeRecord.id)).filter(
        BIMChangeRecord.tenant_id == tenant_id
    ).scalar() or 0
    pending_changes = db.query(func.count(BIMChangeRecord.id)).filter(
        BIMChangeRecord.status == "PENDING",
        BIMChangeRecord.tenant_id == tenant_id
    ).scalar() or 0
    
    total_inspections = db.query(func.count(OSHASafetyInspection.id)).filter(
        OSHASafetyInspection.tenant_id == tenant_id
    ).scalar() or 0
    open_violations = db.query(func.count(OSHASafetyInspection.id)).filter(
        OSHASafetyInspection.violations_found > 0,
        OSHASafetyInspection.status != "CLOSED",
        OSHASafetyInspection.tenant_id == tenant_id
    ).scalar() or 0
    
    return {
        "total_bim_changes": total_changes,
        "pending_approvals": pending_changes,
        "total_osha_inspections": total_inspections,
        "open_violations": open_violations
    }
