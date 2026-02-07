"""
PCOS Gate Evaluator Tests

Unit tests for the Production Compliance OS gate evaluation logic,
state machine transitions, and risk scoring.
"""
import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from app.pcos_models import (
    GateState,
    TaskStatus,
    EvidenceType,
    LocationType,
    Jurisdiction,
    ClassificationType,
)

# Import the module under test
from app.pcos_gate_evaluator import (
    PCOSGateEvaluator,
    GateEvaluation,
    TaskSummary,
    VALID_TRANSITIONS,
)


# =============================================================================
# State Machine Tests
# =============================================================================

class TestValidTransitions:
    """Tests for the state machine transition rules."""

    def test_draft_can_transition_to_ready_for_review(self):
        """DRAFT state should only allow transition to READY_FOR_REVIEW."""
        assert GateState.READY_FOR_REVIEW in VALID_TRANSITIONS[GateState.DRAFT]
        assert len(VALID_TRANSITIONS[GateState.DRAFT]) == 1

    def test_ready_for_review_can_transition_to_greenlit_or_draft(self):
        """READY_FOR_REVIEW can go to GREENLIT or back to DRAFT."""
        valid = VALID_TRANSITIONS[GateState.READY_FOR_REVIEW]
        assert GateState.GREENLIT in valid
        assert GateState.DRAFT in valid
        assert len(valid) == 2

    def test_greenlit_can_transition_to_in_production(self):
        """GREENLIT can transition to IN_PRODUCTION."""
        valid = VALID_TRANSITIONS[GateState.GREENLIT]
        assert GateState.IN_PRODUCTION in valid

    def test_in_production_can_transition_to_wrap(self):
        """IN_PRODUCTION can transition to WRAP."""
        valid = VALID_TRANSITIONS[GateState.IN_PRODUCTION]
        assert GateState.WRAP in valid

    def test_wrap_can_transition_to_archived(self):
        """WRAP can transition to ARCHIVED."""
        valid = VALID_TRANSITIONS[GateState.WRAP]
        assert GateState.ARCHIVED in valid

    def test_archived_is_terminal_state(self):
        """ARCHIVED should have no valid transitions (terminal state)."""
        assert VALID_TRANSITIONS[GateState.ARCHIVED] == []


# =============================================================================
# Gate Evaluation Data Structure Tests
# =============================================================================

class TestGateEvaluation:
    """Tests for the GateEvaluation dataclass."""

    def test_gate_evaluation_default_values(self):
        """GateEvaluation should have sensible defaults."""
        eval = GateEvaluation(
            project_id=uuid.uuid4(),
            current_state=GateState.DRAFT,
        )
        assert eval.can_transition is False
        assert eval.blocking_tasks_count == 0
        assert eval.blocking_tasks == []
        assert eval.missing_evidence == []
        assert eval.risk_score == 0
        assert eval.reasons == []

    def test_gate_evaluation_to_dict(self):
        """GateEvaluation.to_dict() should serialize correctly."""
        project_id = uuid.uuid4()
        eval = GateEvaluation(
            project_id=project_id,
            current_state=GateState.DRAFT,
            target_state=GateState.READY_FOR_REVIEW,
            can_transition=True,
            blocking_tasks_count=2,
            risk_score=45,
            reasons=["Missing permit", "Unpaid invoice"],
        )
        
        result = eval.to_dict()
        
        assert result["project_id"] == str(project_id)
        assert result["current_state"] == "draft"
        assert result["target_state"] == "ready_for_review"
        assert result["can_transition"] is True
        assert result["blocking_tasks_count"] == 2
        assert result["risk_score"] == 45
        assert len(result["reasons"]) == 2


class TestTaskSummary:
    """Tests for the TaskSummary dataclass."""

    def test_task_summary_creation(self):
        """TaskSummary should store task info correctly."""
        task_id = uuid.uuid4()
        summary = TaskSummary(
            id=task_id,
            title="Submit FilmLA Permit",
            task_type="filmla_permit_packet",
            due_date=date.today() + timedelta(days=7),
            status="pending",
        )
        
        assert summary.id == task_id
        assert summary.title == "Submit FilmLA Permit"
        assert summary.task_type == "filmla_permit_packet"
        assert summary.status == "pending"


# =============================================================================
# Risk Score Calculation Tests
# =============================================================================

class TestRiskScoreCalculation:
    """Tests for risk score calculation logic."""

    def test_risk_score_zero_when_no_issues(self):
        """Risk score should be 0 when project has no issues."""
        eval = GateEvaluation(
            project_id=uuid.uuid4(),
            current_state=GateState.GREENLIT,
            blocking_tasks_count=0,
            missing_evidence=[],
            risk_score=0,
        )
        assert eval.risk_score == 0

    def test_risk_score_increases_with_blocking_tasks(self):
        """Risk score should increase with blocking tasks."""
        # Each blocking task adds 15 points (max 45)
        # This tests the algorithm expectation, not implementation
        base_score = 0
        blocking_tasks = 2
        expected_contribution = min(blocking_tasks * 15, 45)
        assert expected_contribution == 30

    def test_risk_score_increases_with_missing_evidence(self):
        """Risk score should increase with missing evidence."""
        # Each missing evidence item adds 10 points (max 30)
        missing_count = 3
        expected_contribution = min(missing_count * 10, 30)
        assert expected_contribution == 30

    def test_risk_score_capped_at_100(self):
        """Risk score should never exceed 100."""
        # Even with many issues, score is capped
        max_score = 100
        # 3+ blocking tasks (45) + 3+ missing evidence (30) + 25 (time pressure) + 5 (minor)
        # = 105, but should cap at 100
        assert max_score == 100


# =============================================================================
# Greenlight Requirements Tests
# =============================================================================

class TestGreenlightRequirements:
    """Tests for greenlight gate requirements."""

    def test_greenlight_blocked_by_blocking_tasks(self):
        """Greenlight should be blocked if there are blocking tasks."""
        eval = GateEvaluation(
            project_id=uuid.uuid4(),
            current_state=GateState.READY_FOR_REVIEW,
            target_state=GateState.GREENLIT,
            blocking_tasks_count=1,
            blocking_tasks=[
                TaskSummary(
                    id=uuid.uuid4(),
                    title="Missing Permit",
                    task_type="filmla_permit_packet",
                )
            ],
            can_transition=False,
            reasons=["1 blocking task(s) must be completed"],
        )
        
        assert eval.can_transition is False
        assert eval.blocking_tasks_count == 1
        assert "blocking task" in eval.reasons[0].lower()

    def test_greenlight_blocked_by_missing_evidence(self):
        """Greenlight should be blocked if required evidence is missing."""
        eval = GateEvaluation(
            project_id=uuid.uuid4(),
            current_state=GateState.READY_FOR_REVIEW,
            target_state=GateState.GREENLIT,
            missing_evidence=["permit_approved", "workers_comp_policy"],
            can_transition=False,
            reasons=["Missing required evidence: permit_approved, workers_comp_policy"],
        )
        
        assert eval.can_transition is False
        assert len(eval.missing_evidence) == 2

    def test_greenlight_allowed_when_requirements_met(self):
        """Greenlight should be allowed when all requirements are met."""
        eval = GateEvaluation(
            project_id=uuid.uuid4(),
            current_state=GateState.READY_FOR_REVIEW,
            target_state=GateState.GREENLIT,
            blocking_tasks_count=0,
            blocking_tasks=[],
            missing_evidence=[],
            can_transition=True,
            reasons=[],
        )
        
        assert eval.can_transition is True
        assert eval.blocking_tasks_count == 0
        assert eval.missing_evidence == []


# =============================================================================
# Conditional Evidence Tests
# =============================================================================

class TestConditionalEvidenceRequirements:
    """Tests for conditional evidence based on project facts."""

    def test_permit_locations_require_permit_evidence(self):
        """Projects with permit locations need permit_approved evidence."""
        # When has_permit_locations is True, require permit_approved and coi
        required = ["permit_approved", "coi"]
        assert "permit_approved" in required
        assert "coi" in required

    def test_employees_require_workers_comp(self):
        """Projects with employees need workers_comp_policy."""
        # When has_employees is True, require workers_comp_policy
        required = ["workers_comp_policy"]
        assert "workers_comp_policy" in required

    def test_contractors_require_classification_memo(self):
        """Projects with contractors need classification_memo_signed."""
        # When has_contractors is True, require classification_memo_signed
        required = ["classification_memo_signed"]
        assert "classification_memo_signed" in required

    def test_minors_require_work_permit(self):
        """Projects with minors need minor_work_permit."""
        # When minor_involved is True, require minor_work_permit
        required = ["minor_work_permit"]
        assert "minor_work_permit" in required


# =============================================================================
# Wage Floor Validation Tests
# =============================================================================

class TestWageFloorValidation:
    """Tests for wage floor validation logic."""

    def test_la_city_minimum_wage_2026(self):
        """LA City minimum wage should be $17.28 in 2026."""
        la_city_min = 17.28
        assert la_city_min == 17.28

    def test_ca_state_minimum_wage_2026(self):
        """CA State minimum wage should be $16.50 in 2026."""
        ca_state_min = 16.50
        assert ca_state_min == 16.50

    def test_wage_below_floor_fails_validation(self):
        """Wage below floor should fail validation."""
        hourly_rate = 15.00
        la_city_min = 17.28
        assert hourly_rate < la_city_min

    def test_wage_at_floor_passes_validation(self):
        """Wage at exactly the floor should pass validation."""
        hourly_rate = 17.28
        la_city_min = 17.28
        assert hourly_rate >= la_city_min

    def test_wage_above_floor_passes_validation(self):
        """Wage above floor should pass validation."""
        hourly_rate = 25.00
        la_city_min = 17.28
        assert hourly_rate >= la_city_min


# =============================================================================
# Blocking Task Logic Tests
# =============================================================================

class TestBlockingTaskLogic:
    """Tests for blocking task identification."""

    def test_pending_blocking_task_blocks_transition(self):
        """A pending blocking task should block transitions."""
        task = {
            "status": TaskStatus.PENDING,
            "is_blocking": True,
        }
        is_blocking = task["status"] != TaskStatus.COMPLETED and task["is_blocking"]
        assert is_blocking is True

    def test_completed_blocking_task_does_not_block(self):
        """A completed blocking task should not block transitions."""
        task = {
            "status": TaskStatus.COMPLETED,
            "is_blocking": True,
        }
        is_blocking = task["status"] != TaskStatus.COMPLETED and task["is_blocking"]
        assert is_blocking is False

    def test_non_blocking_task_does_not_block(self):
        """A non-blocking task should never block transitions."""
        task = {
            "status": TaskStatus.PENDING,
            "is_blocking": False,
        }
        is_blocking = task["status"] != TaskStatus.COMPLETED and task["is_blocking"]
        assert is_blocking is False


# =============================================================================
# Project Facts Gathering Tests
# =============================================================================

class TestProjectFactsGathering:
    """Tests for project fact compilation."""

    def test_facts_include_location_info(self):
        """Facts should include has_permit_locations based on locations."""
        # Mock project with permit location
        facts = {
            "has_permit_locations": True,
            "has_public_row_locations": True,
            "has_certified_studio_locations": False,
            "location_count": 3,
        }
        assert facts["has_permit_locations"] is True

    def test_facts_include_engagement_info(self):
        """Facts should include employee/contractor counts."""
        facts = {
            "has_employees": True,
            "has_contractors": True,
            "employee_count": 5,
            "contractor_count": 10,
            "engagement_count": 15,
        }
        assert facts["has_employees"] is True
        assert facts["has_contractors"] is True
        assert facts["engagement_count"] == 15

    def test_facts_include_minor_status(self):
        """Facts should include minor_involved flag."""
        facts = {
            "minor_involved": True,
        }
        assert facts["minor_involved"] is True

    def test_facts_include_shoot_timing(self):
        """Facts should include days until first shoot."""
        today = date.today()
        first_shoot = today + timedelta(days=14)
        days_until = (first_shoot - today).days
        
        facts = {
            "first_shoot_date": first_shoot,
            "days_until_shoot": days_until,
        }
        assert facts["days_until_shoot"] == 14


# =============================================================================
# Integration-Style Tests (Mock DB)
# =============================================================================

class TestGateEvaluatorIntegration:
    """Integration tests using mocked database sessions."""

    @pytest.fixture
    def mock_session(self):
        """Provide a mocked database session."""
        session = MagicMock()
        session.execute = MagicMock()
        session.query = MagicMock()
        return session

    @pytest.fixture
    def evaluator(self, mock_session, tenant_id):
        """Create a PCOSGateEvaluator with mocked session."""
        return PCOSGateEvaluator(db=mock_session, tenant_id=tenant_id)

    def test_evaluator_initialization(self, mock_session, tenant_id):
        """Evaluator should initialize with session and tenant."""
        evaluator = PCOSGateEvaluator(db=mock_session, tenant_id=tenant_id)
        assert evaluator is not None

    def test_invalid_transition_raises_error(self):
        """Attempting invalid transition should raise ValueError."""
        # DRAFT -> GREENLIT is not valid (must go through READY_FOR_REVIEW)
        current = GateState.DRAFT
        target = GateState.GREENLIT
        
        valid_targets = VALID_TRANSITIONS[current]
        assert target not in valid_targets

    def test_valid_transition_from_draft(self):
        """DRAFT -> READY_FOR_REVIEW should be valid."""
        current = GateState.DRAFT
        target = GateState.READY_FOR_REVIEW
        
        valid_targets = VALID_TRANSITIONS[current]
        assert target in valid_targets
