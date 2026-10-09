"""Bearer logout must answer 401, not 500, when the presented token fails to decode."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from jwt.exceptions import ExpiredSignatureError

from services.admin.app.auth import sessions_router
from services.admin.app.dependencies import get_current_user, get_session_store

USER_ID = uuid.uuid4()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(sessions_router.router, prefix="/auth")
    user = SimpleNamespace(id=USER_ID, email="owner@example.com")
    app.dependency_overrides[get_current_user] = lambda: user
    store = AsyncMock()
    store.revoke_all_user_sessions.return_value = 0
    app.dependency_overrides[get_session_store] = lambda: store
    return app


def _client(monkeypatch) -> TestClient:
    async def _no_elevation(*args, **kwargs):
        return 0

    monkeypatch.setattr(sessions_router, "_revoke_all_elevation_tokens_for_user", _no_elevation)
    return TestClient(_app(), raise_server_exceptions=False)


def test_logout_with_undecodable_token_returns_401(monkeypatch):
    """A token that fails verification inside the logout body is a 401.

    The auth dependency already accepted this request (for example the
    token expired or was revoked between the dependency check and the
    logout body's own decode), so the re-decode must map verification
    failures to "Could not validate credentials", not bubble up as a 500.
    """

    def _bad_token(token: str) -> dict:
        raise ExpiredSignatureError("Signature has expired")

    monkeypatch.setattr(sessions_router, "decode_access_token", _bad_token)

    response = _client(monkeypatch).post("/auth/logout", headers={"Authorization": "Bearer expired-token"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_logout_with_valid_token_still_succeeds(monkeypatch):
    monkeypatch.setattr(sessions_router, "decode_access_token", lambda token: {"sub": str(USER_ID)})

    response = _client(monkeypatch).post("/auth/logout", headers={"Authorization": "Bearer good-token"})

    assert response.status_code == 200
    assert response.json() == {"status": "success"}
