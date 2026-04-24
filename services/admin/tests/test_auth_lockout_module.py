"""Direct tests for the auth.lockout helper module.

The broader auth route tests intentionally import these helpers through
``auth_routes`` to pin backward compatibility. These tests cover the new
module path directly so future auth_routes.py splits do not break callers
that use the extracted lockout module.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

from services.admin.app.auth import lockout


def test_direct_progressive_delay_table_matches_contract():
    assert lockout._progressive_delay_seconds(0) == 0
    assert lockout._progressive_delay_seconds(2) == 0
    assert lockout._progressive_delay_seconds(3) == 1
    assert lockout._progressive_delay_seconds(7) == 16
    assert lockout._progressive_delay_seconds(12) == lockout._PROGRESSIVE_DELAY_CAP_SECONDS


@pytest.mark.asyncio
async def test_direct_record_lockout_attempt_sets_delay_key():
    pipe = MagicMock()
    pipe.incr = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[5, 1])
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)

    client = MagicMock()
    client.pipeline = MagicMock(return_value=pipe)
    client.setex = AsyncMock(return_value=True)

    session_store = MagicMock()
    session_store._get_client = AsyncMock(return_value=client)

    count = await lockout._record_lockout_attempt(session_store, "a@b.c")

    assert count == 5
    client.setex.assert_awaited_once_with(
        lockout._lockout_delay_key("a@b.c"),
        4,
        "1",
    )


@pytest.mark.asyncio
async def test_direct_check_account_lockout_uses_delay_ttl():
    client = MagicMock()
    client.get = AsyncMock(return_value=None)
    client.ttl = AsyncMock(return_value=42)

    session_store = MagicMock()
    session_store._get_client = AsyncMock(return_value=client)

    with pytest.raises(HTTPException) as exc:
        await lockout._check_account_lockout(session_store, "a@b.c")

    assert exc.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert exc.value.headers["Retry-After"] == "42"

