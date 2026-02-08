"""
PCOS Entities Router — Companies, Projects, Locations, People, Engagements, Tasks.
"""

from __future__ import annotations

import uuid as uuid_module
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import UUID

from ._shared import get_pcos_tenant_context
from ..pcos_models import (
    PCOSCompanyModel,
    PCOSProjectModel,
    PCOSLocationModel,
    PCOSPersonModel,
    PCOSEngagementModel,
    PCOSTaskModel,
    # Pydantic Schemas
    CompanyCreateSchema,
    CompanyUpdateSchema,
    CompanyResponseSchema,
    ProjectCreateSchema,
    ProjectUpdateSchema,
    ProjectResponseSchema,
    LocationCreateSchema,
    LocationResponseSchema,
    PersonCreateSchema,
    PersonResponseSchema,
    EngagementCreateSchema,
    EngagementResponseSchema,
    TaskResponseSchema,
    TaskUpdateSchema,
    GateState,
    TaskStatus,
)

logger = structlog.get_logger("pcos.entities")

router = APIRouter(tags=["PCOS Entities"])


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
