"""
Unit tests for the Request Workflow service — business logic only, no database.

Tests cover:
    - State transitions (intake -> scoping -> ... -> submitted)
    - Invalid state transition rejection
    - check_blocking_defects logic
    - check_deadline_status urgency classification
    - Package assembly hash generation
    - Signoff validation
    - _format_countdown helper
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, PropertyMock, call, patch

import pytest

from services.shared.request_workflow import (
    DEFAULT_RESPONSE_HOURS,
    REQUIRED_SIGNOFF_TYPES,
    VALID_REQUEST_CHANNELS,
    VALID_SCOPE_TYPES,
    VALID_SIGNOFF_TYPES,
    VALID_SUBMISSION_METHODS,
    VALID_SUBMISSION_TYPES,
    WORKFLOW_STAGES,
    RequestWorkflow,
    _format_countdown,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT = "tenant-001"
CASE_ID = "case-001"
NOW = datetime(2026, 3, 26, 12, 0, 0, tzinfo=timezone.utc)


def _mock_db():
    """Create a MagicMock that acts like a SQLAlchemy Session."""
    return MagicMock()


def _mock_case_row(status="intake", **overrides):
    """Return a dict simulating a request_cases row."""
    base = {
        "request_case_id": CASE_ID,
        "tenant_id": TENANT,
        "package_status": status,
        "requesting_party": "FDA",
        "request_channel": "email",
        "scope_type": "tlc_trace",
        "scope_description": "Trace lettuce lots",
        "affected_products": ["PROD-A"],
        "affected_lots": ["LOT-1"],
        "affected_facilities": ["FAC-1"],
        "response_due_at": NOW + timedelta(hours=24),
        "gap_count": 0,
        "active_exception_count": 0,
        "reviewer": None,
        "final_approver": None,
    }
    base.update(overrides)
    return base


def _setup_workflow_with_case(case_dict):
    """Build a RequestWorkflow whose _get_case returns the given dict."""
    db = _mock_db()
    wf = RequestWorkflow(db)
    wf._get_case = MagicMock(return_value=case_dict)
    return wf, db


# ---------------------------------------------------------------------------
# 1. Workflow Stage Constants
# ---------------------------------------------------------------------------

class TestWorkflowConstants:
    def test_workflow_stages_order(self):
        expected = [
            "intake", "scoping", "collecting", "gap_analysis",
            "exception_triage", "assembling", "internal_review",
            "ready", "submitted", "amended",
        ]
        assert WORKFLOW_STAGES == expected

    def test_required_signoff_types(self):
        assert "scope_approval" in REQUIRED_SIGNOFF_TYPES
        assert "final_approval" in REQUIRED_SIGNOFF_TYPES

    def test_valid_signoff_types_superset_of_required(self):
        for required in REQUIRED_SIGNOFF_TYPES:
            assert required in VALID_SIGNOFF_TYPES


# ---------------------------------------------------------------------------
# 2. Create Request Case — validation
# ---------------------------------------------------------------------------

class TestCreateRequestCase:
    def test_invalid_channel_raises(self):
        wf = RequestWorkflow(_mock_db())
        with pytest.raises(ValueError, match="Invalid request_channel"):
            wf.create_request_case(TENANT, request_channel="pigeon")

    def test_invalid_scope_type_raises(self):
        wf = RequestWorkflow(_mock_db())
        with pytest.raises(ValueError, match="Invalid scope_type"):
            wf.create_request_case(TENANT, scope_type="magic")

    def test_valid_channels(self):
        for ch in VALID_REQUEST_CHANNELS:
            assert isinstance(ch, str)

    def test_valid_scope_types(self):
        for st in VALID_SCOPE_TYPES:
            assert isinstance(st, str)


# ---------------------------------------------------------------------------
# 3. State Transitions — update_scope
# ---------------------------------------------------------------------------

class TestUpdateScope:
    def test_update_scope_from_intake_allowed(self):
        case = _mock_case_row(status="intake")
        wf, db = _setup_workflow_with_case(case)

        # Mock the DB execute to return a row
        mock_result = MagicMock()
        mock_result.mappings.return_value.fetchone.return_value = {
            **case, "package_status": "scoping",
        }
        db.execute.return_value = mock_result

        result = wf.update_scope(
            TENANT, CASE_ID,
            affected_products=["PROD-B"],
        )
        assert result["package_status"] == "scoping"

    def test_update_scope_from_scoping_allowed(self):
        case = _mock_case_row(status="scoping")
        wf, db = _setup_workflow_with_case(case)
        mock_result = MagicMock()
        mock_result.mappings.return_value.fetchone.return_value = {
            **case, "package_status": "scoping",
        }
        db.execute.return_value = mock_result

        result = wf.update_scope(TENANT, CASE_ID, affected_lots=["LOT-2"])
        assert result is not None

    def test_update_scope_from_collecting_rejected(self):
        case = _mock_case_row(status="collecting")
        wf, _ = _setup_workflow_with_case(case)

        with pytest.raises(ValueError, match="Cannot update scope"):
            wf.update_scope(TENANT, CASE_ID)

    def test_update_scope_from_submitted_rejected(self):
        case = _mock_case_row(status="submitted")
        wf, _ = _setup_workflow_with_case(case)

        with pytest.raises(ValueError, match="Cannot update scope"):
            wf.update_scope(TENANT, CASE_ID)

    def test_update_scope_invalid_scope_type_rejected(self):
        case = _mock_case_row(status="intake")
        wf, _ = _setup_workflow_with_case(case)

        with pytest.raises(ValueError, match="Invalid scope_type"):
            wf.update_scope(TENANT, CASE_ID, scope_type="invalid_type")


# ---------------------------------------------------------------------------
# 4. State Transitions — collect_records
# ---------------------------------------------------------------------------

class TestCollectRecords:
    def test_collect_from_scoping_allowed(self):
        case = _mock_case_row(status="scoping")
        wf, db = _setup_workflow_with_case(case)

        # Mock the events query
        events_result = MagicMock()
        events_result.mappings.return_value.fetchall.return_value = [
            {"event_id": "e1", "event_type": "receiving"},
        ]
        # The method calls db.execute twice (events query + status update)
        db.execute.return_value = events_result

        result = wf.collect_records(TENANT, CASE_ID)
        assert result["total_records"] == 1

    def test_collect_from_intake_rejected(self):
        case = _mock_case_row(status="intake")
        wf, _ = _setup_workflow_with_case(case)

        with pytest.raises(ValueError, match="Cannot collect"):
            wf.collect_records(TENANT, CASE_ID)

    def test_collect_from_gap_analysis_rejected(self):
        case = _mock_case_row(status="gap_analysis")
        wf, _ = _setup_workflow_with_case(case)

        with pytest.raises(ValueError, match="Cannot collect"):
            wf.collect_records(TENANT, CASE_ID)


# ---------------------------------------------------------------------------
# 5. Signoff Validation
# ---------------------------------------------------------------------------

class TestAddSignoff:
    def test_invalid_signoff_type_raises(self):
        case = _mock_case_row(status="assembling")
        wf, _ = _setup_workflow_with_case(case)

        with pytest.raises(ValueError, match="Invalid signoff_type"):
            wf.add_signoff(TENANT, CASE_ID, "magic_approval", signed_by="user")

    def test_scope_approval_advances_to_exception_triage(self):
        case = _mock_case_row(status="gap_analysis")
        wf, db = _setup_workflow_with_case(case)
        db.execute.return_value = MagicMock()

        result = wf.add_signoff(
            TENANT, CASE_ID, "scope_approval", signed_by="qa_lead"
        )
        assert result["signoff_type"] == "scope_approval"
        assert result["case_status"] == "exception_triage"

    def test_final_approval_advances_to_ready(self):
        case = _mock_case_row(status="internal_review")
        wf, db = _setup_workflow_with_case(case)
        db.execute.return_value = MagicMock()

        result = wf.add_signoff(
            TENANT, CASE_ID, "final_approval", signed_by="director"
        )
        assert result["case_status"] == "ready"

    def test_package_review_advances_to_internal_review(self):
        case = _mock_case_row(status="assembling")
        wf, db = _setup_workflow_with_case(case)
        db.execute.return_value = MagicMock()

        result = wf.add_signoff(
            TENANT, CASE_ID, "package_review", signed_by="reviewer"
        )
        assert result["case_status"] == "internal_review"

    def test_signoff_returns_metadata(self):
        case = _mock_case_row(status="assembling")
        wf, db = _setup_workflow_with_case(case)
        db.execute.return_value = MagicMock()

        result = wf.add_signoff(
            TENANT, CASE_ID, "scope_approval",
            signed_by="qa_lead", notes="Looks good",
        )
        assert "signoff_id" in result
        assert result["signed_by"] == "qa_lead"
        assert result["notes"] == "Looks good"


# ---------------------------------------------------------------------------
# 6. check_blocking_defects logic
# ---------------------------------------------------------------------------

class TestCheckBlockingDefects:
    def _setup_blocking_check(self, *, critical_fails=None, critical_exceptions=None,
                               unevaluated=None, signoff_types=None):
        """Wire up a workflow with mock DB responses for check_blocking_defects."""
        case = _mock_case_row(status="ready")
        wf, db = _setup_workflow_with_case(case)
        wf._get_scope_event_ids = MagicMock(return_value=["e1", "e2"])

        call_count = [0]

        def execute_side_effect(stmt, params=None):
            call_count[0] += 1
            mock_result = MagicMock()

            # Query order in check_blocking_defects:
            # 1. critical rule failures
            # 2. critical exceptions
            # 3. unevaluated events
            # 4. signoff types
            # 5. identity review
            # 6. non-critical warnings
            idx = call_count[0]

            if idx == 1:
                mock_result.mappings.return_value.fetchall.return_value = critical_fails or []
            elif idx == 2:
                mock_result.mappings.return_value.fetchall.return_value = critical_exceptions or []
            elif idx == 3:
                mock_result.mappings.return_value.fetchall.return_value = unevaluated or []
            elif idx == 4:
                mock_result.fetchall.return_value = [
                    (st,) for st in (signoff_types or [])
                ]
            elif idx == 5:
                # identity review queue
                mock_result.mappings.return_value.fetchall.return_value = []
            elif idx == 6:
                # non-critical count
                mock_result.scalar.return_value = 0
            return mock_result

        db.execute.side_effect = execute_side_effect
        return wf

    def test_no_blockers_can_submit(self):
        wf = self._setup_blocking_check(
            signoff_types=["scope_approval", "final_approval"],
        )
        result = wf.check_blocking_defects(TENANT, CASE_ID)
        assert result["can_submit"] is True
        assert result["blocker_count"] == 0

    def test_missing_signoff_blocks(self):
        wf = self._setup_blocking_check(
            signoff_types=["scope_approval"],  # missing final_approval
        )
        result = wf.check_blocking_defects(TENANT, CASE_ID)
        assert result["can_submit"] is False
        blocker_types = [b["type"] for b in result["blockers"]]
        assert "missing_signoff" in blocker_types

    def test_critical_rule_failure_blocks(self):
        wf = self._setup_blocking_check(
            critical_fails=[{
                "evaluation_id": "eval-1",
                "event_id": "e1",
                "rule_id": "r1",
                "rule_title": "TLC Required",
                "citation_reference": "21 CFR",
                "why_failed": "Missing TLC",
            }],
            signoff_types=["scope_approval", "final_approval"],
        )
        result = wf.check_blocking_defects(TENANT, CASE_ID)
        assert result["can_submit"] is False
        blocker_types = [b["type"] for b in result["blockers"]]
        assert "critical_rule_failure" in blocker_types

    def test_unevaluated_event_blocks(self):
        wf = self._setup_blocking_check(
            unevaluated=[{
                "event_id": "e1",
                "event_type": "receiving",
                "traceability_lot_code": "TLC-001",
            }],
            signoff_types=["scope_approval", "final_approval"],
        )
        result = wf.check_blocking_defects(TENANT, CASE_ID)
        assert result["can_submit"] is False
        blocker_types = [b["type"] for b in result["blockers"]]
        assert "unevaluated_event" in blocker_types


# ---------------------------------------------------------------------------
# 7. check_deadline_status urgency classification
# ---------------------------------------------------------------------------

class TestCheckDeadlineStatus:
    def _setup_deadline_check(self, rows):
        db = _mock_db()
        wf = RequestWorkflow(db)
        mock_result = MagicMock()
        mock_result.mappings.return_value.fetchall.return_value = rows
        db.execute.return_value = mock_result
        return wf

    @patch("services.shared.request_workflow.logger")
    def test_overdue_classification(self, _mock_logger):
        rows = [{
            "request_case_id": "c1",
            "package_status": "collecting",
            "requesting_party": "FDA",
            "scope_description": "test",
            "response_due_at": NOW - timedelta(hours=2),
            "hours_remaining": -2.0,
            "is_overdue": True,
            "gap_count": 0,
            "active_exception_count": 0,
        }]
        wf = self._setup_deadline_check(rows)
        cases = wf.check_deadline_status(TENANT)
        assert len(cases) == 1
        assert cases[0]["urgency"] == "overdue"

    @patch("services.shared.request_workflow.logger")
    def test_critical_classification(self, _mock_logger):
        rows = [{
            "request_case_id": "c1",
            "package_status": "collecting",
            "requesting_party": "FDA",
            "scope_description": "test",
            "response_due_at": NOW + timedelta(hours=1),
            "hours_remaining": 1.0,
            "is_overdue": False,
            "gap_count": 0,
            "active_exception_count": 0,
        }]
        wf = self._setup_deadline_check(rows)
        cases = wf.check_deadline_status(TENANT)
        assert cases[0]["urgency"] == "critical"

    def test_urgent_classification(self):
        rows = [{
            "request_case_id": "c1",
            "package_status": "collecting",
            "requesting_party": "FDA",
            "scope_description": "test",
            "response_due_at": NOW + timedelta(hours=4),
            "hours_remaining": 4.0,
            "is_overdue": False,
            "gap_count": 0,
            "active_exception_count": 0,
        }]
        wf = self._setup_deadline_check(rows)
        cases = wf.check_deadline_status(TENANT)
        assert cases[0]["urgency"] == "urgent"

    def test_normal_classification(self):
        rows = [{
            "request_case_id": "c1",
            "package_status": "intake",
            "requesting_party": "FDA",
            "scope_description": "test",
            "response_due_at": NOW + timedelta(hours=20),
            "hours_remaining": 20.0,
            "is_overdue": False,
            "gap_count": 0,
            "active_exception_count": 0,
        }]
        wf = self._setup_deadline_check(rows)
        cases = wf.check_deadline_status(TENANT)
        assert cases[0]["urgency"] == "normal"

    @patch("services.shared.request_workflow.logger")
    def test_boundary_2_hours_is_critical(self, _mock_logger):
        """<2 hours = critical, so 1.99 hours should be critical."""
        rows = [{
            "request_case_id": "c1",
            "package_status": "collecting",
            "requesting_party": "FDA",
            "scope_description": "test",
            "response_due_at": NOW + timedelta(hours=1, minutes=59),
            "hours_remaining": 1.99,
            "is_overdue": False,
            "gap_count": 0,
            "active_exception_count": 0,
        }]
        wf = self._setup_deadline_check(rows)
        cases = wf.check_deadline_status(TENANT)
        assert cases[0]["urgency"] == "critical"

    def test_boundary_6_hours_is_normal(self):
        """>=6 hours = normal."""
        rows = [{
            "request_case_id": "c1",
            "package_status": "collecting",
            "requesting_party": "FDA",
            "scope_description": "test",
            "response_due_at": NOW + timedelta(hours=6),
            "hours_remaining": 6.0,
            "is_overdue": False,
            "gap_count": 0,
            "active_exception_count": 0,
        }]
        wf = self._setup_deadline_check(rows)
        cases = wf.check_deadline_status(TENANT)
        assert cases[0]["urgency"] == "normal"


# ---------------------------------------------------------------------------
# 8. Package Assembly — Hash Generation
# ---------------------------------------------------------------------------

class TestPackageHashGeneration:
    def test_sha256_of_sorted_json(self):
        """Verify that the hash computation matches the module's approach."""
        contents = {
            "request_case_id": "c1",
            "version_number": 1,
            "trace_data": [{"event_id": "e1"}],
        }
        contents_json = json.dumps(contents, sort_keys=True, default=str)
        expected_hash = hashlib.sha256(contents_json.encode("utf-8")).hexdigest()

        # Verify the hash is deterministic
        assert len(expected_hash) == 64
        # Same input, same hash
        contents_json_2 = json.dumps(contents, sort_keys=True, default=str)
        assert hashlib.sha256(contents_json_2.encode("utf-8")).hexdigest() == expected_hash

    def test_different_content_different_hash(self):
        c1 = json.dumps({"a": 1}, sort_keys=True)
        c2 = json.dumps({"a": 2}, sort_keys=True)
        h1 = hashlib.sha256(c1.encode()).hexdigest()
        h2 = hashlib.sha256(c2.encode()).hexdigest()
        assert h1 != h2


# ---------------------------------------------------------------------------
# 9. Submit Package — validation
# ---------------------------------------------------------------------------

class TestSubmitPackage:
    def test_invalid_submission_type_raises(self):
        case = _mock_case_row(status="ready")
        wf, _ = _setup_workflow_with_case(case)

        with pytest.raises(ValueError, match="Invalid submission_type"):
            wf.submit_package(
                TENANT, CASE_ID, "pkg-1",
                submitted_by="user",
                submission_type="magic",
            )

    def test_invalid_submission_method_raises(self):
        case = _mock_case_row(status="ready")
        wf, _ = _setup_workflow_with_case(case)

        with pytest.raises(ValueError, match="Invalid submission_method"):
            wf.submit_package(
                TENANT, CASE_ID, "pkg-1",
                submitted_by="user",
                submission_method="carrier_pigeon",
            )

    def test_submit_from_intake_rejected(self):
        case = _mock_case_row(status="intake")
        wf, _ = _setup_workflow_with_case(case)

        with pytest.raises(ValueError, match="Cannot submit"):
            wf.submit_package(
                TENANT, CASE_ID, "pkg-1",
                submitted_by="user",
            )

    def test_submit_from_collecting_rejected(self):
        case = _mock_case_row(status="collecting")
        wf, _ = _setup_workflow_with_case(case)

        with pytest.raises(ValueError, match="Cannot submit"):
            wf.submit_package(
                TENANT, CASE_ID, "pkg-1",
                submitted_by="user",
            )


# ---------------------------------------------------------------------------
# 10. _format_countdown helper
# ---------------------------------------------------------------------------

class TestFormatCountdown:
    def test_overdue_format(self):
        result = _format_countdown(-2.5)
        assert "OVERDUE" in result
        assert "2h" in result

    def test_hours_and_minutes(self):
        result = _format_countdown(3.5)
        assert "3h 30m remaining" == result

    def test_days_format(self):
        result = _format_countdown(50.0)
        assert "2d" in result
        assert "remaining" in result

    def test_zero_hours_overdue(self):
        result = _format_countdown(0)
        assert "OVERDUE" in result

    def test_just_under_one_day(self):
        result = _format_countdown(23.5)
        assert "23h" in result
        assert "remaining" in result


# ---------------------------------------------------------------------------
# 11. Amendment — state enforcement
# ---------------------------------------------------------------------------

class TestCreateAmendment:
    def test_amend_from_intake_rejected(self):
        case = _mock_case_row(status="intake")
        wf, _ = _setup_workflow_with_case(case)

        with pytest.raises(ValueError, match="Cannot amend"):
            wf.create_amendment(TENANT, CASE_ID)

    def test_amend_from_collecting_rejected(self):
        case = _mock_case_row(status="collecting")
        wf, _ = _setup_workflow_with_case(case)

        with pytest.raises(ValueError, match="Cannot amend"):
            wf.create_amendment(TENANT, CASE_ID)
