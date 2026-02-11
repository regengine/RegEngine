"""
Optimization Engine & API Tests

Tests pricing recommendations, revenue opportunities,
win-back campaigns, customer health, expansion metrics,
and API endpoints.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app
from optimization_engine import (
    OptimizationEngine, OpportunityType, OpportunityStatus, CampaignStatus, HealthGrade,
)

client = TestClient(app)


# ── Engine Unit Tests ──────────────────────────────────────────────

class TestPricingRecommendations:
    def test_recommendations_exist(self):
        engine = OptimizationEngine()
        recs = engine.get_recommendations()
        assert len(recs) >= 3

    def test_recommendation_fields(self):
        engine = OptimizationEngine()
        for r in engine.get_recommendations():
            assert r.current_price_cents > 0
            assert r.recommended_price_cents > 0
            assert 0 < r.confidence <= 1.0
            assert len(r.rationale) > 0


class TestRevenueOpportunities:
    def test_list_all(self):
        engine = OptimizationEngine()
        opps = engine.list_opportunities()
        assert len(opps) >= 5

    def test_filter_by_type(self):
        engine = OptimizationEngine()
        upsells = engine.list_opportunities(opp_type=OpportunityType.UPSELL)
        for o in upsells:
            assert o.opp_type == OpportunityType.UPSELL

    def test_filter_by_status(self):
        engine = OptimizationEngine()
        won = engine.list_opportunities(status=OpportunityStatus.WON)
        for o in won:
            assert o.status == OpportunityStatus.WON

    def test_sorted_by_value(self):
        engine = OptimizationEngine()
        opps = engine.list_opportunities()
        for i in range(len(opps) - 1):
            assert opps[i].estimated_value_cents >= opps[i + 1].estimated_value_cents

    def test_update_status(self):
        engine = OptimizationEngine()
        opp = engine.update_opportunity("opp_fresh_addon", OpportunityStatus.WON)
        assert opp.status == OpportunityStatus.WON

    def test_update_not_found(self):
        engine = OptimizationEngine()
        with pytest.raises(ValueError, match="not found"):
            engine.update_opportunity("opp_nope", OpportunityStatus.WON)


class TestWinBackCampaigns:
    def test_list_all(self):
        engine = OptimizationEngine()
        campaigns = engine.list_campaigns()
        assert len(campaigns) >= 3

    def test_filter_active(self):
        engine = OptimizationEngine()
        active = engine.list_campaigns(status=CampaignStatus.ACTIVE)
        for c in active:
            assert c.status == CampaignStatus.ACTIVE

    def test_get_campaign(self):
        engine = OptimizationEngine()
        campaign = engine.get_campaign("wbc_q1_save")
        assert campaign is not None
        assert campaign.converted >= 1

    def test_get_not_found(self):
        engine = OptimizationEngine()
        assert engine.get_campaign("wbc_nope") is None


class TestCustomerHealth:
    def test_all_scores(self):
        engine = OptimizationEngine()
        scores = engine.get_health_scores()
        assert len(scores) >= 6

    def test_sorted_by_score(self):
        engine = OptimizationEngine()
        scores = engine.get_health_scores()
        for i in range(len(scores) - 1):
            assert scores[i].score >= scores[i + 1].score

    def test_filter_by_grade(self):
        engine = OptimizationEngine()
        high = engine.get_health_scores(min_grade=HealthGrade.B)
        for s in high:
            assert s.grade in (HealthGrade.A, HealthGrade.B)

    def test_health_factors(self):
        engine = OptimizationEngine()
        for s in engine.get_health_scores():
            assert "usage" in s.factors
            assert "engagement" in s.factors
            assert "payment" in s.factors


class TestExpansion:
    def test_metrics(self):
        engine = OptimizationEngine()
        metrics = engine.get_expansion_metrics()
        assert len(metrics) >= 6

    def test_nrr_above_100(self):
        engine = OptimizationEngine()
        for m in engine.get_expansion_metrics():
            assert m.net_revenue_retention_pct > 100


class TestPipelineSummary:
    def test_summary(self):
        engine = OptimizationEngine()
        summary = engine.get_pipeline_summary()
        assert summary["pipeline_value_cents"] > 0
        assert summary["active_opportunities"] >= 3
        assert summary["win_back_conversions"] >= 1
        assert "health_distribution" in summary
        assert summary["pricing_recommendations"] >= 3


# ── API Endpoint Tests ─────────────────────────────────────────────

class TestOptimizationAPI:
    def test_pricing(self):
        response = client.get("/v1/billing/optimization/pricing")
        assert response.status_code == 200
        assert response.json()["total"] >= 3

    def test_opportunities(self):
        response = client.get("/v1/billing/optimization/opportunities")
        assert response.status_code == 200
        assert response.json()["total"] >= 5

    def test_update_opportunity(self):
        response = client.put("/v1/billing/optimization/opportunities/opp_acme_ep/status",
                              json={"status": "contacted"})
        assert response.status_code == 200

    def test_campaigns(self):
        response = client.get("/v1/billing/optimization/campaigns")
        assert response.status_code == 200
        assert response.json()["total"] >= 3

    def test_campaign_detail(self):
        response = client.get("/v1/billing/optimization/campaigns/wbc_q1_save")
        assert response.status_code == 200

    def test_campaign_not_found(self):
        response = client.get("/v1/billing/optimization/campaigns/wbc_nope")
        assert response.status_code == 404

    def test_health(self):
        response = client.get("/v1/billing/optimization/health")
        assert response.status_code == 200
        assert response.json()["total"] >= 6

    def test_expansion(self):
        response = client.get("/v1/billing/optimization/expansion")
        assert response.status_code == 200
        assert response.json()["total"] >= 6

    def test_pipeline(self):
        response = client.get("/v1/billing/optimization/pipeline")
        assert response.status_code == 200
