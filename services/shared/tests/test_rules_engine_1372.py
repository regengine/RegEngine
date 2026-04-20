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


def test_batch_persist_evaluations_150_rows_uses_2_inserts() -> None:
    """150 results should produce exactly 2 INSERT calls (chunks of 100)."""
    session = MagicMock()
    savepoint = MagicMock()
    session.begin_nested.return_value = savepoint

    engine = RulesEngine(session)
    results = [("event-x", _result(f"r{i}")) for i in range(150)]
    engine._batch_persist_evaluations("tenant-1", results)

    # One savepoint and one execute per chunk.
    assert session.begin_nested.call_count == 2
    assert session.execute.call_count == 2

    # First chunk: rows 0-99 (100 rows)
    first_params = session.execute.call_args_list[0].args[1]
    assert len(first_params) == 100

    # Second chunk: rows 100-149 (50 rows)
    second_params = session.execute.call_args_list[1].args[1]
    assert len(second_params) == 50

    savepoint.rollback.assert_not_called()


def test_batch_persist_evaluations_mid_batch_exception_isolates_chunk() -> None:
    """First chunk succeeds, second fails → first committed, second logged, no partial second batch."""
    session = MagicMock()
    savepoint_1 = MagicMock()
    savepoint_2 = MagicMock()
    session.begin_nested.side_effect = [savepoint_1, savepoint_2]
    session.execute.side_effect = [
        None,                        # first chunk INSERT succeeds
        RuntimeError("disk full"),   # second chunk INSERT fails
    ]

    engine = RulesEngine(session)
    results = [("event-x", _result(f"r{i}")) for i in range(150)]
    engine._batch_persist_evaluations("tenant-1", results)

    assert session.begin_nested.call_count == 2
    savepoint_1.rollback.assert_not_called()
    savepoint_2.rollback.assert_called_once()
    # Only 2 execute calls — no partial row from the failed chunk.
    assert session.execute.call_count == 2


def test_batch_persist_evaluations_empty_is_noop() -> None:
    """Empty result list must not call begin_nested or execute."""
    session = MagicMock()

    engine = RulesEngine(session)
    engine._batch_persist_evaluations("tenant-1", [])

    session.begin_nested.assert_not_called()
    session.execute.assert_not_called()


def test_batch_persist_isolates_failures_per_chunk() -> None:
    """A chunk failure rolls back only that chunk; subsequent chunks still run.

    Two events each with 100 rows → 2 chunks.  First chunk fails, second
    succeeds.  Each chunk gets its own savepoint; only the first is rolled back.
    """
    session = MagicMock()
    savepoint_1 = MagicMock()
    savepoint_2 = MagicMock()
    session.begin_nested.side_effect = [savepoint_1, savepoint_2]
    session.execute.side_effect = [
        RuntimeError("first chunk broke"),
        None,  # second chunk INSERT succeeds
    ]

    engine = RulesEngine(session)
    # 100 rows for event-a → chunk 1, 100 rows for event-b → chunk 2
    results = (
        [("event-a", _result(f"r{i}")) for i in range(100)]
        + [("event-b", _result(f"s{i}")) for i in range(100)]
    )
    engine._batch_persist_evaluations("tenant-1", results)

    assert session.begin_nested.call_count == 2
    savepoint_1.rollback.assert_called_once()
    savepoint_2.rollback.assert_not_called()

    execute_calls = session.execute.call_args_list
    assert len(execute_calls) == 2
    assert "INSERT INTO fsma.rule_evaluations" in str(execute_calls[0].args[0])
    assert "INSERT INTO fsma.rule_evaluations" in str(execute_calls[1].args[0])
    # Second chunk rows all belong to event-b
    assert all(row["event_id"] == "event-b" for row in execute_calls[1].args[1])
