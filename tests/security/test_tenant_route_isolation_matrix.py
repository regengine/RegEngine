"""Tenant isolation and auth matrix for routes that touch tenant data.

Enumerates every tenant-scoped production operation from the route security
manifest (``docs/security/route-security-manifest.json``) and proves, through
the real production route table in process:

1. Missing API key: every tenant-scoped API-key route refuses (401/403).
2. Wrong API key: every tenant-scoped API-key route refuses (401/403).
3. Cross-tenant path: for each tenant-scoped API-key route whose path names a
   tenant (``{tenant_id}``), a real tenant-A key requesting tenant B's path
   gets that route's mismatch denial (409 ``E_TENANT_MISMATCH``, the billing
   403 tenant-mismatch detail, or the legacy portal 404). The own-tenant
   call must authenticate (anything but 401/403); a 200, 422, or 5xx on the
   cross-tenant path fails, because those prove the tenant check never ran
   (a permission 403 or validation 422 before the check, or scoped data
   served without echoing tenant B).
4. Cross-tenant claims: every tenant-scoped API-key operation is probed with
   a conflicting ``?tenant_id``, ``X-Tenant-ID``, and (for writes) JSON or
   multipart form ``tenant_id`` for tenant B. Routes that evaluate claims
   must deny with a mismatch code; probes for routes that never evaluate
   the claim are pinned per channel in ``CLAIM_UNENFORCED_PROBES`` so a
   change in either direction fails loudly.
5. Cross-tenant query/header claim on one monitoring route: handler-level
   tenant resolution (``services/shared/tenant_context.py``
   ``resolve_tenant_context``, surfaced through ``require_tenant_context``)
   refuses a conflicting explicit tenant with 409 ``E_TENANT_MISMATCH``.

Scope: API-key routes only. The manifest also lists tenant-scoped session
and Bearer [REDACTED] (about 63 operations); those need a separate session matrix
and are not covered here.

Hermetic by design: no database is required, and the fixture forces
synthetic Stripe and Redis settings so own-tenant probes can never touch
real backends when a developer shell exports real keys. Process-global
side effects of own-tenant probes (``stripe.api_key``,
``_onboarding_store``) are restored in teardown.

Existing style follows tests/security/test_auth_coverage.py (production route
table built once, strict staging auth semantics for the anonymous probes, per
request rate limiter resets so one denial cannot mask the next).
"""

from __future__ import annotations

import importlib
import os
import sys
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

TENANT_A = "11111111-1111-4111-8111-111111111111"
TENANT_B = "22222222-2222-4222-8222-222222222222"

BYPASS_TOKEN = "tenant-matrix-bypass-token"

# Statuses that prove the credential itself was rejected. An own-tenant call
# with either status means the tenant check never ran, so the pair proves
# nothing and must fail instead of passing silently.
UNAUTHENTICATED_STATUSES = frozenset({401, 403})

# Detail strings of the mismatch denials. 409 E_TENANT_MISMATCH comes from
# shared.tenant_context.assert_tenant_claim_matches; the 403 text comes from
# ingestion require_permission / resolve_principal_tenant_id; the 404 text is
# the legacy billing portal's deliberate mismatch answer (it returns 404 to
# avoid a tenant-existence oracle).
MISMATCH_403_DETAIL = "Tenant mismatch: your API key does not have access to this tenant."
PORTAL_LEGACY_OPERATION = "billing:POST:/api/v1/billing/portal/{tenant_id}"
PORTAL_LEGACY_404_DETAIL = "Not found"

# Floor tripwires against silent coverage shrinkage (for example by
# reclassifying tenant-scoped operations out of the manifest). Today the
# manifest holds 136 tenant-scoped API-key operations, 25 with a
# {tenant_id} path parameter. Update these floors deliberately, never to
# make a red suite green.
MIN_API_KEY_OPERATIONS = 100
MIN_PATH_OPERATIONS = 20

# (operation, channel) probes whose handlers never evaluate a conflicting
# tenant claim sent via query string, header, or JSON body: the probe is
# answered by body validation, a row lookup, an unavailable-backend
# fallback, or served principal-scoped data that never mentions tenant B
# (the two catalog reads and the billing opt-out below). Pins are per
# channel because several routes enforce query/header claims while
# ignoring the JSON body claim. Membership here is a reviewed statement
# that the probe was observed not to enforce claims; if a listed probe
# starts denying with a mismatch code, or an unlisted probe stops denying,
# the suite fails so the pin gets updated. A 2xx from a listed probe still
# fails when its body mentions tenant B.
CLAIM_UNENFORCED_PROBES = frozenset(
    {
        ("billing:DELETE:/api/v1/billing/usage/opt-in", "body"),
        ("billing:POST:/api/v1/billing/portal", "header"),
        ("billing:POST:/api/v1/billing/portal", "query"),
        ("billing:POST:/api/v1/billing/portal/{tenant_id}", "body"),
        ("billing:POST:/api/v1/billing/portal/{tenant_id}", "query"),
        ("billing:POST:/api/v1/billing/usage/opt-in", "body"),
        ("billing:POST:/api/v1/billing/usage/report", "body"),
        ("core_ingest:POST:/api/v1/regulatory/ingest/url", "body"),
        ("core_ingest:POST:/api/v1/regulatory/ingest/url", "header"),
        ("core_ingest:POST:/api/v1/regulatory/ingest/url", "query"),
        ("core_ingest:POST:/api/v1/regulatory/v1/ingest", "body"),
        ("core_ingest:POST:/api/v1/regulatory/v1/ingest", "header"),
        ("core_ingest:POST:/api/v1/regulatory/v1/ingest", "query"),
        ("core_ingest:POST:/api/v1/regulatory/v1/ingest/file", "body"),
        ("core_ingest:POST:/api/v1/regulatory/v1/ingest/file", "header"),
        ("core_ingest:POST:/api/v1/regulatory/v1/ingest/file", "query"),
        ("core_ingest:POST:/api/v1/regulatory/v1/ingest/regulation", "body"),
        ("core_ingest:POST:/api/v1/regulatory/v1/ingest/regulation", "header"),
        ("core_ingest:POST:/api/v1/regulatory/v1/ingest/regulation", "query"),
        ("core_ingest:POST:/api/v1/regulatory/v1/ingest/url", "body"),
        ("core_ingest:POST:/api/v1/regulatory/v1/ingest/url", "header"),
        ("core_ingest:POST:/api/v1/regulatory/v1/ingest/url", "query"),
        ("core_ingest:POST:/ingest/url", "body"),
        ("core_ingest:POST:/ingest/url", "header"),
        ("core_ingest:POST:/ingest/url", "query"),
        ("core_ingest:POST:/v1/ingest", "body"),
        ("core_ingest:POST:/v1/ingest", "header"),
        ("core_ingest:POST:/v1/ingest", "query"),
        ("core_ingest:POST:/v1/ingest/file", "body"),
        ("core_ingest:POST:/v1/ingest/file", "header"),
        ("core_ingest:POST:/v1/ingest/file", "query"),
        ("core_ingest:POST:/v1/ingest/regulation", "body"),
        ("core_ingest:POST:/v1/ingest/regulation", "header"),
        ("core_ingest:POST:/v1/ingest/regulation", "query"),
        ("core_ingest:POST:/v1/ingest/url", "body"),
        ("core_ingest:POST:/v1/ingest/url", "header"),
        ("core_ingest:POST:/v1/ingest/url", "query"),
        ("csv:POST:/api/v1/ingest/csv", "body"),
        ("edi:POST:/api/v1/ingest/edi", "body"),
        ("edi:POST:/api/v1/ingest/edi/document", "body"),
        ("exceptions:PATCH:/api/v1/exceptions/{case_id}/assign", "body"),
        ("exceptions:PATCH:/api/v1/exceptions/{case_id}/resolve", "body"),
        ("exceptions:PATCH:/api/v1/exceptions/{case_id}/waive", "body"),
        ("exceptions:POST:/api/v1/exceptions", "body"),
        ("exceptions:POST:/api/v1/exceptions/{case_id}/comments", "body"),
        ("fda_export:POST:/api/v1/fda/export/verify", "body"),
        ("fsma_compliance:GET:/checklists", "header"),
        ("fsma_compliance:GET:/checklists", "query"),
        ("fsma_compliance:GET:/checklists/{checklist_id}", "header"),
        ("fsma_compliance:GET:/checklists/{checklist_id}", "query"),
        ("fsma_compliance:GET:/industries", "header"),
        ("fsma_compliance:GET:/industries", "query"),
        ("fsma_compliance:GET:/v1/fsma/audit/spreadsheet", "header"),
        ("fsma_compliance:GET:/v1/fsma/audit/spreadsheet", "query"),
        ("fsma_compliance:POST:/validate", "body"),
        ("fsma_compliance:POST:/validate", "header"),
        ("fsma_compliance:POST:/validate", "query"),
        ("inflow_workbench:PATCH:/api/v1/inflow-workbench/fix-queue/{item_id}", "body"),
        ("inflow_workbench:POST:/api/v1/inflow-workbench/commit-gate", "body"),
        ("inflow_workbench:POST:/api/v1/inflow-workbench/readiness/preview", "body"),
        ("inflow_workbench:POST:/api/v1/inflow-workbench/runs", "body"),
        ("inflow_workbench:POST:/api/v1/inflow-workbench/scenarios", "body"),
        ("portal:PATCH:/api/v1/portal/links/{portal_id}/revoke", "body"),
        ("portal:POST:/api/v1/portal/links", "body"),
        ("request_workflow:PATCH:/api/v1/requests/{request_case_id}/scope", "body"),
        ("request_workflow:POST:/api/v1/requests", "body"),
        ("request_workflow:POST:/api/v1/requests/{request_case_id}/amend", "body"),
        ("request_workflow:POST:/api/v1/requests/{request_case_id}/assemble", "body"),
        ("request_workflow:POST:/api/v1/requests/{request_case_id}/collect", "body"),
        ("request_workflow:POST:/api/v1/requests/{request_case_id}/gap-analysis", "body"),
        ("request_workflow:POST:/api/v1/requests/{request_case_id}/signoff", "body"),
        ("request_workflow:POST:/api/v1/requests/{request_case_id}/submit", "body"),
        ("rules:POST:/api/v1/rules/evaluate", "body"),
        ("rules:POST:/api/v1/rules/evaluate-batch", "body"),
        ("status:GET:/v1/audit/jobs/{job_id}", "header"),
        ("status:GET:/v1/audit/jobs/{job_id}", "query"),
        ("status:GET:/v1/audit/logs/{job_id}", "header"),
        ("status:GET:/v1/audit/logs/{job_id}", "query"),
        ("status:GET:/v1/ingest/documents", "header"),
        ("status:GET:/v1/ingest/documents", "query"),
        ("status:GET:/v1/ingest/documents/{document_id}/analysis", "header"),
        ("status:GET:/v1/ingest/documents/{document_id}/analysis", "query"),
        ("status:GET:/v1/ingest/status/{job_id}", "header"),
        ("status:GET:/v1/ingest/status/{job_id}", "query"),
        ("status:GET:/v1/verify/{document_id}", "header"),
        ("status:GET:/v1/verify/{document_id}", "query"),
        ("webhook:GET:/api/v1/webhooks/chain/verify", "header"),
        ("webhook:GET:/api/v1/webhooks/chain/verify", "query"),
        ("webhook:GET:/api/v1/webhooks/recent", "header"),
        ("webhook:GET:/api/v1/webhooks/recent", "query"),
        ("webhook:POST:/api/v1/webhooks/ingest", "body"),
    }
)

# Probes answered with 429 serve no data, so they pass, but a newly
# rate-limited route must be reviewed rather than silently absorbed. The
# two ingest regulation routes answer 429 intermittently in this harness
# (their endpoint-level limiter fires on some runs and body validation
# answers first on others); both outcomes are pinned.
KNOWN_RATE_LIMITED_OPERATIONS = frozenset(
    {
        "core_ingest:POST:/api/v1/regulatory/v1/ingest/regulation",
        "core_ingest:POST:/v1/ingest/regulation",
    }
)

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
    "REGENGINE_REDIS_URL",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "WEBHOOK_HMAC_SECRET",
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


def _restore_module_state(prev_modules: dict, prev_sys_path: list[str]) -> None:
    sys.path[:] = prev_sys_path
    for name in list(sys.modules):
        if name == "main" or name == "app" or name.startswith("app."):
            sys.modules.pop(name, None)
    sys.modules.update(prev_modules)


def _snapshot_probe_globals() -> dict:
    """Snapshot process globals that own-tenant probes legitimately touch."""
    snapshot: dict = {}
    try:
        import stripe

        snapshot["stripe_api_key"] = stripe.api_key
    except ImportError:
        snapshot["stripe_api_key"] = None
    try:
        from services.ingestion.app import onboarding as onboarding_mod

        store = onboarding_mod._onboarding_store
        snapshot["onboarding"] = {t: store[t] for t in (TENANT_A, TENANT_B) if t in store}
        snapshot["onboarding_module"] = onboarding_mod
    except ImportError:
        snapshot["onboarding"] = None
        snapshot["onboarding_module"] = None
    return snapshot


def _restore_probe_globals(snapshot: dict) -> None:
    try:
        import stripe

        stripe.api_key = snapshot.get("stripe_api_key")
    except ImportError:
        pass
    onboarding_mod = snapshot.get("onboarding_module")
    saved_store = snapshot.get("onboarding")
    if onboarding_mod is not None and saved_store is not None:
        lock = getattr(onboarding_mod, "_onboarding_lock", None)
        if lock is not None:
            lock.acquire()
        try:
            store = onboarding_mod._onboarding_store
            for tenant_id in (TENANT_A, TENANT_B):
                store.pop(tenant_id, None)
            store.update(saved_store)
        finally:
            if lock is not None:
                lock.release()


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
    # Forced (not setdefault): own-tenant probes run real handlers, so a
    # developer shell exporting a real Stripe key or Redis URL must never
    # leak into this module. CI leaves these unset, where the behavior is
    # identical to before.
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    os.environ["REGENGINE_REDIS_URL"] = os.environ["REDIS_URL"]
    os.environ.pop("WEBHOOK_HMAC_SECRET", None)
    os.environ["STRIPE_SECRET_KEY"] = "sk_test_tenant_matrix"  # noqa: S105 - synthetic probe key
    os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_tenant_matrix"  # noqa: S105 - synthetic probe secret
    os.environ.pop("AUTH_TEST_BYPASS_TOKEN", None)
    os.environ.pop("AUTH_TEST_BYPASS_TENANT_ID", None)
    try:
        app, manifest = _build_production_app()
        probe_globals = _snapshot_probe_globals()
        os.environ["REGENGINE_ENV"] = "staging"
        os.environ["ENV"] = "staging"
        client = TestClient(app, raise_server_exceptions=False)
    except Exception as exc:
        _restore_env(saved)
        _restore_module_state(prev_modules, prev_sys_path)
        pytest.fail(f"Cannot build production app for tenant isolation matrix: {exc}")
    try:
        yield client, manifest
    finally:
        _restore_probe_globals(probe_globals)
        _restore_env(saved)
        _restore_module_state(prev_modules, prev_sys_path)


def _tenant_api_key_operations(manifest: dict) -> list[dict]:
    # Covers both plain API-key routes and API-key-plus-HMAC routes
    # (e.g. webhook:POST:/api/v1/webhooks/ingest). The HMAC dependency is
    # neutralized (WEBHOOK_HMAC_SECRET unset) in the generic key probes.
    # Signed probes below additionally require the exact key-auth errors.
    operations = [
        operation
        for operation in manifest["enabled_operations"]
        if operation["classification"] == "tenant-scoped"
        and operation["authentication"] in {"x-regengine-api-key", "x-regengine-api-key+hmac-signature"}
    ]
    assert len(operations) >= MIN_API_KEY_OPERATIONS, (
        f"Tenant-scoped API-key operation count fell to {len(operations)}; "
        "routes may have been reclassified out of the matrix. Update "
        "MIN_API_KEY_OPERATIONS deliberately, never to make red green."
    )
    return operations


def _tenant_hmac_operations(manifest: dict) -> list[dict]:
    return [
        operation
        for operation in manifest["enabled_operations"]
        if operation["classification"] == "tenant-scoped"
        and operation["authentication"] == "x-regengine-api-key+hmac-signature"
    ]


# Current manifest inventory of the API-key-plus-HMAC class. Update only
# with security review: a silent disappearance must fail loudly.
EXPECTED_HMAC_OPERATIONS = frozenset({"webhook:POST:/api/v1/webhooks/ingest"})


def test_tenant_hmac_operations_are_exercised(matrix_client):
    """Completeness: every current +HMAC operation is in the probe set."""
    _, manifest = matrix_client
    hmac_ids = {o["operation"] for o in _tenant_hmac_operations(manifest)}
    assert hmac_ids, "Expected at least one tenant-scoped +HMAC operation in the manifest"
    assert hmac_ids == EXPECTED_HMAC_OPERATIONS, (
        "API-key-plus-HMAC inventory changed; review before updating EXPECTED_HMAC_OPERATIONS. "
        f"Missing: {sorted(EXPECTED_HMAC_OPERATIONS - hmac_ids)}, "
        f"new: {sorted(hmac_ids - EXPECTED_HMAC_OPERATIONS)}"
    )
    probed_ids = {o["operation"] for o in _tenant_api_key_operations(manifest)}
    assert hmac_ids <= probed_ids, f"+HMAC operations not exercised by API-key probes: {sorted(hmac_ids - probed_ids)}"


def _webhook_hmac_headers(secret: str, raw_body: bytes) -> dict[str, str]:
    import hashlib
    import hmac as hmac_module

    digest = hmac_module.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return {"X-Webhook-Signature": f"sha256={digest}"}


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
    os.environ.pop("WEBHOOK_HMAC_SECRET", None)

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
    os.environ.pop("WEBHOOK_HMAC_SECRET", None)

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


def test_hmac_routes_refuse_bad_api_key_with_valid_hmac(matrix_client, monkeypatch):
    """With a VALID HMAC, +HMAC routes still refuse missing/wrong API keys.

    Require the canonical key-auth errors, not just any denial: HMAC or
    subscription failures must not mask a missing API-key dependency.
    """
    client, manifest = matrix_client
    monkeypatch.setenv("REGENGINE_ENV", "staging")
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.delenv("AUTH_TEST_BYPASS_TOKEN", raising=False)
    secret = "tenant-matrix-hmac-secret"  # pragma: allowlist secret -- synthetic test signing material
    monkeypatch.setenv("WEBHOOK_HMAC_SECRET", secret)

    hmac_operations = _tenant_hmac_operations(manifest)
    assert hmac_operations, "Expected +HMAC operations to probe with valid HMAC"

    failures = []
    for operation in hmac_operations:
        raw_body = b"{}"
        hmac_headers = _webhook_hmac_headers(secret, raw_body)
        json_headers = {"Content-Type": "application/json"}
        for label, extra, expected_detail in (
            ("missing-key", {}, "Invalid or missing API key"),
            ("wrong-key", {"X-RegEngine-API-Key": "rge_unknown_key_matrix_probe"}, "Invalid API key"),
        ):
            _reset_probe_limiter()
            response = client.request(
                operation["method"],
                _concrete_path(operation["path"]),
                content=raw_body,
                headers={**json_headers, **hmac_headers, **extra},
            )
            if response.status_code != 401:
                failures.append(f"{operation['operation']} [{label}] -> {response.status_code}")
            elif response.json().get("detail") != expected_detail:
                failures.append(
                    f"{operation['operation']} [{label}] did not return the API-key guard error: {response.text[:160]}"
                )
    assert not failures, "API-key guard not proven under valid HMAC:\n" + "\n".join(f"  {f}" for f in failures)


def _live_key_stores() -> list:
    """Return every live in-memory API key store the routes may consult.

    ``shared.auth`` and ``services.shared.auth`` can be distinct module
    objects in this process with distinct store globals, depending on which
    import path each router used. A key created in only one of them is a
    401 in routes bound to the other, which would read as an auth failure
    rather than a store wiring detail. Fail loudly when neither store is
    the expected in-memory implementation.
    """
    stores = []
    for module_name in ("shared.auth", "services.shared.auth"):
        module = sys.modules.get(module_name)
        if module is None:
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                continue
        get_store = getattr(module, "get_key_store", None)
        if get_store is None:
            continue
        store = get_store()
        if type(store).__name__ != "APIKeyStore" or not hasattr(store, "create_key"):
            raise AssertionError(
                f"{module_name} key store is {type(store).__name__}, not the in-memory APIKeyStore; "
                "refusing to probe because every key would 401 for store reasons, not tenant reasons."
            )
        if all(existing is not store for existing in stores):
            stores.append(store)
    assert stores, "No in-memory API key store found for tenant matrix probes"
    return stores


@contextmanager
def _tenant_a_scoped_key():
    """Yield headers for a real tenant-A key with every permission scope.

    Unlike the test bypass (scopes read/write/admin/webhooks.ingest, where
    admin is a plain scope, not a wildcard), ``*`` satisfies every
    ``require_permission`` gate, so probes reach the tenant comparison on
    every route instead of stopping at a permission 403 that would read as
    isolation. The key is disabled again on exit so no fully-scoped
    credential lingers in the process-global stores.
    """
    stores = _live_key_stores()
    raw_key, api_key = stores[0].create_key(
        name="tenant-matrix-scoped-probe",
        tenant_id=TENANT_A,
        rate_limit_per_minute=100000,
        scopes=["*"],
    )
    for other in stores[1:]:
        with other._lock:
            other._keys[api_key.key_id] = api_key
    try:
        yield {"X-RegEngine-API-Key": raw_key}
    finally:
        api_key.enabled = False


def _detail_parts(response) -> tuple[int, object, object]:
    try:
        detail = response.json().get("detail")
    except Exception:
        return response.status_code, None, None
    if isinstance(detail, dict):
        return response.status_code, detail.get("code"), None
    return response.status_code, None, detail


def _is_tenant_denial(operation_id: str, status: int, code: object, text: object) -> bool:
    if status == 409 and code == "E_TENANT_MISMATCH":
        return True
    if status == 403 and text == MISMATCH_403_DETAIL:
        return True
    if operation_id == PORTAL_LEGACY_OPERATION and status == 404 and text == PORTAL_LEGACY_404_DETAIL:
        return True
    return False


def _tenant_path_variants(path_template: str) -> tuple[str, str]:
    """Render the path template for tenant A (own) and tenant B (other)."""
    own = path_template.replace("{tenant_id}", TENANT_A)
    other = path_template.replace("{tenant_id}", TENANT_B)
    return _concrete_path(own), _concrete_path(other)


def test_tenant_path_mismatch_never_serves_other_tenant(matrix_client, monkeypatch):
    """A tenant A key requesting tenant B's path gets the mismatch denial.

    The own-tenant call must authenticate (any status but 401/403 proves the
    credential was accepted; those two prove the tenant check never ran and
    fail the suite). The cross-tenant call must be that route's mismatch
    denial: 409 E_TENANT_MISMATCH, the 403 tenant-mismatch detail, or the
    legacy portal 404. A 200, 401, 422, or 5xx on the cross-tenant path
    fails: those are a rejected credential, validation before the check, or
    data served without the check.
    """
    client, manifest = matrix_client
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.setenv("ENV", "test")
    monkeypatch.delenv("AUTH_TEST_BYPASS_TOKEN", raising=False)

    path_operations = [o for o in _tenant_api_key_operations(manifest) if "{tenant_id}" in o["path"]]
    assert len(path_operations) >= MIN_PATH_OPERATIONS, (
        f"Tenant path-parameter operation count fell to {len(path_operations)}; "
        "update MIN_PATH_OPERATIONS deliberately, never to make red green."
    )

    failures = []
    with _tenant_a_scoped_key() as headers:
        for operation in path_operations:
            own_path, other_path = _tenant_path_variants(operation["path"])
            kwargs = _write_kwargs(operation["method"])

            _reset_probe_limiter()
            own = client.request(operation["method"], own_path, headers=headers, **kwargs)
            _reset_probe_limiter()
            cross = client.request(operation["method"], other_path, headers=headers, **kwargs)

            if own.status_code in UNAUTHENTICATED_STATUSES:
                failures.append(
                    f"{operation['operation']}: own-tenant request not authenticated "
                    f"(status {own.status_code}); the tenant check never ran"
                )
                continue
            _, cross_code, cross_text = _detail_parts(cross)
            if _is_tenant_denial(operation["operation"], cross.status_code, cross_code, cross_text):
                if TENANT_B in cross.text:
                    failures.append(
                        f"{operation['operation']}: cross-tenant refusal leaks tenant B (status {cross.status_code})"
                    )
                continue
            failures.append(
                f"{operation['operation']}: cross-tenant request not denied by the tenant boundary "
                f"(own {own.status_code}, cross {cross.status_code}, body has tenant B: {TENANT_B in cross.text})"
            )
    assert not failures, "Cross-tenant path isolation failures:\n" + "\n".join(f"  {f}" for f in failures)


def test_conflicting_tenant_claim_never_serves_other_tenant(matrix_client, monkeypatch):
    """A tenant A key with a tenant B claim is denied or serves no B data.

    Every tenant-scoped API-key operation is probed with a conflicting
    ``?tenant_id``, ``X-Tenant-ID``, and (for writes) JSON or multipart form
    ``tenant_id``.
    Routes that evaluate claims must answer with the mismatch denial (same
    rule as the path test). Routes that never evaluate the claim are pinned
    in ``CLAIM_UNENFORCED_OPERATIONS``: anything but a mismatch denial
    passes there, except a 2xx mentioning tenant B (served the other
    tenant) and a 401 (the credential itself broke), which fail. A probe
    answered 429 serves nothing and passes, but the operation is recorded
    and must already be in ``KNOWN_RATE_LIMITED_OPERATIONS``.
    """
    client, manifest = matrix_client
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.setenv("ENV", "test")
    monkeypatch.delenv("AUTH_TEST_BYPASS_TOKEN", raising=False)

    failures = []
    rate_limited_set: set[str] = set()
    with _tenant_a_scoped_key() as headers:
        for operation in _tenant_api_key_operations(manifest):
            path = _concrete_path(operation["path"].replace("{tenant_id}", TENANT_A))
            probes: list[tuple[str, dict, dict]] = [("query", {"params": {"tenant_id": TENANT_B}}, {})]
            # Both tenant header names: X-Tenant-ID (public) and
            # X-RegEngine-Tenant-ID (service-to-service, also consumed by
            # TenantContextMiddleware and treated as a claim by
            # resolve_tenant_context). A route that enforces one must
            # enforce the other through the same claim collectors.
            probes.append(("header", {}, {"X-Tenant-ID": TENANT_B, "X-RegEngine-Tenant-ID": TENANT_B}))
            if operation["operation"] == "csv:POST:/api/v1/ingest/csv/diagnostic":
                # This route binds its tenant claim from multipart form data.
                # A JSON body fails file validation before reaching that boundary.
                probes.append(
                    (
                        "body",
                        {
                            "data": {"tenant_id": TENANT_B},
                            "files": {
                                "file": (
                                    "synthetic.csv",
                                    b"cte_type,traceability_lot_code\nharvesting,synthetic-lot\n",
                                    "text/csv",
                                )
                            },
                        },
                        {},
                    )
                )
            elif operation["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
                import json as json_module

                raw = json_module.dumps({"tenant_id": TENANT_B}).encode("utf-8")
                probes.append(("body", {"content": raw}, {"Content-Type": "application/json"}))
            for label, kwargs, extra_headers in probes:
                _reset_probe_limiter()
                response = client.request(operation["method"], path, headers={**headers, **extra_headers}, **kwargs)
                _, code, text = _detail_parts(response)
                operation_id = operation["operation"]
                tag = f"{operation_id} [{label}]"
                pinned = (operation_id, label) in CLAIM_UNENFORCED_PROBES
                if _is_tenant_denial(operation_id, response.status_code, code, text):
                    if pinned:
                        failures.append(f"{tag}: now denies conflicting claims; remove from CLAIM_UNENFORCED_PROBES")
                    continue
                if response.status_code == 401:
                    failures.append(f"{tag}: credential rejected (401); the tenant check never ran")
                    continue
                if response.status_code == 403 and text != MISMATCH_403_DETAIL:
                    failures.append(f"{tag}: forbidden without the tenant-mismatch detail ({text!r:.120})")
                    continue
                if response.status_code == 429:
                    rate_limited_set.add(operation_id)
                    continue
                if not pinned:
                    failures.append(
                        f"{tag}: conflicting claim not denied by the tenant boundary "
                        f"(status {response.status_code}, detail {code!r})"
                    )
                    continue
                if response.status_code in (200, 201) and TENANT_B in response.text:
                    failures.append(f"{tag}: served data mentioning tenant B (status {response.status_code})")
    unknown_limited = sorted(rate_limited_set - KNOWN_RATE_LIMITED_OPERATIONS)
    if unknown_limited:
        failures.append(
            "Newly rate-limited claim probes (not in KNOWN_RATE_LIMITED_OPERATIONS):\n"
            + "\n".join(f"  {o}" for o in unknown_limited)
        )
    assert not failures, "Cross-tenant claim isolation failures:\n" + "\n".join(f"  {f}" for f in failures)


def test_expired_api_key_is_refused_on_tenant_route(matrix_client, monkeypatch):
    """An expired tenant key answers 401, through the real store path.

    The matrix probes above never build an expired, disabled, or low-scope
    database key; this locks the expiry branch of the in-memory store
    (``services/shared/auth.py`` ``APIKeyStore.validate_key``) against one
    tenant route so a regression there cannot hide behind the bypass.
    """
    import datetime

    client, _ = matrix_client
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.setenv("ENV", "test")
    monkeypatch.delenv("AUTH_TEST_BYPASS_TOKEN", raising=False)

    stores = _live_key_stores()
    now = datetime.datetime.now(datetime.timezone.utc)
    expired_raw, expired_key = stores[0].create_key(
        name="tenant-matrix-expired-probe",
        tenant_id=TENANT_A,
        rate_limit_per_minute=100000,
        scopes=["*"],
        expires_at=now - datetime.timedelta(hours=1),
    )
    live_raw, live_key = stores[0].create_key(
        name="tenant-matrix-live-control",
        tenant_id=TENANT_A,
        rate_limit_per_minute=100000,
        scopes=["*"],
        expires_at=now + datetime.timedelta(hours=1),
    )
    for other in stores[1:]:
        with other._lock:
            other._keys[expired_key.key_id] = expired_key
            other._keys[live_key.key_id] = live_key
    try:
        # Control first: the unexpired twin must authenticate, proving a
        # 401 below is the expiry branch and not a store wiring problem.
        _reset_probe_limiter()
        control = client.get(
            f"/api/v1/monitoring/alerts/{TENANT_A}",
            headers={"X-RegEngine-API-Key": live_raw},
        )
        assert control.status_code == 200, f"Control key answered {control.status_code}: {control.text[:160]}"
        _reset_probe_limiter()
        response = client.get(
            f"/api/v1/monitoring/alerts/{TENANT_A}",
            headers={"X-RegEngine-API-Key": expired_raw},
        )
        assert response.status_code == 401, f"Expired key answered {response.status_code}: {response.text[:160]}"
    finally:
        expired_key.enabled = False
        live_key.enabled = False


def test_low_scope_key_gets_permission_denial_not_tenant_denial(matrix_client, monkeypatch):
    """A key without the route permission stops at 403 before any tenant check.

    ``GET /api/v1/billing/subscription/{tenant_id}`` requires
    ``billing.subscription.read`` ahead of its tenant resolution, and the
    ``admin`` scope is a plain scope, not a wildcard. Both the own-tenant
    and the cross-tenant call must therefore answer 403 with the
    permission detail (never 409): this pins the evaluation order the path
    matrix depends on, so a future reorder fails here instead of silently
    changing what the matrix proves.
    """
    client, _ = matrix_client
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.setenv("ENV", "test")
    monkeypatch.delenv("AUTH_TEST_BYPASS_TOKEN", raising=False)

    stores = _live_key_stores()
    raw_key, api_key = stores[0].create_key(
        name="tenant-matrix-low-scope-probe",
        tenant_id=TENANT_A,
        rate_limit_per_minute=100000,
        scopes=["read", "write", "admin", "webhooks.ingest"],
    )
    for other in stores[1:]:
        with other._lock:
            other._keys[api_key.key_id] = api_key
    try:
        headers = {"X-RegEngine-API-Key": raw_key}
        _reset_probe_limiter()
        own = client.get(f"/api/v1/billing/subscription/{TENANT_A}", headers=headers)
        _reset_probe_limiter()
        cross = client.get(f"/api/v1/billing/subscription/{TENANT_B}", headers=headers)
        for label, response in (("own-tenant", own), ("cross-tenant", cross)):
            assert response.status_code == 403, f"{label} answered {response.status_code}: {response.text[:160]}"
            assert "Insufficient permissions" in response.text, (
                f"{label} 403 is not the permission denial: {response.text[:160]}"
            )
    finally:
        api_key.enabled = False


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
