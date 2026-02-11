"""
Billing Service — Subscription Lifecycle Engine

Manages plan changes (upgrades, downgrades), proration calculations,
trial management, cancellation workflows, and subscription event history.
In-memory store for sandbox mode.
"""

from __future__ import annotations

import structlog
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4
from enum import Enum
from pydantic import BaseModel, Field

from utils import format_cents

logger = structlog.get_logger(__name__)


# ── Enums ──────────────────────────────────────────────────────────

class ChangeType(str, Enum):
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    ADDON = "addon"
    CANCELLATION = "cancellation"
    REACTIVATION = "reactivation"
    TRIAL_START = "trial_start"
    TRIAL_END = "trial_end"


class ChangeStatus(str, Enum):
    PENDING = "pending"
    APPLIED = "applied"
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"


class CancellationReason(str, Enum):
    TOO_EXPENSIVE = "too_expensive"
    MISSING_FEATURES = "missing_features"
    SWITCHING_COMPETITOR = "switching_competitor"
    NO_LONGER_NEEDED = "no_longer_needed"
    POOR_SUPPORT = "poor_support"
    OTHER = "other"


# ── Plan Catalog ───────────────────────────────────────────────────

PLAN_CATALOG = {
    "starter": {"name": "Starter", "monthly_cents": 49_900, "annual_cents": 479_000, "tier": 1},
    "professional": {"name": "Professional", "monthly_cents": 149_900, "annual_cents": 1_439_000, "tier": 2},
    "enterprise": {"name": "Enterprise", "monthly_cents": 499_900, "annual_cents": 4_799_000, "tier": 3},
    "enterprise_plus": {"name": "Enterprise+", "monthly_cents": 999_900, "annual_cents": 9_599_000, "tier": 4},
}


# ── Models ─────────────────────────────────────────────────────────

class ProrationResult(BaseModel):
    """Proration calculation for a mid-cycle plan change."""
    days_remaining: int
    days_in_period: int
    old_plan_credit_cents: int
    new_plan_charge_cents: int
    net_amount_cents: int  # positive = charge, negative = credit
    net_display: str = ""


class PlanChange(BaseModel):
    id: str = Field(default_factory=lambda: f"chg_{uuid4().hex[:10]}")
    tenant_id: str
    tenant_name: str
    change_type: ChangeType
    status: ChangeStatus = ChangeStatus.APPLIED
    # Plan details
    from_plan: str
    to_plan: str
    from_plan_name: str = ""
    to_plan_name: str = ""
    # Proration
    proration: Optional[ProrationResult] = None
    # Cancellation specifics
    cancel_reason: Optional[CancellationReason] = None
    cancel_feedback: str = ""
    effective_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TrialInfo(BaseModel):
    tenant_id: str
    tenant_name: str
    plan: str
    plan_name: str = ""
    trial_start: datetime
    trial_end: datetime
    days_remaining: int
    converted: bool = False


# ── Lifecycle Engine ───────────────────────────────────────────────

class LifecycleEngine:
    """Subscription plan change and lifecycle management."""

    def __init__(self):
        self._changes: dict[str, PlanChange] = {}
        self._trials: dict[str, TrialInfo] = {}
        self._seed_demo_data()

    def _seed_demo_data(self):
        now = datetime.utcnow()

        changes = [
            PlanChange(
                id="chg_acme_up01", tenant_id="acme_foods", tenant_name="Acme Foods Inc.",
                change_type=ChangeType.UPGRADE, from_plan="professional", to_plan="enterprise",
                from_plan_name="Professional", to_plan_name="Enterprise",
                proration=ProrationResult(
                    days_remaining=18, days_in_period=30,
                    old_plan_credit_cents=89_940, new_plan_charge_cents=299_940,
                    net_amount_cents=210_000, net_display="$2,100.00",
                ),
                created_at=now - timedelta(days=12),
            ),
            PlanChange(
                id="chg_med_up01", tenant_id="medsecure", tenant_name="MedSecure Health",
                change_type=ChangeType.UPGRADE, from_plan="starter", to_plan="professional",
                from_plan_name="Starter", to_plan_name="Professional",
                proration=ProrationResult(
                    days_remaining=22, days_in_period=30,
                    old_plan_credit_cents=36_593, new_plan_charge_cents=109_927,
                    net_amount_cents=73_334, net_display="$733.34",
                ),
                created_at=now - timedelta(days=25),
            ),
            PlanChange(
                id="chg_old_cancel", tenant_id="oldco", tenant_name="OldCo Logistics",
                change_type=ChangeType.CANCELLATION, from_plan="starter", to_plan="none",
                from_plan_name="Starter", to_plan_name="Cancelled",
                cancel_reason=CancellationReason.TOO_EXPENSIVE,
                cancel_feedback="Budget cuts forced us to reduce tooling spend.",
                created_at=now - timedelta(days=45),
            ),
            PlanChange(
                id="chg_safety_down", tenant_id="safetyfirst", tenant_name="SafetyFirst Manufacturing",
                change_type=ChangeType.DOWNGRADE, from_plan="enterprise", to_plan="professional",
                from_plan_name="Enterprise", to_plan_name="Professional",
                status=ChangeStatus.SCHEDULED,
                effective_at=now + timedelta(days=15),
                proration=ProrationResult(
                    days_remaining=15, days_in_period=30,
                    old_plan_credit_cents=249_950, new_plan_charge_cents=74_950,
                    net_amount_cents=-175_000, net_display="-$1,750.00",
                ),
                created_at=now - timedelta(days=2),
            ),
            PlanChange(
                id="chg_fresh_addon", tenant_id="freshleaf", tenant_name="FreshLeaf Produce",
                change_type=ChangeType.ADDON, from_plan="professional", to_plan="professional",
                from_plan_name="Professional", to_plan_name="Professional + FDA Export",
                created_at=now - timedelta(days=8),
            ),
        ]
        for c in changes:
            self._changes[c.id] = c

        # Active trials
        trials = [
            TrialInfo(
                tenant_id="newco_trial", tenant_name="NewCo Foods",
                plan="professional", plan_name="Professional",
                trial_start=now - timedelta(days=7), trial_end=now + timedelta(days=7),
                days_remaining=7,
            ),
            TrialInfo(
                tenant_id="beta_corp", tenant_name="BetaCorp Analytics",
                plan="enterprise", plan_name="Enterprise",
                trial_start=now - timedelta(days=12), trial_end=now + timedelta(days=2),
                days_remaining=2,
            ),
            TrialInfo(
                tenant_id="converted_inc", tenant_name="ConvertedInc",
                plan="starter", plan_name="Starter",
                trial_start=now - timedelta(days=20), trial_end=now - timedelta(days=6),
                days_remaining=0, converted=True,
            ),
        ]
        for t in trials:
            self._trials[t.tenant_id] = t

    # ── Plan Changes ──────────────────────────────────────────

    def calculate_proration(self, from_plan: str, to_plan: str,
                            days_remaining: int, days_in_period: int = 30) -> ProrationResult:
        """Calculate proration for a mid-cycle plan change."""
        old_p = PLAN_CATALOG.get(from_plan)
        new_p = PLAN_CATALOG.get(to_plan)
        if not old_p or not new_p:
            raise ValueError(f"Unknown plan: {from_plan} or {to_plan}")

        ratio = days_remaining / days_in_period
        old_credit = int(old_p["monthly_cents"] * ratio)
        new_charge = int(new_p["monthly_cents"] * ratio)
        net = new_charge - old_credit

        return ProrationResult(
            days_remaining=days_remaining,
            days_in_period=days_in_period,
            old_plan_credit_cents=old_credit,
            new_plan_charge_cents=new_charge,
            net_amount_cents=net,
            net_display=format_cents(abs(net)) if net >= 0 else f"-{format_cents(abs(net))}",
        )

    def change_plan(self, tenant_id: str, tenant_name: str,
                    from_plan: str, to_plan: str,
                    days_remaining: int = 15, schedule: bool = False,
                    cancel_reason: CancellationReason | None = None,
                    cancel_feedback: str = "") -> PlanChange:
        """Execute or schedule a plan change."""
        old_p = PLAN_CATALOG.get(from_plan, {})
        new_p = PLAN_CATALOG.get(to_plan, {})

        # Determine change type
        if to_plan == "none" or cancel_reason:
            change_type = ChangeType.CANCELLATION
        elif not old_p or not new_p:
            change_type = ChangeType.ADDON
        elif new_p.get("tier", 0) > old_p.get("tier", 0):
            change_type = ChangeType.UPGRADE
        elif new_p.get("tier", 0) < old_p.get("tier", 0):
            change_type = ChangeType.DOWNGRADE
        else:
            change_type = ChangeType.ADDON

        proration = None
        if from_plan in PLAN_CATALOG and to_plan in PLAN_CATALOG:
            proration = self.calculate_proration(from_plan, to_plan, days_remaining)

        change = PlanChange(
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            change_type=change_type,
            status=ChangeStatus.SCHEDULED if schedule else ChangeStatus.APPLIED,
            from_plan=from_plan,
            to_plan=to_plan,
            from_plan_name=old_p.get("name", from_plan),
            to_plan_name=new_p.get("name", to_plan) if to_plan != "none" else "Cancelled",
            proration=proration,
            cancel_reason=cancel_reason,
            cancel_feedback=cancel_feedback,
            effective_at=datetime.utcnow() + timedelta(days=days_remaining) if schedule else datetime.utcnow(),
        )
        self._changes[change.id] = change
        logger.info("plan_changed", tenant=tenant_name, type=change_type.value, to=to_plan)
        return change

    def list_changes(self, tenant_id: str | None = None,
                     change_type: ChangeType | None = None) -> list[PlanChange]:
        changes = list(self._changes.values())
        if tenant_id:
            changes = [c for c in changes if c.tenant_id == tenant_id]
        if change_type:
            changes = [c for c in changes if c.change_type == change_type]
        return sorted(changes, key=lambda c: c.created_at, reverse=True)

    def get_change(self, change_id: str) -> Optional[PlanChange]:
        return self._changes.get(change_id)

    # ── Trials ─────────────────────────────────────────────────

    def list_trials(self, active_only: bool = False) -> list[TrialInfo]:
        trials = list(self._trials.values())
        if active_only:
            trials = [t for t in trials if t.days_remaining > 0 and not t.converted]
        return sorted(trials, key=lambda t: t.days_remaining)

    def start_trial(self, tenant_id: str, tenant_name: str,
                    plan: str, days: int = 14) -> TrialInfo:
        plan_info = PLAN_CATALOG.get(plan)
        if not plan_info:
            raise ValueError(f"Unknown plan: {plan}")
        trial = TrialInfo(
            tenant_id=tenant_id, tenant_name=tenant_name,
            plan=plan, plan_name=plan_info["name"],
            trial_start=datetime.utcnow(),
            trial_end=datetime.utcnow() + timedelta(days=days),
            days_remaining=days,
        )
        self._trials[tenant_id] = trial
        logger.info("trial_started", tenant=tenant_name, plan=plan, days=days)
        return trial

    # ── Summary ────────────────────────────────────────────────

    def get_summary(self) -> dict:
        changes = list(self._changes.values())
        trials = list(self._trials.values())
        active_trials = [t for t in trials if t.days_remaining > 0 and not t.converted]
        upgrades = [c for c in changes if c.change_type == ChangeType.UPGRADE]
        downgrades = [c for c in changes if c.change_type == ChangeType.DOWNGRADE]
        cancellations = [c for c in changes if c.change_type == ChangeType.CANCELLATION]

        cancel_reasons: dict[str, int] = {}
        for c in cancellations:
            reason = c.cancel_reason.value if c.cancel_reason else "other"
            cancel_reasons[reason] = cancel_reasons.get(reason, 0) + 1

        net_mrr_impact = sum(
            (c.proration.net_amount_cents if c.proration else 0) for c in changes
            if c.change_type in (ChangeType.UPGRADE, ChangeType.DOWNGRADE)
        )

        return {
            "total_changes": len(changes),
            "upgrades": len(upgrades),
            "downgrades": len(downgrades),
            "cancellations": len(cancellations),
            "active_trials": len(active_trials),
            "trial_conversion_rate": round(
                sum(1 for t in trials if t.converted) / max(len(trials), 1) * 100, 1
            ),
            "net_mrr_impact_cents": net_mrr_impact,
            "net_mrr_impact_display": format_cents(abs(net_mrr_impact)) if net_mrr_impact >= 0 else f"-{format_cents(abs(net_mrr_impact))}",
            "cancel_reasons": cancel_reasons,
            "plan_catalog": {k: {"name": v["name"], "monthly": format_cents(v['monthly_cents'])} for k, v in PLAN_CATALOG.items()},
        }


# Singleton
lifecycle_engine = LifecycleEngine()
