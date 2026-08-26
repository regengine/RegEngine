"""Release-gate tests for the consolidated route security manifest."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse
from starlette.routing import Route

import server.route_security_manifest as route_security_manifest
from server.route_ownership import excluded_owned_routes, include_owned_router, route_owner
from server.route_security_manifest import (
    PRODUCTION_OWNERS,
    RouteManifestError,
    _effective_route_stub,
    build_route_security_manifest,
    probe_omitted_paths_exact_404,
)
from server.route_security_policy import (
    TENANT_API_KEY_OPERATION_POLICIES,
    TENANT_API_KEY_OWNER_POLICIES,
    TenantApiKeyRoutePolicy,
    classify_operation,
)
from services.shared.route_introspection import EffectiveRoute, iter_effective_routes

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "docs" / "security" / "route-security-manifest.json"


def _find_owned_effective_route(app: FastAPI, *, owner: str, path: str) -> EffectiveRoute:
    matches = [
        effective
        for effective in iter_effective_routes(app)
        if route_owner(effective.route) == owner and effective.path == path
    ]
    assert len(matches) == 1, f"expected one {owner} route at {path}, found {len(matches)}"
    return matches[0]


def test_owned_router_records_the_fully_prefixed_effective_path():
    router = APIRouter(prefix="/inside")

    @router.get("/owned")
    def owned():
        return {"ok": True}

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    include_owned_router(app, router, owner="root", prefix="/outside")

    assert [
        (effective.path, route_owner(effective.route))
        for effective in iter_effective_routes(app)
    ] == [("/outside/inside/owned", "root")]


def test_owned_router_exclusion_preserves_the_service_local_router():
    router = APIRouter(prefix="/inside")

    @router.get("/kept")
    def kept():
        return {"kept": True}

    @router.get("/removed")
    def removed():
        return {"removed": True}

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    include_owned_router(
        app,
        router,
        owner="nlp",
        prefix="/outside",
        excluded_operations={("GET", "/outside/inside/removed")},
    )

    assert [effective.path for effective in iter_effective_routes(app)] == ["/outside/inside/kept"]
    assert [effective.path for effective in iter_effective_routes(router)] == [
        "/inside/kept",
        "/inside/removed",
    ]
    assert [
        (effective.path, route_owner(effective.route))
        for effective in excluded_owned_routes(app)
    ] == [("/outside/inside/removed", "nlp")]


def test_owned_router_allows_an_intentionally_empty_compatibility_router():
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    include_owned_router(app, APIRouter(), owner="admin")

    assert list(iter_effective_routes(app)) == []


def test_manifest_builds_from_an_included_router_wrapper(monkeypatch):
    """A FastAPI 0.141 wrapper must yield the same owned operation as a flat table."""

    router = APIRouter()

    @router.get("/")
    def root():
        return {"ok": True}

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    include_owned_router(app, router, owner="root")

    monkeypatch.setattr(route_security_manifest, "_MINIMUM_INVENTORY_ROUTE_COUNT", 1)
    monkeypatch.setattr(route_security_manifest, "VALID_ROUTER_NAMES", frozenset())
    monkeypatch.setattr(route_security_manifest, "ALL_ROUTE_OWNERS", frozenset({"root"}))
    monkeypatch.setattr(route_security_manifest, "PRODUCTION_OWNERS", frozenset({"root"}))
    monkeypatch.setattr(route_security_manifest, "OMITTED_ROUTER_OWNERS", frozenset())
    monkeypatch.setattr(route_security_manifest, "PRODUCTION_ENABLED_ROUTERS", frozenset())
    monkeypatch.setattr(route_security_manifest, "ALWAYS_MOUNTED_OWNERS", frozenset({"root"}))
    monkeypatch.setattr(
        route_security_manifest,
        "PUBLIC_OPERATIONS",
        frozenset({("root", "GET", "/")}),
    )
    monkeypatch.setattr(route_security_manifest, "STRIPE_WEBHOOK_OPERATIONS", frozenset())
    monkeypatch.setattr(route_security_manifest, "REQUIRED_EXACT_TENANT_API_KEY_POLICIES", frozenset())
    monkeypatch.setattr(route_security_manifest, "TENANT_API_KEY_OPERATION_POLICIES", {})
    monkeypatch.setattr(route_security_manifest, "TENANT_API_KEY_OWNER_POLICIES", {})

    manifest = build_route_security_manifest(app)

    assert manifest["summary"]["enabled_operation_count"] == 1
    assert manifest["enabled_operations"][0]["operation"] == "root:GET:/"


def test_manifest_refuses_a_collapsed_route_inventory():
    router = APIRouter()

    @router.get("/")
    def root():
        return {"ok": True}

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    include_owned_router(app, router, owner="root")

    with pytest.raises(RouteManifestError, match="potentially collapsed route table"):
        build_route_security_manifest(app)


@pytest.fixture(scope="module")
def inventory_app():
    from server.main import app

    return app


@pytest.fixture(scope="module")
def manifest(inventory_app) -> dict:
    return build_route_security_manifest(inventory_app)


@pytest.fixture(scope="module")
def production_route_app(inventory_app) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.router.routes.extend(
        _effective_route_stub(effective)
        for effective in iter_effective_routes(inventory_app)
        if route_owner(effective.route) in PRODUCTION_OWNERS
    )
    return app


def test_checked_in_manifest_matches_live_route_and_dependency_graph(manifest):
    checked_in = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert checked_in == manifest
    assert checked_in["summary"] == {
        "enabled_operation_count": 248,
        "disabled_operation_count": 178,
        "disabled_unique_path_count": 161,
        "enabled_by_classification": {
            "global-sysadmin": 15,
            "public": 31,
            "tenant-scoped": 195,
            "workload-only": 7,
        },
    }


def test_checkout_is_public_only_when_no_credential_is_present(manifest):
    checkout = next(
        item
        for item in manifest["enabled_operations"]
        if item["operation"] == "billing:POST:/api/v1/billing/checkout"
    )

    assert checkout == {
        "operation": "billing:POST:/api/v1/billing/checkout",
        "owner": "billing",
        "method": "POST",
        "path": "/api/v1/billing/checkout",
        "classification": "public",
        "authentication": "optional-x-regengine-api-key",
        "required_permissions": [],
        "storage_boundary": "stripe+redis:anonymous-or-credential-bound-tenant",
        "test_adapter": "public_optional_tenant_checkout",
    }


def test_every_global_system_operation_requires_high_assurance_session(manifest):
    expected = {
        ("GET", "/v1/system/qa-health"),
        ("GET", "/v1/system/task-queue/summary"),
        ("POST", "/v1/system/task-queue/replay"),
        ("POST", "/v1/system/jwt/rotate"),
        ("GET", "/v1/system/jwt/keys"),
        ("POST", "/v1/system/jwt/revoke"),
        ("POST", "/v1/system/jwt/revoke-key"),
        ("POST", "/v1/system/jwt/revoke-all"),
        ("POST", "/v1/system/dlq/replay"),
    }
    operations = {
        (item["method"], item["path"]): item
        for item in manifest["enabled_operations"]
        if item["owner"] == "admin" and (item["method"], item["path"]) in expected
    }

    assert set(operations) == expected
    assert all(item["classification"] == "global-sysadmin" for item in operations.values())
    assert all(item["authentication"] == "opaque-session-cookie:webauthn-or-sso" for item in operations.values())
    assert all(item["test_adapter"] == "global_sysadmin_high_assurance" for item in operations.values())


def test_agent_review_and_partner_status_use_their_exact_privileged_realms(manifest):
    operations = {
        item["operation"]: item
        for item in manifest["enabled_operations"]
        if item["operation"]
        in {
            "admin:GET:/v1/agent-reviews/items",
            "admin:POST:/v1/agent-reviews/items/{artifact_id}/review",
            "admin:GET:/v1/agent-reviews/items/{artifact_id}/timeline",
            "admin:PATCH:/v1/tenants/{tenant_id}/partner-status",
        }
    }

    assert operations["admin:GET:/v1/agent-reviews/items"]["required_permissions"] == ["review.read"]
    assert operations["admin:GET:/v1/agent-reviews/items"]["authentication"] == "opaque-session-cookie"
    assert operations["admin:GET:/v1/agent-reviews/items/{artifact_id}/timeline"]["required_permissions"] == [
        "review.read"
    ]
    decision = operations["admin:POST:/v1/agent-reviews/items/{artifact_id}/review"]
    assert decision["required_permissions"] == ["review.decide"]
    assert decision["authentication"] == "opaque-session-cookie:webauthn-or-sso"
    partner = operations["admin:PATCH:/v1/tenants/{tenant_id}/partner-status"]
    assert partner["classification"] == "global-sysadmin"
    assert partner["authentication"] == "opaque-session-cookie:webauthn-or-sso"


def test_webauthn_enrollment_requires_existing_high_assurance_session(manifest):
    enrollment = {
        (item["method"], item["path"]): item
        for item in manifest["enabled_operations"]
        if item["path"].startswith("/auth/webauthn/register/")
    }

    assert set(enrollment) == {
        ("POST", "/auth/webauthn/register/generate-options"),
        ("POST", "/auth/webauthn/register/verify"),
    }
    assert all(
        item["authentication"] == "opaque-session-cookie:webauthn-or-sso"
        for item in enrollment.values()
    )
    assert all(
        item["test_adapter"] == "tenant_high_assurance_session"
        for item in enrollment.values()
    )


def test_dual_session_routes_record_cookie_tenancy_and_csrf_adapter(manifest):
    dual = [
        item
        for item in manifest["enabled_operations"]
        if item["test_adapter"] == "tenant_dual_session_csrf"
    ]
    mutations = [item for item in dual if item["method"] in {"POST", "PUT", "PATCH", "DELETE"}]

    assert len(dual) == 49
    assert len(mutations) == 22
    assert all(item["authentication"] == "bearer-token-or-opaque-session-cookie" for item in dual)
    assert all(
        item["storage_boundary"] == "admin-postgres:jwt-tenant-or-session-membership-tenant"
        for item in dual
    )


def test_account_erasure_records_exact_identity_global_self_service_contract(manifest):
    erasure = next(
        item
        for item in manifest["enabled_operations"]
        if item["operation"] == "admin:POST:/v1/account/erasure"
    )

    assert erasure == {
        "operation": "admin:POST:/v1/account/erasure",
        "owner": "admin",
        "method": "POST",
        "path": "/v1/account/erasure",
        "classification": "tenant-scoped",
        "authentication": "bearer-token-or-opaque-session-cookie",
        "required_permissions": ["authenticated"],
        "storage_boundary": "admin-postgres+graph-outbox:authenticated-user-global-identity",
        "test_adapter": "tenant_identity_global_self_erasure",
    }


def test_account_erasure_adapter_rejects_non_authenticated_user_target(inventory_app):
    effective = _find_owned_effective_route(
        inventory_app,
        owner="admin",
        path="/v1/account/erasure",
    )
    route = effective.route
    endpoint = route.endpoint

    async def request_erasure(body, current_user):
        user_id = body.user_id
        user_uuid = uuid.UUID(str(user_id))  # noqa: F821
        _apply_account_erasure(None, user_id=user_uuid, tenant_id=None)  # noqa: F821

    request_erasure.__module__ = endpoint.__module__
    route.endpoint = request_erasure
    try:
        with pytest.raises(RouteManifestError, match="must normalize current_user.id"):
            classify_operation(_effective_route_stub(effective), owner="admin", method="POST")
    finally:
        route.endpoint = endpoint


def test_checkout_manifest_adapter_rejects_broad_auth_failure_downgrade(inventory_app):
    effective = _find_owned_effective_route(
        inventory_app,
        owner="billing",
        path="/api/v1/billing/checkout",
    )
    route = effective.route
    endpoint = route.endpoint

    async def unsafe_checkout_handler():
        safe_principal = None
        if safe_principal is not None:
            try:
                object()._resolve_tenant_context()  # type: ignore[attr-defined]
            except Exception:
                pass

    route.endpoint = unsafe_checkout_handler
    try:
        with pytest.raises(RouteManifestError, match="could downgrade a rejected credential"):
            classify_operation(_effective_route_stub(effective), owner="billing", method="POST")
    finally:
        route.endpoint = endpoint


def test_every_omitted_router_path_returns_exact_404(production_route_app, manifest):
    assert probe_omitted_paths_exact_404(production_route_app, manifest) == 178


def test_http_routes_that_write_the_legacy_fsma_audit_chain_are_graph_omitted(manifest):
    writer_capable_operations = {
        "graph:GET:/api/v1/fsma/traceability/search/events",
        "graph:GET:/api/v1/fsma/traceability/timeline/{tlc}",
        "graph:GET:/api/v1/fsma/traceability/trace/backward/{tlc}",
        "graph:GET:/api/v1/fsma/traceability/trace/forward/{tlc}",
        "graph:GET:/api/v1/lineage/lineage/{tlc}/history",
    }
    disabled = {
        item["operation"]: item
        for item in manifest["disabled_operations"]
        if item["operation"] in writer_capable_operations
    }

    assert set(disabled) == writer_capable_operations
    assert all(item["owner"] == "graph" for item in disabled.values())
    assert all(item["inventory_source"] == "development-route-table" for item in disabled.values())


def test_representative_auth_negative_contracts_are_not_vacuous(production_route_app):
    with TestClient(production_route_app) as client:
        tenant = client.get("/v1/ingest/status/00000000-0000-4000-8000-000000000000")
        metrics = client.get("/metrics")
        workload = client.post("/v1/internal/tenants", json={"name": "manifest-negative-probe"})
        public = client.get("/")
        graph = client.post("/api/v1/query/traceability", json={})
        overlay = client.get("/v1/overlay/controls")
        nlp = client.post("/api/v1/analyze", json={})
        sandbox = client.post("/api/v1/sandbox/evaluate", json={})

    assert tenant.status_code == 401
    assert metrics.status_code == 403
    assert workload.status_code == 401
    assert public.status_code == 200
    assert graph.status_code == 404
    assert overlay.status_code == 404
    assert nlp.status_code == 404
    assert sandbox.status_code == 404


def test_unowned_operation_fails_manifest_generation(inventory_app):
    rogue = APIRoute(
        path="/rogue-security-surface",
        endpoint=lambda: {"ok": False},
        methods=["GET"],
    )
    inventory_app.routes.append(rogue)
    try:
        with pytest.raises(RouteManifestError, match="bypassed ownership registration"):
            build_route_security_manifest(inventory_app)
    finally:
        inventory_app.routes.remove(rogue)


def test_non_api_route_cannot_bypass_manifest_classification(inventory_app):
    async def rogue_endpoint(_request):
        return JSONResponse({"ok": False})

    rogue = Route("/rogue-starlette-surface", rogue_endpoint, methods=["GET"])
    inventory_app.routes.append(rogue)
    try:
        with pytest.raises(RouteManifestError, match="bypassed APIRoute ownership/classification"):
            build_route_security_manifest(inventory_app)
    finally:
        inventory_app.routes.remove(rogue)


def test_duplicate_method_path_ownership_fails_manifest_generation(inventory_app):
    duplicate_router = APIRouter()

    @duplicate_router.get("/")
    def duplicate_root():
        return {"ok": False}

    original_count = len(inventory_app.routes)
    include_owned_router(inventory_app, duplicate_router, owner="root")
    try:
        with pytest.raises(RouteManifestError, match="Duplicate method/path ownership"):
            build_route_security_manifest(inventory_app)
    finally:
        del inventory_app.routes[original_count:]


def test_removing_tenant_auth_dependency_fails_classification(inventory_app):
    effective = _find_owned_effective_route(
        inventory_app,
        owner="status",
        path="/v1/ingest/status/{job_id}",
    )
    route = effective.route
    dependencies = route.dependant.dependencies
    route.dependant.dependencies = []
    try:
        with pytest.raises(RouteManifestError, match="Unclassified production operation"):
            build_route_security_manifest(inventory_app)
    finally:
        route.dependant.dependencies = dependencies


def test_tenant_api_key_storage_contracts_are_explicit_and_storage_accurate(manifest):
    tenant_api_key_operations = {
        (item["owner"], item["method"], item["path"]): item
        for item in manifest["enabled_operations"]
        if item["classification"] == "tenant-scoped" and item["authentication"].startswith("x-regengine-api-key")
    }

    redis_paths = {
        "/v1/ingest/status/{job_id}",
        "/v1/ingest/documents/{document_id}/analysis",
    }
    for path in redis_paths:
        operation = tenant_api_key_operations[("status", "GET", path)]
        assert operation["storage_boundary"] == "redis:tenant-owner-key"
        assert operation["test_adapter"] == "tenant_api_key_redis_job_owner"

    status_postgres = tenant_api_key_operations[("status", "GET", "/v1/audit/jobs/{job_id}")]
    assert status_postgres["storage_boundary"] == "ingestion-postgres:explicit-tenant-filter"
    assert status_postgres["test_adapter"] == "tenant_api_key_ingestion_postgres_filter"
    assert all(item["test_adapter"] != "tenant_api_key" for item in tenant_api_key_operations.values())


def test_redis_storage_adapter_rejects_removed_owner_check(inventory_app):
    effective = _find_owned_effective_route(
        inventory_app,
        owner="status",
        path="/v1/ingest/status/{job_id}",
    )
    route = effective.route
    endpoint = route.endpoint

    async def unguarded_status_handler():
        return {"status": "unsafe"}

    unguarded_status_handler.__module__ = endpoint.__module__
    route.endpoint = unguarded_status_handler
    try:
        with pytest.raises(RouteManifestError, match="no longer denies a failed credential-bound owner check"):
            classify_operation(_effective_route_stub(effective), owner="status", method="GET")
    finally:
        route.endpoint = endpoint


def test_redis_storage_adapter_rejects_ignored_owner_check(inventory_app):
    effective = _find_owned_effective_route(
        inventory_app,
        owner="status",
        path="/v1/ingest/status/{job_id}",
    )
    route = effective.route
    endpoint = route.endpoint

    async def ignored_owner_result(job_id, api_key):
        _job_owned_by_tenant(None, job_id, api_key.tenant_id)  # noqa: F821
        return {"status": "unsafe"}

    ignored_owner_result.__module__ = endpoint.__module__
    route.endpoint = ignored_owner_result
    try:
        with pytest.raises(RouteManifestError, match="no longer denies a failed credential-bound owner check"):
            classify_operation(_effective_route_stub(effective), owner="status", method="GET")
    finally:
        route.endpoint = endpoint


@pytest.mark.parametrize(
    "required_key",
    [
        ("status", "GET", "/v1/ingest/status/{job_id}"),
        ("status", "GET", "/v1/ingest/documents/{document_id}/analysis"),
    ],
)
def test_required_exact_redis_policy_cannot_fall_back_to_owner(inventory_app, monkeypatch, required_key):
    monkeypatch.delitem(TENANT_API_KEY_OPERATION_POLICIES, required_key)

    with pytest.raises(RouteManifestError, match="Required exact tenant API-key policy is missing"):
        build_route_security_manifest(inventory_app)


def test_promoting_discovery_requires_explicit_storage_and_adapter_policy(inventory_app, monkeypatch):
    monkeypatch.setattr(
        route_security_manifest,
        "PRODUCTION_OWNERS",
        route_security_manifest.PRODUCTION_OWNERS | {"discovery"},
    )
    monkeypatch.setattr(
        route_security_manifest,
        "OMITTED_ROUTER_OWNERS",
        route_security_manifest.OMITTED_ROUTER_OWNERS - {"discovery"},
    )

    with pytest.raises(RouteManifestError, match="No explicit tenant API-key storage/test policy for discovery"):
        build_route_security_manifest(inventory_app)


def test_orphaned_tenant_owner_policy_fails_manifest_generation(inventory_app, monkeypatch):
    monkeypatch.setitem(
        TENANT_API_KEY_OWNER_POLICIES,
        "discovery",
        TenantApiKeyRoutePolicy(
            "redis:unreviewed-discovery-queue",
            "tenant_api_key_mixed_storage",
        ),
    )

    with pytest.raises(RouteManifestError, match="Explicit tenant API-key policies are orphaned"):
        build_route_security_manifest(inventory_app)


def test_readiness_compatibility_operations_share_readiness_owner(manifest):
    owners = {
        item["path"]: item["owner"]
        for item in manifest["enabled_operations"]
        if item["path"] in {"/api/v1/fsma/export-jobs", "/api/v1/fsma/mappings"}
    }

    assert owners == {
        "/api/v1/fsma/export-jobs": "readiness",
        "/api/v1/fsma/mappings": "readiness",
    }


def test_disabling_readiness_removes_compatibility_routes():
    script = """
import json
from server.main import app
from services.shared.route_introspection import iter_effective_routes

paths = sorted(
    path
    for path, _route in iter_effective_routes(app)
    if path in {"/api/v1/fsma/export-jobs", "/api/v1/fsma/mappings"}
)
print("READINESS_COMPAT_RESULT=" + json.dumps(paths))
"""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("RAILWAY_")
        and key not in {"ADMIN_DATABASE_URL", "DATABASE_URL", "ENABLED_ROUTERS", "ENABLE_EXPERIMENTAL_ROUTERS"}
    }
    env.update(
        {
            "ADMIN_FALLBACK_SQLITE": "sqlite:///:memory:",
            "AUTH_SECRET_KEY": "route-manifest-readiness-test-secret",  # pragma: allowlist secret
            "DISABLED_ROUTERS": "readiness",
            "ENV": "test",
            "METRICS_API_KEY": "route-manifest-readiness-metrics",  # pragma: allowlist secret
            "RATE_LIMIT_FAIL_MODE": "closed",
            "REGENGINE_ENV": "test",
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    marker = "READINESS_COMPAT_RESULT="
    paths = next(
        json.loads(line.removeprefix(marker)) for line in result.stdout.splitlines() if line.startswith(marker)
    )
    assert paths == []
