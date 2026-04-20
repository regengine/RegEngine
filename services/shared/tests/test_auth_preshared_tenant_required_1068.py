"""Tests for preshared master-key tenant_id enforcement (#1068).

The preshared master-key auth path (services/shared/auth.py) previously accepted
an empty or missing X-Tenant-ID header, silently returning an APIKey with
``tenant_id=None``. Any downstream handler that set RLS from the principal
tenant would then operate outside tenant isolation.

This suite pins the fail-closed contract:

  * missing X-Tenant-ID   → 401  E_TENANT_HEADER_REQUIRED
  * empty  X-Tenant-ID    → 401  E_TENANT_HEADER_REQUIRED
  * non-UUID X-Tenant-ID  → 401  E_TENANT_HEADER_INVALID
  * valid-UUID tenant     → APIKey with that tenant_id (regression guard)
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


# ---- Load services.shared.auth without needing package __init__ ----
_shared_dir = Path(__file__).resolve().parent.parent
# Ensure ``services/`` is on sys.path so auth.py's ``from shared.api_key_store``
# resolves (auth.py imports the sibling module via the top-level name).
_services_dir = _shared_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

_spec = importlib.util.spec_from_file_location(
    "services.shared.auth",
    _shared_dir / "auth.py",
)
auth = importlib.util.module_from_spec(_spec)
sys.modules["services.shared.auth"] = auth
_spec.loader.exec_module(auth)

require_api_key = auth.require_api_key
APIKey = auth.APIKey


# ---- Helpers ----

_MASTER_KEY = "test-master-key-long-enough-for-compare-digest"
_VALID_TENANT_UUID = "11111111-2222-3333-4444-555555555555"


def _make_request(headers: dict[str, str] | None = None) -> MagicMock:
    """Build a minimal MagicMock FastAPI Request.

    Only the attributes require_api_key reads are populated:
    .headers (for X-Tenant-ID), .url.path, .method.
    """
    req = MagicMock()
    req.headers = headers or {}
    req.url.path = "/test-endpoint"
    req.method = "GET"
    return req


@pytest.fixture(autouse=True)
def _configured_master_key(monkeypatch):
    """Install the master key via API_KEY env so the preshared path activates.

    Also clears the test-bypass token and forces a non-test env so the bypass
    path can't intercept the call before the preshared branch runs.
    """
    monkeypatch.setenv("API_KEY", _MASTER_KEY)
    monkeypatch.delenv("REGENGINE_API_KEY", raising=False)
    monkeypatch.delenv("AUTH_TEST_BYPASS_TOKEN", raising=False)
    monkeypatch.setenv("REGENGINE_ENV", "production")
    yield


def _call(request, api_key: str | None):
    """Run the async require_api_key helper synchronously."""
    return asyncio.run(require_api_key(request, api_key))


# ---- Tests ----

class TestPresharedMasterKeyTenantRequired:
    """Preshared master-key auth must fail closed without a valid X-Tenant-ID."""

    def test_preshared_auth_missing_tenant_header_rejected(self):
        """Correct master key, no X-Tenant-ID header -> 401 E_TENANT_HEADER_REQUIRED."""
        request = _make_request(headers={})  # no x-tenant-id
        with pytest.raises(HTTPException) as exc:
            _call(request, _MASTER_KEY)
        assert exc.value.status_code == 401
        assert "E_TENANT_HEADER_REQUIRED" in exc.value.detail

    def test_preshared_auth_empty_tenant_header_rejected(self):
        """Correct master key, X-Tenant-ID: ''  -> 401 E_TENANT_HEADER_REQUIRED."""
        request = _make_request(headers={"x-tenant-id": ""})
        with pytest.raises(HTTPException) as exc:
            _call(request, _MASTER_KEY)
        assert exc.value.status_code == 401
        assert "E_TENANT_HEADER_REQUIRED" in exc.value.detail

    def test_preshared_auth_whitespace_tenant_header_rejected(self):
        """Whitespace-only X-Tenant-ID must also be rejected (.strip() guard)."""
        request = _make_request(headers={"x-tenant-id": "   "})
        with pytest.raises(HTTPException) as exc:
            _call(request, _MASTER_KEY)
        assert exc.value.status_code == 401
        assert "E_TENANT_HEADER_REQUIRED" in exc.value.detail

    def test_preshared_auth_invalid_uuid_rejected(self):
        """X-Tenant-ID: not-a-uuid -> 401 E_TENANT_HEADER_INVALID."""
        request = _make_request(headers={"x-tenant-id": "not-a-uuid"})
        with pytest.raises(HTTPException) as exc:
            _call(request, _MASTER_KEY)
        assert exc.value.status_code == 401
        assert "E_TENANT_HEADER_INVALID" in exc.value.detail

    def test_preshared_auth_valid_tenant_header_accepted(self):
        """Correct master key + valid UUID -> APIKey carrying that tenant_id.

        Regression guard: the happy path must still return an APIKey with
        tenant_id set, so downstream RLS enforcement keeps working.
        """
        request = _make_request(headers={"x-tenant-id": _VALID_TENANT_UUID})
        result = _call(request, _MASTER_KEY)
        assert isinstance(result, APIKey)
        assert result.key_id == "preshared-master"
        assert result.tenant_id == _VALID_TENANT_UUID
