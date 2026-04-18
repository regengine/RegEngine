"""
BUG-001 + #1326 regression tests — RegulatoryEngine._persist_evaluation
========================================================================

Verifies that ``_persist_evaluation``:

1. Writes an ObligationEvaluation node per match (BUG-001 / original intent).
2. Uses a single ``UNWIND``-based Cypher inside a managed transaction
   (``session.execute_write``), not one ``session.run`` per match (#1326).
3. Filters both the Decision and RegulatoryObligation MATCH clauses on
   ``tenant_id`` (#1326 / tenant isolation).
4. Passes each match's own obligation_id/met/missing_evidence/risk_score
   through the parameter payload, not the result-level fields.
5. Returns silently when no graph client is configured and swallows graph
   exceptions.
"""

from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

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
        vertical="food_beverage",
        total_applicable_obligations=len(matches),
        met_obligations=met_count,
        violated_obligations=len(matches) - met_count,
        coverage_percent=100.0 * met_count / len(matches) if matches else 100.0,
        overall_risk_score=0.0 if met_count == len(matches) else 0.75,
        risk_level=RiskLevel.LOW if met_count == len(matches) else RiskLevel.HIGH,
        obligation_matches=matches,
    )


def _make_engine_with_mock_graph() -> tuple[RegulatoryEngine, MagicMock, MagicMock]:
    """Return (engine, mock_session, mock_tx).

    The mock ``session.execute_write(callback)`` implementation invokes
    ``callback(tx)`` so we can observe the Cypher + params handed to the
    managed transaction.
    """
    mock_tx = MagicMock()
    mock_session = MagicMock()

    def _execute_write(cb, *args, **kwargs):
        return cb(mock_tx, *args, **kwargs)

    mock_session.execute_write.side_effect = _execute_write

    mock_graph = MagicMock()
    mock_graph.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_graph.session.return_value.__exit__ = MagicMock(return_value=False)

    engine = RegulatoryEngine(verticals_dir=Path("/tmp/fake"), graph_client=mock_graph)
    return engine, mock_session, mock_tx


# ---------------------------------------------------------------------------
# #1326 — One UNWIND call, not N*3 queries
# ---------------------------------------------------------------------------


class TestPersistEvaluationSingleUnwindCall:
    def test_calls_execute_write_once(self):
        engine, mock_session, mock_tx = _make_engine_with_mock_graph()
        matches = [_make_match(f"OBL_{i:03}", met=(i % 2 == 0)) for i in range(5)]
        result = _make_result(matches)

        engine._persist_evaluation(result)

        assert mock_session.execute_write.call_count == 1, (
            "Single managed transaction expected, got "
            f"{mock_session.execute_write.call_count}"
        )

    def test_tx_run_called_once(self):
        engine, mock_session, mock_tx = _make_engine_with_mock_graph()
        matches = [_make_match(f"OBL_{i:03}", met=(i % 2 == 0)) for i in range(5)]
        result = _make_result(matches)

        engine._persist_evaluation(result)

        assert mock_tx.run.call_count == 1, (
            f"Expected 1 Cypher call total, got {mock_tx.run.call_count}"
        )

    def test_uses_unwind(self):
        engine, mock_session, mock_tx = _make_engine_with_mock_graph()
        result = _make_result([_make_match("OBL_001", met=True)])
        engine._persist_evaluation(result)

        cypher = mock_tx.run.call_args.args[0]
        assert "UNWIND $matches" in cypher

    def test_cypher_creates_obligation_evaluation_node(self):
        engine, mock_session, mock_tx = _make_engine_with_mock_graph()
        result = _make_result([_make_match("OBL_001", met=True)])
        engine._persist_evaluation(result)

        cypher = mock_tx.run.call_args.args[0]
        assert "CREATE (oe:ObligationEvaluation" in cypher


# ---------------------------------------------------------------------------
# #1326 — Tenant filter on both MATCHes
# ---------------------------------------------------------------------------


class TestPersistEvaluationTenantFilter:
    def test_decision_match_filters_tenant(self):
        engine, mock_session, mock_tx = _make_engine_with_mock_graph()
        result = _make_result([_make_match("OBL_001", met=True)])
        engine._persist_evaluation(result, tenant_id="tenant-xyz")

        cypher = mock_tx.run.call_args.args[0]
        assert "(d:Decision {decision_id: $decision_id, tenant_id: $tenant_id})" in cypher

    def test_regulatory_obligation_match_filters_tenant(self):
        engine, mock_session, mock_tx = _make_engine_with_mock_graph()
        result = _make_result([_make_match("OBL_001", met=True)])
        engine._persist_evaluation(result, tenant_id="tenant-xyz")

        cypher = mock_tx.run.call_args.args[0]
        assert "(o:RegulatoryObligation {obligation_id: m.obligation_id, tenant_id: $tenant_id})" in cypher

    def test_tenant_id_is_forwarded_in_params(self):
        engine, mock_session, mock_tx = _make_engine_with_mock_graph()
        result = _make_result([_make_match("OBL_001", met=True)])
        engine._persist_evaluation(result, tenant_id="tenant-abc")

        kwargs = mock_tx.run.call_args.kwargs
        assert kwargs["tenant_id"] == "tenant-abc"


# ---------------------------------------------------------------------------
# Per-match payload carries match-level fields (not result-level)
# ---------------------------------------------------------------------------


class TestPersistEvaluationMatchPayload:
    def test_each_match_carries_own_obligation_id(self):
        engine, mock_session, mock_tx = _make_engine_with_mock_graph()
        matches = [
            _make_match("OBL_A", met=True),
            _make_match("OBL_B", met=False, missing=["field_x"]),
        ]
        result = _make_result(matches)
        engine._persist_evaluation(result)

        payload = mock_tx.run.call_args.kwargs["matches"]
        assert [m["obligation_id"] for m in payload] == ["OBL_A", "OBL_B"]

    def test_match_payload_includes_met_and_missing(self):
        engine, mock_session, mock_tx = _make_engine_with_mock_graph()
        matches = [
            _make_match("OBL_A", met=True),
            _make_match("OBL_B", met=False, missing=["field_x", "field_y"]),
        ]
        result = _make_result(matches)
        engine._persist_evaluation(result)

        payload = mock_tx.run.call_args.kwargs["matches"]
        assert payload[0]["met"] is True
        assert payload[0]["missing_evidence"] == []
        assert payload[1]["met"] is False
        assert payload[1]["missing_evidence"] == ["field_x", "field_y"]

    def test_match_payload_includes_risk_score(self):
        engine, mock_session, mock_tx = _make_engine_with_mock_graph()
        match = _make_match("OBL_A", met=False, missing=["a"])
        result = _make_result([match])
        engine._persist_evaluation(result)

        payload = mock_tx.run.call_args.kwargs["matches"]
        assert payload[0]["risk_score"] == match.risk_score

    def test_evaluated_at_uses_result_timestamp(self):
        """``result.timestamp`` (not a non-existent ``evaluated_at``) must be
        what the Cypher binds to ``$evaluated_at``."""
        engine, mock_session, mock_tx = _make_engine_with_mock_graph()
        ts = datetime(2026, 3, 5, 9, 30, 0)
        result = _make_result([_make_match("OBL_001", met=True)])
        result = result.model_copy(update={"timestamp": ts})

        engine._persist_evaluation(result)

        kwargs = mock_tx.run.call_args.kwargs
        assert kwargs["evaluated_at"] == ts.isoformat()


# ---------------------------------------------------------------------------
# No-graph / empty / error paths
# ---------------------------------------------------------------------------


class TestPersistEvaluationNoGraph:
    def test_no_graph_returns_without_error(self):
        engine = RegulatoryEngine(verticals_dir=Path("/tmp/fake"), graph_client=None)
        result = _make_result([_make_match("OBL_001", met=True)])
        engine._persist_evaluation(result)  # no raise


class TestPersistEvaluationEmptyMatches:
    def test_empty_matches_no_transaction(self):
        engine, mock_session, mock_tx = _make_engine_with_mock_graph()
        result = _make_result([])
        engine._persist_evaluation(result)
        # Nothing to persist — no round-trip should happen.
        mock_session.execute_write.assert_not_called()
        mock_tx.run.assert_not_called()


class TestPersistEvaluationGraphError:
    def test_graph_exception_does_not_propagate(self):
        mock_tx = MagicMock()
        mock_tx.run.side_effect = RuntimeError("Neo4j connection lost")
        mock_session = MagicMock()

        def _execute_write(cb, *args, **kwargs):
            return cb(mock_tx)

        mock_session.execute_write.side_effect = _execute_write
        mock_graph = MagicMock()
        mock_graph.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_graph.session.return_value.__exit__ = MagicMock(return_value=False)

        engine = RegulatoryEngine(verticals_dir=Path("/tmp/fake"), graph_client=mock_graph)
        result = _make_result([_make_match("OBL_001", met=True)])

        engine._persist_evaluation(result)  # no raise
