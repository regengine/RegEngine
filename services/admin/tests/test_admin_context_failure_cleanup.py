"""Negative-path cleanup for transaction-local authentication authority."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from services.admin.app import dependencies


def _cookie_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/protected",
            "headers": [
                (
                    b"cookie",
                    f"{dependencies.AUTH_SESSION_COOKIE}=opaque-session".encode("latin-1"),
                )
            ],
            "client": ("203.0.113.10", 12345),
            "server": ("testserver", 443),
            "scheme": "https",
            "query_string": b"",
            "root_path": "",
        }
    )


@pytest.mark.asyncio
async def test_cookie_bootstrap_failure_rolls_back_and_preserves_503(monkeypatch):
    original = HTTPException(status_code=503, detail="auth database unavailable")
    db = MagicMock()
    arm = MagicMock()
    disarm = MagicMock(side_effect=AssertionError("must not disarm an aborted transaction"))
    monkeypatch.setattr(dependencies, "arm_global_admin_context", arm)
    monkeypatch.setattr(dependencies, "disarm_global_admin_context", disarm)
    monkeypatch.setattr(
        dependencies,
        "get_current_active_session_context",
        MagicMock(side_effect=original),
    )

    with pytest.raises(HTTPException) as exc_info:
        await dependencies.get_current_user(
            request=_cookie_request(),
            token=None,
            db=db,
            session_store=None,
        )

    assert exc_info.value is original
    arm.assert_called_once_with(db)
    db.rollback.assert_called_once_with()
    disarm.assert_not_called()
    db.get.assert_not_called()


@pytest.mark.asyncio
async def test_membership_bootstrap_failure_rolls_back_without_cleanup_query(monkeypatch):
    user_id = uuid.uuid4()
    original = RuntimeError("membership database unavailable")
    db = MagicMock()
    db.bind = None
    db.get.return_value = SimpleNamespace(
        id=user_id,
        is_sysadmin=False,
        status="active",
        token_version=0,
    )
    db.execute.side_effect = original
    arm = MagicMock()
    disarm = MagicMock(side_effect=AssertionError("must not disarm an aborted transaction"))
    monkeypatch.setattr(dependencies, "get_supabase", lambda: None)
    monkeypatch.setattr(dependencies, "requires_strict_auth_runtime", lambda: False)
    monkeypatch.setattr(
        dependencies,
        "decode_access_token",
        lambda _token: {"sub": str(user_id), "tv": 0},
    )
    monkeypatch.setattr(dependencies, "bind_authenticated_user_context", MagicMock())
    monkeypatch.setattr(dependencies, "arm_global_admin_context", arm)
    monkeypatch.setattr(dependencies, "disarm_global_admin_context", disarm)

    with pytest.raises(RuntimeError) as exc_info:
        await dependencies.get_current_user(
            token="valid-local-token",
            db=db,
            session_store=None,
        )

    assert exc_info.value is original
    arm.assert_called_once_with(db)
    db.rollback.assert_called_once_with()
    disarm.assert_not_called()
