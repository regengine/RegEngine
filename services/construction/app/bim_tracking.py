"""
BIM tracking and OSHA safety API.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from typing import Optional
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
    project_id: str
    project_name: str
    change_number: str
    change_type: str = Field(..., pattern="^(RFI|SUBMITTAL|CHANGE_ORDER|DESIGN_REVISION)$")
    description: str
    file_name: str
    file_version: str
    file_content: str
    submitted_by: str


class OSHAInspectionCreate(BaseModel):
    project_id: str
    inspection_date: datetime
    inspector_name: str
    inspection_type: str = Field(..., pattern="^(WEEKLY|MONTHLY|INCIDENT|OSHA_VISIT)$")
    violations_found: int = 0
    violation_description: Optional[str] = None


@router.post("/bim-change", status_code=status.HTTP_201_CREATED)
async def create_bim_change(
    change: BIMChangeCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Create BIM change record with SHA-256 versioning."""
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
    """Record OSHA safety inspection per 29 CFR 1926."""
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
    """Construction compliance dashboard metrics."""
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
