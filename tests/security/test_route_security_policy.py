"""Focused unit tests for server.route_security_policy.

These tests use small synthetic APIRoute objects with stubbed auth
dependencies so they run without importing the full application or any
external service. They cover the main public behavior of
``classify_operation`` plus the ``operation_key``/``operation_id`` helpers,
including edge and error cases.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, Header, HTTPException
from fastapi.routing import APIRoute

from server.route_security_policy import (
    RouteManifestError,
    classify_operation,
    operation_id,
    operation_key,
)


def _stub_dependency(module: str, name: str):
    async def _dependency():
        return {"ok": True}

    _dependency.__module__ = module
    _dependency.__name__ = name
    return _dependency


_REQUIRE_API_KEY = "shared.auth:require_api_key"
_REQUIRE_METRICS_KEY = "shared.observability.metrics_auth:require_metrics_key"
_REQUIRE_SYSADMIN = "services.admin.app.privileged_auth:require_sysadmin_high_assurance"
_REQUIRE_PROVISIONER = "services.admin.app.privileged_auth:require_tenant_provisioner_key"
_SCOPED_SESSION = "services.admin.app.auth.session_auth:get_scoped_active_session_context"


def _make_route(path: str, method: str = "GET", dependencies=(), endpoint=None) -> APIRoute:
    async def _default_endpoint():
        return {"ok": True}

    return APIRoute(
        path=path,
        endpoint=endpoint or _default_endpoint,
        methods=[method],
        dependencies=list(dependencies),
    )


def _tenant_api_key_route(path: str, *, owner: str = "csv", method: str = "GET") -> APIRoute:
    module, _, name = _REQUIRE_API_KEY.partition(":")
    return _make_route(path, method=method, dependencies=[Depends(_stub_dependency(module, name))])


# Module-level endpoints whose source the adapters inspect. They are never
# called, only parsed with inspect.getsource / ast.


async def _redis_job_owner_endpoint(r, job_id, api_key):
    if not _job_owned_by_tenant(r, job_id, api_key.tenant_id):
        raise HTTPException(status_code=404)
    return {"ok": True}


def _job_owned_by_tenant(redis_client, resource_id, tenant_id):  # pragma: no cover
    return True


async def _stripe_webhook_endpoint(stripe_signature: str = Header(alias="Stripe-Signature")):
    return _process_stripe_webhook(stripe_signature)


def _process_stripe_webhook(signature):  # pragma: no cover
    return signature


def test_operation_key_uppercases_method():
    assert operation_key("csv", "get", "/api/v1/templates") == ("csv", "GET", "/api/v1/templates")


def test_operation_id_format():
    assert operation_id("csv", "get", "/api/v1/templates") == "csv:GET:/api/v1/templates"


def test_public_health_route_classifies_without_auth():
    route = _make_route("/health", method="GET")

    assert classify_operation(route, owner="health", method="GET") == (
        "public",
        "none",
        (),
        "public-static-or-health:no-tenant-secret",
        "public_no_auth",
    )


def test_public_route_with_auth_dependency_is_rejected():
    module, _, name = _REQUIRE_API_KEY.partition(":")
    route = _make_route(
        "/health",
        method="GET",
        dependencies=[Depends(_stub_dependency(module, name))],
    )

    with pytest.raises(RouteManifestError, match="forbidden dependencies"):
        classify_operation(route, owner="health", method="GET")


def test_tenant_api_key_route_uses_owner_storage_policy():
    route = _tenant_api_key_route("/api/v1/csv-items")

    classification, authentication, _permissions, storage_boundary, adapter = classify_operation(
        route, owner="csv", method="GET"
    )

    assert classification == "tenant-scoped"
    assert authentication == "x-regengine-api-key"
    assert storage_boundary == "postgres-rls:credential-bound-tenant"
    assert adapter == "tenant_api_key_postgres_rls"


def test_exact_operation_policy_overrides_owner_policy():
    _redis_job_owner_endpoint.__module__ = "services.ingestion.app.routes_status"
    module, _, name = _REQUIRE_API_KEY.partition(":")
    route = _make_route(
        "/v1/ingest/status/{job_id}",
        method="GET",
        dependencies=[Depends(_stub_dependency(module, name))],
        endpoint=_redis_job_owner_endpoint,
    )

    _classification, _auth, _perms, storage_boundary, adapter = classify_operation(route, owner="status", method="GET")

    assert storage_boundary == "redis:tenant-owner-key"
    assert adapter == "tenant_api_key_redis_job_owner"


def test_metrics_dependency_classifies_workload_only():
    module, _, name = _REQUIRE_METRICS_KEY.partition(":")
    route = _make_route(
        "/metrics",
        method="GET",
        dependencies=[Depends(_stub_dependency(module, name))],
    )

    classification, authentication, permissions, _storage, adapter = classify_operation(
        route, owner="metrics", method="GET"
    )

    assert classification == "workload-only"
    assert authentication == "x-metrics-key"
    assert "metrics.read" in permissions
    assert adapter == "workload_metrics_key"


def test_sysadmin_dependency_classifies_global_sysadmin():
    module, _, name = _REQUIRE_SYSADMIN.partition(":")
    route = _make_route(
        "/v1/system/jwt/keys",
        method="GET",
        dependencies=[Depends(_stub_dependency(module, name))],
    )

    classification, _auth, permissions, _storage, adapter = classify_operation(route, owner="admin", method="GET")

    assert classification == "global-sysadmin"
    assert "sysadmin" in permissions
    assert adapter == "global_sysadmin_high_assurance"


def test_workload_provisioner_dependency_classifies_workload_only():
    module, _, name = _REQUIRE_PROVISIONER.partition(":")
    route = _make_route(
        "/v1/internal/tenants",
        method="POST",
        dependencies=[Depends(_stub_dependency(module, name))],
    )

    classification, _auth, permissions, _storage, adapter = classify_operation(route, owner="admin", method="POST")

    assert classification == "workload-only"
    assert "internal.tenants.create" in permissions
    assert adapter == "workload_tenant_provisioner"


def test_scoped_session_dependency_classifies_tenant_scoped():
    module, _, name = _SCOPED_SESSION.partition(":")
    route = _make_route(
        "/v1/tenants/me",
        method="GET",
        dependencies=[Depends(_stub_dependency(module, name))],
    )

    classification, authentication, permissions, _storage, adapter = classify_operation(
        route, owner="admin", method="GET"
    )

    assert classification == "tenant-scoped"
    assert authentication == "opaque-session-cookie"
    assert "authenticated" in permissions
    assert adapter == "tenant_opaque_session"


def test_stripe_webhook_classifies_workload_only_with_signature_header():
    _stripe_webhook_endpoint.__module__ = "services.ingestion.app.stripe_billing.webhooks"
    route = _make_route(
        "/api/v1/billing/webhook/stripe",
        method="POST",
        endpoint=_stripe_webhook_endpoint,
    )

    assert classify_operation(route, owner="billing", method="POST") == (
        "workload-only",
        "stripe-signature",
        ("stripe.webhook.deliver",),
        "stripe-event-to-credential-bound-tenant",
        "workload_stripe_signature",
    )


def test_unclassified_route_without_auth_raises_manifest_error():
    route = _make_route("/api/v1/unknown-widgets", method="GET")

    with pytest.raises(RouteManifestError, match="Unclassified production operation"):
        classify_operation(route, owner="csv", method="GET")


def test_missing_tenant_api_key_policy_raises_manifest_error():
    route = _tenant_api_key_route("/api/v1/discovery/items", owner="discovery")

    with pytest.raises(RouteManifestError, match="No explicit tenant API-key storage/test policy"):
        classify_operation(route, owner="discovery", method="GET")


def test_stripe_webhook_without_signature_header_is_rejected():
    async def _headerless_webhook():
        return _process_stripe_webhook(None)

    _headerless_webhook.__module__ = "services.ingestion.app.stripe_billing.webhooks"
    route = _make_route(
        "/api/v1/billing/webhook/stripe",
        method="POST",
        endpoint=_headerless_webhook,
    )

    with pytest.raises(RouteManifestError, match="does not declare the Stripe-Signature header"):
        classify_operation(route, owner="billing", method="POST")
