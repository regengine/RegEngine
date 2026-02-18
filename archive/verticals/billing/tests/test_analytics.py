"""
Analytics Engine & API Tests

Tests MRR computation, cohort generation, conversion funnel,
credit ROI analysis, and revenue forecasting.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app
from analytics_engine import AnalyticsEngine
from models import Subscription, SubscriptionStatus, BillingCycle

client = TestClient(app)


# ── Engine Unit Tests ──────────────────────────────────────────────

class TestMRRCalculation:
    """Test MRR/ARR computation from subscriptions."""

    def test_empty_subscriptions(self):
        engine = AnalyticsEngine()
        result = engine.compute_mrr({})
        # Should still include seed MRR
        assert result["mrr_cents"] > 0
        assert result["active_subscriptions"] >= 47  # seed count

    def test_mrr_includes_active_subs(self):
        engine = AnalyticsEngine()
        subs = {
            "t1": Subscription(tenant_id="t1", tier_id="growth", status=SubscriptionStatus.ACTIVE,
                               billing_cycle=BillingCycle.ANNUAL),
            "t2": Subscription(tenant_id="t2", tier_id="starter", status=SubscriptionStatus.TRIALING),
        }
        result = engine.compute_mrr(subs)
        # Growth annual = $665/mo + Starter monthly = $299/mo + seed
        assert result["mrr_cents"] > 127_500_00
        assert result["active_subscriptions"] >= 49

    def test_mrr_excludes_canceled(self):
        engine = AnalyticsEngine()
        subs = {
            "t1": Subscription(tenant_id="t1", tier_id="growth", status=SubscriptionStatus.CANCELED),
        }
        result = engine.compute_mrr(subs)
        # Should only be seed MRR (canceled not counted)
        assert result["mrr_cents"] == 127_500_00

    def test_arr_is_12x_mrr(self):
        engine = AnalyticsEngine()
        result = engine.compute_mrr({})
        assert result["arr_cents"] == result["mrr_cents"] * 12


class TestMRRHistory:
    """Test MRR time series generation."""

    def test_history_length(self):
        engine = AnalyticsEngine()
        history = engine.get_mrr_history(12)
        assert len(history) == 12

    def test_history_growth_trend(self):
        engine = AnalyticsEngine()
        history = engine.get_mrr_history(12)
        # MRR should generally increase
        assert history[-1]["mrr_cents"] > history[0]["mrr_cents"]

    def test_history_fields(self):
        engine = AnalyticsEngine()
        entry = engine.get_mrr_history(1)[0]
        assert "month" in entry
        assert "mrr_cents" in entry
        assert "new_mrr_cents" in entry
        assert "churned_mrr_cents" in entry
        assert "net_new_mrr_cents" in entry


class TestCohorts:
    """Test cohort retention data."""

    def test_cohort_count(self):
        engine = AnalyticsEngine()
        data = engine.get_cohort_data()
        assert len(data["cohorts"]) == 6

    def test_retention_rates_decrease(self):
        engine = AnalyticsEngine()
        cohort = engine.get_cohort_data()["cohorts"][0]
        rates = cohort["retention_rates"]
        # Each month retention should be <= previous
        for i in range(1, len(rates)):
            assert rates[i] <= rates[i - 1]


class TestConversionFunnel:
    """Test funnel stage computation."""

    def test_funnel_stages(self):
        engine = AnalyticsEngine()
        funnel = engine.get_conversion_funnel({})
        assert len(funnel["stages"]) == 5
        stage_names = [s["name"] for s in funnel["stages"]]
        assert "Website Visitors" in stage_names
        assert "Converted to Paid" in stage_names

    def test_funnel_rates(self):
        engine = AnalyticsEngine()
        funnel = engine.get_conversion_funnel({})
        assert 0 < funnel["trial_to_paid_rate"] < 1
        assert 0 < funnel["churn_rate"] < 1


class TestForecasting:
    """Test revenue projections."""

    def test_forecast_length(self):
        engine = AnalyticsEngine()
        forecast = engine.get_revenue_forecast(6)
        assert len(forecast["forecasts"]) == 6

    def test_forecast_growth(self):
        engine = AnalyticsEngine()
        forecast = engine.get_revenue_forecast(6)
        projections = forecast["forecasts"]
        # Should project growth
        assert projections[-1]["projected_mrr_cents"] > projections[0]["projected_mrr_cents"]

    def test_confidence_interval_widens(self):
        engine = AnalyticsEngine()
        forecast = engine.get_revenue_forecast(6)
        p = forecast["forecasts"]
        # Later months should have wider confidence intervals
        range_first = p[0]["confidence_high_cents"] - p[0]["confidence_low_cents"]
        range_last = p[-1]["confidence_high_cents"] - p[-1]["confidence_low_cents"]
        assert range_last > range_first


# ── API Endpoint Tests ─────────────────────────────────────────────

class TestAnalyticsAPI:
    """Test analytics router endpoints."""

    def test_overview(self):
        response = client.get("/v1/billing/analytics/overview")
        assert response.status_code == 200
        data = response.json()
        assert "mrr" in data
        assert "key_metrics" in data
        assert "health" in data

    def test_mrr_history(self):
        response = client.get("/v1/billing/analytics/mrr-history?months=6")
        assert response.status_code == 200
        data = response.json()
        assert len(data["history"]) == 6

    def test_cohorts(self):
        response = client.get("/v1/billing/analytics/cohorts")
        assert response.status_code == 200
        data = response.json()
        assert "cohorts" in data
        assert data["avg_retention_rate"] > 0

    def test_funnel(self):
        response = client.get("/v1/billing/analytics/funnel")
        assert response.status_code == 200
        data = response.json()
        assert "stages" in data
        assert data["net_retention_rate"] > 1  # >100% NDR

    def test_credits_roi(self):
        response = client.get("/v1/billing/analytics/credits")
        assert response.status_code == 200
        data = response.json()
        assert "programs" in data
        assert "summary" in data

    def test_forecasts(self):
        response = client.get("/v1/billing/analytics/forecasts?months=3")
        assert response.status_code == 200
        data = response.json()
        assert len(data["forecasts"]) == 3
        assert data["confidence"] in ("high", "medium", "low")
