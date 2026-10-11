"""Unit tests for ``DatabaseAPIKeyStore.get_tenant_status``.

The live suspension deny in ``require_api_key`` depends on this reader:
one indexed status read, bound to the validated key's tenant only, with
lookup failures raised so the caller can fail closed (503). All sessions
are fakes; no database is needed.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest
from shared.api_key_store import DatabaseAPIKeyStore

_TENANT = "11111111-2222-3333-4444-555555555555"


class _FakeSession:
    def __init__(self, status_row):
        self._status_row = status_row
        self.statements: list[tuple[str, object]] = []

    async def execute(self, stmt, params=None):
        self.statements.append((str(stmt), params))
        if isinstance(self._status_row, Exception):
            raise self._status_row
        result = MagicMock()
        result.fetchone.return_value = self._status_row
        return result

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def close(self):
        pass


def _store_with_session(monkeypatch, status_row):
    store = object.__new__(DatabaseAPIKeyStore)
    fake = _FakeSession(status_row)

    @asynccontextmanager
    async def _session():
        yield fake

    monkeypatch.setattr(store, "_session", _session)
    return store, fake


def _run(coro):
    return asyncio.run(coro)


class TestGetTenantStatus:
    def test_returns_status_and_binds_key_tenant(self, monkeypatch):
        store, fake = _store_with_session(monkeypatch, ("suspended",))
        assert _run(store.get_tenant_status(_TENANT)) == "suspended"
        assert len(fake.statements) == 2
        guc_sql, guc_params = fake.statements[0]
        assert "app.tenant_id" in guc_sql
        assert guc_params == {"tid": _TENANT}
        status_sql, status_params = fake.statements[1]
        assert "FROM tenants" in status_sql
        assert status_params == {"tid": _TENANT}

    def test_missing_row_returns_none(self, monkeypatch):
        store, _ = _store_with_session(monkeypatch, None)
        assert _run(store.get_tenant_status(_TENANT)) is None

    def test_lookup_error_propagates_for_fail_closed_caller(self, monkeypatch):
        store, _ = _store_with_session(monkeypatch, RuntimeError("db down"))
        with pytest.raises(RuntimeError, match="db down"):
            _run(store.get_tenant_status(_TENANT))

    @pytest.mark.parametrize("tenant_id", [None, ""])
    def test_empty_tenant_returns_none_without_touching_db(self, monkeypatch, tenant_id):
        store, fake = _store_with_session(monkeypatch, ("active",))
        assert _run(store.get_tenant_status(tenant_id)) is None
        assert fake.statements == []
