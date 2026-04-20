"""Regression tests for rules persistence hardening (#1372)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, call

_SHARED_DIR = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SHARED_DIR.parent
for _p in (_SHARED_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.rules.engine import RulesEngine  # noqa: E402
from shared.rules.types import RuleEvaluationResult  # noqa: E402


def _result(rule_id: str, *, outcome: str = "pass") -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_id=rule_id,
        rule_version=1,
        rule_title=f"Rule {rule_id}",
        severity="warning",
        result=outcome,
        evidence_fields_inspected=[{"field": rule_id}],
        confidence=0.9,
        category="kde_presence",
    )


def test_persist_evaluations_uses_single_executemany_insert() -> None:
    """One event should be persisted with one executemany-style call."""
    session = MagicMock()
    savepoint = MagicMock()
    session.begin_nested.return_value = savepoint

    engine = RulesEngine(session)
    engine._persist_evaluations("tenant-1", "event-1", [_result("r1"), _result("r2")])

    session.begin_nested.assert_called_once()
    assert session.execute.call_count == 1
    insert_stmt, insert_params = session.execute.call_args.args
    assert "INSERT INTO fsma.rule_evaluations" in str(insert_stmt)
    assert isinstance(insert_params, list)
    assert len(insert_params) == 2
    assert {row["rule_id"] for row in insert_params} == {"r1", "r2"}
    savepoint.rollback.assert_not_called()


def test_persist_evaluations_rolls_back_savepoint_and_marks_event_on_error() -> None:
    """A failed insert should roll back the savepoint and mark the event."""
    session = MagicMock()
    savepoint = MagicMock()
    session.begin_nested.return_value = savepoint
    session.execute.side_effect = [RuntimeError("db write failed"), None]

    engine = RulesEngine(session)
    engine._persist_evaluations("tenant-1", "event-1", [_result("r1")])

    savepoint.rollback.assert_called_once()
    assert session.execute.call_count == 2
    marker_stmt, marker_params = session.execute.call_args_list[1].args
    assert "UPDATE fsma.traceability_events" in str(marker_stmt)
    assert marker_params["tenant_id"] == "tenant-1"
    assert marker_params["event_id"] == "event-1"
    assert marker_params["error_message"] == "db write failed"


def test_batch_persist_isolates_failures_per_event() -> None:
    """One event's persistence failure must not abort later events."""
    session = MagicMock()
    savepoint_a = MagicMock()
    savepoint_b = MagicMock()
    session.begin_nested.side_effect = [savepoint_a, savepoint_b]
    session.execute.side_effect = [
        RuntimeError("first event broke"),
        None,  # marker update for event-a
        None,  # successful insert for event-b
    ]

    engine = RulesEngine(session)
    engine._batch_persist_evaluations(
        "tenant-1",
        [
            ("event-a", _result("r1")),
            ("event-b", _result("r2")),
        ],
    )

    assert session.begin_nested.call_count == 2
    savepoint_a.rollback.assert_called_once()
    savepoint_b.rollback.assert_not_called()

    execute_calls = session.execute.call_args_list
    assert len(execute_calls) == 3
    assert "UPDATE fsma.traceability_events" in str(execute_calls[1].args[0])
    assert "INSERT INTO fsma.rule_evaluations" in str(execute_calls[2].args[0])
    assert execute_calls[2].args[1][0]["event_id"] == "event-b"
