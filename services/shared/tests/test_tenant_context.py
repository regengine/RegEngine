"""Tests for services.shared.tenant_context (EPIC-A #1651).

Covers the public contract of resolve_tenant_context():

  * API-key principal with tenant_id → returns context
  * JWT principal with tenant_id → returns context
  * No principal on request → 401 E_NO_PRINCIPAL
  * Principal present but tenant_id missing/empty → 401 E_NO_TENANT
  * Path-param tenant_id conflicting with principal → 409 E_TENANT_MISMATCH
  * Query-param tenant_id conflicting with principal → 409 E_TENANT_MISMATCH
  * Header override mismatch → 409 E_TENANT_MISMATCH
  * Query-param tenant_id matching principal → passes (idempotent call)

These are the failure modes EPIC-A consolidates. If any regresses, CI
should fail here before Semgrep catches it elsewhere.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest


# ---- Load services.shared.tenant_context without needing package __init__ ----
_shared_dir = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "services.shared.tenant_context",
    _shared_dir / "tenant_context.py",
)
tenant_context = importlib.util.module_from_spec(_spec)
sys.modules["services.shared.tenant_context"] = tenant_context
_spec.loader.exec_module(tenant_context)

resolve_tenant_context = tenant_context.resolve_tenant_context
TenantContext = tenant_context.TenantContext
TenantContextError = tenant_context.TenantContextError


# ---- Helpers ----

@dataclass
class _FakeAPIKey:
    key_id: str
    tenant_id: Optional[str]


@dataclass
class _FakeUser:
    id: str
    tenant_id: Optional[str]
    email: Optional[str] = None


def _make_request(
    *,
    api_key: Optional[_FakeAPIKey] = None,
    user: Optional[_FakeUser] = None,
    path_params: Optional[Dict[str, Any]] = None,
    query_params: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
):
    """Build a minimal MagicMock request.

    Only exercises attributes resolve_tenant_context() reads:
    .state, .path_params, .query_params, .headers, .url.path.
    """
    req = MagicMock()
    req.state.api_key = api_key
    req.state.user = user
    req.path_params = path_params or {}
    q = query_params or {}
    req.query_params.get = q.get
    req.headers = headers or {}
    req.url.path = "/test"
    return req


def _run(req):
    return asyncio.run(resolve_tenant_context(req))


# ---- Happy paths ----

def test_api_key_principal_with_tenant_returns_context():
    req = _make_request(api_key=_FakeAPIKey(key_id="abc123", tenant_id="tenant-A"))
    ctx = _run(req)
    assert isinstance(ctx, TenantContext)
    assert ctx.tenant_id == "tenant-A"
    assert ctx.principal_kind == "api_key"
    assert ctx.principal_id == "abc123"


def test_jwt_user_principal_with_tenant_returns_context():
    req = _make_request(
        user=_FakeUser(id="user-42", tenant_id="tenant-B", email="u@example.com"),
    )
    ctx = _run(req)
    assert ctx.tenant_id == "tenant-B"
    assert ctx.principal_kind == "jwt"
    assert ctx.principal_id == "user-42"
    assert ctx.actor_email == "u@example.com"


def test_preshared_master_key_resolves_with_own_kind():
    req = _make_request(api_key=_FakeAPIKey(key_id="preshared-master", tenant_id="tenant-C"))
    ctx = _run(req)
    assert ctx.principal_kind == "preshared"


def test_test_bypass_key_labeled_correctly():
    req = _make_request(api_key=_FakeAPIKey(key_id="test", tenant_id="tenant-D"))
    ctx = _run(req)
    assert ctx.principal_kind == "test_bypass"


def test_matching_query_param_tenant_is_idempotent():
    req = _make_request(
        api_key=_FakeAPIKey(key_id="k", tenant_id="tenant-A"),
        query_params={"tenant_id": "tenant-A"},
    )
    ctx = _run(req)
    assert ctx.tenant_id == "tenant-A"


# ---- Failure modes ----

def test_no_principal_raises_401_e_no_principal():
    req = _make_request()
    with pytest.raises(TenantContextError) as excinfo:
        _run(req)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail["code"] == "E_NO_PRINCIPAL"


def test_principal_without_tenant_raises_401_e_no_tenant():
    req = _make_request(api_key=_FakeAPIKey(key_id="k", tenant_id=None))
    with pytest.raises(TenantContextError) as excinfo:
        _run(req)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail["code"] == "E_NO_TENANT"


def test_user_without_tenant_raises_401_e_no_tenant():
    req = _make_request(user=_FakeUser(id="u", tenant_id=None))
    with pytest.raises(TenantContextError) as excinfo:
        _run(req)
    assert excinfo.value.detail["code"] == "E_NO_TENANT"


def test_empty_string_tenant_raises_e_no_tenant():
    req = _make_request(api_key=_FakeAPIKey(key_id="k", tenant_id=""))
    with pytest.raises(TenantContextError) as excinfo:
        _run(req)
    assert excinfo.value.detail["code"] == "E_NO_TENANT"


def test_path_param_tenant_mismatch_raises_409():
    req = _make_request(
        api_key=_FakeAPIKey(key_id="k", tenant_id="tenant-A"),
        path_params={"tenant_id": "tenant-B"},
    )
    with pytest.raises(TenantContextError) as excinfo:
        _run(req)
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["code"] == "E_TENANT_MISMATCH"


def test_query_param_tenant_mismatch_raises_409():
    req = _make_request(
        api_key=_FakeAPIKey(key_id="k", tenant_id="tenant-A"),
        query_params={"tenant_id": "tenant-B"},
    )
    with pytest.raises(TenantContextError) as excinfo:
        _run(req)
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["code"] == "E_TENANT_MISMATCH"


def test_header_override_mismatch_raises_409():
    req = _make_request(
        api_key=_FakeAPIKey(key_id="k", tenant_id="tenant-A"),
        headers={"x-tenant-id-override": "tenant-evil"},
    )
    with pytest.raises(TenantContextError) as excinfo:
        _run(req)
    assert excinfo.value.detail["code"] == "E_TENANT_MISMATCH"
