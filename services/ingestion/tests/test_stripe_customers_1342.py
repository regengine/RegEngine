"""Unit tests for ``app.stripe_billing.customers`` — issue #1342.

Raises coverage from 62% to 100% by covering the error branches and
the async admin-service call path that existing Stripe webhook tests
mock past rather than exercise.

Pinned behaviors:
  - ``_create_tenant_via_admin``: requires ADMIN_SERVICE_URL and
    ADMIN_MASTER_KEY; both errors raise RuntimeError (never leak to
    HTTP 500). On success, the ``tenant_id`` must be present in the
    admin response or RuntimeError is raised — a silent tenant with no
    id is a worse failure mode than a noisy rejection.
  - ``_create_portal_session``: two SDK variants (``billing_portal.sessions``
    vs legacy ``billing_portal.Session``); plus the HTTPException(500)
    when neither is available.
  - ``_create_customer_for_tenant``: StripeError → HTTPException(502)
    with ``user_message`` preferred over ``str(exc)`` (we expose the
    user-safe message, never the raw stripe internals).
  - ``_ensure_customer_mapping``: short-circuits when mapping already
    has a customer_id; otherwise creates + stores.
  - ``_get_existing_customer_id``: None tenant_id → None (never call
    Redis with an empty key); empty customer_id in mapping → None.
  - ``_record_checkout_session_hint``: None tenant_id is a no-op (the
    mapping is keyed on tenant, so there's nothing to record without
    one).

These are all fire-and-forget code paths that run inside Stripe
webhook handlers; a crash in any of them would corrupt Stripe's
retry window and stall tenant provisioning.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")
pytest.importorskip("stripe")

import structlog  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.stripe_billing import customers as mod  # noqa: E402


# ---------------------------------------------------------------------------
# customers.py now uses structlog.get_logger(...). Stripe/StripeError paths
# emit structured events and we assert on them with
# structlog.testing.capture_logs() where needed.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _create_tenant_via_admin — async HTTP call to admin service
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeClient:
    """Async context manager stand-in for ``resilient_client``."""

    def __init__(self, response: _FakeResponse, captured: dict):
        self._response = response
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, *, headers=None, json=None):
        self._captured["url"] = url
        self._captured["headers"] = headers or {}
        self._captured["json"] = json or {}
        return self._response


def _install_fake_resilient_client(
    monkeypatch, *, payload: dict, status_code: int = 200
) -> dict:
    """Replace ``resilient_client`` in mod with a fake that captures
    the outbound request. Returns the captured dict so tests can assert.
    """
    captured: dict = {}

    def _factory(*, timeout, circuit_name):
        captured["timeout"] = timeout
        captured["circuit_name"] = circuit_name
        return _FakeClient(_FakeResponse(payload, status_code), captured)

    monkeypatch.setattr(mod, "resilient_client", _factory)
    return captured


class TestCreateTenantViaAdmin:
    def test_missing_admin_service_url_raises_runtime_error(self, monkeypatch):
        monkeypatch.delenv("ADMIN_SERVICE_URL", raising=False)
        monkeypatch.setenv("ADMIN_MASTER_KEY", "k")
        with pytest.raises(RuntimeError) as ei:
            asyncio.run(mod._create_tenant_via_admin("Acme Inc."))
        assert "ADMIN_SERVICE_URL" in str(ei.value)

    def test_missing_admin_master_key_raises_runtime_error(self, monkeypatch):
        # The key is only checked if the URL is set, so we test it
        # independently. Pins the security invariant: we NEVER hit the
        # admin service without the master key, because the admin API
        # treats missing X-Admin-Key as unauthenticated.
        monkeypatch.setenv("ADMIN_SERVICE_URL", "http://admin.svc")
        monkeypatch.delenv("ADMIN_MASTER_KEY", raising=False)
        with pytest.raises(RuntimeError) as ei:
            asyncio.run(mod._create_tenant_via_admin("Acme Inc."))
        assert "ADMIN_MASTER_KEY" in str(ei.value)

    def test_happy_path_posts_and_returns_tenant_id(self, monkeypatch):
        monkeypatch.setenv("ADMIN_SERVICE_URL", "http://admin.svc/")
        monkeypatch.setenv("ADMIN_MASTER_KEY", "secret-key")
        captured = _install_fake_resilient_client(
            monkeypatch, payload={"tenant_id": "tenant-42"}
        )

        result = asyncio.run(mod._create_tenant_via_admin("Acme Inc."))

        assert result == "tenant-42"
        # Trailing slash must be stripped so we don't emit
        # ``//v1/admin/tenants``.
        assert captured["url"] == "http://admin.svc/v1/admin/tenants"
        assert captured["headers"]["X-Admin-Key"] == "secret-key"
        assert captured["json"] == {"name": "Acme Inc."}
        assert captured["circuit_name"] == "admin-service"
        assert captured["timeout"] == 20.0

    def test_http_error_propagates(self, monkeypatch):
        # ``raise_for_status()`` lets the underlying 5xx bubble up —
        # the outer Stripe webhook handler retries on that.
        monkeypatch.setenv("ADMIN_SERVICE_URL", "http://admin.svc")
        monkeypatch.setenv("ADMIN_MASTER_KEY", "secret")
        _install_fake_resilient_client(
            monkeypatch, payload={}, status_code=500
        )
        with pytest.raises(RuntimeError):
            asyncio.run(mod._create_tenant_via_admin("Acme"))

    def test_missing_tenant_id_in_response_raises(self, monkeypatch):
        # Admin returning 200 but without ``tenant_id`` is worse than a
        # clean 5xx — it would silently orphan the Stripe customer.
        monkeypatch.setenv("ADMIN_SERVICE_URL", "http://admin.svc")
        monkeypatch.setenv("ADMIN_MASTER_KEY", "secret")
        _install_fake_resilient_client(monkeypatch, payload={"other": "x"})
        with pytest.raises(RuntimeError) as ei:
            asyncio.run(mod._create_tenant_via_admin("Acme"))
        assert "tenant_id" in str(ei.value)

    def test_empty_tenant_id_in_response_raises(self, monkeypatch):
        # ``if not tenant_id`` — empty string is falsy, same path.
        monkeypatch.setenv("ADMIN_SERVICE_URL", "http://admin.svc")
        monkeypatch.setenv("ADMIN_MASTER_KEY", "secret")
        _install_fake_resilient_client(monkeypatch, payload={"tenant_id": ""})
        with pytest.raises(RuntimeError):
            asyncio.run(mod._create_tenant_via_admin("Acme"))


# ---------------------------------------------------------------------------
# _create_portal_session — SDK variant handling
# ---------------------------------------------------------------------------


class _SessionsApi:
    def __init__(self):
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": "cs_test"}


class TestCreatePortalSession:
    def test_modern_sessions_api_preferred(self, monkeypatch):
        # ``stripe.billing_portal.sessions.create`` is the modern path.
        sessions = _SessionsApi()
        fake_portal = types.SimpleNamespace(sessions=sessions, Session=None)
        monkeypatch.setattr(mod.stripe, "billing_portal", fake_portal)

        result = mod._create_portal_session("cus_123", "https://return.example")

        assert result == {"id": "cs_test"}
        assert sessions.calls == [
            {"customer": "cus_123", "return_url": "https://return.example"}
        ]

    def test_legacy_session_api_used_when_modern_missing(self, monkeypatch):
        # Legacy ``billing_portal.Session.create`` — kept working for
        # older Stripe SDK pins. Preference order: modern → legacy → 500.
        legacy = _SessionsApi()
        fake_portal = types.SimpleNamespace(sessions=None, Session=legacy)
        monkeypatch.setattr(mod.stripe, "billing_portal", fake_portal)

        result = mod._create_portal_session("cus_123", "https://return.example")

        assert result == {"id": "cs_test"}
        assert legacy.calls[0]["customer"] == "cus_123"

    def test_legacy_used_when_modern_has_no_create(self, monkeypatch):
        # Defensive: modern namespace exists but is missing ``create`` —
        # fall through to legacy rather than raising AttributeError.
        bad_modern = types.SimpleNamespace()  # no `.create`
        legacy = _SessionsApi()
        fake_portal = types.SimpleNamespace(sessions=bad_modern, Session=legacy)
        monkeypatch.setattr(mod.stripe, "billing_portal", fake_portal)

        result = mod._create_portal_session("cus_123", "https://return.example")

        assert legacy.calls, "Expected fallback to legacy Session API"
        assert result == {"id": "cs_test"}

    def test_no_portal_api_raises_http_500(self, monkeypatch):
        # Completely missing portal — SDK not wired up. HTTPException 500
        # rather than a generic AttributeError so the route handler
        # returns a structured error body.
        fake_portal = types.SimpleNamespace(sessions=None, Session=None)
        monkeypatch.setattr(mod.stripe, "billing_portal", fake_portal)

        with pytest.raises(HTTPException) as ei:
            mod._create_portal_session("cus_123", "https://return.example")

        assert ei.value.status_code == 500
        assert "portal" in ei.value.detail.lower()


# ---------------------------------------------------------------------------
# _create_customer_for_tenant — StripeError path
# ---------------------------------------------------------------------------


class _FakeStripeCustomer:
    def __init__(self, customer_id: str | None):
        self._id = customer_id

    def get(self, key, default=None):
        # ``_stripe_get`` uses getattr then dict access; support both.
        if key == "id":
            return self._id
        return default

    @property
    def id(self):
        return self._id


class TestCreateCustomerForTenant:
    def test_happy_path_returns_customer_id(self, monkeypatch):
        captured: dict = {}

        def _fake_create(**kwargs):
            captured.update(kwargs)
            return _FakeStripeCustomer("cus_123")

        monkeypatch.setattr(mod.stripe.Customer, "create", _fake_create)

        result = mod._create_customer_for_tenant(
            tenant_id="tenant-1",
            tenant_name="Acme",
            customer_email="ops@acme.com",
        )

        assert result == "cus_123"
        assert captured["email"] == "ops@acme.com"
        assert captured["name"] == "Acme"
        assert captured["metadata"] == {"tenant_id": "tenant-1"}

    def test_falls_back_to_default_name_when_tenant_name_blank(self, monkeypatch):
        # ``tenant_name or f"Tenant {tenant_id}"`` — None / "" both
        # fall through to the synthesized default. Keeps the Stripe
        # dashboard readable even for anonymous signups.
        captured: dict = {}

        def _fake_create(**kwargs):
            captured.update(kwargs)
            return _FakeStripeCustomer("cus_xyz")

        monkeypatch.setattr(mod.stripe.Customer, "create", _fake_create)

        mod._create_customer_for_tenant(
            tenant_id="tenant-42",
            tenant_name=None,
            customer_email=None,
        )

        assert captured["name"] == "Tenant tenant-42"

    def test_stripe_error_raises_http_502_with_user_message(
        self, monkeypatch
    ):
        # The user-safe message is exposed; raw internals stay in the
        # logs. Regression guard against accidentally echoing stripe's
        # internal stack trace to the API consumer.
        # ``user_message`` on the base class is a read-only property,
        # so subclass with a writable override rather than set directly.
        class _Err(mod.stripe.error.StripeError):
            def __init__(self, msg, user_msg):
                super().__init__(msg)
                self._override = user_msg

            @property
            def user_message(self):
                return self._override

        def _fake_create(**kwargs):
            raise _Err("internal: card declined", "Your card was declined.")

        monkeypatch.setattr(mod.stripe.Customer, "create", _fake_create)

        with structlog.testing.capture_logs() as cap_logs:
            with pytest.raises(HTTPException) as ei:
                mod._create_customer_for_tenant("t", "Acme", "ops@acme.com")

        assert ei.value.status_code == 502
        assert "Your card was declined." in ei.value.detail
        # Raw internals stayed in the logger event, not the HTTP body.
        assert any(
            e["log_level"] == "error"
            and e["event"] == "stripe_customer_create_failed"
            for e in cap_logs
        )

    def test_stripe_error_falls_back_to_str_when_no_user_message(
        self, monkeypatch
    ):
        # ``exc.user_message or str(exc)`` — empty/None user_message
        # means show the technical message rather than an empty body.
        class _Err(mod.stripe.error.StripeError):
            @property
            def user_message(self):
                return None

        def _fake_create(**kwargs):
            raise _Err("raw-fallback")

        monkeypatch.setattr(mod.stripe.Customer, "create", _fake_create)

        with pytest.raises(HTTPException) as ei:
            mod._create_customer_for_tenant("t", "Acme", "ops@acme.com")

        assert ei.value.status_code == 502
        assert "raw-fallback" in ei.value.detail

    def test_empty_customer_id_raises_http_502(self, monkeypatch):
        # Stripe succeeded but returned a bag without ``id`` — worse
        # than a clean error, we can't key anything off it. 502 so the
        # outer webhook handler retries.
        def _fake_create(**kwargs):
            return _FakeStripeCustomer("")  # empty id

        monkeypatch.setattr(mod.stripe.Customer, "create", _fake_create)

        with pytest.raises(HTTPException) as ei:
            mod._create_customer_for_tenant("t", "Acme", "ops@acme.com")

        assert ei.value.status_code == 502
        assert "no customer" in ei.value.detail.lower()


# ---------------------------------------------------------------------------
# _ensure_customer_mapping — idempotency + creation path
# ---------------------------------------------------------------------------


class TestEnsureCustomerMapping:
    def test_existing_customer_id_short_circuits(self, monkeypatch):
        # Already-mapped tenant — MUST NOT call stripe.Customer.create
        # again or we orphan a second Stripe customer per webhook retry.
        monkeypatch.setattr(
            mod, "_get_subscription_mapping", lambda tid: {"customer_id": "cus_exist"}
        )

        def _boom(**kw):  # pragma: no cover — guards against regression
            raise AssertionError("Should not be called when mapping exists")

        monkeypatch.setattr(mod.stripe.Customer, "create", _boom)

        result = mod._ensure_customer_mapping("t", "Acme", "ops@acme.com")
        assert result == "cus_exist"

    def test_whitespace_customer_id_treated_as_empty(self, monkeypatch):
        # ``.strip()`` + truthy check — whitespace counts as missing and
        # we go through the creation path. Guards against a Redis hash
        # containing "  " as a placeholder.
        monkeypatch.setattr(
            mod, "_get_subscription_mapping", lambda tid: {"customer_id": "   "}
        )
        monkeypatch.setattr(
            mod, "_create_customer_for_tenant", lambda **kw: "cus_new"
        )
        stored: dict = {}
        monkeypatch.setattr(
            mod,
            "_store_subscription_mapping",
            lambda tid, payload: stored.update({"tid": tid, "payload": payload}),
        )

        result = mod._ensure_customer_mapping("t", "Acme", "ops@acme.com")

        assert result == "cus_new"
        assert stored["tid"] == "t"
        assert stored["payload"]["customer_id"] == "cus_new"

    def test_creation_preserves_existing_mapping_fields(self, monkeypatch):
        # The stored payload must merge the new customer_id onto
        # anything already in the mapping (session_id, plan_id, etc.)
        # — otherwise webhook retries reset the plan_id to "none".
        existing = {
            "session_id": "cs_old",
            "subscription_id": "sub_old",
            "plan_id": "growth",
            "billing_period": "annual",
            "status": "active",
            "customer_email": "old@acme.com",
            "current_period_end": "2025-12-01",
        }
        monkeypatch.setattr(mod, "_get_subscription_mapping", lambda tid: existing)
        monkeypatch.setattr(
            mod, "_create_customer_for_tenant", lambda **kw: "cus_new"
        )
        stored: list = []
        monkeypatch.setattr(
            mod,
            "_store_subscription_mapping",
            lambda tid, payload: stored.append(payload),
        )

        mod._ensure_customer_mapping("t", "Acme", "ops@acme.com")

        p = stored[0]
        assert p["session_id"] == "cs_old"
        assert p["subscription_id"] == "sub_old"
        assert p["plan_id"] == "growth"
        assert p["billing_period"] == "annual"
        assert p["status"] == "active"
        # customer_email carries over; webhook-supplied only fills if empty.
        assert p["customer_email"] == "old@acme.com"
        assert p["current_period_end"] == "2025-12-01"

    def test_empty_mapping_uses_supplied_email_and_defaults(self, monkeypatch):
        # No existing mapping → sensible defaults for every field
        # (plan_id=none, billing_period=monthly, status=none).
        monkeypatch.setattr(mod, "_get_subscription_mapping", lambda tid: {})
        monkeypatch.setattr(
            mod, "_create_customer_for_tenant", lambda **kw: "cus_new"
        )
        stored: list = []
        monkeypatch.setattr(
            mod,
            "_store_subscription_mapping",
            lambda tid, payload: stored.append(payload),
        )

        mod._ensure_customer_mapping("t", "Acme", "ops@acme.com")

        p = stored[0]
        assert p["plan_id"] == "none"
        assert p["billing_period"] == "monthly"
        assert p["status"] == "none"
        assert p["customer_email"] == "ops@acme.com"


# ---------------------------------------------------------------------------
# _get_existing_customer_id
# ---------------------------------------------------------------------------


class TestGetExistingCustomerId:
    def test_none_tenant_id_returns_none(self, monkeypatch):
        # Defensive — caller passes None when the webhook arrives for a
        # tenant we don't know about yet. Must NOT call Redis with an
        # empty key (would return the wrong tenant via a global hit).
        def _boom(tid):  # pragma: no cover
            raise AssertionError("Should not call Redis with missing tenant")

        monkeypatch.setattr(mod, "_get_subscription_mapping", _boom)
        assert mod._get_existing_customer_id(None) is None

    def test_empty_tenant_id_returns_none(self, monkeypatch):
        # ``if not tenant_id`` — empty string is falsy too.
        def _boom(tid):  # pragma: no cover
            raise AssertionError("Should not call Redis with empty tenant")

        monkeypatch.setattr(mod, "_get_subscription_mapping", _boom)
        assert mod._get_existing_customer_id("") is None

    def test_populated_mapping_returns_customer_id(self, monkeypatch):
        monkeypatch.setattr(
            mod, "_get_subscription_mapping", lambda tid: {"customer_id": "cus_42"}
        )
        assert mod._get_existing_customer_id("t") == "cus_42"

    def test_whitespace_customer_id_returns_none(self, monkeypatch):
        # Whitespace-only value is normalized to None so callers can
        # rely on ``is None`` rather than a ``.strip()`` check.
        monkeypatch.setattr(
            mod, "_get_subscription_mapping", lambda tid: {"customer_id": "  "}
        )
        assert mod._get_existing_customer_id("t") is None

    def test_missing_customer_id_returns_none(self, monkeypatch):
        monkeypatch.setattr(mod, "_get_subscription_mapping", lambda tid: {})
        assert mod._get_existing_customer_id("t") is None


# ---------------------------------------------------------------------------
# _record_checkout_session_hint
# ---------------------------------------------------------------------------


class TestRecordCheckoutSessionHint:
    def test_none_tenant_id_is_no_op(self, monkeypatch):
        # No tenant → no storage key → silent noop. Guards against
        # polluting Redis with anonymous/empty tenant keys.
        def _boom(*a, **kw):  # pragma: no cover
            raise AssertionError("Should not touch Redis without tenant_id")

        monkeypatch.setattr(mod, "_get_subscription_mapping", _boom)
        monkeypatch.setattr(mod, "_store_subscription_mapping", _boom)

        # Returns None and doesn't raise.
        result = mod._record_checkout_session_hint(
            tenant_id=None,
            session_id="cs_1",
            plan_id="growth",
            billing_period="monthly",
            customer_email="ops@acme.com",
            customer_id="cus_1",
        )
        assert result is None

    def test_empty_tenant_id_is_no_op(self, monkeypatch):
        def _boom(*a, **kw):  # pragma: no cover
            raise AssertionError("Should not touch Redis without tenant_id")

        monkeypatch.setattr(mod, "_get_subscription_mapping", _boom)
        monkeypatch.setattr(mod, "_store_subscription_mapping", _boom)
        mod._record_checkout_session_hint(
            tenant_id="",
            session_id="cs_1",
            plan_id="growth",
            billing_period="monthly",
            customer_email=None,
            customer_id=None,
        )

    def test_happy_path_writes_hint_preserving_existing(self, monkeypatch):
        # Existing mapping has subscription_id + last_invoice_id; new
        # hint must not clobber those. Session + plan are what the
        # caller wanted to update.
        existing = {
            "customer_id": "cus_old",
            "subscription_id": "sub_old",
            "status": "active",
            "customer_email": "old@acme.com",
            "current_period_end": "2025-12-01",
            "last_invoice_id": "in_old",
            "last_payment_at": "2025-11-01",
            "last_payment_failure_at": "",
        }
        monkeypatch.setattr(mod, "_get_subscription_mapping", lambda tid: existing)
        captured: list = []
        monkeypatch.setattr(
            mod,
            "_store_subscription_mapping",
            lambda tid, payload: captured.append((tid, payload)),
        )

        mod._record_checkout_session_hint(
            tenant_id="t",
            session_id="cs_new",
            plan_id="scale",
            billing_period="annual",
            customer_email=None,
            customer_id=None,  # fall back to existing customer_id
        )

        tid, p = captured[0]
        assert tid == "t"
        assert p["session_id"] == "cs_new"
        assert p["plan_id"] == "scale"
        assert p["billing_period"] == "annual"
        # Existing fields preserved:
        assert p["customer_id"] == "cus_old"
        assert p["subscription_id"] == "sub_old"
        assert p["status"] == "active"
        assert p["customer_email"] == "old@acme.com"
        assert p["last_invoice_id"] == "in_old"

    def test_supplied_customer_id_overrides_existing(self, monkeypatch):
        # When caller passes customer_id explicitly (e.g. hot off a
        # ``customer.created`` webhook), it takes precedence.
        existing = {"customer_id": "cus_old", "status": "pending"}
        monkeypatch.setattr(mod, "_get_subscription_mapping", lambda tid: existing)
        captured: list = []
        monkeypatch.setattr(
            mod,
            "_store_subscription_mapping",
            lambda tid, payload: captured.append(payload),
        )

        mod._record_checkout_session_hint(
            tenant_id="t",
            session_id="cs_x",
            plan_id="growth",
            billing_period="monthly",
            customer_email="new@acme.com",
            customer_id="cus_new",
        )

        p = captured[0]
        assert p["customer_id"] == "cus_new"

    def test_defaults_when_mapping_is_empty(self, monkeypatch):
        # First-ever hint for a tenant — defaults flow through. Status
        # defaults to "checkout_pending" so the admin UI knows the
        # subscription is mid-flight.
        monkeypatch.setattr(mod, "_get_subscription_mapping", lambda tid: {})
        captured: list = []
        monkeypatch.setattr(
            mod,
            "_store_subscription_mapping",
            lambda tid, payload: captured.append(payload),
        )

        mod._record_checkout_session_hint(
            tenant_id="t",
            session_id="cs_1",
            plan_id="growth",
            billing_period="monthly",
            customer_email="ops@acme.com",
            customer_id="cus_1",
        )

        p = captured[0]
        assert p["customer_id"] == "cus_1"
        assert p["status"] == "checkout_pending"
        assert p["customer_email"] == "ops@acme.com"
        assert p["subscription_id"] == ""
        assert p["last_invoice_id"] == ""
