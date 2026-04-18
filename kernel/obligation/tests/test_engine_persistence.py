"""
BUG-001 regression tests — RegulatoryEngine._persist_evaluation
================================================================
Verifies that _persist_evaluation correctly iterates over obligation_matches
and writes one ObligationEvaluation node per match, rather than accessing
fields that only exist on ObligationMatch (not ObligationEvaluationResult).
"""

from datetime import datetime
from unittest.mock import MagicMock, call, patch
from pathlib import Path

import pytest

from kernel.obligation.engine import RegulatoryEngine  # noqa: avoid kernel/__init__ eager imports
from kernel.obligation.models import (
    ObligationEvaluationResult,
    ObligationMatch,
    RiskLevel,
    Regulator,
    RegulatoryDomain,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_match(obligation_id: str, met: bool, missing: list[str] | None = None) -> ObligationMatch:
    return ObligationMatch(
        obligation_id=obligation_id,
        citation="21 CFR 1.1320",
        regulator=Regulator.FDA,
        domain=RegulatoryDomain.FSMA,
        met=met,
        missing_evidence=missing or [],
        risk_score=0.0 if met else 0.75,
    )


def _make_result(matches: list[ObligationMatch]) -> ObligationEvaluationResult:
    met_count = sum(1 for m in matches if m.met)
    return ObligationEvaluationResult(
        evaluation_id="eval-001",
        decision_id="decision-abc",
        timestamp=datetime(2026, 3, 5, 12, 0, 0),
        vertical="finance",
        total_applicable_obligations=len(matches),
        met_obligations=met_count,
        violated_obligations=len(matches) - met_count,
        coverage_percent=100.0 * met_count / len(matches) if matches else 100.0,
        overall_risk_score=0.0 if met_count == len(matches) else 0.75,
        risk_level=RiskLevel.LOW if met_count == len(matches) else RiskLevel.HIGH,
        obligation_matches=matches,
    )


def _make_engine_with_mock_graph() -> tuple[RegulatoryEngine, MagicMock]:
    """Return an engine wired to a mock Neo4j graph client."""
    mock_session = MagicMock()
    mock_graph = MagicMock()
    mock_graph.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_graph.session.return_value.__exit__ = MagicMock(return_value=False)

    engine = RegulatoryEngine(verticals_dir=Path("/tmp/fake"), graph_client=mock_graph)
    return engine, mock_session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPersistEvaluationNodeCount:
    """session.run() must be called once per match (CREATE) plus relationship calls."""

    def test_single_match_calls_session_run(self):
        engine, mock_session = _make_engine_with_mock_graph()
        result = _make_result([_make_match("OBL_001", met=True)])

        engine._persist_evaluation(result)

        # At minimum one CREATE call must have happened
        assert mock_session.run.called

    def test_two_matches_each_get_a_create_call(self):
        engine, mock_session = _make_engine_with_mock_graph()
        matches = [
            _make_match("OBL_001", met=True),
            _make_match("OBL_002", met=False, missing=["field_x"]),
        ]
        result = _make_result(matches)

        engine._persist_evaluation(result)

        # Collect all Cypher queries passed to session.run
        cypher_calls = [str(c.args[0]) for c in mock_session.run.call_args_list]
        create_calls = [q for q in cypher_calls if "CREATE (oe:ObligationEvaluation" in q]

        assert len(create_calls) == 2, (
            f"Expected one CREATE per match, got {len(create_calls)}"
        )

    def test_three_matches_produce_three_create_calls(self):
        engine, mock_session = _make_engine_with_mock_graph()
        matches = [_make_match(f"OBL_{i:03}", met=(i % 2 == 0)) for i in range(3)]
        result = _make_result(matches)

        engine._persist_evaluation(result)

        cypher_calls = [str(c.args[0]) for c in mock_session.run.call_args_list]
        create_calls = [q for q in cypher_calls if "CREATE (oe:ObligationEvaluation" in q]

        assert len(create_calls) == 3


class TestPersistEvaluationParameters:
    """Each CREATE call must use match-level fields, not result-level fields."""

    def test_create_uses_match_obligation_id(self):
        engine, mock_session = _make_engine_with_mock_graph()
        match = _make_match("ECOA_ADVERSE_ACTION", met=False, missing=["reason_codes"])
        result = _make_result([match])

        engine._persist_evaluation(result)

        # Find the CREATE call and inspect keyword args
        create_call = next(
            c for c in mock_session.run.call_args_list
            if "CREATE (oe:ObligationEvaluation" in str(c.args[0])
        )
        kwargs = create_call.kwargs
        assert kwargs["obligation_id"] == "ECOA_ADVERSE_ACTION"

    def test_create_uses_match_met_status(self):
        engine, mock_session = _make_engine_with_mock_graph()
        match = _make_match("OBL_001", met=False, missing=["field_a", "field_b"])
        result = _make_result([match])

        engine._persist_evaluation(result)

        create_call = next(
            c for c in mock_session.run.call_args_list
            if "CREATE (oe:ObligationEvaluation" in str(c.args[0])
        )
        assert create_call.kwargs["met"] is False

    def test_create_uses_match_risk_score(self):
        engine, mock_session = _make_engine_with_mock_graph()
        match = _make_match("OBL_001", met=False, missing=["x"])
        result = _make_result([match])

        engine._persist_evaluation(result)

        create_call = next(
            c for c in mock_session.run.call_args_list
            if "CREATE (oe:ObligationEvaluation" in str(c.args[0])
        )
        assert create_call.kwargs["risk_score"] == match.risk_score

    def test_create_uses_match_missing_evidence(self):
        engine, mock_session = _make_engine_with_mock_graph()
        missing = ["reason_codes", "notice_timestamp"]
        match = _make_match("OBL_001", met=False, missing=missing)
        result = _make_result([match])

        engine._persist_evaluation(result)

        create_call = next(
            c for c in mock_session.run.call_args_list
            if "CREATE (oe:ObligationEvaluation" in str(c.args[0])
        )
        assert create_call.kwargs["missing_evidence"] == missing

    def test_create_uses_result_timestamp_not_nonexistent_evaluated_at(self):
        """result.evaluated_at does not exist — must use result.timestamp."""
        engine, mock_session = _make_engine_with_mock_graph()
        match = _make_match("OBL_001", met=True)
        ts = datetime(2026, 3, 5, 9, 30, 0)
        result = _make_result([match])
        result = result.model_copy(update={"timestamp": ts})

        engine._persist_evaluation(result)

        create_call = next(
            c for c in mock_session.run.call_args_list
            if "CREATE (oe:ObligationEvaluation" in str(c.args[0])
        )
        assert create_call.kwargs["evaluated_at"] == ts.isoformat()


class TestPersistEvaluationNoGraph:
    """With no graph client, _persist_evaluation must return silently."""

    def test_no_graph_returns_without_error(self):
        engine = RegulatoryEngine(verticals_dir=Path("/tmp/fake"), graph_client=None)
        result = _make_result([_make_match("OBL_001", met=True)])

        # Should not raise
        engine._persist_evaluation(result)

    def test_no_graph_does_not_attempt_session(self):
        mock_graph = MagicMock()
        engine = RegulatoryEngine(verticals_dir=Path("/tmp/fake"), graph_client=None)
        result = _make_result([_make_match("OBL_001", met=True)])

        engine._persist_evaluation(result)

        mock_graph.session.assert_not_called()


class TestPersistEvaluationEmptyMatches:
    """Zero obligation matches — graph client is called but no CREATE runs."""

    def test_empty_matches_no_create_calls(self):
        engine, mock_session = _make_engine_with_mock_graph()
        result = _make_result([])

        engine._persist_evaluation(result)

        cypher_calls = [str(c.args[0]) for c in mock_session.run.call_args_list]
        create_calls = [q for q in cypher_calls if "CREATE (oe:ObligationEvaluation" in q]
        assert len(create_calls) == 0


class TestPersistEvaluationGraphError:
    """Graph errors must be caught and logged, not re-raised."""

    def test_graph_exception_does_not_propagate(self):
        mock_session = MagicMock()
        mock_session.run.side_effect = RuntimeError("Neo4j connection lost")
        mock_graph = MagicMock()
        mock_graph.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_graph.session.return_value.__exit__ = MagicMock(return_value=False)

        engine = RegulatoryEngine(verticals_dir=Path("/tmp/fake"), graph_client=mock_graph)
        result = _make_result([_make_match("OBL_001", met=True)])

        # Must not raise — errors are caught internally
        engine._persist_evaluation(result)
