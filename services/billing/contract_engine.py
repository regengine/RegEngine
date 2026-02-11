"""
Billing Service — Enterprise Contract Management Engine

Manages the full deal lifecycle: quote generation with discount modeling,
multi-year contracts, SLA tracking with breach detection, and renewal
forecasting. In-memory store for sandbox; production would use Postgres.
"""

from __future__ import annotations

import structlog
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4
from enum import Enum
from pydantic import BaseModel, Field

from models import PRICING_TIERS, BillingCycle

logger = structlog.get_logger(__name__)


# ── Enums ──────────────────────────────────────────────────────────

class DealStage(str, Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    NEGOTIATING = "negotiating"
    APPROVED = "approved"
    ACTIVE = "active"
    RENEWED = "renewed"
    CHURNED = "churned"


class ContractType(str, Enum):
    STANDARD = "standard"      # Self-serve, standard terms
    ENTERPRISE = "enterprise"  # Custom SLA, dedicated support
    CUSTOM = "custom"          # Fully custom pricing & terms


class SLALevel(str, Enum):
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    PREMIUM = "premium"


# ── Models ─────────────────────────────────────────────────────────

class SLATerms(BaseModel):
    level: SLALevel = SLALevel.PROFESSIONAL
    uptime_pct: float = 99.9
    response_time_hours: int = 4
    resolution_time_hours: int = 24
    dedicated_support: bool = False
    phone_support: bool = False
    custom_integrations: int = 0


class DiscountRule(BaseModel):
    type: str  # volume | multi_year | partner | negotiated
    description: str
    pct: float  # Percentage discount (0.0 - 1.0)
    amount_cents: int = 0  # Fixed amount discount


class Quote(BaseModel):
    id: str = Field(default_factory=lambda: f"qt_{uuid4().hex[:12]}")
    contract_id: str
    tier_id: str
    billing_cycle: BillingCycle = BillingCycle.ANNUAL
    term_years: int = 1
    base_price_cents: int = 0
    discounts: list[DiscountRule] = []
    total_discount_pct: float = 0
    total_discount_cents: int = 0
    final_monthly_cents: int = 0
    final_annual_cents: int = 0
    total_contract_value_cents: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    notes: str = ""


class Contract(BaseModel):
    id: str = Field(default_factory=lambda: f"ctr_{uuid4().hex[:12]}")
    tenant_id: str
    tenant_name: str = ""
    tier_id: str = "enterprise"
    contract_type: ContractType = ContractType.ENTERPRISE
    stage: DealStage = DealStage.DRAFT
    sla: SLATerms = Field(default_factory=SLATerms)
    # Financial
    annual_contract_value_cents: int = 0
    total_contract_value_cents: int = 0
    term_years: int = 1
    billing_cycle: BillingCycle = BillingCycle.ANNUAL
    # Lifecycle
    owner: str = "sales@regengine.co"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    renewal_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    # Quotes
    quotes: list[Quote] = []
    notes: str = ""
    custom_terms: dict = {}


# ── SLA Definitions ────────────────────────────────────────────────

SLA_TEMPLATES: dict[str, SLATerms] = {
    "starter": SLATerms(
        level=SLALevel.BASIC,
        uptime_pct=99.5,
        response_time_hours=24,
        resolution_time_hours=72,
    ),
    "growth": SLATerms(
        level=SLALevel.PROFESSIONAL,
        uptime_pct=99.9,
        response_time_hours=4,
        resolution_time_hours=24,
    ),
    "scale": SLATerms(
        level=SLALevel.ENTERPRISE,
        uptime_pct=99.95,
        response_time_hours=2,
        resolution_time_hours=8,
        dedicated_support=True,
        phone_support=True,
        custom_integrations=3,
    ),
    "enterprise": SLATerms(
        level=SLALevel.PREMIUM,
        uptime_pct=99.99,
        response_time_hours=1,
        resolution_time_hours=4,
        dedicated_support=True,
        phone_support=True,
        custom_integrations=10,
    ),
}

# ── Discount Rules ─────────────────────────────────────────────────

DISCOUNT_RULES = {
    "multi_year_2": DiscountRule(type="multi_year", description="2-year commitment", pct=0.10),
    "multi_year_3": DiscountRule(type="multi_year", description="3-year commitment", pct=0.18),
    "volume_50": DiscountRule(type="volume", description="50+ facilities", pct=0.12),
    "volume_100": DiscountRule(type="volume", description="100+ facilities", pct=0.20),
    "partner_channel": DiscountRule(type="partner", description="Channel partner", pct=0.08),
    "strategic": DiscountRule(type="negotiated", description="Strategic account", pct=0.15),
}


# ── Contract Engine ────────────────────────────────────────────────

class ContractEngine:
    """Enterprise contract lifecycle management."""

    def __init__(self):
        self._contracts: dict[str, Contract] = {}
        self._seed_demo_data()

    def _seed_demo_data(self):
        """Create realistic demo deals."""
        now = datetime.utcnow()
        demos = [
            Contract(
                id="ctr_acme001", tenant_id="acme_foods", tenant_name="Acme Foods Inc.",
                tier_id="enterprise", contract_type=ContractType.ENTERPRISE,
                stage=DealStage.ACTIVE, owner="sarah@regengine.co",
                annual_contract_value_cents=150_000_00,
                total_contract_value_cents=450_000_00,
                term_years=3,
                sla=SLA_TEMPLATES["enterprise"],
                start_date=now - timedelta(days=180),
                end_date=now + timedelta(days=915),
                renewal_date=now + timedelta(days=885),
                notes="Flagship customer. Custom FDA 204 integration.",
            ),
            Contract(
                id="ctr_medsec002", tenant_id="medsecure", tenant_name="MedSecure Health",
                tier_id="scale", contract_type=ContractType.ENTERPRISE,
                stage=DealStage.ACTIVE, owner="james@regengine.co",
                annual_contract_value_cents=180_000_00,
                total_contract_value_cents=360_000_00,
                term_years=2,
                sla=SLA_TEMPLATES["scale"],
                start_date=now - timedelta(days=90),
                end_date=now + timedelta(days=640),
                renewal_date=now + timedelta(days=610),
            ),
            Contract(
                id="ctr_global003", tenant_id="globaltech", tenant_name="GlobalTech Solutions",
                tier_id="scale", contract_type=ContractType.STANDARD,
                stage=DealStage.NEGOTIATING, owner="sarah@regengine.co",
                annual_contract_value_cents=60_000_00,
                total_contract_value_cents=60_000_00,
                term_years=1,
                sla=SLA_TEMPLATES["growth"],
                notes="Expanding from Growth tier. Needs SSO.",
            ),
            Contract(
                id="ctr_energy004", tenant_id="energyflow", tenant_name="EnergyFlow Corp",
                tier_id="growth", contract_type=ContractType.STANDARD,
                stage=DealStage.PROPOSED, owner="james@regengine.co",
                annual_contract_value_cents=9_588_00,
                total_contract_value_cents=9_588_00,
                term_years=1,
                sla=SLA_TEMPLATES["growth"],
            ),
            Contract(
                id="ctr_safety005", tenant_id="safetyfirst", tenant_name="SafetyFirst Manufacturing",
                tier_id="enterprise", contract_type=ContractType.ENTERPRISE,
                stage=DealStage.DRAFT, owner="sarah@regengine.co",
                annual_contract_value_cents=120_000_00,
                notes="Manufacturing vertical. Needs on-prem deployment option.",
            ),
            Contract(
                id="ctr_fresh006", tenant_id="freshleaf", tenant_name="FreshLeaf Produce",
                tier_id="scale", contract_type=ContractType.ENTERPRISE,
                stage=DealStage.APPROVED, owner="james@regengine.co",
                annual_contract_value_cents=95_000_00,
                total_contract_value_cents=190_000_00,
                term_years=2,
                sla=SLA_TEMPLATES["scale"],
                start_date=now + timedelta(days=5),
                end_date=now + timedelta(days=735),
                renewal_date=now + timedelta(days=700),
                notes="Signed. Onboarding starts next week.",
            ),
        ]
        for c in demos:
            self._contracts[c.id] = c

    # ── CRUD ───────────────────────────────────────────────────

    def create_contract(self, tenant_id: str, tenant_name: str, tier_id: str,
                        contract_type: ContractType = ContractType.ENTERPRISE,
                        term_years: int = 1, owner: str = "sales@regengine.co",
                        notes: str = "") -> Contract:
        """Create a new deal/contract."""
        sla = SLA_TEMPLATES.get(tier_id, SLA_TEMPLATES["growth"])
        tier = PRICING_TIERS.get(tier_id)
        # Enterprise tier has None price (contact sales) — default to $5,000/mo
        monthly_price = (tier.annual_price or tier.monthly_price or 5000) if tier else 5000
        annual_price = monthly_price * 12 * 100

        contract = Contract(
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            tier_id=tier_id,
            contract_type=contract_type,
            term_years=term_years,
            owner=owner,
            sla=sla,
            annual_contract_value_cents=annual_price,
            total_contract_value_cents=annual_price * term_years,
            notes=notes,
        )
        self._contracts[contract.id] = contract
        logger.info("contract_created", contract_id=contract.id, tenant=tenant_name)
        return contract

    def get_contract(self, contract_id: str) -> Optional[Contract]:
        return self._contracts.get(contract_id)

    def list_contracts(self, stage: Optional[DealStage] = None,
                       owner: Optional[str] = None) -> list[Contract]:
        contracts = list(self._contracts.values())
        if stage:
            contracts = [c for c in contracts if c.stage == stage]
        if owner:
            contracts = [c for c in contracts if c.owner == owner]
        return sorted(contracts, key=lambda c: c.updated_at, reverse=True)

    # ── Stage Transitions ──────────────────────────────────────

    VALID_TRANSITIONS = {
        DealStage.DRAFT: [DealStage.PROPOSED, DealStage.CHURNED],
        DealStage.PROPOSED: [DealStage.NEGOTIATING, DealStage.APPROVED, DealStage.CHURNED],
        DealStage.NEGOTIATING: [DealStage.APPROVED, DealStage.PROPOSED, DealStage.CHURNED],
        DealStage.APPROVED: [DealStage.ACTIVE, DealStage.NEGOTIATING, DealStage.CHURNED],
        DealStage.ACTIVE: [DealStage.RENEWED, DealStage.CHURNED],
        DealStage.RENEWED: [DealStage.ACTIVE, DealStage.CHURNED],
    }

    def advance_stage(self, contract_id: str, new_stage: DealStage) -> Contract:
        """Advance a deal through the pipeline."""
        contract = self._contracts.get(contract_id)
        if not contract:
            raise ValueError(f"Contract {contract_id} not found")

        valid_next = self.VALID_TRANSITIONS.get(contract.stage, [])
        if new_stage not in valid_next:
            raise ValueError(
                f"Cannot transition from {contract.stage.value} to {new_stage.value}. "
                f"Valid: {[s.value for s in valid_next]}"
            )

        contract.stage = new_stage
        contract.updated_at = datetime.utcnow()

        if new_stage == DealStage.ACTIVE and not contract.start_date:
            contract.start_date = datetime.utcnow()
            contract.end_date = contract.start_date + timedelta(days=365 * contract.term_years)
            contract.renewal_date = contract.end_date - timedelta(days=30)

        logger.info("contract_stage_changed", contract_id=contract_id, new_stage=new_stage.value)
        return contract

    # ── Quote Generation ───────────────────────────────────────

    def generate_quote(self, contract_id: str, discount_codes: list[str] | None = None,
                       custom_discount_pct: float = 0, notes: str = "") -> Quote:
        """Generate a quote with discount modeling for a deal."""
        contract = self._contracts.get(contract_id)
        if not contract:
            raise ValueError(f"Contract {contract_id} not found")

        tier = PRICING_TIERS.get(contract.tier_id)
        base_monthly = (tier.annual_price or tier.monthly_price or 5000) * 100 if tier else 500_000
        base_annual = base_monthly * 12

        # Apply discounts
        discounts: list[DiscountRule] = []
        total_discount_pct = 0

        # Multi-year discount
        if contract.term_years >= 3:
            discounts.append(DISCOUNT_RULES["multi_year_3"])
            total_discount_pct += 0.18
        elif contract.term_years >= 2:
            discounts.append(DISCOUNT_RULES["multi_year_2"])
            total_discount_pct += 0.10

        # Explicit discount codes
        for code in (discount_codes or []):
            rule = DISCOUNT_RULES.get(code)
            if rule:
                discounts.append(rule)
                total_discount_pct += rule.pct

        # Custom negotiated discount
        if custom_discount_pct > 0:
            discounts.append(DiscountRule(
                type="negotiated",
                description=f"Custom negotiated discount",
                pct=custom_discount_pct,
            ))
            total_discount_pct += custom_discount_pct

        # Cap total discount at 35%
        total_discount_pct = min(total_discount_pct, 0.35)
        discount_annual_cents = int(base_annual * total_discount_pct)
        final_annual = base_annual - discount_annual_cents
        final_monthly = final_annual // 12
        total_value = final_annual * contract.term_years

        quote = Quote(
            contract_id=contract_id,
            tier_id=contract.tier_id,
            billing_cycle=contract.billing_cycle,
            term_years=contract.term_years,
            base_price_cents=base_annual,
            discounts=discounts,
            total_discount_pct=round(total_discount_pct, 4),
            total_discount_cents=discount_annual_cents,
            final_monthly_cents=final_monthly,
            final_annual_cents=final_annual,
            total_contract_value_cents=total_value,
            expires_at=datetime.utcnow() + timedelta(days=30),
            notes=notes,
        )

        contract.quotes.append(quote)
        contract.annual_contract_value_cents = final_annual
        contract.total_contract_value_cents = total_value
        contract.updated_at = datetime.utcnow()

        logger.info(
            "quote_generated",
            contract_id=contract_id,
            quote_id=quote.id,
            total_value=total_value,
            discount_pct=total_discount_pct,
        )
        return quote

    # ── Pipeline Summary ───────────────────────────────────────

    def get_pipeline(self) -> dict:
        """Summarize deal pipeline by stage."""
        pipeline: dict[str, list[dict]] = {stage.value: [] for stage in DealStage}
        stage_totals: dict[str, int] = {stage.value: 0 for stage in DealStage}

        for contract in self._contracts.values():
            stage = contract.stage.value
            pipeline[stage].append({
                "id": contract.id,
                "tenant_name": contract.tenant_name,
                "tier_id": contract.tier_id,
                "acv_cents": contract.annual_contract_value_cents,
                "acv_display": f"${contract.annual_contract_value_cents / 100:,.0f}",
                "owner": contract.owner,
                "term_years": contract.term_years,
            })
            stage_totals[stage] += contract.annual_contract_value_cents

        total_pipeline_value = sum(
            c.annual_contract_value_cents for c in self._contracts.values()
            if c.stage in (DealStage.PROPOSED, DealStage.NEGOTIATING, DealStage.APPROVED)
        )

        return {
            "pipeline": pipeline,
            "stage_totals": {k: {"count": len(v), "acv_cents": stage_totals[k],
                                  "acv_display": f"${stage_totals[k] / 100:,.0f}"}
                             for k, v in pipeline.items()},
            "total_pipeline_value_cents": total_pipeline_value,
            "total_pipeline_value_display": f"${total_pipeline_value / 100:,.0f}",
            "weighted_pipeline_cents": int(total_pipeline_value * 0.35),
            "weighted_pipeline_display": f"${int(total_pipeline_value * 0.35) / 100:,.0f}",
        }

    # ── SLA Status ─────────────────────────────────────────────

    def get_sla_status(self) -> list[dict]:
        """Check SLA compliance for all active contracts."""
        statuses = []
        for contract in self._contracts.values():
            if contract.stage not in (DealStage.ACTIVE, DealStage.RENEWED):
                continue

            # Simulate real metrics
            actual_uptime = 99.97
            actual_response_hours = 1.5
            actual_resolution_hours = 3.2

            sla = contract.sla
            breaches = []
            if actual_uptime < sla.uptime_pct:
                breaches.append({
                    "metric": "uptime",
                    "target": f"{sla.uptime_pct}%",
                    "actual": f"{actual_uptime}%",
                    "severity": "critical",
                })
            if actual_response_hours > sla.response_time_hours:
                breaches.append({
                    "metric": "response_time",
                    "target": f"{sla.response_time_hours}h",
                    "actual": f"{actual_response_hours}h",
                    "severity": "warning",
                })

            statuses.append({
                "contract_id": contract.id,
                "tenant_name": contract.tenant_name,
                "sla_level": sla.level.value,
                "uptime_target": sla.uptime_pct,
                "uptime_actual": actual_uptime,
                "response_target_hours": sla.response_time_hours,
                "response_actual_hours": actual_response_hours,
                "resolution_target_hours": sla.resolution_time_hours,
                "resolution_actual_hours": actual_resolution_hours,
                "compliance": "passing" if not breaches else "breached",
                "breaches": breaches,
                "breach_count": len(breaches),
            })

        return statuses

    # ── Renewals ───────────────────────────────────────────────

    def get_upcoming_renewals(self, days_ahead: int = 90) -> list[dict]:
        """Identify contracts approaching renewal."""
        now = datetime.utcnow()
        cutoff = now + timedelta(days=days_ahead)
        renewals = []

        for contract in self._contracts.values():
            if contract.stage not in (DealStage.ACTIVE, DealStage.RENEWED):
                continue
            if contract.renewal_date and contract.renewal_date <= cutoff:
                days_until = (contract.renewal_date - now).days
                urgency = "critical" if days_until <= 30 else "warning" if days_until <= 60 else "upcoming"
                renewals.append({
                    "contract_id": contract.id,
                    "tenant_name": contract.tenant_name,
                    "tier_id": contract.tier_id,
                    "acv_cents": contract.annual_contract_value_cents,
                    "acv_display": f"${contract.annual_contract_value_cents / 100:,.0f}",
                    "renewal_date": contract.renewal_date.isoformat(),
                    "days_until_renewal": days_until,
                    "urgency": urgency,
                    "owner": contract.owner,
                })

        return sorted(renewals, key=lambda r: r["days_until_renewal"])


# Singleton
contract_engine = ContractEngine()
