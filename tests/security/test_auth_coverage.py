"""
Auth coverage test — verifies every API endpoint requires authentication.

Uses FastAPI's TestClient to walk the route table of the app production
actually deploys and hit every endpoint without auth headers. Endpoints that
return 200/2xx without auth are flagged as unprotected.

The app under test is ``server.main:app`` — the consolidated monolith the
repo-root Dockerfile builds and railway.toml deploys. Until #2822 this module
built ``services/ingestion/main.py`` instead, a standalone entrypoint nothing
deploys: every admin, graph, NLP and compliance route was outside the
enumeration, so the gate certified auth coverage over a route table that is
neither a subset nor a superset of the shipped one.

Intentionally unauthenticated endpoints (health checks, sandbox, docs)
are explicitly allow-listed so new unprotected endpoints are caught.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# ── Allow-list: endpoints that are intentionally unauthenticated ──────
#
# Every entry needs a one-line reason. "It returned 200" is not a reason —
# #2822 exists because a gate that widens its allowlist to whatever it found
# proves nothing. ``GET /health/deep`` was the one route the monolith surfaced
# that did not belong here (hostname + build + dependency topology to an
# anonymous caller); it is gated behind X-Metrics-Key instead, in
# services/admin/app/routes.py.

UNAUTHENTICATED_ALLOWLIST = frozenset(
    {
        # Service root and liveness aliases — public for platform probes
        "GET /",
        # Health/liveness — must be public for load balancers and orchestrators.
        # ``/health`` is also the gate .github/workflows/inflow-contract-ci.yml
        # and deploy.yml poll; the rest are the per-router aliases #2856 left in
        # place so each mounted service keeps a probe of its own.
        "GET /health",
        "GET /api/health",
        "GET /healthz",
        "GET /health/live",
        "GET /api/v1/fsma/metrics/health",
        "GET /api/v1/labels/health",
        # Readiness — orchestrator probes. ``/readiness`` is Railway's
        # healthcheckPath (railway.toml) and the Dockerfile HEALTHCHECK target;
        # blocking it on a credential would fail every deploy.
        "GET /ready",
        "GET /readiness",
        "GET /api/v1/ready",
        # Graph dependency probe — 200 with {"status","neo4j"} when Neo4j is
        # reachable, 503 otherwise. Listed rather than left to chance: whether
        # it answers 200 depends on the environment the gate runs in.
        "GET /api/v1/health",
        # Feature discovery is NOT allow-listed: the monolith gates
        # ``GET /api/v1/features`` behind X-Metrics-Key (#2517) because the
        # router topology fingerprints the deployment. Leaving it here would
        # blind this gate to that guard being removed.
        # Public/static compatibility and reference data — no tenant data returned
        "GET /api/v1/billing/plans",
        # Unprefixed alias of /api/v1/billing/plans — same static plan catalog
        "GET /billing/plans",
        "GET /api/v1/fsma/export-jobs",
        "GET /api/v1/fsma/mappings",
        "GET /api/v1/onboarding/steps",
        "GET /api/v1/products/categories/ftl",
        "GET /api/v1/team/roles/definitions",
        # CSV column definitions for each CTE type — schema documentation,
        # no tenant data and no store lookup
        "GET /api/v1/templates",
        # Supplier correction form — static HTML shell with no tenant data.
        # The correction link carries the token in the URL fragment (never
        # sent to the server, keeping it out of access logs); every data
        # endpoint behind the form (/context, /exchange, /session/*) requires
        # the token or a bearer session and is rate-limited (#2594 slice).
        "GET /api/v1/remediation/supplier/form",
        # Sandbox — intentionally public with rate limiting
        "POST /api/v1/sandbox/evaluate",
        # Public proof surface — deterministic recall drill over a frozen
        # synthetic dataset baked into the module, no tenant context and no
        # store access. Documented as tenantless and unauthenticated in
        # docs/engineering/ROUTER_SURFACE.md ("Public Proof Surface").
        "POST /api/v1/proof/recall-drill",
        # Webhook receivers — use signature verification instead of API keys
        "POST /api/v1/integrations/webhook/{tenant_id}/{connector_id}",
        # OpenAPI docs
        "GET /docs",
        "GET /redoc",
        "GET /openapi.json",
    }
)

# Env the monolith needs to build and to authenticate like a deployed
# instance. Set before ``server.main`` is imported.
#
# ``REGENGINE_ENV`` is the load-bearing one. ``authz._is_dev_env()`` opens the
# ``dev_open`` fallback for ``development`` and ``test`` only — and
# tests/env_defaults.py sets ``REGENGINE_ENV=test`` for the whole session,
# which would authenticate every unauthenticated probe and make this gate
# vacuous. ``staging`` takes the fail-closed branch, which is what production
# takes too.
#
# ``API_KEY`` arms the configured-master-key branch of
# ``get_ingestion_principal``. Note it may be inert here: that branch reads
# ``importlib.import_module("app.config").get_settings().api_key``, and in the
# monolith the bare ``app`` package resolves to whichever service directory
# won sys.path — often one whose Settings has no ``api_key`` field at all. It
# is set because when it does resolve to the ingestion config it is required;
# the gate does not depend on it, because both branches reject an
# unauthenticated caller outside dev/test.
_AUTH_ENV = {
    "API_KEY": "test-auth-coverage-master-key",  # pragma: allowlist secret
    "REGENGINE_ENV": "staging",
    "ENV": "staging",
}

# Build-time requirements of the monolith that the ingestion entrypoint did
# not have. ``setdefault`` semantics: a CI job that supplies a real Postgres
# keeps it.
_BUILD_ENV_DEFAULTS = {
    # services/admin/app/database.py refuses to start without one of these,
    # and its ADMIN_FALLBACK_SQLITE path is allowed only under
    # REGENGINE_ENV=development/test/local — which this module is not.
    "ADMIN_DATABASE_URL": "sqlite:///:memory:",
    "ADMIN_FALLBACK_SQLITE": "sqlite:///:memory:",
    "AUTH_SECRET_KEY": "auth-coverage-gate-secret-not-a-real-key-000000",  # pragma: allowlist secret
    "ADMIN_MASTER_KEY": "auth-coverage-admin-master-key",  # pragma: allowlist secret
    # Neutralises TenantRateLimitMiddleware for a cold import. The bucket is
    # also swapped at probe time (see _neutralise_rate_limiters) because the
    # middleware reads this only when it is instantiated, which may already
    # have happened.
    "TENANT_RATE_LIMIT_RPM": "1000000",
}


def _build_test_app():
    """Import and return the consolidated monolith FastAPI app.

    ``server.main`` is what the repo-root Dockerfile runs
    (``gunicorn server.main:app``) and what railway.toml deploys, so it is
    the only route table worth policing. It bootstraps sys.path for
    ``services/`` and ``shared/`` itself; the caller is responsible for the
    environment (see ``app_and_client``).
    """
    import sys
    from pathlib import Path

    repo_root = str(Path(__file__).resolve().parents[2])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    _clear_settings_caches()

    import server.main as server_main

    # Settings are cached per process; an earlier test module may have
    # populated them before _AUTH_ENV was applied.
    _clear_settings_caches()

    return server_main.app


def _clear_settings_caches() -> None:
    """Drop cached Settings so the auth env applied by the fixture is read."""
    import importlib
    import sys

    for module_name in ("app.config", "services.ingestion.app.config"):
        module = sys.modules.get(module_name)
        if module is None:
            try:
                module = importlib.import_module(module_name)
            except Exception:
                continue
        get_settings = getattr(module, "get_settings", None)
        cache_clear = getattr(get_settings, "cache_clear", None)
        if cache_clear is not None:
            cache_clear()


def _extract_endpoints(app) -> list[tuple[str, str]]:
    """Extract all (METHOD, path) pairs from the FastAPI app's routes.

    Enumeration goes through ``shared.route_introspection`` rather than
    ``app.routes`` directly. Since fastapi 0.137 an included router stays on
    ``app.routes`` as one wrapper object, so the direct walk returned the few
    routes registered on the app itself — this gate would have policed a
    handful of endpoints and reported success. The helper flattens both
    shapes and raises on any it does not recognise.
    """
    from shared.paths import ensure_shared_importable

    ensure_shared_importable()
    from shared.route_introspection import iter_effective_routes

    endpoints = [
        (method, path)
        for path, route in iter_effective_routes(app)
        for method in (route.methods or ())
        if method in ("GET", "POST", "PUT", "PATCH", "DELETE")
    ]
    # A gate that proves "every endpoint requires auth" is worthless if it
    # found no endpoints. The monolith mounts 425 (method, path) pairs across
    # 399 paths at the time of writing; the floor only has to be high enough
    # that a collapsed route table — or a silent fall back to one of the
    # standalone service entrypoints — cannot slip through as a pass.
    assert len(endpoints) > 300, (
        f"route enumeration returned only {len(endpoints)} endpoints — the monolith's "
        "route table did not flatten, so this gate is not actually inspecting it"
    )
    return sorted(endpoints)


def _make_dummy_path(path: str) -> str:
    """Replace path parameters with dummy values for testing."""
    import re

    return re.sub(r"\{[^}]+\}", "test-000", path)


@pytest.fixture(scope="module")
def app_and_client():
    """Build the monolith once for all tests in this module, with auth enforced.

    Applies ``_AUTH_ENV`` so the auth layer rejects unauthenticated requests
    instead of falling through to the ``dev_open`` fallback, plus the
    monolith's build-time env, then restores the prior environment on teardown
    so the change does not leak into the rest of the test session.
    """
    import os

    env_keys = tuple(_AUTH_ENV) + tuple(_BUILD_ENV_DEFAULTS) + ("AUTH_TEST_BYPASS_TOKEN",)
    prev_env = {key: os.environ.get(key) for key in env_keys}
    os.environ.update(_AUTH_ENV)
    for key, value in _BUILD_ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)
    os.environ.pop("AUTH_TEST_BYPASS_TOKEN", None)
    try:
        app = _build_test_app()
        client = TestClient(app, raise_server_exceptions=False)
    except Exception as e:
        _restore_env(prev_env)
        raise AssertionError(
            f"Cannot build the consolidated monolith (server.main): {e}. This gate used "
            "to pytest.skip here, which is indistinguishable from a pass in the checks UI."
        ) from e

    # The one env var this gate cannot work without: dev_open authenticates
    # every anonymous request, so an armed fallback makes the whole module
    # meaningless. Assert it rather than trusting the env round-trip.
    from services.ingestion.app import authz

    assert not authz._is_dev_env(), (
        "REGENGINE_ENV puts authz in dev/test mode — the dev_open fallback would "
        "authenticate every unauthenticated probe and this gate would prove nothing"
    )

    try:
        yield app, client
    finally:
        _restore_env(prev_env)
        _clear_settings_caches()


def _restore_env(prev_env):
    """Restore auth-related environment after the module runs."""
    import os

    for key, value in prev_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _neutralise_rate_limiters(endpoint_count: int):
    """Disarm every limiter that sits in front of auth; return an undo callable.

    A rate limiter answering 429 means the probe never reached the auth layer,
    so a limited route proves nothing either way — and this test counts any
    non-2xx as "auth enforced". Measured on the monolith at 2b2fb10d: with the
    tenant limiter at its default 100 rpm, 320 of 425 probes came back 429 and
    only 89 reached auth. The gate would have been ~75% vacuous while green.

    ``test_no_probe_was_rate_limited`` asserts the neutralisation worked, so a
    limiter added later cannot quietly re-mask the gate.
    """
    import sys

    undo = []

    # 1. TenantRateLimitMiddleware (server/main.py, default_rpm=100). Swapping
    #    the shared module-level bucket rather than raising the env limit
    #    works whether or not the middleware has already been instantiated,
    #    and also covers the route-level ``consume_tenant_rate_limit`` guards.
    from shared.tenant_rate_limiting import TenantRateLimitMiddleware

    tenant_rl = sys.modules[TenantRateLimitMiddleware.__module__]

    class _AlwaysAllowBucket:
        def is_allowed(self, key: str, limit: int, window: int = 60) -> tuple[bool, int]:
            return True, limit

    previous_bucket = tenant_rl._bucket
    tenant_rl._bucket = _AlwaysAllowBucket()
    undo.append(lambda: setattr(tenant_rl, "_bucket", previous_bucket))

    # 2. The per-IP auth *failure* counter. Every probe here is a failed auth
    #    by construction, so after 15 of them the limiter blocks "testclient"
    #    and every later endpoint returns 429 — masking a genuinely
    #    unprotected endpoint and making the result order-dependent.
    #
    #    This used to clear a module-level dict, authz._auth_failures. #2711
    #    replaced that with a BruteForceLimiter and deleted the dict (there is
    #    a test asserting it stays deleted). Swap in a fresh per-process
    #    limiter whose budget is far above the endpoint count instead.
    from shared.rate_limit import BruteForceLimiter

    def _unlimited(namespace: str, window_seconds: int) -> BruteForceLimiter:
        limiter = BruteForceLimiter(
            namespace=namespace,
            max_failures=10 * endpoint_count + 1000,
            window_seconds=window_seconds,
            redis_client=None,
        )
        limiter._redis = None  # ignore any env-provided Redis
        return limiter

    # The monolith mounts ``services.ingestion.app.routes``, so its handlers
    # close over ``services.ingestion.app.authz``. Patch every loaded module
    # that exposes the limiter, since sys.path ordering decides whether a bare
    # ``app.authz`` is the same object or a second copy.
    for name in [n for n in list(sys.modules) if n.endswith("app.authz")]:
        module = sys.modules.get(name)
        if module is None or not hasattr(module, "_auth_limiter"):
            continue
        previous = module._auth_limiter
        module._auth_limiter = _unlimited("test-auth-coverage", module._AUTH_FAIL_WINDOW)
        undo.append(lambda m=module, p=previous: setattr(m, "_auth_limiter", p))

    # 3. verify_admin_key locks an IP out after 5 failed X-Admin-Key attempts
    #    in 60s. The monolith mounts admin routes that use it, and the counter
    #    is Redis-backed wherever REDIS_URL is set — so it survives between CI
    #    runs and would 429 probes for reasons unrelated to this branch.
    from services.admin.app import routes as admin_routes

    previous_admin = admin_routes._admin_brute_force
    admin_routes._admin_brute_force = _unlimited("test-auth-coverage-admin", admin_routes._ADMIN_WINDOW_SECONDS)
    undo.append(lambda: setattr(admin_routes, "_admin_brute_force", previous_admin))

    # 4. slowapi route decorators (e.g. 5/min on the public recall drill,
    #    10/min on proof verify). Shared storage means a second CI run inside
    #    the same window would otherwise inherit the first run's counters.
    from shared.rate_limit import limiter as slowapi_limiter

    previous_enabled = slowapi_limiter.enabled
    slowapi_limiter.enabled = False
    undo.append(lambda: setattr(slowapi_limiter, "enabled", previous_enabled))

    def _restore():
        for fn in reversed(undo):
            fn()

    return _restore


@pytest.fixture(scope="module")
def probe_results(app_and_client):
    """Probe every enumerated endpoint once, unauthenticated.

    Module-scoped so the route table is walked once and both the
    unprotected-endpoint assertion and the rate-limit assertion read the same
    run — two independent walks would double every limiter's consumption.
    """
    app, client = app_and_client
    endpoints = _extract_endpoints(app)
    restore = _neutralise_rate_limiters(len(endpoints))

    results: dict[str, int] = {}
    try:
        for method, path in endpoints:
            # Skip HEAD (mirrors GET auth) and OPTIONS (CORS preflight)
            if method in ("HEAD", "OPTIONS"):
                continue
            response = client.request(method, _make_dummy_path(path))
            results[f"{method} {path}"] = response.status_code
    finally:
        restore()

    return results


def test_all_endpoints_require_auth(probe_results):
    """Every endpoint not in the allowlist must reject unauthenticated requests."""
    # 401/403 = auth enforced. 404/405/422 = route resolved but rejected
    # on other grounds (still means auth middleware ran or route doesn't match).
    # Only 200/201/204 without auth is a problem.
    unprotected = [
        f"{key} -> {status}"
        for key, status in sorted(probe_results.items())
        if status in (200, 201, 204) and key not in UNAUTHENTICATED_ALLOWLIST
    ]

    assert not unprotected, "Endpoints accessible without authentication:\n" + "\n".join(
        f"  {e}" for e in unprotected
    )


def test_no_probe_was_rate_limited(probe_results):
    """A 429 means the probe never reached auth — the gate must not accept it.

    ``test_all_endpoints_require_auth`` treats every non-2xx as "auth
    enforced". A rate limiter in front of the auth layer therefore turns
    unproven endpoints into silent passes, which is exactly how the monolith
    behaved before #2822: 320 of 425 probes were 429 at the default 100 rpm.
    Without this assertion the neutralisation in ``_neutralise_rate_limiters``
    could rot — a new limiter, a changed default — and nothing would say so.
    """
    limited = [f"{key} -> {status}" for key, status in sorted(probe_results.items()) if status == 429]

    assert not limited, (
        "Probes were rate-limited before reaching the auth layer, so their result proves "
        "nothing. Add the responsible limiter to _neutralise_rate_limiters():\n"
        + "\n".join(f"  {e}" for e in limited)
    )


def test_auth_layer_actually_ran(probe_results):
    """Most probes must come back 401/403, not merely "not 2xx".

    The counterpart to the endpoint-count floor. If a misconfiguration made
    every request fail early — a rejecting middleware, a broken app build —
    every probe would be non-2xx and this module would report success without
    the auth layer having run once. Measured on the monolith at 2b2fb10d:
    370 of 404 non-allowlisted probes were 401/403 (92%).
    """
    probed = {key: status for key, status in probe_results.items() if key not in UNAUTHENTICATED_ALLOWLIST}
    auth_enforced = sum(1 for status in probed.values() if status in (401, 403))

    assert probed, "no endpoints were probed"
    assert auth_enforced >= 0.75 * len(probed), (
        f"only {auth_enforced} of {len(probed)} probed endpoints answered 401/403. The auth "
        "layer is not the thing rejecting these requests, so this gate is not measuring auth."
    )


def test_allowlist_entries_still_exist(app_and_client):
    """Verify allowlist entries map to real endpoints — stale entries should be removed."""
    app, _ = app_and_client
    endpoints = _extract_endpoints(app)
    endpoint_keys = {f"{m} {p}" for m, p in endpoints}

    stale = UNAUTHENTICATED_ALLOWLIST - endpoint_keys
    # /docs, /redoc and /openapi.json are plain starlette Routes, not
    # APIRoutes, so route enumeration deliberately skips them.
    docs_paths = {"GET /docs", "GET /redoc", "GET /openapi.json"}
    stale -= docs_paths

    assert not stale, "Stale allowlist entries (endpoints no longer exist):\n" + "\n".join(
        f"  {e}" for e in sorted(stale)
    )
