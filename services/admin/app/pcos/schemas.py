"""
PCOS Pydantic Schemas

Request/Response models for API endpoints.
"""

import uuid as uuid_module
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from .enums import (
    ClassificationType,
    EntityType,
    EvidenceType,
    Jurisdiction,
    LocationType,
    OwnerPayMode,
    ProjectType,
    TaskStatus,
)

# Pydantic Schemas (API Request/Response Models)
# =============================================================================

class AddressSchema(BaseModel):
    """Reusable address schema."""
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = "CA"
    zip: Optional[str] = None


# --- Company Schemas ---

class CompanyCreateSchema(BaseModel):
    """Schema for creating a company."""
    legal_name: str
    entity_type: EntityType
    ein: Optional[str] = None
    sos_entity_number: Optional[str] = None
    legal_address: Optional[AddressSchema] = None
    mailing_address: Optional[AddressSchema] = None
    has_la_city_presence: bool = False
    la_business_address: Optional[AddressSchema] = None
    owner_pay_mode: Optional[OwnerPayMode] = None


class CompanyUpdateSchema(BaseModel):
    """Schema for updating a company."""
    legal_name: Optional[str] = None
    entity_type: Optional[EntityType] = None
    ein: Optional[str] = None
    sos_entity_number: Optional[str] = None
    has_la_city_presence: Optional[bool] = None
    owner_pay_mode: Optional[OwnerPayMode] = None
    owner_pay_cpa_approved: Optional[bool] = None
    status: Optional[str] = None


class CompanyResponseSchema(BaseModel):
    """Schema for company response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    tenant_id: uuid_module.UUID
    legal_name: str
    entity_type: str
    has_la_city_presence: bool
    owner_pay_mode: Optional[str] = None
    owner_pay_cpa_approved: bool
    status: str
    created_at: datetime


# --- Project Schemas ---

class ProjectCreateSchema(BaseModel):
    """Schema for creating a project."""
    name: str
    company_id: uuid_module.UUID
    code: Optional[str] = None
    project_type: ProjectType
    is_commercial: bool = False
    client_name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    first_shoot_date: Optional[date] = None
    union_status: str = "non_union"
    minor_involved: bool = False


class ProjectUpdateSchema(BaseModel):
    """Schema for updating a project."""
    name: Optional[str] = None
    code: Optional[str] = None
    project_type: Optional[ProjectType] = None
    is_commercial: Optional[bool] = None
    client_name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    first_shoot_date: Optional[date] = None
    union_status: Optional[str] = None
    minor_involved: Optional[bool] = None
    notes: Optional[str] = None


class ProjectResponseSchema(BaseModel):
    """Schema for project response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    tenant_id: uuid_module.UUID
    company_id: uuid_module.UUID
    name: str
    code: Optional[str] = None
    project_type: str
    is_commercial: bool
    client_name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    first_shoot_date: Optional[date] = None
    union_status: str
    minor_involved: bool
    gate_state: str
    risk_score: int
    blocking_tasks_count: int
    created_at: datetime


# --- Location Schemas ---

class LocationCreateSchema(BaseModel):
    """Schema for creating a location."""
    name: str
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: str = "CA"
    zip: Optional[str] = None
    jurisdiction: Jurisdiction
    location_type: LocationType
    estimated_crew_size: Optional[int] = None
    parking_spaces_needed: Optional[int] = None
    filming_hours_start: Optional[time] = None
    filming_hours_end: Optional[time] = None
    has_generator: bool = False
    has_special_effects: bool = False
    noise_level: Optional[str] = None
    shoot_dates: Optional[list[date]] = None


class LocationResponseSchema(BaseModel):
    """Schema for location response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    project_id: uuid_module.UUID
    name: str
    city: Optional[str] = None
    jurisdiction: str
    location_type: str
    permit_required: Optional[bool] = None
    created_at: datetime


# --- Engagement Schemas ---

class EngagementCreateSchema(BaseModel):
    """Schema for creating an engagement."""
    person_id: uuid_module.UUID
    role_title: str
    department: Optional[str] = None
    classification: ClassificationType
    pay_rate: Decimal
    pay_type: str  # 'hourly', 'daily', 'weekly', 'flat', 'kit_rental'
    overtime_eligible: bool = True
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    guaranteed_days: Optional[int] = None


class EngagementResponseSchema(BaseModel):
    """Schema for engagement response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    project_id: uuid_module.UUID
    person_id: uuid_module.UUID
    role_title: str
    department: Optional[str] = None
    classification: str
    pay_rate: Decimal
    pay_type: str
    status: str
    classification_memo_signed: bool
    w9_received: bool
    i9_received: bool
    w4_received: bool
    created_at: datetime


# --- Timecard Schemas ---

class TimecardCreateSchema(BaseModel):
    """Schema for creating a timecard."""
    work_date: date
    call_time: Optional[time] = None
    wrap_time: Optional[time] = None
    meal_1_out: Optional[time] = None
    meal_1_in: Optional[time] = None
    meal_2_out: Optional[time] = None
    meal_2_in: Optional[time] = None
    notes: Optional[str] = None


class TimecardResponseSchema(BaseModel):
    """Schema for timecard response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    engagement_id: uuid_module.UUID
    work_date: date
    call_time: Optional[time] = None
    wrap_time: Optional[time] = None
    regular_hours: Optional[Decimal] = None
    overtime_hours: Optional[Decimal] = None
    double_time_hours: Optional[Decimal] = None
    meal_penalty_count: int
    status: str
    wage_floor_met: Optional[bool] = None
    created_at: datetime


# --- Task Schemas ---

class TaskResponseSchema(BaseModel):
    """Schema for task response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    tenant_id: uuid_module.UUID
    source_type: str
    source_id: uuid_module.UUID
    task_type: str
    title: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    status: str
    is_blocking: bool
    requires_evidence: bool
    completed_at: Optional[datetime] = None
    created_at: datetime


class TaskUpdateSchema(BaseModel):
    """Schema for updating a task."""
    status: Optional[TaskStatus] = None
    notes: Optional[str] = None
    assigned_to: Optional[uuid_module.UUID] = None


# --- Gate Evaluation Schemas ---

class GateEvaluationResponseSchema(BaseModel):
    """Schema for gate evaluation response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    project_id: uuid_module.UUID
    current_state: str
    target_state: Optional[str] = None
    transition_allowed: bool
    blocking_tasks_count: int
    missing_evidence: Optional[list[str]] = None
    risk_score: int
    reasons: Optional[list[str]] = None
    evaluated_at: datetime


# --- Evidence Schemas ---

class EvidenceCreateSchema(BaseModel):
    """Schema for creating evidence."""
    entity_type: str
    entity_id: uuid_module.UUID
    evidence_type: EvidenceType
    title: str
    description: Optional[str] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None


class EvidenceResponseSchema(BaseModel):
    """Schema for evidence response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    tenant_id: uuid_module.UUID
    entity_type: str
    entity_id: uuid_module.UUID
    evidence_type: str
    title: str
    file_name: Optional[str] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    is_signed: bool
    created_at: datetime


# --- Person Schemas ---

class PersonCreateSchema(BaseModel):
    """Schema for creating a person."""
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    address: Optional[AddressSchema] = None
    preferred_classification: Optional[ClassificationType] = None
    is_loan_out: bool = False
    loan_out_company_name: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relation: Optional[str] = None


class PersonResponseSchema(BaseModel):
    """Schema for person response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    tenant_id: uuid_module.UUID
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    preferred_classification: Optional[str] = None
    is_loan_out: bool
    status: str
    created_at: datetime


# =============================================================================
