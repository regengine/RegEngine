"""
Production Compliance OS — API Routes

FastAPI routes for the Production Compliance OS add-on module.
Provides RESTful endpoints for companies, projects, locations,
engagements, timecards, tasks, and evidence management.

Adapted to use synchronous SQLAlchemy sessions matching the admin service.
"""

from __future__ import annotations

import uuid as uuid_module
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status, Header, UploadFile, File, Form
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from .config import get_settings
from . import s3_utils

from .database import get_pcos_session
from .models import TenantContext
from .sqlalchemy_models import UserModel
from .pcos_models import (
    # SQLAlchemy Models
    PCOSCompanyModel,
    PCOSProjectModel,
    PCOSLocationModel,
    PCOSPersonModel,
    PCOSEngagementModel,
    PCOSTimecardModel,
    PCOSTaskModel,
    PCOSEvidenceModel,
    PCOSBudgetModel,
    PCOSBudgetLineItemModel,
    PCOSUnionRateCheckModel,
    PCOSTaxCreditApplicationModel,
    PCOSQualifiedSpendCategoryModel,
    PCOSFormTemplateModel,
    PCOSGeneratedFormModel,
    PCOSClassificationAnalysisModel,
    PCOSClassificationExemptionModel,
    PCOSDocumentRequirementModel,
    PCOSEngagementDocumentModel,
    PCOSVisaCategoryModel,
    PCOSPersonVisaStatusModel,
    PCOSRuleEvaluationModel,
    PCOSComplianceSnapshotModel,
    PCOSAuditEventModel,
    # Pydantic Schemas
    CompanyCreateSchema,
    CompanyUpdateSchema,
    CompanyResponseSchema,
    ProjectCreateSchema,
    ProjectUpdateSchema,
    ProjectResponseSchema,
    LocationCreateSchema,
    LocationResponseSchema,
    EngagementCreateSchema,
    EngagementResponseSchema,
    TimecardCreateSchema,
    TimecardResponseSchema,
    TaskResponseSchema,
    TaskUpdateSchema,
    EvidenceCreateSchema,
    EvidenceResponseSchema,
    PersonCreateSchema,
    PersonResponseSchema,
    GateEvaluationResponseSchema,
    # Enums
    GateState,
    TaskStatus,
)

logger = structlog.get_logger("pcos.routes")

# Create router with PCOS prefix
router = APIRouter(prefix="/pcos", tags=["Production Compliance OS"])


# =============================================================================
# HELPER DEPENDENCIES
# =============================================================================

def get_pcos_tenant_context(
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    db: Session = Depends(get_pcos_session),
) -> tuple[Session, UUID]:
    """
    Get Entertainment database session with tenant context set for PCOS operations.
    
    As of V002 migration (Jan 31, 2026), all PCOS tables are in the Entertainment DB.
    For development/testing, uses header-based tenant ID.
    """
    if not x_tenant_id:
        # Default tenant for development
        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    else:
        try:
            tenant_id = UUID(x_tenant_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid tenant ID format")
    
    # Set tenant context for RLS
    TenantContext.set_tenant_context(db, tenant_id)
    
    return db, tenant_id


# =============================================================================
# DASHBOARD ENDPOINTS
# =============================================================================

@router.get("/dashboard")
def get_dashboard_metrics(
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Get high-level dashboard metrics for PCOS."""
    db, tenant_id = ctx
    
    from sqlalchemy import func
    from datetime import date as date_type, timedelta
    
    # Total projects
    total_projects = db.execute(
        select(func.count()).select_from(PCOSProjectModel).where(
            PCOSProjectModel.tenant_id == tenant_id
        )
    ).scalar() or 0
    
    # Active projects (not archived)
    active_projects = db.execute(
        select(func.count()).select_from(PCOSProjectModel).where(
            PCOSProjectModel.tenant_id == tenant_id,
            PCOSProjectModel.gate_state != GateState.ARCHIVED.value
        )
    ).scalar() or 0
    
    # Greenlit projects
    greenlit_projects = db.execute(
        select(func.count()).select_from(PCOSProjectModel).where(
            PCOSProjectModel.tenant_id == tenant_id,
            PCOSProjectModel.gate_state.in_([GateState.GREENLIT.value, GateState.IN_PRODUCTION.value])
        )
    ).scalar() or 0
    
    # Overdue tasks
    today = date_type.today()
    overdue_tasks = db.execute(
        select(func.count()).select_from(PCOSTaskModel).where(
            PCOSTaskModel.tenant_id == tenant_id,
            PCOSTaskModel.status == TaskStatus.PENDING.value,
            PCOSTaskModel.due_date < today
        )
    ).scalar() or 0
    
    # Total blocking tasks
    total_blocking_tasks = db.execute(
        select(func.count()).select_from(PCOSTaskModel).where(
            PCOSTaskModel.tenant_id == tenant_id,
            PCOSTaskModel.status == TaskStatus.PENDING.value,
            PCOSTaskModel.is_blocking == True
        )
    ).scalar() or 0
    
    # Expiring permits (next 30 days) - simplified for now
    expiring_permits = 0
    
    # Expiring insurance (next 30 days) - simplified for now
    expiring_insurance = 0
    
    # Average risk score
    avg_risk = db.execute(
        select(func.avg(PCOSProjectModel.risk_score)).where(
            PCOSProjectModel.tenant_id == tenant_id,
            PCOSProjectModel.gate_state != GateState.ARCHIVED.value
        )
    ).scalar()
    avg_risk_score = float(avg_risk or 0)
    
    return {
        "total_projects": total_projects,
        "active_projects": active_projects,
        "greenlit_projects": greenlit_projects,
        "overdue_tasks": overdue_tasks,
        "expiring_permits": expiring_permits,
        "expiring_insurance": expiring_insurance,
        "total_blocking_tasks": total_blocking_tasks,
        "avg_risk_score": round(avg_risk_score, 2)
    }


# =============================================================================
# COMPANY ENDPOINTS
# =============================================================================

@router.post("/companies", response_model=CompanyResponseSchema, status_code=status.HTTP_201_CREATED)
def create_company(
    company_data: CompanyCreateSchema,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Create a new production company profile."""
    db, tenant_id = ctx
    
    company = PCOSCompanyModel(
        tenant_id=tenant_id,
        legal_name=company_data.legal_name,
        entity_type=company_data.entity_type.value,
        ein=company_data.ein,
        sos_entity_number=company_data.sos_entity_number,
        has_la_city_presence=company_data.has_la_city_presence,
        owner_pay_mode=company_data.owner_pay_mode.value if company_data.owner_pay_mode else None,
    )
    
    if company_data.legal_address:
        company.legal_address_line1 = company_data.legal_address.line1
        company.legal_address_line2 = company_data.legal_address.line2
        company.legal_address_city = company_data.legal_address.city
        company.legal_address_state = company_data.legal_address.state
        company.legal_address_zip = company_data.legal_address.zip
    
    if company_data.mailing_address:
        company.mailing_address_line1 = company_data.mailing_address.line1
        company.mailing_address_line2 = company_data.mailing_address.line2
        company.mailing_address_city = company_data.mailing_address.city
        company.mailing_address_state = company_data.mailing_address.state
        company.mailing_address_zip = company_data.mailing_address.zip
    
    db.add(company)
    db.commit()
    db.refresh(company)
    
    logger.info("company_created", company_id=str(company.id), tenant_id=str(tenant_id))
    
    return company


@router.get("/companies", response_model=list[CompanyResponseSchema])
def list_companies(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """List all companies for the tenant."""
    db, tenant_id = ctx
    
    query = select(PCOSCompanyModel).where(PCOSCompanyModel.tenant_id == tenant_id)
    
    if status_filter:
        query = query.where(PCOSCompanyModel.status == status_filter)
    
    query = query.order_by(PCOSCompanyModel.created_at.desc())
    
    result = db.execute(query)
    return result.scalars().all()


@router.get("/companies/{company_id}", response_model=CompanyResponseSchema)
def get_company(
    company_id: uuid_module.UUID,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Get a company by ID."""
    db, tenant_id = ctx
    
    result = db.execute(
        select(PCOSCompanyModel).where(
            PCOSCompanyModel.id == company_id,
            PCOSCompanyModel.tenant_id == tenant_id,
        )
    )
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    return company


@router.patch("/companies/{company_id}", response_model=CompanyResponseSchema)
def update_company(
    company_id: uuid_module.UUID,
    update_data: CompanyUpdateSchema,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Update a company."""
    db, tenant_id = ctx
    
    result = db.execute(
        select(PCOSCompanyModel).where(
            PCOSCompanyModel.id == company_id,
            PCOSCompanyModel.tenant_id == tenant_id,
        )
    )
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        if field == "entity_type" and value:
            value = value.value
        elif field == "owner_pay_mode" and value:
            value = value.value
        setattr(company, field, value)
    
    db.commit()
    db.refresh(company)
    
    logger.info("company_updated", company_id=str(company_id), tenant_id=str(tenant_id))
    
    return company


# =============================================================================
# PROJECT ENDPOINTS
# =============================================================================

@router.post("/projects", response_model=ProjectResponseSchema, status_code=status.HTTP_201_CREATED)
def create_project(
    project_data: ProjectCreateSchema,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Create a new production project."""
    db, tenant_id = ctx
    
    # Verify company exists
    company_result = db.execute(
        select(PCOSCompanyModel).where(
            PCOSCompanyModel.id == project_data.company_id,
            PCOSCompanyModel.tenant_id == tenant_id,
        )
    )
    if not company_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Company not found")
    
    project = PCOSProjectModel(
        tenant_id=tenant_id,
        company_id=project_data.company_id,
        name=project_data.name,
        code=project_data.code,
        project_type=project_data.project_type.value,
        is_commercial=project_data.is_commercial,
        client_name=project_data.client_name,
        start_date=project_data.start_date,
        end_date=project_data.end_date,
        first_shoot_date=project_data.first_shoot_date,
        union_status=project_data.union_status,
        minor_involved=project_data.minor_involved,
        gate_state=GateState.DRAFT.value,
    )
    
    db.add(project)
    db.commit()
    db.refresh(project)
    
    logger.info("project_created", project_id=str(project.id), tenant_id=str(tenant_id))
    
    return project


@router.get("/projects", response_model=list[ProjectResponseSchema])
def list_projects(
    company_id: Optional[uuid_module.UUID] = Query(None),
    gate_state: Optional[str] = Query(None),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """List all projects for the tenant."""
    db, tenant_id = ctx
    
    query = select(PCOSProjectModel).where(PCOSProjectModel.tenant_id == tenant_id)
    
    if company_id:
        query = query.where(PCOSProjectModel.company_id == company_id)
    if gate_state:
        query = query.where(PCOSProjectModel.gate_state == gate_state)
    
    query = query.order_by(PCOSProjectModel.created_at.desc())
    
    result = db.execute(query)
    return result.scalars().all()


@router.get("/projects/{project_id}", response_model=ProjectResponseSchema)
def get_project(
    project_id: uuid_module.UUID,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Get a project by ID."""
    db, tenant_id = ctx
    
    result = db.execute(
        select(PCOSProjectModel).where(
            PCOSProjectModel.id == project_id,
            PCOSProjectModel.tenant_id == tenant_id,
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return project


@router.patch("/projects/{project_id}", response_model=ProjectResponseSchema)
def update_project(
    project_id: uuid_module.UUID,
    update_data: ProjectUpdateSchema,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Update a project."""
    db, tenant_id = ctx
    
    result = db.execute(
        select(PCOSProjectModel).where(
            PCOSProjectModel.id == project_id,
            PCOSProjectModel.tenant_id == tenant_id,
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        if field == "project_type" and value:
            value = value.value
        setattr(project, field, value)
    
    db.commit()
    db.refresh(project)
    
    logger.info("project_updated", project_id=str(project_id), tenant_id=str(tenant_id))
    
    return project


# =============================================================================
# GATE STATUS ENDPOINTS
# =============================================================================

@router.get("/projects/{project_id}/gate-status")
def get_project_gate_status(
    project_id: uuid_module.UUID,
    target_state: Optional[str] = Query(None, description="Target state to evaluate"),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Get the current gate status for a project."""
    db, tenant_id = ctx
    
    # Get project
    result = db.execute(
        select(PCOSProjectModel).where(
            PCOSProjectModel.id == project_id,
            PCOSProjectModel.tenant_id == tenant_id,
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get blocking tasks count
    blocking_tasks_result = db.execute(
        select(PCOSTaskModel).where(
            PCOSTaskModel.source_type == "project",
            PCOSTaskModel.source_id == project_id,
            PCOSTaskModel.tenant_id == tenant_id,
            PCOSTaskModel.is_blocking == True,
            PCOSTaskModel.status.in_(["pending", "in_progress", "blocked"]),
        )
    )
    blocking_tasks = blocking_tasks_result.scalars().all()
    
    # Calculate simple risk score
    risk_score = min(len(blocking_tasks) * 15, 100)
    
    current_state = GateState(project.gate_state)
    can_transition = len(blocking_tasks) == 0
    
    return {
        "id": str(uuid_module.uuid4()),
        "project_id": str(project_id),
        "current_state": current_state.value,
        "target_state": target_state,
        "transition_allowed": can_transition,
        "blocking_tasks_count": len(blocking_tasks),
        "blocking_tasks": [
            {"id": str(t.id), "title": t.title, "status": t.status}
            for t in blocking_tasks
        ],
        "missing_evidence": [],
        "risk_score": risk_score,
        "reasons": [] if can_transition else [f"{len(blocking_tasks)} blocking tasks remain"],
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/projects/{project_id}/greenlight")
def greenlight_project(
    project_id: uuid_module.UUID,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Attempt to greenlight a project."""
    db, tenant_id = ctx
    
    # Get project
    result = db.execute(
        select(PCOSProjectModel).where(
            PCOSProjectModel.id == project_id,
            PCOSProjectModel.tenant_id == tenant_id,
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Check blocking tasks
    blocking_tasks_result = db.execute(
        select(PCOSTaskModel).where(
            PCOSTaskModel.source_type == "project",
            PCOSTaskModel.source_id == project_id,
            PCOSTaskModel.tenant_id == tenant_id,
            PCOSTaskModel.is_blocking == True,
            PCOSTaskModel.status.in_(["pending", "in_progress", "blocked"]),
        )
    )
    blocking_tasks = blocking_tasks_result.scalars().all()
    
    if blocking_tasks:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot greenlight: {len(blocking_tasks)} blocking task(s) remain"
        )
    
    # Transition to greenlit
    project.gate_state = GateState.GREENLIT.value
    project.gate_state_changed_at = datetime.now(timezone.utc)
    
    db.commit()
    
    logger.info("project_greenlit", project_id=str(project_id), tenant_id=str(tenant_id))
    
    return {
        "project_id": str(project_id),
        "current_state": GateState.GREENLIT.value,
        "transition_allowed": True,
        "message": "Project successfully greenlit",
    }


# =============================================================================
# LOCATION ENDPOINTS
# =============================================================================

@router.post("/projects/{project_id}/locations", response_model=LocationResponseSchema, status_code=status.HTTP_201_CREATED)
def add_location(
    project_id: uuid_module.UUID,
    location_data: LocationCreateSchema,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Add a location to a project."""
    db, tenant_id = ctx
    
    # Verify project exists
    project_result = db.execute(
        select(PCOSProjectModel).where(
            PCOSProjectModel.id == project_id,
            PCOSProjectModel.tenant_id == tenant_id,
        )
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Determine if permit is required
    permit_required = location_data.location_type.value in ["public_row", "certified_studio"]
    
    location = PCOSLocationModel(
        tenant_id=tenant_id,
        project_id=project_id,
        name=location_data.name,
        address_line1=location_data.address_line1,
        address_line2=location_data.address_line2,
        city=location_data.city,
        state=location_data.state,
        zip=location_data.zip,
        jurisdiction=location_data.jurisdiction.value,
        location_type=location_data.location_type.value,
        estimated_crew_size=location_data.estimated_crew_size,
        parking_spaces_needed=location_data.parking_spaces_needed,
        filming_hours_start=location_data.filming_hours_start,
        filming_hours_end=location_data.filming_hours_end,
        has_generator=location_data.has_generator,
        has_special_effects=location_data.has_special_effects,
        noise_level=location_data.noise_level,
        permit_required=permit_required,
        shoot_dates=location_data.shoot_dates,
    )
    
    db.add(location)
    db.commit()
    db.refresh(location)
    
    logger.info(
        "location_added",
        location_id=str(location.id),
        project_id=str(project_id),
        permit_required=permit_required,
    )
    
    return location


@router.get("/projects/{project_id}/locations", response_model=list[LocationResponseSchema])
def list_project_locations(
    project_id: uuid_module.UUID,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """List all locations for a project."""
    db, tenant_id = ctx
    
    result = db.execute(
        select(PCOSLocationModel).where(
            PCOSLocationModel.project_id == project_id,
            PCOSLocationModel.tenant_id == tenant_id,
        ).order_by(PCOSLocationModel.created_at)
    )
    return result.scalars().all()


# =============================================================================
# PEOPLE ENDPOINTS
# =============================================================================

@router.post("/people", response_model=PersonResponseSchema, status_code=status.HTTP_201_CREATED)
def create_person(
    person_data: PersonCreateSchema,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Create a person in the people registry."""
    db, tenant_id = ctx
    
    person = PCOSPersonModel(
        tenant_id=tenant_id,
        first_name=person_data.first_name,
        last_name=person_data.last_name,
        email=person_data.email,
        phone=person_data.phone,
        date_of_birth=person_data.date_of_birth,
        preferred_classification=person_data.preferred_classification.value if person_data.preferred_classification else None,
        is_loan_out=person_data.is_loan_out,
        loan_out_company_name=person_data.loan_out_company_name,
        emergency_contact_name=person_data.emergency_contact_name,
        emergency_contact_phone=person_data.emergency_contact_phone,
        emergency_contact_relation=person_data.emergency_contact_relation,
    )
    
    if person_data.address:
        person.address_line1 = person_data.address.line1
        person.address_line2 = person_data.address.line2
        person.city = person_data.address.city
        person.state = person_data.address.state
        person.zip = person_data.address.zip
    
    db.add(person)
    db.commit()
    db.refresh(person)
    
    logger.info("person_created", person_id=str(person.id), tenant_id=str(tenant_id))
    
    return person


@router.get("/people", response_model=list[PersonResponseSchema])
def list_people(
    search: Optional[str] = Query(None, description="Search by name or email"),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """List people in the registry."""
    db, tenant_id = ctx
    
    query = select(PCOSPersonModel).where(
        PCOSPersonModel.tenant_id == tenant_id,
        PCOSPersonModel.status == "active",
    )
    
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (PCOSPersonModel.first_name.ilike(search_pattern)) |
            (PCOSPersonModel.last_name.ilike(search_pattern)) |
            (PCOSPersonModel.email.ilike(search_pattern))
        )
    
    query = query.order_by(PCOSPersonModel.last_name, PCOSPersonModel.first_name)
    
    result = db.execute(query)
    return result.scalars().all()


# =============================================================================
# ENGAGEMENT ENDPOINTS
# =============================================================================

@router.post("/projects/{project_id}/engagements", response_model=EngagementResponseSchema, status_code=status.HTTP_201_CREATED)
def create_engagement(
    project_id: uuid_module.UUID,
    engagement_data: EngagementCreateSchema,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Create an engagement (assign person to project)."""
    db, tenant_id = ctx
    
    # Verify project exists
    project_result = db.execute(
        select(PCOSProjectModel).where(
            PCOSProjectModel.id == project_id,
            PCOSProjectModel.tenant_id == tenant_id,
        )
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Verify person exists
    person_result = db.execute(
        select(PCOSPersonModel).where(
            PCOSPersonModel.id == engagement_data.person_id,
            PCOSPersonModel.tenant_id == tenant_id,
        )
    )
    if not person_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Person not found")
    
    engagement = PCOSEngagementModel(
        tenant_id=tenant_id,
        project_id=project_id,
        person_id=engagement_data.person_id,
        role_title=engagement_data.role_title,
        department=engagement_data.department,
        classification=engagement_data.classification.value,
        pay_rate=engagement_data.pay_rate,
        pay_type=engagement_data.pay_type,
        overtime_eligible=engagement_data.overtime_eligible,
        start_date=engagement_data.start_date,
        end_date=engagement_data.end_date,
        guaranteed_days=engagement_data.guaranteed_days,
    )
    
    db.add(engagement)
    db.commit()
    db.refresh(engagement)
    
    logger.info(
        "engagement_created",
        engagement_id=str(engagement.id),
        project_id=str(project_id),
        classification=engagement_data.classification.value,
    )
    
    return engagement


@router.get("/projects/{project_id}/engagements", response_model=list[EngagementResponseSchema])
def list_project_engagements(
    project_id: uuid_module.UUID,
    classification: Optional[str] = Query(None),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """List all engagements for a project."""
    db, tenant_id = ctx
    
    query = select(PCOSEngagementModel).where(
        PCOSEngagementModel.project_id == project_id,
        PCOSEngagementModel.tenant_id == tenant_id,
    )
    
    if classification:
        query = query.where(PCOSEngagementModel.classification == classification)
    
    query = query.order_by(PCOSEngagementModel.created_at)
    
    result = db.execute(query)
    return result.scalars().all()


# =============================================================================
# TASK ENDPOINTS
# =============================================================================

@router.get("/tasks", response_model=list[TaskResponseSchema])
def list_tasks(
    project_id: Optional[uuid_module.UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    is_blocking: Optional[bool] = Query(None),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """List compliance tasks."""
    db, tenant_id = ctx
    
    query = select(PCOSTaskModel).where(PCOSTaskModel.tenant_id == tenant_id)
    
    if project_id:
        query = query.where(
            PCOSTaskModel.source_type == "project",
            PCOSTaskModel.source_id == project_id,
        )
    if status_filter:
        query = query.where(PCOSTaskModel.status == status_filter)
    if is_blocking is not None:
        query = query.where(PCOSTaskModel.is_blocking == is_blocking)
    
    query = query.order_by(PCOSTaskModel.due_date.asc().nullslast(), PCOSTaskModel.created_at)
    
    result = db.execute(query)
    return result.scalars().all()


@router.patch("/tasks/{task_id}", response_model=TaskResponseSchema)
def update_task(
    task_id: uuid_module.UUID,
    update_data: TaskUpdateSchema,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Update a task status."""
    db, tenant_id = ctx
    
    result = db.execute(
        select(PCOSTaskModel).where(
            PCOSTaskModel.id == task_id,
            PCOSTaskModel.tenant_id == tenant_id,
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    update_dict = update_data.model_dump(exclude_unset=True)
    
    for field, value in update_dict.items():
        if field == "status" and value:
            value = value.value
            if value == TaskStatus.COMPLETED.value:
                task.completed_at = datetime.now(timezone.utc)
        setattr(task, field, value)
    
    db.commit()
    db.refresh(task)
    
    logger.info("task_updated", task_id=str(task_id), new_status=task.status)
    
    return task


# =============================================================================
# EVIDENCE ENDPOINTS
# =============================================================================

@router.get("/projects/{project_id}/evidence", response_model=list[EvidenceResponseSchema])
def list_project_evidence(
    project_id: uuid_module.UUID,
    evidence_type: Optional[str] = Query(None),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """List all evidence for a project."""
    db, tenant_id = ctx
    
    query = select(PCOSEvidenceModel).where(
        PCOSEvidenceModel.entity_type == "project",
        PCOSEvidenceModel.entity_id == project_id,
        PCOSEvidenceModel.tenant_id == tenant_id,
    )
    
    if evidence_type:
        query = query.where(PCOSEvidenceModel.evidence_type == evidence_type)
    
    query = query.order_by(PCOSEvidenceModel.created_at.desc())
    
    result = db.execute(query)
    return result.scalars().all()


@router.post("/evidence", response_model=EvidenceResponseSchema, status_code=status.HTTP_201_CREATED)
def upload_evidence(
    evidence_data: EvidenceCreateSchema,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Create an evidence record."""
    db, tenant_id = ctx
    
    evidence = PCOSEvidenceModel(
        tenant_id=tenant_id,
        entity_type=evidence_data.entity_type,
        entity_id=evidence_data.entity_id,
        evidence_type=evidence_data.evidence_type.value,
        title=evidence_data.title,
        description=evidence_data.description,
        valid_from=evidence_data.valid_from,
        valid_until=evidence_data.valid_until,
        s3_key=f"pcos/{tenant_id}/{evidence_data.entity_type}/{evidence_data.entity_id}/{uuid_module.uuid4()}",
    )
    
    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    
    logger.info(
        "evidence_created",
        evidence_id=str(evidence.id),
        entity_type=evidence_data.entity_type,
        entity_id=str(evidence_data.entity_id),
        evidence_type=evidence_data.evidence_type.value,
    )
    
    return evidence


@router.post("/documents/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form(...),
    project_id: Optional[str] = Form(None),
    entity_type: str = Form(default="project"),
    entity_id: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """
    Upload a document file to PCOS storage.

    This endpoint handles actual file uploads for compliance documents,
    storing them in S3 and creating evidence records.

    Supported file types: PDF, DOC, DOCX, JPG, JPEG, PNG
    Maximum file size: 10MB (configurable)

    Args:
        file: The file to upload
        category: Document category (permits, insurance, labor, minors, safety, union)
        project_id: Optional project ID to associate the document with
        entity_type: Type of entity (project, company, engagement, person)
        entity_id: ID of the entity to associate with (defaults to project_id if provided)
        title: Optional title for the document (defaults to filename)

    Returns:
        Evidence record with file metadata and storage location
    """
    db, tenant_id = ctx
    settings = get_settings()

    # Validate file type
    allowed_types = {
        "application/pdf": "pdf",
        "application/msword": "doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "image/jpeg": "jpg",
        "image/png": "png",
    }

    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, DOC, DOCX, JPG, PNG"
        )

    # Validate file size
    max_size = settings.max_upload_size_mb * 1024 * 1024
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {settings.max_upload_size_mb}MB"
        )
    # Reset file position for re-reading
    await file.seek(0)

    # Validate category
    valid_categories = {"permits", "insurance", "labor", "minors", "safety", "union"}
    if category not in valid_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be one of: {', '.join(valid_categories)}"
        )

    # Map category to evidence type
    category_to_evidence_type = {
        "permits": "permit_approved",
        "insurance": "coi",
        "labor": "signed_contract",
        "minors": "minor_work_permit",
        "safety": "iipp_policy",
        "union": "classification_memo_signed",
    }
    evidence_type = category_to_evidence_type.get(category, "other")

    # Determine entity
    final_entity_id = entity_id or project_id
    if not final_entity_id:
        raise HTTPException(
            status_code=400,
            detail="Either project_id or entity_id must be provided"
        )

    try:
        final_entity_id = UUID(final_entity_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entity ID format")

    # Generate S3 key
    file_ext = allowed_types[file.content_type]
    unique_id = uuid_module.uuid4()
    s3_key = f"pcos/{tenant_id}/{entity_type}/{final_entity_id}/{unique_id}.{file_ext}"

    # Upload to S3
    s3_uri, sha256_hash, file_size = s3_utils.upload_file(
        bucket=settings.pcos_bucket,
        key=s3_key,
        file_data=file.file,
        content_type=file.content_type,
    )

    # Create evidence record
    evidence = PCOSEvidenceModel(
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=final_entity_id,
        evidence_type=evidence_type,
        title=title or file.filename,
        file_name=file.filename,
        file_size_bytes=file_size,
        mime_type=file.content_type,
        s3_key=s3_key,
        sha256_hash=sha256_hash,
    )

    db.add(evidence)
    db.commit()
    db.refresh(evidence)

    logger.info(
        "document_uploaded",
        evidence_id=str(evidence.id),
        entity_type=entity_type,
        entity_id=str(final_entity_id),
        category=category,
        file_name=file.filename,
        file_size=file_size,
    )

    return {
        "id": str(evidence.id),
        "filename": evidence.file_name,
        "category": category,
        "evidence_type": evidence_type,
        "status": "uploaded",
        "uploadedAt": evidence.created_at.isoformat() if evidence.created_at else None,
        "fileSize": file_size,
        "mimeType": file.content_type,
        "sha256Hash": sha256_hash,
    }


@router.get("/documents/{document_id}/download")
def get_document_download_url(
    document_id: uuid_module.UUID,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """
    Get a presigned URL for downloading a document.

    The URL is valid for 1 hour.
    """
    db, tenant_id = ctx
    settings = get_settings()

    # Find evidence record
    result = db.execute(
        select(PCOSEvidenceModel).where(
            PCOSEvidenceModel.id == document_id,
            PCOSEvidenceModel.tenant_id == tenant_id,
        )
    )
    evidence = result.scalar_one_or_none()

    if not evidence:
        raise HTTPException(status_code=404, detail="Document not found")

    # Generate presigned URL
    download_url = s3_utils.generate_presigned_url(
        bucket=settings.pcos_bucket,
        key=evidence.s3_key,
        expires_in=3600,
    )

    return {
        "downloadUrl": download_url,
        "filename": evidence.file_name,
        "mimeType": evidence.mime_type,
        "expiresIn": 3600,
    }


# =============================================================================
# RISK & GUIDANCE ENDPOINTS
# =============================================================================

@router.get("/projects/{project_id}/risks")
def get_project_risks(
    project_id: uuid_module.UUID,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Get aggregated risk scores by category for a project."""
    from .pcos_fact_provider import PCOSFactProvider
    
    db, tenant_id = ctx
    
    # Verify project exists
    result = db.execute(
        select(PCOSProjectModel).where(
            PCOSProjectModel.id == project_id,
            PCOSProjectModel.tenant_id == tenant_id,
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get risk summary from fact provider
    provider = PCOSFactProvider(db=db, tenant_id=tenant_id)
    risk_categories = provider.get_risk_summary(project_id)
    
    # Calculate overall score
    overall_score = 0
    if risk_categories:
        overall_score = sum(c.score for c in risk_categories) // len(risk_categories)
    
    return {
        "project_id": str(project_id),
        "overall_risk_score": overall_score,
        "categories": [c.to_dict() for c in risk_categories],
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/projects/{project_id}/guidance")
def get_project_guidance(
    project_id: uuid_module.UUID,
    category: Optional[str] = Query(None, description="Filter by category"),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Get prioritized guidance items for a project."""
    from .pcos_fact_provider import PCOSFactProvider
    
    db, tenant_id = ctx
    
    # Verify project exists
    result = db.execute(
        select(PCOSProjectModel).where(
            PCOSProjectModel.id == project_id,
            PCOSProjectModel.tenant_id == tenant_id,
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get guidance from fact provider
    provider = PCOSFactProvider(db=db, tenant_id=tenant_id)
    guidance_items = provider.get_guidance_items(project_id)
    
    # Filter by category if specified
    if category:
        guidance_items = [g for g in guidance_items if g.category == category]
    
    return {
        "project_id": str(project_id),
        "total_items": len(guidance_items),
        "items": [g.to_dict() for g in guidance_items],
    }


@router.get("/projects/{project_id}/documents")
def list_project_documents(
    project_id: uuid_module.UUID,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """List all documents/evidence for a project with status tracking."""
    db, tenant_id = ctx
    
    # Verify project exists
    result = db.execute(
        select(PCOSProjectModel).where(
            PCOSProjectModel.id == project_id,
            PCOSProjectModel.tenant_id == tenant_id,
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get evidence records
    evidence_result = db.execute(
        select(PCOSEvidenceModel).where(
            PCOSEvidenceModel.entity_type == "project",
            PCOSEvidenceModel.entity_id == project_id,
            PCOSEvidenceModel.tenant_id == tenant_id,
        ).order_by(PCOSEvidenceModel.created_at.desc())
    )
    evidence_list = evidence_result.scalars().all()
    
    # Build document list with status
    documents = []
    for ev in evidence_list:
        documents.append({
            "id": str(ev.id),
            "name": ev.title or f"{ev.evidence_type} document",
            "type": ev.evidence_type,
            "category": _evidence_type_to_category(ev.evidence_type),
            "status": "verified" if ev.verified_at else "uploaded",
            "uploadedAt": ev.created_at.isoformat() if ev.created_at else None,
            "verifiedAt": ev.verified_at.isoformat() if ev.verified_at else None,
            "fileUrl": ev.s3_key,
        })
    
    return {
        "project_id": str(project_id),
        "total": len(documents),
        "documents": documents,
    }


def _evidence_type_to_category(evidence_type: str) -> str:
    """Map evidence type to risk category."""
    mapping = {
        "permit_approved": "permits",
        "coi": "insurance",
        "workers_comp_policy": "insurance",
        "classification_memo_signed": "labor",
        "minor_work_permit": "minors",
        "iipp_policy": "safety",
        "wvpp_policy": "safety",
        "w9": "labor",
        "i9": "labor",
        "w4": "labor",
    }
    return mapping.get(evidence_type, "other")


# =============================================================================
# BUDGET ENDPOINTS
# =============================================================================

@router.post("/projects/{project_id}/budgets", status_code=status.HTTP_201_CREATED)
def upload_budget(
    project_id: uuid_module.UUID,
    budget_data: dict,  # Contains parsed budget from frontend
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """
    Create a budget record from parsed spreadsheet data.
    
    Expected budget_data format:
    {
        "fileName": "budget.xlsx",
        "grandTotal": 40000,
        "subtotal": 36364,
        "contingency": 3636,
        "contingencyPercent": 10,
        "location": "CA",
        "departments": [
            {
                "code": "100",
                "name": "Above The Line",
                "lineItems": [
                    {"description": "Producer", "rate": 500, "quantity": 10, "extension": 5000, ...}
                ]
            }
        ]
    }
    """
    db, tenant_id = ctx
    
    # Verify project exists
    result = db.execute(
        select(PCOSProjectModel).where(
            PCOSProjectModel.id == project_id,
            PCOSProjectModel.tenant_id == tenant_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Deactivate any existing active budgets
    db.execute(
        PCOSBudgetModel.__table__.update()
        .where(PCOSBudgetModel.project_id == project_id)
        .where(PCOSBudgetModel.tenant_id == tenant_id)
        .where(PCOSBudgetModel.is_active == True)
        .values(is_active=False)
    )
    
    # Count compliance issues
    compliance_count = 0
    critical_count = 0
    for dept in budget_data.get("departments", []):
        for item in dept.get("lineItems", []):
            flags = item.get("complianceFlags", [])
            compliance_count += len(flags)
            if any("misclassification" in f or "critical" in f for f in flags):
                critical_count += 1
    
    # Create budget record
    budget = PCOSBudgetModel(
        tenant_id=tenant_id,
        project_id=project_id,
        source_file_name=budget_data.get("fileName", "budget.xlsx"),
        grand_total=budget_data.get("grandTotal", 0),
        subtotal=budget_data.get("subtotal", 0),
        contingency_amount=budget_data.get("contingency", 0),
        contingency_percent=budget_data.get("contingencyPercent", 0),
        detected_location=budget_data.get("location", "CA"),
        status="active",
        is_active=True,
        compliance_issue_count=compliance_count,
        critical_issue_count=critical_count,
        risk_score=min(100, critical_count * 25 + compliance_count * 5),
    )
    db.add(budget)
    db.flush()  # Get budget.id
    
    # Create line items
    line_number = 0
    for dept in budget_data.get("departments", []):
        for item in dept.get("lineItems", []):
            line_number += 1
            line_item = PCOSBudgetLineItemModel(
                tenant_id=tenant_id,
                budget_id=budget.id,
                row_number=line_number,
                cost_code=item.get("costCode"),
                department=dept.get("name"),
                description=item.get("description", "Unknown"),
                rate=item.get("rate", 0),
                quantity=item.get("quantity", 1),
                extension=item.get("extension", 0),
                classification=item.get("classification"),
                role_category=item.get("roleCategory"),
                deal_memo_status=item.get("dealMemoStatus"),
                compliance_flags=item.get("complianceFlags", []),
                raw_row_data=item,
            )
            db.add(line_item)
    
    db.commit()
    db.refresh(budget)
    
    logger.info(
        "budget_created",
        budget_id=str(budget.id),
        project_id=str(project_id),
        grand_total=float(budget.grand_total),
        line_item_count=line_number,
    )
    
    return {
        "id": str(budget.id),
        "project_id": str(project_id),
        "grand_total": float(budget.grand_total),
        "line_item_count": line_number,
        "compliance_issue_count": compliance_count,
        "risk_score": budget.risk_score,
        "created_at": budget.created_at.isoformat(),
    }


@router.get("/projects/{project_id}/budgets")
def list_project_budgets(
    project_id: uuid_module.UUID,
    active_only: bool = Query(True, description="Only return active budgets"),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """List all budgets for a project."""
    db, tenant_id = ctx
    
    query = select(PCOSBudgetModel).where(
        PCOSBudgetModel.project_id == project_id,
        PCOSBudgetModel.tenant_id == tenant_id,
    )
    
    if active_only:
        query = query.where(PCOSBudgetModel.is_active == True)
    
    query = query.order_by(PCOSBudgetModel.created_at.desc())
    
    result = db.execute(query)
    budgets = result.scalars().all()
    
    return [
        {
            "id": str(b.id),
            "source_file_name": b.source_file_name,
            "grand_total": float(b.grand_total),
            "subtotal": float(b.subtotal),
            "contingency_percent": float(b.contingency_percent) if b.contingency_percent else 0,
            "detected_location": b.detected_location,
            "is_active": b.is_active,
            "compliance_issue_count": b.compliance_issue_count,
            "risk_score": b.risk_score,
            "created_at": b.created_at.isoformat(),
        }
        for b in budgets
    ]


@router.get("/budgets/{budget_id}")
def get_budget(
    budget_id: uuid_module.UUID,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Get a budget with all line items."""
    db, tenant_id = ctx
    
    result = db.execute(
        select(PCOSBudgetModel).where(
            PCOSBudgetModel.id == budget_id,
            PCOSBudgetModel.tenant_id == tenant_id,
        )
    )
    budget = result.scalar_one_or_none()
    
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    
    # Get line items
    items_result = db.execute(
        select(PCOSBudgetLineItemModel)
        .where(PCOSBudgetLineItemModel.budget_id == budget_id)
        .order_by(PCOSBudgetLineItemModel.row_number)
    )
    line_items = items_result.scalars().all()
    
    # Group by department
    departments = {}
    for item in line_items:
        dept = item.department or "Uncategorized"
        if dept not in departments:
            departments[dept] = {"name": dept, "lineItems": [], "subtotal": 0}
        departments[dept]["lineItems"].append({
            "id": str(item.id),
            "costCode": item.cost_code,
            "description": item.description,
            "rate": float(item.rate) if item.rate else 0,
            "quantity": float(item.quantity) if item.quantity else 1,
            "extension": float(item.extension),
            "classification": item.classification,
            "roleCategory": item.role_category,
            "dealMemoStatus": item.deal_memo_status,
            "complianceFlags": item.compliance_flags or [],
        })
        departments[dept]["subtotal"] += float(item.extension)
    
    return {
        "id": str(budget.id),
        "project_id": str(budget.project_id),
        "source_file_name": budget.source_file_name,
        "grand_total": float(budget.grand_total),
        "subtotal": float(budget.subtotal),
        "contingency_amount": float(budget.contingency_amount) if budget.contingency_amount else 0,
        "contingency_percent": float(budget.contingency_percent) if budget.contingency_percent else 0,
        "detected_location": budget.detected_location,
        "is_active": budget.is_active,
        "compliance_issue_count": budget.compliance_issue_count,
        "critical_issue_count": budget.critical_issue_count,
        "risk_score": budget.risk_score,
        "departments": list(departments.values()),
        "created_at": budget.created_at.isoformat(),
    }


@router.post("/budgets/{budget_id}/validate-rates")
def validate_budget_rates(
    budget_id: uuid_module.UUID,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """
    Run union rate validation on all line items in a budget.
    Returns compliance results with provenance.
    """
    from .union_rate_checker import UnionRateChecker
    
    db, tenant_id = ctx
    
    # Get budget
    result = db.execute(
        select(PCOSBudgetModel).where(
            PCOSBudgetModel.id == budget_id,
            PCOSBudgetModel.tenant_id == tenant_id,
        )
    )
    budget = result.scalar_one_or_none()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    
    # Get line items
    items_result = db.execute(
        select(PCOSBudgetLineItemModel)
        .where(PCOSBudgetLineItemModel.budget_id == budget_id)
    )
    line_items = items_result.scalars().all()
    
    # Initialize checker
    checker = UnionRateChecker()
    
    results = []
    non_compliant_count = 0
    total_shortfall = 0
    
    for item in line_items:
        if not item.rate or item.rate <= 0:
            continue
        
        # Check rate
        check = checker.check_rate(
            role_category=item.role_category or item.description,
            actual_rate=float(item.rate),
            budget_total=float(budget.grand_total)
        )
        
        # Store result in DB
        rate_check = PCOSUnionRateCheckModel(
            tenant_id=tenant_id,
            line_item_id=item.id,
            union_code=check.union_code,
            role_category=check.role_category,
            minimum_rate=check.minimum_rate,
            actual_rate=check.actual_rate,
            is_compliant=check.is_compliant,
            shortfall_amount=check.shortfall_amount,
            fringe_percent_required=check.fringe_percent_required,
            fringe_amount_required=check.fringe_amount_required,
            rate_table_version=check.rate_table_version,
            rate_table_effective_date=check.rate_table_effective_date,
            notes=check.notes,
        )
        db.add(rate_check)
        
        if not check.is_compliant:
            non_compliant_count += 1
            total_shortfall += float(check.shortfall_amount)
        
        results.append({
            "line_item_id": str(item.id),
            "description": item.description,
            **check.to_dict()
        })
    
    db.commit()
    
    logger.info(
        "budget_rates_validated",
        budget_id=str(budget_id),
        total_checked=len(results),
        non_compliant=non_compliant_count,
        total_shortfall=total_shortfall,
    )
    
    return {
        "budget_id": str(budget_id),
        "rate_table_version": checker.version,
        "rate_table_effective_date": checker.effective_date.isoformat() if checker.effective_date else None,
        "total_checked": len(results),
        "compliant_count": len(results) - non_compliant_count,
        "non_compliant_count": non_compliant_count,
        "total_shortfall": total_shortfall,
        "results": results,
    }


@router.get("/budgets/{budget_id}/rate-checks")
def get_budget_rate_checks(
    budget_id: uuid_module.UUID,
    non_compliant_only: bool = Query(False, description="Only return non-compliant results"),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Get stored rate check results for a budget."""
    db, tenant_id = ctx
    
    # Get all rate checks for budget line items
    query = (
        select(PCOSUnionRateCheckModel, PCOSBudgetLineItemModel.description)
        .join(PCOSBudgetLineItemModel)
        .where(PCOSBudgetLineItemModel.budget_id == budget_id)
        .where(PCOSUnionRateCheckModel.tenant_id == tenant_id)
    )
    
    if non_compliant_only:
        query = query.where(PCOSUnionRateCheckModel.is_compliant == False)
    
    result = db.execute(query)
    rows = result.all()
    
    return [
        {
            "id": str(check.id),
            "line_item_id": str(check.line_item_id),
            "description": description,
            "union_code": check.union_code,
            "role_category": check.role_category,
            "minimum_rate": float(check.minimum_rate),
            "actual_rate": float(check.actual_rate),
            "is_compliant": check.is_compliant,
            "shortfall_amount": float(check.shortfall_amount) if check.shortfall_amount else 0,
            "fringe_percent_required": float(check.fringe_percent_required) if check.fringe_percent_required else None,
            "rate_table_version": check.rate_table_version,
            "notes": check.notes,
        }
        for check, description in rows
    ]


# =============================================================================
# TAX CREDIT ANALYSIS ENDPOINTS
# =============================================================================

@router.get("/projects/{project_id}/tax-credits")
def get_project_tax_credits(
    project_id: uuid_module.UUID,
    budget_id: Optional[uuid_module.UUID] = Query(None, description="Specific budget to analyze"),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """
    Analyze a project's budget for tax credit eligibility.
    
    Returns CA Film Tax Credit 4.0 eligibility status and estimated credit.
    """
    from .tax_credit_engine import analyze_budget_for_tax_credit
    
    db, tenant_id = ctx
    
    # Get the budget to analyze
    if budget_id:
        budget = db.execute(
            select(PCOSBudgetModel)
            .where(PCOSBudgetModel.id == budget_id)
            .where(PCOSBudgetModel.project_id == project_id)
            .where(PCOSBudgetModel.tenant_id == tenant_id)
        ).scalar_one_or_none()
    else:
        # Get the active budget
        budget = db.execute(
            select(PCOSBudgetModel)
            .where(PCOSBudgetModel.project_id == project_id)
            .where(PCOSBudgetModel.tenant_id == tenant_id)
            .where(PCOSBudgetModel.is_active == True)
        ).scalar_one_or_none()
    
    if not budget:
        raise HTTPException(404, "No budget found for this project")
    
    # Get project info for eligibility checks
    project = db.execute(
        select(PCOSProjectModel)
        .where(PCOSProjectModel.id == project_id)
        .where(PCOSProjectModel.tenant_id == tenant_id)
    ).scalar_one_or_none()
    
    if not project:
        raise HTTPException(404, "Project not found")
    
    # Get line items
    line_items = db.execute(
        select(PCOSBudgetLineItemModel)
        .where(PCOSBudgetLineItemModel.budget_id == budget.id)
        .where(PCOSBudgetLineItemModel.tenant_id == tenant_id)
    ).scalars().all()
    
    # Build project info dict
    project_info = {
        "is_ca_registered": True,  # Default assumption
        "ca_filming_days_pct": 100,  # Default to 100% if not specified
        "is_independent": budget.grand_total < 3000000,  # Heuristic for indie
        "is_relocating": False,  # Would need explicit flag
        "ca_jobs_ratio": 0.85,  # Default assumption
    }
    
    # If location is detected, use it
    if budget.detected_location:
        is_ca = budget.detected_location.upper() in ("CA", "CALIFORNIA")
        project_info["ca_filming_days_pct"] = 100 if is_ca else 0
    
    # Prepare line items for analysis
    items_for_analysis = [
        {
            "id": str(item.id),
            "department": item.department or "99",
            "description": item.description,
            "role": item.description,
            "total_cost": float(item.total_cost) if item.total_cost else 0,
        }
        for item in line_items
    ]
    
    # Run analysis
    analysis_result = analyze_budget_for_tax_credit(
        float(budget.grand_total),
        items_for_analysis,
        project_info
    )
    
    # Check for existing application record
    existing_app = db.execute(
        select(PCOSTaxCreditApplicationModel)
        .where(PCOSTaxCreditApplicationModel.project_id == project_id)
        .where(PCOSTaxCreditApplicationModel.budget_id == budget.id)
        .where(PCOSTaxCreditApplicationModel.program_code == "CA_FTC_4.0")
        .where(PCOSTaxCreditApplicationModel.tenant_id == tenant_id)
    ).scalar_one_or_none()
    
    # Create or update application record
    if not existing_app:
        existing_app = PCOSTaxCreditApplicationModel(
            tenant_id=tenant_id,
            project_id=project_id,
            budget_id=budget.id,
            program_code=analysis_result["program_code"],
            program_name=analysis_result["program_name"],
            program_year=analysis_result["program_year"],
        )
        db.add(existing_app)
    
    # Update with latest analysis
    existing_app.eligibility_status = "eligible" if analysis_result["eligibility"]["is_eligible"] else "ineligible"
    existing_app.eligibility_score = analysis_result["eligibility"]["score"]
    existing_app.requirements_met = analysis_result["eligibility"]["requirements_met"]
    existing_app.rule_pack_version = analysis_result["rule_pack_version"]
    existing_app.evaluated_at = datetime.utcnow()
    existing_app.evaluation_details = analysis_result
    
    if "credit_calculation" in analysis_result:
        calc = analysis_result["credit_calculation"]
        existing_app.base_credit_rate = calc["base_rate"]
        existing_app.uplift_rate = calc["uplift_rate"]
        existing_app.total_credit_rate = calc["total_rate"]
        existing_app.actual_qualified_spend = calc["qualified_spend"]
        existing_app.estimated_credit_amount = calc["estimated_credit"]
        existing_app.qualified_spend_pct = (
            calc["qualified_spend"] / (calc["qualified_spend"] + calc["non_qualified_spend"]) * 100
            if (calc["qualified_spend"] + calc["non_qualified_spend"]) > 0
            else 0
        )
        
        # Clear and recreate spend categories
        db.execute(
            delete(PCOSQualifiedSpendCategoryModel)
            .where(PCOSQualifiedSpendCategoryModel.application_id == existing_app.id)
        )
        
        for cat in calc["spend_categories"]:
            spend_cat = PCOSQualifiedSpendCategoryModel(
                tenant_id=tenant_id,
                application_id=existing_app.id,
                category_code=cat["code"],
                category_name=cat["name"],
                total_spend=cat["total"],
                qualified_spend=cat["qualified"],
                non_qualified_spend=cat["non_qualified"],
                qualification_status=cat["status"],
                qualification_reason=cat["reason"],
                line_item_count=cat["line_item_count"],
            )
            db.add(spend_cat)
    
    db.commit()
    
    # Return the analysis with application ID
    analysis_result["application_id"] = str(existing_app.id)
    analysis_result["budget_id"] = str(budget.id)
    analysis_result["project_id"] = str(project_id)
    analysis_result["budget_total"] = float(budget.grand_total)
    
    return analysis_result


# =============================================================================
# FORM AUTO-FILL ENDPOINTS
# =============================================================================

@router.get("/projects/{project_id}/forms/filmla")
def get_filmla_permit_form(
    project_id: uuid_module.UUID,
    location_id: Optional[uuid_module.UUID] = Query(None, description="Specific location for permit"),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """
    Generate pre-filled FilmLA permit application data.
    
    Returns form field values extracted from project, company, location, and insurance data.
    This data can be used to fill a PDF form client-side using pdf-lib.
    """
    from .filmla_form_generator import generate_filmla_form
    
    db, tenant_id = ctx
    
    # Get project
    project = db.execute(
        select(PCOSProjectModel)
        .where(PCOSProjectModel.id == project_id)
        .where(PCOSProjectModel.tenant_id == tenant_id)
    ).scalar_one_or_none()
    
    if not project:
        raise HTTPException(404, "Project not found")
    
    # Get company
    from .pcos_models import PCOSCompanyModel, PCOSInsurancePolicyModel
    
    company = db.execute(
        select(PCOSCompanyModel)
        .where(PCOSCompanyModel.id == project.company_id)
        .where(PCOSCompanyModel.tenant_id == tenant_id)
    ).scalar_one_or_none()
    
    if not company:
        raise HTTPException(404, "Company not found for project")
    
    # Get location (either specified or first location)
    if location_id:
        location = db.execute(
            select(PCOSLocationModel)
            .where(PCOSLocationModel.id == location_id)
            .where(PCOSLocationModel.project_id == project_id)
            .where(PCOSLocationModel.tenant_id == tenant_id)
        ).scalar_one_or_none()
    else:
        location = db.execute(
            select(PCOSLocationModel)
            .where(PCOSLocationModel.project_id == project_id)
            .where(PCOSLocationModel.tenant_id == tenant_id)
            .limit(1)
        ).scalar_one_or_none()
    
    if not location:
        raise HTTPException(404, "No location found for project. Add a location first.")
    
    # Get insurance policy (if any)
    insurance = db.execute(
        select(PCOSInsurancePolicyModel)
        .where(PCOSInsurancePolicyModel.company_id == company.id)
        .where(PCOSInsurancePolicyModel.tenant_id == tenant_id)
        .where(PCOSInsurancePolicyModel.status == "active")
        .limit(1)
    ).scalar_one_or_none()
    
    # Build data dicts
    project_data = {
        "name": project.name,
        "code": project.code,
        "project_type": project.project_type,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "end_date": project.end_date.isoformat() if project.end_date else None,
    }
    
    company_data = {
        "name": company.name,
        "primary_contact_name": company.primary_contact_name,
        "primary_contact_phone": company.primary_contact_phone,
        "primary_contact_email": company.primary_contact_email,
        "address_line1": company.address_line1,
        "city": company.city,
        "state": company.state,
        "zip": company.zip,
    }
    
    location_data = {
        "name": location.name,
        "address_line1": location.address_line1,
        "city": location.city,
        "state": location.state,
        "zip": location.zip,
        "estimated_crew_size": location.estimated_crew_size,
        "parking_spaces_needed": location.parking_spaces_needed,
        "has_generator": location.has_generator,
        "has_special_effects": location.has_special_effects,
        "shoot_dates": [d.isoformat() for d in (location.shoot_dates or [])],
    }
    
    insurance_data = None
    if insurance:
        insurance_data = {
            "carrier_name": insurance.carrier_name,
            "policy_number": insurance.policy_number,
            "expiration_date": insurance.expiration_date.isoformat() if insurance.expiration_date else None,
        }
    
    # Generate form data
    form_result = generate_filmla_form(
        project_data,
        company_data,
        location_data,
        insurance_data
    )
    
    # Store generated form record
    template = db.execute(
        select(PCOSFormTemplateModel)
        .where(PCOSFormTemplateModel.template_code == "FILMLA_PERMIT")
        .where(PCOSFormTemplateModel.is_active == True)
    ).scalar_one_or_none()
    
    if template:
        # Create or update generated form
        existing = db.execute(
            select(PCOSGeneratedFormModel)
            .where(PCOSGeneratedFormModel.project_id == project_id)
            .where(PCOSGeneratedFormModel.location_id == location.id)
            .where(PCOSGeneratedFormModel.template_id == template.id)
            .where(PCOSGeneratedFormModel.tenant_id == tenant_id)
        ).scalar_one_or_none()
        
        if not existing:
            existing = PCOSGeneratedFormModel(
                tenant_id=tenant_id,
                project_id=project_id,
                template_id=template.id,
                location_id=location.id,
                requires_signature=template.requires_signature,
            )
            db.add(existing)
        
        existing.source_data_snapshot = form_result["source_data_snapshot"]
        existing.status = "ready" if form_result["is_complete"] else "draft"
        db.commit()
        
        form_result["generated_form_id"] = str(existing.id)
    
    form_result["project_id"] = str(project_id)
    form_result["location_id"] = str(location.id)
    
    return form_result


# =============================================================================
# WORKER CLASSIFICATION ENDPOINTS
# =============================================================================

@router.post("/engagements/{engagement_id}/classify")
def classify_engagement(
    engagement_id: uuid_module.UUID,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """
    Analyze an engagement for worker classification using CA AB5 ABC Test.
    
    Returns detailed analysis with risk assessment and recommended action.
    """
    from .abc_test_evaluator import analyze_engagement_classification
    
    db, tenant_id = ctx
    
    # Get engagement
    engagement = db.execute(
        select(PCOSEngagementModel)
        .where(PCOSEngagementModel.id == engagement_id)
        .where(PCOSEngagementModel.tenant_id == tenant_id)
    ).scalar_one_or_none()
    
    if not engagement:
        raise HTTPException(404, "Engagement not found")
    
    # Get person
    person = db.execute(
        select(PCOSPersonModel)
        .where(PCOSPersonModel.id == engagement.person_id)
        .where(PCOSPersonModel.tenant_id == tenant_id)
    ).scalar_one_or_none()
    
    # Get project and company
    project = db.execute(
        select(PCOSProjectModel)
        .where(PCOSProjectModel.id == engagement.project_id)
        .where(PCOSProjectModel.tenant_id == tenant_id)
    ).scalar_one_or_none()
    
    from .pcos_models import PCOSCompanyModel
    company = None
    if project:
        company = db.execute(
            select(PCOSCompanyModel)
            .where(PCOSCompanyModel.id == project.company_id)
            .where(PCOSCompanyModel.tenant_id == tenant_id)
        ).scalar_one_or_none()
    
    # Get exemptions
    exemptions = db.execute(
        select(PCOSClassificationExemptionModel)
        .where(PCOSClassificationExemptionModel.is_active == True)
    ).scalars().all()
    
    exemptions_list = [
        {
            "exemption_code": e.exemption_code,
            "exemption_name": e.exemption_name,
            "exemption_category": e.exemption_category,
            "qualifying_criteria": e.qualifying_criteria,
            "description": e.description
        }
        for e in exemptions
    ]
    
    # Build engagement data
    engagement_data = {
        "role_title": engagement.role_title,
        "department": engagement.department,
        "classification": engagement.classification,
        "pay_rate": float(engagement.pay_rate) if engagement.pay_rate else None,
        "pay_type": engagement.pay_type,
        "sets_own_methods": engagement.classification == "contractor",
        "sets_own_schedule": engagement.pay_type != "hourly",
        "supervision_level": "minimal" if engagement.classification == "contractor" else "medium",
        "training_provided": engagement.classification == "employee",
    }
    
    # Build person data
    person_data = {}
    if person:
        person_data = {
            "has_business_entity": person.preferred_classification == "contractor",
            "other_client_count": 0,  # Would need to track this
            "owns_equipment": False,  # Would need metadata
            "advertises_services": False,
        }
    
    # Build company data
    company_data = {}
    if company:
        company_data = {
            "name": company.name,
            "business_type": "production"
        }
    
    # Run analysis
    result = analyze_engagement_classification(
        engagement_data,
        person_data,
        company_data,
        questionnaire_responses=None,
        exemptions=exemptions_list
    )
    
    # Store analysis
    analysis = PCOSClassificationAnalysisModel(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        rule_version=result["rule_version"],
        prong_a_passed=result["prong_a"]["passed"],
        prong_a_score=result["prong_a"]["score"],
        prong_a_factors=result["prong_a"]["factors"],
        prong_a_reasoning=result["prong_a"]["reasoning"],
        prong_b_passed=result["prong_b"]["passed"],
        prong_b_score=result["prong_b"]["score"],
        prong_b_factors=result["prong_b"]["factors"],
        prong_b_reasoning=result["prong_b"]["reasoning"],
        prong_c_passed=result["prong_c"]["passed"],
        prong_c_score=result["prong_c"]["score"],
        prong_c_factors=result["prong_c"]["factors"],
        prong_c_reasoning=result["prong_c"]["reasoning"],
        overall_result=result["overall_result"],
        overall_score=result["overall_score"],
        confidence_level=result["confidence"],
        risk_level=result["risk_level"],
        risk_factors=result["risk_factors"],
        recommended_action=result["recommended_action"],
        exemption_applicable=result.get("exemption", {}).get("is_applicable", False) if result.get("exemption") else False,
        exemption_type=result.get("exemption", {}).get("type") if result.get("exemption") else None,
    )
    db.add(analysis)
    db.commit()
    
    result["analysis_id"] = str(analysis.id)
    result["engagement_id"] = str(engagement_id)
    
    return result


@router.get("/engagements/{engagement_id}/classification")
def get_engagement_classification(
    engagement_id: uuid_module.UUID,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Get the most recent classification analysis for an engagement."""
    db, tenant_id = ctx
    
    analysis = db.execute(
        select(PCOSClassificationAnalysisModel)
        .where(PCOSClassificationAnalysisModel.engagement_id == engagement_id)
        .where(PCOSClassificationAnalysisModel.tenant_id == tenant_id)
        .order_by(PCOSClassificationAnalysisModel.analyzed_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    
    if not analysis:
        raise HTTPException(404, "No classification analysis found")
    
    return {
        "analysis_id": str(analysis.id),
        "engagement_id": str(engagement_id),
        "overall_result": analysis.overall_result,
        "overall_score": analysis.overall_score,
        "confidence": analysis.confidence_level,
        "risk_level": analysis.risk_level,
        "risk_factors": analysis.risk_factors,
        "recommended_action": analysis.recommended_action,
        "analyzed_at": analysis.analyzed_at.isoformat(),
        "prong_a": {
            "passed": analysis.prong_a_passed,
            "score": analysis.prong_a_score,
            "reasoning": analysis.prong_a_reasoning
        },
        "prong_b": {
            "passed": analysis.prong_b_passed,
            "score": analysis.prong_b_score,
            "reasoning": analysis.prong_b_reasoning
        },
        "prong_c": {
            "passed": analysis.prong_c_passed,
            "score": analysis.prong_c_score,
            "reasoning": analysis.prong_c_reasoning
        },
        "exemption_applicable": analysis.exemption_applicable,
        "exemption_type": analysis.exemption_type
    }


# =============================================================================
# FRINGE & PAYROLL TAX ENDPOINTS
# =============================================================================

@router.get("/budgets/{budget_id}/fringe-analysis")
def analyze_budget_fringes(
    budget_id: uuid_module.UUID,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """
    Analyze fringe and payroll tax requirements for a budget.
    
    Returns breakdown by line item with shortfall detection.
    """
    from .fringe_calculator import calculate_budget_fringes
    
    db, tenant_id = ctx
    
    # Get budget
    budget = db.execute(
        select(PCOSBudgetModel)
        .where(PCOSBudgetModel.id == budget_id)
        .where(PCOSBudgetModel.tenant_id == tenant_id)
    ).scalar_one_or_none()
    
    if not budget:
        raise HTTPException(404, "Budget not found")
    
    # Get line items
    line_items = db.execute(
        select(PCOSBudgetLineItemModel)
        .where(PCOSBudgetLineItemModel.budget_id == budget_id)
        .where(PCOSBudgetLineItemModel.tenant_id == tenant_id)
    ).scalars().all()
    
    # Convert to dicts
    items_for_analysis = [
        {
            "id": str(item.id),
            "department": item.department or "99",
            "description": item.description,
            "total_cost": float(item.total_cost) if item.total_cost else 0,
        }
        for item in line_items
    ]
    
    # Detect budgeted fringes from department 80/81
    budgeted_fringes = sum(
        float(item.total_cost or 0)
        for item in line_items
        if str(item.department or "").startswith("8")
    )
    
    # Run analysis
    result = calculate_budget_fringes(items_for_analysis, budgeted_fringes)
    
    result["budget_id"] = str(budget_id)
    result["budget_total"] = float(budget.grand_total)
    result["budgeted_fringes_detected"] = budgeted_fringes
    
    return result


# =============================================================================
# PAPERWORK TRACKING ENDPOINTS
# =============================================================================

@router.get("/projects/{project_id}/paperwork-status")
def get_project_paperwork_status(
    project_id: uuid_module.UUID,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """
    Get paperwork completion status for all engagements in a project.
    
    Returns document checklist with completion percentage.
    """
    db, tenant_id = ctx
    
    # Get all engagements for project
    engagements = db.execute(
        select(PCOSEngagementModel)
        .where(PCOSEngagementModel.project_id == project_id)
        .where(PCOSEngagementModel.tenant_id == tenant_id)
    ).scalars().all()
    
    if not engagements:
        return {
            "project_id": str(project_id),
            "engagements": [],
            "overall_completion_pct": 0,
            "total_pending": 0,
            "total_received": 0
        }
    
    # Get all requirements
    requirements = db.execute(
        select(PCOSDocumentRequirementModel)
        .where(PCOSDocumentRequirementModel.is_active == True)
    ).scalars().all()
    
    engagement_statuses = []
    total_docs = 0
    total_received = 0
    total_pending = 0
    
    for eng in engagements:
        # Get person for minor/visa checks
        person = db.execute(
            select(PCOSPersonModel)
            .where(PCOSPersonModel.id == eng.person_id)
            .where(PCOSPersonModel.tenant_id == tenant_id)
        ).scalar_one_or_none()
        
        # Check visa status
        visa_status = None
        if person:
            visa_status = db.execute(
                select(PCOSPersonVisaStatusModel)
                .where(PCOSPersonVisaStatusModel.person_id == person.id)
                .where(PCOSPersonVisaStatusModel.tenant_id == tenant_id)
                .limit(1)
            ).scalar_one_or_none()
        
        is_minor = person.date_of_birth is not None if person else False  # Would check age
        has_visa = visa_status is not None
        
        # Get applicable requirements
        applicable_reqs = []
        for req in requirements:
            # Check classification match
            if req.applies_to_classification not in (None, "both", eng.classification):
                continue
            # Check minor requirement
            if req.applies_to_minor and not is_minor:
                continue
            # Check visa requirement
            if req.applies_to_visa_holder and not has_visa:
                continue
            applicable_reqs.append(req)
        
        # Get existing document records
        existing_docs = db.execute(
            select(PCOSEngagementDocumentModel)
            .where(PCOSEngagementDocumentModel.engagement_id == eng.id)
            .where(PCOSEngagementDocumentModel.tenant_id == tenant_id)
        ).scalars().all()
        
        doc_map = {str(d.requirement_id): d for d in existing_docs}
        
        docs = []
        eng_received = 0
        eng_pending = 0
        
        for req in applicable_reqs:
            doc = doc_map.get(str(req.id))
            status = doc.status if doc else "pending"
            
            if status in ("received", "verified"):
                eng_received += 1
            else:
                eng_pending += 1
            
            docs.append({
                "requirement_code": req.requirement_code,
                "requirement_name": req.requirement_name,
                "document_type": req.document_type,
                "is_required": req.is_required,
                "status": status,
                "received_at": doc.received_at.isoformat() if doc and doc.received_at else None,
            })
        
        total = eng_received + eng_pending
        completion_pct = (eng_received / total * 100) if total > 0 else 0
        
        engagement_statuses.append({
            "engagement_id": str(eng.id),
            "person_name": f"{person.first_name} {person.last_name}" if person else "Unknown",
            "role_title": eng.role_title,
            "classification": eng.classification,
            "documents": docs,
            "received_count": eng_received,
            "pending_count": eng_pending,
            "completion_pct": round(completion_pct, 1)
        })
        
        total_docs += total
        total_received += eng_received
        total_pending += eng_pending
    
    overall_pct = (total_received / total_docs * 100) if total_docs > 0 else 0
    
    return {
        "project_id": str(project_id),
        "engagements": engagement_statuses,
        "overall_completion_pct": round(overall_pct, 1),
        "total_docs": total_docs,
        "total_received": total_received,
        "total_pending": total_pending
    }


@router.get("/people/{person_id}/visa-timeline")
def get_person_visa_timeline(
    person_id: uuid_module.UUID,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """
    Get visa status and timeline warnings for a person.
    
    Returns expiration warnings and work authorization status.
    """
    db, tenant_id = ctx
    
    # Get person
    person = db.execute(
        select(PCOSPersonModel)
        .where(PCOSPersonModel.id == person_id)
        .where(PCOSPersonModel.tenant_id == tenant_id)
    ).scalar_one_or_none()
    
    if not person:
        raise HTTPException(404, "Person not found")
    
    # Get visa status
    visa_status = db.execute(
        select(PCOSPersonVisaStatusModel)
        .where(PCOSPersonVisaStatusModel.person_id == person_id)
        .where(PCOSPersonVisaStatusModel.tenant_id == tenant_id)
        .order_by(PCOSPersonVisaStatusModel.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    
    if not visa_status:
        return {
            "person_id": str(person_id),
            "person_name": f"{person.first_name} {person.last_name}",
            "has_visa_record": False,
            "is_us_citizen_assumed": True,
            "warnings": []
        }
    
    # Get visa category details
    visa_category = None
    if visa_status.visa_category_id:
        visa_category = db.execute(
            select(PCOSVisaCategoryModel)
            .where(PCOSVisaCategoryModel.id == visa_status.visa_category_id)
        ).scalar_one_or_none()
    
    # Check for warnings
    warnings = []
    today = date.today()
    
    if visa_status.expiration_date:
        days_until_expiry = (visa_status.expiration_date - today).days
        
        if days_until_expiry < 0:
            warnings.append({
                "type": "critical",
                "message": f"Visa expired {abs(days_until_expiry)} days ago",
                "action": "Cannot work legally; engagement must be terminated"
            })
        elif days_until_expiry <= 30:
            warnings.append({
                "type": "high",
                "message": f"Visa expires in {days_until_expiry} days",
                "action": "Initiate renewal immediately"
            })
        elif days_until_expiry <= 90:
            warnings.append({
                "type": "medium",
                "message": f"Visa expires in {days_until_expiry} days",
                "action": "Begin renewal planning"
            })
    
    if visa_status.i94_expiration:
        i94_days = (visa_status.i94_expiration - today).days
        if i94_days < 0:
            warnings.append({
                "type": "critical",
                "message": "I-94 expired - unlawful presence accruing",
                "action": "Consult immigration attorney immediately"
            })
        elif i94_days <= 30:
            warnings.append({
                "type": "high",
                "message": f"I-94 expires in {i94_days} days",
                "action": "Plan departure or extension before expiry"
            })
    
    if visa_status.ead_expiration:
        ead_days = (visa_status.ead_expiration - today).days
        if ead_days < 0:
            warnings.append({
                "type": "critical",
                "message": "EAD expired - work authorization invalid",
                "action": "Cannot work until EAD renewed"
            })
        elif ead_days <= 90:
            warnings.append({
                "type": "medium",
                "message": f"EAD expires in {ead_days} days",
                "action": "File renewal application"
            })
    
    if visa_status.employer_restricted and visa_category and visa_category.employer_specific:
        warnings.append({
            "type": "info",
            "message": "Visa is employer-specific",
            "action": f"Worker authorized only for: {visa_status.restricted_to_employer or 'Current employer'}"
        })
    
    return {
        "person_id": str(person_id),
        "person_name": f"{person.first_name} {person.last_name}",
        "has_visa_record": True,
        "visa_code": visa_status.visa_code,
        "visa_name": visa_category.visa_name if visa_category else visa_status.visa_code,
        "status": visa_status.status,
        "is_work_authorized": visa_status.is_work_authorized,
        "expiration_date": visa_status.expiration_date.isoformat() if visa_status.expiration_date else None,
        "i94_expiration": visa_status.i94_expiration.isoformat() if visa_status.i94_expiration else None,
        "ead_expiration": visa_status.ead_expiration.isoformat() if visa_status.ead_expiration else None,
        "employer_restricted": visa_status.employer_restricted,
        "warnings": warnings,
        "warning_count": len(warnings),
        "has_critical_warning": any(w["type"] == "critical" for w in warnings)
    }


# =============================================================================
# COMPLIANCE SNAPSHOT ENDPOINTS
# =============================================================================

@router.post("/projects/{project_id}/compliance-snapshots")
def create_compliance_snapshot(
    project_id: uuid_module.UUID,
    snapshot_type: str = Query("manual", description="Snapshot type: manual, pre_greenlight, scheduled"),
    snapshot_name: Optional[str] = Query(None, description="Optional name for the snapshot"),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """
    Create a point-in-time compliance snapshot for a project.
    
    Runs all applicable rule evaluations and stores aggregate results.
    """
    from .compliance_snapshot_service import ComplianceSnapshotService
    
    db, tenant_id = ctx
    
    service = ComplianceSnapshotService(db, tenant_id)
    snapshot = service.create_snapshot(
        project_id=project_id,
        snapshot_type=snapshot_type,
        snapshot_name=snapshot_name,
        trigger_reason="Manual snapshot via API"
    )
    
    return snapshot


@router.get("/projects/{project_id}/compliance-snapshots")
def list_compliance_snapshots(
    project_id: uuid_module.UUID,
    limit: int = Query(10, le=50),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """List compliance snapshots for a project."""
    db, tenant_id = ctx
    
    snapshots = db.execute(
        select(PCOSComplianceSnapshotModel)
        .where(PCOSComplianceSnapshotModel.project_id == project_id)
        .where(PCOSComplianceSnapshotModel.tenant_id == tenant_id)
        .order_by(PCOSComplianceSnapshotModel.created_at.desc())
        .limit(limit)
    ).scalars().all()
    
    return [
        {
            "id": str(s.id),
            "snapshot_type": s.snapshot_type,
            "snapshot_name": s.snapshot_name,
            "compliance_status": s.compliance_status,
            "overall_score": s.overall_score,
            "rules_evaluated": s.total_rules_evaluated,
            "passed": s.rules_passed,
            "failed": s.rules_failed,
            "warnings": s.rules_warning,
            "is_attested": s.is_attested,
            "created_at": s.created_at.isoformat()
        }
        for s in snapshots
    ]


@router.get("/compliance-snapshots/{snapshot_id}")
def get_compliance_snapshot(
    snapshot_id: uuid_module.UUID,
    include_evaluations: bool = Query(False),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Get a compliance snapshot with optional rule evaluations."""
    db, tenant_id = ctx
    
    snapshot = db.execute(
        select(PCOSComplianceSnapshotModel)
        .where(PCOSComplianceSnapshotModel.id == snapshot_id)
        .where(PCOSComplianceSnapshotModel.tenant_id == tenant_id)
    ).scalar_one_or_none()
    
    if not snapshot:
        raise HTTPException(404, "Snapshot not found")
    
    result = {
        "id": str(snapshot.id),
        "project_id": str(snapshot.project_id),
        "snapshot_type": snapshot.snapshot_type,
        "snapshot_name": snapshot.snapshot_name,
        "compliance_status": snapshot.compliance_status,
        "overall_score": snapshot.overall_score,
        "total_rules_evaluated": snapshot.total_rules_evaluated,
        "rules_passed": snapshot.rules_passed,
        "rules_failed": snapshot.rules_failed,
        "rules_warning": snapshot.rules_warning,
        "category_scores": snapshot.category_scores,
        "delta_summary": snapshot.delta_summary,
        "project_state": snapshot.project_state,
        "is_attested": snapshot.is_attested,
        "attested_at": snapshot.attested_at.isoformat() if snapshot.attested_at else None,
        "created_at": snapshot.created_at.isoformat()
    }
    
    if include_evaluations:
        evaluations = db.execute(
            select(PCOSRuleEvaluationModel)
            .where(PCOSRuleEvaluationModel.snapshot_id == snapshot_id)
            .order_by(PCOSRuleEvaluationModel.rule_category)
        ).scalars().all()
        
        result["evaluations"] = [
            {
                "id": str(e.id),
                "rule_code": e.rule_code,
                "rule_name": e.rule_name,
                "rule_category": e.rule_category,
                "entity_type": e.entity_type,
                "result": e.result,
                "severity": e.severity,
                "message": e.message,
                "source_authorities": e.source_authorities
            }
            for e in evaluations
        ]
    
    return result


@router.get("/compliance-snapshots/{snapshot_id_1}/compare/{snapshot_id_2}")
def compare_snapshots(
    snapshot_id_1: uuid_module.UUID,
    snapshot_id_2: uuid_module.UUID,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Compare two compliance snapshots."""
    from .compliance_snapshot_service import ComplianceSnapshotService
    
    db, tenant_id = ctx
    
    service = ComplianceSnapshotService(db, tenant_id)
    comparison = service.compare_snapshots(snapshot_id_1, snapshot_id_2)
    
    return comparison


# =============================================================================
# AUDIT PACK ENDPOINTS
# =============================================================================

@router.get("/projects/{project_id}/audit-pack")
def get_audit_pack(
    project_id: uuid_module.UUID,
    snapshot_id: Optional[uuid_module.UUID] = Query(None),
    include_evidence: bool = Query(True),
    include_budget: bool = Query(True),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """
    Generate a comprehensive audit pack for a project.
    
    Returns structured data suitable for PDF generation including:
    - Project summary
    - Compliance metrics and rule evaluations
    - Budget analysis
    - Evidence inventory
    """
    from .audit_pack_service import AuditPackService
    
    db, tenant_id = ctx
    
    service = AuditPackService(db, tenant_id)
    pack = service.generate_audit_pack(
        project_id=project_id,
        snapshot_id=snapshot_id,
        include_evidence_list=include_evidence,
        include_budget_summary=include_budget
    )
    
    return pack


@router.post("/compliance-snapshots/{snapshot_id}/attest")
def attest_snapshot(
    snapshot_id: uuid_module.UUID,
    attestation_notes: Optional[str] = Query(None, description="Notes for attestation"),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """
    Attest to a compliance snapshot's accuracy.
    
    Records that a user has reviewed and attests to the compliance state.
    In production, this would integrate with e-sign (DocuSign/Dropbox Sign).
    """
    db, tenant_id = ctx
    
    snapshot = db.execute(
        select(PCOSComplianceSnapshotModel)
        .where(PCOSComplianceSnapshotModel.id == snapshot_id)
        .where(PCOSComplianceSnapshotModel.tenant_id == tenant_id)
    ).scalar_one_or_none()
    
    if not snapshot:
        raise HTTPException(404, "Snapshot not found")
    
    if snapshot.is_attested:
        raise HTTPException(400, "Snapshot already attested")
    
    # Update attestation
    snapshot.is_attested = True
    snapshot.attested_at = datetime.now(timezone.utc)
    snapshot.attestation_notes = attestation_notes
    # In production: snapshot.attestation_signature_id = docusign_envelope_id
    
    # Log audit event
    audit_event = PCOSAuditEventModel(
        tenant_id=tenant_id,
        project_id=snapshot.project_id,
        event_type="attestation",
        event_action="created",
        entity_type="compliance_snapshot",
        entity_id=snapshot.id,
        event_data={
            "snapshot_type": snapshot.snapshot_type,
            "compliance_status": snapshot.compliance_status,
            "overall_score": snapshot.overall_score,
            "attestation_notes": attestation_notes
        }
    )
    db.add(audit_event)
    db.commit()
    
    return {
        "snapshot_id": str(snapshot_id),
        "is_attested": True,
        "attested_at": snapshot.attested_at.isoformat(),
        "message": "Snapshot successfully attested"
    }


@router.get("/projects/{project_id}/audit-events")
def list_audit_events(
    project_id: uuid_module.UUID,
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """List audit events for a project."""
    db, tenant_id = ctx
    
    query = (
        select(PCOSAuditEventModel)
        .where(PCOSAuditEventModel.project_id == project_id)
        .where(PCOSAuditEventModel.tenant_id == tenant_id)
    )
    
    if event_type:
        query = query.where(PCOSAuditEventModel.event_type == event_type)
    
    query = query.order_by(PCOSAuditEventModel.created_at.desc()).limit(limit)
    
    events = db.execute(query).scalars().all()
    
    return [
        {
            "id": str(e.id),
            "event_type": e.event_type,
            "event_action": e.event_action,
            "entity_type": e.entity_type,
            "entity_id": str(e.entity_id) if e.entity_id else None,
            "event_data": e.event_data,
            "created_at": e.created_at.isoformat()
        }
        for e in events
    ]


# =============================================================================
# HEALTH CHECK
# =============================================================================

@router.get("/health")
def pcos_health():
    """PCOS module health check."""
    return {
        "status": "healthy",
        "module": "Production Compliance OS",
        "version": "1.0.0",
    }


# =============================================================================
# AUTHORITY & FACT LINEAGE ENDPOINTS
# =============================================================================

@router.post("/authorities")
def register_authority_document(
    document_code: str,
    document_name: str,
    document_type: str,
    issuer_name: str,
    effective_date: date,
    issuer_type: Optional[str] = None,
    expiration_date: Optional[date] = None,
    file_path: Optional[str] = None,
    extraction_method: str = "manual",
    extraction_notes: Optional[str] = None,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    Register a new authority document (CBA, statute, regulation).
    
    Creates a record for source documents that contain authoritative facts.
    If a file path is provided, the document will be hashed for integrity.
    """
    from .authority_lineage_service import AuthorityLineageService
    from .models import set_tenant_context
    
    tenant_id = UUID(x_tenant_id)
    user_id = UUID(x_user_id) if x_user_id else None
    set_tenant_context(session, tenant_id)
    
    service = AuthorityLineageService(session, tenant_id)
    result = service.register_authority_document(
        document_code=document_code,
        document_name=document_name,
        document_type=document_type,
        issuer_name=issuer_name,
        effective_date=effective_date,
        issuer_type=issuer_type,
        expiration_date=expiration_date,
        file_path=file_path,
        extraction_method=extraction_method,
        extraction_notes=extraction_notes,
        ingested_by=user_id
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result


@router.get("/authorities")
def list_authority_documents(
    document_type: Optional[str] = None,
    issuer: Optional[str] = None,
    status: str = "active",
    include_expired: bool = False,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    List authority documents with optional filtering.
    
    Filter by document type (cba, statute, regulation, municipal_code),
    issuer name, or status (active, superseded, expired).
    """
    from .authority_lineage_service import AuthorityLineageService
    from .models import TenantContext
    
    tenant_id = UUID(x_tenant_id)
    TenantContext.set_tenant_context(session, tenant_id)
    
    service = AuthorityLineageService(session, tenant_id)
    return service.list_authority_documents(
        document_type=document_type,
        issuer=issuer,
        status=status,
        include_expired=include_expired
    )


@router.get("/authorities/{code}/export")
def export_authority_lineage(
    code: str,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """
    Export full audit lineage for an authority document family.
    Returns cryptographic proofs for all facts and history.
    """
    db, tenant_id = ctx
    from .authority_lineage_service import AuthorityLineageService
    
    service = AuthorityLineageService(db, tenant_id)
    result = service.export_authority_history(code)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
        
    return result


@router.post("/authorities/{authority_id}/facts")
def extract_fact_from_authority(
    authority_id: UUID,
    fact_key: str,
    fact_name: str,
    fact_category: str,
    fact_value: str,
    fact_value_type: str,
    validity_conditions: Optional[str] = None,
    fact_unit: Optional[str] = None,
    fact_description: Optional[str] = None,
    source_page: Optional[int] = None,
    source_section: Optional[str] = None,
    source_quote: Optional[str] = None,
    extraction_confidence: Optional[float] = None,
    extraction_method: str = "manual",
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    Extract a fact from an authority document.
    
    Creates a versioned, citable fact linked to the source document.
    If a fact with the same key exists, creates a new version.
    """
    from .authority_lineage_service import AuthorityLineageService
    from .models import TenantContext
    import json
    
    tenant_id = UUID(x_tenant_id)
    user_id = UUID(x_user_id) if x_user_id else None
    TenantContext.set_tenant_context(session, tenant_id)
    
    # Parse validity conditions if provided
    conditions = None
    if validity_conditions:
        try:
            conditions = json.loads(validity_conditions)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON in validity_conditions")
    
    # Convert fact value based on type
    parsed_value = fact_value
    if fact_value_type == "decimal":
        parsed_value = float(fact_value)
    elif fact_value_type == "integer":
        parsed_value = int(fact_value)
    elif fact_value_type == "boolean":
        parsed_value = fact_value.lower() in ("true", "1", "yes")
    elif fact_value_type == "json":
        parsed_value = json.loads(fact_value)
    
    service = AuthorityLineageService(session, tenant_id)
    result = service.extract_fact(
        authority_document_id=authority_id,
        fact_key=fact_key,
        fact_name=fact_name,
        fact_category=fact_category,
        fact_value=parsed_value,
        fact_value_type=fact_value_type,
        validity_conditions=conditions,
        fact_unit=fact_unit,
        fact_description=fact_description,
        source_page=source_page,
        source_section=source_section,
        source_quote=source_quote,
        extraction_confidence=extraction_confidence,
        extraction_method=extraction_method,
        extracted_by=user_id
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result


@router.get("/authorities/{authority_id}/facts")
def list_authority_facts(
    authority_id: UUID,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    List all extracted facts for a specific authority document.
    """
    from .authority_lineage_service import AuthorityLineageService
    from .models import TenantContext
    
    tenant_id = UUID(x_tenant_id)
    TenantContext.set_tenant_context(session, tenant_id)
    
    service = AuthorityLineageService(session, tenant_id)
    # We assume this method exists or we'll add it momentarily
    return service.list_authority_facts(authority_id)


@router.get("/facts/{fact_key}/resolve")
def resolve_fact(
    fact_key: str,
    budget: Optional[float] = None,
    project_type: Optional[str] = None,
    union: Optional[str] = None,
    as_of_date: Optional[date] = None,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    Resolve a fact for a given production context.
    
    Finds the applicable fact based on validity conditions like
    budget tier, date range, project type, and union affiliation.
    Returns the fact value with full provenance back to source document.
    """
    from .authority_lineage_service import AuthorityLineageService
    from .models import TenantContext
    
    tenant_id = UUID(x_tenant_id)
    TenantContext.set_tenant_context(session, tenant_id)
    
    context = {}
    if budget is not None:
        context["budget"] = budget
    if project_type:
        context["project_type"] = project_type
    if union:
        context["union"] = union
    
    service = AuthorityLineageService(session, tenant_id)
    result = service.resolve_fact(
        fact_key=fact_key,
        context=context,
        as_of_date=as_of_date
    )
    
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Fact '{fact_key}' not found or not applicable for given context"
        )
    
    return result


@router.get("/verdicts/{entity_type}/{entity_id}/lineage")
def get_verdict_lineage(
    entity_type: str,
    entity_id: UUID,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    Get the full lineage for a verdict or rule evaluation.
    
    Returns all facts cited by this entity with complete provenance
    back to the source authority documents, including document hashes.
    """
    from .authority_lineage_service import AuthorityLineageService
    from .models import TenantContext
    
    tenant_id = UUID(x_tenant_id)
    TenantContext.set_tenant_context(session, tenant_id)
    
    service = AuthorityLineageService(session, tenant_id)
    return service.get_verdict_lineage(
        citing_entity_type=entity_type,
        citing_entity_id=entity_id
    )


@router.get("/facts")
def list_facts(
    fact_category: Optional[str] = None,
    authority_code: Optional[str] = None,
    current_only: bool = True,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    List extracted facts with optional filtering.
    
    Filter by fact category (rate, threshold, deadline, requirement)
    or source authority document code.
    """
    from .pcos_models import PCOSExtractedFactModel, PCOSAuthorityDocumentModel
    from .models import set_tenant_context
    
    tenant_id = UUID(x_tenant_id)
    set_tenant_context(session, tenant_id)
    
    query = (
        select(PCOSExtractedFactModel)
        .where(PCOSExtractedFactModel.tenant_id == tenant_id)
    )
    
    if current_only:
        query = query.where(PCOSExtractedFactModel.is_current == True)
    
    if fact_category:
        query = query.where(PCOSExtractedFactModel.fact_category == fact_category)
    
    if authority_code:
        query = (
            query.join(PCOSAuthorityDocumentModel)
            .where(PCOSAuthorityDocumentModel.document_code == authority_code)
        )
    
    query = query.order_by(PCOSExtractedFactModel.fact_key)
    
    facts = session.execute(query).scalars().all()
    
    return [
        {
            "id": str(f.id),
            "fact_key": f.fact_key,
            "fact_name": f.fact_name,
            "fact_category": f.fact_category,
            "value_type": f.fact_value_type,
            "value": float(f.fact_value_decimal) if f.fact_value_decimal else (
                f.fact_value_integer or f.fact_value_string or f.fact_value_boolean
            ),
            "unit": f.fact_unit,
            "version": f.version,
            "is_current": f.is_current,
            "validity_conditions": f.validity_conditions,
            "authority_id": str(f.authority_document_id),
            "extraction_confidence": float(f.extraction_confidence) if f.extraction_confidence else None,
            "created_at": f.created_at.isoformat()
        }
        for f in facts
    ]


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
    from .compliance_invariants import ComplianceInvariantsService
    from .models import set_tenant_context
    
    tenant_id = UUID(x_tenant_id)
    set_tenant_context(session, tenant_id)
    
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
    from .compliance_invariants import ComplianceInvariantsService
    from .models import set_tenant_context
    
    tenant_id = UUID(x_tenant_id)
    set_tenant_context(session, tenant_id)
    
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
    from .compliance_invariants import ComplianceInvariantsService
    from .models import set_tenant_context
    
    tenant_id = UUID(x_tenant_id)
    set_tenant_context(session, tenant_id)
    
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
    from .compliance_invariants import ComplianceInvariantsService
    from .models import set_tenant_context
    
    tenant_id = UUID(x_tenant_id)
    set_tenant_context(session, tenant_id)
    
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
    from .compliance_invariants import ComplianceInvariantsService
    from .models import set_tenant_context
    
    tenant_id = UUID(x_tenant_id)
    set_tenant_context(session, tenant_id)
    
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
    from .compliance_invariants import ComplianceInvariantsService
    from .models import set_tenant_context
    
    tenant_id = UUID(x_tenant_id)
    user_id = UUID(x_user_id) if x_user_id else None
    set_tenant_context(session, tenant_id)
    
    service = ComplianceInvariantsService(session, tenant_id)
    return service.create_correction(
        original_verdict_id=original_verdict_id,
        corrected_result=corrected_result,
        correction_reason=correction_reason,
        corrected_by=user_id
    )


