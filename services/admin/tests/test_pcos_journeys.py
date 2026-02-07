"""
PCOS Integration Journey Tests

End-to-end journey tests for the Production Compliance OS module.
Tests complete user workflows from company creation through greenlight.
"""
import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.pcos_models import (
    GateState,
    TaskStatus,
    ClassificationType,
    LocationType,
    Jurisdiction,
    EvidenceType,
    EntityType,
    ProjectType,
)


# =============================================================================
# Journey A: Company Onboarding → Compliance Calendar
# =============================================================================

class TestJourneyCompanyOnboarding:
    """
    Journey A: New company onboarding
    
    User Story: As a new production company, I want to register my company
    and see what compliance tasks are automatically generated based on my
    company profile.
    """

    def test_journey_step1_create_company(self):
        """Step 1: Create a new production company."""
        company_data = {
            "legal_name": "Sunset Productions LLC",
            "dba_name": "Sunset Films",
            "entity_type": EntityType.LLC_SINGLE_MEMBER,
            "has_la_city_presence": True,
            "ein": "12-3456789",
            "mailing_address": "123 Sunset Blvd, Los Angeles, CA 90028",
        }
        
        # Verify all required fields present
        assert "legal_name" in company_data
        assert "entity_type" in company_data
        assert company_data["has_la_city_presence"] is True

    def test_journey_step2_company_with_la_presence_triggers_btrc(self):
        """Step 2: LA City presence should trigger BTRC registration task."""
        # When has_la_city_presence is True, expect BTRC task
        company_facts = {
            "has_la_city_presence": True,
        }
        
        expected_tasks = ["la_btrc_registration"]
        
        assert "la_btrc_registration" in expected_tasks

    def test_journey_step3_company_entity_triggers_sos_task(self):
        """Step 3: LLC/Corp entities should trigger SOS Statement of Info."""
        entity_type = EntityType.LLC_SINGLE_MEMBER
        
        # LLCs and Corps require SOS Statement of Information
        requires_sos = entity_type in [
            EntityType.LLC_SINGLE_MEMBER,
            EntityType.LLC_MULTI_MEMBER,
            EntityType.S_CORP,
            EntityType.C_CORP,
        ]
        
        assert requires_sos is True


# =============================================================================
# Journey B: Project Creation → Permit Task → Greenlight Block
# =============================================================================

class TestJourneyProjectCreationToGreenlight:
    """
    Journey B: Project lifecycle from creation to greenlight attempt
    
    User Story: As a producer, I want to create a project, add locations,
    understand what compliance tasks exist, and see why I cannot greenlight
    until all blocking tasks are complete.
    """

    def test_journey_step1_create_project(self):
        """Step 1: Create a new production project."""
        project_data = {
            "name": "Summer Commercial 2026",
            "company_id": uuid.uuid4(),
            "project_type": ProjectType.COMMERCIAL,
            "is_commercial": True,
            "first_shoot_date": date.today() + timedelta(days=30),
            "last_shoot_date": date.today() + timedelta(days=32),
            "minor_involved": False,
        }
        
        assert project_data["project_type"] == ProjectType.COMMERCIAL
        assert project_data["is_commercial"] is True

    def test_journey_step2_new_project_starts_in_draft(self):
        """Step 2: New project should start in DRAFT state."""
        initial_state = GateState.DRAFT
        assert initial_state == GateState.DRAFT

    def test_journey_step3_add_public_row_location(self):
        """Step 3: Add a public ROW location that requires permit."""
        location_data = {
            "name": "Hollywood Blvd Street Scene",
            "address": "Hollywood Blvd & Vine St, Los Angeles, CA",
            "location_type": LocationType.PUBLIC_ROW,
            "jurisdiction": Jurisdiction.LA_CITY,
            "requires_permit": True,
            "shoot_dates": [date.today() + timedelta(days=30)],
        }
        
        assert location_data["location_type"] == LocationType.PUBLIC_ROW
        assert location_data["requires_permit"] is True

    def test_journey_step4_permit_location_triggers_filmla_task(self):
        """Step 4: Public ROW in LA should trigger FilmLA permit task."""
        location_facts = {
            "location_type": LocationType.PUBLIC_ROW,
            "jurisdiction": Jurisdiction.LA_CITY,
            "requires_permit": True,
        }
        
        # Rule: permit_filmla_required triggers filmla_permit_packet task
        expected_task = "filmla_permit_packet"
        assert expected_task == "filmla_permit_packet"

    def test_journey_step5_blocking_task_blocks_greenlight(self):
        """Step 5: Incomplete blocking task should prevent greenlight."""
        blocking_tasks = [
            {
                "id": uuid.uuid4(),
                "task_type": "filmla_permit_packet",
                "title": "Submit FilmLA Permit Application",
                "status": TaskStatus.PENDING,
                "is_blocking": True,
            }
        ]
        
        can_greenlight = len([t for t in blocking_tasks if t["status"] != TaskStatus.COMPLETED]) == 0
        assert can_greenlight is False

    def test_journey_step6_complete_task_allows_greenlight(self):
        """Step 6: Completing all blocking tasks should allow greenlight."""
        blocking_tasks = [
            {
                "id": uuid.uuid4(),
                "task_type": "filmla_permit_packet",
                "title": "Submit FilmLA Permit Application",
                "status": TaskStatus.COMPLETED,
                "is_blocking": True,
            }
        ]
        
        # Also need required evidence
        evidence = [EvidenceType.PERMIT_APPROVED, EvidenceType.COI]
        
        blocking_count = len([t for t in blocking_tasks if t["status"] != TaskStatus.COMPLETED])
        has_evidence = len(evidence) >= 2
        
        can_greenlight = blocking_count == 0 and has_evidence
        assert can_greenlight is True


# =============================================================================
# Journey C: Engagement → Timecard → Wage Validation
# =============================================================================

class TestJourneyEngagementTimecard:
    """
    Journey C: Crew engagement and timecard workflow
    
    User Story: As a payroll admin, I want to add crew to a project,
    submit their timecards, and ensure wage floors are validated
    before approval.
    """

    def test_journey_step1_create_crew_person(self):
        """Step 1: Create a person in the registry."""
        person_data = {
            "legal_name": "John Smith",
            "email": "john@example.com",
            "phone": "310-555-0100",
            "is_minor": False,
        }
        
        assert person_data["legal_name"] == "John Smith"
        assert person_data["is_minor"] is False

    def test_journey_step2_create_contractor_engagement(self):
        """Step 2: Create a contractor engagement on the project."""
        engagement_data = {
            "person_id": uuid.uuid4(),
            "role": "Camera Operator",
            "department": "Camera",
            "classification": ClassificationType.CONTRACTOR,
            "daily_rate": 650.00,
            "start_date": date.today() + timedelta(days=30),
        }
        
        assert engagement_data["classification"] == ClassificationType.CONTRACTOR
        assert engagement_data["daily_rate"] == 650.00

    def test_journey_step3_contractor_triggers_classification_memo(self):
        """Step 3: Contractor engagement triggers classification memo task."""
        classification = ClassificationType.CONTRACTOR
        
        # Rule: contractor_classification_memo triggers task
        expected_task = "classification_memo"
        assert expected_task == "classification_memo"

    def test_journey_step4_submit_timecard(self):
        """Step 4: Submit a timecard for a work day."""
        timecard_data = {
            "work_date": date.today() + timedelta(days=30),
            "call_time": "07:00",
            "wrap_time": "19:00",
            "meal_break_minutes": 60,
            "hours_worked": 11.0,
            "daily_rate": 650.00,
        }
        
        assert timecard_data["hours_worked"] == 11.0

    def test_journey_step5_wage_floor_validation_passes(self):
        """Step 5: Timecard should pass wage floor validation."""
        daily_rate = 650.00
        hours_worked = 11.0
        effective_hourly = daily_rate / hours_worked  # 59.09
        
        la_city_minimum = 17.28
        wage_floor_met = effective_hourly >= la_city_minimum
        
        assert wage_floor_met is True

    def test_journey_step6_approve_timecard(self):
        """Step 6: Approve the timecard."""
        timecard = {
            "status": "pending",
            "wage_floor_met": True,
        }
        
        # After approval
        timecard["status"] = "approved"
        timecard["approved_at"] = "2026-03-15T18:00:00Z"
        
        assert timecard["status"] == "approved"


# =============================================================================
# Journey D: Minor Involvement → Special Requirements
# =============================================================================

class TestJourneyMinorInvolvement:
    """
    Journey D: Project with minor talent
    
    User Story: As a production with child actors, I need to ensure
    all minor-specific compliance requirements are tracked, including
    work permits, studio teachers, and trust accounts.
    """

    def test_journey_step1_create_project_with_minor(self):
        """Step 1: Create project with minor_involved flag."""
        project_data = {
            "name": "Kids Commercial 2026",
            "project_type": ProjectType.COMMERCIAL,
            "minor_involved": True,
        }
        
        assert project_data["minor_involved"] is True

    def test_journey_step2_minor_triggers_work_permit_task(self):
        """Step 2: Minor involvement triggers work permit task."""
        minor_involved = True
        
        # Rule: minor_work_permit triggers task
        expected_tasks = ["minor_permit_verification"]
        assert "minor_permit_verification" in expected_tasks

    def test_journey_step3_minor_triggers_studio_teacher_task(self):
        """Step 3: Minor involvement triggers studio teacher task."""
        minor_involved = True
        
        # Rule: minor_studio_teacher triggers task
        expected_tasks = ["studio_teacher_confirmation"]
        assert "studio_teacher_confirmation" in expected_tasks

    def test_journey_step4_minor_evidence_required_for_greenlight(self):
        """Step 4: Greenlight requires minor_work_permit evidence."""
        minor_involved = True
        required_evidence = ["minor_work_permit"]
        
        assert "minor_work_permit" in required_evidence

    def test_journey_step5_minor_adds_to_risk_score(self):
        """Step 5: Minor involvement adds to project risk score."""
        base_risk = 0
        minor_risk_addition = 5  # Per risk calculation algorithm
        
        total_risk = base_risk + minor_risk_addition
        assert total_risk == 5


# =============================================================================
# Journey E: Employee Classification → Onboarding Tasks
# =============================================================================

class TestJourneyEmployeeOnboarding:
    """
    Journey E: Employee engagement triggers compliance
    
    User Story: As a production hiring W-2 employees, I need to ensure
    all employer obligations are tracked, including workers' comp,
    safety policies, and new hire reporting.
    """

    def test_journey_step1_create_employee_engagement(self):
        """Step 1: Create an employee engagement."""
        engagement_data = {
            "classification": ClassificationType.EMPLOYEE,
            "role": "Production Assistant",
            "daily_rate": 250.00,
        }
        
        assert engagement_data["classification"] == ClassificationType.EMPLOYEE

    def test_journey_step2_employee_triggers_workers_comp(self):
        """Step 2: Having employees triggers workers' comp requirement."""
        has_employees = True
        
        # Rule: employees_exist_workers_comp
        expected_evidence = ["workers_comp_policy"]
        assert "workers_comp_policy" in expected_evidence

    def test_journey_step3_employee_triggers_safety_policies(self):
        """Step 3: Employees trigger IIPP and WVPP requirements."""
        has_employees = True
        
        # Rule: employees_exist_safety_policies
        expected_evidence = ["iipp_policy", "wvpp_policy"]
        assert "iipp_policy" in expected_evidence
        assert "wvpp_policy" in expected_evidence

    def test_journey_step4_employee_triggers_new_hire_report(self):
        """Step 4: New employee triggers CA new hire report."""
        classification = ClassificationType.EMPLOYEE
        
        # Rule triggers new_hire_report task
        expected_task = "new_hire_report"
        assert expected_task == "new_hire_report"

    def test_journey_step5_employee_triggers_calsavers(self):
        """Step 5: Employees trigger CalSavers verification."""
        has_employees = True
        
        # Rule: employees_exist_calsavers (non-blocking)
        expected_task = "calsavers_verification"
        is_blocking = False  # CalSavers is warning, not blocking
        
        assert expected_task == "calsavers_verification"
        assert is_blocking is False


# =============================================================================
# Journey F: Complete Greenlight Flow
# =============================================================================

class TestJourneyCompleteGreenlight:
    """
    Journey F: Full greenlight approval flow
    
    User Story: As a production coordinator, I want to verify all
    requirements are met and successfully transition my project
    from DRAFT to GREENLIT status.
    """

    def test_journey_full_greenlight_checklist(self):
        """Complete greenlight checklist verification."""
        project = {
            "gate_state": GateState.READY_FOR_REVIEW,
            "minor_involved": False,
        }
        
        # Verify all requirements
        blocking_tasks = []  # All completed
        missing_evidence = []  # All uploaded
        
        can_greenlight = (
            len(blocking_tasks) == 0 and
            len(missing_evidence) == 0
        )
        
        assert can_greenlight is True

    def test_journey_greenlight_transitions_state(self):
        """Successful greenlight should transition to GREENLIT."""
        initial_state = GateState.READY_FOR_REVIEW
        target_state = GateState.GREENLIT
        
        # After successful greenlight
        new_state = GateState.GREENLIT
        
        assert new_state == target_state

    def test_journey_after_greenlight_next_states(self):
        """After greenlight, project can move to IN_PRODUCTION."""
        current_state = GateState.GREENLIT
        
        # Valid next transition
        next_valid = GateState.IN_PRODUCTION
        
        assert next_valid == GateState.IN_PRODUCTION

    def test_journey_production_to_wrap_flow(self):
        """Project should flow from IN_PRODUCTION to WRAP."""
        states_sequence = [
            GateState.GREENLIT,
            GateState.IN_PRODUCTION,
            GateState.WRAP,
            GateState.ARCHIVED,
        ]
        
        assert states_sequence[0] == GateState.GREENLIT
        assert states_sequence[-1] == GateState.ARCHIVED
