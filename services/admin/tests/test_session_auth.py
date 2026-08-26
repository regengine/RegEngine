"""Tests for cookie-backed session auth dependency."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from services.admin.app.auth import session_auth


def _request(*, session_token: str | None = "session-token") -> Request:
    raw_headers = []
    if session_token is not None:
        raw_headers.append((b"cookie", f"{session_auth.AUTH_SESSION_COOKIE}={session_token}".encode("latin-1")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/admin/organizations",
        "headers": raw_headers,
        "client": ("203.0.113.50", 12345),
        "server": ("testserver", 80),
        "scheme": "https",
        "query_string": b"",
        "http_version": "1.1",
        "root_path": "",
        "state": {},
        "app": SimpleNamespace(state=SimpleNamespace()),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def test_get_current_active_user_hashes_cookie_and_filters_active_session_user():
    user = SimpleNamespace(id="user-id", is_sysadmin=True)
    session = SimpleNamespace(id="session-id", auth_method="email_otp")
    db = MagicMock()
    db.execute.return_value.one_or_none.return_value = (user, session)
    crypto = MagicMock()
    crypto.hash_session_token.return_value = "stored-token-hash"

    result = session_auth.get_current_active_session_context(
        request=_request(session_token="raw-session-token"),
        db=db,
        crypto_service=crypto,
    )

    assert result.user is user
    assert result.session is session
    crypto.hash_session_token.assert_called_once_with("raw-session-token")
    statement = db.execute.call_args.args[0]
    sql = str(statement)
    assert "sessions.token_hash" in sql
    assert "sessions.auth_method" in sql
    assert "sessions.authenticated_at" in sql
    assert "sessions.is_revoked" in sql
    assert "sessions.revoked_at IS NULL" in sql
    assert "sessions.expires_at" in sql
    assert "users.global_status" in sql
    assert "users.status" in sql


def test_get_current_active_user_rejects_missing_cookie_without_db_query():
    db = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        session_auth.get_current_active_session_context(
            request=_request(session_token=None),
            db=db,
            crypto_service=MagicMock(),
        )

    assert exc_info.value.status_code == 401
    db.execute.assert_not_called()


def test_get_current_active_user_rejects_unknown_or_inactive_session():
    db = MagicMock()
    db.execute.return_value.one_or_none.return_value = None
    crypto = MagicMock()
    crypto.hash_session_token.return_value = "stored-token-hash"

    with pytest.raises(HTTPException) as exc_info:
        session_auth.get_current_active_session_context(
            request=_request(session_token="raw-session-token"),
            db=db,
            crypto_service=crypto,
        )

    assert exc_info.value.status_code == 401


def test_scoped_session_lookup_failure_rolls_back_without_masking_503(monkeypatch):
    original = HTTPException(
        status_code=503,
        detail="Authentication service temporarily unavailable.",
    )
    db = MagicMock()
    arm = MagicMock()
    disarm = MagicMock(side_effect=AssertionError("disarm must not run in an aborted transaction"))
    monkeypatch.setattr(session_auth, "arm_global_admin_context", arm)
    monkeypatch.setattr(session_auth, "disarm_global_admin_context", disarm)
    monkeypatch.setattr(
        session_auth,
        "get_current_active_session_context",
        MagicMock(side_effect=original),
    )

    with pytest.raises(HTTPException) as exc_info:
        session_auth.get_scoped_active_session_context(
            request=_request(),
            db=db,
            crypto_service=MagicMock(),
        )

    assert exc_info.value is original
    arm.assert_called_once_with(db)
    db.rollback.assert_called_once_with()
    disarm.assert_not_called()


def test_scoped_session_success_disarms_before_binding_user(monkeypatch):
    user = SimpleNamespace(id="user-id", is_sysadmin=False)
    context = session_auth.ActiveSessionContext(
        user=user,
        session=SimpleNamespace(id="session-id", auth_method="webauthn"),
    )
    events = MagicMock()

    def select_context(**_kwargs):
        events("select")
        return context

    monkeypatch.setattr(
        session_auth,
        "arm_global_admin_context",
        lambda db: events("arm", db),
    )
    monkeypatch.setattr(
        session_auth,
        "get_current_active_session_context",
        select_context,
    )
    monkeypatch.setattr(
        session_auth,
        "disarm_global_admin_context",
        lambda db: events("disarm", db),
    )
    monkeypatch.setattr(
        session_auth,
        "bind_authenticated_user_context",
        lambda db, user_id: events("bind", db, user_id),
    )
    db = MagicMock()

    result = session_auth.get_scoped_active_session_context(
        request=_request(),
        db=db,
        crypto_service=MagicMock(),
    )

    assert result is context
    assert events.call_args_list == [
        call("arm", db),
        call("select"),
        call("disarm", db),
        call("bind", db, user.id),
    ]


def test_get_current_active_user_returns_user_from_context():
    user = SimpleNamespace(id="user-id", is_sysadmin=True)
    session = SimpleNamespace(id="session-id", auth_method="email_otp")

    assert session_auth.get_current_active_user(
        context=session_auth.ActiveSessionContext(user=user, session=session),
    ) is user


def test_require_high_assurance_session_rejects_email_otp():
    user = SimpleNamespace(id="user-id", is_sysadmin=True)
    session = SimpleNamespace(id="session-id", auth_method="email_otp")

    with pytest.raises(HTTPException) as exc_info:
        session_auth.require_high_assurance_session(
            context=session_auth.ActiveSessionContext(user=user, session=session),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "requires_step_up"
    assert exc_info.value.detail["auth_method"] == "email_otp"


@pytest.mark.parametrize("auth_method", ["webauthn", "sso"])
def test_require_high_assurance_session_allows_webauthn_or_sso(auth_method):
    user = SimpleNamespace(id="user-id", is_sysadmin=True)
    session = SimpleNamespace(id="session-id", auth_method=auth_method)

    assert (
        session_auth.require_high_assurance_session(
            context=session_auth.ActiveSessionContext(user=user, session=session),
        )
        is user
    )
