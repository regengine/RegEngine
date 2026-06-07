"""Regression tests for login validation audit findings #4 and #5."""

from __future__ import annotations

import os
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_repo_root = Path(__file__).resolve().parents[3]
_service_dir = Path(__file__).resolve().parents[2]
for _p in (_repo_root, _service_dir):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

os.environ.setdefault("ADMIN_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-for-login-validation")
os.environ.setdefault("JWT_SECRET", "test-secret-for-login-validation")
os.environ.setdefault("JWT_ALGORITHM", "HS256")

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from services.admin.app.auth import login_router

GENERIC_AUTH_ERROR = {"detail": "Incorrect email or password"}


def _make_session_store() -> MagicMock:
    redis_client = AsyncMock()
    redis_client.get = AsyncMock(return_value=None)
    redis_client.ttl = AsyncMock(return_value=-1)
    redis_client.delete = AsyncMock(return_value=1)
    redis_client.setex = AsyncMock(return_value=True)

    pipe = AsyncMock()
    pipe.incr = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[1, True])
    redis_client.pipeline = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=pipe),
            __aexit__=AsyncMock(return_value=False),
        )
    )

    store = MagicMock()
    store._get_client = AsyncMock(return_value=redis_client)
    store.create_session = AsyncMock(return_value=None)
    return store


def _make_user(email: str = "alice@example.com") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = email
    user.password_hash = "hashed"
    user.status = "active"
    user.is_sysadmin = False
    user.token_version = 0
    return user


@contextmanager
def _client_for_login(*, user: object | None = None, verify_result: bool = False):
    app = FastAPI()
    app.state.limiter = login_router.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(login_router.router, prefix="/auth")

    db = MagicMock()
    executed_statements = []

    def execute(stmt):
        executed_statements.append(stmt)
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        result.all.return_value = []
        return result

    db.execute.side_effect = execute
    app.dependency_overrides[login_router.get_session] = lambda: db
    app.dependency_overrides[login_router.get_session_store] = _make_session_store

    original_enabled = login_router.limiter.enabled
    original_verify_login = login_router.verify_login
    login_router.limiter.enabled = False
    login_router.verify_login = MagicMock(return_value=verify_result)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, db, executed_statements, login_router.verify_login
    finally:
        login_router.verify_login = original_verify_login
        login_router.limiter.enabled = original_enabled


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "", "password": "password"},
        {"email": "alice@example.com", "password": ""},
        {"email": "", "password": ""},
        {"email": "   \t", "password": "password"},
        {"email": "alice@example.com", "password": "   \n"},
    ],
)
def test_login_rejects_empty_and_whitespace_only_values(payload):
    with _client_for_login() as (client, db, _statements, verify_login):
        response = client.post("/auth/login", json=payload)

    assert response.status_code == 422
    db.execute.assert_not_called()
    verify_login.assert_not_called()


def test_sql_injection_looking_email_returns_generic_401():
    with _client_for_login(user=None, verify_result=False) as (
        client,
        _db,
        _statements,
        verify_login,
    ):
        response = client.post(
            "/auth/login",
            json={"email": "' OR '1'='1", "password": "password"},
        )

    assert response.status_code == 401
    assert response.json() == GENERIC_AUTH_ERROR
    verify_login.assert_called_once_with("password", None)


def test_wrong_password_and_nonexistent_email_return_identical_generic_401():
    with _client_for_login(user=_make_user(), verify_result=False) as (
        wrong_password_client,
        *_wrong_password_rest,
    ):
        wrong_password_response = wrong_password_client.post(
            "/auth/login",
            json={"email": "alice@example.com", "password": "wrong-password"},
        )

    with _client_for_login(user=None, verify_result=False) as (
        nonexistent_client,
        *_nonexistent_rest,
    ):
        nonexistent_response = nonexistent_client.post(
            "/auth/login",
            json={"email": "missing@example.com", "password": "wrong-password"},
        )

    assert wrong_password_response.status_code == 401
    assert nonexistent_response.status_code == 401
    assert wrong_password_response.json() == nonexistent_response.json() == GENERIC_AUTH_ERROR


def test_login_lookup_trims_and_lowercases_email_before_query():
    with _client_for_login(user=None, verify_result=False) as (
        client,
        _db,
        statements,
        _verify_login,
    ):
        response = client.post(
            "/auth/login",
            json={"email": "  ALICE@EXAMPLE.COM  ", "password": "password"},
        )

    assert response.status_code == 401
    compiled = str(statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert "'alice@example.com'" in compiled
    assert "ALICE@EXAMPLE.COM" not in compiled
