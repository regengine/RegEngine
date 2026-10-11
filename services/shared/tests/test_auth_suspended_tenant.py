"""Suspended tenants must not authenticate on the live API-key path.

Regression coverage for the finding that the suspended-tenant deny lived
only in ``services/admin/app/dependencies.py::get_current_tenant`` (which
no production route calls) while the live dependency
``shared.auth.require_api_key`` never read ``tenants.status``.

Every test below calls ``require_api_key`` itself against a stubbed
``DatabaseAPIKeyStore`` (built via ``object.__new__`` so no real database
is needed). On the old code the status read did not exist, so the
suspended/archived/missing cases authenticated and these tests failed;
with the fix they deny.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

_shared_dir = Path(__file__).resolve().parent.parent
_services_dir = _shared_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

if "shared.auth" in sys.modules:
    auth = sys.modules["shared.auth"]
else:
    _spec = importlib.util.spec_from_file_location("shared.auth", _shared_dir / "auth.py")
    auth = importlib.util.module_from_spec(_spec)
    sys.modules["shared.auth"] = auth
    _spec.loader.exec_module(auth)

require_api_key = auth.require_api_key

_VALID_TENANT_UUID = "11111111-2222-3333-4444-555555555555"
_OTHER_TENANT_UUID = "99999999-8888-7777-6666-555555555555"


def _make_request(headers: dict[str, str] | None = None, path: str = "/x") -> MagicMock:
    req = MagicMock()
    req.headers = headers or {}
    req.url.path = path
    req.method = "GET"
    # A real namespace so "principal stored?" assertions are meaningful
    # (a bare MagicMock auto-creates any attribute it is asked about).
    req.state = SimpleNamespace()
    return req


def _run(coro):
    return asyncio.run(coro)


def _make_principal(tenant_id=_VALID_TENANT_UUID):
    principal = MagicMock()
    principal.key_id = "rge_live_test"
    principal.rate_limit_per_minute = 100
    principal.tenant_id = tenant_id
    principal.scopes = ["read", "write"]
    return principal


def _make_store(principal, tenant_status="active"):
    instance = object.__new__(auth.DatabaseAPIKeyStore)
    instance.validate_key = AsyncMock(return_value=principal)
    instance.check_rate_limit = AsyncMock(return_value=MagicMock(allowed=True, remaining=99, retry_after=None))
    if isinstance(tenant_status, Exception):
        instance.get_tenant_status = AsyncMock(side_effect=tenant_status)
    else:
        instance.get_tenant_status = AsyncMock(return_value=tenant_status)
    return instance


@pytest.fixture(autouse=True)
def _clean_auth_env(monkeypatch):
    for var in (
        "AUTH_TEST_BYPASS_TOKEN",
        "AUTH_TEST_BYPASS_TENANT_ID",
        "REGENGINE_ENV",
        "REGENGINE_AUTH_STRICT",
        "ENABLE_DB_API_KEYS",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REGENGINE_ENV", "production")
    yield


def _production_store(monkeypatch, store):
    monkeypatch.setattr(auth, "_db_store_instance", store)


class TestSuspendedTenantDenied:
    @pytest.mark.parametrize("status", ["suspended", "archived", None, ""])
    def test_non_active_tenant_gets_403(self, monkeypatch, status):
        """Suspended, archived, and missing tenants deny with 403."""
        principal = _make_principal()
        store = _make_store(principal, tenant_status=status)
        _production_store(monkeypatch, store)

        with pytest.raises(HTTPException) as exc:
            _run(require_api_key(_make_request(), "rge_live_test.secret"))

        assert exc.value.status_code == 403
        assert "Invalid API key" in exc.value.detail

    def test_denied_principal_is_never_stored(self, monkeypatch):
        """A suspended key must not reach request state or rate limiting."""
        principal = _make_principal()
        store = _make_store(principal, tenant_status="suspended")
        _production_store(monkeypatch, store)
        request = _make_request()

        with pytest.raises(HTTPException):
            _run(require_api_key(request, "rge_live_test.secret"))

        assert not hasattr(request.state, "api_key")
        store.check_rate_limit.assert_not_awaited()

    def test_status_lookup_binds_only_the_key_tenant(self, monkeypatch):
        """A spoofed tenant header cannot change which status is read."""
        principal = _make_principal()
        store = _make_store(principal, tenant_status="suspended")
        _production_store(monkeypatch, store)

        with pytest.raises(HTTPException) as exc:
            _run(
                require_api_key(
                    _make_request(headers={"X-Tenant-ID": _OTHER_TENANT_UUID}),
                    "rge_live_test.secret",
                )
            )

        assert exc.value.status_code == 403
        store.get_tenant_status.assert_awaited_once_with(_VALID_TENANT_UUID)

    def test_status_lookup_error_fails_closed_with_503(self, monkeypatch):
        """An unreadable tenant status denies, it never allows."""
        principal = _make_principal()
        store = _make_store(principal, tenant_status=RuntimeError("db down"))
        _production_store(monkeypatch, store)
        request = _make_request()

        with pytest.raises(HTTPException) as exc:
            _run(require_api_key(request, "rge_live_test.secret"))

        assert exc.value.status_code == 503
        assert not hasattr(request.state, "api_key")

    @pytest.mark.parametrize("status", ["active", "trial"])
    def test_active_and_trial_tenants_authenticate(self, monkeypatch, status):
        """The allow-list matches the opaque-session check exactly."""
        principal = _make_principal()
        store = _make_store(principal, tenant_status=status)
        _production_store(monkeypatch, store)
        request = _make_request()

        result = _run(require_api_key(request, "rge_live_test.secret"))

        assert result is principal
        assert request.state.api_key is principal
