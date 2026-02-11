"""
Billing Service — Tax Engine

Multi-jurisdiction tax calculation, tax profiles, exemptions,
and tax reporting. In-memory store for sandbox mode.
"""

from __future__ import annotations

import structlog
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4
from enum import Enum
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ── Enums ──────────────────────────────────────────────────────────

class TaxType(str, Enum):
    SALES_TAX = "sales_tax"
    VAT = "vat"
    GST = "gst"
    HST = "hst"
    EXEMPT = "exempt"


class ExemptionReason(str, Enum):
    GOVERNMENT = "government"
    NONPROFIT = "nonprofit"
    RESELLER = "reseller"
    EDUCATION = "education"
    HEALTHCARE = "healthcare"


# ── Models ─────────────────────────────────────────────────────────

class TaxJurisdiction(BaseModel):
    id: str
    name: str
    country: str
    state: str = ""
    tax_type: TaxType
    rate: float  # as decimal, e.g. 0.0875
    rate_display: str = ""
    digital_services_rate: Optional[float] = None
    effective_date: datetime = Field(default_factory=datetime.utcnow)


class TaxExemption(BaseModel):
    id: str = Field(default_factory=lambda: f"txe_{uuid4().hex[:8]}")
    tenant_id: str
    tenant_name: str
    jurisdiction_id: str
    reason: ExemptionReason
    certificate_number: str = ""
    valid_from: datetime = Field(default_factory=datetime.utcnow)
    valid_until: Optional[datetime] = None
    verified: bool = False


class TaxCalculation(BaseModel):
    """Result of a tax calculation."""
    jurisdiction_id: str
    jurisdiction_name: str
    tax_type: TaxType
    subtotal_cents: int
    tax_rate: float
    tax_amount_cents: int
    total_cents: int
    is_exempt: bool = False
    exemption_id: Optional[str] = None


class TaxRecord(BaseModel):
    """Historical tax record for reporting."""
    id: str = Field(default_factory=lambda: f"txr_{uuid4().hex[:12]}")
    tenant_id: str
    tenant_name: str
    invoice_id: str
    jurisdiction_id: str
    jurisdiction_name: str
    tax_type: TaxType
    subtotal_cents: int
    tax_rate: float
    tax_amount_cents: int
    period: str  # e.g. "2026-Q1"
    recorded_at: datetime = Field(default_factory=datetime.utcnow)


# ── Tax Jurisdictions Database ─────────────────────────────────────

JURISDICTIONS: dict[str, TaxJurisdiction] = {
    "us_ca": TaxJurisdiction(id="us_ca", name="California", country="US", state="CA",
                              tax_type=TaxType.SALES_TAX, rate=0.0875, rate_display="8.75%"),
    "us_ny": TaxJurisdiction(id="us_ny", name="New York", country="US", state="NY",
                              tax_type=TaxType.SALES_TAX, rate=0.08, rate_display="8.00%"),
    "us_tx": TaxJurisdiction(id="us_tx", name="Texas", country="US", state="TX",
                              tax_type=TaxType.SALES_TAX, rate=0.0625, rate_display="6.25%"),
    "us_fl": TaxJurisdiction(id="us_fl", name="Florida", country="US", state="FL",
                              tax_type=TaxType.SALES_TAX, rate=0.06, rate_display="6.00%"),
    "us_wa": TaxJurisdiction(id="us_wa", name="Washington", country="US", state="WA",
                              tax_type=TaxType.SALES_TAX, rate=0.065, rate_display="6.50%",
                              digital_services_rate=0.065),
    "us_or": TaxJurisdiction(id="us_or", name="Oregon", country="US", state="OR",
                              tax_type=TaxType.EXEMPT, rate=0.0, rate_display="0.00%"),
    "us_de": TaxJurisdiction(id="us_de", name="Delaware", country="US", state="DE",
                              tax_type=TaxType.EXEMPT, rate=0.0, rate_display="0.00%"),
    "ca_on": TaxJurisdiction(id="ca_on", name="Ontario", country="CA", state="ON",
                              tax_type=TaxType.HST, rate=0.13, rate_display="13.00%"),
    "ca_bc": TaxJurisdiction(id="ca_bc", name="British Columbia", country="CA", state="BC",
                              tax_type=TaxType.GST, rate=0.05, rate_display="5.00%"),
    "gb": TaxJurisdiction(id="gb", name="United Kingdom", country="GB",
                           tax_type=TaxType.VAT, rate=0.20, rate_display="20.00%",
                           digital_services_rate=0.20),
    "de": TaxJurisdiction(id="de", name="Germany", country="DE",
                           tax_type=TaxType.VAT, rate=0.19, rate_display="19.00%"),
    "au": TaxJurisdiction(id="au", name="Australia", country="AU",
                           tax_type=TaxType.GST, rate=0.10, rate_display="10.00%"),
}


# ── Tax Engine ─────────────────────────────────────────────────────

class TaxEngine:
    """Multi-jurisdiction tax calculation and management."""

    def __init__(self):
        self._exemptions: dict[str, TaxExemption] = {}
        self._records: dict[str, TaxRecord] = {}
        self._seed_demo_data()

    def _seed_demo_data(self):
        """Create realistic tax exemptions and records."""
        now = datetime.utcnow()

        # Exemptions
        exemptions = [
            TaxExemption(id="txe_acme_01", tenant_id="acme_foods", tenant_name="Acme Foods Inc.",
                         jurisdiction_id="us_or", reason=ExemptionReason.RESELLER,
                         certificate_number="OR-RES-2025-4477", verified=True,
                         valid_from=now - timedelta(days=180), valid_until=now + timedelta(days=185)),
            TaxExemption(id="txe_med_01", tenant_id="medsecure", tenant_name="MedSecure Health",
                         jurisdiction_id="us_ca", reason=ExemptionReason.HEALTHCARE,
                         certificate_number="CA-HC-2025-8891", verified=True,
                         valid_from=now - timedelta(days=90), valid_until=now + timedelta(days=275)),
            TaxExemption(id="txe_gov_01", tenant_id="usda_inspect", tenant_name="USDA Inspection Unit",
                         jurisdiction_id="us_ny", reason=ExemptionReason.GOVERNMENT,
                         certificate_number="FED-GOV-0001", verified=True,
                         valid_from=now - timedelta(days=365)),
        ]
        for ex in exemptions:
            self._exemptions[ex.id] = ex

        # Tax records for reporting
        months = ["2025-10", "2025-11", "2025-12", "2026-01"]
        tenants = [
            ("acme_foods", "Acme Foods Inc.", "us_ca", 500_000),
            ("medsecure", "MedSecure Health", "us_ny", 180_000),
            ("safetyfirst", "SafetyFirst Manufacturing", "us_tx", 95_000),
        ]
        for month in months:
            for tenant_id, name, jur_id, subtotal in tenants:
                j = JURISDICTIONS.get(jur_id)
                if not j:
                    continue
                # Check exemption
                exempt = self._check_exemption(tenant_id, jur_id)
                rate = 0.0 if exempt else j.rate
                tax = int(subtotal * rate)
                record = TaxRecord(
                    tenant_id=tenant_id, tenant_name=name,
                    invoice_id=f"inv_{month}_{tenant_id[:4]}",
                    jurisdiction_id=jur_id, jurisdiction_name=j.name,
                    tax_type=j.tax_type, subtotal_cents=subtotal,
                    tax_rate=rate, tax_amount_cents=tax,
                    period=month,
                    recorded_at=datetime.strptime(month + "-15", "%Y-%m-%d"),
                )
                self._records[record.id] = record

    def _check_exemption(self, tenant_id: str, jurisdiction_id: str) -> bool:
        """Check if a tenant has an active exemption for a jurisdiction."""
        now = datetime.utcnow()
        for ex in self._exemptions.values():
            if (ex.tenant_id == tenant_id and ex.jurisdiction_id == jurisdiction_id
                    and ex.verified
                    and ex.valid_from <= now
                    and (ex.valid_until is None or ex.valid_until > now)):
                return True
        return False

    # ── Tax Calculation ────────────────────────────────────────

    def calculate_tax(self, tenant_id: str, jurisdiction_id: str,
                      subtotal_cents: int, is_digital: bool = True) -> TaxCalculation:
        """Calculate tax for a given transaction."""
        jur = JURISDICTIONS.get(jurisdiction_id)
        if not jur:
            raise ValueError(f"Unknown jurisdiction: {jurisdiction_id}")

        exempt = self._check_exemption(tenant_id, jurisdiction_id)
        rate = 0.0
        if not exempt and jur.tax_type != TaxType.EXEMPT:
            rate = jur.digital_services_rate if (is_digital and jur.digital_services_rate) else jur.rate

        tax_amount = int(subtotal_cents * rate)
        return TaxCalculation(
            jurisdiction_id=jur.id,
            jurisdiction_name=jur.name,
            tax_type=jur.tax_type,
            subtotal_cents=subtotal_cents,
            tax_rate=rate,
            tax_amount_cents=tax_amount,
            total_cents=subtotal_cents + tax_amount,
            is_exempt=exempt,
        )

    # ── Jurisdictions ──────────────────────────────────────────

    def list_jurisdictions(self, country: str | None = None) -> list[TaxJurisdiction]:
        jurs = list(JURISDICTIONS.values())
        if country:
            jurs = [j for j in jurs if j.country == country.upper()]
        return sorted(jurs, key=lambda j: j.name)

    # ── Exemptions ─────────────────────────────────────────────

    def add_exemption(self, tenant_id: str, tenant_name: str, jurisdiction_id: str,
                      reason: ExemptionReason, certificate_number: str = "") -> TaxExemption:
        """Register a tax exemption."""
        if jurisdiction_id not in JURISDICTIONS:
            raise ValueError(f"Unknown jurisdiction: {jurisdiction_id}")

        exemption = TaxExemption(
            tenant_id=tenant_id, tenant_name=tenant_name,
            jurisdiction_id=jurisdiction_id, reason=reason,
            certificate_number=certificate_number,
            valid_until=datetime.utcnow() + timedelta(days=365),
        )
        self._exemptions[exemption.id] = exemption
        logger.info("exemption_added", tenant=tenant_name, jurisdiction=jurisdiction_id)
        return exemption

    def verify_exemption(self, exemption_id: str) -> TaxExemption:
        """Mark an exemption as verified."""
        ex = self._exemptions.get(exemption_id)
        if not ex:
            raise ValueError(f"Exemption {exemption_id} not found")
        ex.verified = True
        return ex

    def list_exemptions(self, tenant_id: str | None = None) -> list[TaxExemption]:
        exemptions = list(self._exemptions.values())
        if tenant_id:
            exemptions = [e for e in exemptions if e.tenant_id == tenant_id]
        return exemptions

    # ── Tax Report ─────────────────────────────────────────────

    def get_tax_report(self, period: str | None = None) -> dict:
        """Tax liability summary by jurisdiction."""
        records = list(self._records.values())
        if period:
            records = [r for r in records if r.period == period]

        by_jurisdiction: dict[str, dict] = {}
        for r in records:
            key = r.jurisdiction_id
            if key not in by_jurisdiction:
                by_jurisdiction[key] = {
                    "jurisdiction_id": key,
                    "jurisdiction_name": r.jurisdiction_name,
                    "tax_type": r.tax_type.value,
                    "total_taxable_cents": 0,
                    "total_tax_cents": 0,
                    "transaction_count": 0,
                }
            by_jurisdiction[key]["total_taxable_cents"] += r.subtotal_cents
            by_jurisdiction[key]["total_tax_cents"] += r.tax_amount_cents
            by_jurisdiction[key]["transaction_count"] += 1

        for j in by_jurisdiction.values():
            j["total_taxable_display"] = f"${j['total_taxable_cents'] / 100:,.2f}"
            j["total_tax_display"] = f"${j['total_tax_cents'] / 100:,.2f}"

        total_tax = sum(j["total_tax_cents"] for j in by_jurisdiction.values())
        total_taxable = sum(j["total_taxable_cents"] for j in by_jurisdiction.values())

        return {
            "period": period or "all",
            "jurisdictions": list(by_jurisdiction.values()),
            "total_taxable_cents": total_taxable,
            "total_taxable_display": f"${total_taxable / 100:,.2f}",
            "total_tax_cents": total_tax,
            "total_tax_display": f"${total_tax / 100:,.2f}",
            "effective_rate_pct": round(total_tax / max(total_taxable, 1) * 100, 2),
            "exemptions_active": sum(1 for e in self._exemptions.values() if e.verified),
        }


# Singleton
tax_engine = TaxEngine()
