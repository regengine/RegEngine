"""Tests for opaque-session POST /auth/session/logout revocation."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from starlette.testclient import TestClient

from services.admin.app import auth_routes
from services.admin.app.auth import session_auth

USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = uuid.UUID("66666666-6666-4666-8666-666666666666")


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_routes.router)
    return app


def _wire(app, *, db):
    user = SimpleNamespace(id=USER_ID, email="owner@example.com")
    session = SimpleNamespace(id=SESSION_ID, auth_method="webauthn")
    app.dependency_overrides[session_auth.get_current_active_session_context] = lambda: (
        session_auth.ActiveSessionContext(user=user, session=session)
    )
    app.dependency_overrides[auth_routes.get_session] = lambda: db


def test_session_logout_revokes_the_presented_session_row():
    app = _app()
    db = MagicMock()
    db.execute.return_value.rowcount = 1
    _wire(app, db=db)

    response = TestClient(app).post("/auth/session/logout")

    assert response.status_code == 200
    assert response.json() == {"status": "success"}

    update_sql = str(db.execute.call_args.args[0])
    assert "UPDATE sessions" in update_sql
    assert "is_revoked" in update_sql
    assert "revoked_at" in update_sql
    assert "sessions.id" in update_sql
    db.commit.assert_called_once()


def test_session_logout_clears_the_session_cookie():
    app = _app()
    db = MagicMock()
    db.execute.return_value.rowcount = 1
    _wire(app, db=db)

    response = TestClient(app).post("/auth/session/logout")

    set_cookie = response.headers.get("set-cookie", "")
    assert "__Host-regengine_session=" in set_cookie
    assert "Max-Age=0" in set_cookie
    assert "Path=/" in set_cookie
    assert "Secure" in set_cookie
    assert "HttpOnly" in set_cookie


def test_session_logout_rejects_unauthenticated_requests():
    """No cookie => 401 from get_current_active_session_context, no DB write."""
    app = _app()
    db = MagicMock()
    app.dependency_overrides[session_auth.get_session] = lambda: db

    response = TestClient(app).post("/auth/session/logout")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}
    db.commit.assert_not_called()
