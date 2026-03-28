"""Comprehensive tests for Stripe billing module.

Covers plan definitions, checkout session creation, webhook signature
verification, subscription lifecycle events, and authentication
requirements. All Stripe API calls are mocked -- no live keys needed.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from services.ingestion.app.stripe_billing import (
    PLAN_ALIASES,
    PLANS,
    CheckoutRequest,
    _configure_stripe,
    _handle_checkout_completed,
    _handle_stripe_event,
    _normalize_billing_period,
    _normalize_plan_id,
    _process_stripe_webhook,
    _resolve_price_id,
    _update_subscription_status,
)


# ── Plan Definition Tests ────────────────────────────────────────


class TestPlanDefinitions:
    """Validate that all plan definitions are well-formed."""

    REQUIRED_FIELDS = {"id", "name", "features", "limits"}

    def test_all_plans_have_required_fields(self):
        """Every plan must include id, name, features, and limits."""
        for plan_id, plan in PLANS.items():
            for field in self.REQUIRED_FIELDS:
                assert field in plan, f"Plan '{plan_id}' is missing required field '{field}'"

    def test_plans_have_stripe_price_env_keys(self):
        """Every plan must declare Stripe price env var names for monthly and annual."""
        for plan_id, plan in PLANS.items():
            assert "stripe_price_env_monthly" in plan, (
                f"Plan '{plan_id}' missing stripe_price_env_monthly"
            )
            assert "stripe_price_env_annual" in plan, (
                f"Plan '{plan_id}' missing stripe_price_env_annual"
            )

    def test_features_are_non_empty_lists(self):
        """Each plan must list at least one feature."""
        for plan_id, plan in PLANS.items():
            assert isinstance(plan["features"], list), f"Plan '{plan_id}' features is not a list"
            assert len(plan["features"]) > 0, f"Plan '{plan_id}' has empty features list"

    def test_limits_have_required_keys(self):
        """Every plan's limits must specify facilities and events_per_month."""
        for plan_id, plan in PLANS.items():
            limits = plan["limits"]
            assert "facilities" in limits, f"Plan '{plan_id}' limits missing 'facilities'"
            assert "events_per_month" in limits, f"Plan '{plan_id}' limits missing 'events_per_month'"

    def test_growth_plan_values(self):
        """Verify growth plan has expected pricing tiers."""
        growth = PLANS["growth"]
        assert growth["name"] == "Growth"
        assert growth["price_monthly"] == 999
        assert growth["price_annual"] == 832

    def test_scale_plan_values(self):
        """Verify scale plan has expected pricing tiers."""
        scale = PLANS["scale"]
        assert scale["name"] == "Scale"
        assert scale["price_monthly"] == 1999
        assert scale["price_annual"] == 1666

    def test_enterprise_plan_has_no_self_serve_pricing(self):
        """Enterprise plan prices should be None (sales-driven)."""
        enterprise = PLANS["enterprise"]
        assert enterprise["price_monthly"] is None
        assert enterprise["price_annual"] is None

    def test_enterprise_plan_has_unlimited_limits(self):
        """Enterprise plan limits should be -1 (unlimited)."""
        enterprise = PLANS["enterprise"]
        assert enterprise["limits"]["facilities"] == -1
        assert enterprise["limits"]["events_per_month"] == -1

    def test_plan_aliases_resolve_correctly(self):
        """Plan aliases should map to canonical plan IDs."""
        assert PLAN_ALIASES["starter"] == "growth"
        assert PLAN_ALIASES["professional"] == "scale"
        assert PLAN_ALIASES["base"] == "growth"
        assert PLAN_ALIASES["standard"] == "scale"


# ── Normalization Helpers ────────────────────────────────────────


class TestNormalizationHelpers:
    """Tests for plan ID and billing period normalization."""

    def test_normalize_plan_id_with_alias(self):
        """Aliases should resolve to canonical plan IDs."""
        assert _normalize_plan_id("starter") == "growth"
        assert _normalize_plan_id("professional") == "scale"

    def test_normalize_plan_id_passthrough(self):
        """Canonical IDs should pass through unchanged."""
        assert _normalize_plan_id("growth") == "growth"
        assert _normalize_plan_id("scale") == "scale"

    def test_normalize_billing_period_valid(self):
        """Valid billing periods should normalize correctly."""
        assert _normalize_billing_period("monthly") == "monthly"
        assert _normalize_billing_period("annual") == "annual"
        assert _normalize_billing_period("  MONTHLY  ") == "monthly"

    def test_normalize_billing_period_invalid(self):
        """Invalid billing periods should raise HTTPException."""
        with pytest.raises(HTTPException) as exc_info:
            _normalize_billing_period("weekly")
        assert exc_info.value.status_code == 400


# ── Stripe Configuration ─────────────────────────────────────────


class TestConfigureStripe:
    """Tests for _configure_stripe."""

    @patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_123"})
    @patch("services.ingestion.app.stripe_billing.stripe")
    def test_configure_stripe_sets_api_key(self, mock_stripe):
        """_configure_stripe should set stripe.api_key from env."""
        _configure_stripe()
        assert mock_stripe.api_key == "sk_test_123"

    @patch.dict("os.environ", {}, clear=True)
    def test_configure_stripe_raises_without_key(self):
        """_configure_stripe should raise 500 if STRIPE_SECRET_KEY is not set."""
        # Clear the key if it exists in the environment
        import os
        os.environ.pop("STRIPE_SECRET_KEY", None)
        with pytest.raises(HTTPException) as exc_info:
            _configure_stripe()
        assert exc_info.value.status_code == 500


# ── Price Resolution ─────────────────────────────────────────────


class TestResolvePriceId:
    """Tests for _resolve_price_id."""

    @patch.dict("os.environ", {"STRIPE_PRICE_GROWTH_MONTHLY": "price_growth_m"})
    def test_resolve_growth_monthly(self):
        """Should return the growth plan, price ID, and monthly amount."""
        plan, price_id, amount = _resolve_price_id("growth", "monthly")
        assert plan["id"] == "growth"
        assert price_id == "price_growth_m"
        assert amount == 999

    @patch.dict("os.environ", {"STRIPE_PRICE_SCALE_ANNUAL": "price_scale_a"})
    def test_resolve_scale_annual(self):
        """Should return scale plan with annual pricing."""
        plan, price_id, amount = _resolve_price_id("scale", "annual")
        assert plan["id"] == "scale"
        assert price_id == "price_scale_a"
        assert amount == 1666

    @patch.dict("os.environ", {"STRIPE_PRICE_GROWTH_MONTHLY": "price_growth_m"})
    def test_resolve_alias_redirects(self):
        """Alias plan IDs should resolve to the canonical plan."""
        plan, price_id, amount = _resolve_price_id("starter", "monthly")
        assert plan["id"] == "growth"

    def test_resolve_enterprise_raises(self):
        """Enterprise plans should reject self-serve checkout."""
        with pytest.raises(HTTPException) as exc_info:
            _resolve_price_id("enterprise", "monthly")
        assert exc_info.value.status_code == 400
        assert "sales" in exc_info.value.detail.lower()

    def test_resolve_invalid_plan_raises(self):
        """Unknown plan IDs should raise 400."""
        with pytest.raises(HTTPException) as exc_info:
            _resolve_price_id("nonexistent", "monthly")
        assert exc_info.value.status_code == 400

    @patch.dict("os.environ", {"STRIPE_PRICE_GROWTH_MONTHLY": "price_growth_m"})
    def test_annual_falls_back_to_monthly_price(self):
        """Annual billing should fall back to monthly price ID if annual is unconfigured."""
        # Only monthly env is set; annual is not
        plan, price_id, amount = _resolve_price_id("growth", "annual")
        assert price_id == "price_growth_m"
        assert amount == 832  # Annual amount, not monthly


# ── Checkout Session Creation ────────────────────────────────────


class TestCheckoutCreation:
    """Tests for checkout session creation via Stripe API."""

    @patch("services.ingestion.app.stripe_billing._record_checkout_session_hint")
    @patch("services.ingestion.app.stripe_billing.emit_funnel_event")
    @patch("services.ingestion.app.stripe_billing._get_existing_customer_id", return_value=None)
    @patch("services.ingestion.app.stripe_billing.stripe")
    @patch.dict("os.environ", {
        "STRIPE_SECRET_KEY": "sk_test_123",
        "STRIPE_PRICE_GROWTH_MONTHLY": "price_growth_m",
    })
    def test_checkout_creates_session(self, mock_stripe, mock_get_cust, mock_emit, mock_hint):
        """create_checkout should call Stripe checkout.Session.create and return a response."""
        mock_session = MagicMock()
        mock_session.id = "cs_test_abc"
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_abc"
        mock_stripe.checkout.Session.create.return_value = mock_session

        from services.ingestion.app.stripe_billing import create_checkout

        request = CheckoutRequest(
            plan_id="growth",
            billing_period="monthly",
            customer_email="test@example.com",
        )

        import asyncio
        response = asyncio.get_event_loop().run_until_complete(create_checkout(request))

        assert response.session_id == "cs_test_abc"
        assert response.checkout_url == "https://checkout.stripe.com/pay/cs_test_abc"
        assert response.plan == "growth"
        assert response.billing_period == "monthly"
        assert response.amount == 999
        mock_stripe.checkout.Session.create.assert_called_once()

    @patch("services.ingestion.app.stripe_billing.stripe")
    @patch.dict("os.environ", {
        "STRIPE_SECRET_KEY": "sk_test_123",
        "STRIPE_PRICE_GROWTH_MONTHLY": "price_growth_m",
    })
    def test_checkout_stripe_error_raises_502(self, mock_stripe):
        """Stripe API errors during checkout should raise HTTPException 502."""
        import stripe as real_stripe

        mock_stripe.checkout.Session.create.side_effect = real_stripe.error.StripeError(
            message="API error"
        )
        mock_stripe.error = real_stripe.error

        from services.ingestion.app.stripe_billing import create_checkout

        request = CheckoutRequest(plan_id="growth", billing_period="monthly")

        import asyncio
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(create_checkout(request))
        assert exc_info.value.status_code == 502


# ── Webhook Signature Verification ──────────────────────────────


class TestWebhookSignatureVerification:
    """Tests for webhook signature verification in _process_stripe_webhook."""

    @pytest.mark.asyncio
    @patch.dict("os.environ", {
        "STRIPE_SECRET_KEY": "sk_test_123",
        "STRIPE_WEBHOOK_SECRET": "whsec_test_123",
    })
    @patch("services.ingestion.app.stripe_billing._handle_stripe_event", new_callable=AsyncMock)
    @patch("services.ingestion.app.stripe_billing.stripe")
    async def test_valid_signature_processes_event(self, mock_stripe, mock_handle):
        """A valid Stripe-Signature should pass verification and process the event."""
        mock_event = {"type": "checkout.session.completed", "data": {"object": {}}}
        mock_stripe.Webhook.construct_event.return_value = mock_event

        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"type": "checkout.session.completed"}'

        result = await _process_stripe_webhook(mock_request, "t=123,v1=sig")

        assert result["received"] is True
        assert result["event_type"] == "checkout.session.completed"
        mock_stripe.Webhook.construct_event.assert_called_once()
        mock_handle.assert_called_once_with(mock_event)

    @pytest.mark.asyncio
    @patch.dict("os.environ", {
        "STRIPE_SECRET_KEY": "sk_test_123",
        "STRIPE_WEBHOOK_SECRET": "whsec_test_123",
    })
    @patch("services.ingestion.app.stripe_billing.stripe")
    async def test_invalid_signature_raises_401(self, mock_stripe):
        """An invalid Stripe-Signature should raise HTTPException 401."""
        import stripe as real_stripe

        mock_stripe.Webhook.construct_event.side_effect = (
            real_stripe.error.SignatureVerificationError(
                message="Invalid signature",
                sig_header="t=123,v1=bad",
            )
        )
        mock_stripe.error = real_stripe.error

        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"type": "test"}'

        with pytest.raises(HTTPException) as exc_info:
            await _process_stripe_webhook(mock_request, "t=123,v1=bad")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch.dict("os.environ", {
        "STRIPE_SECRET_KEY": "sk_test_123",
        "STRIPE_WEBHOOK_SECRET": "whsec_test_123",
    })
    @patch("services.ingestion.app.stripe_billing.stripe")
    async def test_invalid_payload_raises_400(self, mock_stripe):
        """A malformed payload should raise HTTPException 400."""
        mock_stripe.Webhook.construct_event.side_effect = ValueError("bad json")

        mock_request = AsyncMock()
        mock_request.body.return_value = b"not-json"

        with pytest.raises(HTTPException) as exc_info:
            await _process_stripe_webhook(mock_request, "t=123,v1=sig")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_123"})
    async def test_missing_webhook_secret_raises_500(self):
        """Missing STRIPE_WEBHOOK_SECRET should raise 500."""
        import os
        os.environ.pop("STRIPE_WEBHOOK_SECRET", None)

        mock_request = AsyncMock()
        mock_request.body.return_value = b"{}"

        with pytest.raises(HTTPException) as exc_info:
            await _process_stripe_webhook(mock_request, "t=123,v1=sig")
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    @patch.dict("os.environ", {
        "STRIPE_SECRET_KEY": "sk_test_123",
        "STRIPE_WEBHOOK_SECRET": "whsec_test_123",
    })
    async def test_missing_signature_header_raises_400(self):
        """Missing Stripe-Signature header should raise 400."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b"{}"

        with pytest.raises(HTTPException) as exc_info:
            await _process_stripe_webhook(mock_request, None)
        assert exc_info.value.status_code == 400


# ── Webhook Event: checkout.session.completed ────────────────────


class TestHandleCheckoutCompleted:
    """Tests for checkout.session.completed webhook event handling."""

    @pytest.mark.asyncio
    @patch("services.ingestion.app.stripe_billing._store_subscription_mapping")
    @patch("services.ingestion.app.stripe_billing._redis_client")
    @patch("services.ingestion.app.stripe_billing.stripe")
    async def test_checkout_completed_stores_mapping(
        self, mock_stripe, mock_redis_client, mock_store
    ):
        """checkout.session.completed should store subscription mapping in Redis."""
        mock_client = MagicMock()
        mock_client.get.return_value = None  # No existing tenant from session lookup
        mock_redis_client.return_value = mock_client

        mock_stripe.Subscription.retrieve.return_value = {
            "status": "active",
            "current_period_end": 1700000000,
        }

        session = {
            "id": "cs_test_123",
            "subscription": "sub_test_456",
            "customer": "cus_test_789",
            "customer_details": {"email": "user@example.com"},
            "metadata": {
                "tenant_id": "tenant-abc",
                "plan_id": "growth",
                "billing_period": "monthly",
            },
        }

        await _handle_checkout_completed(session)

        mock_store.assert_called_once()
        call_args = mock_store.call_args
        assert call_args[0][0] == "tenant-abc"  # tenant_id
        payload = call_args[0][1]
        assert payload["plan_id"] == "growth"
        assert payload["status"] == "active"
        assert payload["subscription_id"] == "sub_test_456"
        assert payload["customer_id"] == "cus_test_789"

    @pytest.mark.asyncio
    @patch("services.ingestion.app.stripe_billing._create_tenant_via_admin")
    @patch("services.ingestion.app.stripe_billing._store_subscription_mapping")
    @patch("services.ingestion.app.stripe_billing._redis_client")
    @patch("services.ingestion.app.stripe_billing.stripe")
    async def test_checkout_completed_creates_tenant_when_missing(
        self, mock_stripe, mock_redis_client, mock_store, mock_create_tenant
    ):
        """If no tenant_id in metadata, should create one via admin service."""
        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_redis_client.return_value = mock_client

        mock_create_tenant.return_value = "new-tenant-xyz"

        mock_stripe.Subscription.retrieve.return_value = {
            "status": "active",
            "current_period_end": 1700000000,
        }

        session = {
            "id": "cs_test_456",
            "subscription": "sub_test_789",
            "customer": "cus_test_000",
            "customer_email": "new@example.com",
            "metadata": {},
        }

        await _handle_checkout_completed(session)

        mock_create_tenant.assert_called_once()
        tenant_name_arg = mock_create_tenant.call_args[0][0]
        assert "new" in tenant_name_arg.lower()  # Derived from email


# ── Webhook Event: customer.subscription.deleted ─────────────────


class TestHandleSubscriptionDeleted:
    """Tests for customer.subscription.deleted webhook event handling."""

    @pytest.mark.asyncio
    @patch("services.ingestion.app.stripe_billing._store_subscription_mapping")
    @patch("services.ingestion.app.stripe_billing._get_subscription_mapping")
    @patch("services.ingestion.app.stripe_billing._find_tenant_id")
    async def test_subscription_deleted_sets_canceled(
        self, mock_find_tenant, mock_get_mapping, mock_store
    ):
        """customer.subscription.deleted should set status to 'canceled'."""
        mock_find_tenant.return_value = "tenant-abc"
        mock_get_mapping.return_value = {
            "tenant_id": "tenant-abc",
            "plan_id": "growth",
            "status": "active",
            "subscription_id": "sub_test_123",
            "customer_id": "cus_test_456",
        }

        event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": "sub_test_123",
                    "customer": "cus_test_456",
                    "status": "canceled",
                    "current_period_end": 1700000000,
                },
            },
        }

        await _handle_stripe_event(event)

        # _update_subscription_status is called, then _store for period end
        assert mock_store.call_count >= 1
        # Check at least one call sets canceled
        all_payloads = [call[0][1] for call in mock_store.call_args_list]
        statuses = [p.get("status") for p in all_payloads]
        assert "canceled" in statuses

    @pytest.mark.asyncio
    @patch("services.ingestion.app.stripe_billing._store_subscription_mapping")
    @patch("services.ingestion.app.stripe_billing._get_subscription_mapping")
    @patch("services.ingestion.app.stripe_billing._find_tenant_id")
    async def test_subscription_updated_preserves_status(
        self, mock_find_tenant, mock_get_mapping, mock_store
    ):
        """customer.subscription.updated should use the sub's actual status."""
        mock_find_tenant.return_value = "tenant-abc"
        mock_get_mapping.return_value = {
            "tenant_id": "tenant-abc",
            "plan_id": "scale",
            "status": "active",
            "subscription_id": "sub_test_999",
            "customer_id": "cus_test_111",
        }

        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_test_999",
                    "customer": "cus_test_111",
                    "status": "past_due",
                    "current_period_end": 1700000000,
                },
            },
        }

        await _handle_stripe_event(event)

        all_payloads = [call[0][1] for call in mock_store.call_args_list]
        statuses = [p.get("status") for p in all_payloads]
        assert "past_due" in statuses


# ── Webhook Event: invoice.paid ──────────────────────────────────


class TestHandleInvoicePaid:
    """Tests for invoice.paid webhook event handling."""

    @pytest.mark.asyncio
    @patch("services.ingestion.app.stripe_billing.emit_funnel_event")
    @patch("services.ingestion.app.stripe_billing._store_subscription_mapping")
    @patch("services.ingestion.app.stripe_billing._get_subscription_mapping")
    @patch("services.ingestion.app.stripe_billing._find_tenant_id")
    async def test_invoice_paid_sets_active(
        self, mock_find_tenant, mock_get_mapping, mock_store, mock_emit
    ):
        """invoice.paid should update subscription status to active."""
        mock_find_tenant.return_value = "tenant-abc"
        mock_get_mapping.return_value = {
            "tenant_id": "tenant-abc",
            "plan_id": "growth",
            "status": "past_due",
            "subscription_id": "sub_test_123",
            "customer_id": "cus_test_456",
        }

        event = {
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": "inv_test_789",
                    "subscription": "sub_test_123",
                    "customer": "cus_test_456",
                    "created": 1700000000,
                    "period_end": 1702592000,
                    "status_transitions": {"paid_at": 1700000100},
                },
            },
        }

        await _handle_stripe_event(event)

        all_payloads = [call[0][1] for call in mock_store.call_args_list]
        statuses = [p.get("status") for p in all_payloads]
        assert "active" in statuses


# ── Webhook Event: invoice.payment_failed ────────────────────────


class TestHandleInvoicePaymentFailed:
    """Tests for invoice.payment_failed webhook event handling."""

    @pytest.mark.asyncio
    @patch("services.ingestion.app.stripe_billing._store_subscription_mapping")
    @patch("services.ingestion.app.stripe_billing._get_subscription_mapping")
    @patch("services.ingestion.app.stripe_billing._find_tenant_id")
    async def test_payment_failed_sets_past_due(
        self, mock_find_tenant, mock_get_mapping, mock_store
    ):
        """invoice.payment_failed should set status to past_due."""
        mock_find_tenant.return_value = "tenant-abc"
        mock_get_mapping.return_value = {
            "tenant_id": "tenant-abc",
            "plan_id": "growth",
            "status": "active",
            "subscription_id": "sub_test_123",
            "customer_id": "cus_test_456",
        }

        event = {
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "id": "inv_test_fail",
                    "subscription": "sub_test_123",
                    "customer": "cus_test_456",
                    "created": 1700000000,
                },
            },
        }

        await _handle_stripe_event(event)

        all_payloads = [call[0][1] for call in mock_store.call_args_list]
        statuses = [p.get("status") for p in all_payloads]
        assert "past_due" in statuses


# ── Unknown Webhook Events ───────────────────────────────────────


class TestUnknownWebhookEvents:
    """Tests for unhandled webhook event types."""

    @pytest.mark.asyncio
    async def test_unknown_event_is_logged_and_ignored(self):
        """Unknown event types should be silently ignored (no exception)."""
        event = {
            "type": "payment_intent.succeeded",
            "data": {"object": {}},
        }

        # Should not raise
        await _handle_stripe_event(event)


# ── Authentication Requirement Tests ─────────────────────────────


class TestAuthenticationRequirements:
    """Verify that billing endpoints requiring auth declare dependencies."""

    def test_subscription_endpoint_requires_api_key(self):
        """GET /subscription/{tenant_id} should depend on _verify_api_key."""
        from services.ingestion.app.stripe_billing import get_subscription

        # FastAPI stores dependencies on the route function
        deps = getattr(get_subscription, "__depends__", None)
        # Check via the route's dependant params instead
        import inspect
        sig = inspect.signature(get_subscription)
        params = sig.parameters

        # The '_' parameter should have a Depends default
        assert "_" in params, "get_subscription should have an auth dependency parameter"
        default = params["_"].default
        assert hasattr(default, "dependency"), "Auth parameter should be a Depends() instance"

    def test_portal_endpoint_requires_principal(self):
        """POST /portal should depend on get_ingestion_principal."""
        from services.ingestion.app.stripe_billing import create_portal_session_for_tenant

        import inspect
        sig = inspect.signature(create_portal_session_for_tenant)
        params = sig.parameters

        assert "principal" in params, "create_portal_session_for_tenant should accept a principal"
        default = params["principal"].default
        assert hasattr(default, "dependency"), "principal parameter should be a Depends() instance"

    def test_invoices_endpoint_requires_permission(self):
        """GET /invoices should depend on require_permission('billing.invoices.read')."""
        from services.ingestion.app.stripe_billing import list_invoices

        import inspect
        sig = inspect.signature(list_invoices)
        params = sig.parameters

        assert "principal" in params, "list_invoices should accept a principal"
        default = params["principal"].default
        assert hasattr(default, "dependency"), "principal parameter should be a Depends() instance"

    def test_invoice_pdf_endpoint_requires_permission(self):
        """GET /invoices/{invoice_id}/pdf should require billing.invoices.read permission."""
        from services.ingestion.app.stripe_billing import get_invoice_pdf

        import inspect
        sig = inspect.signature(get_invoice_pdf)
        params = sig.parameters

        assert "principal" in params, "get_invoice_pdf should accept a principal"
        default = params["principal"].default
        assert hasattr(default, "dependency"), "principal parameter should be a Depends() instance"

    def test_webhook_endpoint_does_not_require_auth(self):
        """POST /webhooks should NOT require auth (Stripe signs the payload)."""
        from services.ingestion.app.stripe_billing import stripe_webhooks

        import inspect
        sig = inspect.signature(stripe_webhooks)
        params = sig.parameters

        # Webhook endpoint should not have a principal or auth-dependency parameter
        assert "principal" not in params, "Webhook endpoint should not require principal auth"
        # It should have stripe_signature instead
        assert "stripe_signature" in params, "Webhook endpoint should accept Stripe-Signature"
