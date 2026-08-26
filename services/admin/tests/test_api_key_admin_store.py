"""Unit coverage for the isolated human-admin API-key store."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from shared.api_key_store import DatabaseAPIKeyStore

from services.admin.app import api_key_admin_store as mod


@pytest.fixture(autouse=True)
def _reset_admin_store(monkeypatch):
    monkeypatch.setattr(mod, "_admin_api_key_store", None)


def test_strict_runtime_constructs_separate_store_from_admin_database_url(monkeypatch):
    sentinel = object()
    constructor = MagicMock(return_value=sentinel)
    monkeypatch.setattr(mod, "requires_strict_auth_runtime", lambda: True)
    monkeypatch.setenv(
        "ADMIN_DATABASE_URL",
        "postgresql://regengine_sysadmin:secret@db.example.test/regengine",  # pragma: allowlist secret
    )
    monkeypatch.setattr(mod, "DatabaseAPIKeyStore", constructor)

    first = mod.get_admin_api_key_store()
    second = mod.get_admin_api_key_store()

    assert first is sentinel
    assert second is sentinel
    constructor.assert_called_once_with(
        database_url="postgresql://regengine_sysadmin:secret@db.example.test/regengine",  # pragma: allowlist secret
        arm_sysadmin_rls=True,
    )


def test_strict_runtime_never_falls_back_to_tenant_database_url(monkeypatch):
    monkeypatch.setattr(mod, "requires_strict_auth_runtime", lambda: True)
    monkeypatch.delenv("ADMIN_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://regengine:secret@db/regengine")  # pragma: allowlist secret

    with pytest.raises(RuntimeError, match="ADMIN_DATABASE_URL is required"):
        mod.get_admin_api_key_store()


def test_explicit_local_runtime_preserves_in_memory_fallback(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(mod, "requires_strict_auth_runtime", lambda: False)
    monkeypatch.setenv("ENABLE_DB_API_KEYS", "false")
    monkeypatch.setattr(mod, "get_key_store", lambda: sentinel)

    assert mod.get_admin_api_key_store() is sentinel


@pytest.mark.asyncio
async def test_sysadmin_context_requires_exact_database_role():
    session = AsyncMock()
    role_result = MagicMock()
    role_result.one.return_value = ("regengine", False, False)
    session.execute.return_value = role_result

    with pytest.raises(RuntimeError, match="connected as 'regengine'"):
        await DatabaseAPIKeyStore._set_sysadmin_context(session)

    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_sysadmin_context_is_transaction_local():
    session = AsyncMock()
    role_result = MagicMock()
    role_result.one.return_value = ("regengine_sysadmin", False, False)
    session.execute.side_effect = [role_result, MagicMock()]

    await DatabaseAPIKeyStore._set_sysadmin_context(session)

    rendered = str(session.execute.await_args_list[1].args[0])
    assert "set_config('regengine.is_sysadmin', 'true', true)" in rendered


@pytest.mark.asyncio
@pytest.mark.parametrize("posture", [("regengine_sysadmin", True, False), ("regengine_sysadmin", False, True)])
async def test_sysadmin_context_rejects_inert_role_posture(posture):
    session = AsyncMock()
    role_result = MagicMock()
    role_result.one.return_value = posture
    session.execute.return_value = role_result

    with pytest.raises(RuntimeError, match="NOSUPERUSER/NOBYPASSRLS"):
        await DatabaseAPIKeyStore._set_sysadmin_context(session)

    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_pretenant_lookup_context_contains_hashes_not_raw_key():
    session = AsyncMock()
    raw_key = "rge_live_identifier.super-secret-material"

    await DatabaseAPIKeyStore._set_key_lookup_context(
        session,
        key_id="rge_live_identifier",
        key_hashes=("a" * 64, "b" * 64),
    )

    params = session.execute.await_args.args[1]
    assert params == {
        "key_id": "rge_live_identifier",
        "current_hash": "a" * 64,
        "legacy_hash": "b" * 64,
    }
    assert raw_key not in repr(params)
    assert ", true)" in str(session.execute.await_args.args[0])
