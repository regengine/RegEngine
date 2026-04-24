"""Focused error-path and endpoint coverage for ``stripe_billing.routes`` — #1342.

The existing ``test_stripe_billing_router.py`` exercises several happy paths
but (a) polluttes state between tests (visible as several pre-existing
failures when the full stripe suite runs together) and (b) leaves wide
gaps in the error branches and the legacy/subscription endpoints.

This file calls the async endpoint functions directly with in-memory
stubs so the tests are order-independent and hit every untested branch.

Target: raise ``app/stripe_billing/routes.py`` from 62% → near-100%.
Missing ranges (from combined stripe-suite coverage run against main):
    51, 143-144, 175-177, 189-191, 236-275, 337-370, 398-446,
    474-503, 523-554

These are almost entirely error-handling and endpoint-body branches
that never get touched by the happy-path router tests.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest
import redis
import stripe
import structlog

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.authz import IngestionPrincipal  # noqa: E402
from app.stripe_billing import (  # noqa: E402
    customers as customers_mod,
    helpers as helpers_mod,
    plans as plans_mod,
    routes as routes_mod,
    state as state_mod,
)
from app.stripe_billing.models import (  # noqa: E402
    BillingPortalRequest,
    CheckoutRequest,
)


# ── Small fixtures ─────────────────────────────────────────────────────────


def _principal(
    scopes: Optional[list[str]] = None,
    tenant_id: Optional[str] = None,
    key_id: str = "test-key",
) -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id=key_id,
        scopes=scopes or ["*"],
        tenant_id=tenant_id,
        auth_mode="test",
    )


@pytest.fixture(autouse=True)
def _stub_configure_stripe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Don't hit the real ``STRIPE_SECRET_KEY`` env — tests pin their own
    surface area.  Every endpoint calls ``_configure_stripe`` as its first
    line; replace it with a no-op so we don't bleed into other env-dependent
    validation."""
    monkeypatch.setattr(helpers_mod, "_configure_stripe", lambda: None)


@pytest.fixture(autouse=True)
def _stub_emit_funnel_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """``emit_funnel_event`` reaches out to a live HTTP funnel endpoint in
    prod. Swap for a noop so tests stay hermetic."""
    import shared.funnel_events as funnel_events

    monkeypatch.setattr(
        funnel_events, "emit_funnel_event", lambda **_kwargs: True
    )


# ── list_plans ──────────────────────────────────────────────────────────────


class TestListPlans:
    @pytest.mark.asyncio
    async def test_returns_all_plans_with_expected_shape(self) -> None:
        """Every plan dict contains id/name/price/features/limits — the
        front-end relies on this contract."""
        result = await routes_mod.list_plans()
        assert "plans" in result
        assert len(result["plans"]) == len(plans_mod.PLANS)
        for plan in result["plans"]:
            assert set(plan.keys()) == {
                "id",
                "name",
                "price_monthly",
                "price_annual",
                "features",
                "limits",
            }


# ── create_checkout — error branches not touched by the happy-path test ────


class TestCreateCheckoutErrorBranches:
    """Covers lines 143-144, 175-177, 189-191."""

    @pytest.fixture(autouse=True)
    def _configure_price_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``_resolve_price_id`` reads STRIPE_PRICE_{PLAN}_{PERIOD} from env
        and raises a 500 if unset. Pin one so the test reaches the
        error-branch code we actually want to exercise."""
        monkeypatch.setenv("STRIPE_PRICE_GROWTH_MONTHLY", "price_growth_monthly")

    @pytest.fixture
    def base_request(self) -> CheckoutRequest:
        return CheckoutRequest(
            plan_id="growth",
            billing_period="monthly",
            tenant_name="Acme",
            customer_email="ops@example.com",
            # These two must be allowlisted — defaults to regengine.co.
        )

    @pytest.mark.asyncio
    async def test_redis_error_on_existing_customer_lookup_logs_and_continues(
        self, monkeypatch: pytest.MonkeyPatch, base_request: CheckoutRequest
    ) -> None:
        """#1184 + checkout flow: if Redis is down when we look up the
        existing Stripe customer, we still create the checkout session
        (without the ``customer`` kwarg) rather than blocking the user
        from paying."""

        def _boom(_tenant_id: str) -> None:
            raise redis.RedisError("conn dropped")

        monkeypatch.setattr(customers_mod, "_get_existing_customer_id", _boom)
        monkeypatch.setattr(
            customers_mod, "_record_checkout_session_hint", lambda **_: None
        )

        class _Session:
            id = "cs_test_123"
            url = "https://checkout.stripe.com/c/pay/cs_test_123"

        monkeypatch.setattr(
            stripe.checkout.Session, "create", lambda **kwargs: _Session()
        )

        response = await routes_mod.create_checkout(
            base_request, x_tenant_id=None, principal=_principal()
        )
        # Still returns a session — checkout is not blocked by Redis outage.
        assert response.session_id == "cs_test_123"
        assert response.plan == "growth"

    @pytest.mark.asyncio
    async def test_existing_customer_id_sets_customer_kwarg(
        self, monkeypatch: pytest.MonkeyPatch, base_request: CheckoutRequest
    ) -> None:
        """Line 169: when a prior Stripe customer exists for this tenant
        the Session.create call must receive ``customer=...`` so the
        same payment method is remembered."""
        captured: dict[str, Any] = {}

        monkeypatch.setattr(
            customers_mod, "_get_existing_customer_id", lambda _: "cus_existing"
        )
        monkeypatch.setattr(
            customers_mod, "_record_checkout_session_hint", lambda **_: None
        )

        class _Session:
            id = "cs_456"
            url = "https://checkout.stripe.com/c/pay/cs_456"

        def _create(**kwargs: Any) -> _Session:
            captured.update(kwargs)
            return _Session()

        monkeypatch.setattr(stripe.checkout.Session, "create", _create)

        response = await routes_mod.create_checkout(
            base_request, x_tenant_id=None, principal=_principal(tenant_id="tenant-checkout")
        )
        assert response.session_id == "cs_456"
        assert captured["customer"] == "cus_existing"
        # customer_email must NOT also be set — passing both would cause
        # Stripe to reject the session.
        assert "customer_email" not in captured

    @pytest.mark.asyncio
    async def test_stripe_error_maps_to_502_with_user_message(
        self, monkeypatch: pytest.MonkeyPatch, base_request: CheckoutRequest
    ) -> None:
        """Lines 175-177: a StripeError at session create time must
        surface as a 502 with ``user_message`` (the version safe to
        show an end user) rather than a 500."""
        monkeypatch.setattr(customers_mod, "_get_existing_customer_id", lambda _: None)

        class _Err(stripe.error.StripeError):
            @property
            def user_message(self) -> str:
                return "Card declined"

        def _raise(**_kwargs: Any) -> Any:
            raise _Err("internal stripe diag")

        monkeypatch.setattr(stripe.checkout.Session, "create", _raise)

        with pytest.raises(Exception) as excinfo:
            await routes_mod.create_checkout(
                base_request, x_tenant_id=None, principal=_principal()
            )
        exc = excinfo.value
        assert getattr(exc, "status_code", None) == 502
        assert "Card declined" in getattr(exc, "detail", "")

    @pytest.mark.asyncio
    async def test_unauthenticated_caller_reaches_signup_flow(
        self, monkeypatch: pytest.MonkeyPatch, base_request: CheckoutRequest
    ) -> None:
        """Lines 111-116: self-serve signup. When there is no principal
        and no X-Tenant-ID, ``_resolve_tenant_context`` raises 400. We
        catch it, set ``authenticated_tenant_id=None``, and proceed — the
        webhook provisions a fresh tenant after payment."""
        monkeypatch.setattr(customers_mod, "_get_existing_customer_id", lambda _: None)
        monkeypatch.setattr(
            customers_mod, "_record_checkout_session_hint", lambda **_: None
        )

        captured: dict[str, Any] = {}

        class _Session:
            id = "cs_signup"
            url = "https://checkout.stripe.com/c/pay/cs_signup"

        def _create(**kwargs: Any) -> _Session:
            captured.update(kwargs)
            return _Session()

        monkeypatch.setattr(stripe.checkout.Session, "create", _create)

        response = await routes_mod.create_checkout(
            base_request,
            x_tenant_id=None,
            principal=None,  # unauthenticated
        )
        assert response.session_id == "cs_signup"
        # No tenant_id in metadata since the caller was unauthenticated —
        # the webhook will attach one after admin-service provisioning.
        assert "tenant_id" not in captured["metadata"]

    @pytest.mark.asyncio
    async def test_client_tenant_mismatch_is_logged_and_ignored(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """#1184: a client cannot attach its own ``tenant_id``; the
        authenticated tenant always wins. The mismatch must be logged
        for audit as a structlog event."""
        monkeypatch.setattr(customers_mod, "_get_existing_customer_id", lambda _: None)
        monkeypatch.setattr(
            customers_mod, "_record_checkout_session_hint", lambda **_: None
        )

        class _Session:
            id = "cs_mismatch"
            url = "https://checkout.stripe.com/c/pay/cs_mismatch"

        captured: dict[str, Any] = {}

        def _create(**kwargs: Any) -> _Session:
            captured.update(kwargs)
            return _Session()

        monkeypatch.setattr(stripe.checkout.Session, "create", _create)

        with structlog.testing.capture_logs() as log_entries:
            await routes_mod.create_checkout(
                CheckoutRequest(
                    plan_id="growth",
                    billing_period="monthly",
                    # Mismatch: client says tenant-evil, principal says tenant-good.
                    tenant_id="tenant-evil",
                ),
                x_tenant_id=None,
                principal=_principal(tenant_id="tenant-good"),
            )

        # The authenticated tenant wins in the checkout metadata.
        assert captured["metadata"]["tenant_id"] == "tenant-good"
        # A warning was logged about the client-supplied mismatch — the
        # structured fields must travel with it for audit.
        mismatch_entries = [
            entry
            for entry in log_entries
            if entry.get("event") == "checkout_ignored_client_tenant_id"
        ]
        assert mismatch_entries, f"expected mismatch log; got {log_entries!r}"
        entry = mismatch_entries[0]
        assert entry["log_level"] == "warning"
        assert entry["client_tenant"] == "tenant-evil"
        assert entry["auth_tenant"] == "tenant-good"

    @pytest.mark.asyncio
    async def test_redis_error_on_record_session_hint_does_not_block_checkout(
        self, monkeypatch: pytest.MonkeyPatch, base_request: CheckoutRequest
    ) -> None:
        """Lines 189-191: if we can't write the session-hint to Redis,
        the user's payment still goes through. The hint is only a
        convenience for later dashboard display."""
        monkeypatch.setattr(customers_mod, "_get_existing_customer_id", lambda _: None)

        def _boom(**_kwargs: Any) -> None:
            raise redis.RedisError("write dropped")

        monkeypatch.setattr(
            customers_mod, "_record_checkout_session_hint", _boom
        )

        class _Session:
            id = "cs_hint_failed"
            url = "https://checkout.stripe.com/c/pay/cs_hint_failed"

        monkeypatch.setattr(
            stripe.checkout.Session, "create", lambda **kwargs: _Session()
        )

        response = await routes_mod.create_checkout(
            base_request, x_tenant_id=None, principal=_principal()
        )
        # Redis failure on the hint is logged and swallowed.
        assert response.session_id == "cs_hint_failed"


# ── get_subscription ───────────────────────────────────────────────────────


class TestGetSubscription:
    """Lines 236-275. The endpoint depends on ``_verify_api_key`` which
    is a FastAPI dependency; when calling the coroutine directly we
    bypass it with ``_=None``."""

    @pytest.mark.asyncio
    async def test_redis_error_raises_503(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(_tenant_id: str) -> None:
            raise redis.RedisError("conn dropped")

        monkeypatch.setattr(state_mod, "_get_subscription_mapping", _boom)

        with pytest.raises(Exception) as excinfo:
            await routes_mod.get_subscription("tenant-x", _=None)
        exc = excinfo.value
        assert getattr(exc, "status_code", None) == 503

    @pytest.mark.asyncio
    async def test_missing_mapping_returns_none_plan(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            state_mod, "_get_subscription_mapping", lambda _t: {}
        )
        result = await routes_mod.get_subscription("tenant-no-mapping", _=None)
        assert result.plan == "none"
        assert result.status == "none"
        assert result.events_used == 0
        assert result.events_limit == 0

    @pytest.mark.asyncio
    async def test_mapping_without_subscription_id_returns_stored_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            state_mod,
            "_get_subscription_mapping",
            lambda _t: {
                "plan_id": "growth",
                "status": "checkout_pending",
                "current_period_end": "2030-01-01T00:00:00+00:00",
            },
        )
        result = await routes_mod.get_subscription("tenant-mid-flow", _=None)
        assert result.plan == "growth"
        assert result.status == "checkout_pending"
        assert result.current_period_end == "2030-01-01T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_mapping_with_subscription_id_refreshes_from_stripe(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            state_mod,
            "_get_subscription_mapping",
            lambda _t: {
                "plan_id": "growth",
                "status": "trialing",
                "subscription_id": "sub_live_1",
                "current_period_end": "old",
            },
        )
        stored: dict[str, Any] = {}
        monkeypatch.setattr(
            state_mod,
            "_store_subscription_mapping",
            lambda t, mapping: stored.update(mapping),
        )

        monkeypatch.setattr(
            stripe.Subscription,
            "retrieve",
            lambda sub_id: {
                "status": "active",
                # Epoch seconds → helpers._format_period_end → ISO string.
                "current_period_end": 1_800_000_000,
            },
        )

        result = await routes_mod.get_subscription("tenant-sub-refresh", _=None)
        assert result.status == "active"
        assert result.current_period_end is not None
        assert "2027" in result.current_period_end  # 1_800_000_000 ≈ 2027
        # The refreshed state was persisted.
        assert stored["status"] == "active"


# ── stripe_webhooks / stripe_webhook_legacy thin wrappers ──────────────────


class TestWebhookRouteWrappers:
    """Lines 297 and 311 are the one-line bodies of the two webhook routes.
    They both delegate to ``_webhooks_mod._process_stripe_webhook``. Cover
    both so future refactors don't silently drop one endpoint."""

    @pytest.mark.asyncio
    async def test_primary_webhook_delegates_to_processor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.stripe_billing import webhooks as webhooks_mod

        called: dict[str, Any] = {}

        async def _fake_process(request: Any, sig: Any) -> dict[str, Any]:
            called["request"] = request
            called["sig"] = sig
            return {"received": True}

        monkeypatch.setattr(webhooks_mod, "_process_stripe_webhook", _fake_process)

        request = MagicMock()
        result = await routes_mod.stripe_webhooks(
            request, stripe_signature="t=1,v1=fake"
        )
        assert result == {"received": True}
        assert called["request"] is request
        assert called["sig"] == "t=1,v1=fake"

    @pytest.mark.asyncio
    async def test_legacy_webhook_delegates_to_processor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ``/webhook/stripe`` path is retained for backward compat;
        must call the same processor as the primary route."""
        from app.stripe_billing import webhooks as webhooks_mod

        called: dict[str, Any] = {}

        async def _fake_process(request: Any, sig: Any) -> dict[str, Any]:
            called["request"] = request
            called["sig"] = sig
            return {"received": True, "legacy": True}

        monkeypatch.setattr(webhooks_mod, "_process_stripe_webhook", _fake_process)

        request = MagicMock()
        result = await routes_mod.stripe_webhook_legacy(
            request, stripe_signature="t=2,v1=fake"
        )
        assert result == {"received": True, "legacy": True}
        assert called["sig"] == "t=2,v1=fake"


# ── create_portal_session_for_tenant ───────────────────────────────────────


class TestCreatePortalSessionForTenant:
    """Lines 337-370."""

    def _req(self, return_url: Optional[str] = None) -> BillingPortalRequest:
        return BillingPortalRequest(
            tenant_id="tenant-portal",
            tenant_name="Acme",
            customer_email="ops@example.com",
            return_url=return_url,
        )

    @pytest.mark.asyncio
    async def test_with_client_return_url_uses_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Line 337-340: client-supplied return_url is validated and used."""
        monkeypatch.setattr(
            customers_mod, "_ensure_customer_mapping", lambda **_: "cus_p1"
        )
        captured: dict[str, Any] = {}

        class _Portal:
            url = "https://billing.stripe.com/session/p1"

        def _create(customer_id: str, return_url: str) -> Any:
            captured["customer_id"] = customer_id
            captured["return_url"] = return_url
            return _Portal()

        monkeypatch.setattr(customers_mod, "_create_portal_session", _create)

        result = await routes_mod.create_portal_session_for_tenant(
            self._req(return_url="https://regengine.co/billing-done"),
            x_tenant_id=None,
            principal=_principal(),
        )
        assert result.portal_url == "https://billing.stripe.com/session/p1"
        assert captured["customer_id"] == "cus_p1"
        assert captured["return_url"] == "https://regengine.co/billing-done"

    @pytest.mark.asyncio
    async def test_without_client_return_url_uses_env_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 342-345: missing client return_url falls back to
        STRIPE_PORTAL_RETURN_URL env, which is ALSO validated — so a
        misconfigured env variable fails loudly rather than silently
        shipping an open redirect."""
        monkeypatch.setenv(
            "STRIPE_PORTAL_RETURN_URL", "https://app.regengine.co/settings"
        )
        monkeypatch.setattr(
            customers_mod, "_ensure_customer_mapping", lambda **_: "cus_env"
        )
        captured: dict[str, Any] = {}

        class _Portal:
            url = "https://billing.stripe.com/session/env"

        def _create(customer_id: str, return_url: str) -> Any:
            captured["return_url"] = return_url
            return _Portal()

        monkeypatch.setattr(customers_mod, "_create_portal_session", _create)

        await routes_mod.create_portal_session_for_tenant(
            self._req(),  # no return_url
            x_tenant_id=None,
            principal=_principal(),
        )
        assert captured["return_url"] == "https://app.regengine.co/settings"

    @pytest.mark.asyncio
    async def test_redis_error_on_ensure_customer_raises_503(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(**_kwargs: Any) -> None:
            raise redis.RedisError("conn dropped")

        monkeypatch.setattr(customers_mod, "_ensure_customer_mapping", _boom)

        with pytest.raises(Exception) as excinfo:
            await routes_mod.create_portal_session_for_tenant(
                self._req(), x_tenant_id=None, principal=_principal()
            )
        assert getattr(excinfo.value, "status_code", None) == 503

    @pytest.mark.asyncio
    async def test_stripe_error_on_portal_create_raises_502(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            customers_mod, "_ensure_customer_mapping", lambda **_: "cus_err"
        )

        class _Err(stripe.error.StripeError):
            @property
            def user_message(self) -> str:
                return "Portal unavailable"

        def _raise(**_kwargs: Any) -> Any:
            raise _Err("internal")

        monkeypatch.setattr(customers_mod, "_create_portal_session", _raise)

        with pytest.raises(Exception) as excinfo:
            await routes_mod.create_portal_session_for_tenant(
                self._req(), x_tenant_id=None, principal=_principal()
            )
        assert getattr(excinfo.value, "status_code", None) == 502
        assert "Portal unavailable" in getattr(excinfo.value, "detail", "")

    @pytest.mark.asyncio
    async def test_missing_portal_url_raises_502(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Line 368: Stripe returned a session object without a URL
        (observed in the wild when the portal configuration is missing)."""
        monkeypatch.setattr(
            customers_mod, "_ensure_customer_mapping", lambda **_: "cus_missing"
        )

        class _NoUrlPortal:
            url = ""

        monkeypatch.setattr(
            customers_mod,
            "_create_portal_session",
            lambda **_kwargs: _NoUrlPortal(),
        )

        with pytest.raises(Exception) as excinfo:
            await routes_mod.create_portal_session_for_tenant(
                self._req(), x_tenant_id=None, principal=_principal()
            )
        assert getattr(excinfo.value, "status_code", None) == 502
        assert "missing portal URL" in getattr(excinfo.value, "detail", "")


# ── list_invoices ──────────────────────────────────────────────────────────


class TestListInvoices:
    """Lines 398-446."""

    @pytest.mark.asyncio
    async def test_redis_error_raises_503(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(_t: str) -> None:
            raise redis.RedisError("conn dropped")

        monkeypatch.setattr(state_mod, "_get_subscription_mapping", _boom)

        with pytest.raises(Exception) as excinfo:
            await routes_mod.list_invoices(
                tenant_id="tenant-invs",
                limit=25,
                starting_after=None,
                x_tenant_id=None,
                principal=_principal(),
            )
        assert getattr(excinfo.value, "status_code", None) == 503

    @pytest.mark.asyncio
    async def test_missing_customer_id_raises_404(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            state_mod, "_get_subscription_mapping", lambda _t: {"customer_id": "  "}
        )
        with pytest.raises(Exception) as excinfo:
            await routes_mod.list_invoices(
                tenant_id="tenant-no-cus",
                limit=25,
                starting_after=None,
                x_tenant_id=None,
                principal=_principal(),
            )
        assert getattr(excinfo.value, "status_code", None) == 404

    @pytest.mark.asyncio
    async def test_stripe_list_error_raises_502(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            state_mod,
            "_get_subscription_mapping",
            lambda _t: {"customer_id": "cus_1"},
        )

        class _Err(stripe.error.StripeError):
            @property
            def user_message(self) -> str:
                return "rate limited"

        def _raise(**_kwargs: Any) -> Any:
            raise _Err("internal")

        monkeypatch.setattr(stripe.Invoice, "list", _raise)

        with pytest.raises(Exception) as excinfo:
            await routes_mod.list_invoices(
                tenant_id="tenant-stripe-err",
                limit=25,
                starting_after=None,
                x_tenant_id=None,
                principal=_principal(),
            )
        assert getattr(excinfo.value, "status_code", None) == 502
        assert "rate limited" in getattr(excinfo.value, "detail", "")

    @pytest.mark.asyncio
    async def test_happy_path_returns_paginated_summary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            state_mod,
            "_get_subscription_mapping",
            lambda _t: {"customer_id": "cus_p"},
        )

        captured: dict[str, Any] = {}

        def _list(**kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {
                "data": [
                    {
                        "id": "in_1",
                        "amount_due": 1000,
                        "amount_paid": 1000,
                        "currency": "usd",
                        "status": "paid",
                        "created": 1_700_000_000,
                        "invoice_pdf": "https://files.stripe.com/pdf/in_1",
                        "hosted_invoice_url": "https://billing.stripe.com/in/in_1",
                    },
                    # Invoice with NO id is skipped (line 428).
                    {"amount_due": 99},
                    {
                        "id": "in_2",
                        "amount_due": 500,
                        "amount_paid": 0,
                        "currency": "usd",
                        "status": "open",
                        "created": 1_700_000_100,
                        "invoice_pdf": None,
                        "hosted_invoice_url": None,
                    },
                ],
                "has_more": True,
            }

        monkeypatch.setattr(stripe.Invoice, "list", _list)

        result = await routes_mod.list_invoices(
            tenant_id="tenant-happy",
            limit=50,
            starting_after="in_prev",
            x_tenant_id=None,
            principal=_principal(),
        )

        assert captured["customer"] == "cus_p"
        assert captured["limit"] == 50
        # starting_after forwarded as pagination cursor.
        assert captured["starting_after"] == "in_prev"
        # Only two summaries: the id-less invoice was skipped.
        assert len(result.invoices) == 2
        assert result.invoices[0].invoice_id == "in_1"
        assert result.has_more is True
        # next_cursor is the id of the last returned summary.
        assert result.next_cursor == "in_2"

    @pytest.mark.asyncio
    async def test_empty_invoice_list_has_none_cursor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            state_mod,
            "_get_subscription_mapping",
            lambda _t: {"customer_id": "cus_empty"},
        )
        monkeypatch.setattr(
            stripe.Invoice, "list", lambda **_: {"data": [], "has_more": False}
        )

        result = await routes_mod.list_invoices(
            tenant_id="tenant-empty",
            limit=25,
            starting_after=None,
            x_tenant_id=None,
            principal=_principal(),
        )
        assert result.invoices == []
        assert result.has_more is False
        assert result.next_cursor is None


# ── get_invoice_pdf ────────────────────────────────────────────────────────


class TestGetInvoicePdf:
    """Lines 474-503."""

    @pytest.mark.asyncio
    async def test_redis_error_raises_503(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(_t: str) -> None:
            raise redis.RedisError("conn dropped")

        monkeypatch.setattr(state_mod, "_get_subscription_mapping", _boom)

        with pytest.raises(Exception) as excinfo:
            await routes_mod.get_invoice_pdf(
                invoice_id="in_1",
                tenant_id="tenant-pdf",
                x_tenant_id=None,
                principal=_principal(),
            )
        assert getattr(excinfo.value, "status_code", None) == 503

    @pytest.mark.asyncio
    async def test_missing_customer_id_raises_404(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            state_mod, "_get_subscription_mapping", lambda _t: {}
        )
        with pytest.raises(Exception) as excinfo:
            await routes_mod.get_invoice_pdf(
                invoice_id="in_1",
                tenant_id="tenant-no-cus",
                x_tenant_id=None,
                principal=_principal(),
            )
        assert getattr(excinfo.value, "status_code", None) == 404

    @pytest.mark.asyncio
    async def test_invalid_request_error_returns_404(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 486-487: Stripe's InvalidRequestError on retrieve means
        the invoice doesn't exist — surface as 404 (not 502) so clients
        know to stop retrying."""
        monkeypatch.setattr(
            state_mod,
            "_get_subscription_mapping",
            lambda _t: {"customer_id": "cus_1"},
        )

        def _raise(_id: str) -> Any:
            raise stripe.error.InvalidRequestError("no such invoice", param="id")

        monkeypatch.setattr(stripe.Invoice, "retrieve", _raise)

        with pytest.raises(Exception) as excinfo:
            await routes_mod.get_invoice_pdf(
                invoice_id="in_404",
                tenant_id="tenant-1",
                x_tenant_id=None,
                principal=_principal(),
            )
        assert getattr(excinfo.value, "status_code", None) == 404

    @pytest.mark.asyncio
    async def test_stripe_error_raises_502(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            state_mod,
            "_get_subscription_mapping",
            lambda _t: {"customer_id": "cus_1"},
        )

        class _Err(stripe.error.StripeError):
            @property
            def user_message(self) -> str:
                return "Stripe is down"

        def _raise(_id: str) -> Any:
            raise _Err("internal")

        monkeypatch.setattr(stripe.Invoice, "retrieve", _raise)

        with pytest.raises(Exception) as excinfo:
            await routes_mod.get_invoice_pdf(
                invoice_id="in_err",
                tenant_id="tenant-1",
                x_tenant_id=None,
                principal=_principal(),
            )
        assert getattr(excinfo.value, "status_code", None) == 502
        assert "Stripe is down" in getattr(excinfo.value, "detail", "")

    @pytest.mark.asyncio
    async def test_cross_tenant_invoice_returns_404(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Defense: if the invoice's customer doesn't match the tenant's
        customer, we MUST return 404 — never leak another tenant's
        billing metadata."""
        monkeypatch.setattr(
            state_mod,
            "_get_subscription_mapping",
            lambda _t: {"customer_id": "cus_mine"},
        )
        monkeypatch.setattr(
            stripe.Invoice,
            "retrieve",
            lambda _id: {
                "id": "in_1",
                "customer": "cus_other",  # different tenant's customer
                "invoice_pdf": "https://files.stripe.com/secret",
                "status": "paid",
                "created": 1_700_000_000,
                "hosted_invoice_url": "https://billing.stripe.com/secret",
            },
        )

        with pytest.raises(Exception) as excinfo:
            await routes_mod.get_invoice_pdf(
                invoice_id="in_1",
                tenant_id="tenant-mine",
                x_tenant_id=None,
                principal=_principal(),
            )
        assert getattr(excinfo.value, "status_code", None) == 404

    @pytest.mark.asyncio
    async def test_missing_pdf_url_returns_404(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 499-501: Stripe returned the invoice but no PDF URL
        (draft invoice, etc). This is 404 not 502."""
        monkeypatch.setattr(
            state_mod,
            "_get_subscription_mapping",
            lambda _t: {"customer_id": "cus_mine"},
        )
        monkeypatch.setattr(
            stripe.Invoice,
            "retrieve",
            lambda _id: {
                "id": "in_draft",
                "customer": "cus_mine",
                "invoice_pdf": "",  # no PDF yet
                "status": "draft",
                "created": 1_700_000_000,
                "hosted_invoice_url": None,
            },
        )

        with pytest.raises(Exception) as excinfo:
            await routes_mod.get_invoice_pdf(
                invoice_id="in_draft",
                tenant_id="tenant-mine",
                x_tenant_id=None,
                principal=_principal(),
            )
        assert getattr(excinfo.value, "status_code", None) == 404
        assert "does not have a PDF URL" in getattr(excinfo.value, "detail", "")

    @pytest.mark.asyncio
    async def test_happy_path_returns_pdf_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            state_mod,
            "_get_subscription_mapping",
            lambda _t: {"customer_id": "cus_mine"},
        )
        monkeypatch.setattr(
            stripe.Invoice,
            "retrieve",
            lambda _id: {
                "id": "in_ok",
                "customer": "cus_mine",
                "invoice_pdf": "https://files.stripe.com/pdf/in_ok",
                "status": "paid",
                "created": 1_700_000_000,
                "hosted_invoice_url": "https://billing.stripe.com/in/in_ok",
            },
        )

        result = await routes_mod.get_invoice_pdf(
            invoice_id="in_ok",
            tenant_id="tenant-mine",
            x_tenant_id=None,
            principal=_principal(),
        )
        assert result.invoice_id == "in_ok"
        assert result.pdf_url == "https://files.stripe.com/pdf/in_ok"
        assert result.status == "paid"


# ── create_portal_session_legacy ───────────────────────────────────────────


class TestCreatePortalSessionLegacy:
    """Lines 523-554. Companion to the non-legacy portal endpoint."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_portal_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            customers_mod,
            "_ensure_customer_mapping",
            lambda **_: "cus_legacy",
        )

        class _Portal:
            url = "https://billing.stripe.com/session/legacy"

        monkeypatch.setattr(
            customers_mod, "_create_portal_session", lambda **_: _Portal()
        )

        result = await routes_mod.create_portal_session_legacy(
            "tenant-legacy", _=None
        )
        assert result.portal_url == "https://billing.stripe.com/session/legacy"
        assert result.customer_id == "cus_legacy"
        assert result.tenant_id == "tenant-legacy"

    @pytest.mark.asyncio
    async def test_redis_error_raises_503(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(**_kwargs: Any) -> None:
            raise redis.RedisError("conn dropped")

        monkeypatch.setattr(customers_mod, "_ensure_customer_mapping", _boom)

        with pytest.raises(Exception) as excinfo:
            await routes_mod.create_portal_session_legacy(
                "tenant-legacy-err", _=None
            )
        assert getattr(excinfo.value, "status_code", None) == 503

    @pytest.mark.asyncio
    async def test_stripe_error_raises_502(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            customers_mod, "_ensure_customer_mapping", lambda **_: "cus_x"
        )

        class _Err(stripe.error.StripeError):
            @property
            def user_message(self) -> str:
                return "portal offline"

        def _raise(**_kwargs: Any) -> Any:
            raise _Err("internal")

        monkeypatch.setattr(customers_mod, "_create_portal_session", _raise)

        with pytest.raises(Exception) as excinfo:
            await routes_mod.create_portal_session_legacy(
                "tenant-legacy-502", _=None
            )
        assert getattr(excinfo.value, "status_code", None) == 502
        assert "portal offline" in getattr(excinfo.value, "detail", "")

    @pytest.mark.asyncio
    async def test_missing_portal_url_raises_502(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            customers_mod, "_ensure_customer_mapping", lambda **_: "cus_x"
        )

        class _NoUrl:
            url = ""

        monkeypatch.setattr(
            customers_mod, "_create_portal_session", lambda **_: _NoUrl()
        )

        with pytest.raises(Exception) as excinfo:
            await routes_mod.create_portal_session_legacy(
                "tenant-legacy-no-url", _=None
            )
        assert getattr(excinfo.value, "status_code", None) == 502
        assert "missing portal URL" in getattr(excinfo.value, "detail", "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
