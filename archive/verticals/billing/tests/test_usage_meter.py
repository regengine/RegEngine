"""
Usage Meter & API Tests

Tests usage recording, tiered pricing calculation, overage detection,
summary generation, and API endpoints.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app
from usage_meter import UsageMeter, USAGE_PRICING, TIER_ALLOCATIONS

client = TestClient(app)


# ── Engine Unit Tests ──────────────────────────────────────────────

class TestUsageRecording:
    """Test recording usage events."""

    def test_record_event(self):
        meter = UsageMeter()
        event = meter.record("t1", "document_processing", 100)
        assert event.tenant_id == "t1"
        assert event.resource == "document_processing"
        assert event.quantity == 100

    def test_record_invalid_resource(self):
        meter = UsageMeter()
        with pytest.raises(ValueError, match="Unknown resource"):
            meter.record("t1", "invalid_resource", 100)

    def test_record_accumulates(self):
        meter = UsageMeter()
        meter.record("t1", "api_calls", 500)
        meter.record("t1", "api_calls", 300)
        summary = meter.get_summary("t1", "growth")
        assert summary.resources["api_calls"]["used"] == 800


class TestTieredPricing:
    """Test graduated tier cost calculation."""

    def test_zero_overage(self):
        cost = UsageMeter._compute_tiered_cost("document_processing", 0)
        assert cost == 0

    def test_first_tier_pricing(self):
        # 500 docs at $0.10 = $50 = 5000 cents
        cost = UsageMeter._compute_tiered_cost("document_processing", 500)
        assert cost == 5_000

    def test_crosses_tier_boundary(self):
        # 1500 docs: first 1000 at $0.10 + 500 at $0.08
        cost = UsageMeter._compute_tiered_cost("document_processing", 1_500)
        expected = (1_000 * 10) + (500 * 8)
        assert cost == expected

    def test_all_tiers(self):
        # 150,000 docs: 1K@$0.10 + 10K@$0.08 + 100K@$0.05 + 39K@$0.03
        cost = UsageMeter._compute_tiered_cost("document_processing", 150_000)
        expected = (1_000 * 10) + (10_000 * 8) + (100_000 * 5) + (39_000 * 3)
        assert cost == expected

    def test_api_call_pricing(self):
        # 5000 API calls at $0.01 = $50 = 5000 cents
        cost = UsageMeter._compute_tiered_cost("api_calls", 5_000)
        assert cost == 5_000


class TestUsageSummary:
    """Test period usage summary with allocation checks."""

    def test_within_allocation(self):
        meter = UsageMeter()
        meter.record("within_test", "document_processing", 500)
        summary = meter.get_summary("within_test", "growth")
        assert summary.resources["document_processing"]["overage"] == 0
        assert summary.total_overage_cents == 0

    def test_overage_detected(self):
        meter = UsageMeter()
        # Growth tier includes 10K docs, record 12K
        meter.record("over_test", "document_processing", 12_000)
        summary = meter.get_summary("over_test", "growth")
        assert summary.resources["document_processing"]["overage"] == 2_000
        assert summary.total_overage_cents > 0

    def test_unlimited_no_overage(self):
        meter = UsageMeter()
        # Enterprise has unlimited API calls
        meter.record("ent_test", "api_calls", 999_999)
        summary = meter.get_summary("ent_test", "enterprise")
        assert summary.resources["api_calls"]["overage"] == 0

    def test_starter_lower_allocation(self):
        meter = UsageMeter()
        # Starter only gets 1K docs
        meter.record("starter_test", "document_processing", 2_000)
        summary = meter.get_summary("starter_test", "starter")
        assert summary.resources["document_processing"]["overage"] == 1_000

    def test_usage_percentage(self):
        meter = UsageMeter()
        meter.record("pct_test", "document_processing", 8_000)
        summary = meter.get_summary("pct_test", "growth")
        assert summary.resources["document_processing"]["usage_pct"] == 80.0


class TestOverageAlerts:
    """Test overage alert detection."""

    def test_no_alerts_under_threshold(self):
        meter = UsageMeter()
        meter.record("safe", "document_processing", 100)
        alerts = meter.get_overage_alerts({"safe": "growth"})
        safe_alerts = [a for a in alerts if a["tenant_id"] == "safe"]
        assert len(safe_alerts) == 0

    def test_warning_at_80_pct(self):
        meter = UsageMeter()
        meter.record("warn", "document_processing", 8_500)  # 85% of 10K
        alerts = meter.get_overage_alerts({"warn": "growth"})
        warn_alerts = [a for a in alerts if a["tenant_id"] == "warn"]
        assert any(a["severity"] == "warning" for a in warn_alerts)

    def test_critical_at_100_pct(self):
        meter = UsageMeter()
        meter.record("crit", "document_processing", 15_000)  # 150% of 10K
        alerts = meter.get_overage_alerts({"crit": "growth"})
        crit_alerts = [a for a in alerts if a["tenant_id"] == "crit"]
        assert any(a["severity"] == "critical" for a in crit_alerts)

    def test_seed_data_alerts(self):
        meter = UsageMeter()
        alerts = meter.get_overage_alerts()
        # Seed data should have some alerts
        assert isinstance(alerts, list)


# ── API Endpoint Tests ─────────────────────────────────────────────

class TestUsageAPI:
    """Test usage router endpoints."""

    def test_record_usage(self):
        response = client.post(
            "/v1/billing/usage/record",
            headers={"X-Tenant-ID": "api_test"},
            json={"resource": "document_processing", "quantity": 50},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["resource"] == "document_processing"
        assert data["quantity"] == 50

    def test_record_invalid_resource(self):
        response = client.post(
            "/v1/billing/usage/record",
            json={"resource": "invalid"},
        )
        assert response.status_code == 400

    def test_usage_summary(self):
        response = client.get("/v1/billing/usage/acme_foods/summary?tier_id=growth")
        assert response.status_code == 200
        data = response.json()
        assert "resources" in data
        assert "document_processing" in data["resources"]

    def test_usage_breakdown(self):
        response = client.get("/v1/billing/usage/acme_foods/breakdown?tier_id=growth")
        assert response.status_code == 200
        data = response.json()
        assert "resources" in data
        # Should include pricing tiers
        for resource_data in data["resources"].values():
            assert "pricing_tiers" in resource_data

    def test_overage_alerts(self):
        response = client.get("/v1/billing/usage/overage-alerts")
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert "total_alerts" in data
        assert "critical_count" in data
