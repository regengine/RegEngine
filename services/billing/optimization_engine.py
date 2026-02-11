"""
Billing Service — Revenue Optimization Engine

AI-powered revenue intelligence: dynamic pricing recommendations,
win-back campaign management, upsell opportunity identification,
expansion revenue tracking, and health scoring.
In-memory with realistic seeded data.
"""

from __future__ import annotations

import structlog
import random
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4
from enum import Enum
from pydantic import BaseModel, Field

from utils import format_cents

logger = structlog.get_logger(__name__)

random.seed(99)  # Reproducible optimization data


# ── Enums ──────────────────────────────────────────────────────────

class OpportunityType(str, Enum):
    UPSELL = "upsell"
    CROSS_SELL = "cross_sell"
    EXPANSION = "expansion"
    WIN_BACK = "win_back"


class OpportunityStatus(str, Enum):
    IDENTIFIED = "identified"
    CONTACTED = "contacted"
    IN_PROGRESS = "in_progress"
    WON = "won"
    LOST = "lost"


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class HealthGrade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


# ── Models ─────────────────────────────────────────────────────────

class PricingRecommendation(BaseModel):
    id: str = Field(default_factory=lambda: f"rec_{uuid4().hex[:8]}")
    plan: str
    current_price_cents: int
    recommended_price_cents: int
    change_pct: float
    rationale: str
    expected_impact: str
    confidence: float
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RevenueOpportunity(BaseModel):
    id: str = Field(default_factory=lambda: f"opp_{uuid4().hex[:8]}")
    tenant_id: str
    tenant_name: str
    opp_type: OpportunityType
    status: OpportunityStatus
    title: str
    description: str
    estimated_value_cents: int
    estimated_value_display: str = ""
    probability_pct: float
    recommended_action: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WinBackCampaign(BaseModel):
    id: str = Field(default_factory=lambda: f"wbc_{uuid4().hex[:8]}")
    name: str
    status: CampaignStatus
    target_segment: str
    offer: str
    discount_pct: float
    target_count: int
    contacted: int
    responded: int
    converted: int
    revenue_recovered_cents: int
    started_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CustomerHealth(BaseModel):
    tenant_id: str
    tenant_name: str
    grade: HealthGrade
    score: int  # 0-100
    factors: dict  # usage, engagement, payment, support, growth
    opportunities: list[str]


class ExpansionMetrics(BaseModel):
    period: str
    expansion_revenue_cents: int
    expansion_display: str
    net_revenue_retention_pct: float
    upgrades: int
    addons: int
    cross_sells: int


# ── Optimization Engine ────────────────────────────────────────────

class OptimizationEngine:
    """AI-powered revenue intelligence and optimization."""

    def __init__(self):
        self._recommendations: dict[str, PricingRecommendation] = {}
        self._opportunities: dict[str, RevenueOpportunity] = {}
        self._campaigns: dict[str, WinBackCampaign] = {}
        self._health_scores: dict[str, CustomerHealth] = {}
        self._expansion: list[ExpansionMetrics] = []
        self._seed_demo_data()

    def _seed_demo_data(self):
        now = datetime.utcnow()

        # Pricing recommendations
        recs = [
            PricingRecommendation(
                id="rec_starter", plan="starter",
                current_price_cents=49_900, recommended_price_cents=59_900,
                change_pct=20.0, confidence=0.82,
                rationale="Market analysis shows 23% of prospects select Starter despite needing Pro features. Price anchoring at $599 would drive more Pro conversions.",
                expected_impact="Estimated +$8.4K MRR from conversion lift, minimal churn risk at this tier.",
            ),
            PricingRecommendation(
                id="rec_enterprise", plan="enterprise",
                current_price_cents=499_900, recommended_price_cents=549_900,
                change_pct=10.0, confidence=0.75,
                rationale="Enterprise customers show 94% retention and high willingness-to-pay. Competitor pricing averages $6,200/mo.",
                expected_impact="Estimated +$15K MRR with <2% additional churn based on price elasticity modeling.",
            ),
            PricingRecommendation(
                id="rec_addons", plan="fda_export_addon",
                current_price_cents=29_900, recommended_price_cents=39_900,
                change_pct=33.4, confidence=0.88,
                rationale="FDA Export addon has 98% attachment rate among food safety tenants. No competitive alternative exists.",
                expected_impact="Estimated +$4.2K MRR. Zero churn risk — regulatory requirement for customers.",
            ),
        ]
        for r in recs:
            self._recommendations[r.id] = r

        # Revenue opportunities
        opps = [
            RevenueOpportunity(
                id="opp_acme_ep", tenant_id="acme_foods", tenant_name="Acme Foods Inc.",
                opp_type=OpportunityType.UPSELL, status=OpportunityStatus.IDENTIFIED,
                title="Enterprise+ Upgrade", description="API usage trending at 92% capacity. Multi-team deployment expanding.",
                estimated_value_cents=500_000, estimated_value_display="$5,000.00",
                probability_pct=72, recommended_action="Schedule demo of Enterprise+ features with CTO",
                created_at=now - timedelta(days=3),
            ),
            RevenueOpportunity(
                id="opp_fresh_addon", tenant_id="freshleaf", tenant_name="FreshLeaf Produce",
                opp_type=OpportunityType.CROSS_SELL, status=OpportunityStatus.CONTACTED,
                title="FDA Export Module", description="FreshLeaf handles 200+ FSMA 204 shipments/month without automated exports.",
                estimated_value_cents=39_900, estimated_value_display="$399.00",
                probability_pct=85, recommended_action="Share FDA export ROI calculator",
                created_at=now - timedelta(days=7),
            ),
            RevenueOpportunity(
                id="opp_med_exp", tenant_id="medsecure", tenant_name="MedSecure Health",
                opp_type=OpportunityType.EXPANSION, status=OpportunityStatus.IN_PROGRESS,
                title="Multi-Department Expansion", description="Compliance team interested in adding 3 more departments.",
                estimated_value_cents=299_700, estimated_value_display="$2,997.00",
                probability_pct=55, recommended_action="Arrange multi-department pricing review",
                created_at=now - timedelta(days=14),
            ),
            RevenueOpportunity(
                id="opp_oldco_wb", tenant_id="oldco", tenant_name="OldCo Logistics",
                opp_type=OpportunityType.WIN_BACK, status=OpportunityStatus.IDENTIFIED,
                title="Win-Back — Cancelled 45 Days", description="Cancelled due to budget cuts. New fiscal year starts next month.",
                estimated_value_cents=49_900, estimated_value_display="$499.00",
                probability_pct=30, recommended_action="Send win-back offer with 3 months at 50% off",
                created_at=now - timedelta(days=2),
            ),
            RevenueOpportunity(
                id="opp_global_seats", tenant_id="globalfish", tenant_name="GlobalFish Imports",
                opp_type=OpportunityType.EXPANSION, status=OpportunityStatus.WON,
                title="Seat Expansion — 15 Additional Users", description="GlobalFish expanding to 3 new import facilities.",
                estimated_value_cents=150_000, estimated_value_display="$1,500.00",
                probability_pct=100, recommended_action="Deploy additional seats and schedule onboarding",
                created_at=now - timedelta(days=20),
            ),
        ]
        for o in opps:
            self._opportunities[o.id] = o

        # Win-back campaigns
        campaigns = [
            WinBackCampaign(
                id="wbc_q1_save", name="Q1 Save & Recover", status=CampaignStatus.ACTIVE,
                target_segment="Churned < 90 days, Starter/Professional",
                offer="50% off first 3 months", discount_pct=50.0,
                target_count=12, contacted=8, responded=5, converted=2,
                revenue_recovered_cents=149_800,
                started_at=now - timedelta(days=30),
            ),
            WinBackCampaign(
                id="wbc_enterprise_retention", name="Enterprise Retention Boost", status=CampaignStatus.ACTIVE,
                target_segment="Enterprise with declining usage",
                offer="Free 3-month Enterprise+ trial", discount_pct=0.0,
                target_count=4, contacted=3, responded=2, converted=1,
                revenue_recovered_cents=499_900,
                started_at=now - timedelta(days=15),
            ),
            WinBackCampaign(
                id="wbc_annual_offer", name="Annual Commitment Incentive", status=CampaignStatus.COMPLETED,
                target_segment="Monthly subscribers > 6 months",
                offer="20% discount for annual commitment", discount_pct=20.0,
                target_count=18, contacted=18, responded=12, converted=7,
                revenue_recovered_cents=2_519_300,
                started_at=now - timedelta(days=60),
            ),
        ]
        for c in campaigns:
            self._campaigns[c.id] = c

        # Customer health scores
        health_data = [
            ("acme_foods", "Acme Foods Inc.", HealthGrade.A, 92,
             {"usage": 95, "engagement": 88, "payment": 100, "support": 85, "growth": 90},
             ["Ready for Enterprise+ upsell", "Potential case study candidate"]),
            ("globalfish", "GlobalFish Imports", HealthGrade.A, 96,
             {"usage": 98, "engagement": 95, "payment": 100, "support": 90, "growth": 95},
             ["Strategic account — expand with co-marketing", "Reference customer potential"]),
            ("freshleaf", "FreshLeaf Produce", HealthGrade.B, 78,
             {"usage": 82, "engagement": 75, "payment": 100, "support": 60, "growth": 72},
             ["Cross-sell FDA Export addon", "Offer annual contract"]),
            ("medsecure", "MedSecure Health", HealthGrade.C, 55,
             {"usage": 45, "engagement": 50, "payment": 65, "support": 70, "growth": 40},
             ["Schedule customer success review", "Address payment issues"]),
            ("safetyfirst", "SafetyFirst Mfg", HealthGrade.D, 32,
             {"usage": 30, "engagement": 25, "payment": 45, "support": 35, "growth": 20},
             ["Executive intervention needed", "Offer contract restructuring"]),
            ("oldco", "OldCo Logistics", HealthGrade.F, 8,
             {"usage": 0, "engagement": 0, "payment": 0, "support": 10, "growth": 0},
             ["Win-back campaign target", "Survey for churn feedback"]),
        ]
        for tid, name, grade, score, factors, opps_list in health_data:
            self._health_scores[tid] = CustomerHealth(
                tenant_id=tid, tenant_name=name, grade=grade,
                score=score, factors=factors, opportunities=opps_list,
            )

        # Expansion metrics (6 months)
        for i in range(6, 0, -1):
            month = now - timedelta(days=30 * i)
            exp_rev = random.randint(15_000_00, 65_000_00)
            self._expansion.append(ExpansionMetrics(
                period=month.strftime("%Y-%m"),
                expansion_revenue_cents=exp_rev,
                expansion_display=format_cents(exp_rev),
                net_revenue_retention_pct=round(100 + random.uniform(5, 25), 1),
                upgrades=random.randint(1, 4),
                addons=random.randint(0, 3),
                cross_sells=random.randint(0, 2),
            ))

    # ── Pricing Recommendations ────────────────────────────────

    def get_recommendations(self) -> list[PricingRecommendation]:
        return list(self._recommendations.values())

    # ── Revenue Opportunities ──────────────────────────────────

    def list_opportunities(self, opp_type: OpportunityType | None = None,
                           status: OpportunityStatus | None = None) -> list[RevenueOpportunity]:
        opps = list(self._opportunities.values())
        if opp_type:
            opps = [o for o in opps if o.opp_type == opp_type]
        if status:
            opps = [o for o in opps if o.status == status]
        return sorted(opps, key=lambda o: o.estimated_value_cents, reverse=True)

    def update_opportunity(self, opp_id: str, status: OpportunityStatus) -> RevenueOpportunity:
        opp = self._opportunities.get(opp_id)
        if not opp:
            raise ValueError(f"Opportunity {opp_id} not found")
        opp.status = status
        logger.info("opportunity_updated", opp_id=opp_id, status=status.value)
        return opp

    # ── Win-Back Campaigns ─────────────────────────────────────

    def list_campaigns(self, status: CampaignStatus | None = None) -> list[WinBackCampaign]:
        campaigns = list(self._campaigns.values())
        if status:
            campaigns = [c for c in campaigns if c.status == status]
        return campaigns

    def get_campaign(self, campaign_id: str) -> Optional[WinBackCampaign]:
        return self._campaigns.get(campaign_id)

    # ── Customer Health ────────────────────────────────────────

    def get_health_scores(self, min_grade: HealthGrade | None = None) -> list[CustomerHealth]:
        scores = list(self._health_scores.values())
        if min_grade:
            grade_order = list(HealthGrade)
            min_idx = grade_order.index(min_grade)
            scores = [s for s in scores if grade_order.index(s.grade) <= min_idx]
        return sorted(scores, key=lambda s: s.score, reverse=True)

    # ── Expansion Tracking ─────────────────────────────────────

    def get_expansion_metrics(self) -> list[ExpansionMetrics]:
        return self._expansion

    # ── Pipeline Summary ───────────────────────────────────────

    def get_pipeline_summary(self) -> dict:
        opps = list(self._opportunities.values())
        pipeline_value = sum(o.estimated_value_cents for o in opps if o.status not in (OpportunityStatus.WON, OpportunityStatus.LOST))
        weighted_value = sum(int(o.estimated_value_cents * o.probability_pct / 100) for o in opps if o.status not in (OpportunityStatus.WON, OpportunityStatus.LOST))
        won_value = sum(o.estimated_value_cents for o in opps if o.status == OpportunityStatus.WON)

        campaigns = list(self._campaigns.values())
        total_recovered = sum(c.revenue_recovered_cents for c in campaigns)
        total_converted = sum(c.converted for c in campaigns)

        health = list(self._health_scores.values())
        grade_dist = {g.value: 0 for g in HealthGrade}
        for h in health:
            grade_dist[h.grade.value] += 1

        exp = self._expansion
        latest_nrr = exp[-1].net_revenue_retention_pct if exp else 100.0

        return {
            "pipeline_value_cents": pipeline_value,
            "pipeline_value_display": format_cents(pipeline_value),
            "weighted_pipeline_cents": weighted_value,
            "weighted_pipeline_display": format_cents(weighted_value),
            "won_revenue_cents": won_value,
            "won_revenue_display": format_cents(won_value),
            "active_opportunities": sum(1 for o in opps if o.status in (OpportunityStatus.IDENTIFIED, OpportunityStatus.CONTACTED, OpportunityStatus.IN_PROGRESS)),
            "win_back_recovered_cents": total_recovered,
            "win_back_recovered_display": format_cents(total_recovered),
            "win_back_conversions": total_converted,
            "health_distribution": grade_dist,
            "net_revenue_retention_pct": latest_nrr,
            "pricing_recommendations": len(self._recommendations),
        }


# Singleton
optimization_engine = OptimizationEngine()
