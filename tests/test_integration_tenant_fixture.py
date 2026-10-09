"""Regression tests for the integration tenant_id fixture.

tests/integration/conftest.py:tenant_id used to catch every error and fall
back to "default-tenant", which masked broken authentication. These tests
call the fixture's underlying function with a stubbed HTTP client and prove
that auth failures fail instead of returning a default tenant.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest


def _load_integration_conftest():
    path = Path(__file__).parent / "integration" / "conftest.py"
    spec = importlib.util.spec_from_file_location("integration_conftest_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def conftest_module():
    return _load_integration_conftest()


class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _StubClient:
    """Minimal async stand-in for httpx.AsyncClient."""

    result = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, *args, **kwargs):
        result = type(self).result
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def stub_http(monkeypatch, conftest_module):
    def install(result):
        _StubClient.result = result
        monkeypatch.setattr(conftest_module, "httpx", SimpleNamespace(AsyncClient=_StubClient))

    return install


def _resolve(conftest_module, token="some-token"):
    return conftest_module.tenant_id.__wrapped__(token)


async def test_unauthorized_identity_fails(conftest_module, stub_http):
    """A 401 from /v1/users/me must fail, not yield a default tenant."""
    stub_http(_FakeResponse(401))
    with pytest.raises(AssertionError, match="Failed to resolve tenant_id"):
        await _resolve(conftest_module)


async def test_transport_error_propagates(conftest_module, stub_http):
    """A connection failure must surface, not yield a default tenant."""
    stub_http(httpx.ConnectError("connection refused"))
    with pytest.raises(httpx.ConnectError):
        await _resolve(conftest_module)


async def test_identity_without_tenant_fails(conftest_module, stub_http):
    """A 200 response missing tenant_id must fail, not yield a default."""
    stub_http(_FakeResponse(200, {"user_id": "u-1"}))
    with pytest.raises(AssertionError, match="no tenant_id"):
        await _resolve(conftest_module)


async def test_valid_identity_returns_tenant(conftest_module, stub_http):
    """The happy path still resolves the tenant from the identity response."""
    stub_http(_FakeResponse(200, {"tenant_id": "tenant-abc"}))
    assert await _resolve(conftest_module) == "tenant-abc"
