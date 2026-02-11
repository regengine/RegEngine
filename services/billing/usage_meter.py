"""
Billing Service — Usage Metering Engine

Tracks per-tenant resource consumption (documents, API calls, storage)
and computes tiered overage charges. In production this would be backed
by a time-series database; sandbox mode uses in-memory counters with
realistic seed data.
"""

from __future__ import annotations

import structlog
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict
from uuid import uuid4
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ── Usage Tiers ────────────────────────────────────────────────────

USAGE_PRICING = {
    "document_processing": {
        "unit": "document",
        "tiers": [
            {"limit": 1_000, "price_cents": 10},     # $0.10/doc
            {"limit": 10_000, "price_cents": 8},      # $0.08/doc
            {"limit": 100_000, "price_cents": 5},     # $0.05/doc
            {"limit": None, "price_cents": 3},        # $0.03/doc (unlimited)
        ],
    },
    "api_calls": {
        "unit": "call",
        "tiers": [
            {"limit": 10_000, "price_cents": 1},      # $0.01/call
            {"limit": 100_000, "price_cents": 0.5},    # $0.005/call
            {"limit": None, "price_cents": 0.2},       # $0.002/call
        ],
    },
    "storage_gb": {
        "unit": "GB-month",
        "tiers": [
            {"limit": 100, "price_cents": 25},         # $0.25/GB
            {"limit": 500, "price_cents": 20},          # $0.20/GB
            {"limit": None, "price_cents": 15},         # $0.15/GB
        ],
    },
}

# Included allocations per subscription tier
TIER_ALLOCATIONS = {
    "starter": {
        "document_processing": 1_000,
        "api_calls": 5_000,
        "storage_gb": 10,
    },
    "growth": {
        "document_processing": 10_000,
        "api_calls": 50_000,
        "storage_gb": 100,
    },
    "scale": {
        "document_processing": 100_000,
        "api_calls": 500_000,
        "storage_gb": 500,
    },
    "enterprise": {
        "document_processing": 1_000_000,
        "api_calls": -1,  # unlimited
        "storage_gb": 1_000,
    },
}


# ── Models ─────────────────────────────────────────────────────────

class UsageEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")
    tenant_id: str
    resource: str  # document_processing | api_calls | storage_gb
    quantity: int = 1
    metadata: dict = {}
    recorded_at: datetime = Field(default_factory=datetime.utcnow)


class UsageSummary(BaseModel):
    tenant_id: str
    period_start: datetime
    period_end: datetime
    resources: dict  # resource → { used, included, overage, overage_cost_cents }
    total_overage_cents: int = 0
    total_overage_display: str = "$0.00"


class OverageAlert(BaseModel):
    tenant_id: str
    resource: str
    used: int
    included: int
    usage_pct: float
    overage_cost_cents: int
    severity: str  # warning (>80%), critical (>100%)


# ── Usage Meter ────────────────────────────────────────────────────

class UsageMeter:
    """Track resource consumption per-tenant with tiered overage pricing."""

    def __init__(self):
        # tenant_id → resource → list[UsageEvent]
        self._events: dict[str, dict[str, list[UsageEvent]]] = defaultdict(
            lambda: defaultdict(list)
        )
        # Seed demo data
        self._seed_demo_data()

    def _seed_demo_data(self):
        """Populate realistic usage data for demo tenants."""
        now = datetime.utcnow()
        demo_tenants = {
            "acme_foods": {"document_processing": 8_420, "api_calls": 34_200, "storage_gb": 45},
            "globaltech": {"document_processing": 3_150, "api_calls": 12_800, "storage_gb": 22},
            "medsecure": {"document_processing": 15_600, "api_calls": 67_300, "storage_gb": 89},
            "energyflow": {"document_processing": 320, "api_calls": 1_200, "storage_gb": 3},
            "safetyfirst": {"document_processing": 5_800, "api_calls": 28_400, "storage_gb": 38},
        }

        for tenant_id, usage in demo_tenants.items():
            for resource, quantity in usage.items():
                event = UsageEvent(
                    tenant_id=tenant_id,
                    resource=resource,
                    quantity=quantity,
                    recorded_at=now - timedelta(hours=2),
                )
                self._events[tenant_id][resource].append(event)

    # ── Record Usage ───────────────────────────────────────────

    def record(self, tenant_id: str, resource: str, quantity: int = 1,
               metadata: dict | None = None) -> UsageEvent:
        """Record a usage event."""
        if resource not in USAGE_PRICING:
            raise ValueError(f"Unknown resource type: {resource}")

        event = UsageEvent(
            tenant_id=tenant_id,
            resource=resource,
            quantity=quantity,
            metadata=metadata or {},
        )
        self._events[tenant_id][resource].append(event)

        logger.info(
            "usage_recorded",
            tenant_id=tenant_id,
            resource=resource,
            quantity=quantity,
        )
        return event

    # ── Usage Summary ──────────────────────────────────────────

    def get_summary(self, tenant_id: str, tier_id: str = "growth") -> UsageSummary:
        """Compute current-period usage summary with overage calculations."""
        now = datetime.utcnow()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)

        allocations = TIER_ALLOCATIONS.get(tier_id, TIER_ALLOCATIONS["growth"])
        resources = {}
        total_overage_cents = 0

        for resource in USAGE_PRICING:
            events = self._events.get(tenant_id, {}).get(resource, [])
            period_events = [e for e in events if e.recorded_at >= period_start]
            used = sum(e.quantity for e in period_events)
            included = allocations.get(resource, 0)

            if included == -1:  # unlimited
                overage = 0
                overage_cost = 0
            else:
                overage = max(0, used - included)
                overage_cost = self._compute_tiered_cost(resource, overage)

            total_overage_cents += overage_cost

            resources[resource] = {
                "used": used,
                "included": included if included != -1 else "unlimited",
                "overage": overage,
                "usage_pct": round(used / max(included, 1) * 100, 1) if included > 0 else 0,
                "overage_cost_cents": overage_cost,
                "overage_cost_display": f"${overage_cost / 100:.2f}",
                "unit": USAGE_PRICING[resource]["unit"],
            }

        return UsageSummary(
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            resources=resources,
            total_overage_cents=total_overage_cents,
            total_overage_display=f"${total_overage_cents / 100:.2f}",
        )

    # ── Detailed Breakdown ─────────────────────────────────────

    def get_breakdown(self, tenant_id: str, tier_id: str = "growth") -> dict:
        """Per-resource usage breakdown with trend data."""
        summary = self.get_summary(tenant_id, tier_id)

        breakdown = {}
        for resource, data in summary.resources.items():
            pricing = USAGE_PRICING[resource]
            breakdown[resource] = {
                **data,
                "pricing_tiers": [
                    {
                        "limit": t["limit"],
                        "limit_display": f"{t['limit']:,}" if t["limit"] else "Unlimited",
                        "price_cents": t["price_cents"],
                        "price_display": f"${t['price_cents'] / 100:.3f}/{pricing['unit']}",
                    }
                    for t in pricing["tiers"]
                ],
            }

        return {
            "tenant_id": tenant_id,
            "tier_id": tier_id,
            "period": {
                "start": summary.period_start.isoformat(),
                "end": summary.period_end.isoformat(),
            },
            "resources": breakdown,
            "total_overage_cents": summary.total_overage_cents,
            "total_overage_display": summary.total_overage_display,
        }

    # ── Overage Alerts ─────────────────────────────────────────

    def get_overage_alerts(self, tier_overrides: dict[str, str] | None = None) -> list[dict]:
        """Identify tenants approaching or exceeding their usage limits."""
        alerts = []
        tier_map = tier_overrides or {}

        for tenant_id in self._events:
            tier_id = tier_map.get(tenant_id, "growth")
            summary = self.get_summary(tenant_id, tier_id)

            for resource, data in summary.resources.items():
                if isinstance(data["included"], str):  # "unlimited"
                    continue

                usage_pct = data["usage_pct"]
                if usage_pct >= 80:
                    alerts.append({
                        "tenant_id": tenant_id,
                        "resource": resource,
                        "used": data["used"],
                        "included": data["included"],
                        "usage_pct": usage_pct,
                        "overage_cost_cents": data["overage_cost_cents"],
                        "severity": "critical" if usage_pct >= 100 else "warning",
                    })

        # Sort by severity (critical first) then usage %
        alerts.sort(key=lambda a: (0 if a["severity"] == "critical" else 1, -a["usage_pct"]))
        return alerts

    # ── Tiered Cost Calculation ────────────────────────────────

    @staticmethod
    def _compute_tiered_cost(resource: str, overage_quantity: int) -> int:
        """Calculate cost using graduated tiered pricing."""
        if overage_quantity <= 0:
            return 0

        tiers = USAGE_PRICING[resource]["tiers"]
        remaining = overage_quantity
        total_cost_cents = 0

        for tier in tiers:
            limit = tier["limit"]
            price = tier["price_cents"]

            if limit is None:
                # Final unlimited tier
                total_cost_cents += int(remaining * price)
                remaining = 0
                break

            tier_quantity = min(remaining, limit)
            total_cost_cents += int(tier_quantity * price)
            remaining -= tier_quantity

            if remaining <= 0:
                break

        return total_cost_cents


# Singleton
usage_meter = UsageMeter()
