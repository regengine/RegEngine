"""
Hardening tests for ``kernel.obligation.routes`` (#1319).

Covers:

* Empty-tenant API keys are rejected (403).
* ``tenant_id`` flows from the APIKey through to the engine calls so
  persistence and coverage queries land in the right tenant bucket.
* ``/coverage/{vertical}`` no longer claims the wrong response_model, so
  a successful engine response returns 200, not 500 from Pydantic.
* The engine singleton is overridable via FastAPI's
  ``dependency_overrides`` — test scaffolding for the monolith wire-up.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kernel.obligation.engine import RegulatoryEngine
from kernel.obligation.models import (
    ObligationEvaluationResult,
    ObligationMatch,
    Regulator,
    RegulatoryDomain,
    RiskLevel,
)
from kernel.obligation.routes import get_engine, router
from shared.auth import APIKey, require_api_key


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _api_key(tenant_id: str | None = "tenant-xyz") -> APIKey:
    return APIKey(
        key_id="kid-1",
        key_hash="hash",
        name="test",
        tenant_id=tenant_id,
        created_at=datetime(2026, 1, 1),
    )


def _make_evaluation_result(tenant_id: str = "tenant-xyz") -> ObligationEvaluationResult:
    match = ObligationMatch(
        obligation_id="FSMA_204_RECEIVE",
        citation="21 CFR 1.1320",
        regulator=Regulator.FDA,
        domain=RegulatoryDomain.FSMA,
        met=True,
        missing_evidence=[],
        risk_score=0.0,
    )
    return ObligationEvaluationResult(
        evaluation_id="eval-1",
        decision_id="decision-1",
        timestamp=datetime(2026, 4, 17, 12, 0),
        vertical="food_beverage",
        total_applicable_obligations=1,
        met_obligations=1,
        violated_obligations=0,
        coverage_percent=100.0,
        overall_risk_score=0.0,
        risk_level=RiskLevel.LOW,
        obligation_matches=[match],
    )


@pytest.fixture
def app_with_mock_engine():
    """Build an app with mocked engine and API-key auth overrides."""
    app = FastAPI()
    app.include_router(router)

    mock_engine = MagicMock(spec=RegulatoryEngine)
    mock_engine.evaluators = {}
    mock_engine.evaluate_decision.return_value = _make_evaluation_result()
    mock_engine.get_coverage_report.return_value = {
        "vertical": "food_beverage",
        "status": "success",
        "total_obligations": 5,
        "evaluated_obligations": 5,
        "met_obligations": 4,
        "coverage_percent": 100.0,
        "recent_evaluations_7d": 10,
        "recent_compliance_rate": 0.8,
        "avg_confidence": 0.2,
    }

    # Default override: tenant-scoped key.
    current_key = {"value": _api_key("tenant-xyz")}

    def _key_dep() -> APIKey:
        return current_key["value"]

    app.dependency_overrides[get_engine] = lambda: mock_engine
    app.dependency_overrides[require_api_key] = _key_dep

    client = TestClient(app)
    return app, client, mock_engine, current_key


# ---------------------------------------------------------------------------
# #1319 part 1 — tenant extraction
# ---------------------------------------------------------------------------


class TestTenantIdExtraction:
    def test_empty_tenant_rejected_on_evaluate(self, app_with_mock_engine):
        app, client, mock_engine, current_key = app_with_mock_engine
        current_key["value"] = _api_key(tenant_id=None)

        resp = client.post(
            "/v1/obligations/evaluate",
            json={
                "decision_id": "d1",
                "decision_type": "shipment_receipt",
                "decision_data": {"lot_code": "LOT-1"},
                "vertical": "food_beverage",
            },
        )
        assert resp.status_code == 403
        mock_engine.evaluate_decision.assert_not_called()

    def test_empty_tenant_rejected_on_coverage(self, app_with_mock_engine):
        app, client, mock_engine, current_key = app_with_mock_engine
        current_key["value"] = _api_key(tenant_id="")

        resp = client.get("/v1/obligations/coverage/food_beverage")
        assert resp.status_code == 403
        mock_engine.get_coverage_report.assert_not_called()

    def test_tenant_forwarded_to_evaluate(self, app_with_mock_engine):
        app, client, mock_engine, current_key = app_with_mock_engine
        resp = client.post(
            "/v1/obligations/evaluate",
            json={
                "decision_id": "d1",
                "decision_type": "shipment_receipt",
                "decision_data": {"lot_code": "LOT-1"},
                "vertical": "food_beverage",
            },
        )
        assert resp.status_code == 200, resp.text
        mock_engine.evaluate_decision.assert_called_once()
        assert mock_engine.evaluate_decision.call_args.kwargs["tenant_id"] == "tenant-xyz"

    def test_tenant_forwarded_to_coverage(self, app_with_mock_engine):
        app, client, mock_engine, current_key = app_with_mock_engine
        resp = client.get("/v1/obligations/coverage/food_beverage")
        assert resp.status_code == 200, resp.text
        mock_engine.get_coverage_report.assert_called_once()
        assert mock_engine.get_coverage_report.call_args.kwargs["tenant_id"] == "tenant-xyz"


# ---------------------------------------------------------------------------
# #1319 part 2 — /coverage response_model reconciliation
# ---------------------------------------------------------------------------


class TestCoverageResponseModel:
    def test_coverage_returns_200_with_engine_dict(self, app_with_mock_engine):
        """Engine returns a plain dict; route must pass it through without a
        Pydantic 500.
        """
        app, client, mock_engine, current_key = app_with_mock_engine
        resp = client.get("/v1/obligations/coverage/food_beverage")
        assert resp.status_code == 200
        body = resp.json()
        # The engine dict's keys must be present in the response.
        assert body["vertical"] == "food_beverage"
        assert body["coverage_percent"] == 100.0
        assert body["total_obligations"] == 5


# ---------------------------------------------------------------------------
# #1319 part 3 — engine singleton is a dependency (overridable)
# ---------------------------------------------------------------------------


class TestEngineDependency:
    def test_dependency_override_is_respected(self, app_with_mock_engine):
        """Adoption requirement: tests must be able to swap the engine."""
        app, client, mock_engine, current_key = app_with_mock_engine
        # The fixture installs a MagicMock; a successful round-trip through
        # the evaluate endpoint confirms the override wins over the module
        # default.
        resp = client.post(
            "/v1/obligations/evaluate",
            json={
                "decision_id": "d1",
                "decision_type": "shipment_receipt",
                "decision_data": {"lot_code": "LOT-1"},
                "vertical": "food_beverage",
            },
        )
        assert resp.status_code == 200
        mock_engine.evaluate_decision.assert_called_once()


# ---------------------------------------------------------------------------
# Sanity: happy-path evaluation payload shape
# ---------------------------------------------------------------------------


class TestEvaluationPayload:
    def test_evaluate_returns_result_schema(self, app_with_mock_engine):
        app, client, mock_engine, current_key = app_with_mock_engine
        resp = client.post(
            "/v1/obligations/evaluate",
            json={
                "decision_id": "d1",
                "decision_type": "shipment_receipt",
                "decision_data": {"lot_code": "LOT-1"},
                "vertical": "food_beverage",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        for field in (
            "evaluation_id",
            "decision_id",
            "vertical",
            "coverage_percent",
            "risk_level",
            "obligation_matches",
        ):
            assert field in body
