"""In-process security tests for the audit fixes (PRs #321-#330) — #2503 rewrite.

The previous version of this module targeted live HTTP services on
``localhost:8400/8002/8200`` and wrapped every test body in
``except httpx.ConnectError: pytest.skip``. No CI job ever booted those
services, so all 33 tests passed by skipping — coverage theater on
SQL-injection, auth-guard, bypass-token, RLS-sysadmin, JWT and CSRF checks
(#2503).

This rewrite executes every assertion in-process against the consolidated
monolith (``server/main.py``) via ``fastapi.testclient.TestClient``. There
are no connection-error skip guards left: an unreachable dependency FAILS
the test.

Dependencies:
  * Postgres is NOT required — every assertion here resolves before any
    database access (auth guards raise 401 first; JWT decode fails before
    the user lookup; the SQL-injection allowlist test uses a recording
    fake session).
  * Redis IS required for the job-status tests (``ingest:owner:*`` /
    ``ingest:status:*`` lookups). The backend-ci ``repo-root-suite`` job
    provides it; locally run a Redis on ``localhost:6379`` or export
    ``REDIS_URL``.

Tests that previously targeted routes that do not exist on any RegEngine
entrypoint (``/v1/ingest/epcis/transform``, ``/v1/ingest/cte/persist``,
``/v1/ingest/alerts/configure``, ``/v1/evidence/*``, ``/v1/obligation/*``,
``/v1/admin/user/promote``, ``/v1/admin/suppliers``,
``/v1/admin/onboarding/*``, ``/v1/admin/audit-log``) were retargeted to the
real equivalents or replaced with tests of the actual defense layer — the
full disposition table is in the PR that introduced this rewrite (#2503).
"""

from __future__ import annotations

import ast
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _qualified_name(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _literal_ints(node: ast.AST) -> set[int]:
    if not isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        return set()
    return {
        item.value
        for item in node.elts
        if isinstance(item, ast.Constant) and isinstance(item.value, int) and not isinstance(item.value, bool)
    }


def test_security_release_gate_contains_no_skip_or_vacuous_assertion_patterns():
    """Keep checked-in security tests from regressing into coverage theater."""
    violations: set[str] = set()
    for path in sorted((_REPO_ROOT / "tests" / "security").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(_REPO_ROOT)
        for node in ast.walk(tree):
            location = f"{relative}:{getattr(node, 'lineno', 1)}"
            if isinstance(node, ast.Assert) and isinstance(node.test, ast.Constant) and node.test.value is True:
                violations.add(f"{location}: unconditional assert True")

            if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
                if any(isinstance(value, ast.Constant) and value.value is True for value in node.values):
                    violations.add(f"{location}: expression contains 'or True'")

            if isinstance(node, (ast.Call, ast.Attribute)):
                callable_node = node.func if isinstance(node, ast.Call) else node
                qualified = _qualified_name(callable_node)
                if qualified in {"pytest.skip", "pytest.importorskip", "pytest.xfail"} or qualified.startswith(
                    ("pytest.mark.skip", "pytest.mark.xfail")
                ):
                    violations.add(f"{location}: security release gate contains {qualified}")

            if not isinstance(node, ast.Assert) or not isinstance(node.test, ast.Compare):
                continue
            comparison = node.test
            if not isinstance(comparison.left, ast.Attribute) or comparison.left.attr != "status_code":
                continue
            for operator, comparator in zip(comparison.ops, comparison.comparators):
                if isinstance(operator, ast.In) and _literal_ints(comparator) & {404, 405, 422}:
                    violations.add(
                        f"{location}: broad status acceptance includes a routing/validation result (404/405/422)"
                    )

    assert not violations, "Security release-gate quality violations:\n" + "\n".join(sorted(violations))


def test_required_integration_database_cannot_degrade_to_skip(monkeypatch):
    """REGENGINE_REQUIRE_DB turns a missing CI database into a hard failure."""
    from tests.integration_requirements import sqlalchemy_session_or_skip

    monkeypatch.setenv("REGENGINE_REQUIRE_DB", "1")
    with pytest.raises(pytest.fail.Exception, match="integration gate must execute"):
        sqlalchemy_session_or_skip(None, reason="mandatory security database unavailable")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def monolith():
    """Import the consolidated monolith app with test env applied.

    ``tests/conftest.py`` applies ``tests/env_defaults.py`` before any test
    module imports, so REGENGINE_ENV=test, AUTH_TEST_BYPASS_TOKEN and
    AUTH_SECRET_KEY are already set. The app is
    imported (not run through its lifespan), so no DB init, task workers or
    schedulers start.
    """
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    root = str(_REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)

    # The ingestion settings object caches REDIS_URL at first call; an
    # earlier test module in the same session may have cached the
    # container-network default (rediss://redis:6379). Re-read the env.
    from services.ingestion.app.config import get_settings as ingestion_settings

    ingestion_settings.cache_clear()

    import server.main as server_main

    return server_main


@pytest.fixture(scope="module")
def client(monolith):
    # No context manager: the lifespan (DB init, workers, scheduler) must
    # not run. raise_server_exceptions=False so 500-sanitization is
    # observable instead of re-raised into the test.
    return TestClient(monolith.app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def bypass_token():
    return os.environ["AUTH_TEST_BYPASS_TOKEN"]


@pytest.fixture(scope="module")
def bypass_tenant():
    return os.getenv("AUTH_TEST_BYPASS_TENANT_ID", "11111111-1111-1111-1111-111111111111")


@pytest.fixture(scope="module")
def bypass_headers(bypass_token, bypass_tenant):
    return {"X-RegEngine-API-Key": bypass_token, "X-Tenant-ID": bypass_tenant}


@pytest.fixture(autouse=True)
def _reset_admin_bruteforce(monkeypatch, monolith):
    """Isolate auth counters without reading or deleting shared Redis data."""
    for module_name in ("app.privileged_auth", "services.admin.app.privileged_auth"):
        module = sys.modules.get(module_name)
        if module is not None:
            monkeypatch.setattr(module, "_privileged_auth_throttle", module.PrivilegedAuthThrottle(redis_client=None))


@pytest.fixture()
def in_memory_key_store(monkeypatch, monolith):
    """Force shared.auth to use the in-memory key store regardless of env.

    ``get_key_store`` returns the DatabaseAPIKeyStore whenever
    REGENGINE_ENV=production, which would require a live Postgres. The
    bypass-guard tests only assert on the branch *before* store lookup
    (bypass disabled → key invalid → 401), so pin the in-memory store to
    keep them hermetic.
    """
    from shared import auth as shared_auth

    monkeypatch.setattr(shared_auth, "get_key_store", lambda: shared_auth._key_store)


def _make_session_jwt(secret: str, *, exp_delta_s: int, aud: str = "regengine-api", extra: dict | None = None) -> str:
    now = int(time.time())
    payload = {
        "sub": str(uuid4()),
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "iat": now,
        "exp": now + exp_delta_s,
        "aud": aud,
        "iss": "regengine-admin",
        "jti": str(uuid4()),
    }
    if extra:
        payload.update(extra)
    return pyjwt.encode(payload, secret, algorithm="HS256")


# ---------------------------------------------------------------------------
# SQL Injection Prevention (PR #323)
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _RecordingSession:
    """Stands in for a SQLAlchemy session; records every executed statement."""

    def __init__(self, information_schema_rows):
        self.executed: list[tuple[str, dict | None]] = []
        self._info_rows = information_schema_rows

    def execute(self, clause, params=None):
        sql = str(clause)
        self.executed.append((sql, params))
        if "information_schema.columns" in sql:
            return _FakeResult(self._info_rows)
        return _FakeResult([])


class TestSQLInjectionPrevention:
    """PR #323 hardened dynamic column names behind an allowlist.

    The real surface is ``_query_alert_rows`` in
    ``services/ingestion/app/epcis/persistence.py``: column names read from
    ``information_schema`` are intersected with ``_ALLOWED_COLS`` before
    being interpolated into SQL. The previous tests posted ``event_col`` /
    ``tenant_col`` / ``message_expr`` JSON fields to endpoints that never
    existed; those are the internal variable names of that function, not
    API parameters.
    """

    def test_malicious_information_schema_columns_never_interpolated(self, monolith):
        from services.ingestion.app.epcis.persistence import _query_alert_rows

        evil = 'message"; DROP TABLE fsma.compliance_alerts; --'
        session = _RecordingSession(
            [(evil,), ("tenant_id",), ("cte_event_id",), ("severity",), ("alert_type",), ("message",)]
        )

        _query_alert_rows(session, tenant_id=str(uuid4()), event_id=str(uuid4()))

        # The information_schema probe plus exactly one data query.
        assert len(session.executed) == 2, f"Expected 2 statements, got {len(session.executed)}"
        data_sql = session.executed[1][0]
        assert "DROP TABLE" not in data_sql, "Malicious column name was interpolated into SQL"
        assert evil not in data_sql
        # tenant/event predicates must be bound parameters, not literals.
        assert ":tenant_id" in data_sql and ":event_id" in data_sql

    def test_no_data_query_when_no_allowlisted_columns(self, monolith):
        from services.ingestion.app.epcis.persistence import _query_alert_rows

        session = _RecordingSession([("evil'; --",), ("also_not_allowlisted",)])

        rows = _query_alert_rows(session, tenant_id=str(uuid4()), event_id=str(uuid4()))

        assert rows == []
        assert len(session.executed) == 1, "Data query must not run when no column survives the allowlist"

    @pytest.mark.parametrize(
        "malicious_job_id",
        [
            "job'; DROP TABLE events; --",
            "job' UNION SELECT * FROM secret_data; --",
            "job` OR `1`=`1",
        ],
    )
    def test_malicious_job_id_path_param_is_handled_safely(self, client, bypass_headers, malicious_job_id):
        """SQL metacharacters in the job-id path segment must yield 404, never 500."""
        response = client.get(f"/v1/ingest/status/{malicious_job_id}", headers=bypass_headers)

        assert response.status_code == 404, (
            f"Expected 404 for malicious job id, got {response.status_code}: {response.text}"
        )


# ---------------------------------------------------------------------------
# Auth Guard enforcement (PR #322)
# ---------------------------------------------------------------------------


class TestAuthGuardEnforcement:
    """Endpoints requiring authentication must 401 without credentials.

    The ``/v1/evidence/*`` and ``/v1/obligation/*`` targets of the previous
    version do not exist on any entrypoint; the tenant API-key and opaque
    admin-session surfaces below are their real counterparts.
    """

    @pytest.mark.parametrize(
        "method,endpoint",
        [
            ("GET", "/v1/ingest/status/job-123"),
            ("GET", "/v1/ingest/documents/doc-456/analysis"),
            ("GET", "/v1/ingest/discovery/queue"),
        ],
    )
    def test_ingestion_endpoints_require_auth(self, client, method, endpoint):
        response = client.request(method, endpoint)

        assert response.status_code in (401, 403), (
            f"{method} {endpoint} returned {response.status_code}, expected 401/403"
        )

    def test_vision_analyze_label_requires_auth(self, client):
        response = client.post("/api/v1/vision/analyze-label")

        assert response.status_code in (401, 403), (
            f"Expected 401/403 for unauthenticated vision analyze, got {response.status_code}"
        )

    @pytest.mark.parametrize(
        "method,endpoint",
        [
            ("GET", "/v1/admin/users"),
            ("PATCH", f"/v1/admin/users/{uuid4()}/role"),
        ],
    )
    def test_admin_session_endpoints_require_auth(self, client, method, endpoint):
        response = client.request(method, endpoint, json={"role": "admin"} if method == "PATCH" else None)

        assert response.status_code in (401, 403), (
            f"{method} {endpoint} returned {response.status_code}, expected 401/403"
        )

    @pytest.mark.parametrize(
        "method,endpoint",
        [
            ("GET", "/v1/admin/keys"),
            ("POST", "/v1/admin/tenants"),
            ("DELETE", f"/v1/admin/keys/{uuid4()}"),
        ],
    )
    def test_human_admin_endpoints_require_session_auth(self, client, method, endpoint):
        response = client.request(method, endpoint, json={} if method == "POST" else None)

        assert response.status_code in (401, 403), (
            f"{method} {endpoint} returned {response.status_code}, expected 401/403"
        )

    def test_invalid_api_key_rejected(self, client):
        response = client.get("/v1/ingest/status/job-123", headers={"X-RegEngine-API-Key": "invalid-key-12345"})

        assert response.status_code in (401, 403)

    def test_malformed_api_key_rejected(self, client):
        response = client.get(
            "/v1/ingest/status/job-123",
            headers={"X-RegEngine-API-Key": "'; DROP TABLE api_keys; --"},
        )

        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Test-bypass token guard (PR #321)
# ---------------------------------------------------------------------------


class TestK8sAuthBypassGuard:
    """AUTH_TEST_BYPASS_TOKEN must authenticate only in development/test.

    ``require_api_key`` reads REGENGINE_ENV per-request, so the production
    branch is exercised directly by flipping the env var — the previous
    version skipped itself whenever the env was not production (always).
    """

    def test_bypass_token_authenticates_in_test_env(self, client, bypass_headers):
        # 404 (job unknown) proves authentication succeeded; 401 would mean
        # the bypass was refused.
        response = client.get(f"/v1/ingest/status/{uuid4()}", headers=bypass_headers)

        assert response.status_code == 404, (
            f"Bypass token should authenticate in test env, got {response.status_code}: {response.text}"
        )

    def test_bypass_token_rejected_in_production_env(self, client, bypass_headers, monkeypatch, in_memory_key_store):
        monkeypatch.setenv("REGENGINE_ENV", "production")

        response = client.get(f"/v1/ingest/status/{uuid4()}", headers=bypass_headers)

        assert response.status_code in (401, 403), (
            f"Bypass token must not authenticate when REGENGINE_ENV=production, got {response.status_code}"
        )

    def test_bypass_token_rejected_when_env_unset(self, client, bypass_headers, monkeypatch, in_memory_key_store):
        # Unset env defaults to production — fail closed.
        monkeypatch.delenv("REGENGINE_ENV", raising=False)

        response = client.get(f"/v1/ingest/status/{uuid4()}", headers=bypass_headers)

        assert response.status_code in (401, 403), (
            f"Bypass token must not authenticate when REGENGINE_ENV is unset, got {response.status_code}"
        )


# ---------------------------------------------------------------------------
# Privilege-escalation defense (PR #324)
# ---------------------------------------------------------------------------


class TestRLSSysadminDefense:
    """Privilege elevation requires real credentials.

    ``/v1/admin/user/promote`` never existed; the real role-mutation
    surface is ``PATCH /v1/admin/users/{id}/role`` (session-authenticated,
    ``PermissionChecker("users.manage_roles")``) and human tenant
    provisioning requires an opaque high-assurance sysadmin session.
    """

    def test_role_change_rejects_api_key_credentials(self, client, bypass_headers):
        """An ingestion API key (even a privileged one) cannot change user roles."""
        response = client.patch(
            f"/v1/admin/users/{uuid4()}/role",
            headers=bypass_headers,
            json={"role": "admin"},
        )

        assert response.status_code in (401, 403), (
            f"Expected 401/403 for role change without session auth, got {response.status_code}"
        )

    def test_forged_sysadmin_bearer_token_rejected(self, client):
        """A self-signed JWT carrying a sysadmin claim must be rejected."""
        forged = _make_session_jwt("attacker-controlled-key", exp_delta_s=3600, extra={"sysadmin": True})

        response = client.get("/v1/admin/users", headers={"Authorization": f"Bearer {forged}"})

        assert response.status_code in (401, 403), f"Forged sysadmin token accepted with {response.status_code}"

    def test_tenant_provisioning_rejects_tenant_api_key(self, client, bypass_headers):
        response = client.post(
            "/v1/admin/tenants",
            headers=bypass_headers,
            json={"name": f"tenant-{uuid4()}"},
        )

        assert response.status_code in (401, 403), (
            f"Expected 401/403 for tenant provisioning without a browser session, got {response.status_code}"
        )

    def test_retired_admin_header_rejected(self, client):
        response = client.get("/v1/admin/keys", headers={"X-Admin-Key": "retired-shared-credential"})

        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# JWT validation & key rotation (PR #328)
# ---------------------------------------------------------------------------


class TestJWTKeyRotation:
    """Session JWT validation on the real bearer-authenticated surface.

    The previous version sent static strings to ``/v1/labels/health`` (an
    unauthenticated health probe) and asserted only inside an
    ``if response != 200`` branch — vacuous. ``GET /auth/me`` is the real
    JWT surface: ``decode_access_token`` verifies signature, expiry and
    audience before any user lookup.
    """

    def test_expired_jwt_rejected(self, client):
        secret = os.environ["AUTH_SECRET_KEY"]
        expired = _make_session_jwt(secret, exp_delta_s=-3600)

        response = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})

        assert response.status_code == 401, f"Expected 401 for expired JWT, got {response.status_code}"

    def test_jwt_signed_with_wrong_key_rejected(self, client):
        wrong_key = _make_session_jwt("some-other-signing-key", exp_delta_s=3600)

        response = client.get("/auth/me", headers={"Authorization": f"Bearer {wrong_key}"})

        assert response.status_code == 401, f"Expected 401 for wrong-key JWT, got {response.status_code}"

    def test_jwt_with_invalid_format_rejected(self, client):
        response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-valid-jwt"})

        assert response.status_code == 401, f"Expected 401 for malformed JWT, got {response.status_code}"

    def test_jwt_with_wrong_audience_rejected(self, client):
        """A tool-access token must not be usable as a session token (#1060)."""
        secret = os.environ["AUTH_SECRET_KEY"]
        wrong_aud = _make_session_jwt(secret, exp_delta_s=3600, aud="regengine-tool-access")

        response = client.get("/auth/me", headers={"Authorization": f"Bearer {wrong_aud}"})

        assert response.status_code == 401, f"Expected 401 for wrong-audience JWT, got {response.status_code}"


# ---------------------------------------------------------------------------
# CSRF surface (PR #329)
# ---------------------------------------------------------------------------


class TestCSRFDefenses:
    """Cookie mutations require a valid session/CSRF proof and strict origin.

    Tenant API routes use explicit header credentials. Browser administration
    uses opaque session cookies, and mutation routes additionally pass through
    the shared origin/CSRF gate. Credentialed CORS must never allow wildcard or
    unknown origins.
    """

    def test_cookie_only_request_cannot_mutate_state(self, client):
        """A browser-forgeable request (cookies, no custom headers) must be rejected."""
        response = client.post(
            "/v1/admin/tenants",
            headers={"Cookie": "session=stolen-session-cookie"},
            json={"name": "csrf-tenant"},
        )

        assert response.status_code in (401, 403), (
            f"Cookie-only state change must be rejected, got {response.status_code}"
        )

    def test_disallowed_origin_gets_no_cors_grant(self, client):
        response = client.options(
            "/v1/admin/keys",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "DELETE",
            },
        )

        allow_origin = response.headers.get("access-control-allow-origin")
        assert allow_origin != "https://evil.example.com", "CORS grant issued to a disallowed origin"
        assert allow_origin != "*", "Wildcard CORS grant issued on a credentialed API"

    def test_wildcard_origins_forbidden_in_restricted_envs(self, monolith, monkeypatch):
        from shared.cors import get_allowed_origins, should_allow_credentials

        # Invariant in the current (test) env: no wildcard alongside credentials.
        origins = get_allowed_origins()
        if should_allow_credentials():
            assert "*" not in origins, "Wildcard origin combined with credentials is a CSRF hole"

        # In production-like envs a configured wildcard must hard-fail.
        monkeypatch.setenv("REGENGINE_ENV", "production")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
        with pytest.raises(ValueError):
            get_allowed_origins()


# ---------------------------------------------------------------------------
# Security middleware behavior
# ---------------------------------------------------------------------------


class TestSecurityMiddleware:
    """Headers and host validation the middleware stack actually guarantees.

    The previous ``TestSecurityHeadersPresence`` looked for
    X-Content-Type-Options / CSP / HSTS and skipped when absent — the
    monolith does not set those (edge/frontend concern), so the tests never
    asserted anything. What the stack does guarantee: TrustedHost
    validation (PYSEC-2026-161 mitigation) and the FSMA-204 traceability
    marker on every response.
    """

    def test_forged_host_header_rejected(self, client):
        response = client.get("/v1/admin/keys", headers={"Host": "evil.example.com"})

        assert response.status_code == 400, f"Expected 400 for forged Host header, got {response.status_code}"

    def test_health_probe_exempt_from_host_validation(self, client):
        response = client.get("/health", headers={"Host": "evil.example.com"})

        assert response.status_code == 200

    def test_compliance_traceability_header_on_every_response(self, client):
        ok = client.get("/health")
        denied = client.get("/v1/ingest/status/job-123")  # 401 path

        assert ok.headers.get("X-FSMA-204-Traceability") == "true"
        assert denied.headers.get("X-FSMA-204-Traceability") == "true"


# ---------------------------------------------------------------------------
# Input validation and sanitization
# ---------------------------------------------------------------------------


class TestInputValidationAndSanitization:
    def test_oversized_request_rejected(self, client, bypass_headers):
        """Bodies above the 10 MiB RequestSizeLimitMiddleware cap must 413."""
        big_body = b'{"pad": "' + b"x" * (10 * 1024 * 1024) + b'"}'

        response = client.post(
            "/v1/ingest/url",
            content=big_body,
            headers={**bypass_headers, "Content-Type": "application/json"},
        )

        assert response.status_code == 413, f"Expected 413 for oversized request, got {response.status_code}"

    @pytest.mark.parametrize(
        "malicious_segment",
        [
            "..%2F..%2F..%2Fetc%2Fpasswd",
            "<script>alert('xss')</script>",
            "%2500%250a%250d",
        ],
    )
    def test_malicious_path_segments_handled_safely(self, client, bypass_headers, malicious_segment):
        response = client.get(f"/v1/ingest/status/{malicious_segment}", headers=bypass_headers)

        assert response.status_code == 404, (
            f"Expected 404 for malicious path segment, got {response.status_code}: {response.text}"
        )


# ---------------------------------------------------------------------------
# Error handling & information leakage
# ---------------------------------------------------------------------------


class TestErrorHandlingAndInfoLeakage:
    def test_404_does_not_leak_paths(self, client):
        response = client.get("/v1/admin/secret-internal-path-xyz")

        assert response.status_code == 404
        body = response.text.lower()
        assert "/users/" not in body
        assert "traceback" not in body
        assert 'file "' not in body

    def test_500_does_not_leak_stack_trace(self, client, monolith):
        """Unhandled exceptions must return the generic sanitized body."""
        sentinel = "sekrit-internal-detail-c0ffee"
        path = "/__test_boom_2503"

        async def _boom():
            raise RuntimeError(f"{sentinel} in /Users/internal/secret_module.py")

        monolith.app.add_api_route(path, _boom, methods=["GET"], include_in_schema=False)
        try:
            response = client.get(path)
        finally:
            monolith.app.router.routes[:] = [r for r in monolith.app.router.routes if getattr(r, "path", None) != path]

        assert response.status_code == 500
        body = response.text
        assert sentinel not in body, "Internal exception detail leaked to the client"
        lowered = body.lower()
        assert "traceback" not in lowered
        assert 'file "' not in lowered
        assert "runtimeerror" not in lowered

    def test_invalid_credentials_error_is_generic(self, client):
        secret_looking_key = "rge_prod.super-secret-key-value-123"  # pragma: allowlist secret

        response = client.get("/v1/ingest/status/job-123", headers={"X-RegEngine-API-Key": secret_looking_key})

        assert response.status_code in (401, 403)
        assert secret_looking_key not in response.text, "Submitted credential echoed back in the error body"
