"""Signup session-persistence ordering — #1403.

The previous flow was:
    1. Supabase user created
    2. DB flushes (user + tenant + membership)
    3. ``db.commit()``
    4. Redis ``create_session``  ← if this raised, the DB rows stayed
       committed, the client got 503 with no session, and a retry with
       the same email returned 409 "user already exists" — orphan tenant,
       no recovery path.

This test suite locks in the new flow:

    Redis persist → db.commit()

with a ``db.rollback()`` on Redis failure so a retry finds no user in the
DB and can proceed. Supabase-user orphan cleanup is explicitly out of
scope — that is tracked by #1090.

Tests are direct-call unit tests (calling ``signup.__wrapped__``) to
avoid the SlowAPI limiter and the full app-wiring path.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


def _make_request(headers=None):
    from starlette.requests import Request

    raw_headers = []
    for k, v in (headers or {"user-agent": "pytest"}).items():
        raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/signup",
        "headers": raw_headers,
        "client": ("127.0.0.1", 0),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
        "http_version": "1.1",
        "root_path": "",
        "state": {},
        "app": SimpleNamespace(
            state=SimpleNamespace(limiter=None, rate_limit_exceeded_handler=None),
        ),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def _valid_password() -> str:
    # Long enough + mixed enough to satisfy password_policy.validate_password.
    return "Correct-Horse-Battery-Staple-9!"


def _make_db_no_existing_user() -> MagicMock:
    """DB mock where the duplicate-email lookup returns no user."""
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    db.add.return_value = None
    db.flush.return_value = None
    return db


def _call_signup(db, session_store, *, email: str = "new@example.com"):
    from services.admin.app.auth_routes import signup, RegisterRequest

    payload = RegisterRequest(
        email=email,
        password=_valid_password(),
        tenant_name="Acme Foods",
    )
    return signup.__wrapped__(
        payload=payload,
        request=_make_request(),
        db=db,
        session_store=session_store,
    )


# ── Happy path ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_signup_happy_path_commits_after_session_persist(monkeypatch):
    """Happy path: Redis persists, then DB commits, then response is returned."""
    from services.admin.app import auth_routes

    # No Supabase — keep the test hermetic.
    monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)
    # Best-effort side-effects at the tail of signup — make them no-ops.
    monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)

    db = _make_db_no_existing_user()
    call_order: list[str] = []
    db.commit.side_effect = lambda: call_order.append("db.commit")

    session_store = MagicMock()

    async def _ok_create(session_data):
        call_order.append("redis.create_session")
        return session_data

    session_store.create_session = AsyncMock(side_effect=_ok_create)

    result = await _call_signup(db, session_store)

    # Redis MUST be persisted before the first DB commit — any ordering
    # where the commit fires first would re-introduce the #1403 orphan.
    assert call_order, "expected at least one step to fire"
    assert call_order[0] == "redis.create_session", (
        f"Redis must persist before DB commit; saw {call_order}"
    )
    assert "db.commit" in call_order, (
        f"expected a db.commit after Redis persist; saw {call_order}"
    )
    assert result.access_token
    assert result.refresh_token
    assert db.rollback.call_count == 0
    session_store.create_session.assert_awaited_once()


# ── Redis failure → DB rollback ────────────────────────────────────────


@pytest.mark.asyncio
async def test_signup_rolls_back_db_when_redis_persist_fails(monkeypatch):
    """If Redis ``create_session`` always raises, the signup MUST:
      * roll back the DB (so no tenant/user/membership row is committed),
      * raise 503 to the client,
      * NOT call ``db.commit()``.
    """
    from services.admin.app import auth_routes

    monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)
    monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)
    # Eliminate the retry back-off so the test stays fast.
    monkeypatch.setattr(auth_routes.asyncio, "sleep", AsyncMock(return_value=None))

    db = _make_db_no_existing_user()
    session_store = MagicMock()
    session_store.create_session = AsyncMock(
        side_effect=ConnectionError("redis down")
    )

    with pytest.raises(HTTPException) as exc_info:
        await _call_signup(db, session_store)

    assert exc_info.value.status_code == 503
    assert db.rollback.call_count >= 1
    assert db.commit.call_count == 0
    # Both retries should have been attempted.
    assert session_store.create_session.await_count == 2


# ── Retry after Redis-failure → no 409 ────────────────────────────────


@pytest.mark.asyncio
async def test_retry_after_redis_failure_is_not_blocked_by_409(monkeypatch):
    """After a Redis-failed signup rolls back, the same email must be free.

    We simulate two sequential signups on a shared DB mock whose
    duplicate-email lookup returns ``None`` (because the first attempt
    was rolled back). The second attempt should succeed, not raise 409.
    """
    from services.admin.app import auth_routes

    monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)
    monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)
    monkeypatch.setattr(auth_routes.asyncio, "sleep", AsyncMock(return_value=None))

    db = _make_db_no_existing_user()

    # First signup: Redis fails.
    session_store_fail = MagicMock()
    session_store_fail.create_session = AsyncMock(
        side_effect=ConnectionError("redis down")
    )
    with pytest.raises(HTTPException) as exc_info:
        await _call_signup(db, session_store_fail, email="retry@example.com")
    assert exc_info.value.status_code == 503

    # DB was rolled back, so the duplicate-email lookup still returns None:
    # a fresh signup call with the same email must not hit 409.
    # (We mimic this by re-using the same DB mock whose lookup still returns
    # None — which mirrors the post-rollback state of real Postgres.)
    assert db.rollback.call_count >= 1

    # Second signup: Redis healthy.
    session_store_ok = MagicMock()
    session_store_ok.create_session = AsyncMock(side_effect=lambda sd: sd)

    result = await _call_signup(db, session_store_ok, email="retry@example.com")
    assert result.access_token
    assert result.refresh_token
    session_store_ok.create_session.assert_awaited_once()


# ── DB commit failure → Redis session is cleaned up ──────────────────


@pytest.mark.asyncio
async def test_db_commit_failure_deletes_persisted_redis_session(monkeypatch):
    """If the DB commit fails AFTER Redis persisted, the Redis session
    we just wrote would otherwise dangle (pointing at a user that was
    just rolled back). The fix deletes it best-effort.
    """
    from services.admin.app import auth_routes

    monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)
    monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)

    db = _make_db_no_existing_user()
    db.commit.side_effect = RuntimeError("db connection reset")

    session_store = MagicMock()
    session_store.create_session = AsyncMock(side_effect=lambda sd: sd)
    session_store.delete_session = AsyncMock(return_value=True)

    with pytest.raises(RuntimeError):
        await _call_signup(db, session_store)

    assert db.rollback.call_count >= 1
    session_store.delete_session.assert_awaited_once()
