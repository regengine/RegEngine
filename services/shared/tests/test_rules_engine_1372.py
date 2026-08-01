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


def test_batch_persist_evaluations_mid_batch_exception_salvages_rows() -> None:
    """First chunk succeeds, second fails → the failed chunk is salvaged
    row-by-row (#2695) instead of silently dropped (audit-trail gap)."""
    session = MagicMock()
    session.execute.side_effect = [
        None,  # first chunk INSERT (100 rows) succeeds
        RuntimeError("disk full"),  # second chunk INSERT (50 rows) fails
    ] + [None] * 50  # 50 row-level salvage INSERTs succeed

    engine = RulesEngine(session)
    results = [("event-x", _result(f"r{i}")) for i in range(150)]
    engine._batch_persist_evaluations("tenant-1", results)

    # 2 chunk savepoints + 50 row-salvage savepoints
    assert session.begin_nested.call_count == 52
    assert session.execute.call_count == 52
    # Only the failed chunk's savepoint rolled back (same mock instance).
    assert session.begin_nested.return_value.rollback.call_count == 1
    # Every salvage insert succeeded — no evaluation_error markers.
    assert not any("UPDATE fsma.traceability_events" in str(c.args[0]) for c in session.execute.call_args_list)


def test_batch_persist_evaluations_empty_is_noop() -> None:
    """Empty result list must not call begin_nested or execute."""
    session = MagicMock()

    engine = RulesEngine(session)
    engine._batch_persist_evaluations("tenant-1", [])

    session.begin_nested.assert_not_called()
    session.execute.assert_not_called()


def test_batch_persist_isolates_failures_per_chunk() -> None:
    """A chunk failure rolls back only that chunk; subsequent chunks still run.

    Two events each with 100 rows → 2 chunks.  First chunk fails (then is
    salvaged row-by-row, #2695), second chunk succeeds untouched.
    """
    session = MagicMock()
    session.execute.side_effect = (
        [
            RuntimeError("first chunk broke"),
        ]
        + [None] * 100
        + [None]
    )  # 100 row salvages, then chunk 2 INSERT

    engine = RulesEngine(session)
    # 100 rows for event-a → chunk 1, 100 rows for event-b → chunk 2
    results = [("event-a", _result(f"r{i}")) for i in range(100)] + [("event-b", _result(f"s{i}")) for i in range(100)]
    engine._batch_persist_evaluations("tenant-1", results)

    # chunk 1 + 100 row salvages + chunk 2
    assert session.begin_nested.call_count == 102
    assert session.begin_nested.return_value.rollback.call_count == 1

    execute_calls = session.execute.call_args_list
    assert len(execute_calls) == 102
    assert "INSERT INTO fsma.rule_evaluations" in str(execute_calls[0].args[0])
    # Salvage inserts carry single-row dict params for event-a.
    assert all(execute_calls[i].args[1]["event_id"] == "event-a" for i in range(1, 101))
    # Second chunk rows all belong to event-b
    assert all(row["event_id"] == "event-b" for row in execute_calls[101].args[1])


def test_batch_salvage_marks_still_failing_rows() -> None:
    """A row that fails even individually is marked via evaluation_error
    (#2695) — same operator-visible marker as the single-row path."""
    session = MagicMock()

    def _execute(stmt, params=None):
        sql = str(stmt)
        if "INSERT INTO fsma.rule_evaluations" in sql:
            if isinstance(params, list):
                raise RuntimeError("chunk broke")
            if params["rule_id"] == "r-poisoned":
                raise RuntimeError("row poisoned")
        return None

    session.execute.side_effect = _execute

    engine = RulesEngine(session)
    engine._batch_persist_evaluations(
        "tenant-1",
        [("event-a", _result("r-poisoned")), ("event-b", _result("r-fine"))],
    )

    marker_calls = [c for c in session.execute.call_args_list if "UPDATE fsma.traceability_events" in str(c.args[0])]
    assert len(marker_calls) == 1
    assert marker_calls[0].args[1]["event_id"] == "event-a"
    assert marker_calls[0].args[1]["error_message"] == "row poisoned"
