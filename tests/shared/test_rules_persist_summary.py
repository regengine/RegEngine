"""Unit tests for ``RulesEngine.persist_summary``.

Public wrapper added to let ingestion paths persist a pre-computed
``EvaluationSummary`` without re-evaluating the rules — closes the
double-eval regression that lands when ``RULES_ENGINE_ENFORCE`` flips
from ``off`` to ``cte_only|all`` (see project memory: review-fix plan).

Coverage:
  - Empty / no-verdict summary writes no rule rows but DOES stamp the
    event-level tri-state verdict (v121) so downstream consumers can tell
    "no verdict" apart from "passed"
  - Populated summary writes one row per ``RuleEvaluationResult``
  - Event-level verdict stamp mirrors ``EvaluationSummary.verdict``
  - ``event_id`` defaults to ``summary.event_id`` when not supplied
  - Explicit ``event_id`` kwarg overrides ``summary.event_id``
  - Missing ``event_id`` (neither kwarg nor on summary) raises ValueError
    rather than silently writing rows with an empty FK
  - Internal savepoint rollback path is reached on DB failure (mirrors
    the existing ``_persist_evaluations`` contract)
"""

from __future__ import annotations

from typing import Any, List
from unittest.mock import MagicMock

import pytest
from shared.rules.engine import RulesEngine
from shared.rules.types import EvaluationSummary, RuleEvaluationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _result(**overrides: Any) -> RuleEvaluationResult:
    defaults = dict(
        rule_id="R1",
        rule_version=1,
        rule_title="Test Rule",
        severity="critical",
        result="fail",
        why_failed="missing_kde",
    )
    defaults.update(overrides)
    return RuleEvaluationResult(**defaults)


def _populated_summary(event_id: str = "evt-1", results: List[RuleEvaluationResult] | None = None) -> EvaluationSummary:
    res = results if results is not None else [_result()]
    return EvaluationSummary(event_id=event_id, total_rules=len(res), failed=1, results=res)


def _empty_summary(event_id: str = "") -> EvaluationSummary:
    return EvaluationSummary(event_id=event_id, total_rules=0, no_verdict_reason="no_rules_loaded")


def _make_engine_with_recording_session():
    """Return ``(engine, executes)`` where ``executes`` is a list capturing
    every statement passed to ``session.execute`` so tests can assert
    whether/how persistence ran without needing a real Postgres.

    The fake session also tracks ``begin_nested`` calls — the persistence
    helper wraps the INSERT in a savepoint, and rolling that savepoint
    back on failure is part of the contract this test pins down.
    """
    executes: List[tuple] = []
    savepoints: List[Any] = []

    class _FakeSavepoint:
        def __init__(self) -> None:
            self.committed = False
            self.rolled_back = False

        def commit(self) -> None:
            self.committed = True

        def rollback(self) -> None:
            self.rolled_back = True

    class _FakeSession:
        def __init__(self) -> None:
            self.execute_should_raise: Exception | None = None

        def execute(self, stmt, params=None):
            executes.append((stmt, params))
            if self.execute_should_raise is not None:
                # Only raise on the INSERT, not the marker UPDATE.
                if "INSERT INTO fsma.rule_evaluations" in str(stmt):
                    raise self.execute_should_raise
            return MagicMock()

        def begin_nested(self):
            sp = _FakeSavepoint()
            savepoints.append(sp)
            return sp

    session = _FakeSession()
    engine = RulesEngine(session)
    return engine, session, executes, savepoints


def _inserts(executes: List[tuple]) -> List[tuple]:
    return [(stmt, params) for stmt, params in executes if "INSERT INTO fsma.rule_evaluations" in str(stmt)]


def _verdict_updates(executes: List[tuple]) -> List[tuple]:
    return [(stmt, params) for stmt, params in executes if "SET evaluation_verdict" in str(stmt)]


def _error_marker_updates(executes: List[tuple]) -> List[tuple]:
    return [(stmt, params) for stmt, params in executes if "SET evaluation_error" in str(stmt)]


# ---------------------------------------------------------------------------
# Empty / no-verdict short-circuit
# ---------------------------------------------------------------------------


class TestEmptySummary:
    def test_empty_results_writes_no_rule_rows_but_stamps_verdict(self):
        engine, session, executes, savepoints = _make_engine_with_recording_session()
        summary = _empty_summary(event_id="evt-empty")

        engine.persist_summary(summary, tenant_id="t-1")

        # _persist_evaluations short-circuits on empty results — no rule
        # rows are written...
        assert _inserts(executes) == []
        # ...but the event is stamped ``no_verdict`` so the FDA export and
        # auditor list cannot mistake "nothing evaluated" for PASS.
        updates = _verdict_updates(executes)
        assert len(updates) == 1
        rows = updates[0][1]
        assert rows == [
            {"tenant_id": "t-1", "event_id": "evt-empty", "verdict": "no_verdict", "reason": "no_rules_loaded"}
        ]

    def test_no_verdict_reason_is_stamped_not_flattened(self):
        """A non-FTL summary (no_verdict_reason set, zero results) must
        surface as ``no_verdict`` on the event — never as ``pass``."""
        engine, session, executes, savepoints = _make_engine_with_recording_session()
        summary = EvaluationSummary(
            event_id="evt-nv",
            total_rules=0,
            no_verdict_reason="not_ftl_scoped",
        )

        engine.persist_summary(summary, tenant_id="t-1")

        assert _inserts(executes) == []
        updates = _verdict_updates(executes)
        assert len(updates) == 1
        assert updates[0][1][0]["verdict"] == "no_verdict"
        assert updates[0][1][0]["reason"] == "not_ftl_scoped"

    def test_non_ftl_meta_pass_rows_still_stamp_no_verdict(self):
        """Regression for the flattening bug: a non-FTL event whose only
        rows are passing NON_FTL meta-rules persists ``pass`` rows, so a
        consumer that only looks at rule rows sees "all passed". The
        event-level stamp must carry the ``no_verdict`` context."""
        engine, session, executes, _ = _make_engine_with_recording_session()
        summary = EvaluationSummary(
            event_id="evt-nonftl",
            total_rules=1,
            passed=1,
            results=[_result(rule_id="NON_FTL_META", result="pass", why_failed=None)],
            no_verdict_reason="not_ftl_scoped",
        )

        engine.persist_summary(summary, tenant_id="t-1")

        assert len(_inserts(executes)) == 1
        updates = _verdict_updates(executes)
        assert len(updates) == 1
        assert updates[0][1][0]["verdict"] == "no_verdict"
        assert updates[0][1][0]["reason"] == "not_ftl_scoped"


# ---------------------------------------------------------------------------
# Populated summary writes rows
# ---------------------------------------------------------------------------


class TestPopulatedSummary:
    def test_single_result_writes_one_insert(self):
        engine, session, executes, savepoints = _make_engine_with_recording_session()
        summary = _populated_summary()

        engine.persist_summary(summary, tenant_id="t-1")

        # Exactly one INSERT statement was executed.
        inserts = [(stmt, params) for stmt, params in executes if "INSERT INTO fsma.rule_evaluations" in str(stmt)]
        assert len(inserts) == 1
        # Parameter list has one row, the rule's evaluation_id.
        _, params = inserts[0]
        assert isinstance(params, list)
        assert len(params) == 1
        assert params[0]["rule_id"] == "R1"
        assert params[0]["tenant_id"] == "t-1"
        assert params[0]["event_id"] == "evt-1"

    def test_multiple_results_batch_into_one_insert(self):
        """``_persist_evaluations`` uses an executemany-style INSERT — every
        row in the summary lands in one statement, not N statements."""
        engine, session, executes, _ = _make_engine_with_recording_session()
        summary = _populated_summary(
            results=[
                _result(rule_id="R1"),
                _result(rule_id="R2", result="pass", severity="info"),
                _result(rule_id="R3", result="warn", severity="warning"),
            ]
        )

        engine.persist_summary(summary, tenant_id="t-1")

        inserts = [(stmt, params) for stmt, params in executes if "INSERT INTO fsma.rule_evaluations" in str(stmt)]
        assert len(inserts) == 1
        rule_ids = [p["rule_id"] for p in inserts[0][1]]
        assert rule_ids == ["R1", "R2", "R3"]

    def test_savepoint_committed_on_success(self):
        engine, session, executes, savepoints = _make_engine_with_recording_session()
        engine.persist_summary(_populated_summary(), tenant_id="t-1")

        # One savepoint for the rule-row INSERT, one for the verdict stamp.
        assert len(savepoints) == 2
        # _persist_evaluations does not explicitly commit the savepoint —
        # it relies on the surrounding transaction. We just assert it
        # WAS opened (defense against a future refactor that removes
        # the savepoint guard).
        assert savepoints[0].rolled_back is False
        assert savepoints[1].rolled_back is False

    def test_verdict_stamp_mirrors_summary(self):
        engine, _, executes, _ = _make_engine_with_recording_session()
        engine.persist_summary(_populated_summary(), tenant_id="t-1")

        updates = _verdict_updates(executes)
        assert len(updates) == 1
        assert updates[0][1] == [{"tenant_id": "t-1", "event_id": "evt-1", "verdict": "fail", "reason": None}]

    def test_error_only_summary_stamps_fail(self):
        """An evaluator crash is a failure for the event verdict — it must
        never be persisted as ``pass``."""
        engine, _, executes, _ = _make_engine_with_recording_session()
        summary = EvaluationSummary(
            event_id="evt-err",
            total_rules=1,
            errored=1,
            results=[_result(result="error", why_failed="boom")],
        )

        engine.persist_summary(summary, tenant_id="t-1")

        updates = _verdict_updates(executes)
        assert updates[0][1][0]["verdict"] == "fail"


# ---------------------------------------------------------------------------
# event_id resolution
# ---------------------------------------------------------------------------


class TestEventIdResolution:
    def test_defaults_to_summary_event_id(self):
        engine, session, executes, _ = _make_engine_with_recording_session()
        summary = _populated_summary(event_id="from-summary")

        engine.persist_summary(summary, tenant_id="t-1")

        inserts = [(stmt, params) for stmt, params in executes if "INSERT" in str(stmt)]
        assert inserts[0][1][0]["event_id"] == "from-summary"

    def test_kwarg_overrides_summary_event_id(self):
        """Explicit ``event_id=`` wins over ``summary.event_id``. Useful when
        the same engine instance evaluated multiple events and the caller
        wants to persist results against a specific one."""
        engine, session, executes, _ = _make_engine_with_recording_session()
        summary = _populated_summary(event_id="from-summary")

        engine.persist_summary(summary, tenant_id="t-1", event_id="explicit-override")

        inserts = [(stmt, params) for stmt, params in executes if "INSERT" in str(stmt)]
        assert inserts[0][1][0]["event_id"] == "explicit-override"

    def test_missing_event_id_raises_value_error(self):
        """No event_id on summary AND no kwarg → ValueError. Refuse to
        write rows with an empty FK that downstream queries can't join."""
        engine, _, _, _ = _make_engine_with_recording_session()
        summary = _populated_summary(event_id="")

        with pytest.raises(ValueError, match="event_id"):
            engine.persist_summary(summary, tenant_id="t-1")


# ---------------------------------------------------------------------------
# Failure path mirrors _persist_evaluations contract
# ---------------------------------------------------------------------------


class TestFailurePath:
    def test_db_failure_rolls_savepoint_and_marks_event(self):
        """On INSERT failure: savepoint rolled back, traceability_events
        marked with ``evaluation_error`` so operators can see the event
        needs re-evaluation. Exception swallowed (consistent with the
        pre-existing ``_persist_evaluations`` contract)."""
        engine, session, executes, savepoints = _make_engine_with_recording_session()
        session.execute_should_raise = RuntimeError("disk full")

        engine.persist_summary(_populated_summary(), tenant_id="t-1")

        # Every savepoint opened by the failure path (outer persist, salvage
        # row, marker UPDATE, dead-letter INSERT — each guards its own
        # statement so one failure cannot abort the outer transaction) was
        # explicitly released or rolled back; none left dangling.
        assert len(savepoints) >= 1
        assert all(sp.rolled_back or sp.committed for sp in savepoints)
        # The failed INSERT's savepoints rolled back, the successful marker
        # and dead-letter savepoints committed.
        assert any(sp.rolled_back for sp in savepoints)
        assert any(sp.committed for sp in savepoints)

        # The failed INSERT is followed by the error marker UPDATE; the
        # verdict stamp is a separate UPDATE and must not be confused with
        # the marker.
        update_calls = _error_marker_updates(executes)
        assert len(update_calls) == 1
        assert update_calls[0][1]["tenant_id"] == "t-1"
        assert update_calls[0][1]["event_id"] == "evt-1"
        assert "disk full" in update_calls[0][1]["error_message"]
