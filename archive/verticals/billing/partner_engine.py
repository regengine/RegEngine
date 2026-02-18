"""
Billing Service — Partner Portal & Commission Management Engine

Handles partner registration, referral tracking, commission calculation,
and payout management. In-memory store for sandbox mode.
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

class PartnerTier(str, Enum):
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class PartnerStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    SUSPENDED = "suspended"
    CHURNED = "churned"


class PayoutStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PAID = "paid"
    FAILED = "failed"


# ── Models ─────────────────────────────────────────────────────────

class Partner(BaseModel):
    id: str = Field(default_factory=lambda: f"ptr_{uuid4().hex[:12]}")
    name: str
    company: str
    email: str
    tier: PartnerTier = PartnerTier.SILVER
    status: PartnerStatus = PartnerStatus.ACTIVE
    referral_code: str = ""
    # Commission
    commission_rate: float = 0.10  # 10% default
    # Metrics
    total_referrals: int = 0
    active_referrals: int = 0
    total_earned_cents: int = 0
    total_paid_cents: int = 0
    pending_payout_cents: int = 0
    # Dates
    joined_at: datetime = Field(default_factory=datetime.utcnow)
    last_referral_at: Optional[datetime] = None


class Referral(BaseModel):
    id: str = Field(default_factory=lambda: f"ref_{uuid4().hex[:12]}")
    partner_id: str
    tenant_id: str
    tenant_name: str
    tier_id: str
    monthly_value_cents: int = 0
    commission_cents: int = 0
    status: str = "active"  # active | churned | trial
    referred_at: datetime = Field(default_factory=datetime.utcnow)


class Payout(BaseModel):
    id: str = Field(default_factory=lambda: f"po_{uuid4().hex[:12]}")
    partner_id: str
    partner_name: str
    amount_cents: int
    status: PayoutStatus = PayoutStatus.PENDING
    period_start: datetime = Field(default_factory=datetime.utcnow)
    period_end: datetime = Field(default_factory=datetime.utcnow)
    referral_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    paid_at: Optional[datetime] = None


# ── Commission Tiers ───────────────────────────────────────────────

COMMISSION_TIERS = {
    PartnerTier.SILVER: {"rate": 0.10, "min_referrals": 0, "bonus_pct": 0},
    PartnerTier.GOLD: {"rate": 0.15, "min_referrals": 5, "bonus_pct": 0.02},
    PartnerTier.PLATINUM: {"rate": 0.20, "min_referrals": 15, "bonus_pct": 0.05},
}


# ── Partner Engine ─────────────────────────────────────────────────

class PartnerEngine:
    """Partner ecosystem management."""

    def __init__(self):
        self._partners: dict[str, Partner] = {}
        self._referrals: dict[str, Referral] = {}
        self._payouts: dict[str, Payout] = {}
        self._seed_demo_data()

    def _seed_demo_data(self):
        """Create realistic partner ecosystem."""
        now = datetime.utcnow()

        partners = [
            Partner(
                id="ptr_compliance01", name="Jordan Mitchell", company="CompliancePro Consulting",
                email="jordan@compliancepro.com", tier=PartnerTier.PLATINUM, status=PartnerStatus.ACTIVE,
                referral_code="COMPRO20", commission_rate=0.20,
                total_referrals=18, active_referrals=14,
                total_earned_cents=864_000, total_paid_cents=720_000, pending_payout_cents=144_000,
                joined_at=now - timedelta(days=365), last_referral_at=now - timedelta(days=8),
            ),
            Partner(
                id="ptr_foodsafe02", name="Emily Chen", company="FoodSafe Solutions",
                email="emily@foodsafe.io", tier=PartnerTier.GOLD, status=PartnerStatus.ACTIVE,
                referral_code="FSAFE15", commission_rate=0.15,
                total_referrals=9, active_referrals=7,
                total_earned_cents=315_000, total_paid_cents=270_000, pending_payout_cents=45_000,
                joined_at=now - timedelta(days=240), last_referral_at=now - timedelta(days=22),
            ),
            Partner(
                id="ptr_techint03", name="Marcus Williams", company="TechIntegrations LLC",
                email="marcus@techint.dev", tier=PartnerTier.SILVER, status=PartnerStatus.ACTIVE,
                referral_code="TECH10", commission_rate=0.10,
                total_referrals=3, active_referrals=3,
                total_earned_cents=54_000, total_paid_cents=36_000, pending_payout_cents=18_000,
                joined_at=now - timedelta(days=90), last_referral_at=now - timedelta(days=45),
            ),
            Partner(
                id="ptr_regadv04", name="Sarah Park", company="RegAdvisory Group",
                email="sarah@regadvisory.com", tier=PartnerTier.GOLD, status=PartnerStatus.ACTIVE,
                referral_code="REGADV15", commission_rate=0.15,
                total_referrals=7, active_referrals=5,
                total_earned_cents=210_000, total_paid_cents=180_000, pending_payout_cents=30_000,
                joined_at=now - timedelta(days=180), last_referral_at=now - timedelta(days=15),
            ),
        ]

        for p in partners:
            self._partners[p.id] = p

        # Seed referrals
        referrals = [
            Referral(partner_id="ptr_compliance01", tenant_id="acme_foods", tenant_name="Acme Foods Inc.",
                     tier_id="enterprise", monthly_value_cents=500_000, commission_cents=100_000,
                     referred_at=now - timedelta(days=180)),
            Referral(partner_id="ptr_compliance01", tenant_id="freshleaf", tenant_name="FreshLeaf Produce",
                     tier_id="scale", monthly_value_cents=150_000, commission_cents=30_000,
                     referred_at=now - timedelta(days=90)),
            Referral(partner_id="ptr_foodsafe02", tenant_id="medsecure", tenant_name="MedSecure Health",
                     tier_id="scale", monthly_value_cents=180_000, commission_cents=27_000,
                     referred_at=now - timedelta(days=120)),
            Referral(partner_id="ptr_techint03", tenant_id="energyflow", tenant_name="EnergyFlow Corp",
                     tier_id="growth", monthly_value_cents=80_000, commission_cents=8_000,
                     referred_at=now - timedelta(days=60)),
        ]
        for r in referrals:
            self._referrals[r.id] = r

        # Seed payouts
        payouts = [
            Payout(partner_id="ptr_compliance01", partner_name="CompliancePro Consulting",
                   amount_cents=240_000, status=PayoutStatus.PAID,
                   period_start=now - timedelta(days=60), period_end=now - timedelta(days=30),
                   referral_count=14, paid_at=now - timedelta(days=25)),
            Payout(partner_id="ptr_foodsafe02", partner_name="FoodSafe Solutions",
                   amount_cents=90_000, status=PayoutStatus.PAID,
                   period_start=now - timedelta(days=60), period_end=now - timedelta(days=30),
                   referral_count=7, paid_at=now - timedelta(days=25)),
            Payout(partner_id="ptr_compliance01", partner_name="CompliancePro Consulting",
                   amount_cents=144_000, status=PayoutStatus.PENDING,
                   period_start=now - timedelta(days=30), period_end=now,
                   referral_count=14),
        ]
        for po in payouts:
            self._payouts[po.id] = po

    # ── Partner CRUD ───────────────────────────────────────────

    def register_partner(self, name: str, company: str, email: str,
                         tier: PartnerTier = PartnerTier.SILVER) -> Partner:
        """Register a new channel partner."""
        code = company.upper().replace(" ", "")[:6] + str(int(COMMISSION_TIERS[tier]["rate"] * 100))
        rate = COMMISSION_TIERS[tier]["rate"]

        partner = Partner(
            name=name, company=company, email=email,
            tier=tier, referral_code=code, commission_rate=rate,
        )
        self._partners[partner.id] = partner
        logger.info("partner_registered", partner_id=partner.id, company=company)
        return partner

    def get_partner(self, partner_id: str) -> Optional[Partner]:
        return self._partners.get(partner_id)

    def list_partners(self, tier: PartnerTier | None = None,
                      status: PartnerStatus | None = None) -> list[Partner]:
        partners = list(self._partners.values())
        if tier:
            partners = [p for p in partners if p.tier == tier]
        if status:
            partners = [p for p in partners if p.status == status]
        return sorted(partners, key=lambda p: p.total_earned_cents, reverse=True)

    # ── Referral Tracking ──────────────────────────────────────

    def record_referral(self, partner_id: str, tenant_id: str, tenant_name: str,
                        tier_id: str, monthly_value_cents: int) -> Referral:
        """Record a partner referral."""
        partner = self._partners.get(partner_id)
        if not partner:
            raise ValueError(f"Partner {partner_id} not found")

        commission = int(monthly_value_cents * partner.commission_rate)
        referral = Referral(
            partner_id=partner_id,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            tier_id=tier_id,
            monthly_value_cents=monthly_value_cents,
            commission_cents=commission,
        )
        self._referrals[referral.id] = referral

        partner.total_referrals += 1
        partner.active_referrals += 1
        partner.pending_payout_cents += commission
        partner.last_referral_at = datetime.utcnow()

        # Auto-upgrade tier
        if partner.total_referrals >= COMMISSION_TIERS[PartnerTier.PLATINUM]["min_referrals"]:
            partner.tier = PartnerTier.PLATINUM
            partner.commission_rate = COMMISSION_TIERS[PartnerTier.PLATINUM]["rate"]
        elif partner.total_referrals >= COMMISSION_TIERS[PartnerTier.GOLD]["min_referrals"]:
            partner.tier = PartnerTier.GOLD
            partner.commission_rate = COMMISSION_TIERS[PartnerTier.GOLD]["rate"]

        logger.info("referral_recorded", partner_id=partner_id, tenant=tenant_name, commission=commission)
        return referral

    def list_referrals(self, partner_id: str | None = None) -> list[Referral]:
        referrals = list(self._referrals.values())
        if partner_id:
            referrals = [r for r in referrals if r.partner_id == partner_id]
        return sorted(referrals, key=lambda r: r.referred_at, reverse=True)

    # ── Payout Management ──────────────────────────────────────

    def create_payout(self, partner_id: str) -> Payout:
        """Create a payout for a partner's pending commissions."""
        partner = self._partners.get(partner_id)
        if not partner:
            raise ValueError(f"Partner {partner_id} not found")
        if partner.pending_payout_cents <= 0:
            raise ValueError("No pending commissions to pay")

        now = datetime.utcnow()
        payout = Payout(
            partner_id=partner_id,
            partner_name=partner.company,
            amount_cents=partner.pending_payout_cents,
            status=PayoutStatus.PENDING,
            period_start=now - timedelta(days=30),
            period_end=now,
            referral_count=partner.active_referrals,
        )
        self._payouts[payout.id] = payout
        logger.info("payout_created", payout_id=payout.id, partner=partner.company, amount=payout.amount_cents)
        return payout

    def process_payout(self, payout_id: str) -> Payout:
        """Mark a payout as paid."""
        payout = self._payouts.get(payout_id)
        if not payout:
            raise ValueError(f"Payout {payout_id} not found")

        partner = self._partners.get(payout.partner_id)
        if partner:
            partner.total_paid_cents += payout.amount_cents
            partner.pending_payout_cents = max(0, partner.pending_payout_cents - payout.amount_cents)

        payout.status = PayoutStatus.PAID
        payout.paid_at = datetime.utcnow()
        logger.info("payout_processed", payout_id=payout_id)
        return payout

    def list_payouts(self, partner_id: str | None = None) -> list[Payout]:
        payouts = list(self._payouts.values())
        if partner_id:
            payouts = [p for p in payouts if p.partner_id == partner_id]
        return sorted(payouts, key=lambda p: p.created_at, reverse=True)

    # ── Program Summary ────────────────────────────────────────

    def get_program_summary(self) -> dict:
        """Partner program performance overview."""
        partners = list(self._partners.values())
        active = [p for p in partners if p.status == PartnerStatus.ACTIVE]

        total_earned = sum(p.total_earned_cents for p in partners)
        total_paid = sum(p.total_paid_cents for p in partners)
        total_pending = sum(p.pending_payout_cents for p in partners)
        total_referrals = sum(p.total_referrals for p in partners)
        active_referrals = sum(p.active_referrals for p in partners)

        # Revenue through partners
        partner_revenue = sum(r.monthly_value_cents for r in self._referrals.values()
                             if r.status == "active")

        tier_breakdown = {}
        for tier in PartnerTier:
            tier_partners = [p for p in active if p.tier == tier]
            tier_breakdown[tier.value] = {
                "count": len(tier_partners),
                "total_referrals": sum(p.total_referrals for p in tier_partners),
                "total_earned_cents": sum(p.total_earned_cents for p in tier_partners),
                "commission_rate": f"{int(COMMISSION_TIERS[tier]['rate'] * 100)}%",
            }

        return {
            "total_partners": len(partners),
            "active_partners": len(active),
            "total_referrals": total_referrals,
            "active_referrals": active_referrals,
            "total_earned_cents": total_earned,
            "total_earned_display": format_cents(total_earned),
            "total_paid_cents": total_paid,
            "total_paid_display": format_cents(total_paid),
            "pending_payouts_cents": total_pending,
            "pending_payouts_display": format_cents(total_pending),
            "partner_sourced_revenue_cents": partner_revenue,
            "partner_sourced_revenue_display": format_cents(partner_revenue),
            "tier_breakdown": tier_breakdown,
        }


# Singleton
partner_engine = PartnerEngine()
