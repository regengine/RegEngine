"""Unit tests for ``services/shared/auth.py`` FastAPI surface — issue #1338.

This file complements three existing focused suites that already cover most
of ``auth.py``:

- ``services/shared/tests/test_auth_fail_closed.py`` — startup
  ``validate_auth_config`` env var checks (subprocess, so module-import-time
  failures actually fire).
- ``services/shared/tests/test_auth_preshared_tenant_required_1068.py`` —
  pins the master-key / X-Tenant-ID fail-closed contract.
- ``tests/shared/test_auth_in_memory_keystore.py`` — covers the in-memory
  ``APIKeyStore`` (create / validate / rate-limit / revoke / list / hash).

Issue #1338 calls out auth.py / canonical_event.py / external_connectors as
the three shared-kernel modules with no dedicated tests. After the in-memory
keystore suite landed, the remaining uncovered surface in auth.py was the
FastAPI dependency layer:

- ``get_key_store`` selector (dev/test vs production cache).
- ``require_api_key`` test-bypass branch and the in-memory + DB store async
  branches (success / 401 / 429).
- ``optional_api_key`` (no-key returns None vs invalid-key re-raises).
- ``verify_jurisdiction_access`` entitlement matrix (federal vs sub-region).
- ``init_demo_keys`` smoke test.
- ``get_tenant_id`` UUID validator.

This file fills those gaps. The other two modules listed in #1338
(``canonical_event.py`` and ``external_connectors``) are tracked as
follow-up — one shared-lib module per PR.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------
# auth.py imports ``from shared.api_key_store import ...`` so we need the
# ``services/`` directory on sys.path before loading it. Reuse the canonical
# ``shared.auth`` module name so coverage attributes lines correctly even
# when this file is run in isolation.

_shared_dir = Path(__file__).resolve().parent.parent
_services_dir = _shared_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

if "shared.auth" in sys.modules:
    auth = sys.modules["shared.auth"]
else:
    _spec = importlib.util.spec_from_file_location(
        "shared.auth", _shared_dir / "auth.py"
    )
    auth = importlib.util.module_from_spec(_spec)
    sys.modules["shared.auth"] = auth
    _spec.loader.exec_module(auth)

APIKey = auth.APIKey
APIKeyStore = auth.APIKeyStore
require_api_key = auth.require_api_key
optional_api_key = auth.optional_api_key
verify_jurisdiction_access = auth.verify_jurisdiction_access
init_demo_keys = auth.init_demo_keys
get_tenant_id = auth.get_tenant_id
get_key_store = auth.get_key_store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TENANT_UUID = "11111111-2222-3333-4444-555555555555"


def _make_request(headers: dict[str, str] | None = None, path: str = "/x") -> MagicMock:
    """Build a minimal MagicMock FastAPI Request used by require_api_key."""
    req = MagicMock()
    req.headers = headers or {}
    req.url.path = path
    req.method = "GET"
    return req


def _run(coro):
    """Run an async coroutine synchronously inside a sync test."""
    return asyncio.run(coro)


def _make_db_store_stub(*, validate_return=None, rate_limit_return=None):
    """Create a real ``DatabaseAPIKeyStore`` subclass instance with stubs.

    ``require_api_key`` uses ``isinstance(key_store, DatabaseAPIKeyStore)``
    to decide which branch to take, so a plain MagicMock won't work. We
    build the instance via ``object.__new__`` to bypass __init__ (which
    would otherwise demand a real ``DATABASE_URL``).
    """
    instance = object.__new__(auth.DatabaseAPIKeyStore)
    instance.validate_key = AsyncMock(return_value=validate_return)
    instance.check_rate_limit = AsyncMock(return_value=rate_limit_return)
    return instance


@pytest.fixture(autouse=True)
def _clean_auth_env(monkeypatch):
    """Strip auth-related env vars so each test starts from a known-clean slate."""
    for var in (
        "API_KEY",
        "REGENGINE_API_KEY",
        "AUTH_TEST_BYPASS_TOKEN",
        "AUTH_TEST_BYPASS_TENANT_ID",
        "REGENGINE_ENV",
        "ENABLE_DB_API_KEYS",
    ):
        monkeypatch.delenv(var, raising=False)
    yield


# ---------------------------------------------------------------------------
# get_key_store selector
# ---------------------------------------------------------------------------


class TestGetKeyStore:
    """Returns DB store in production / when ENABLE_DB_API_KEYS=true, else in-memory."""

    def test_dev_returns_in_memory(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "development")
        assert isinstance(get_key_store(), APIKeyStore)

    def test_test_env_returns_in_memory(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "test")
        assert isinstance(get_key_store(), APIKeyStore)

    def test_production_returns_db_store(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "production")
        sentinel = _make_db_store_stub()
        # Pre-seed the cached instance so we don't hit the real DB constructor.
        monkeypatch.setattr(auth, "_db_store_instance", sentinel)
        assert get_key_store() is sentinel
        # Cached on second call.
        assert get_key_store() is sentinel

    def test_enable_db_api_keys_overrides_dev(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "development")
        monkeypatch.setenv("ENABLE_DB_API_KEYS", "true")
        sentinel = _make_db_store_stub()
        monkeypatch.setattr(auth, "_db_store_instance", sentinel)
        assert get_key_store() is sentinel


# ---------------------------------------------------------------------------
# require_api_key — header handling
# ---------------------------------------------------------------------------


class TestRequireApiKeyMissingHeader:
    def test_missing_header_returns_401(self):
        with pytest.raises(HTTPException) as exc:
            _run(require_api_key(_make_request(), None))
        assert exc.value.status_code == 401
        assert "Missing API key" in exc.value.detail
        assert exc.value.headers["WWW-Authenticate"] == "ApiKey"


# ---------------------------------------------------------------------------
# require_api_key — AUTH_TEST_BYPASS_TOKEN behaviour
# ---------------------------------------------------------------------------


class TestRequireApiKeyBypass:
    """AUTH_TEST_BYPASS_TOKEN works in dev/test, must fail closed in production."""

    def test_bypass_active_in_development(self, monkeypatch):
        monkeypatch.setenv("AUTH_TEST_BYPASS_TOKEN", "let-me-in")
        monkeypatch.setenv("REGENGINE_ENV", "development")
        result = _run(require_api_key(_make_request(), "let-me-in"))
        assert isinstance(result, APIKey)
        assert result.key_id == "test"
        assert result.billing_tier == "ENTERPRISE"
        # Default tenant when AUTH_TEST_BYPASS_TENANT_ID isn't overridden.
        assert result.tenant_id == "11111111-1111-1111-1111-111111111111"
        assert "admin" in result.scopes

    def test_bypass_uses_overridden_tenant_id(self, monkeypatch):
        monkeypatch.setenv("AUTH_TEST_BYPASS_TOKEN", "let-me-in")
        monkeypatch.setenv("REGENGINE_ENV", "test")
        monkeypatch.setenv("AUTH_TEST_BYPASS_TENANT_ID", _VALID_TENANT_UUID)
        result = _run(require_api_key(_make_request(), "let-me-in"))
        assert result.tenant_id == _VALID_TENANT_UUID

    def test_bypass_blocked_when_token_does_not_match(self, monkeypatch):
        """Wrong bypass value falls through and is rejected by the keystore path."""
        monkeypatch.setenv("AUTH_TEST_BYPASS_TOKEN", "let-me-in")
        monkeypatch.setenv("REGENGINE_ENV", "development")
        with pytest.raises(HTTPException) as exc:
            _run(require_api_key(_make_request(), "wrong-token"))
        assert exc.value.status_code == 401

    def test_bypass_blocked_in_production(self, monkeypatch):
        """Bypass token + production env must NOT auto-authenticate."""
        monkeypatch.setenv("AUTH_TEST_BYPASS_TOKEN", "let-me-in")
        monkeypatch.setenv("REGENGINE_ENV", "production")
        instance = _make_db_store_stub(validate_return=None)
        monkeypatch.setattr(auth, "_db_store_instance", instance)
        with pytest.raises(HTTPException) as exc:
            _run(require_api_key(_make_request(), "let-me-in"))
        assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# require_api_key — preshared master key happy path
# ---------------------------------------------------------------------------


class TestRequireApiKeyPresharedHappyPath:
    """The fail-closed master-key/tenant cases are pinned in #1068's suite —
    here we just smoke-test the happy path so we don't drift on the env var
    aliases (API_KEY vs REGENGINE_API_KEY)."""

    def test_master_key_with_valid_tenant_returns_principal(self, monkeypatch):
        master = "configured-master-key-with-enough-entropy"
        monkeypatch.setenv("API_KEY", master)
        monkeypatch.setenv("REGENGINE_ENV", "production")
        result = _run(require_api_key(
            _make_request(headers={"x-tenant-id": _VALID_TENANT_UUID}),
            master,
        ))
        assert isinstance(result, APIKey)
        assert result.key_id == "preshared-master"
        assert result.tenant_id == _VALID_TENANT_UUID
        assert result.billing_tier == "ENTERPRISE"

    def test_regengine_api_key_env_var_is_also_honored(self, monkeypatch):
        master = "configured-via-regengine-api-key-env-var"
        monkeypatch.setenv("REGENGINE_API_KEY", master)
        monkeypatch.setenv("REGENGINE_ENV", "production")
        result = _run(require_api_key(
            _make_request(headers={"x-tenant-id": _VALID_TENANT_UUID}),
            master,
        ))
        assert result.key_id == "preshared-master"


# ---------------------------------------------------------------------------
# require_api_key — in-memory store branch
# ---------------------------------------------------------------------------


class TestRequireApiKeyInMemoryStoreBranch:
    """Header doesn't match master, env is dev -> in-memory store path."""

    def test_in_memory_validate_success(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "development")
        store = auth._key_store
        raw, meta = store.create_key(name="dev-key", rate_limit_per_minute=10)
        try:
            result = _run(require_api_key(_make_request(), raw))
            assert isinstance(result, APIKey)
            assert result.key_id == meta.key_id
        finally:
            store._keys.pop(meta.key_id, None)
            store._rate_limits.pop(meta.key_id, None)

    def test_in_memory_validate_failure_returns_401(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "development")
        with pytest.raises(HTTPException) as exc:
            _run(require_api_key(_make_request(), "rge_bogus.secretpart"))
        assert exc.value.status_code == 401
        assert "Invalid API key" in exc.value.detail

    def test_in_memory_rate_limit_exceeded(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "development")
        store = auth._key_store
        raw, meta = store.create_key(name="rl-key", rate_limit_per_minute=1)
        try:
            # First request consumes the entire quota.
            _run(require_api_key(_make_request(), raw))
            # Second must trip the limiter.
            with pytest.raises(HTTPException) as exc:
                _run(require_api_key(_make_request(), raw))
            assert exc.value.status_code == 429
            assert exc.value.headers["Retry-After"] == "60"
        finally:
            store._keys.pop(meta.key_id, None)
            store._rate_limits.pop(meta.key_id, None)


# ---------------------------------------------------------------------------
# require_api_key — DatabaseAPIKeyStore branch (async)
# ---------------------------------------------------------------------------


class TestRequireApiKeyDatabaseStoreBranch:
    """Production path uses the async DB store branch."""

    def test_db_store_invalid_key_returns_401(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "production")
        instance = _make_db_store_stub(validate_return=None)
        monkeypatch.setattr(auth, "_db_store_instance", instance)
        with pytest.raises(HTTPException) as exc:
            _run(require_api_key(_make_request(), "rge_x.y"))
        assert exc.value.status_code == 401

    def test_db_store_rate_limit_exceeded_returns_429(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "production")
        principal = MagicMock()
        principal.key_id = "rge_db"
        principal.rate_limit_per_minute = 5
        principal.tenant_id = _VALID_TENANT_UUID
        rate_info = MagicMock()
        rate_info.allowed = False

        instance = _make_db_store_stub(
            validate_return=principal, rate_limit_return=rate_info
        )
        monkeypatch.setattr(auth, "_db_store_instance", instance)
        with pytest.raises(HTTPException) as exc:
            _run(require_api_key(_make_request(), "rge_db.secret"))
        assert exc.value.status_code == 429

    def test_db_store_happy_path_returns_principal(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "production")
        principal = MagicMock()
        principal.key_id = "rge_db"
        principal.rate_limit_per_minute = 5
        principal.tenant_id = _VALID_TENANT_UUID
        rate_info = MagicMock()
        rate_info.allowed = True

        instance = _make_db_store_stub(
            validate_return=principal, rate_limit_return=rate_info
        )
        monkeypatch.setattr(auth, "_db_store_instance", instance)
        result = _run(require_api_key(_make_request(), "rge_db.secret"))
        assert result is principal


# ---------------------------------------------------------------------------
# optional_api_key
# ---------------------------------------------------------------------------


class TestOptionalApiKey:
    def test_no_key_returns_none(self):
        assert _run(optional_api_key(_make_request(), None)) is None

    def test_valid_key_returns_principal(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "development")
        store = auth._key_store
        raw, meta = store.create_key(name="opt-key")
        try:
            result = _run(optional_api_key(_make_request(), raw))
            assert isinstance(result, APIKey)
            assert result.key_id == meta.key_id
        finally:
            store._keys.pop(meta.key_id, None)
            store._rate_limits.pop(meta.key_id, None)

    def test_invalid_key_re_raises_401(self, monkeypatch):
        """When a key IS supplied but invalid, surface 401 — not silent None."""
        monkeypatch.setenv("REGENGINE_ENV", "development")
        with pytest.raises(HTTPException) as exc:
            _run(optional_api_key(_make_request(), "rge_bad.secret"))
        assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# verify_jurisdiction_access
# ---------------------------------------------------------------------------


class TestVerifyJurisdictionAccess:
    """Federal roots (US/EU/UK) are universal; sub-regions need explicit grant."""

    def _key(self, allowed: list[str]) -> APIKey:
        return APIKey(
            key_id="k",
            key_hash="h",
            name="n",
            created_at=datetime.now(timezone.utc),
            allowed_jurisdictions=allowed,
        )

    @pytest.mark.parametrize("jurisdiction", ["US", "EU", "UK"])
    def test_federal_root_allowed_for_anyone(self, jurisdiction):
        # Empty entitlement list — federal still allowed.
        verify_jurisdiction_access(self._key([]), jurisdiction)

    def test_state_blocked_without_entitlement(self):
        with pytest.raises(HTTPException) as exc:
            verify_jurisdiction_access(self._key(["US"]), "US-CA")
        assert exc.value.status_code == 403
        assert "Upgrade" in exc.value.detail

    def test_state_allowed_with_exact_entitlement(self):
        verify_jurisdiction_access(self._key(["US-CA"]), "US-CA")

    def test_state_allowed_with_prefix_entitlement(self):
        # Entitlement is a parent region (US-CA), request is a sub-region (US-CA-LA).
        verify_jurisdiction_access(self._key(["US-CA"]), "US-CA-LA")

    def test_state_blocked_when_only_other_state_allowed(self):
        with pytest.raises(HTTPException):
            verify_jurisdiction_access(self._key(["US-NY"]), "US-CA")

    def test_unknown_root_blocked(self):
        with pytest.raises(HTTPException):
            verify_jurisdiction_access(self._key([]), "MARS")

    def test_empty_jurisdiction_blocked(self):
        with pytest.raises(HTTPException):
            verify_jurisdiction_access(self._key([]), "")

    def test_none_allowed_jurisdictions_treated_as_empty(self):
        """Defensive: if allowed_jurisdictions is None at the model level."""
        key = APIKey(
            key_id="k", key_hash="h", name="n",
            created_at=datetime.now(timezone.utc),
        )
        key.allowed_jurisdictions = None  # type: ignore[assignment]
        with pytest.raises(HTTPException):
            verify_jurisdiction_access(key, "US-CA")


# ---------------------------------------------------------------------------
# init_demo_keys
# ---------------------------------------------------------------------------


class TestInitDemoKeys:
    def test_returns_demo_and_admin_keys(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "development")
        # Use a fresh store to avoid leaking state into other tests.
        store = APIKeyStore()
        monkeypatch.setattr(auth, "_key_store", store)
        result = init_demo_keys()
        assert set(result) == {"demo_key", "admin_key"}
        assert result["demo_key"].startswith("rge_")
        assert result["admin_key"].startswith("rge_")
        assert result["demo_key"] != result["admin_key"]

        # Both keys are persisted with their declared scopes/tier.
        keys = store.list_keys()
        names = {k.name for k in keys}
        assert names == {"Demo Key", "Admin Key"}
        admin = next(k for k in keys if k.name == "Admin Key")
        assert "admin" in admin.scopes
        assert admin.billing_tier == "ENTERPRISE"


# ---------------------------------------------------------------------------
# get_tenant_id
# ---------------------------------------------------------------------------


class TestGetTenantId:
    def test_returns_valid_uuid(self):
        assert get_tenant_id(_VALID_TENANT_UUID) == _VALID_TENANT_UUID

    def test_missing_header_400(self):
        with pytest.raises(HTTPException) as exc:
            get_tenant_id(None)
        assert exc.value.status_code == 400
        assert "Missing X-Tenant-ID" in exc.value.detail

    def test_empty_header_400(self):
        with pytest.raises(HTTPException) as exc:
            get_tenant_id("")
        assert exc.value.status_code == 400

    def test_invalid_uuid_400(self):
        with pytest.raises(HTTPException) as exc:
            get_tenant_id("not-a-uuid")
        assert exc.value.status_code == 400
        assert "valid UUID" in exc.value.detail
