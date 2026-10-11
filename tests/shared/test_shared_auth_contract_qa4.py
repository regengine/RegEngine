"""QA deep pass: ``shared.auth`` contract beyond the in-memory keystore.

``tests/shared/test_auth_in_memory_keystore.py`` covers ``APIKeyStore``
create/validate/rate-limit/revoke. This file pins the surrounding
contract that actually fronts HTTP traffic:

1. ``validate_key`` with naive ``expires_at`` (regression: raised
   ``TypeError``, surfaced as a 500 instead of an auth decision).
2. ``verify_jurisdiction_access`` entitlement rules.
3. ``reconcile_tenant_scope`` fail-closed reconciliation.
4. ``get_tenant_id`` header syntax validation.
5. ``validate_auth_config`` strict vs non-strict startup gate.
6. ``require_api_key`` / ``optional_api_key`` HTTP behavior
   (401/403/429, test bypass, workload-key rejection).

Pure Python, no DB, no network. FastAPI ``TestClient`` drives the
dependency-level tests in process.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
import shared.auth as auth_mod
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from shared.auth import (
    APIKey,
    APIKeyStore,
    get_tenant_id,
    optional_api_key,
    reconcile_tenant_scope,
    require_api_key,
    validate_auth_config,
    verify_jurisdiction_access,
)

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def store() -> APIKeyStore:
    return APIKeyStore()


@pytest.fixture(autouse=True)
def _clean_rls_context():
    yield
    from shared.tenant_context import set_rls_tenant_id

    set_rls_tenant_id(None)


# ---------------------------------------------------------------------------
# 1. Naive expires_at regression
# ---------------------------------------------------------------------------


class TestNaiveExpiresAt:
    def test_naive_future_expiry_validates(self, store: APIKeyStore):
        # Naive instant derived from UTC, so the assertion holds in any
        # host timezone. The store treats naive values as UTC.
        naive_future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
        raw, _ = store.create_key(name="naive-future", expires_at=naive_future)
        assert store.validate_key(raw) is not None

    def test_naive_past_expiry_rejected_not_raised(self, store: APIKeyStore):
        naive_past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        raw, _ = store.create_key(name="naive-past", expires_at=naive_past)
        assert store.validate_key(raw) is None

    def test_naive_expiry_inside_one_hour_window(self, store: APIKeyStore):
        # A one-day delta sorts the same way in every real offset, so the
        # cases above pass even if the UTC labeling were wrong. These
        # sub-hour cases pin the naive-as-UTC rule: the instants are past
        # and future in UTC terms regardless of host zone.
        naive_past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=30)
        raw_past, _ = store.create_key(name="naive-past-30m", expires_at=naive_past)
        assert store.validate_key(raw_past) is None
        naive_future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=30)
        raw_future, _ = store.create_key(name="naive-future-30m", expires_at=naive_future)
        assert store.validate_key(raw_future) is not None


# ---------------------------------------------------------------------------
# 2. verify_jurisdiction_access
# ---------------------------------------------------------------------------


def _key(**overrides) -> APIKey:
    base = {
        "key_id": "rge_test",
        "key_hash": "hash",
        "name": "t",
        "created_at": datetime.now(timezone.utc),
        "allowed_jurisdictions": ["US"],
    }
    base.update(overrides)
    return APIKey(**base)


class TestVerifyJurisdictionAccess:
    def test_federal_root_allowed_for_all_tiers(self):
        for root in ("US", "EU", "UK"):
            verify_jurisdiction_access(_key(allowed_jurisdictions=["US"]), root)

    def test_state_without_entitlement_is_403(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            verify_jurisdiction_access(_key(allowed_jurisdictions=["US"]), "US-CA")
        assert exc_info.value.status_code == 403

    def test_state_with_explicit_entitlement_allowed(self):
        verify_jurisdiction_access(_key(allowed_jurisdictions=["US", "US-CA"]), "US-CA")

    def test_municipal_prefix_match_allowed(self):
        verify_jurisdiction_access(_key(allowed_jurisdictions=["US-TX"]), "US-TX-AUS")

    def test_federal_root_does_not_cover_state(self):
        """Entitlement to "US" alone must not open "US-CA"."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            verify_jurisdiction_access(_key(allowed_jurisdictions=["US"]), "US-NY")
        assert exc_info.value.status_code == 403

    def test_sibling_state_not_covered_by_prefix(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            verify_jurisdiction_access(_key(allowed_jurisdictions=["US-CA"]), "US-NY")


# ---------------------------------------------------------------------------
# 3. reconcile_tenant_scope
# ---------------------------------------------------------------------------


class TestReconcileTenantScope:
    def test_matching_scopes_return_authenticated_tenant(self):
        import uuid

        key = _key(tenant_id=TENANT_A)
        assert reconcile_tenant_scope(key, uuid.UUID(TENANT_A)) == TENANT_A

    def test_mismatch_raises_409(self):
        import uuid

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            reconcile_tenant_scope(_key(tenant_id=TENANT_A), uuid.UUID(TENANT_B))
        assert exc_info.value.status_code == 409

    def test_key_without_tenant_raises_403(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            reconcile_tenant_scope(_key(tenant_id=None), TENANT_A)
        assert exc_info.value.status_code == 403

    def test_none_middleware_tenant_still_returns_principal(self):
        assert reconcile_tenant_scope(_key(tenant_id=TENANT_A), None) == TENANT_A


# ---------------------------------------------------------------------------
# 4. get_tenant_id header syntax
# ---------------------------------------------------------------------------


class TestGetTenantId:
    def test_valid_uuid_passes_through(self):
        assert get_tenant_id(TENANT_A) == TENANT_A

    def test_missing_header_is_400(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            get_tenant_id(None)
        assert exc_info.value.status_code == 400

    def test_malformed_uuid_is_400(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            get_tenant_id("not-a-uuid")
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# 5. validate_auth_config
# ---------------------------------------------------------------------------


_STRICT_ENV = {
    "REGENGINE_ENV": "production",
    "AUTH_SECRET_KEY": "a-long-enough-test-secret-value",
    "TOOL_ACCESS_SECRET": "another-long-enough-secret",
}


def _set_strict_env(monkeypatch: pytest.MonkeyPatch, **overrides):
    from shared.env import CLOUD_ENV_VARS

    for var in CLOUD_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("AUTH_TEST_BYPASS_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    for key, value in {**_STRICT_ENV, **overrides}.items():
        monkeypatch.setenv(key, value)


class TestValidateAuthConfig:
    def test_healthy_strict_config_passes(self, monkeypatch):
        _set_strict_env(monkeypatch)
        validate_auth_config()

    def test_missing_secret_raises_in_strict(self, monkeypatch):
        _set_strict_env(monkeypatch)
        monkeypatch.delenv("AUTH_SECRET_KEY", raising=False)
        monkeypatch.delenv("JWT_SECRET", raising=False)
        with pytest.raises(RuntimeError, match="Auth config validation failed"):
            validate_auth_config()

    def test_missing_secret_only_warns_outside_strict(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "test")
        monkeypatch.delenv("AUTH_SECRET_KEY", raising=False)
        monkeypatch.delenv("JWT_SECRET", raising=False)
        # validate_auth_config also consults CI markers, so clear them:
        # otherwise a dropped strict check could hide behind `not is_ci`.
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("CI", raising=False)
        validate_auth_config()

    def test_known_default_secret_raises_in_strict(self, monkeypatch):
        _set_strict_env(monkeypatch, AUTH_SECRET_KEY="dev_secret_key_change_me")
        with pytest.raises(RuntimeError, match="known default"):
            validate_auth_config()

    def test_bypass_token_raises_in_strict(self, monkeypatch):
        _set_strict_env(monkeypatch, AUTH_TEST_BYPASS_TOKEN="some-token")
        with pytest.raises(RuntimeError, match="AUTH_TEST_BYPASS_TOKEN"):
            validate_auth_config()


# ---------------------------------------------------------------------------
# 6. require_api_key / optional_api_key over HTTP
# ---------------------------------------------------------------------------


def _auth_app(key_store: APIKeyStore) -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    async def protected(key=Depends(require_api_key)):
        return {"key_id": key.key_id, "tenant_id": str(key.tenant_id)}

    @app.get("/maybe")
    async def maybe(key=Depends(optional_api_key)):
        if key is None:
            return {"anonymous": True}
        return {"key_id": key.key_id}

    return app


@pytest.fixture
def http_store(monkeypatch) -> APIKeyStore:
    """Route ``get_key_store`` at a fresh isolated store for HTTP tests."""
    fresh = APIKeyStore()
    monkeypatch.setattr(auth_mod, "_key_store", fresh)
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.delenv("ENABLE_DB_API_KEYS", raising=False)
    monkeypatch.delenv("REGENGINE_AUTH_STRICT", raising=False)
    return fresh


class TestRequireApiKeyHttp:
    def test_missing_key_is_401(self, http_store: APIKeyStore):
        resp = TestClient(_auth_app(http_store)).get("/protected")
        assert resp.status_code == 401

    def test_invalid_key_is_401(self, http_store: APIKeyStore):
        resp = TestClient(_auth_app(http_store)).get(
            "/protected", headers={"X-RegEngine-API-Key": "rge_bogus.secret"}
        )
        assert resp.status_code == 401

    def test_valid_key_reaches_handler(self, http_store: APIKeyStore):
        raw, _ = http_store.create_key(name="web", tenant_id=TENANT_A)
        resp = TestClient(_auth_app(http_store)).get(
            "/protected", headers={"X-RegEngine-API-Key": raw}
        )
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == TENANT_A

    def test_tenantless_key_rejected_with_403(self, http_store: APIKeyStore):
        raw, _ = http_store.create_key(name="workload", tenant_id=None)
        resp = TestClient(_auth_app(http_store)).get(
            "/protected", headers={"X-RegEngine-API-Key": raw}
        )
        assert resp.status_code == 403

    def test_internal_scoped_key_rejected_with_403(self, http_store: APIKeyStore):
        raw, _ = http_store.create_key(
            name="internal", tenant_id=TENANT_A, scopes=["internal.provision"]
        )
        resp = TestClient(_auth_app(http_store)).get(
            "/protected", headers={"X-RegEngine-API-Key": raw}
        )
        assert resp.status_code == 403

    def test_rate_limit_exceeded_is_429_with_retry_after(self, http_store: APIKeyStore):
        raw, _ = http_store.create_key(name="tight", tenant_id=TENANT_A, rate_limit_per_minute=2)
        client = TestClient(_auth_app(http_store))
        headers = {"X-RegEngine-API-Key": raw}
        assert client.get("/protected", headers=headers).status_code == 200
        assert client.get("/protected", headers=headers).status_code == 200
        resp = client.get("/protected", headers=headers)
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_revoked_key_is_401(self, http_store: APIKeyStore):
        raw, key = http_store.create_key(name="doomed", tenant_id=TENANT_A)
        assert http_store.revoke_key(key.key_id) is True
        resp = TestClient(_auth_app(http_store)).get(
            "/protected", headers={"X-RegEngine-API-Key": raw}
        )
        assert resp.status_code == 401

    def test_test_bypass_reaches_handler(self, http_store: APIKeyStore, monkeypatch):
        token = os.getenv("AUTH_TEST_BYPASS_TOKEN", "test-bypass-ci-only-not-for-production")
        monkeypatch.setenv("AUTH_TEST_BYPASS_TOKEN", token)
        monkeypatch.setenv("REGENGINE_ENV", "test")
        resp = TestClient(_auth_app(http_store)).get(
            "/protected", headers={"X-RegEngine-API-Key": token}
        )
        assert resp.status_code == 200


class TestOptionalApiKeyHttp:
    def test_absent_header_is_anonymous(self, http_store: APIKeyStore):
        resp = TestClient(_auth_app(http_store)).get("/maybe")
        assert resp.status_code == 200
        assert resp.json() == {"anonymous": True}

    def test_invalid_presented_key_is_401_not_anonymous(self, http_store: APIKeyStore):
        """A presented but bad credential must not downgrade to anonymous."""
        resp = TestClient(_auth_app(http_store)).get(
            "/maybe", headers={"X-RegEngine-API-Key": "rge_bogus.secret"}
        )
        assert resp.status_code == 401

    def test_valid_key_is_identified(self, http_store: APIKeyStore):
        raw, key = http_store.create_key(name="opt", tenant_id=TENANT_A)
        resp = TestClient(_auth_app(http_store)).get(
            "/maybe", headers={"X-RegEngine-API-Key": raw}
        )
        assert resp.status_code == 200
        assert resp.json()["key_id"] == key.key_id

    def test_api_key_principal_seeds_request_state(self, http_store: APIKeyStore):
        """The accepted key must seed tenant resolution downstream: the real
        ``resolve_tenant_context`` funnel reads it off request state."""
        from shared.tenant_context import TenantContext, resolve_tenant_context

        app = FastAPI()

        @app.get("/probe")
        async def probe(
            key: APIKey = Depends(require_api_key),
            ctx: TenantContext = Depends(resolve_tenant_context),
        ):
            return {"key_id": key.key_id, "tenant_id": ctx.tenant_id}

        raw, key = http_store.create_key(name="probe", tenant_id=TENANT_A)
        resp = TestClient(app).get("/probe", headers={"X-RegEngine-API-Key": raw})
        assert resp.status_code == 200
        assert resp.json() == {"key_id": key.key_id, "tenant_id": TENANT_A}


def test_reconcile_after_http_auth_rejects_cross_tenant_assertion(http_store: APIKeyStore):
    """End to end tenant isolation: credential tenant A plus a middleware
    tenant B must fail closed with 409, never serve B."""
    import uuid

    app = FastAPI()

    @app.get("/records")
    async def records(key: APIKey = Depends(require_api_key)):
        tenant = reconcile_tenant_scope(key, uuid.UUID(TENANT_B), request_path="/records")
        return {"tenant": tenant}

    raw, _ = http_store.create_key(name="cross", tenant_id=TENANT_A)
    resp = TestClient(app).get("/records", headers={"X-RegEngine-API-Key": raw})
    assert resp.status_code == 409
