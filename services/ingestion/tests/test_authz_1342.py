"""Coverage for app/authz.py — ingestion service authorization.

Locks:
- IP auth-failure rate limiting (15-failure / 5-minute window)
- Production detection via REGENGINE_ENV / ENV / DATABASE_URL heuristics
- IngestionPrincipal Pydantic defaults
- Permission normalization and RBAC role → rate-limit multiplier
- Per-scope RPM overrides via INGESTION_RBAC_RATE_LIMITS
- Tenant rate-limit chain: principal.tenant_id → X-Tenant-ID/X-RegEngine-Tenant-ID → ?tenant_id → "global"
- get_ingestion_principal branches (database-scoped key and explicit dev-open)
- require_permission: insufficient perm 403, cross-tenant 403, tenant-context conflict 400, rate-limit 429

Issue: #1342
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from services.ingestion.app import authz
from services.ingestion.app.authz import (
    IngestionPrincipal,
    _check_auth_rate_limit,
    _is_dev_env,
    _is_production_env,
    _normalize_permission,
    _principal_from_api_key,
    _principal_rate_limit_role,
    _rate_limit_overrides,
    _rate_limit_window_seconds,
    _record_auth_failure,
    _requested_tenant_context,
    _rpm_for_permission,
    _tenant_for_rate_limit,
    get_ingestion_principal,
    get_optional_ingestion_principal,
    require_permission,
)
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_auth_failures(monkeypatch):
    """#2711: give every test a fresh per-process BruteForceLimiter (no
    Redis) so failure state cannot leak between tests."""
    from shared.rate_limit import BruteForceLimiter

    limiter = BruteForceLimiter(
        namespace="test-authz-1342",
        max_failures=authz._AUTH_FAIL_MAX,
        window_seconds=authz._AUTH_FAIL_WINDOW,
        redis_client=None,
    )
    limiter._redis = None  # ignore any env-provided Redis
    monkeypatch.setattr(authz, "_auth_limiter", limiter)
    yield


@pytest.fixture(autouse=True)
def _clear_rate_limit_override_cache():
    """_rate_limit_overrides is @lru_cache — flush between tests."""
    _rate_limit_overrides.cache_clear()
    yield
    _rate_limit_overrides.cache_clear()


@pytest.fixture
def _strip_env(monkeypatch):
    """Remove env vars that drive branching inside authz."""
    for var in (
        "REGENGINE_ENV",
        "ENV",
        "DATABASE_URL",
        "INGESTION_RBAC_RATE_LIMITS",
        "INGESTION_RBAC_RATE_LIMIT_DEFAULT_RPM",
        "INGESTION_RBAC_RATE_LIMIT_WINDOW_SECONDS",
        "API_KEY",
        "REGENGINE_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# _check_auth_rate_limit / _record_auth_failure
# ---------------------------------------------------------------------------


class TestAuthFailureRateLimit:
    def test_record_adds_timestamp(self):
        _record_auth_failure("1.2.3.4")
        assert len(authz._auth_limiter._mem_failures["1.2.3.4"]) == 1

    def test_record_accumulates(self):
        for _ in range(5):
            _record_auth_failure("1.2.3.4")
        assert len(authz._auth_limiter._mem_failures["1.2.3.4"]) == 5

    def test_check_below_threshold_allows(self):
        for _ in range(authz._AUTH_FAIL_MAX - 1):
            _record_auth_failure("1.2.3.4")
        _check_auth_rate_limit("1.2.3.4")  # should not raise

    def test_check_at_threshold_raises_429(self):
        for _ in range(authz._AUTH_FAIL_MAX):
            _record_auth_failure("1.2.3.4")
        with pytest.raises(HTTPException) as exc:
            _check_auth_rate_limit("1.2.3.4")
        assert exc.value.status_code == 429
        assert "authentication" in exc.value.detail.lower()

    def test_check_prunes_expired_entries(self):
        old = time.time() - authz._AUTH_FAIL_WINDOW - 10
        authz._auth_limiter._mem_failures["1.2.3.4"] = [old] * authz._AUTH_FAIL_MAX
        # Even though 15 timestamps exist, all are stale → not blocked
        _check_auth_rate_limit("1.2.3.4")
        assert authz._auth_limiter._mem_failures["1.2.3.4"] == []

    def test_check_unseen_ip_ok(self):
        _check_auth_rate_limit("8.8.8.8")  # no state → no raise


# ---------------------------------------------------------------------------
# _is_production_env
# ---------------------------------------------------------------------------


class TestIsProductionEnv:
    """Fail-closed environment detection for dev-open auth."""

    def test_regengine_env_production(self, _strip_env, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "production")
        assert _is_production_env() is True

    def test_regengine_env_uppercase(self, _strip_env, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "PRODUCTION")
        assert _is_production_env() is True

    def test_env_fallback_production(self, _strip_env, monkeypatch):
        monkeypatch.setenv("ENV", "production")
        assert _is_production_env() is True

    def test_database_url_supabase(self, _strip_env, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgres://x@aws-1.pooler.supabase.com:5432/db")
        assert _is_production_env() is True

    def test_database_url_railway(self, _strip_env, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgres://x@railway.app/db")
        assert _is_production_env() is True

    def test_all_unset_is_production_fail_closed(self, _strip_env):
        assert _is_production_env() is True

    def test_dev_env_returns_false(self, _strip_env, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "development")
        monkeypatch.setenv("ENV", "staging")
        monkeypatch.setenv("DATABASE_URL", "postgres://localhost:5432/db")
        assert _is_production_env() is False

    def test_test_env_returns_false(self, _strip_env, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "test")
        assert _is_production_env() is False

    def test_is_dev_env_requires_explicit_dev_or_test(self, _strip_env, monkeypatch):
        assert _is_dev_env() is False
        monkeypatch.setenv("REGENGINE_ENV", "staging")
        assert _is_dev_env() is False
        monkeypatch.setenv("REGENGINE_ENV", "development")
        assert _is_dev_env() is True


# ---------------------------------------------------------------------------
# IngestionPrincipal
# ---------------------------------------------------------------------------


class TestIngestionPrincipal:
    def test_minimal_required(self):
        p = IngestionPrincipal(key_id="k1")
        assert p.key_id == "k1"
        assert p.scopes == []
        assert p.tenant_id is None
        assert p.auth_mode == "scoped_key"

    def test_default_scopes_is_independent(self):
        a = IngestionPrincipal(key_id="a")
        b = IngestionPrincipal(key_id="b")
        a.scopes.append("x")
        assert b.scopes == []

    def test_missing_key_id_raises(self):
        with pytest.raises(ValidationError):
            IngestionPrincipal()  # type: ignore[call-arg]

    def test_all_fields(self):
        p = IngestionPrincipal(
            key_id="k",
            scopes=["fda.export"],
            tenant_id="t1",
            auth_mode="scoped_key",
        )
        assert p.scopes == ["fda.export"]
        assert p.tenant_id == "t1"
        assert p.auth_mode == "scoped_key"


# ---------------------------------------------------------------------------
# _normalize_permission + _principal_rate_limit_role
# ---------------------------------------------------------------------------


class TestNormalizePermission:
    def test_lowercases(self):
        assert _normalize_permission("FDA.Export") == "fda.export"

    def test_replaces_colon_with_dot(self):
        assert _normalize_permission("fda:export") == "fda.export"

    def test_strips_whitespace(self):
        assert _normalize_permission("  exchange.read  ") == "exchange.read"


class TestPrincipalRateLimitRole:
    def test_wildcard_is_admin(self):
        p = IngestionPrincipal(key_id="k", scopes=["*"])
        assert _principal_rate_limit_role(p) == "admin"

    def test_admin_scope_prefix_is_admin(self):
        p = IngestionPrincipal(key_id="k", scopes=["admin.tenants"])
        assert _principal_rate_limit_role(p) == "admin"

    def test_write_scope_is_operator(self):
        p = IngestionPrincipal(key_id="k", scopes=["fda.write"])
        assert _principal_rate_limit_role(p) == "operator"

    def test_ingest_scope_is_operator(self):
        p = IngestionPrincipal(key_id="k", scopes=["kafka.ingest"])
        assert _principal_rate_limit_role(p) == "operator"

    def test_export_scope_is_operator(self):
        p = IngestionPrincipal(key_id="k", scopes=["fda.export"])
        assert _principal_rate_limit_role(p) == "operator"

    def test_verify_scope_is_operator(self):
        p = IngestionPrincipal(key_id="k", scopes=["fda.verify"])
        assert _principal_rate_limit_role(p) == "operator"

    def test_read_only_is_viewer(self):
        p = IngestionPrincipal(key_id="k", scopes=["exchange.read"])
        assert _principal_rate_limit_role(p) == "viewer"

    def test_empty_scopes_is_viewer(self):
        p = IngestionPrincipal(key_id="k")
        assert _principal_rate_limit_role(p) == "viewer"

    def test_case_insensitive(self):
        p = IngestionPrincipal(key_id="k", scopes=["FDA:WRITE"])
        assert _principal_rate_limit_role(p) == "operator"


# ---------------------------------------------------------------------------
# _rate_limit_overrides
# ---------------------------------------------------------------------------


class TestRateLimitOverrides:
    def test_no_env_returns_empty(self, _strip_env):
        assert _rate_limit_overrides() == {}

    def test_single_override(self, _strip_env, monkeypatch):
        monkeypatch.setenv("INGESTION_RBAC_RATE_LIMITS", "fda.export=60")
        assert _rate_limit_overrides() == {"fda.export": 60}

    def test_multiple_overrides(self, _strip_env, monkeypatch):
        monkeypatch.setenv("INGESTION_RBAC_RATE_LIMITS", "fda.export=60,exchange.read=240")
        assert _rate_limit_overrides() == {"fda.export": 60, "exchange.read": 240}

    def test_normalizes_scope(self, _strip_env, monkeypatch):
        monkeypatch.setenv("INGESTION_RBAC_RATE_LIMITS", "FDA:Export=30")
        assert _rate_limit_overrides() == {"fda.export": 30}

    def test_drops_malformed_missing_eq(self, _strip_env, monkeypatch):
        monkeypatch.setenv("INGESTION_RBAC_RATE_LIMITS", "fda.export,exchange.read=100")
        assert _rate_limit_overrides() == {"exchange.read": 100}

    def test_drops_non_numeric_value(self, _strip_env, monkeypatch):
        monkeypatch.setenv("INGESTION_RBAC_RATE_LIMITS", "fda.export=abc,exchange.read=100")
        assert _rate_limit_overrides() == {"exchange.read": 100}

    def test_clamps_to_min_one(self, _strip_env, monkeypatch):
        monkeypatch.setenv("INGESTION_RBAC_RATE_LIMITS", "fda.export=0,exchange.read=-5")
        result = _rate_limit_overrides()
        assert result == {"fda.export": 1, "exchange.read": 1}

    def test_empty_tokens_ignored(self, _strip_env, monkeypatch):
        monkeypatch.setenv("INGESTION_RBAC_RATE_LIMITS", ",,fda.export=60,,")
        assert _rate_limit_overrides() == {"fda.export": 60}

    def test_whitespace_stripped_from_raw(self, _strip_env, monkeypatch):
        monkeypatch.setenv("INGESTION_RBAC_RATE_LIMITS", "   ")
        assert _rate_limit_overrides() == {}


# ---------------------------------------------------------------------------
# _rpm_for_permission + _rate_limit_window_seconds
# ---------------------------------------------------------------------------


class TestRpmForPermission:
    def test_base_action_read(self, _strip_env):
        p = IngestionPrincipal(key_id="k", scopes=["exchange.read"])
        # read=180 base × 1.0 viewer
        assert _rpm_for_permission("exchange.read", p) == 180

    def test_base_action_write(self, _strip_env):
        p = IngestionPrincipal(key_id="k", scopes=["fda.write"])
        # write=90 base × 1.5 operator
        assert _rpm_for_permission("fda.write", p) == 135

    def test_admin_multiplier(self, _strip_env):
        p = IngestionPrincipal(key_id="k", scopes=["*"])
        # ingest=75 base × 3.0 admin
        assert _rpm_for_permission("kafka.ingest", p) == 225

    def test_unknown_action_uses_default(self, _strip_env, monkeypatch):
        monkeypatch.setenv("INGESTION_RBAC_RATE_LIMIT_DEFAULT_RPM", "200")
        p = IngestionPrincipal(key_id="k")
        # "fancy" not in _ACTION_BASE_RPM → default_rpm 200 × 1.0 viewer
        assert _rpm_for_permission("fda.fancy", p) == 200

    def test_override_wins(self, _strip_env, monkeypatch):
        monkeypatch.setenv("INGESTION_RBAC_RATE_LIMITS", "fda.export=12")
        p = IngestionPrincipal(key_id="k", scopes=["fda.export"])
        # override 12 × 1.5 operator = 18
        assert _rpm_for_permission("fda.export", p) == 18

    def test_clamps_to_at_least_one(self, _strip_env, monkeypatch):
        monkeypatch.setenv("INGESTION_RBAC_RATE_LIMITS", "fda.export=1")
        p = IngestionPrincipal(key_id="k", scopes=["exchange.read"])
        # viewer × 1 = 1
        assert _rpm_for_permission("fda.export", p) == 1

    def test_permission_without_dot(self, _strip_env):
        p = IngestionPrincipal(key_id="k")
        # "read" → action = "read" → base 180 × 1.0
        assert _rpm_for_permission("read", p) == 180


class TestRateLimitWindowSeconds:
    def test_default_is_60(self, _strip_env):
        assert _rate_limit_window_seconds() == 60

    def test_env_override(self, _strip_env, monkeypatch):
        monkeypatch.setenv("INGESTION_RBAC_RATE_LIMIT_WINDOW_SECONDS", "30")
        assert _rate_limit_window_seconds() == 30

    def test_clamps_to_min_one(self, _strip_env, monkeypatch):
        monkeypatch.setenv("INGESTION_RBAC_RATE_LIMIT_WINDOW_SECONDS", "0")
        assert _rate_limit_window_seconds() == 1


# ---------------------------------------------------------------------------
# _tenant_for_rate_limit
# ---------------------------------------------------------------------------


def _fake_request(
    tenant_header=None,
    tenant_query=None,
    client_host="1.1.1.1",
    regengine_tenant_header=None,
):
    headers = {}
    if tenant_header is not None:
        headers["X-Tenant-ID"] = tenant_header
    if regengine_tenant_header is not None:
        headers["X-RegEngine-Tenant-ID"] = regengine_tenant_header
    query = {}
    if tenant_query is not None:
        query["tenant_id"] = tenant_query
    req = MagicMock(spec=Request)
    req.headers = headers
    req.query_params = query
    req.client = SimpleNamespace(host=client_host) if client_host else None
    req.state = SimpleNamespace()
    return req


class TestTenantForRateLimit:
    def test_principal_tenant_wins(self):
        p = IngestionPrincipal(key_id="k", tenant_id="principal-t")
        req = _fake_request(tenant_header="header-t", tenant_query="query-t")
        assert _tenant_for_rate_limit(req, p) == "principal-t"

    def test_header_fallback(self):
        p = IngestionPrincipal(key_id="k")
        req = _fake_request(tenant_header="header-t", tenant_query="query-t")
        assert _tenant_for_rate_limit(req, p) == "header-t"

    def test_regengine_header_fallback(self):
        p = IngestionPrincipal(key_id="k")
        req = _fake_request(regengine_tenant_header="regengine-header-t", tenant_query="query-t")
        assert _tenant_for_rate_limit(req, p) == "regengine-header-t"

    def test_query_string_ignored_returns_global(self):
        """EPIC-A #1651: query-string tenant_id is attacker-controllable
        and must not determine the rate-limit bucket. With no principal
        tenant and no X-Tenant-ID header, the bucket falls through to
        "global" — a query-only request cannot isolate itself into a
        low-traffic per-tenant bucket."""
        p = IngestionPrincipal(key_id="k")
        req = _fake_request(tenant_query="query-t")
        assert _tenant_for_rate_limit(req, p) == "global"

    def test_global_default(self):
        p = IngestionPrincipal(key_id="k")
        req = _fake_request()
        assert _tenant_for_rate_limit(req, p) == "global"


class TestRequestedTenantContext:
    def test_query_only(self):
        """Query tenant_id is read for DEFENSIVE mismatch detection only —
        the value is never used as a trust signal. See the
        ``nosemgrep:`` annotation on the read in authz.py."""
        assert _requested_tenant_context(_fake_request(tenant_query="query-t")) == "query-t"

    def test_x_tenant_header_only(self):
        assert _requested_tenant_context(_fake_request(tenant_header="header-t")) == "header-t"

    def test_regengine_tenant_header_only(self):
        req = _fake_request(regengine_tenant_header="regengine-header-t")
        assert _requested_tenant_context(req) == "regengine-header-t"

    def test_matching_query_and_header_ok(self):
        req = _fake_request(tenant_header="tenant-a", tenant_query="tenant-a")
        assert _requested_tenant_context(req) == "tenant-a"

    def test_conflicting_query_and_header_rejected(self):
        req = _fake_request(tenant_header="header-t", tenant_query="query-t")
        with pytest.raises(HTTPException) as exc:
            _requested_tenant_context(req)
        assert exc.value.status_code == 400
        assert "Conflicting tenant context" in exc.value.detail


# ---------------------------------------------------------------------------
# _principal_from_api_key
# ---------------------------------------------------------------------------


class TestPrincipalFromApiKey:
    def test_maps_all_fields(self):
        api_key = SimpleNamespace(key_id="k-1", scopes=["fda.export"], tenant_id="t-1")
        p = _principal_from_api_key(api_key)  # type: ignore[arg-type]
        assert p.key_id == "k-1"
        assert p.scopes == ["fda.export"]
        assert p.tenant_id == "t-1"
        assert p.auth_mode == "scoped_key"

    def test_none_scopes_normalized(self):
        api_key = SimpleNamespace(key_id="k", scopes=None, tenant_id=None)
        p = _principal_from_api_key(api_key)  # type: ignore[arg-type]
        assert p.scopes == []


# ---------------------------------------------------------------------------
# get_ingestion_principal
# ---------------------------------------------------------------------------


def _build_app(dep=None):
    app = FastAPI()

    @app.get("/whoami")
    async def _whoami(principal: IngestionPrincipal = _dep_default(dep)):
        return {
            "key_id": principal.key_id,
            "scopes": principal.scopes,
            "tenant_id": principal.tenant_id,
            "auth_mode": principal.auth_mode,
        }

    return app


def _dep_default(dep):
    from fastapi import Depends

    return Depends(dep or get_ingestion_principal)


class TestGetIngestionPrincipal:
    def test_retired_environment_key_is_not_special(self, _strip_env, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "production")
        monkeypatch.setenv("API_KEY", "retired-master")

        async def _reject(request, x_regengine_api_key):
            raise HTTPException(status_code=401, detail="invalid")

        monkeypatch.setattr(authz, "require_api_key", _reject)
        response = TestClient(_build_app()).get(
            "/whoami",
            headers={
                "X-RegEngine-API-Key": "retired-master",
                "X-Tenant-ID": "11111111-1111-1111-1111-111111111111",
            },
        )

        assert response.status_code == 401
        assert len(authz._auth_limiter._mem_failures.get("testclient", [])) == 1

    def test_missing_header_production_returns_401_and_counts_failure(self, _strip_env, monkeypatch):
        monkeypatch.setattr(authz, "_is_dev_env", lambda: False)

        response = TestClient(_build_app()).get("/whoami")

        assert response.status_code == 401
        assert len(authz._auth_limiter._mem_failures.get("testclient", [])) == 1

    def test_missing_header_explicit_dev_uses_dev_open(self, _strip_env, monkeypatch):
        monkeypatch.setattr(authz, "_is_dev_env", lambda: True)

        response = TestClient(_build_app()).get("/whoami")

        assert response.status_code == 200
        assert response.json()["auth_mode"] == "dev_open"

    def test_scoped_key_accepted(self, _strip_env, monkeypatch):
        monkeypatch.setattr(authz, "_is_dev_env", lambda: False)

        async def _accept(request, x_regengine_api_key):
            return SimpleNamespace(
                key_id="scoped-1",
                scopes=["fda.export"],
                tenant_id="tenant-42",
            )

        monkeypatch.setattr(authz, "require_api_key", _accept)
        response = TestClient(_build_app()).get(
            "/whoami",
            headers={"X-RegEngine-API-Key": "scoped"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "key_id": "scoped-1",
            "scopes": ["fda.export"],
            "tenant_id": "tenant-42",
            "auth_mode": "scoped_key",
        }

    def test_invalid_presented_key_never_downgrades_to_dev_open(self, _strip_env, monkeypatch):
        monkeypatch.setattr(authz, "_is_dev_env", lambda: True)

        async def _reject(request, x_regengine_api_key):
            raise HTTPException(status_code=401, detail="invalid")

        monkeypatch.setattr(authz, "require_api_key", _reject)
        response = TestClient(_build_app()).get(
            "/whoami",
            headers={"X-RegEngine-API-Key": "invalid"},
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "invalid"

    def test_auth_backend_503_is_preserved(self, _strip_env, monkeypatch):
        monkeypatch.setattr(authz, "_is_dev_env", lambda: False)

        async def _unavailable(request, x_regengine_api_key):
            raise HTTPException(status_code=503, detail="authentication unavailable")

        monkeypatch.setattr(authz, "require_api_key", _unavailable)
        response = TestClient(_build_app()).get(
            "/whoami",
            headers={"X-RegEngine-API-Key": "candidate"},
        )

        assert response.status_code == 503
        assert authz._auth_limiter._mem_failures.get("testclient", []) == []

    def test_blocked_ip_returns_429(self, _strip_env):
        now = time.time()
        authz._auth_limiter._mem_failures["testclient"] = [now] * authz._AUTH_FAIL_MAX

        response = TestClient(_build_app()).get(
            "/whoami",
            headers={"X-RegEngine-API-Key": "candidate"},
        )

        assert response.status_code == 429

    def test_client_none_uses_unknown_host(self, _strip_env, monkeypatch):
        async def _accept(request, x_regengine_api_key):
            return SimpleNamespace(key_id="scoped", scopes=[], tenant_id="tenant")

        monkeypatch.setattr(authz, "require_api_key", _accept)
        request = MagicMock(spec=Request)
        request.client = None

        import asyncio

        result = asyncio.run(get_ingestion_principal(request, x_regengine_api_key="candidate"))

        assert result.key_id == "scoped"


class TestGetOptionalIngestionPrincipal:
    def test_missing_header_is_anonymous_in_production(self, _strip_env, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "production")
        app = FastAPI()

        from fastapi import Depends

        @app.get("/optional")
        async def _optional(principal=Depends(get_optional_ingestion_principal)):
            return {"principal": principal}

        response = TestClient(app).get("/optional")

        assert response.status_code == 200
        assert response.json() == {"principal": None}

    def test_retired_admin_header_is_rejected_without_entering_public_path(self, _strip_env):
        app = FastAPI()

        from fastapi import Depends

        @app.get("/optional")
        async def _optional(principal=Depends(get_optional_ingestion_principal)):
            return {"principal": principal}

        response = TestClient(app).get(
            "/optional",
            headers={"X-Admin-Key": "retired"},
        )

        assert response.status_code == 401
        assert "X-Admin-Key" in response.json()["detail"]

    @pytest.mark.parametrize("status_code", [401, 403, 429, 503])
    def test_presented_credential_error_is_preserved(self, _strip_env, monkeypatch, status_code):
        async def _reject(request, x_regengine_api_key):
            raise HTTPException(status_code=status_code, detail=f"rejected-{status_code}")

        monkeypatch.setattr(authz, "optional_api_key", _reject)
        app = FastAPI()

        from fastapi import Depends

        @app.get("/optional")
        async def _optional(principal=Depends(get_optional_ingestion_principal)):
            return {"principal": principal}

        response = TestClient(app).get(
            "/optional",
            headers={"X-RegEngine-API-Key": "present"},
        )

        assert response.status_code == status_code
        assert response.json()["detail"] == f"rejected-{status_code}"

# ---------------------------------------------------------------------------
# require_permission
# ---------------------------------------------------------------------------


class TestRequirePermission:
    def _app_with(self, principal, monkeypatch, *, allowed=True):
        app = FastAPI()
        dep = require_permission("fda.export")

        async def _stub_principal():
            return principal

        # Override the captured Depends(get_ingestion_principal) inside dep
        app.dependency_overrides[get_ingestion_principal] = _stub_principal

        consumed: list = []

        def _consume(*, tenant_id, bucket_suffix, limit, window):
            consumed.append((tenant_id, bucket_suffix, limit, window))
            return (allowed, limit - 1 if allowed else 0)

        monkeypatch.setattr(authz, "consume_tenant_rate_limit", _consume)

        from fastapi import Depends

        @app.get("/protected")
        async def _h(p: IngestionPrincipal = Depends(dep)):
            return {"ok": True, "key": p.key_id}

        return app, consumed

    def test_permission_granted(self, monkeypatch):
        p = IngestionPrincipal(key_id="k", scopes=["fda.export"], tenant_id="t")
        app, consumed = self._app_with(p, monkeypatch)
        client = TestClient(app)
        resp = client.get("/protected")
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"]
        assert resp.headers["X-RateLimit-Remaining"]
        assert resp.headers["X-RateLimit-Reset"]
        assert resp.headers["X-RateLimit-Tenant"] == "t"
        assert resp.headers["X-RateLimit-Scope"] == "fda.export"
        assert consumed  # rate limit was consumed
        tenant_id, bucket, limit, window = consumed[0]
        assert tenant_id == "t"
        assert "rbac.fda.export.operator" in bucket
        assert window == 60

    def test_wildcard_scope_grants(self, monkeypatch):
        p = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id="t")
        app, _ = self._app_with(p, monkeypatch)
        client = TestClient(app)
        assert client.get("/protected").status_code == 200

    def test_insufficient_permission_403(self, monkeypatch):
        p = IngestionPrincipal(key_id="k", scopes=["exchange.read"], tenant_id="t")
        app, _ = self._app_with(p, monkeypatch)
        client = TestClient(app)
        resp = client.get("/protected")
        assert resp.status_code == 403
        assert "Insufficient permissions" in resp.json()["detail"]

    def test_cross_tenant_403(self, monkeypatch):
        # Principal tenant t-a but ?tenant_id=t-b, no wildcard
        p = IngestionPrincipal(key_id="k", scopes=["fda.export"], tenant_id="t-a")
        app, _ = self._app_with(p, monkeypatch)
        client = TestClient(app)
        resp = client.get("/protected?tenant_id=t-b")
        assert resp.status_code == 403
        assert "Tenant mismatch" in resp.json()["detail"]

    def test_cross_tenant_header_403(self, monkeypatch):
        p = IngestionPrincipal(key_id="k", scopes=["fda.export"], tenant_id="t-a")
        app, _ = self._app_with(p, monkeypatch)
        client = TestClient(app)
        resp = client.get("/protected", headers={"X-RegEngine-Tenant-ID": "t-b"})
        assert resp.status_code == 403
        assert "Tenant mismatch" in resp.json()["detail"]

    def test_conflicting_query_and_header_400(self, monkeypatch):
        p = IngestionPrincipal(key_id="k", scopes=["fda.export"], tenant_id="t-a")
        app, _ = self._app_with(p, monkeypatch)
        client = TestClient(app)
        resp = client.get("/protected?tenant_id=t-a", headers={"X-Tenant-ID": "t-b"})
        assert resp.status_code == 400
        assert "Conflicting tenant context" in resp.json()["detail"]

    def test_cross_tenant_denied_with_wildcard(self, monkeypatch):
        """A tenant-scoped principal with wildcard ``*`` permission MUST
        still be denied cross-tenant access — wildcard grants action
        breadth, not tenant breadth. Regression for the 2026-05 audit
        finding (authz.py:385). The local-development fallback is unaffected
        because it carries ``tenant_id=None``."""
        p = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id="t-a")
        app, _ = self._app_with(p, monkeypatch)
        client = TestClient(app)
        resp = client.get("/protected?tenant_id=t-b")
        assert resp.status_code == 403
        assert "Tenant mismatch" in resp.json()["detail"]

    def test_same_tenant_wildcard_still_works(self, monkeypatch):
        """Regression guard: removing the wildcard bypass must not break
        same-tenant access for ``*``-scope principals."""
        p = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id="t-a")
        app, _ = self._app_with(p, monkeypatch)
        client = TestClient(app)
        resp = client.get("/protected?tenant_id=t-a")
        assert resp.status_code == 200

    def test_dev_open_principal_cross_tenant_still_allowed(self, monkeypatch):
        """A dev-open principal (tenant_id=None, scopes=['*']) retains
        cross-tenant access — it bypasses the check via the
        ``principal.tenant_id`` guard, not via the wildcard short-circuit
        that the audit removed.

        ``dev_open`` is the only legitimate producer of this shape and is
        gated on an explicit local-development environment.
        """
        p = IngestionPrincipal(
            key_id="dev-open",
            scopes=["*"],
            tenant_id=None,
            auth_mode="dev_open",
        )
        app, _ = self._app_with(p, monkeypatch)
        client = TestClient(app)
        resp = client.get("/protected?tenant_id=any-tenant")
        assert resp.status_code == 200

    def test_same_tenant_query_ok(self, monkeypatch):
        p = IngestionPrincipal(key_id="k", scopes=["fda.export"], tenant_id="t-a")
        app, _ = self._app_with(p, monkeypatch)
        client = TestClient(app)
        resp = client.get("/protected?tenant_id=t-a")
        assert resp.status_code == 200

    def test_no_principal_tenant_query_param_ignored(self, monkeypatch):
        """If principal has no tenant_id, cross-tenant check is skipped."""
        p = IngestionPrincipal(key_id="k", scopes=["fda.export"], tenant_id=None)
        app, _ = self._app_with(p, monkeypatch)
        client = TestClient(app)
        resp = client.get("/protected?tenant_id=anything")
        assert resp.status_code == 200

    def test_rate_limit_exceeded_429(self, monkeypatch):
        p = IngestionPrincipal(key_id="k", scopes=["fda.export"], tenant_id="t")
        app, _ = self._app_with(p, monkeypatch, allowed=False)
        client = TestClient(app)
        resp = client.get("/protected")
        assert resp.status_code == 429
        assert resp.headers["Retry-After"] == "60"
        assert resp.headers["X-RateLimit-Remaining"] == "0"
        assert resp.headers["X-RateLimit-Reset"]
        assert resp.headers["X-RateLimit-Tenant"] == "t"
        assert resp.headers["X-RateLimit-Scope"] == "fda.export"


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


class TestModuleSurface:
    def test_principal_exports(self):
        assert hasattr(authz, "IngestionPrincipal")
        assert hasattr(authz, "get_ingestion_principal")
        assert hasattr(authz, "require_permission")

    def test_auth_fail_window_constants(self):
        assert authz._AUTH_FAIL_WINDOW == 300
        assert authz._AUTH_FAIL_MAX == 15

    def test_action_base_rpm_table(self):
        assert authz._ACTION_BASE_RPM["read"] == 180
        assert authz._ACTION_BASE_RPM["write"] == 90
        assert authz._ACTION_BASE_RPM["ingest"] == 75
        assert authz._ACTION_BASE_RPM["export"] == 90
        assert authz._ACTION_BASE_RPM["verify"] == 45

    def test_role_multipliers(self):
        assert authz._ROLE_MULTIPLIER["viewer"] == 1.0
        assert authz._ROLE_MULTIPLIER["operator"] == 1.5
        assert authz._ROLE_MULTIPLIER["admin"] == 3.0
