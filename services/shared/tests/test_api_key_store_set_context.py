"""Regression test for #1879: _set_context must not use SET LOCAL with $1.

Postgres does not allow parameter placeholders in ``SET`` / ``SET LOCAL``.
The previous implementation sent ``SET LOCAL app.tenant_id = $1`` via
asyncpg, which Postgres rejected with ``syntax error at or near "$1"``,
500'ing every ``POST /v1/admin/keys``.

The fix switches to ``set_config(name, value, is_local=true)`` — a
regular function call that accepts bound parameters. This test pins
the rendered SQL so a future refactor that reintroduces ``SET LOCAL``
trips CI.
"""
from unittest.mock import AsyncMock, patch

import pytest

from shared.api_key_store import DatabaseAPIKeyStore


@pytest.mark.asyncio
async def test_set_context_uses_set_config_not_set_local(monkeypatch):
    """Rendered SQL must call set_config(…), not SET LOCAL …"""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:6543/d")
    with patch("shared.api_key_store.create_async_engine") as _e, patch(
        "shared.api_key_store.sessionmaker"
    ) as _s:
        _e.return_value = object()
        _s.return_value = lambda: None
        store = DatabaseAPIKeyStore()

    captured = {}

    class _Session:
        async def execute(self, stmt, params=None):
            captured["sql"] = str(stmt)
            captured["params"] = params

    await store._set_context(_Session(), "5946c58f-ddf9-4db0-9baa-acb11c6fce91")

    sql = captured["sql"]
    # Must use set_config — the parameterizable path
    assert "set_config" in sql
    assert "app.tenant_id" in sql
    assert ":tid" in sql  # Still parameterized (no f-string interpolation)
    # Must NOT use SET LOCAL — the unparameterizable path
    assert "SET LOCAL" not in sql.upper()
    # Params passed as a dict
    assert captured["params"] == {"tid": "5946c58f-ddf9-4db0-9baa-acb11c6fce91"}


@pytest.mark.asyncio
async def test_set_context_skipped_when_no_tenant(monkeypatch):
    """Empty or None tenant → no DB call (unchanged)."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:6543/d")
    with patch("shared.api_key_store.create_async_engine") as _e, patch(
        "shared.api_key_store.sessionmaker"
    ) as _s:
        _e.return_value = object()
        _s.return_value = lambda: None
        store = DatabaseAPIKeyStore()

    called = {"count": 0}

    class _Session:
        async def execute(self, stmt, params=None):
            called["count"] += 1

    await store._set_context(_Session(), None)
    await store._set_context(_Session(), "")
    assert called["count"] == 0


@pytest.mark.asyncio
async def test_set_context_rejects_non_uuid(monkeypatch):
    """UUID validation still runs — SQL injection surface stays closed."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:6543/d")
    with patch("shared.api_key_store.create_async_engine") as _e, patch(
        "shared.api_key_store.sessionmaker"
    ) as _s:
        _e.return_value = object()
        _s.return_value = lambda: None
        store = DatabaseAPIKeyStore()

    class _Session:
        async def execute(self, stmt, params=None):
            pass

    with pytest.raises(ValueError, match="Invalid UUID"):
        await store._set_context(_Session(), "not-a-uuid")

    # Classic SQL-injection attempt also rejected before reaching the DB
    with pytest.raises(ValueError, match="Invalid UUID"):
        await store._set_context(_Session(), "'; DROP TABLE api_keys; --")
