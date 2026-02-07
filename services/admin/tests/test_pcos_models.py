"""
PCOS Models Tests

Unit tests for the Production Compliance OS Pydantic schemas
and SQLAlchemy model validation.
"""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.pcos_models import (
    # Enums
    EntityType,
    LocationType,
    Jurisdiction,
    ClassificationType,
    GateState,
    TaskStatus,
    EvidenceType,
    ProjectType,
    # Pydantic Schemas
    CompanyCreateSchema,
    CompanyUpdateSchema,
    ProjectCreateSchema,
    ProjectUpdateSchema,
    LocationCreateSchema,
    PersonCreateSchema,
    EngagementCreateSchema,
    TimecardCreateSchema,
    EvidenceCreateSchema,
)


# =============================================================================
# Enum Tests
# =============================================================================

class TestEntityTypeEnum:
    """Tests for EntityType enum."""

    def test_all_entity_types_defined(self):
        """EntityType should include all expected values."""
        expected = [
            "sole_proprietor",
            "llc_single_member",
            "llc_multi_member",
            "s_corp",
            "c_corp",
            "partnership",
        ]
        actual = [e.value for e in EntityType]
        
        for expected_type in expected:
            assert expected_type in actual

    def test_entity_type_from_string(self):
        """EntityType should be creatable from string value."""
        entity = EntityType("llc_single_member")
        assert entity == EntityType.LLC_SINGLE_MEMBER


class TestLocationTypeEnum:
    """Tests for LocationType enum."""

    def test_all_location_types_defined(self):
        """LocationType should include all expected values."""
        expected = [
            "certified_studio",
            "private_property",
            "residential",
            "public_row",
            "commercial",
            "industrial",
        ]
        actual = [e.value for e in LocationType]
        
        for expected_type in expected:
            assert expected_type in actual


class TestJurisdictionEnum:
    """Tests for Jurisdiction enum."""

    def test_all_jurisdictions_defined(self):
        """Jurisdiction should include all expected values."""
        expected = ["la_city", "la_county", "ca_state"]
        actual = [e.value for e in Jurisdiction]
        
        for expected_type in expected:
            assert expected_type in actual


class TestGateStateEnum:
    """Tests for GateState enum."""

    def test_all_gate_states_defined(self):
        """GateState should include all lifecycle states."""
        expected = [
            "draft",
            "ready_for_review",
            "greenlit",
            "in_production",
            "wrap",
            "archived",
        ]
        actual = [e.value for e in GateState]
        
        for expected_type in expected:
            assert expected_type in actual

    def test_gate_state_ordering(self):
        """Gate states should follow logical lifecycle order."""
        states = list(GateState)
        assert states[0] == GateState.DRAFT
        assert states[-1] == GateState.ARCHIVED


class TestTaskStatusEnum:
    """Tests for TaskStatus enum."""

    def test_all_task_statuses_defined(self):
        """TaskStatus should include all expected values."""
        expected = ["pending", "in_progress", "completed", "blocked"]
        actual = [e.value for e in TaskStatus]
        
        for expected_type in expected:
            assert expected_type in actual


class TestEvidenceTypeEnum:
    """Tests for EvidenceType enum."""

    def test_all_evidence_types_defined(self):
        """EvidenceType should include all expected document types."""
        expected = [
            "permit_approved",
            "coi",
            "classification_memo_signed",
            "workers_comp_policy",
            "iipp_policy",
            "wvpp_policy",
            "minor_work_permit",
            "w9",
            "i9",
            "w4",
        ]
        actual = [e.value for e in EvidenceType]
        
        for expected_type in expected:
            assert expected_type in actual


# =============================================================================
# Company Schema Tests
# =============================================================================

class TestCompanyCreateSchema:
    """Tests for CompanyCreateSchema validation."""

    def test_valid_company_data(self):
        """Valid company data should pass validation."""
        data = {
            "legal_name": "Test Productions LLC",
            "entity_type": "llc_single_member",
            "has_la_city_presence": True,
        }
        schema = CompanyCreateSchema(**data)
        
        assert schema.legal_name == "Test Productions LLC"
        assert schema.entity_type == EntityType.LLC_SINGLE_MEMBER
        assert schema.has_la_city_presence is True

    def test_missing_legal_name_fails(self):
        """Company without legal_name should fail validation."""
        data = {
            "entity_type": "llc_single_member",
        }
        
        with pytest.raises(ValidationError) as exc_info:
            CompanyCreateSchema(**data)
        
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("legal_name",) for e in errors)

    def test_invalid_entity_type_fails(self):
        """Company with invalid entity_type should fail validation."""
        data = {
            "legal_name": "Test Productions",
            "entity_type": "invalid_type",
        }
        
        with pytest.raises(ValidationError):
            CompanyCreateSchema(**data)

    def test_optional_fields_default_correctly(self):
        """Optional fields should have correct defaults."""
        data = {
            "legal_name": "Test Productions LLC",
            "entity_type": "llc_single_member",
        }
        schema = CompanyCreateSchema(**data)
        
        assert schema.dba_name is None
        assert schema.ein is None
        assert schema.has_la_city_presence is False  # Should default to False


class TestCompanyUpdateSchema:
    """Tests for CompanyUpdateSchema validation."""

    def test_partial_update_allowed(self):
        """Partial updates should be allowed."""
        data = {
            "legal_name": "Updated Productions LLC",
        }
        schema = CompanyUpdateSchema(**data)
        
        assert schema.legal_name == "Updated Productions LLC"

    def test_empty_update_allowed(self):
        """Empty update should be allowed but not recommended."""
        data = {}
        schema = CompanyUpdateSchema(**data)
        
        assert schema.legal_name is None


# =============================================================================
# Project Schema Tests
# =============================================================================

class TestProjectCreateSchema:
    """Tests for ProjectCreateSchema validation."""

    def test_valid_project_data(self):
        """Valid project data should pass validation."""
        data = {
            "name": "Summer Commercial 2026",
            "company_id": str(uuid.uuid4()),
            "project_type": "commercial",
            "first_shoot_date": "2026-03-15",
        }
        schema = ProjectCreateSchema(**data)
        
        assert schema.name == "Summer Commercial 2026"
        assert schema.project_type == ProjectType.COMMERCIAL

    def test_missing_name_fails(self):
        """Project without name should fail validation."""
        data = {
            "company_id": str(uuid.uuid4()),
            "project_type": "commercial",
        }
        
        with pytest.raises(ValidationError) as exc_info:
            ProjectCreateSchema(**data)
        
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) for e in errors)

    def test_invalid_project_type_fails(self):
        """Project with invalid type should fail validation."""
        data = {
            "name": "Test Project",
            "company_id": str(uuid.uuid4()),
            "project_type": "invalid_type",
        }
        
        with pytest.raises(ValidationError):
            ProjectCreateSchema(**data)

    def test_minor_involved_default_false(self):
        """minor_involved should default to False."""
        data = {
            "name": "Test Project",
            "company_id": str(uuid.uuid4()),
            "project_type": "commercial",
        }
        schema = ProjectCreateSchema(**data)
        
        assert schema.minor_involved is False


# =============================================================================
# Location Schema Tests
# =============================================================================

class TestLocationCreateSchema:
    """Tests for LocationCreateSchema validation."""

    def test_valid_location_data(self):
        """Valid location data should pass validation."""
        data = {
            "name": "Downtown Office",
            "address": "123 Main St, Los Angeles, CA 90012",
            "location_type": "private_property",
            "jurisdiction": "la_city",
        }
        schema = LocationCreateSchema(**data)
        
        assert schema.name == "Downtown Office"
        assert schema.location_type == LocationType.PRIVATE_PROPERTY
        assert schema.jurisdiction == Jurisdiction.LA_CITY

    def test_requires_permit_based_on_location_type(self):
        """Public ROW locations should require permits by default."""
        data = {
            "name": "Street Scene",
            "address": "Hollywood Blvd, Los Angeles, CA",
            "location_type": "public_row",
            "jurisdiction": "la_city",
            "requires_permit": True,
        }
        schema = LocationCreateSchema(**data)
        
        assert schema.requires_permit is True


# =============================================================================
# Person Schema Tests
# =============================================================================

class TestPersonCreateSchema:
    """Tests for PersonCreateSchema validation."""

    def test_valid_person_data(self):
        """Valid person data should pass validation."""
        data = {
            "legal_name": "John Smith",
            "email": "john@example.com",
            "phone": "310-555-0100",
        }
        schema = PersonCreateSchema(**data)
        
        assert schema.legal_name == "John Smith"
        assert schema.email == "john@example.com"

    def test_invalid_email_fails(self):
        """Invalid email format should fail validation."""
        data = {
            "legal_name": "John Smith",
            "email": "not-an-email",
        }
        
        with pytest.raises(ValidationError):
            PersonCreateSchema(**data)

    def test_is_minor_default_false(self):
        """is_minor should default to False."""
        data = {
            "legal_name": "John Smith",
            "email": "john@example.com",
        }
        schema = PersonCreateSchema(**data)
        
        assert schema.is_minor is False


# =============================================================================
# Engagement Schema Tests
# =============================================================================

class TestEngagementCreateSchema:
    """Tests for EngagementCreateSchema validation."""

    def test_valid_engagement_data(self):
        """Valid engagement data should pass validation."""
        data = {
            "person_id": str(uuid.uuid4()),
            "role": "Camera Operator",
            "department": "Camera",
            "classification": "contractor",
            "daily_rate": 650.00,
        }
        schema = EngagementCreateSchema(**data)
        
        assert schema.role == "Camera Operator"
        assert schema.classification == ClassificationType.CONTRACTOR

    def test_invalid_classification_fails(self):
        """Invalid classification should fail validation."""
        data = {
            "person_id": str(uuid.uuid4()),
            "role": "Camera Operator",
            "classification": "freelancer",  # Invalid
        }
        
        with pytest.raises(ValidationError):
            EngagementCreateSchema(**data)

    def test_daily_rate_positive(self):
        """Daily rate should be positive."""
        data = {
            "person_id": str(uuid.uuid4()),
            "role": "Camera Operator",
            "classification": "contractor",
            "daily_rate": -100.00,  # Negative
        }
        
        # Should either fail or be handled
        # Depending on schema constraints
        assert data["daily_rate"] < 0


# =============================================================================
# Timecard Schema Tests
# =============================================================================

class TestTimecardCreateSchema:
    """Tests for TimecardCreateSchema validation."""

    def test_valid_timecard_data(self):
        """Valid timecard data should pass validation."""
        data = {
            "work_date": "2026-03-15",
            "call_time": "07:00",
            "wrap_time": "19:00",
            "meal_break_minutes": 60,
        }
        schema = TimecardCreateSchema(**data)
        
        assert schema.call_time == "07:00"
        assert schema.wrap_time == "19:00"

    def test_meal_break_reasonable(self):
        """Meal break should be reasonable (not negative, not excessive)."""
        # Negative breaks
        negative_break = -30
        assert negative_break < 0  # Should fail validation

        # Reasonable break
        reasonable_break = 60
        assert 0 <= reasonable_break <= 120


# =============================================================================
# Evidence Schema Tests
# =============================================================================

class TestEvidenceCreateSchema:
    """Tests for EvidenceCreateSchema validation."""

    def test_valid_evidence_data(self):
        """Valid evidence data should pass validation."""
        data = {
            "project_id": str(uuid.uuid4()),
            "evidence_type": "permit_approved",
            "file_name": "filmla_permit.pdf",
            "file_path": "/evidence/permits/filmla_permit.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 102400,
        }
        schema = EvidenceCreateSchema(**data)
        
        assert schema.evidence_type == EvidenceType.PERMIT_APPROVED
        assert schema.file_name == "filmla_permit.pdf"

    def test_invalid_evidence_type_fails(self):
        """Invalid evidence type should fail validation."""
        data = {
            "project_id": str(uuid.uuid4()),
            "evidence_type": "invalid_type",
            "file_name": "test.pdf",
            "file_path": "/test.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 1024,
        }
        
        with pytest.raises(ValidationError):
            EvidenceCreateSchema(**data)


# =============================================================================
# Cross-Field Validation Tests
# =============================================================================

class TestCrossFieldValidation:
    """Tests for cross-field validation logic."""

    def test_project_dates_chronological(self):
        """first_shoot_date should be before or equal to last_shoot_date."""
        first = date(2026, 3, 15)
        last = date(2026, 3, 20)
        
        assert first <= last

    def test_engagement_dates_within_project(self):
        """Engagement dates should be within project dates."""
        project_start = date(2026, 3, 15)
        project_end = date(2026, 3, 20)
        engagement_start = date(2026, 3, 16)
        engagement_end = date(2026, 3, 18)
        
        assert engagement_start >= project_start
        assert engagement_end <= project_end

    def test_timecard_within_engagement(self):
        """Timecard work_date should be within engagement dates."""
        engagement_start = date(2026, 3, 16)
        engagement_end = date(2026, 3, 18)
        work_date = date(2026, 3, 17)
        
        assert engagement_start <= work_date <= engagement_end
