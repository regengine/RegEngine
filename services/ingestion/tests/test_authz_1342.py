"""Coverage for app/authz.py — ingestion service authorization.

Locks:
- IP auth-failure rate limiting (15-failure / 5-minute window)
- Production detection via REGENGINE_ENV / ENV / DATABASE_URL heuristics
- IngestionPrincipal Pydantic defaults
- Permission normalization and RBAC role → rate-limit multiplier
- Per-scope RPM overrides via INGESTION_RBAC_RATE_LIMITS
- Tenant resolution chain: principal.tenant_id → X-Tenant-ID → ?tenant_id → "global"
- DB fallback key lookup (disabled/expired/no-row/exception)
- get_ingestion_principal branches (legacy master, scoped key, DB fallback, dev-open)
- require_permission: insufficient perm 403, cross-tenant 403, rate-limit 429

Issue: #1342
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import authz
from app.authz import (
    IngestionPrincipal,
    _check_auth_rate_limit,
    _is_production_env,
    _lookup_scoped_key_from_db,
    _normalize_permission,
    _principal_from_api_key,
    _principal_rate_limit_role,
    _rate_limit_overrides,
    _rate_limit_window_seconds,
    _record_auth_failure,
    _rpm_for_permission,
    _tenant_for_rate_limit,
    get_ingestion_principal,
    require_permission,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_auth_failures():
    """Strip the module-level IP→failures dict between tests."""
    with authz._auth_failures_lock:
        authz._auth_failures.clear()
    yield
    with authz._auth_failures_lock:
        authz._auth_failures.clear()


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
        "REGENGINE_ENV", "ENV", "DATABASE_URL",
        "INGESTION_RBAC_RATE_LIMITS",
        "INGESTION_RBAC_RATE_LIMIT_DEFAULT_RPM",
        "INGESTION_RBAC_RATE_LIMIT_WINDOW_SECONDS",
        "REGENGINE_API_KEY",
        "API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# _check_auth_rate_limit / _record_auth_failure
# ---------------------------------------------------------------------------


class TestAuthFailureRateLimit:
    def test_record_adds_timestamp(self):
        _record_auth_failure("1.2.3.4")
        assert len(authz._auth_failures["1.2.3.4"]) == 1

    def test_record_accumulates(self):
        for _ in range(5):
            _record_auth_failure("1.2.3.4")
        assert len(authz._auth_failures["1.2.3.4"]) == 5

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
        authz._auth_failures["1.2.3.4"] = [old] * authz._AUTH_FAIL_MAX
        # Even though 15 timestamps exist, all are stale → not blocked
        _check_auth_rate_limit("1.2.3.4")
        assert authz._auth_failures["1.2.3.4"] == []

    def test_check_unseen_ip_ok(self):
        _check_auth_rate_limit("8.8.8.8")  # no state → no raise


# ---------------------------------------------------------------------------
# _is_production_env
# ---------------------------------------------------------------------------


class TestIsProductionEnv:
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

    def test_all_unset_returns_false(self, _strip_env):
        assert _is_production_env() is False

    def test_dev_env_returns_false(self, _strip_env, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "development")
        monkeypatch.setenv("ENV", "staging")
        monkeypatch.setenv("DATABASE_URL", "postgres://localhost:5432/db")
        assert _is_production_env() is False


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
            auth_mode="legacy_master",
        )
        assert p.scopes == ["fda.export"]
        assert p.tenant_id == "t1"
        assert p.auth_mode == "legacy_master"


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
        monkeypatch.setenv(
            "INGESTION_RBAC_RATE_LIMITS", "fda.export=60,exchange.read=240"
        )
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


def _fake_request(tenant_header=None, tenant_query=None, client_host="1.1.1.1"):
    headers = {}
    if tenant_header is not None:
        headers["X-Tenant-ID"] = tenant_header
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

    def test_query_fallback(self):
        p = IngestionPrincipal(key_id="k")
        req = _fake_request(tenant_query="query-t")
        assert _tenant_for_rate_limit(req, p) == "query-t"

    def test_global_default(self):
        p = IngestionPrincipal(key_id="k")
        req = _fake_request()
        assert _tenant_for_rate_limit(req, p) == "global"


# ---------------------------------------------------------------------------
# _principal_from_api_key
# ---------------------------------------------------------------------------


class TestPrincipalFromApiKey:
    def test_maps_all_fields(self):
        api_key = SimpleNamespace(
            key_id="k-1", scopes=["fda.export"], tenant_id="t-1"
        )
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
# _lookup_scoped_key_from_db
# ---------------------------------------------------------------------------


class _FakeSession:
    def __init__(self, row):
        self._row = row
        self.closed = False
        self.execute_calls = []

    def execute(self, stmt, params):
        self.execute_calls.append((stmt, params))
        return SimpleNamespace(fetchone=lambda: self._row)

    def close(self):
        self.closed = True


class _SessionFactory:
    def __init__(self, row):
        self._row = row
        self.last = None

    def __call__(self):
        self.last = _FakeSession(self._row)
        return self.last


class TestLookupScopedKeyFromDb:
    def test_row_found(self, monkeypatch):
        row = ("k-id", "t-id", ["fda.read"], True, None)
        factory = _SessionFactory(row)
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", factory)
        result = _lookup_scoped_key_from_db("raw-key")
        assert result is not None
        assert result.key_id == "k-id"
        assert result.tenant_id == "t-id"
        assert result.auth_mode == "scoped_key_db_fallback"
        assert factory.last.closed is True

    def test_no_row_returns_none(self, monkeypatch):
        factory = _SessionFactory(None)
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", factory)
        assert _lookup_scoped_key_from_db("raw") is None
        assert factory.last.closed is True

    def test_disabled_key_returns_none(self, monkeypatch):
        row = ("k", "t", [], False, None)
        factory = _SessionFactory(row)
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", factory)
        assert _lookup_scoped_key_from_db("raw") is None

    def test_expired_key_returns_none(self, monkeypatch):
        expired = datetime.now(timezone.utc) - timedelta(days=1)
        row = ("k", "t", [], True, expired)
        factory = _SessionFactory(row)
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", factory)
        assert _lookup_scoped_key_from_db("raw") is None

    def test_future_expiry_ok(self, monkeypatch):
        future = datetime.now(timezone.utc) + timedelta(days=30)
        row = ("k", "t", ["x"], True, future)
        factory = _SessionFactory(row)
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", factory)
        result = _lookup_scoped_key_from_db("raw")
        assert result is not None
        assert result.tenant_id == "t"

    def test_no_tenant_id(self, monkeypatch):
        row = ("k", None, ["*"], True, None)
        factory = _SessionFactory(row)
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", factory)
        result = _lookup_scoped_key_from_db("raw")
        assert result.tenant_id is None

    def test_none_scopes_normalizes(self, monkeypatch):
        row = ("k", "t", None, True, None)
        factory = _SessionFactory(row)
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", factory)
        result = _lookup_scoped_key_from_db("raw")
        assert result.scopes == []

    def test_exception_returns_none(self, monkeypatch):
        def _boom():
            raise RuntimeError("DB down")
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", _boom)
        assert _lookup_scoped_key_from_db("raw") is None

    def test_exception_in_execute_still_closes(self, monkeypatch):
        class _ExplodingSession:
            def __init__(self):
                self.closed = False
            def execute(self, *a, **k):
                raise RuntimeError("bad query")
            def close(self):
                self.closed = True

        session = _ExplodingSession()
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", lambda: session)
        assert _lookup_scoped_key_from_db("raw") is None
        assert session.closed is True


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
    def test_legacy_master_key_accepted(self, _strip_env, monkeypatch):
        from app import config as cfg
        cfg.get_settings.cache_clear()
        monkeypatch.setenv("API_KEY", "master-secret")
        app = _build_app()
        client = TestClient(app)
        resp = client.get(
            "/whoami",
            headers={
                "X-RegEngine-API-Key": "master-secret",
                "X-Tenant-ID": "11111111-2222-3333-4444-555555555555",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["auth_mode"] == "legacy_master"
        assert "*" in resp.json()["scopes"]
        assert resp.json()["tenant_id"] == "11111111-2222-3333-4444-555555555555"

    def test_regengine_master_key_accepted(self, _strip_env, monkeypatch):
        from app import config as cfg
        cfg.get_settings.cache_clear()
        monkeypatch.setenv("REGENGINE_API_KEY", "master-secret")
        app = _build_app()
        client = TestClient(app)
        resp = client.get(
            "/whoami",
            headers={
                "X-RegEngine-API-Key": "master-secret",
                "X-Tenant-ID": "11111111-2222-3333-4444-555555555555",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["auth_mode"] == "legacy_master"
        assert resp.json()["tenant_id"] == "11111111-2222-3333-4444-555555555555"

    def test_missing_header_with_api_key_returns_401(
        self, _strip_env, monkeypatch
    ):
        from app import config as cfg
        cfg.get_settings.cache_clear()
        monkeypatch.setenv("API_KEY", "master-secret")
        app = _build_app()
        client = TestClient(app)
        resp = client.get("/whoami")
        assert resp.status_code == 401
        # Failure was recorded
        assert len(authz._auth_failures.get("testclient", [])) == 1

    def test_invalid_header_falls_through_to_require_then_db_then_401(
        self, _strip_env, monkeypatch
    ):
        from app import config as cfg
        cfg.get_settings.cache_clear()
        monkeypatch.setenv("API_KEY", "master-secret")

        async def _fake_require(request, x_regengine_api_key):
            raise HTTPException(status_code=401, detail="bad")

        monkeypatch.setattr(authz, "require_api_key", _fake_require)
        monkeypatch.setattr(authz, "_lookup_scoped_key_from_db", lambda raw: None)

        app = _build_app()
        client = TestClient(app)
        resp = client.get("/whoami", headers={"X-RegEngine-API-Key": "wrong"})
        assert resp.status_code == 401

    def test_scoped_key_accepted(self, _strip_env, monkeypatch):
        from app import config as cfg
        cfg.get_settings.cache_clear()
        monkeypatch.setenv("API_KEY", "master-secret")

        async def _fake_require(request, x_regengine_api_key):
            return SimpleNamespace(
                key_id="scoped-1",
                scopes=["fda.export"],
                tenant_id="t-42",
            )

        monkeypatch.setattr(authz, "require_api_key", _fake_require)
        app = _build_app()
        client = TestClient(app)
        resp = client.get("/whoami", headers={"X-RegEngine-API-Key": "scoped"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["key_id"] == "scoped-1"
        assert body["auth_mode"] == "scoped_key"

    def test_require_raises_but_db_fallback_succeeds(self, _strip_env, monkeypatch):
        from app import config as cfg
        cfg.get_settings.cache_clear()
        monkeypatch.setenv("API_KEY", "master-secret")

        async def _fake_require(request, x_regengine_api_key):
            raise HTTPException(status_code=401, detail="no")

        monkeypatch.setattr(authz, "require_api_key", _fake_require)
        monkeypatch.setattr(
            authz,
            "_lookup_scoped_key_from_db",
            lambda raw: IngestionPrincipal(
                key_id="db-1",
                scopes=["exchange.read"],
                tenant_id="t-db",
                auth_mode="scoped_key_db_fallback",
            ),
        )
        app = _build_app()
        client = TestClient(app)
        resp = client.get("/whoami", headers={"X-RegEngine-API-Key": "db-key"})
        assert resp.status_code == 200
        assert resp.json()["auth_mode"] == "scoped_key_db_fallback"

    def test_no_api_key_configured_no_header_dev_open(
        self, _strip_env, monkeypatch
    ):
        from app import config as cfg
        cfg.get_settings.cache_clear()
        # API_KEY stripped via _strip_env
        monkeypatch.setattr(authz, "_is_production_env", lambda: False)
        app = _build_app()
        client = TestClient(app)
        resp = client.get("/whoami")
        assert resp.status_code == 200
        assert resp.json()["auth_mode"] == "dev_open"

    def test_no_api_key_configured_no_header_production_401(
        self, _strip_env, monkeypatch
    ):
        from app import config as cfg
        cfg.get_settings.cache_clear()
        monkeypatch.setattr(authz, "_is_production_env", lambda: True)
        app = _build_app()
        client = TestClient(app)
        resp = client.get("/whoami")
        assert resp.status_code == 401

    def test_no_api_key_header_present_scoped_key_works(
        self, _strip_env, monkeypatch
    ):
        from app import config as cfg
        cfg.get_settings.cache_clear()
        monkeypatch.setattr(authz, "_is_production_env", lambda: False)

        async def _fake_require(request, x_regengine_api_key):
            return SimpleNamespace(
                key_id="s-1", scopes=["fda.read"], tenant_id="t"
            )

        monkeypatch.setattr(authz, "require_api_key", _fake_require)
        app = _build_app()
        client = TestClient(app)
        resp = client.get(
            "/whoami", headers={"X-RegEngine-API-Key": "scoped-xyz"}
        )
        assert resp.status_code == 200
        assert resp.json()["key_id"] == "s-1"

    def test_no_api_key_header_present_require_fails_db_fallback(
        self, _strip_env, monkeypatch
    ):
        from app import config as cfg
        cfg.get_settings.cache_clear()
        monkeypatch.setattr(authz, "_is_production_env", lambda: False)

        async def _fake_require(request, x_regengine_api_key):
            raise HTTPException(status_code=401, detail="no")

        monkeypatch.setattr(authz, "require_api_key", _fake_require)
        monkeypatch.setattr(
            authz,
            "_lookup_scoped_key_from_db",
            lambda raw: IngestionPrincipal(
                key_id="db-x", scopes=["fda.read"], tenant_id="t",
                auth_mode="scoped_key_db_fallback",
            ),
        )
        app = _build_app()
        client = TestClient(app)
        resp = client.get("/whoami", headers={"X-RegEngine-API-Key": "x"})
        assert resp.status_code == 200
        assert resp.json()["auth_mode"] == "scoped_key_db_fallback"

    def test_no_api_key_header_present_both_fail_dev_open(
        self, _strip_env, monkeypatch
    ):
        from app import config as cfg
        cfg.get_settings.cache_clear()
        monkeypatch.setattr(authz, "_is_production_env", lambda: False)

        async def _fake_require(request, x_regengine_api_key):
            raise HTTPException(status_code=401, detail="no")

        monkeypatch.setattr(authz, "require_api_key", _fake_require)
        monkeypatch.setattr(authz, "_lookup_scoped_key_from_db", lambda raw: None)

        app = _build_app()
        client = TestClient(app)
        resp = client.get("/whoami", headers={"X-RegEngine-API-Key": "x"})
        assert resp.status_code == 200
        assert resp.json()["auth_mode"] == "dev_open"

    def test_no_api_key_header_present_both_fail_production_401(
        self, _strip_env, monkeypatch
    ):
        from app import config as cfg
        cfg.get_settings.cache_clear()
        monkeypatch.setattr(authz, "_is_production_env", lambda: True)

        async def _fake_require(request, x_regengine_api_key):
            raise HTTPException(status_code=401, detail="no")

        monkeypatch.setattr(authz, "require_api_key", _fake_require)
        monkeypatch.setattr(authz, "_lookup_scoped_key_from_db", lambda raw: None)

        app = _build_app()
        client = TestClient(app)
        resp = client.get("/whoami", headers={"X-RegEngine-API-Key": "x"})
        assert resp.status_code == 401

    def test_blocked_ip_returns_429(self, _strip_env, monkeypatch):
        from app import config as cfg
        cfg.get_settings.cache_clear()
        monkeypatch.setenv("API_KEY", "master-secret")

        # Pre-populate the failure log past threshold for the TestClient IP
        now = time.time()
        with authz._auth_failures_lock:
            authz._auth_failures["testclient"] = [now] * authz._AUTH_FAIL_MAX

        app = _build_app()
        client = TestClient(app)
        resp = client.get("/whoami", headers={"X-RegEngine-API-Key": "x"})
        assert resp.status_code == 429

    def test_client_none_uses_unknown_host(self, _strip_env, monkeypatch):
        """Hit the `request.client is None → 'unknown'` branch directly."""
        from app import config as cfg
        cfg.get_settings.cache_clear()
        monkeypatch.setenv("API_KEY", "master-secret")

        async def _fake_require(request, x_regengine_api_key):
            return SimpleNamespace(key_id="k", scopes=[], tenant_id=None)

        monkeypatch.setattr(authz, "require_api_key", _fake_require)

        req = MagicMock(spec=Request)
        req.client = None
        import asyncio
        result = asyncio.run(
            get_ingestion_principal(req, x_regengine_api_key="anything")
        )
        assert result.key_id == "k"


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
        p = IngestionPrincipal(
            key_id="k", scopes=["fda.export"], tenant_id="t-a"
        )
        app, _ = self._app_with(p, monkeypatch)
        client = TestClient(app)
        resp = client.get("/protected?tenant_id=t-b")
        assert resp.status_code == 403
        assert "Tenant mismatch" in resp.json()["detail"]

    def test_cross_tenant_allowed_with_wildcard(self, monkeypatch):
        p = IngestionPrincipal(
            key_id="k", scopes=["*"], tenant_id="t-a"
        )
        app, _ = self._app_with(p, monkeypatch)
        client = TestClient(app)
        resp = client.get("/protected?tenant_id=t-b")
        assert resp.status_code == 200

    def test_same_tenant_query_ok(self, monkeypatch):
        p = IngestionPrincipal(
            key_id="k", scopes=["fda.export"], tenant_id="t-a"
        )
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
        p = IngestionPrincipal(
            key_id="k", scopes=["fda.export"], tenant_id="t"
        )
        app, _ = self._app_with(p, monkeypatch, allowed=False)
        client = TestClient(app)
        resp = client.get("/protected")
        assert resp.status_code == 429
        assert resp.headers["Retry-After"] == "60"
        assert resp.headers["X-RateLimit-Remaining"] == "0"
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
