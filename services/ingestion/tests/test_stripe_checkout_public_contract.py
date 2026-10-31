"""Security contract for the public Stripe checkout surface.

An absent API-key header is an intentional anonymous signup flow. A present
credential is never optional: invalid, expired, revoked, workload-only, and
cross-tenant credentials must fail before Stripe is called.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from app import authz
from app.stripe_billing import rate_limiting as rate_limiting_mod, routes as routes_mod
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from shared.rate_limit import BruteForceLimiter


@pytest.fixture(autouse=True)
def _isolated_checkout_security_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the two independent per-IP budgets deterministic per test."""
    monkeypatch.setenv("REGENGINE_ENV", "test")
    for name in ("RAILWAY_ENVIRONMENT", "VERCEL_ENV", "RENDER", "FLY_APP_NAME", "KUBERNETES_SERVICE_HOST"):
        monkeypatch.delenv(name, raising=False)

    auth_limiter = BruteForceLimiter(
        namespace="test-checkout-auth",
        max_failures=authz._AUTH_FAIL_MAX,
        window_seconds=authz._AUTH_FAIL_WINDOW,
        redis_client=None,
    )
    auth_limiter._redis = None
    monkeypatch.setattr(authz, "_auth_limiter", auth_limiter)

    checkout_limiter = BruteForceLimiter(
        namespace="test-checkout-requests",
        max_failures=rate_limiting_mod._CHECKOUT_RATE_LIMIT,
        window_seconds=rate_limiting_mod._CHECKOUT_WINDOW,
        redis_client=None,
    )
    checkout_limiter._redis = None
    monkeypatch.setattr(rate_limiting_mod, "_checkout_limiter", checkout_limiter)


@pytest.fixture
def checkout_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, list[dict[str, Any]]]:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_checkout_contract")
    monkeypatch.setenv("STRIPE_PRICE_LIST_MONTHLY", "price_list_monthly")

    stripe_calls: list[dict[str, Any]] = []

    class _Session:
        id = "cs_checkout_contract"
        url = "https://checkout.stripe.com/c/pay/cs_checkout_contract"

    def _create(**kwargs: Any) -> _Session:
        stripe_calls.append(kwargs)
        return _Session()

    monkeypatch.setattr(routes_mod.stripe.checkout.Session, "create", _create)
    monkeypatch.setattr(routes_mod._customers_mod, "_get_existing_customer_id", lambda _tenant_id: None)
    monkeypatch.setattr(routes_mod._customers_mod, "_record_checkout_session_hint", lambda **_kwargs: None)
    monkeypatch.setattr(routes_mod._funnel_mod, "emit_funnel_event", lambda **_kwargs: True)

    app = FastAPI()
    app.include_router(routes_mod.router)
    return TestClient(app, raise_server_exceptions=False), stripe_calls


def test_no_credential_is_anonymous_and_untrusted_tenant_header_is_ignored(checkout_client) -> None:
    client, stripe_calls = checkout_client

    response = client.post(
        "/api/v1/billing/checkout",
        headers={"X-Tenant-ID": "attacker-selected-tenant"},
        json={"plan_id": "growth", "tenant_id": "body-selected-tenant"},
    )

    assert response.status_code == 200
    assert len(stripe_calls) == 1
    assert "tenant_id" not in stripe_calls[0]["metadata"]
    assert "attacker-selected-tenant" not in str(stripe_calls[0])
    assert "body-selected-tenant" not in str(stripe_calls[0])


@pytest.mark.parametrize(
    ("detail", "status_code"),
    [
        ("Invalid API key", 401),
        ("Expired API key", 401),
        ("Revoked API key", 401),
        ("Workload credentials are not accepted by tenant APIs", 403),
    ],
)
def test_presented_rejected_credential_never_downgrades_to_anonymous(
    checkout_client,
    monkeypatch: pytest.MonkeyPatch,
    detail: str,
    status_code: int,
) -> None:
    client, stripe_calls = checkout_client

    async def _reject(request, x_regengine_api_key):
        del request, x_regengine_api_key
        raise HTTPException(status_code=status_code, detail=detail)

    monkeypatch.setattr(authz, "optional_api_key", _reject)

    response = client.post(
        "/api/v1/billing/checkout",
        headers={"X-RegEngine-API-Key": "present-but-rejected"},
        json={"plan_id": "growth"},
    )

    assert response.status_code == status_code
    assert response.json()["detail"] == detail
    assert stripe_calls == []


def test_empty_presented_credential_is_rejected_not_treated_as_absent(checkout_client) -> None:
    client, stripe_calls = checkout_client

    response = client.post(
        "/api/v1/billing/checkout",
        headers={"X-RegEngine-API-Key": ""},
        json={"plan_id": "growth"},
    )

    assert response.status_code == 401
    assert stripe_calls == []


@pytest.mark.parametrize("retired_value", ["wrong", "former-production-value"])
def test_retired_admin_credential_is_rejected_on_public_checkout(checkout_client, retired_value: str) -> None:
    client, stripe_calls = checkout_client

    response = client.post(
        "/api/v1/billing/checkout",
        headers={"X-Admin-Key": retired_value},
        json={"plan_id": "growth"},
    )

    assert response.status_code == 401
    assert "X-Admin-Key" in response.json()["detail"]
    assert stripe_calls == []


def test_credential_tenant_mismatch_is_403_and_never_calls_stripe(
    checkout_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, stripe_calls = checkout_client

    async def _accept(request, x_regengine_api_key):
        del request, x_regengine_api_key
        return SimpleNamespace(key_id="tenant-key", scopes=["billing.write"], tenant_id="tenant-a")

    monkeypatch.setattr(authz, "optional_api_key", _accept)

    response = client.post(
        "/api/v1/billing/checkout",
        headers={
            "X-RegEngine-API-Key": "valid-tenant-a-key",
            "X-Tenant-ID": "tenant-b",
        },
        json={"plan_id": "growth"},
    )

    assert response.status_code == 403
    assert "tenant" in response.json()["detail"].lower()
    assert stripe_calls == []


def test_valid_credential_binds_checkout_metadata_to_credential_tenant(
    checkout_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, stripe_calls = checkout_client

    async def _accept(request, x_regengine_api_key):
        del request, x_regengine_api_key
        return SimpleNamespace(key_id="tenant-key", scopes=["billing.write"], tenant_id="tenant-a")

    monkeypatch.setattr(authz, "optional_api_key", _accept)

    response = client.post(
        "/api/v1/billing/checkout",
        headers={
            "X-RegEngine-API-Key": "valid-tenant-a-key",
            "X-Tenant-ID": "tenant-a",
        },
        json={"plan_id": "growth", "tenant_id": "tenant-b"},
    )

    assert response.status_code == 200
    assert stripe_calls[0]["metadata"]["tenant_id"] == "tenant-a"
    assert stripe_calls[0]["metadata"]["issued_by_key_id"] == "tenant-key"
    assert "tenant-b" not in str(stripe_calls[0])


def test_checkout_request_budget_is_enforced_before_second_stripe_call(
    checkout_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, stripe_calls = checkout_client
    limiter = BruteForceLimiter(
        namespace="test-checkout-one-request",
        max_failures=1,
        window_seconds=60,
        redis_client=None,
    )
    limiter._redis = None
    monkeypatch.setattr(rate_limiting_mod, "_checkout_limiter", limiter)

    assert client.post("/api/v1/billing/checkout", json={"plan_id": "growth"}).status_code == 200
    blocked = client.post("/api/v1/billing/checkout", json={"plan_id": "growth"})

    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "60"
    assert len(stripe_calls) == 1


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-RegEngine-API-Key": "present-during-outage"},
    ],
)
def test_production_without_shared_limiter_backend_fails_closed_before_stripe(
    checkout_client,
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
) -> None:
    client, stripe_calls = checkout_client
    monkeypatch.setenv("REGENGINE_ENV", "production")
    for name in ("REGENGINE_REDIS_URL", "REDIS_URL", "UPSTASH_REDIS_REST_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(rate_limiting_mod, "_checkout_limiter", None)

    response = client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plan_id": "growth"},
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    assert stripe_calls == []


def test_cloud_marker_forces_shared_limiter_even_if_environment_says_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "preview")

    assert rate_limiting_mod._checkout_requires_shared_backend() is True


def test_checkout_openapi_exposes_only_optional_supported_headers() -> None:
    app = FastAPI()
    app.include_router(routes_mod.router)

    operation = app.openapi()["paths"]["/api/v1/billing/checkout"]["post"]
    headers = {
        parameter["name"].lower(): parameter
        for parameter in operation.get("parameters", [])
        if parameter["in"] == "header"
    }

    assert headers["x-regengine-api-key"]["required"] is False
    assert headers["x-tenant-id"]["required"] is False
    assert "x-admin-key" not in headers
    assert "security" not in operation
