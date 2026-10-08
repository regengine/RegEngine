"""Tenant isolation and auth matrix for routes that touch tenant data.

Enumerates every tenant-scoped production operation from the route security
manifest (``docs/security/route-security-manifest.json``) and proves, through
the real production route table in process:

1. Missing API key: every tenant-scoped API-key route refuses (401/403).
2. Wrong API key: every tenant-scoped API-key route refuses (401/403).
3. Cross-tenant path: for each tenant-scoped API-key route whose path names a
   tenant (``{tenant_id}``), a credential bound to tenant A requesting tenant
   B's path is refused (400/401/403/404/409/422) or served scoped data that
   never contains tenant B. A 200 that echoes tenant B fails the suite.
4. Cross-tenant query/header claim: handler-level tenant resolution
   (``services/ingestion/app/tenant_validation.py:resolve_tenant``) refuses a
   conflicting explicit tenant with 403 and never serves the other tenant.

Hermetic by design: no database is required. Routes that need Postgres or
Stripe return their usual unavailable fallbacks for the owning tenant, while
the tenant boundary itself is enforced before any handler runs, so the
cross-tenant probes stay deterministic with or without backing services.

Existing style follows tests/security/test_auth_coverage.py (production route
table built once, strict staging auth semantics for the anonymous probes, per
request rate limiter resets so one denial cannot mask the next).
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

TENANT_A = "11111111-1111-4111-8111-111111111111"
TENANT_B = "22222222-2222-4222-8222-222222222222"

BYPASS_TOKEN = "tenant-matrix-bypass-token"

# Refusals that prove no cross-tenant data was served. 404 is included on
# purpose: the legacy billing portal route answers 404 on tenant mismatch to
# avoid a tenant-existence oracle. 422 is included because body validation
# runs after auth on some write routes.
REFUSED_STATUSES = frozenset({400, 401, 403, 404, 409, 422})

_ENV_KEYS = (
    "ADMIN_FALLBACK_SQLITE",
    "API_KEY",
    "AUTH_SECRET_KEY",
    "AUTH_TEST_BYPASS_TOKEN",
    "AUTH_TEST_BYPASS_TENANT_ID",
    "ENV",
    "METRICS_API_KEY",
    "REDIS_URL",
    "REGENGINE_API_KEY",
    "REGENGINE_ENV",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
)


def _save_env() -> dict[str, str | None]:
    return {key: os.environ.get(key) for key in _ENV_KEYS}


def _restore_env(saved: dict[str, str | None]) -> None:
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    for module_name in ("app.config", "services.ingestion.app.config"):
        module = sys.modules.get(module_name)
        get_settings = getattr(module, "get_settings", None)
        cache_clear = getattr(get_settings, "cache_clear", None)
        if cache_clear is not None:
            cache_clear()


def _build_production_app() -> tuple[FastAPI, dict]:
    """Mount the exact production route table and its security manifest."""
    from server.main import app as inventory_app
    from server.route_ownership import route_owner
    from server.route_security_manifest import PRODUCTION_OWNERS, build_route_security_manifest

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.router.routes.extend(
        route
        for route in inventory_app.routes
        if isinstance(route, APIRoute) and route_owner(route) in PRODUCTION_OWNERS
    )
    manifest = build_route_security_manifest(inventory_app)
    return app, manifest


def _concrete_path(path_template: str) -> str:
    from server.route_security_manifest import _concrete_probe_path

    return _concrete_probe_path(path_template)


@pytest.fixture(scope="module")
def matrix_client():
    """Production route table with strict auth, restored after the module."""
    saved = _save_env()
    prev_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "main" or name == "app" or name.startswith("app.")
    }
    prev_sys_path = list(sys.path)
    os.environ.pop("API_KEY", None)
    os.environ.pop("REGENGINE_API_KEY", None)
    os.environ["REGENGINE_ENV"] = "test"
    os.environ["ENV"] = "test"
    os.environ["ADMIN_FALLBACK_SQLITE"] = "sqlite:///:memory:"
    os.environ.setdefault("AUTH_SECRET_KEY", "tenant-matrix-signing-material")
    os.environ.setdefault("METRICS_API_KEY", "tenant-matrix-metrics")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_tenant_matrix")
    os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_tenant_matrix")
    os.environ.pop("AUTH_TEST_BYPASS_TOKEN", None)
    os.environ.pop("AUTH_TEST_BYPASS_TENANT_ID", None)
    try:
        app, manifest = _build_production_app()
        os.environ["REGENGINE_ENV"] = "staging"
        os.environ["ENV"] = "staging"
        client = TestClient(app, raise_server_exceptions=False)
    except Exception as exc:
        _restore_env(saved)
        pytest.fail(f"Cannot build production app for tenant isolation matrix: {exc}")
    try:
        yield client, manifest
    finally:
        _restore_env(saved)
        sys.path[:] = prev_sys_path
        for name in list(sys.modules):
            if name == "main" or name == "app" or name.startswith("app."):
                sys.modules.pop(name, None)
        sys.modules.update(prev_modules)


def _tenant_api_key_operations(manifest: dict) -> list[dict]:
    return [
        operation
        for operation in manifest["enabled_operations"]
        if operation["classification"] == "tenant-scoped" and operation["authentication"] == "x-regengine-api-key"
    ]


def _reset_probe_limiter() -> None:
    from services.ingestion.app import authz

    authz._get_auth_limiter().reset("testclient")


def _write_kwargs(method: str) -> dict:
    return {"json": {}} if method in {"POST", "PUT", "PATCH", "DELETE"} else {}


def test_tenant_scoped_routes_refuse_missing_api_key(matrix_client):
    """Every tenant-data route answers 401/403 with no credential at all."""
    client, manifest = matrix_client
    os.environ["REGENGINE_ENV"] = "staging"
    os.environ["ENV"] = "staging"
    os.environ.pop("AUTH_TEST_BYPASS_TOKEN", None)

    failures = []
    for operation in _tenant_api_key_operations(manifest):
        _reset_probe_limiter()
        response = client.request(
            operation["method"],
            _concrete_path(operation["path"]),
            **_write_kwargs(operation["method"]),
        )
        if response.status_code not in (401, 403):
            failures.append(f"{operation['operation']} -> {response.status_code}")
    assert not failures, "Tenant-scoped routes reachable without an API key:\n" + "\n".join(f"  {f}" for f in failures)


def test_tenant_scoped_routes_refuse_wrong_api_key(matrix_client):
    """Every tenant-data route answers 401/403 for an unknown API key."""
    client, manifest = matrix_client
    os.environ["REGENGINE_ENV"] = "staging"
    os.environ["ENV"] = "staging"
    os.environ.pop("AUTH_TEST_BYPASS_TOKEN", None)

    failures = []
    for operation in _tenant_api_key_operations(manifest):
        _reset_probe_limiter()
        response = client.request(
            operation["method"],
            _concrete_path(operation["path"]),
            headers={"X-RegEngine-API-Key": "rge_unknown_key_matrix_probe"},
            **_write_kwargs(operation["method"]),
        )
        if response.status_code not in (401, 403):
            failures.append(f"{operation['operation']} -> {response.status_code}")
    assert not failures, "Tenant-scoped routes reachable with a wrong API key:\n" + "\n".join(
        f"  {f}" for f in failures
    )


def _tenant_path_variants(path_template: str) -> tuple[str, str]:
    """Render the path template for tenant A (own) and tenant B (other)."""
    own = path_template.replace("{tenant_id}", TENANT_A)
    other = path_template.replace("{tenant_id}", TENANT_B)
    return _concrete_path(own), _concrete_path(other)


def test_tenant_path_mismatch_never_serves_other_tenant(matrix_client, monkeypatch):
    """A tenant A credential requesting tenant B's path is refused or scoped.

    Refused means any of 400/401/403/404/409/422. Scoped means 200 whose body
    never mentions tenant B. Anything else (including a 200 echoing tenant B,
    or a 5xx that skipped the tenant check) fails.
    """
    client, manifest = matrix_client
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("AUTH_TEST_BYPASS_TOKEN", BYPASS_TOKEN)
    monkeypatch.setenv("AUTH_TEST_BYPASS_TENANT_ID", TENANT_A)
    headers = {"X-RegEngine-API-Key": BYPASS_TOKEN}

    path_operations = [o for o in _tenant_api_key_operations(manifest) if "{tenant_id}" in o["path"]]
    assert path_operations, "Expected tenant-scoped API-key routes with a {tenant_id} path parameter"

    failures = []
    for operation in path_operations:
        own_path, other_path = _tenant_path_variants(operation["path"])
        kwargs = _write_kwargs(operation["method"])

        _reset_probe_limiter()
        own = client.request(operation["method"], own_path, headers=headers, **kwargs)
        _reset_probe_limiter()
        cross = client.request(operation["method"], other_path, headers=headers, **kwargs)

        if own.status_code == 409:
            failures.append(f"{operation['operation']}: own-tenant request refused with 409")
            continue
        if cross.status_code in REFUSED_STATUSES:
            if TENANT_B in cross.text:
                failures.append(
                    f"{operation['operation']}: cross-tenant refusal leaks tenant B (status {cross.status_code})"
                )
            if cross.status_code == 409:
                try:
                    code = cross.json().get("detail", {}).get("code")
                except Exception:
                    code = None
                if code != "E_TENANT_MISMATCH":
                    failures.append(f"{operation['operation']}: 409 without E_TENANT_MISMATCH (got {code!r})")
        elif cross.status_code == 200 and TENANT_B not in cross.text:
            continue
        else:
            failures.append(
                f"{operation['operation']}: cross-tenant request not refused "
                f"(status {cross.status_code}, body has tenant B: {TENANT_B in cross.text})"
            )
    assert not failures, "Cross-tenant path isolation failures:\n" + "\n".join(f"  {f}" for f in failures)


def _bypass_headers() -> dict[str, str]:
    return {"X-RegEngine-API-Key": BYPASS_TOKEN}


def _use_bypass_tenant_a(monkeypatch) -> None:
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("AUTH_TEST_BYPASS_TOKEN", BYPASS_TOKEN)
    monkeypatch.setenv("AUTH_TEST_BYPASS_TENANT_ID", TENANT_A)


def test_explicit_query_tenant_mismatch_is_refused(matrix_client, monkeypatch):
    """A ?tenant_id claim for another tenant is refused with E_TENANT_MISMATCH."""
    client, _ = matrix_client
    _use_bypass_tenant_a(monkeypatch)

    _reset_probe_limiter()
    match = client.get(
        f"/api/v1/monitoring/alerts/{TENANT_A}",
        params={"tenant_id": TENANT_A},
        headers=_bypass_headers(),
    )
    assert match.status_code == 200
    assert TENANT_B not in match.text

    _reset_probe_limiter()
    mismatch = client.get(
        f"/api/v1/monitoring/alerts/{TENANT_A}",
        params={"tenant_id": TENANT_B},
        headers=_bypass_headers(),
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "E_TENANT_MISMATCH"
    assert TENANT_B not in mismatch.text


def test_explicit_header_tenant_mismatch_is_refused(matrix_client, monkeypatch):
    """A conflicting X-Tenant-ID header for another tenant is refused."""
    client, _ = matrix_client
    _use_bypass_tenant_a(monkeypatch)

    _reset_probe_limiter()
    match = client.get(
        f"/api/v1/monitoring/alerts/{TENANT_A}",
        headers={**_bypass_headers(), "X-Tenant-ID": TENANT_A},
    )
    assert match.status_code == 200
    assert TENANT_B not in match.text

    _reset_probe_limiter()
    mismatch = client.get(
        f"/api/v1/monitoring/alerts/{TENANT_A}",
        headers={**_bypass_headers(), "X-Tenant-ID": TENANT_B},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "E_TENANT_MISMATCH"
    assert TENANT_B not in mismatch.text
