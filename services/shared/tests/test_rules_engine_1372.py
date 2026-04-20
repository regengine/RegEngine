"""Regression tests for issue #1372.

_persist_evaluations must wrap all per-row INSERTs in a single savepoint
so that a failure on any row rolls back the entire batch atomically — no
partial writes should survive in the parent transaction.
"""
from unittest.mock import MagicMock, call, patch
import pytest

from shared.rules.types import RuleEvaluationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_results(n: int) -> list[RuleEvaluationResult]:
    return [
        RuleEvaluationResult(
            evaluation_id=f"eval-{i}",
            rule_id=f"rule-{i}",
            rule_version=1,
            result="pass",
        )
        for i in range(n)
    ]


def _make_engine(session):
    """Construct a RulesEngine with a mock session, bypassing DB rule load."""
    from shared.rules.engine import RulesEngine

    engine = object.__new__(RulesEngine)
    engine.session = session
    engine.rules = []
    return engine


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPersistEvaluationsAtomicity:
    """_persist_evaluations is atomic: failure rolls back the whole batch."""

    def test_success_executes_all_inserts(self):
        """Happy path: all INSERTs are issued inside the savepoint."""
        session = MagicMock()
        # begin_nested() returns a context manager; default MagicMock handles that
        engine = _make_engine(session)
        results = _make_results(3)

        engine._persist_evaluations("tenant-1", "event-1", results)

        # begin_nested called once (one savepoint for the whole batch)
        session.begin_nested.assert_called_once()
        # execute called once per result
        assert session.execute.call_count == 3

    def test_partial_failure_raises_and_no_rows_committed(self):
        """If the Nth INSERT raises, the exception propagates and the
        savepoint is rolled back — no rows from the batch survive."""
        session = MagicMock()

        # Make execute succeed for first call, fail on second
        session.execute.side_effect = [
            None,  # first INSERT ok
            Exception("simulated DB error on row 2"),
        ]

        # begin_nested returns a real context-manager-like mock so __exit__
        # is called.  We need the savepoint to actually call __exit__ with
        # the exception so SQLAlchemy can roll it back.  Use a simple helper:
        class _FakeSavepoint:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                # Don't suppress the exception — let it propagate (mimics
                # SQLAlchemy behaviour: rollback to savepoint then re-raise)
                return False

        session.begin_nested.return_value = _FakeSavepoint()

        engine = _make_engine(session)
        results = _make_results(3)

        with pytest.raises(Exception, match="simulated DB error on row 2"):
            engine._persist_evaluations("tenant-1", "event-1", results)

        # begin_nested was entered (savepoint was created)
        session.begin_nested.assert_called_once()

        # execute was called only twice — the third INSERT was never reached
        assert session.execute.call_count == 2

    def test_empty_results_no_execute(self):
        """An empty results list is a no-op — no DB calls."""
        session = MagicMock()
        engine = _make_engine(session)

        engine._persist_evaluations("tenant-1", "event-1", [])

        session.execute.assert_not_called()

    def test_savepoint_used_not_bare_begin(self):
        """The method must call begin_nested() (savepoint), NOT begin()."""
        session = MagicMock()
        engine = _make_engine(session)

        engine._persist_evaluations("tenant-1", "event-1", _make_results(2))

        session.begin_nested.assert_called_once()
        session.begin.assert_not_called()
