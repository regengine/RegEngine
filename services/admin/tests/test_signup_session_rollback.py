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

import uuid as uuid_mod
from datetime import timedelta
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


# ── Correlated Redis failure — commit fails AND cleanup fails (#1692) ──


@pytest.mark.asyncio
async def test_correlated_redis_failure_does_not_mask_original_db_error(
    monkeypatch, caplog
):
    """Correlated-failure path from #1692.

    Most likely Redis failure mode is that Redis is down for BOTH
    ``create_session`` and the subsequent ``delete_session`` cleanup
    (Redis is flaky is the whole reason we have a rollback path). In
    that case:

      * the original ``db.commit()`` exception MUST propagate to the
        caller — callers and Sentry need to see the actionable DB error,
        not the secondary cleanup error that happened trying to recover;
      * the cleanup failure MUST be observable via ``__context__`` so
        operators investigating the trace can still see both legs;
      * a warning log MUST be emitted so ops can correlate the residual
        dangling Redis session (bounded by TTL — see TTL test below).
    """
    from services.admin.app import auth_routes

    monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)
    monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)

    db = _make_db_no_existing_user()
    db_error = RuntimeError("db connection reset mid-commit")
    db.commit.side_effect = db_error

    session_store = MagicMock()
    # create_session succeeds — we get past the 503 gate and into the
    # DB-commit leg.
    session_store.create_session = AsyncMock(side_effect=lambda sd: sd)
    # ...but the correlated failure hits on cleanup.
    cleanup_error = ConnectionError("redis down during cleanup")
    session_store.delete_session = AsyncMock(side_effect=cleanup_error)

    with pytest.raises(RuntimeError) as exc_info:
        await _call_signup(db, session_store)

    # The caller MUST see the DB error, not the cleanup error. Masking
    # the commit failure behind the cleanup failure would make this
    # incident undiagnosable in production.
    assert exc_info.value is db_error
    assert "db connection reset" in str(exc_info.value)

    # Both failures must have been attempted — rollback fired, cleanup
    # was tried once, and the exception chain preserves the cleanup
    # error via __context__ for operators.
    assert db.rollback.call_count >= 1
    session_store.delete_session.assert_awaited_once()

    # Exception chaining — operators can still reach the cleanup error.
    # Python implicitly sets __context__ when a new exception is raised
    # (or re-raised) inside an except block. The cleanup `except` caught
    # the ConnectionError and then `raise` re-raised the db_error, so
    # db_error.__context__ should be the cleanup_error.
    assert exc_info.value.__context__ is cleanup_error


@pytest.mark.asyncio
async def test_correlated_redis_failure_logs_residual_orphan(monkeypatch):
    """The cleanup-also-failed path MUST emit a warning log so ops can
    reconcile the dangling Redis session against TTL cleanup. We also
    verify the residual-orphan marker is present so log-based alerting
    can target this failure mode specifically.
    """
    from services.admin.app import auth_routes

    monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)
    monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)

    # Intercept structlog warnings on the auth logger. structlog is not
    # globally configured in this test env (no ``structlog.configure``),
    # so it uses ``PrintLoggerFactory`` which bypasses ``caplog``. We
    # capture calls directly off the logger instance.
    captured: list[tuple[str, dict]] = []

    def _capture_warning(event: str, **kwargs):
        captured.append((event, kwargs))

    monkeypatch.setattr(auth_routes.logger, "warning", _capture_warning)

    db = _make_db_no_existing_user()
    db.commit.side_effect = RuntimeError("db connection reset")

    session_store = MagicMock()
    session_store.create_session = AsyncMock(side_effect=lambda sd: sd)
    session_store.delete_session = AsyncMock(
        side_effect=ConnectionError("redis down during cleanup")
    )

    with pytest.raises(RuntimeError):
        await _call_signup(db, session_store)

    # Find the cleanup-failure log record.
    cleanup_logs = [
        (event, kwargs)
        for event, kwargs in captured
        if event == "signup_session_cleanup_failed"
    ]
    assert cleanup_logs, (
        f"expected a ``signup_session_cleanup_failed`` warning log; "
        f"saw events {[e for e, _ in captured]}"
    )

    # Residual-orphan marker must be present so ops-side alerts can
    # distinguish TTL-bounded dangling sessions from other cleanup
    # failures and correlate with the session's TTL expiry.
    _, kwargs = cleanup_logs[0]
    assert kwargs.get("residual_orphan") == "redis_session_dangling_until_ttl", (
        f"expected residual_orphan marker; saw {kwargs}"
    )
    assert "session_id" in kwargs, f"expected session_id in log; saw {kwargs}"
    assert "user_id" in kwargs, f"expected user_id in log; saw {kwargs}"


# ── TTL verification — signup session MUST have bounded expiry (#1692) ──


@pytest.mark.asyncio
async def test_signup_session_has_bounded_ttl(monkeypatch):
    """#1692 — the residual-orphan safety net is Redis TTL. Verify the
    ``SessionData`` passed to ``create_session`` has an ``expires_at``
    in the future (so ``RedisSessionStore._calculate_ttl`` yields a
    positive bounded TTL, not -1/no-expiry). If a regression removed
    the ``expires_at`` wiring and Redis started persisting sessions
    without expiry, a correlated-failure dangling session would survive
    forever.
    """
    from datetime import datetime, timezone

    from services.admin.app import auth_routes
    from services.admin.app.session_store import RedisSessionStore

    monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)
    monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)

    db = _make_db_no_existing_user()

    captured_session = {}

    async def _capture(session_data):
        captured_session["data"] = session_data
        return session_data

    session_store = MagicMock()
    session_store.create_session = AsyncMock(side_effect=_capture)

    await _call_signup(db, session_store)

    sd = captured_session.get("data")
    assert sd is not None, "create_session was not called with session data"

    # Sanity: expires_at must be in the future and bounded (not year 9999).
    now = datetime.now(timezone.utc)
    assert sd.expires_at > now, (
        f"signup session expires_at must be in the future; "
        f"got {sd.expires_at} vs now {now}"
    )
    # REFRESH_TOKEN_EXPIRE_DAYS is the upper bound the handler applies.
    max_allowed = now + timedelta(days=auth_routes.REFRESH_TOKEN_EXPIRE_DAYS + 1)
    assert sd.expires_at < max_allowed, (
        f"signup session TTL exceeds REFRESH_TOKEN_EXPIRE_DAYS upper bound; "
        f"got {sd.expires_at}"
    )

    # And the store's TTL calculation converts that to a bounded positive
    # number of seconds — i.e. the key will carry a real EXPIRE, not -1.
    store = RedisSessionStore("redis://unused")
    ttl_seconds = store._calculate_ttl(sd.expires_at)
    assert ttl_seconds > 0, (
        f"computed TTL must be > 0 so Redis applies EXPIRE; got {ttl_seconds}"
    )
    assert ttl_seconds <= (
        auth_routes.REFRESH_TOKEN_EXPIRE_DAYS * 86400 + 60
    ), f"computed TTL exceeds expected upper bound; got {ttl_seconds}s"


# ── Supabase orphan cleanup on DB commit failure (#1090) ─────────────


@pytest.mark.asyncio
async def test_supabase_orphan_deleted_when_db_commit_fails(monkeypatch):
    """#1090 — if the DB commit fails after Supabase already created a user,
    the handler must call ``supabase.auth.admin.delete_user(supabase_user_id)``
    so the Supabase account does not persist without a matching DB record.
    """
    from services.admin.app import auth_routes

    # Inject a fake Supabase client that records the user_id created.
    fake_sb_user_id = str(uuid_mod.uuid4())
    fake_sb_user = SimpleNamespace(id=fake_sb_user_id)
    fake_sb_response = SimpleNamespace(user=fake_sb_user)

    deleted_ids: list[str] = []

    class FakeSupabaseAuth:
        class admin:
            @staticmethod
            def create_user(_payload):
                return fake_sb_response

            @staticmethod
            def delete_user(uid: str):
                deleted_ids.append(uid)

    class FakeSupabase:
        auth = FakeSupabaseAuth()

    monkeypatch.setattr(auth_routes, "get_supabase", lambda: FakeSupabase())
    monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)

    db = _make_db_no_existing_user()
    db.commit.side_effect = RuntimeError("unique violation — duplicate email")

    session_store = MagicMock()
    session_store.create_session = AsyncMock(side_effect=lambda sd: sd)
    session_store.delete_session = AsyncMock(return_value=True)

    with pytest.raises(RuntimeError):
        await _call_signup(db, session_store)

    assert db.rollback.call_count >= 1
    assert deleted_ids == [fake_sb_user_id], (
        f"expected Supabase delete_user({fake_sb_user_id!r}); "
        f"got delete calls: {deleted_ids}"
    )


@pytest.mark.asyncio
async def test_supabase_not_created_when_supabase_is_unavailable_and_db_fails(
    monkeypatch,
):
    """#1090 — when Supabase is absent (get_supabase returns None), no
    cleanup should be attempted, and the DB commit failure still propagates.
    """
    from services.admin.app import auth_routes

    monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)
    monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)

    db = _make_db_no_existing_user()
    db.commit.side_effect = RuntimeError("unique violation")

    session_store = MagicMock()
    session_store.create_session = AsyncMock(side_effect=lambda sd: sd)
    session_store.delete_session = AsyncMock(return_value=True)

    with pytest.raises(RuntimeError, match="unique violation"):
        await _call_signup(db, session_store)

    assert db.rollback.call_count >= 1
    # No Supabase to clean up — test just verifies no AttributeError/crash.


@pytest.mark.asyncio
async def test_supabase_orphan_cleanup_failure_is_logged_and_original_error_propagates(
    monkeypatch,
):
    """#1090 — if the Supabase delete_user call itself fails, that failure
    must be logged (``signup_supabase_orphan_cleanup_failed``) and the
    original DB commit exception must still propagate to the caller.
    """
    from services.admin.app import auth_routes

    fake_sb_user_id = str(uuid_mod.uuid4())
    fake_sb_user = SimpleNamespace(id=fake_sb_user_id)
    fake_sb_response = SimpleNamespace(user=fake_sb_user)

    class FakeSupabaseAuth:
        class admin:
            @staticmethod
            def create_user(_payload):
                return fake_sb_response

            @staticmethod
            def delete_user(_uid: str):
                raise RuntimeError("supabase API unreachable")

    class FakeSupabase:
        auth = FakeSupabaseAuth()

    monkeypatch.setattr(auth_routes, "get_supabase", lambda: FakeSupabase())
    monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)

    captured: list[tuple[str, dict]] = []

    def _capture_warning(event: str, **kwargs):
        captured.append((event, kwargs))

    monkeypatch.setattr(auth_routes.logger, "warning", _capture_warning)

    db = _make_db_no_existing_user()
    db_error = RuntimeError("db commit failed")
    db.commit.side_effect = db_error

    session_store = MagicMock()
    session_store.create_session = AsyncMock(side_effect=lambda sd: sd)
    session_store.delete_session = AsyncMock(return_value=True)

    with pytest.raises(RuntimeError) as exc_info:
        await _call_signup(db, session_store)

    # Original DB error must propagate — not the Supabase cleanup error.
    assert exc_info.value is db_error

    # Cleanup failure must have been logged.
    cleanup_logs = [e for e, _ in captured if e == "signup_supabase_orphan_cleanup_failed"]
    assert cleanup_logs, (
        f"expected signup_supabase_orphan_cleanup_failed warning; "
        f"saw {[e for e, _ in captured]}"
    )
    _, kw = [item for item in captured if item[0] == "signup_supabase_orphan_cleanup_failed"][0]
    assert kw.get("residual_orphan") == "supabase_user_dangling"
    assert "supabase_user_id" in kw


@pytest.mark.asyncio
async def test_redis_create_session_applies_expire_to_every_key(monkeypatch):
    """#1692 — belt-and-braces check that ``RedisSessionStore.create_session``
    actually calls ``EXPIRE`` / ``SETEX`` on all three Redis keys with a
    positive TTL. If a refactor switched to plain ``SET`` without an
    expiry, the signup-rollback residual orphan would survive forever.
    """
    from datetime import datetime, timezone

    from services.admin.app.session_store import RedisSessionStore, SessionData

    store = RedisSessionStore("redis://unused")

    mock_client = MagicMock()
    pipe = MagicMock()
    pipe.hset = AsyncMock()
    pipe.expire = AsyncMock()
    pipe.sadd = AsyncMock()
    pipe.setex = AsyncMock()
    pipe.execute = AsyncMock(return_value=None)
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=None)
    mock_client.pipeline = MagicMock(return_value=pipe)

    async def _get_client():
        return mock_client

    monkeypatch.setattr(store, "_get_client", _get_client)

    now = datetime.now(timezone.utc)
    session_data = SessionData(
        id=uuid_mod.uuid4(),
        user_id=uuid_mod.uuid4(),
        refresh_token_hash="deadbeef",
        family_id=uuid_mod.uuid4(),
        is_revoked=False,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(hours=1),
        user_agent="pytest",
        ip_address="127.0.0.1",
    )

    await store.create_session(session_data)

    # Every key MUST be given a bounded TTL:
    #   session:{id}        → pipe.expire(..., ttl)
    #   user_sessions:{uid} → pipe.expire(..., ttl)
    #   token_hash:{hash}   → pipe.setex(..., ttl, ...)
    assert pipe.expire.await_count == 2, (
        f"expected 2 EXPIRE calls (session + user_sessions); "
        f"saw {pipe.expire.await_count}"
    )
    assert pipe.setex.await_count == 1, (
        f"expected 1 SETEX call (token_hash); saw {pipe.setex.await_count}"
    )

    # TTL passed to EXPIRE must be positive (not -1 / 0).
    for call in pipe.expire.await_args_list:
        ttl_arg = call.args[1] if len(call.args) > 1 else call.kwargs.get("time")
        assert ttl_arg is not None and ttl_arg > 0, (
            f"EXPIRE must be called with a positive TTL; got {ttl_arg}"
        )

    # TTL passed to SETEX (positional arg 1) must be positive.
    setex_call = pipe.setex.await_args_list[0]
    setex_ttl = setex_call.args[1] if len(setex_call.args) > 1 else None
    assert setex_ttl is not None and setex_ttl > 0, (
        f"SETEX must be called with a positive TTL; got {setex_ttl}"
    )
