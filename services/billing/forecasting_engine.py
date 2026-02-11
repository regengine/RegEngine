"""
Billing Service — Forecasting & Advanced Analytics Engine

Predictive analytics: MRR/ARR forecasting with confidence intervals,
churn prediction scoring, customer lifetime value (CLV) modeling,
cohort retention analysis, and revenue trend detection.
In-memory with realistic seeded data.
"""

from __future__ import annotations

import structlog
import math
import random
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4
from enum import Enum
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

random.seed(42)  # Reproducible analytics


# ── Enums ──────────────────────────────────────────────────────────

class ChurnRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TrendDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


class CohortPeriod(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


# ── Models ─────────────────────────────────────────────────────────

class MRRForecast(BaseModel):
    month: str
    predicted_mrr_cents: int
    lower_bound_cents: int
    upper_bound_cents: int
    confidence: float
    growth_rate_pct: float


class ChurnScore(BaseModel):
    tenant_id: str
    tenant_name: str
    risk: ChurnRisk
    score: float  # 0-100, higher = more likely to churn
    signals: list[str]
    recommended_action: str
    last_payment_at: datetime
    usage_trend: TrendDirection


class CLVEstimate(BaseModel):
    tenant_id: str
    tenant_name: str
    plan: str
    monthly_revenue_cents: int
    months_active: int
    predicted_months_remaining: int
    lifetime_value_cents: int
    lifetime_value_display: str


class CohortData(BaseModel):
    cohort: str  # e.g. "2025-Q3"
    initial_count: int
    retention_rates: list[float]  # % retained at month 1, 2, 3...
    avg_revenue_per_user_cents: int
    total_revenue_cents: int


class RevenueAnomaly(BaseModel):
    id: str = Field(default_factory=lambda: f"anom_{uuid4().hex[:8]}")
    metric: str
    description: str
    severity: str
    detected_at: datetime
    value: float
    expected_value: float
    deviation_pct: float


# ── Forecasting Engine ─────────────────────────────────────────────

class ForecastingEngine:
    """Advanced billing analytics and predictive modeling."""

    def __init__(self):
        self._historical_mrr: list[dict] = []
        self._churn_scores: dict[str, ChurnScore] = {}
        self._clv_estimates: dict[str, CLVEstimate] = {}
        self._cohorts: list[CohortData] = []
        self._anomalies: list[RevenueAnomaly] = []
        self._seed_demo_data()

    def _seed_demo_data(self):
        now = datetime.utcnow()

        # Historical MRR (12 months)
        base_mrr = 85_000_00  # $85k
        for i in range(12, 0, -1):
            month = (now - timedelta(days=30 * i))
            growth = 1 + random.uniform(0.02, 0.08)
            base_mrr = int(base_mrr * growth)
            self._historical_mrr.append({
                "month": month.strftime("%Y-%m"),
                "mrr_cents": base_mrr,
                "mrr_display": f"${base_mrr / 100:,.2f}",
                "new_mrr_cents": int(base_mrr * random.uniform(0.05, 0.12)),
                "churned_mrr_cents": int(base_mrr * random.uniform(0.01, 0.04)),
                "expansion_mrr_cents": int(base_mrr * random.uniform(0.02, 0.06)),
                "customers": 45 + i * 3,
            })

        current_mrr = base_mrr

        # Churn scores
        tenants = [
            ("acme_foods", "Acme Foods Inc.", "enterprise", 499_900, 18, ChurnRisk.LOW, 12,
             ["High engagement", "Recent upgrade", "Growing usage"],
             "Upsell to Enterprise+"),
            ("medsecure", "MedSecure Health", "professional", 149_900, 14, ChurnRisk.MEDIUM, 45,
             ["Payment failure", "Declining API usage", "No support tickets"],
             "Schedule customer success call"),
            ("freshleaf", "FreshLeaf Produce", "professional", 149_900, 10, ChurnRisk.LOW, 18,
             ["Consistent usage", "Active integrations", "Positive NPS"],
             "Offer annual contract discount"),
            ("safetyfirst", "SafetyFirst Mfg", "enterprise", 499_900, 8, ChurnRisk.HIGH, 72,
             ["Downgrade scheduled", "Declining usage", "Contract dispute"],
             "Executive intervention required"),
            ("oldco", "OldCo Logistics", "starter", 49_900, 3, ChurnRisk.CRITICAL, 95,
             ["Cancelled subscription", "No recent activity", "Payment failures"],
             "Win-back campaign with 50% discount"),
            ("beta_corp", "BetaCorp Analytics", "enterprise", 499_900, 2, ChurnRisk.MEDIUM, 40,
             ["Trial user", "High initial engagement", "No payment method"],
             "Convert trial with Enterprise offer"),
            ("newco_trial", "NewCo Foods", "professional", 149_900, 1, ChurnRisk.LOW, 15,
             ["Active trial", "Exploring features", "Submitted support ticket"],
             "Guided onboarding call"),
            ("globalfish", "GlobalFish Imports", "enterprise_plus", 999_900, 24, ChurnRisk.LOW, 5,
             ["Flagship customer", "Multi-team usage", "Annual contract"],
             "Strategic account review"),
        ]

        for tid, name, plan, rev, months, risk, score, signals, action in tenants:
            usage_trend = TrendDirection.DOWN if score > 60 else (TrendDirection.FLAT if score > 30 else TrendDirection.UP)
            self._churn_scores[tid] = ChurnScore(
                tenant_id=tid, tenant_name=name, risk=risk, score=score,
                signals=signals, recommended_action=action,
                last_payment_at=now - timedelta(days=random.randint(1, 30)),
                usage_trend=usage_trend,
            )
            predicted_remaining = max(1, int((100 - score) / 100 * 36))
            self._clv_estimates[tid] = CLVEstimate(
                tenant_id=tid, tenant_name=name, plan=plan,
                monthly_revenue_cents=rev, months_active=months,
                predicted_months_remaining=predicted_remaining,
                lifetime_value_cents=rev * (months + predicted_remaining),
                lifetime_value_display=f"${rev * (months + predicted_remaining) / 100:,.2f}",
            )

        # Cohort retention data
        for q in ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1"]:
            initial = random.randint(8, 18)
            rates = [100.0]
            for m in range(1, 7):
                decay = random.uniform(0.88, 0.96)
                rates.append(round(rates[-1] * decay, 1))
            self._cohorts.append(CohortData(
                cohort=q, initial_count=initial, retention_rates=rates,
                avg_revenue_per_user_cents=random.randint(100_000, 400_000),
                total_revenue_cents=initial * random.randint(200_000, 600_000),
            ))

        # Revenue anomalies
        self._anomalies = [
            RevenueAnomaly(
                id="anom_churn_spike", metric="churn_rate",
                description="Monthly churn rate 2.1x higher than 6-month average",
                severity="critical", detected_at=now - timedelta(hours=4),
                value=4.2, expected_value=2.0, deviation_pct=110.0,
            ),
            RevenueAnomaly(
                id="anom_expansion", metric="expansion_mrr",
                description="Expansion MRR 35% above forecast — 3 enterprise upgrades",
                severity="info", detected_at=now - timedelta(days=2),
                value=42_500, expected_value=31_500, deviation_pct=34.9,
            ),
            RevenueAnomaly(
                id="anom_arpu", metric="arpu",
                description="ARPU declining 8% MoM for Starter tier — potential pricing issue",
                severity="warning", detected_at=now - timedelta(days=5),
                value=385, expected_value=419, deviation_pct=-8.1,
            ),
        ]

    # ── MRR Forecasting ───────────────────────────────────────

    def get_mrr_history(self) -> list[dict]:
        """Historical MRR data."""
        return self._historical_mrr

    def forecast_mrr(self, months_ahead: int = 6) -> list[MRRForecast]:
        """Forecast MRR with confidence intervals using trend extrapolation."""
        if len(self._historical_mrr) < 2:
            return []

        recent = self._historical_mrr[-6:]
        avg_growth = sum(
            (recent[i]["mrr_cents"] - recent[i - 1]["mrr_cents"]) / max(recent[i - 1]["mrr_cents"], 1)
            for i in range(1, len(recent))
        ) / max(len(recent) - 1, 1)

        current = self._historical_mrr[-1]["mrr_cents"]
        last_month = datetime.strptime(self._historical_mrr[-1]["month"], "%Y-%m")
        forecasts: list[MRRForecast] = []

        for m in range(1, months_ahead + 1):
            forecast_month = last_month + timedelta(days=30 * m)
            confidence = max(0.60, 0.95 - m * 0.05)
            growth = avg_growth * (1 + random.uniform(-0.15, 0.15))
            predicted = int(current * (1 + growth) ** m)
            margin = int(predicted * (1 - confidence) * 0.8)

            forecasts.append(MRRForecast(
                month=forecast_month.strftime("%Y-%m"),
                predicted_mrr_cents=predicted,
                lower_bound_cents=predicted - margin,
                upper_bound_cents=predicted + margin,
                confidence=round(confidence, 2),
                growth_rate_pct=round(growth * 100, 1),
            ))

        return forecasts

    # ── Churn Prediction ───────────────────────────────────────

    def get_churn_scores(self, risk: ChurnRisk | None = None) -> list[ChurnScore]:
        scores = list(self._churn_scores.values())
        if risk:
            scores = [s for s in scores if s.risk == risk]
        return sorted(scores, key=lambda s: s.score, reverse=True)

    def get_churn_overview(self) -> dict:
        scores = list(self._churn_scores.values())
        by_risk = {r.value: 0 for r in ChurnRisk}
        for s in scores:
            by_risk[s.risk.value] += 1

        at_risk_revenue = sum(
            self._clv_estimates[s.tenant_id].monthly_revenue_cents
            for s in scores if s.risk in (ChurnRisk.HIGH, ChurnRisk.CRITICAL)
        )

        return {
            "total_scored": len(scores),
            "risk_distribution": by_risk,
            "avg_score": round(sum(s.score for s in scores) / max(len(scores), 1), 1),
            "at_risk_revenue_cents": at_risk_revenue,
            "at_risk_revenue_display": f"${at_risk_revenue / 100:,.2f}",
            "high_risk_tenants": [
                {"tenant": s.tenant_name, "score": s.score, "action": s.recommended_action}
                for s in scores if s.risk in (ChurnRisk.HIGH, ChurnRisk.CRITICAL)
            ],
        }

    # ── Customer Lifetime Value ─────────────────────────────────

    def get_clv_estimates(self, sort_by: str = "lifetime_value") -> list[CLVEstimate]:
        estimates = list(self._clv_estimates.values())
        if sort_by == "lifetime_value":
            return sorted(estimates, key=lambda e: e.lifetime_value_cents, reverse=True)
        return sorted(estimates, key=lambda e: e.predicted_months_remaining, reverse=True)

    def get_clv_summary(self) -> dict:
        estimates = list(self._clv_estimates.values())
        total_clv = sum(e.lifetime_value_cents for e in estimates)
        avg_clv = total_clv // max(len(estimates), 1)

        by_plan: dict[str, dict] = {}
        for e in estimates:
            if e.plan not in by_plan:
                by_plan[e.plan] = {"count": 0, "total_clv_cents": 0}
            by_plan[e.plan]["count"] += 1
            by_plan[e.plan]["total_clv_cents"] += e.lifetime_value_cents

        for v in by_plan.values():
            v["avg_clv_cents"] = v["total_clv_cents"] // max(v["count"], 1)
            v["avg_clv_display"] = f"${v['avg_clv_cents'] / 100:,.2f}"

        return {
            "total_customers": len(estimates),
            "total_clv_cents": total_clv,
            "total_clv_display": f"${total_clv / 100:,.2f}",
            "avg_clv_cents": avg_clv,
            "avg_clv_display": f"${avg_clv / 100:,.2f}",
            "by_plan": by_plan,
            "top_customers": [
                {"tenant": e.tenant_name, "clv": e.lifetime_value_display, "plan": e.plan}
                for e in sorted(estimates, key=lambda e: e.lifetime_value_cents, reverse=True)[:5]
            ],
        }

    # ── Cohort Analysis ─────────────────────────────────────────

    def get_cohorts(self) -> list[CohortData]:
        return self._cohorts

    def get_retention_matrix(self) -> dict:
        """Retention heatmap data."""
        matrix = {}
        for c in self._cohorts:
            matrix[c.cohort] = {
                "initial": c.initial_count,
                "rates": c.retention_rates,
                "arpu_cents": c.avg_revenue_per_user_cents,
            }
        avg_retention = [0.0] * 7
        for c in self._cohorts:
            for i, r in enumerate(c.retention_rates[:7]):
                avg_retention[i] += r / len(self._cohorts)
        return {
            "cohorts": matrix,
            "avg_retention": [round(r, 1) for r in avg_retention],
            "best_cohort": max(self._cohorts, key=lambda c: c.retention_rates[-1]).cohort,
            "worst_cohort": min(self._cohorts, key=lambda c: c.retention_rates[-1]).cohort,
        }

    # ── Revenue Anomalies ───────────────────────────────────────

    def get_anomalies(self) -> list[RevenueAnomaly]:
        return sorted(self._anomalies, key=lambda a: a.detected_at, reverse=True)

    # ── Executive Summary ───────────────────────────────────────

    def get_executive_summary(self) -> dict:
        hist = self._historical_mrr
        current_mrr = hist[-1]["mrr_cents"] if hist else 0
        prev_mrr = hist[-2]["mrr_cents"] if len(hist) >= 2 else current_mrr
        growth = (current_mrr - prev_mrr) / max(prev_mrr, 1) * 100

        forecasts = self.forecast_mrr(3)
        churn = self.get_churn_overview()
        clv = self.get_clv_summary()

        return {
            "current_mrr_cents": current_mrr,
            "current_mrr_display": f"${current_mrr / 100:,.2f}",
            "mrr_growth_pct": round(growth, 1),
            "arr_cents": current_mrr * 12,
            "arr_display": f"${current_mrr * 12 / 100:,.2f}",
            "forecast_3mo": {
                "predicted_cents": forecasts[2].predicted_mrr_cents if len(forecasts) >= 3 else 0,
                "confidence": forecasts[2].confidence if len(forecasts) >= 3 else 0,
            },
            "churn_risk_summary": churn["risk_distribution"],
            "at_risk_revenue": churn["at_risk_revenue_display"],
            "total_clv": clv["total_clv_display"],
            "avg_clv": clv["avg_clv_display"],
            "anomalies_count": len(self._anomalies),
            "critical_anomalies": sum(1 for a in self._anomalies if a.severity == "critical"),
        }


# Singleton
forecasting_engine = ForecastingEngine()
