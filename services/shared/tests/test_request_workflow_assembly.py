"""Focused unit tests for services/shared/request_workflow/assembly.py.

Covers the AssemblyMixin public behavior with a mocked database session:
manifest hashing, signoff handling, package assembly guards and snapshot
shape, blocking defect checks, and deadline urgency classification.

No database, no network. Follows the mocking style of
tests/test_request_workflow_unit.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.shared.request_workflow import RequestWorkflow
from services.shared.request_workflow.assembly import compute_manifest_hash

TENANT = "tenant-assembly-001"
CASE_ID = "case-assembly-001"
NOW = datetime(2026, 3, 26, 12, 0, 0, tzinfo=timezone.utc)


def _mock_case_row(status="gap_analysis", **overrides):
    base = {
        "request_case_id": CASE_ID,
        "tenant_id": TENANT,
        "package_status": status,
        "requesting_party": "FDA",
        "scope_type": "tlc_trace",
        "scope_description": "Trace lettuce lots",
        "affected_products": ["PROD-A"],
        "affected_lots": ["LOT-1"],
        "affected_facilities": ["FAC-1"],
    }
    base.update(overrides)
    return base


def _workflow_with_case(case_dict):
    db = MagicMock()
    wf = RequestWorkflow(db)
    wf._get_case = MagicMock(return_value=case_dict)
    return wf, db


class _Result:
    """Minimal stand-in for a SQLAlchemy execute result."""

    def __init__(self, *, scalar_value=None, rows=None, row=None):
        self._scalar_value = scalar_value
        self._rows = rows if rows is not None else []
        self._row = row

    def scalar(self):
        return self._scalar_value

    def mappings(self):
        return self

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


# ---------------------------------------------------------------------------
# compute_manifest_hash
# ---------------------------------------------------------------------------


class TestComputeManifestHash:
    def test_deterministic_64_char_hex(self):
        contents = {"request_case_id": "c1", "version_number": 1, "trace_data": [{"event_id": "e1"}]}
        first = compute_manifest_hash(contents)
        assert len(first) == 64
        assert compute_manifest_hash(contents) == first

    def test_ignores_embedded_package_hash(self):
        contents = {"request_case_id": "c1", "version_number": 1}
        clean = compute_manifest_hash(contents)
        assert compute_manifest_hash({**contents, "package_hash": "0" * 64}) == clean

    def test_content_change_moves_digest(self):
        contents = {"request_case_id": "c1", "trace_data": [{"event_id": "e1"}]}
        original = compute_manifest_hash(contents)
        tampered = {"request_case_id": "c1", "trace_data": [{"event_id": "e2"}]}
        assert compute_manifest_hash(tampered) != original

    def test_key_order_does_not_move_digest(self):
        first = {"a": 1, "b": [1, 2], "c": {"x": "y"}}
        second = {"c": {"x": "y"}, "b": [1, 2], "a": 1}
        assert compute_manifest_hash(first) == compute_manifest_hash(second)


# ---------------------------------------------------------------------------
# add_signoff
# ---------------------------------------------------------------------------


class TestAddSignoff:
    def test_invalid_signoff_type_raises(self):
        wf, _ = _workflow_with_case(_mock_case_row())
        with pytest.raises(ValueError, match="Invalid signoff_type"):
            wf.add_signoff(TENANT, CASE_ID, "not_a_signoff", signed_by="qa_lead")

    def test_submission_authorization_reaches_ready_without_owner_fields(self):
        wf, db = _workflow_with_case(_mock_case_row(status="ready"))
        db.execute.return_value = MagicMock()
        result = wf.add_signoff(TENANT, CASE_ID, "submission_authorization", signed_by="director")
        assert result["case_status"] == "ready"
        update_params = db.execute.call_args_list[1][0][1]
        assert update_params["new_status"] == "ready"
        assert "reviewer" not in update_params
        assert "approver" not in update_params

    def test_package_review_records_reviewer(self):
        wf, db = _workflow_with_case(_mock_case_row(status="assembling"))
        db.execute.return_value = MagicMock()
        result = wf.add_signoff(TENANT, CASE_ID, "package_review", signed_by="reviewer")
        assert result["case_status"] == "internal_review"
        update_params = db.execute.call_args_list[1][0][1]
        assert update_params["reviewer"] == "reviewer"


# ---------------------------------------------------------------------------
# assemble_response_package
# ---------------------------------------------------------------------------


class TestAssembleResponsePackage:
    def _wire_empty_scope(self, wf, db, captured):
        def execute_side_effect(stmt, params=None):
            sql = str(stmt)
            if "MAX(version_number)" in sql:
                return _Result(scalar_value=0)
            if "INSERT INTO fsma.response_packages" in sql:
                captured.update(params or {})
                return _Result(row={"package_id": "pkg-1", "version_number": 1})
            return _Result(rows=[])

        db.execute.side_effect = execute_side_effect
        wf._get_scope_event_ids = MagicMock(return_value=[])
        wf._compute_gap_snapshot = MagicMock(
            return_value={
                "missing_events": [],
                "failed_rules": [],
                "unresolved_exceptions": [],
                "gap_owners": {},
            }
        )

    def test_wrong_status_raises(self):
        wf, db = _workflow_with_case(_mock_case_row(status="submitted"))
        with pytest.raises(ValueError, match="Cannot assemble"):
            wf.assemble_response_package(TENANT, CASE_ID)
        db.execute.assert_not_called()

    def test_first_version_snapshot_is_self_verifiable(self):
        wf, db = _workflow_with_case(_mock_case_row(status="gap_analysis"))
        captured = {}
        self._wire_empty_scope(wf, db, captured)

        result = wf.assemble_response_package(TENANT, CASE_ID, generated_by="qa_lead")

        assert result["package_id"] == "pkg-1"
        contents = json.loads(captured["contents"])
        assert contents["version_number"] == 1
        assert contents["manifest_version"] == "1.0"
        assert contents["generated_by"] == "qa_lead"
        assert contents["summary"] == {
            "total_events": 0,
            "total_rule_evaluations": 0,
            "failed_evaluations": 0,
            "warned_evaluations": 0,
            "total_exceptions": 0,
            "open_exceptions": 0,
        }
        stored_hash = contents.pop("package_hash")
        assert compute_manifest_hash(contents) == stored_hash


# ---------------------------------------------------------------------------
# check_blocking_defects
# ---------------------------------------------------------------------------


class TestCheckBlockingDefects:
    def _setup(
        self,
        *,
        critical_fails=None,
        critical_exceptions=None,
        unevaluated=None,
        signoff_types=None,
        stale=None,
        warn_count=0,
    ):
        wf, db = _workflow_with_case(_mock_case_row(status="ready"))
        wf._get_scope_event_ids = MagicMock(return_value=["e1", "e2"])
        calls = [0]

        def execute_side_effect(stmt, params=None):
            calls[0] += 1
            idx = calls[0]
            if idx == 1:
                return _Result(rows=critical_fails or [])
            if idx == 2:
                return _Result(rows=critical_exceptions or [])
            if idx == 3:
                return _Result(rows=unevaluated or [])
            if idx == 4:
                fake = MagicMock()
                fake.fetchall.return_value = [(st,) for st in (signoff_types or [])]
                return fake
            if idx == 5:
                return _Result(rows=[])
            if idx == 6:
                return _Result(rows=stale or [])
            return _Result(scalar_value=warn_count)

        db.execute.side_effect = execute_side_effect
        return wf

    def test_missing_signoff_blocks(self):
        wf = self._setup(signoff_types=["scope_approval"])
        result = wf.check_blocking_defects(TENANT, CASE_ID)
        assert result["can_submit"] is False
        assert "missing_signoff" in [b["type"] for b in result["blockers"]]

    def test_unresolved_critical_exception_blocks(self):
        wf = self._setup(
            signoff_types=["scope_approval", "final_approval"],
            critical_exceptions=[
                {
                    "case_id": "exc-1",
                    "severity": "critical",
                    "source_supplier": "Supplier A",
                    "rule_category": "traceability",
                    "recommended_remediation": "fix",
                }
            ],
        )
        result = wf.check_blocking_defects(TENANT, CASE_ID)
        assert result["can_submit"] is False
        assert "unresolved_critical_exception" in [b["type"] for b in result["blockers"]]

    def test_non_critical_warnings_do_not_block(self):
        wf = self._setup(
            signoff_types=["scope_approval", "final_approval"],
            warn_count=3,
        )
        result = wf.check_blocking_defects(TENANT, CASE_ID)
        assert result["can_submit"] is True
        assert result["warning_count"] == 1
        assert result["warnings"][0]["count"] == 3


# ---------------------------------------------------------------------------
# check_deadline_status
# ---------------------------------------------------------------------------


class TestCheckDeadlineStatus:
    def _setup(self, rows):
        db = MagicMock()
        wf = RequestWorkflow(db)
        db.execute.return_value = _Result(rows=rows)
        return wf, db

    def _row(self, case_id, hours, overdue):
        return {
            "request_case_id": case_id,
            "package_status": "collecting",
            "requesting_party": "FDA",
            "scope_description": "test",
            "response_due_at": NOW + timedelta(hours=hours),
            "hours_remaining": hours,
            "is_overdue": overdue,
            "gap_count": 0,
            "active_exception_count": 0,
        }

    def test_urgency_mapping(self):
        wf, _ = self._setup(
            [
                self._row("c-overdue", -2.0, True),
                self._row("c-critical", 1.0, False),
                self._row("c-urgent", 4.0, False),
                self._row("c-normal", 20.0, False),
            ]
        )
        cases = wf.check_deadline_status(TENANT)
        assert [c["urgency"] for c in cases] == ["overdue", "critical", "urgent", "normal"]

    def test_overdue_flag_wins_over_positive_hours(self):
        wf, _ = self._setup([self._row("c1", 5.0, True)])
        cases = wf.check_deadline_status(TENANT)
        assert cases[0]["urgency"] == "overdue"

    def test_custom_limit_forwarded_to_query(self):
        wf, db = self._setup([self._row("c1", 20.0, False)])
        wf.check_deadline_status(TENANT, limit=7)
        _, params = db.execute.call_args_list[0][0]
        assert params["limit"] == 7

    @patch("services.shared.request_workflow.assembly.logger")
    def test_truncation_at_limit_logs_error(self, mock_logger):
        wf, _ = self._setup([self._row("c1", 1.0, False), self._row("c2", 20.0, False)])
        cases = wf.check_deadline_status(TENANT, limit=2)
        assert len(cases) == 2
        mock_logger.error.assert_called_once()
        assert mock_logger.error.call_args[0][0] == "deadline_status_truncated"
