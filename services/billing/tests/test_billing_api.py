"""
Billing API Integration Tests

Tests run in sandbox mode — no Stripe keys required.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure billing module is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app

client = TestClient(app)


# ── Health ─────────────────────────────────────────────────────────

class TestHealth:
    """Basic health and info endpoints."""

    def test_health_endpoint(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "billing-service"
        assert data["billing_mode"] == "sandbox"

    def test_root_endpoint(self):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "endpoints" in data
        assert "subscriptions" in data["endpoints"]


# ── Pricing Tiers ──────────────────────────────────────────────────

class TestPricingTiers:
    """Tier listing and validation."""

    def test_list_tiers(self):
        response = client.get("/v1/billing/subscriptions/tiers")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tiers"]) == 4
        tier_ids = [t["id"] for t in data["tiers"]]
        assert "starter" in tier_ids
        assert "growth" in tier_ids
        assert "scale" in tier_ids
        assert "enterprise" in tier_ids

    def test_growth_tier_pricing(self):
        response = client.get("/v1/billing/subscriptions/tiers")
        tiers = {t["id"]: t for t in response.json()["tiers"]}
        growth = tiers["growth"]
        assert growth["monthly_price"] == 799
        assert growth["annual_price"] == 665
        assert growth["highlighted"] is True


# ── Subscriptions ──────────────────────────────────────────────────

class TestSubscriptions:
    """Subscription CRUD operations."""

    def test_no_subscription_initially(self):
        response = client.get(
            "/v1/billing/subscriptions/current",
            headers={"X-Tenant-ID": "test_sub_tenant"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["subscription"] is None

    def test_create_subscription(self):
        response = client.post(
            "/v1/billing/subscriptions/create",
            headers={"X-Tenant-ID": "test_create_tenant"},
            json={"tier_id": "growth", "billing_cycle": "annual"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["subscription"]["tier_id"] == "growth"
        assert data["subscription"]["status"] == "trialing"
        assert "14-day trial" in data["message"]

    def test_create_enterprise_subscription_rejected(self):
        response = client.post(
            "/v1/billing/subscriptions/create",
            headers={"X-Tenant-ID": "test_ent_tenant"},
            json={"tier_id": "enterprise"},
        )
        assert response.status_code == 400
        assert "custom pricing" in response.json()["detail"].lower()

    def test_create_invalid_tier_rejected(self):
        response = client.post(
            "/v1/billing/subscriptions/create",
            headers={"X-Tenant-ID": "test_invalid_tier"},
            json={"tier_id": "nonexistent"},
        )
        assert response.status_code == 400

    def test_duplicate_subscription_rejected(self):
        tenant = "test_dup_tenant"
        client.post(
            "/v1/billing/subscriptions/create",
            headers={"X-Tenant-ID": tenant},
            json={"tier_id": "starter"},
        )
        response = client.post(
            "/v1/billing/subscriptions/create",
            headers={"X-Tenant-ID": tenant},
            json={"tier_id": "growth"},
        )
        assert response.status_code == 409

    def test_cancel_subscription(self):
        tenant = "test_cancel_tenant"
        client.post(
            "/v1/billing/subscriptions/create",
            headers={"X-Tenant-ID": tenant},
            json={"tier_id": "starter"},
        )
        response = client.post(
            "/v1/billing/subscriptions/cancel",
            headers={"X-Tenant-ID": tenant},
        )
        assert response.status_code == 200
        assert "canceled" in response.json()["message"].lower()

    def test_change_tier(self):
        tenant = "test_upgrade_tenant"
        client.post(
            "/v1/billing/subscriptions/create",
            headers={"X-Tenant-ID": tenant},
            json={"tier_id": "starter"},
        )
        response = client.post(
            "/v1/billing/subscriptions/change-tier",
            headers={"X-Tenant-ID": tenant},
            json={"new_tier_id": "growth"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "upgraded" in data["message"]
        assert data["subscription"]["tier_id"] == "growth"


# ── Checkout ───────────────────────────────────────────────────────

class TestCheckout:
    """Checkout session creation and retrieval."""

    def test_create_checkout_session(self):
        response = client.post(
            "/v1/billing/checkout/session",
            headers={"X-Tenant-ID": "test_checkout_tenant"},
            json={"tier_id": "growth", "billing_cycle": "annual"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tier"] == "Growth"
        assert data["sandbox_mode"] is True
        assert "checkout_url" in data
        assert data["session_id"].startswith("cs_")

    def test_checkout_with_credit_code(self):
        response = client.post(
            "/v1/billing/checkout/session",
            headers={"X-Tenant-ID": "test_checkout_credit"},
            json={
                "tier_id": "starter",
                "billing_cycle": "monthly",
                "credit_code": "LAUNCH50",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["credits_applied"] is not None

    def test_checkout_enterprise_rejected(self):
        response = client.post(
            "/v1/billing/checkout/session",
            json={"tier_id": "enterprise"},
        )
        assert response.status_code == 400

    def test_get_checkout_session(self):
        # Create first
        create_resp = client.post(
            "/v1/billing/checkout/session",
            json={"tier_id": "growth"},
        )
        session_id = create_resp.json()["session_id"]

        # Retrieve
        response = client.get(f"/v1/billing/checkout/session/{session_id}")
        assert response.status_code == 200
        assert response.json()["tier_id"] == "growth"


# ── Webhooks ───────────────────────────────────────────────────────

class TestWebhooks:
    """Webhook processing tests."""

    def test_webhook_checkout_completed(self):
        event = {
            "id": "evt_test_123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "payment_status": "paid",
                    "metadata": {"tenant_id": "test_webhook", "tier_id": "growth"},
                }
            },
        }
        response = client.post("/v1/billing/webhooks/stripe", json=event)
        assert response.status_code == 200
        assert response.json()["event_type"] == "checkout.session.completed"

    def test_webhook_payment_failed(self):
        event = {
            "id": "evt_test_fail",
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "customer": "cus_test",
                    "attempt_count": 2,
                }
            },
        }
        response = client.post("/v1/billing/webhooks/stripe", json=event)
        assert response.status_code == 200

    def test_webhook_events_log(self):
        response = client.get("/v1/billing/webhooks/events")
        assert response.status_code == 200
        assert "events" in response.json()
