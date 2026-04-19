"""Regression tests for #1071 — cross-worker token revocation.

Before the fix, ``_check_revoked`` tried to consult Redis via
``loop.run_until_complete`` from a sync function. Whenever FastAPI was
already running the event loop — which is always, for every request —
that branch silently no-op'd, so a token revoked by worker A (writing
to Redis) remained valid on worker B until B's in-memory
``_revoked_jtis`` set happened to pick it up. In a multi-worker deploy
this meant up-to-TTL acceptance of revoked tokens on every worker that
did not itself process the logout.

These tests pin the new contract:

    1. ``_check_revoked`` is now in-memory only. It deliberately does
       NOT reach for Redis — the sync path cannot make that work.
    2. ``check_revoked_async`` is the async authoritative check; it
       reads Redis, and a hit is cached into the in-memory set so
       subsequent requests on the same worker short-circuit.
    3. :func:`services.admin.app.dependencies.get_current_user` calls
       ``check_revoked_async`` on every local-JWT path and raises 401
       if the jti is in Redis even when the in-memory set is empty
       (the cross-worker case — the whole point of #1071).
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
import pytest
from fastapi import HTTPException


# ─────────────────────────────────────────────────────────────────────
# Unit — _check_revoked is in-memory only
# ─────────────────────────────────────────────────────────────────────


def test_check_revoked_does_not_touch_redis(monkeypatch):
    """Even when _revocation_redis is set, the sync _check_revoked
    must never call into it. The sync-under-async-loop path was the
    bug — prove it is gone.

    Rationale: any attempt to consult Redis from a sync function under
    a running event loop silently fails, so an implementation that
    appears to check Redis and actually doesn't is worse than one that
    explicitly doesn't — the latter is obviously wrong, the former
    lulls reviewers into thinking revocation is cross-worker.
    """
    from services.admin.app import auth_utils

    # A Redis-shaped mock whose methods should never be called.
    redis_mock = MagicMock()
    redis_mock.sismember = MagicMock(
        side_effect=AssertionError(
            "_check_revoked must not call Redis — the sync path silently "
            "no-ops under a running event loop (#1071)"
        )
    )
    monkeypatch.setattr(auth_utils, "_revocation_redis", redis_mock)

    # Clean in-memory state so the jti is not already present.
    jti = f"jti-{uuid.uuid4()}"
    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())

    payload = {"jti": jti, "sub": "u1"}
    assert auth_utils._check_revoked(payload) is payload
    redis_mock.sismember.assert_not_called()


def test_check_revoked_rejects_on_in_memory_hit(monkeypatch):
    from services.admin.app import auth_utils

    jti = f"jti-{uuid.uuid4()}"
    monkeypatch.setattr(auth_utils, "_revoked_jtis", {jti})

    with pytest.raises(pyjwt.exceptions.InvalidTokenError):
        auth_utils._check_revoked({"jti": jti, "sub": "u1"})


def test_check_revoked_legacy_token_without_jti_passes(monkeypatch):
    """Tokens minted before the jti claim existed have no individual
    revocation handle — the sync fast-path must let them through so
    auth doesn't regress on existing sessions."""
    from services.admin.app import auth_utils

    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    payload = {"sub": "u1"}  # no jti
    assert auth_utils._check_revoked(payload) is payload


# ─────────────────────────────────────────────────────────────────────
# Unit — check_revoked_async consults Redis and caches on hit
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_revoked_async_hits_redis_and_caches(monkeypatch):
    """The cross-worker case: in-memory empty, Redis has the jti → True.
    Hit is cached so subsequent calls on this worker short-circuit."""
    from services.admin.app import auth_utils

    jti = f"jti-{uuid.uuid4()}"
    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())

    redis_mock = MagicMock()
    redis_mock.sismember = AsyncMock(return_value=True)
    monkeypatch.setattr(auth_utils, "_revocation_redis", redis_mock)

    assert await auth_utils.check_revoked_async(jti) is True
    redis_mock.sismember.assert_awaited_once_with("regengine:jwt:revoked", jti)
    # Cached locally
    assert jti in auth_utils._revoked_jtis

    # Second call hits the in-memory fast path — no more Redis calls.
    assert await auth_utils.check_revoked_async(jti) is True
    assert redis_mock.sismember.await_count == 1


@pytest.mark.asyncio
async def test_check_revoked_async_returns_false_when_not_revoked(monkeypatch):
    from services.admin.app import auth_utils

    jti = f"jti-{uuid.uuid4()}"
    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    redis_mock = MagicMock()
    redis_mock.sismember = AsyncMock(return_value=False)
    monkeypatch.setattr(auth_utils, "_revocation_redis", redis_mock)

    assert await auth_utils.check_revoked_async(jti) is False
    assert jti not in auth_utils._revoked_jtis  # NOT cached — still live


@pytest.mark.asyncio
async def test_check_revoked_async_no_redis_returns_false(monkeypatch):
    """Dev environments may not wire Redis. The async check should
    degrade to the in-memory set without raising."""
    from services.admin.app import auth_utils

    monkeypatch.setattr(auth_utils, "_revocation_redis", None)
    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())

    assert await auth_utils.check_revoked_async("some-jti") is False


@pytest.mark.asyncio
async def test_check_revoked_async_empty_jti_returns_false(monkeypatch):
    from services.admin.app import auth_utils

    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    monkeypatch.setattr(auth_utils, "_revocation_redis", MagicMock())
    # Empty string and None are both treated as "no jti" — we must not
    # poison the in-memory set with an empty key and we must not call
    # Redis for a legacy token.
    assert await auth_utils.check_revoked_async("") is False
    assert await auth_utils.check_revoked_async(None) is False  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_check_revoked_async_redis_error_fails_permissive(monkeypatch):
    """Redis transient error → best-effort fallback to in-memory.

    The alternative (fail closed on every Redis hiccup) makes every
    request 401 whenever Redis blips, which we've decided is the wrong
    tradeoff: the worker that issued the revocation still blocks the
    token, and logout is audited in the DB."""
    from services.admin.app import auth_utils

    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    redis_mock = MagicMock()
    redis_mock.sismember = AsyncMock(side_effect=ConnectionError("redis down"))
    monkeypatch.setattr(auth_utils, "_revocation_redis", redis_mock)

    # Must not raise.
    assert await auth_utils.check_revoked_async("jti-x") is False


# ─────────────────────────────────────────────────────────────────────
# Integration — get_current_user rejects cross-worker-revoked jti
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_current_user_rejects_redis_revoked_jti(monkeypatch):
    """The core #1071 regression:

    * Worker A: ``revoke_token(jti)`` writes jti to Redis + A's
      in-memory set.
    * Worker B: request arrives with the same jti. B's in-memory set
      is still empty (A didn't push, or pub/sub hasn't fanned out).

    Pre-fix: B accepted the token because the sync ``_check_revoked``
    silently skipped Redis.
    Post-fix: B's ``get_current_user`` awaits ``check_revoked_async``,
    hits Redis, sees the jti, and 401s.
    """
    from services.admin.app import auth_utils, dependencies
    from services.admin.app.auth_utils import create_access_token

    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    # Supabase disabled — force the local JWT fallback path.
    monkeypatch.setattr(dependencies, "get_supabase", lambda: None)

    tok = create_access_token(
        {
            "sub": str(user_id),
            "tenant_id": str(tenant_id),
            "tv": 0,
        }
    )
    # Decode to grab the auto-generated jti for the Redis mock.
    decoded = pyjwt.decode(tok, options={"verify_signature": False})
    jti = decoded["jti"]

    # Worker B: in-memory set does NOT yet contain the jti.
    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    # Redis DOES contain it (it was written by worker A).
    redis_mock = MagicMock()
    redis_mock.sismember = AsyncMock(return_value=True)
    monkeypatch.setattr(auth_utils, "_revocation_redis", redis_mock)

    user = SimpleNamespace(
        id=user_id,
        email="u@e",
        is_sysadmin=False,
        status="active",
        token_version=0,
    )
    db = MagicMock()
    db.bind = None
    db.get.return_value = user

    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_user(token=tok, db=db)
    assert exc.value.status_code == 401
    redis_mock.sismember.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_current_user_accepts_non_revoked_jti(monkeypatch):
    """Happy path — same shape as the rejection test but Redis returns
    False. The request must succeed so we know the new check isn't
    accidentally rejecting valid tokens."""
    from services.admin.app import auth_utils, dependencies
    from services.admin.app.auth_utils import create_access_token

    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    monkeypatch.setattr(dependencies, "get_supabase", lambda: None)

    tok = create_access_token(
        {"sub": str(user_id), "tenant_id": str(tenant_id), "tv": 3}
    )

    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    redis_mock = MagicMock()
    redis_mock.sismember = AsyncMock(return_value=False)
    monkeypatch.setattr(auth_utils, "_revocation_redis", redis_mock)

    user = SimpleNamespace(
        id=user_id,
        email="u@e",
        is_sysadmin=False,
        status="active",
        token_version=3,
    )
    db = MagicMock()
    db.bind = None
    db.get.return_value = user
    membership = SimpleNamespace(is_active=True)
    db.execute.return_value.scalar_one_or_none.return_value = membership
    db.execute.return_value.scalars.return_value.all.return_value = [membership]

    out = await dependencies.get_current_user(token=tok, db=db)
    assert out is user


@pytest.mark.asyncio
async def test_get_current_user_rejects_in_memory_revoked_jti(monkeypatch):
    """Belt-and-braces: if the jti is already in the worker's own
    in-memory set (e.g. this worker issued the revoke), the async path
    must still reject it — the short-circuit branch is what keeps us
    from hitting Redis on every subsequent request."""
    from services.admin.app import auth_utils, dependencies
    from services.admin.app.auth_utils import create_access_token

    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    monkeypatch.setattr(dependencies, "get_supabase", lambda: None)

    tok = create_access_token(
        {"sub": str(user_id), "tenant_id": str(tenant_id), "tv": 0}
    )
    decoded = pyjwt.decode(tok, options={"verify_signature": False})
    jti = decoded["jti"]

    # In-memory set already carries the revocation (this worker did it).
    monkeypatch.setattr(auth_utils, "_revoked_jtis", {jti})
    # Redis intentionally unreachable — in-memory must short-circuit
    # before Redis is consulted.
    monkeypatch.setattr(auth_utils, "_revocation_redis", None)

    user = SimpleNamespace(
        id=user_id,
        email="u@e",
        is_sysadmin=False,
        status="active",
        token_version=0,
    )
    db = MagicMock()
    db.bind = None
    db.get.return_value = user

    # decode_access_token itself raises on the in-memory hit, which
    # the dependency maps to 401.
    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_user(token=tok, db=db)
    assert exc.value.status_code == 401
