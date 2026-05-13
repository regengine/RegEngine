from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_repo_root = Path(__file__).resolve().parents[3]
_service_dir = Path(__file__).resolve().parents[2]
for _p in (_repo_root, _service_dir):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

os.environ.setdefault("ADMIN_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AUTH_SECRET_KEY", "session-lifecycle-auth-audit-test-secret")
os.environ.setdefault("SESSION_STORE_BACKEND", "memory")


def _request(headers: dict[str, str] | None = None):
    return SimpleNamespace(
        headers=headers or {},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(),
    )


def _user(user_id: uuid.UUID | None = None, *, sysadmin: bool = True):
    return SimpleNamespace(
        id=user_id or uuid.uuid4(),
        email="alice@example.com",
        password_hash="hashed",
        status="active",
        is_sysadmin=sysadmin,
        token_version=0,
        last_login_at=None,
    )


def _tenant():
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="Acme Corp",
        slug="acme",
        status="active",
    )


def _membership(user_id: uuid.UUID, tenant_id: uuid.UUID, role_id: uuid.UUID | None = None):
    return SimpleNamespace(
        user_id=user_id,
        tenant_id=tenant_id,
        role_id=role_id or uuid.uuid4(),
        is_active=True,
    )


def _role(role_id: uuid.UUID):
    return SimpleNamespace(id=role_id, name="Owner", permissions=["*"])


def _db_for_user(user):
    db = MagicMock()
    db.bind = None
    db.get.return_value = user
    db.commit.return_value = None
    return db


def _session(user_id: uuid.UUID, *, session_id: uuid.UUID | None = None, **overrides):
    from services.admin.app.session_store import SessionData

    now = datetime.now(timezone.utc)
    data = dict(
        id=session_id or uuid.uuid4(),
        user_id=user_id,
        refresh_token_hash="hash-" + uuid.uuid4().hex,
        family_id=uuid.uuid4(),
        is_revoked=False,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=7),
        user_agent="pytest",
        ip_address="127.0.0.1",
    )
    data.update(overrides)
    return SessionData(**data)


@pytest.mark.asyncio
async def test_login_access_token_carries_sid_and_session_id(monkeypatch):
    from services.admin.app.auth.login_router import login
    from services.admin.app.auth_utils import decode_access_token
    from services.admin.app.session_store import InMemorySessionStore

    user = _user(sysadmin=False)
    tenant = _tenant()
    membership = _membership(user.id, tenant.id)
    role = _role(membership.role_id)
    store = InMemorySessionStore()

    db = MagicMock()
    db.commit.return_value = None

    def _execute(_stmt):
        result = MagicMock()
        if not hasattr(_execute, "calls"):
            _execute.calls = 0
        if _execute.calls == 0:
            result.scalar_one_or_none.return_value = user
        else:
            result.all.return_value = [(membership, tenant, role)]
        _execute.calls += 1
        return result

    db.execute.side_effect = _execute
    monkeypatch.setattr("services.admin.app.auth.login_router.verify_login", lambda *_: True)
    monkeypatch.setattr(
        "services.admin.app.auth.login_router.AuditLogger.log_event",
        lambda *_, **__: None,
    )

    payload = SimpleNamespace(email="Alice@Example.com", password="correct")
    result = await login.__wrapped__(payload, _request({"User-Agent": "pytest"}), db=db, session_store=store)
    claims = decode_access_token(result.access_token)
    sessions = await store.list_user_sessions(user.id)

    assert len(sessions) == 1
    assert claims["sid"] == str(sessions[0].id)
    assert claims["session_id"] == str(sessions[0].id)


@pytest.mark.asyncio
async def test_refresh_access_token_carries_sid_and_session_id():
    from services.admin.app.auth.refresh_router import RefreshRequest, refresh_session
    from services.admin.app.auth_utils import create_access_token, decode_access_token, hash_token
    from services.admin.app.session_store import InMemorySessionStore

    user = _user(sysadmin=False)
    tenant = _tenant()
    membership = _membership(user.id, tenant.id)
    role = _role(membership.role_id)
    raw_refresh = "refresh-token"
    session = _session(user.id, refresh_token_hash=hash_token(raw_refresh))
    store = InMemorySessionStore()
    await store.create_session(session)

    db = MagicMock()
    db.commit.return_value = None
    db.execute.return_value.scalars.return_value.all.return_value = [membership]

    def _get(model, ident):
        from services.admin.app.sqlalchemy_models import RoleModel, TenantModel, UserModel

        if model is UserModel:
            return user
        if model is TenantModel:
            return tenant
        if model is RoleModel:
            return role
        return None

    db.get.side_effect = _get
    old_access = create_access_token({"sub": str(user.id), "tenant_id": str(tenant.id), "tv": 0})
    result = await refresh_session.__wrapped__(
        RefreshRequest(refresh_token=raw_refresh),
        _request({"Authorization": f"Bearer {old_access}"}),
        db=db,
        session_store=store,
    )

    claims = decode_access_token(result.access_token)
    assert claims["sid"] == str(session.id)
    assert claims["session_id"] == str(session.id)


@pytest.mark.asyncio
async def test_logout_revokes_current_jti_session_and_blocks_replay(monkeypatch):
    from fastapi import HTTPException
    from services.admin.app import dependencies
    from services.admin.app.auth.sessions_router import logout
    from services.admin.app.auth_utils import create_access_token, hash_token
    from services.admin.app.session_store import InMemorySessionStore

    monkeypatch.setattr(dependencies, "get_supabase", lambda: None)
    user = _user()
    session = _session(user.id, refresh_token_hash=hash_token("refresh"))
    store = InMemorySessionStore()
    await store.create_session(session)

    token = create_access_token({"sub": str(user.id), "sid": str(session.id), "session_id": str(session.id), "tv": 0})
    db = _db_for_user(user)

    await dependencies.get_current_user(token=token, db=db, session_store=store)
    result = await logout(
        request=_request({"Authorization": f"Bearer {token}"}),
        current_user=user,
        session_store=store,
    )

    assert result == {"status": "success"}
    assert await store.claim_session_by_token(hash_token("refresh")) is None
    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_user(token=token, db=db, session_store=store)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_legacy_no_sid_logout_revokes_jti(monkeypatch):
    from fastapi import HTTPException
    from services.admin.app import dependencies
    from services.admin.app.auth.sessions_router import logout
    from services.admin.app.auth_utils import create_access_token
    from services.admin.app.session_store import InMemorySessionStore

    monkeypatch.setattr(dependencies, "get_supabase", lambda: None)
    user = _user()
    token = create_access_token({"sub": str(user.id), "tv": 0})
    db = _db_for_user(user)
    store = InMemorySessionStore()

    await logout(
        request=_request({"Authorization": f"Bearer {token}"}),
        current_user=user,
        session_store=store,
    )
    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_user(token=token, db=db, session_store=store)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_rejects_revoked_session_bound_token(monkeypatch):
    from fastapi import HTTPException
    from services.admin.app import dependencies
    from services.admin.app.auth_utils import create_access_token
    from services.admin.app.session_store import InMemorySessionStore

    monkeypatch.setattr(dependencies, "get_supabase", lambda: None)
    user = _user()
    session = _session(user.id, is_revoked=True)
    store = InMemorySessionStore()
    await store.create_session(session)
    token = create_access_token({"sub": str(user.id), "sid": str(session.id), "session_id": str(session.id), "tv": 0})

    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_user(token=token, db=_db_for_user(user), session_store=store)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_returns_503_when_session_store_unavailable(monkeypatch):
    from fastapi import HTTPException
    from services.admin.app import dependencies
    from services.admin.app.auth_utils import create_access_token

    monkeypatch.setattr(dependencies, "get_supabase", lambda: None)
    user = _user()
    session_id = uuid.uuid4()
    store = MagicMock()
    store.get_session = AsyncMock(side_effect=ConnectionError("redis unavailable"))
    token = create_access_token({"sub": str(user.id), "sid": str(session_id), "session_id": str(session_id), "tv": 0})

    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_user(token=token, db=_db_for_user(user), session_store=store)

    assert exc.value.status_code == 503
    assert exc.value.detail == "Authentication service temporarily unavailable"


@pytest.mark.asyncio
async def test_refresh_enforces_idle_timeout_and_revokes(monkeypatch):
    from fastapi import HTTPException
    from services.admin.app.auth import refresh_router
    from services.admin.app.auth.refresh_router import RefreshRequest

    user = _user()
    session = _session(
        user.id,
        last_used_at=datetime.now(timezone.utc) - timedelta(minutes=6),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    store = MagicMock()
    store.claim_session_by_token = AsyncMock(return_value=session)
    store.revoke_session = AsyncMock(return_value=True)

    monkeypatch.setattr(refresh_router, "SESSION_IDLE_TIMEOUT_MINUTES", 5)
    with pytest.raises(HTTPException) as exc:
        await refresh_router.refresh_session.__wrapped__(
            RefreshRequest(refresh_token="raw"),
            _request(),
            db=MagicMock(),
            session_store=store,
        )
    assert exc.value.status_code == 401
    assert exc.value.detail == "Session idle timeout"
    store.revoke_session.assert_awaited_once_with(session.id)


@pytest.mark.asyncio
async def test_refresh_absolute_timeout_still_wins(monkeypatch):
    from fastapi import HTTPException
    from services.admin.app.auth import refresh_router
    from services.admin.app.auth.refresh_router import RefreshRequest

    session = _session(
        uuid.uuid4(),
        last_used_at=datetime.now(timezone.utc) - timedelta(days=2),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    store = MagicMock()
    store.claim_session_by_token = AsyncMock(return_value=session)
    store.revoke_session = AsyncMock(return_value=True)

    monkeypatch.setattr(refresh_router.auth_utils, "SESSION_IDLE_TIMEOUT_MINUTES", 1)
    with pytest.raises(HTTPException) as exc:
        await refresh_router.refresh_session.__wrapped__(
            RefreshRequest(refresh_token="raw"),
            _request(),
            db=MagicMock(),
            session_store=store,
        )
    assert exc.value.status_code == 401
    assert exc.value.detail == "Session expired"
    store.revoke_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_reuse_detection_still_revokes_family():
    from fastapi import HTTPException
    from services.admin.app.auth.refresh_router import RefreshRequest, refresh_session

    user_id = uuid.uuid4()
    session = _session(user_id)
    store = MagicMock()
    store.claim_session_by_token = AsyncMock(return_value=None)
    store.check_token_reuse = AsyncMock(return_value=session.id)
    store.get_session = AsyncMock(return_value=session)
    store.revoke_all_for_family = AsyncMock(return_value=1)

    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None

    with pytest.raises(HTTPException) as exc:
        await refresh_session.__wrapped__(
            RefreshRequest(refresh_token="raw"),
            _request(),
            db=db,
            session_store=store,
        )
    assert exc.value.status_code == 401
    assert exc.value.detail == "Refresh token reuse detected"
    store.revoke_all_for_family.assert_awaited_once_with(session.family_id)


@pytest.mark.asyncio
async def test_logout_all_revokes_sessions_and_bumps_token_version():
    from services.admin.app.auth.sessions_router import revoke_all_sessions
    from services.admin.app.session_store import InMemorySessionStore

    user = _user()
    store = InMemorySessionStore()
    await store.create_session(_session(user.id))
    await store.create_session(_session(user.id))
    db = _db_for_user(user)

    result = await revoke_all_sessions(current_user=user, db=db, session_store=store)

    assert result["status"] == "success"
    assert result["revoked_count"] == 2
    assert user.token_version == 1
    assert await store.list_user_sessions(user.id, active_only=True) == []


@pytest.mark.asyncio
async def test_multiple_active_sessions_are_allowed(monkeypatch):
    from services.admin.app import dependencies
    from services.admin.app.auth_utils import create_access_token
    from services.admin.app.session_store import InMemorySessionStore

    monkeypatch.setattr(dependencies, "get_supabase", lambda: None)
    user = _user()
    store = InMemorySessionStore()
    first = await store.create_session(_session(user.id))
    second = await store.create_session(_session(user.id))
    db = _db_for_user(user)

    active_sessions = await store.list_user_sessions(user.id, active_only=True)
    first_token = create_access_token({"sub": str(user.id), "sid": str(first.id), "session_id": str(first.id), "tv": 0})
    second_token = create_access_token({"sub": str(user.id), "sid": str(second.id), "session_id": str(second.id), "tv": 0})

    assert {s.id for s in active_sessions} == {first.id, second.id}
    assert await dependencies.get_current_user(token=first_token, db=db, session_store=store) == user
    assert await dependencies.get_current_user(token=second_token, db=db, session_store=store) == user
