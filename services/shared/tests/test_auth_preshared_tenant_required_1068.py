"""Regression tests proving the environment-backed master key is retired."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from shared import auth

_RETIRED_KEY = "retired-environment-master-key"
_ATTACKER_TENANT = "11111111-2222-3333-4444-555555555555"


def _request() -> MagicMock:
    request = MagicMock()
    request.headers = {"x-tenant-id": _ATTACKER_TENANT}
    request.url.path = "/industries"
    request.method = "GET"
    return request


def _db_store_rejecting_key():
    store = object.__new__(auth.DatabaseAPIKeyStore)
    store.validate_key = AsyncMock(return_value=None)
    store.check_rate_limit = AsyncMock()
    return store


@pytest.mark.parametrize("environment_name", ["API_KEY", "REGENGINE_API_KEY"])
def test_environment_key_cannot_authenticate_or_select_tenant(monkeypatch, environment_name):
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setenv(environment_name, _RETIRED_KEY)
    store = _db_store_rejecting_key()
    monkeypatch.setattr(auth, "_db_store_instance", store)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth.require_api_key(_request(), _RETIRED_KEY))

    assert exc.value.status_code == 401
    store.validate_key.assert_awaited_once_with(_RETIRED_KEY)
