"""
Forecasting Engine & API Tests

Tests MRR forecasting, churn prediction, CLV modeling,
cohort analysis, anomaly detection, and API endpoints.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app
from forecasting_engine import ForecastingEngine, ChurnRisk

client = TestClient(app)


# ── Engine Unit Tests ──────────────────────────────────────────────

class TestMRRHistory:
    def test_history_exists(self):
        engine = ForecastingEngine()
        history = engine.get_mrr_history()
        assert len(history) == 12

    def test_history_has_required_fields(self):
        engine = ForecastingEngine()
        entry = engine.get_mrr_history()[0]
        assert "month" in entry
        assert "mrr_cents" in entry
        assert "new_mrr_cents" in entry
        assert "churned_mrr_cents" in entry

    def test_mrr_is_growing(self):
        engine = ForecastingEngine()
        history = engine.get_mrr_history()
        assert history[-1]["mrr_cents"] > history[0]["mrr_cents"]


class TestMRRForecast:
    def test_forecast_default(self):
        engine = ForecastingEngine()
        forecasts = engine.forecast_mrr()
        assert len(forecasts) == 6

    def test_forecast_custom_months(self):
        engine = ForecastingEngine()
        forecasts = engine.forecast_mrr(3)
        assert len(forecasts) == 3

    def test_forecast_has_confidence(self):
        engine = ForecastingEngine()
        forecasts = engine.forecast_mrr()
        for f in forecasts:
            assert 0.5 <= f.confidence <= 1.0

    def test_forecast_bounds(self):
        engine = ForecastingEngine()
        forecasts = engine.forecast_mrr()
        for f in forecasts:
            assert f.lower_bound_cents <= f.predicted_mrr_cents <= f.upper_bound_cents

    def test_confidence_decreases(self):
        engine = ForecastingEngine()
        forecasts = engine.forecast_mrr(6)
        assert forecasts[0].confidence >= forecasts[-1].confidence


class TestChurnPrediction:
    def test_all_scores(self):
        engine = ForecastingEngine()
        scores = engine.get_churn_scores()
        assert len(scores) >= 8

    def test_filter_by_risk(self):
        engine = ForecastingEngine()
        critical = engine.get_churn_scores(risk=ChurnRisk.CRITICAL)
        for s in critical:
            assert s.risk == ChurnRisk.CRITICAL

    def test_scores_sorted_descending(self):
        engine = ForecastingEngine()
        scores = engine.get_churn_scores()
        for i in range(len(scores) - 1):
            assert scores[i].score >= scores[i + 1].score

    def test_churn_overview(self):
        engine = ForecastingEngine()
        overview = engine.get_churn_overview()
        assert overview["total_scored"] >= 8
        assert "risk_distribution" in overview
        assert "at_risk_revenue_display" in overview
        assert len(overview["high_risk_tenants"]) >= 1


class TestCLV:
    def test_estimates(self):
        engine = ForecastingEngine()
        estimates = engine.get_clv_estimates()
        assert len(estimates) >= 8

    def test_clv_positive(self):
        engine = ForecastingEngine()
        for e in engine.get_clv_estimates():
            assert e.lifetime_value_cents > 0

    def test_clv_summary(self):
        engine = ForecastingEngine()
        summary = engine.get_clv_summary()
        assert summary["total_customers"] >= 8
        assert summary["total_clv_cents"] > 0
        assert "by_plan" in summary
        assert len(summary["top_customers"]) >= 5


class TestCohorts:
    def test_cohorts_exist(self):
        engine = ForecastingEngine()
        cohorts = engine.get_cohorts()
        assert len(cohorts) >= 5

    def test_retention_rates(self):
        engine = ForecastingEngine()
        for c in engine.get_cohorts():
            assert c.retention_rates[0] == 100.0
            for i in range(1, len(c.retention_rates)):
                assert c.retention_rates[i] <= c.retention_rates[i - 1]

    def test_retention_matrix(self):
        engine = ForecastingEngine()
        matrix = engine.get_retention_matrix()
        assert "avg_retention" in matrix
        assert "best_cohort" in matrix
        assert "worst_cohort" in matrix


class TestAnomalies:
    def test_anomalies(self):
        engine = ForecastingEngine()
        anomalies = engine.get_anomalies()
        assert len(anomalies) >= 3


class TestExecutiveSummary:
    def test_summary(self):
        engine = ForecastingEngine()
        summary = engine.get_executive_summary()
        assert "current_mrr_cents" in summary
        assert "arr_cents" in summary
        assert "forecast_3mo" in summary
        assert "churn_risk_summary" in summary
        assert "total_clv" in summary


# ── API Endpoint Tests ─────────────────────────────────────────────

class TestForecastingAPI:
    def test_mrr_history(self):
        response = client.get("/v1/billing/forecasting/mrr/history")
        assert response.status_code == 200
        assert response.json()["months"] == 12

    def test_mrr_forecast(self):
        response = client.get("/v1/billing/forecasting/mrr/forecast?months=3")
        assert response.status_code == 200
        assert len(response.json()["forecasts"]) == 3

    def test_churn_scores(self):
        response = client.get("/v1/billing/forecasting/churn/scores")
        assert response.status_code == 200
        assert response.json()["total"] >= 8

    def test_churn_overview(self):
        response = client.get("/v1/billing/forecasting/churn/overview")
        assert response.status_code == 200

    def test_clv(self):
        response = client.get("/v1/billing/forecasting/clv")
        assert response.status_code == 200
        assert response.json()["total"] >= 8

    def test_clv_summary(self):
        response = client.get("/v1/billing/forecasting/clv/summary")
        assert response.status_code == 200

    def test_cohorts(self):
        response = client.get("/v1/billing/forecasting/cohorts")
        assert response.status_code == 200
        assert response.json()["total"] >= 5

    def test_retention(self):
        response = client.get("/v1/billing/forecasting/cohorts/retention")
        assert response.status_code == 200

    def test_anomalies(self):
        response = client.get("/v1/billing/forecasting/anomalies")
        assert response.status_code == 200
        assert response.json()["total"] >= 3

    def test_summary(self):
        response = client.get("/v1/billing/forecasting/summary")
        assert response.status_code == 200
