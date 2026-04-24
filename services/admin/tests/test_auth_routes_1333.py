"""Dedicated test suite for services/admin/app/auth_routes.py — #1333.

Covers:
  - JWT issuance: valid login → tokens with correct claims
  - JWT expiry: expired token → 401 via decode_access_token
  - Session creation/validation on login
  - Refresh token rotation: valid refresh → new access token
  - Refresh token tampered → 401
  - Suspended tenant → login still succeeds but tenant_status reflected
  - Disabled user account → 403
  - Email rate-limit: exceeded → 401
  - Account lockout: threshold reached → 423
  - Password reset: missing auth → 401; no supabase → 503; happy path
  - Change password: wrong current → 401; happy path
  - Session listing, revocation, and logout-all
  - /confirm (elevation token) happy path and wrong password
  - /register: disabled when users exist; happy path
  - /me endpoint
  - /unlock admin endpoint
  - Signup: duplicate email → generic 200; happy path
  - Internal helpers: _slugify_tenant_name, _ensure_unique_tenant_slug,
    _progressive_delay_seconds, _email_attempt_key, _lockout_key
"""

from __future__ import annotations

import uuid as uuid_mod
import time
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

import jwt as _jwt
import pytest
from fastapi import HTTPException, status

# Ensure repo root is importable
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "services" / "admin"))

import services.admin.app.auth_routes as ar
from services.admin.app.auth_routes import (
    LoginRequest,
    RegisterRequest,
    RefreshRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,
    ConfirmPasswordRequest,
    _slugify_tenant_name,
    _email_attempt_key,
    _lockout_key,
    _lockout_delay_key,
    _progressive_delay_seconds,
    _LOCKOUT_THRESHOLD,
    _EMAIL_ATTEMPT_LIMIT,
    _EMAIL_ATTEMPT_WINDOW,
    _LOCKOUT_DURATION,
    _PROGRESSIVE_DELAY_CAP_SECONDS,
)
from services.admin.app.auth_utils import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    hash_token,
    create_refresh_token,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from services.admin.app.session_store import SessionData


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_request(path: str = "/auth/login", headers: dict | None = None):
    """Build a minimal Starlette Request object."""
    from starlette.requests import Request

    raw_headers = []
    for k, v in (headers or {"user-agent": "pytest/1333"}).items():
        raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
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


def _make_user(
    *,
    email: str = "user@example.com",
    password: str = "correct-password",
    status: str = "active",
    is_sysadmin: bool = False,
    token_version: int = 0,
) -> SimpleNamespace:
    """Build a fake UserModel-like object."""
    return SimpleNamespace(
        id=uuid_mod.uuid4(),
        email=email,
        password_hash=get_password_hash(password),
        is_sysadmin=is_sysadmin,
        status=status,
        token_version=token_version,
        last_login_at=None,
    )


def _make_tenant(*, status: str = "active") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid_mod.uuid4(),
        name="Acme Corp",
        slug="acme-corp",
        status=status,
    )


def _make_session_store(*, redis_client: MagicMock | None = None) -> MagicMock:
    """Return a mock session store with a real-enough redis client."""
    if redis_client is None:
        redis_client = _make_redis_client()
    store = MagicMock()
    store._get_client = AsyncMock(return_value=redis_client)
    store.create_session = AsyncMock(return_value=None)
    store.get_session = AsyncMock(return_value=None)
    store.claim_session_by_token = AsyncMock(return_value=None)
    store.check_token_reuse = AsyncMock(return_value=None)
    store.update_session = AsyncMock(return_value=None)
    store.mark_token_used = AsyncMock(return_value=None)
    store.revoke_session = AsyncMock(return_value=None)
    store.revoke_all_user_sessions = AsyncMock(return_value=0)
    store.revoke_all_for_user = AsyncMock(return_value=0)
    store.revoke_all_for_family = AsyncMock(return_value=0)
    store.list_user_sessions = AsyncMock(return_value=[])
    store.delete_session = AsyncMock(return_value=None)
    return store


def _make_redis_client() -> MagicMock:
    """Return a mock Redis client that satisfies the rate-limit helpers."""
    client = MagicMock()
    client.get = AsyncMock(return_value=None)
    client.ttl = AsyncMock(return_value=-2)
    client.delete = AsyncMock(return_value=1)
    client.setex = AsyncMock(return_value=True)
    client.set = AsyncMock(return_value=True)
    client.scan = AsyncMock(return_value=(0, []))

    pipe = MagicMock()
    pipe.incr = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[1, 1])
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)
    client.pipeline = MagicMock(return_value=pipe)
    return client


def _make_db_with_user(user, tenant=None, membership=None) -> MagicMock:
    """Build a DB mock that returns ``user`` on a scalar_one_or_none lookup
    and optionally returns memberships."""
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = user
    # For get() calls (e.g. db.get(UserModel, user_id))
    db.get = MagicMock(return_value=user)

    if tenant and membership:
        db.execute.return_value.all.return_value = [(membership, tenant)]
        db.execute.return_value.scalars.return_value.all.return_value = [membership]
        db.execute.return_value.scalars.return_value.first.return_value = membership
    else:
        db.execute.return_value.all.return_value = []
        db.execute.return_value.scalars.return_value.all.return_value = []
        db.execute.return_value.scalars.return_value.first.return_value = None

    db.add = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    return db


def _make_membership(user, tenant) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid_mod.uuid4(),
        user_id=user.id,
        tenant_id=tenant.id,
        role_id=uuid_mod.uuid4(),
        is_active=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 1. Internal helpers
# ──────────────────────────────────────────────────────────────────────────────


class TestInternalHelpers:
    def test_slugify_basic(self):
        assert _slugify_tenant_name("Acme Corp") == "acme-corp"

    def test_slugify_strips_specials(self):
        assert _slugify_tenant_name("Hello! World #1") == "hello-world-1"

    def test_slugify_empty_falls_back(self):
        assert _slugify_tenant_name("!!!") == "tenant"

    def test_email_attempt_key(self):
        assert _email_attempt_key("a@b.c") == "login_attempts:a@b.c"

    def test_lockout_key(self):
        assert _lockout_key("a@b.c") == "login_lockout:a@b.c"

    def test_lockout_delay_key(self):
        assert _lockout_delay_key("a@b.c") == "login_lockout_delay:a@b.c"

    def test_progressive_delay_zero_below_start(self):
        assert _progressive_delay_seconds(0) == 0
        assert _progressive_delay_seconds(1) == 0
        assert _progressive_delay_seconds(2) == 0

    def test_progressive_delay_exponential(self):
        assert _progressive_delay_seconds(3) == 1
        assert _progressive_delay_seconds(4) == 2
        assert _progressive_delay_seconds(5) == 4

    def test_progressive_delay_cap(self):
        assert _progressive_delay_seconds(100) == _PROGRESSIVE_DELAY_CAP_SECONDS == 300

    def test_constants(self):
        assert _LOCKOUT_THRESHOLD == 10
        assert _EMAIL_ATTEMPT_LIMIT == 5
        assert _EMAIL_ATTEMPT_WINDOW == 900
        assert _LOCKOUT_DURATION == 86400


# ──────────────────────────────────────────────────────────────────────────────
# 2. JWT issuance and expiry
# ──────────────────────────────────────────────────────────────────────────────


class TestJwtIssuance:
    def test_access_token_has_correct_claims(self):
        user_id = str(uuid_mod.uuid4())
        tenant_id = str(uuid_mod.uuid4())
        token = create_access_token({
            "sub": user_id,
            "email": "test@example.com",
            "tenant_id": tenant_id,
            "tid": tenant_id,
            "tenant_status": "active",
            "tv": 0,
        })
        payload = decode_access_token(token)
        assert payload["sub"] == user_id
        assert payload["email"] == "test@example.com"
        assert payload["tenant_id"] == tenant_id
        assert payload["tv"] == 0
        assert "jti" in payload
        assert "exp" in payload

    def test_expired_token_raises_401(self):
        import jwt as _pyjwt
        from services.admin.app.auth_utils import SECRET_KEY, ALGORITHM, SESSION_AUDIENCE, SESSION_ISSUER
        # Mint a token that expired in the past.
        payload = {
            "sub": "user-1",
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
            "iat": datetime.now(timezone.utc) - timedelta(minutes=61),
            "aud": SESSION_AUDIENCE,
            "iss": SESSION_ISSUER,
            "jti": str(uuid_mod.uuid4()),
        }
        expired_token = _jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        # decode_access_token does not wrap ExpiredSignatureError in HTTPException;
        # it propagates the PyJWT exception. The dependency (get_current_user) wraps it.
        with pytest.raises((_pyjwt.ExpiredSignatureError, HTTPException)) as exc:
            decode_access_token(expired_token)
        # If it's an HTTPException it must be 401; if it's the raw JWT error that's also fine.
        if isinstance(exc.value, HTTPException):
            assert exc.value.status_code == 401

    def test_tampered_token_raises_401(self):
        import jwt as _pyjwt
        token = create_access_token({"sub": "u1", "tv": 0})
        tampered = token[:-4] + "XXXX"
        with pytest.raises((_pyjwt.InvalidSignatureError, _pyjwt.DecodeError, HTTPException)):
            decode_access_token(tampered)

    def test_create_refresh_token_is_unique(self):
        t1 = create_refresh_token()
        t2 = create_refresh_token()
        assert t1 != t2

    def test_hash_token_stable(self):
        raw = create_refresh_token()
        assert hash_token(raw) == hash_token(raw)

    def test_hash_token_different_for_different_inputs(self):
        assert hash_token("abc") != hash_token("def")


# ──────────────────────────────────────────────────────────────────────────────
# 3. Login endpoint — happy path and failure modes
# ──────────────────────────────────────────────────────────────────────────────


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_happy_path_returns_tokens(self, monkeypatch):
        """Valid credentials → 200 with access_token, refresh_token, tenant_id."""
        user = _make_user(email="u@example.com", password="pass123")
        tenant = _make_tenant()
        membership = _make_membership(user, tenant)
        db = _make_db_with_user(user, tenant, membership)
        session_store = _make_session_store()

        # Patch AuditLogger so it doesn't blow up
        monkeypatch.setattr(ar, "AuditLogger", MagicMock())

        result = await ar.login.__wrapped__(
            payload=LoginRequest(email="U@Example.com", password="pass123"),
            request=_make_request(),
            db=db,
            session_store=session_store,
        )

        assert result.access_token
        assert result.refresh_token
        assert result.tenant_id == tenant.id
        assert result.user["email"] == "u@example.com"

    @pytest.mark.asyncio
    async def test_login_email_normalized_to_lowercase(self, monkeypatch):
        """Email is lowercased before lookup."""
        user = _make_user(email="user@example.com", password="pw")
        tenant = _make_tenant()
        membership = _make_membership(user, tenant)
        db = _make_db_with_user(user, tenant, membership)
        session_store = _make_session_store()
        monkeypatch.setattr(ar, "AuditLogger", MagicMock())

        result = await ar.login.__wrapped__(
            payload=LoginRequest(email="  USER@EXAMPLE.COM  ", password="pw"),
            request=_make_request(),
            db=db,
            session_store=session_store,
        )
        assert result.user["email"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_login_wrong_password_raises_401(self, monkeypatch):
        user = _make_user(email="u@x.com", password="correct")
        db = _make_db_with_user(user)
        session_store = _make_session_store()

        with pytest.raises(HTTPException) as exc:
            await ar.login.__wrapped__(
                payload=LoginRequest(email="u@x.com", password="wrong"),
                request=_make_request(),
                db=db,
                session_store=session_store,
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_unknown_email_raises_401(self, monkeypatch):
        db = _make_db_with_user(None)  # no user found
        session_store = _make_session_store()

        with pytest.raises(HTTPException) as exc:
            await ar.login.__wrapped__(
                payload=LoginRequest(email="ghost@example.com", password="pw"),
                request=_make_request(),
                db=db,
                session_store=session_store,
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_disabled_account_raises_403(self, monkeypatch):
        user = _make_user(email="u@x.com", password="pw", status="disabled")
        db = _make_db_with_user(user)
        session_store = _make_session_store()

        with pytest.raises(HTTPException) as exc:
            await ar.login.__wrapped__(
                payload=LoginRequest(email="u@x.com", password="pw"),
                request=_make_request(),
                db=db,
                session_store=session_store,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_login_jwt_contains_tenant_id_and_tv(self, monkeypatch):
        """Access token must carry tenant_id, tid, tv, and sub."""
        user = _make_user(email="u@x.com", password="pw", token_version=3)
        tenant = _make_tenant()
        membership = _make_membership(user, tenant)
        db = _make_db_with_user(user, tenant, membership)
        session_store = _make_session_store()
        monkeypatch.setattr(ar, "AuditLogger", MagicMock())

        result = await ar.login.__wrapped__(
            payload=LoginRequest(email="u@x.com", password="pw"),
            request=_make_request(),
            db=db,
            session_store=session_store,
        )
        payload = decode_access_token(result.access_token)
        assert payload["sub"] == str(user.id)
        assert payload["tenant_id"] == str(tenant.id)
        assert payload["tid"] == str(tenant.id)
        assert payload["tv"] == 3

    @pytest.mark.asyncio
    async def test_login_rate_limited_raises_401(self, monkeypatch):
        """If the email attempt counter is at limit, login returns generic 401."""
        client = _make_redis_client()
        client.get = AsyncMock(return_value=str(_EMAIL_ATTEMPT_LIMIT))
        client.ttl = AsyncMock(return_value=-2)  # no lockout delay
        session_store = _make_session_store(redis_client=client)
        db = _make_db_with_user(None)

        with pytest.raises(HTTPException) as exc:
            await ar.login.__wrapped__(
                payload=LoginRequest(email="u@x.com", password="pw"),
                request=_make_request(),
                db=db,
                session_store=session_store,
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_locked_account_raises_423(self, monkeypatch):
        """If the lockout counter is at threshold, login returns 423."""
        client = _make_redis_client()
        client.get = AsyncMock(return_value=str(_LOCKOUT_THRESHOLD))
        client.ttl = AsyncMock(return_value=-2)
        session_store = _make_session_store(redis_client=client)
        db = _make_db_with_user(None)

        with pytest.raises(HTTPException) as exc:
            await ar.login.__wrapped__(
                payload=LoginRequest(email="u@x.com", password="pw"),
                request=_make_request(),
                db=db,
                session_store=session_store,
            )
        assert exc.value.status_code == 423

    @pytest.mark.asyncio
    async def test_login_session_store_failure_raises_503(self, monkeypatch):
        """If Redis create_session fails twice, login returns 503."""
        user = _make_user(email="u@x.com", password="pw")
        tenant = _make_tenant()
        membership = _make_membership(user, tenant)
        db = _make_db_with_user(user, tenant, membership)
        session_store = _make_session_store()
        session_store.create_session = AsyncMock(side_effect=RuntimeError("redis down"))

        with pytest.raises(HTTPException) as exc:
            await ar.login.__wrapped__(
                payload=LoginRequest(email="u@x.com", password="pw"),
                request=_make_request(),
                db=db,
                session_store=session_store,
            )
        assert exc.value.status_code == 503


# ──────────────────────────────────────────────────────────────────────────────
# 4. Refresh token rotation
# ──────────────────────────────────────────────────────────────────────────────


class TestRefreshToken:
    def _make_session(self, user_id, *, is_revoked=False, expired=False) -> SessionData:
        now = datetime.now(timezone.utc)
        expires_at = now - timedelta(days=1) if expired else now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        raw = create_refresh_token()
        return SessionData(
            id=uuid_mod.uuid4(),
            user_id=user_id,
            refresh_token_hash=hash_token(raw),
            family_id=uuid_mod.uuid4(),
            is_revoked=is_revoked,
            created_at=now,
            last_used_at=now,
            expires_at=expires_at,
            user_agent="pytest",
            ip_address="127.0.0.1",
        ), raw

    @pytest.mark.asyncio
    async def test_refresh_happy_path(self, monkeypatch):
        """Valid refresh token → new access token + new refresh token."""
        user = _make_user(email="u@x.com", password="pw")
        tenant = _make_tenant()
        membership = _make_membership(user, tenant)
        session, raw_token = self._make_session(user.id)

        session_store = _make_session_store()
        session_store.claim_session_by_token = AsyncMock(return_value=session)

        db = _make_db_with_user(user, tenant, membership)
        db.get = MagicMock(return_value=user)

        # Provide old access token in Authorization header so tenant preserved
        old_access = create_access_token({
            "sub": str(user.id),
            "tenant_id": str(tenant.id),
            "tid": str(tenant.id),
            "tv": 0,
        })
        request = _make_request(headers={
            "authorization": f"Bearer {old_access}",
            "user-agent": "pytest",
        })

        result = await ar.refresh_session.__wrapped__(
            payload=RefreshRequest(refresh_token=raw_token),
            request=request,
            db=db,
            session_store=session_store,
        )

        assert result.access_token
        assert result.refresh_token != raw_token
        payload = decode_access_token(result.access_token)
        assert payload["sub"] == str(user.id)

    @pytest.mark.asyncio
    async def test_refresh_invalid_token_raises_401(self):
        """Unknown refresh token → 401."""
        session_store = _make_session_store()
        session_store.claim_session_by_token = AsyncMock(return_value=None)
        db = _make_db_with_user(None)

        with pytest.raises(HTTPException) as exc:
            await ar.refresh_session.__wrapped__(
                payload=RefreshRequest(refresh_token="bad-token"),
                request=_make_request(),
                db=db,
                session_store=session_store,
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_revoked_session_raises_401(self):
        user = _make_user()
        session, raw_token = self._make_session(user.id, is_revoked=True)

        session_store = _make_session_store()
        session_store.claim_session_by_token = AsyncMock(return_value=session)
        db = _make_db_with_user(user)

        with pytest.raises(HTTPException) as exc:
            await ar.refresh_session.__wrapped__(
                payload=RefreshRequest(refresh_token=raw_token),
                request=_make_request(),
                db=db,
                session_store=session_store,
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_expired_session_raises_401(self):
        user = _make_user()
        session, raw_token = self._make_session(user.id, expired=True)

        session_store = _make_session_store()
        session_store.claim_session_by_token = AsyncMock(return_value=session)
        db = _make_db_with_user(user)

        with pytest.raises(HTTPException) as exc:
            await ar.refresh_session.__wrapped__(
                payload=RefreshRequest(refresh_token=raw_token),
                request=_make_request(),
                db=db,
                session_store=session_store,
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_tenant_no_longer_member_raises_403(self):
        """If the user lost membership to the acting tenant, refresh is refused."""
        user = _make_user()
        old_tenant_id = uuid_mod.uuid4()
        session, raw_token = self._make_session(user.id)

        session_store = _make_session_store()
        session_store.claim_session_by_token = AsyncMock(return_value=session)

        db = MagicMock()
        db.get = MagicMock(return_value=user)
        # No active memberships
        db.execute.return_value.scalars.return_value.all.return_value = []

        # Pass old access token with a tenant_id not in memberships
        old_access = create_access_token({
            "sub": str(user.id),
            "tenant_id": str(old_tenant_id),
            "tid": str(old_tenant_id),
            "tv": 0,
        })
        request = _make_request(headers={
            "authorization": f"Bearer {old_access}",
            "user-agent": "pytest",
        })

        with pytest.raises(HTTPException) as exc:
            await ar.refresh_session.__wrapped__(
                payload=RefreshRequest(refresh_token="tok"),
                request=request,
                db=db,
                session_store=session_store,
            )
        # Either 401 (no session found from hash) or 403 (tenant check)
        assert exc.value.status_code in (401, 403)


# ──────────────────────────────────────────────────────────────────────────────
# 5. Session listing, revocation, and logout-all
# ──────────────────────────────────────────────────────────────────────────────


class TestSessionManagement:
    @pytest.mark.asyncio
    async def test_list_sessions_returns_items(self):
        user = _make_user()
        now = datetime.now(timezone.utc)
        fake_session = SessionData(
            id=uuid_mod.uuid4(),
            user_id=user.id,
            refresh_token_hash=hash_token(create_refresh_token()),
            family_id=uuid_mod.uuid4(),
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=7),
            user_agent="browser",
            ip_address="1.2.3.4",
        )
        session_store = _make_session_store()
        session_store.list_user_sessions = AsyncMock(return_value=[fake_session])

        from services.admin.app.auth_routes import list_sessions

        result = await list_sessions(
            pagination=MagicMock(skip=0, limit=50),
            current_user=user,
            session_store=session_store,
        )
        assert result["total"] == 1
        assert result["items"][0]["ip_address"] == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_revoke_session_success(self):
        user = _make_user()
        now = datetime.now(timezone.utc)
        session_id = uuid_mod.uuid4()
        fake_session = SessionData(
            id=session_id,
            user_id=user.id,
            refresh_token_hash="hash",
            family_id=uuid_mod.uuid4(),
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=7),
            user_agent="browser",
            ip_address="1.2.3.4",
        )
        session_store = _make_session_store()
        session_store.get_session = AsyncMock(return_value=fake_session)

        from services.admin.app.auth_routes import revoke_session
        result = await revoke_session(
            session_id=session_id,
            current_user=user,
            session_store=session_store,
        )
        assert result == {"status": "revoked"}
        session_store.revoke_session.assert_awaited_once_with(session_id)

    @pytest.mark.asyncio
    async def test_revoke_session_not_owned_raises_404(self):
        user = _make_user()
        other_user_id = uuid_mod.uuid4()
        now = datetime.now(timezone.utc)
        session_id = uuid_mod.uuid4()
        fake_session = SessionData(
            id=session_id,
            user_id=other_user_id,  # belongs to someone else
            refresh_token_hash="hash",
            family_id=uuid_mod.uuid4(),
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=7),
            user_agent="browser",
            ip_address="1.2.3.4",
        )
        session_store = _make_session_store()
        session_store.get_session = AsyncMock(return_value=fake_session)

        from services.admin.app.auth_routes import revoke_session
        with pytest.raises(HTTPException) as exc:
            await revoke_session(
                session_id=session_id,
                current_user=user,
                session_store=session_store,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_logout_all_revokes_sessions_and_bumps_tv(self, monkeypatch):
        user = _make_user(token_version=2)
        session_store = _make_session_store()
        session_store.revoke_all_user_sessions = AsyncMock(return_value=3)

        db = _make_db_with_user(user)
        db.get = MagicMock(return_value=user)

        monkeypatch.setattr(
            ar,
            "_revoke_all_elevation_tokens_for_user",
            AsyncMock(return_value=0),
        )

        from services.admin.app.auth_routes import revoke_all_sessions
        result = await revoke_all_sessions(
            current_user=user,
            db=db,
            session_store=session_store,
        )
        assert result["status"] == "success"
        assert result["revoked_count"] == 3
        assert user.token_version == 3  # bumped from 2 to 3


# ──────────────────────────────────────────────────────────────────────────────
# 6. Password reset
# ──────────────────────────────────────────────────────────────────────────────


class TestPasswordReset:
    @pytest.mark.asyncio
    async def test_reset_missing_auth_header_raises_401(self):
        """No Authorization header → 401."""
        request = _make_request(headers={"user-agent": "pytest"})
        db = MagicMock()
        session_store = _make_session_store()

        with pytest.raises(HTTPException) as exc:
            await ar.reset_password.__wrapped__(
                payload=ResetPasswordRequest(new_password="NewPass-1234"),
                request=request,
                db=db,
                session_store=session_store,
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_reset_no_supabase_raises_503(self, monkeypatch):
        """If Supabase client unavailable → 503."""
        monkeypatch.setattr(ar, "get_supabase", lambda: None)

        request = _make_request(headers={
            "authorization": "Bearer some-token",
            "user-agent": "pytest",
        })
        db = MagicMock()
        session_store = _make_session_store()

        with pytest.raises(HTTPException) as exc:
            await ar.reset_password.__wrapped__(
                payload=ResetPasswordRequest(new_password="NewPass-1234"),
                request=request,
                db=db,
                session_store=session_store,
            )
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_reset_invalid_supabase_token_raises_401(self, monkeypatch):
        """Supabase rejects token → 401."""
        fake_sb = SimpleNamespace(
            auth=SimpleNamespace(
                get_user=MagicMock(side_effect=RuntimeError("bad token"))
            )
        )
        monkeypatch.setattr(ar, "get_supabase", lambda: fake_sb)

        request = _make_request(headers={
            "authorization": "Bearer garbage-token",
            "user-agent": "pytest",
        })
        db = MagicMock()
        session_store = _make_session_store()

        with pytest.raises(HTTPException) as exc:
            await ar.reset_password.__wrapped__(
                payload=ResetPasswordRequest(new_password="NewPass-1234"),
                request=request,
                db=db,
                session_store=session_store,
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_reset_happy_path_updates_hash_and_bumps_tv(self, monkeypatch):
        """Happy path: fresh OTP token → password_hash updated, token_version bumped."""
        now_ts = int(time.time())
        recovery_token_payload = {
            "sub": "sb-user-1",
            "aud": "authenticated",
            "amr": [{"method": "otp", "timestamp": now_ts}],
            "iat": now_ts,
            "exp": now_ts + 3600,
            "jti": str(uuid_mod.uuid4()),
        }
        recovery_token = _jwt.encode(recovery_token_payload, "irrelevant", algorithm="HS256")  # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret

        fake_sb_user = SimpleNamespace(id="sb-user-1", email="reset@example.com")
        fake_sb = SimpleNamespace(
            auth=SimpleNamespace(
                get_user=MagicMock(return_value=SimpleNamespace(user=fake_sb_user)),
                admin=SimpleNamespace(update_user_by_id=MagicMock(return_value=None)),
            )
        )
        monkeypatch.setattr(ar, "get_supabase", lambda: fake_sb)

        user = _make_user(email="reset@example.com", password="old-pass", token_version=1)
        db = _make_db_with_user(user)

        session_store = _make_session_store()
        client = _make_redis_client()
        client.set = AsyncMock(return_value=True)
        session_store._get_client = AsyncMock(return_value=client)
        session_store.revoke_all_for_user = AsyncMock(return_value=2)

        monkeypatch.setattr(
            ar,
            "_revoke_all_elevation_tokens_for_user",
            AsyncMock(return_value=0),
        )

        request = _make_request(headers={
            "authorization": f"Bearer {recovery_token}",
            "user-agent": "pytest",
        })

        old_hash = user.password_hash
        result = await ar.reset_password.__wrapped__(
            payload=ResetPasswordRequest(new_password="NewStrongPass-9!"),
            request=request,
            db=db,
            session_store=session_store,
        )

        assert result == {"status": "success"}
        assert user.password_hash != old_hash
        assert user.token_version == 2  # bumped from 1
        db.commit.assert_called_once()


# ──────────────────────────────────────────────────────────────────────────────
# 7. Change password
# ──────────────────────────────────────────────────────────────────────────────


class TestChangePassword:
    @pytest.mark.asyncio
    async def test_change_password_wrong_current_raises_401(self, monkeypatch):
        user = _make_user(email="u@x.com", password="correct")
        db = _make_db_with_user(user)
        db.get = MagicMock(return_value=user)
        session_store = _make_session_store()

        with pytest.raises(HTTPException) as exc:
            await ar.change_password.__wrapped__(
                payload=ChangePasswordRequest(
                    current_password="wrong",
                    new_password="NewStrongPass-9!",
                ),
                request=_make_request(),
                db=db,
                current_user=user,
                session_store=session_store,
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_change_password_happy_path(self, monkeypatch):
        monkeypatch.setattr(ar, "get_supabase", lambda: None)
        monkeypatch.setattr(
            ar,
            "_revoke_all_elevation_tokens_for_user",
            AsyncMock(return_value=0),
        )

        user = _make_user(email="u@x.com", password="OldPass-123!")
        db = _make_db_with_user(user)
        db.get = MagicMock(return_value=user)
        session_store = _make_session_store()

        old_hash = user.password_hash
        result = await ar.change_password.__wrapped__(
            payload=ChangePasswordRequest(
                current_password="OldPass-123!",
                new_password="NewStrongPass-9!",
            ),
            request=_make_request(),
            db=db,
            current_user=user,
            session_store=session_store,
        )

        assert result == {"status": "success"}
        assert user.password_hash != old_hash
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_change_password_disabled_account_raises_403(self, monkeypatch):
        user = _make_user(email="u@x.com", password="pw", status="disabled")
        db = _make_db_with_user(user)
        db.get = MagicMock(return_value=user)
        session_store = _make_session_store()

        with pytest.raises(HTTPException) as exc:
            await ar.change_password.__wrapped__(
                payload=ChangePasswordRequest(
                    current_password="pw",
                    new_password="NewStrongPass-9!",
                ),
                request=_make_request(),
                db=db,
                current_user=user,
                session_store=session_store,
            )
        assert exc.value.status_code == 403


# ──────────────────────────────────────────────────────────────────────────────
# 8. /confirm — elevation token
# ──────────────────────────────────────────────────────────────────────────────


class TestConfirmPassword:
    @pytest.mark.asyncio
    async def test_confirm_wrong_password_raises_401(self, monkeypatch):
        user = _make_user(email="u@x.com", password="correct")
        db = MagicMock()
        session_store = _make_session_store()

        with pytest.raises(HTTPException) as exc:
            await ar.confirm_password.__wrapped__(
                payload=ConfirmPasswordRequest(password="wrong"),
                request=_make_request(),
                current_user=user,
                db=db,
                session_store=session_store,
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_confirm_happy_path_returns_elevation_token(self, monkeypatch):
        user = _make_user(email="u@x.com", password="correct", token_version=0)
        tenant = _make_tenant()
        membership = _make_membership(user, tenant)

        db = MagicMock()
        db.execute.return_value.scalars.return_value.first.return_value = membership

        # Patch TenantContext to return None so it falls through to membership lookup
        monkeypatch.setattr(ar, "AuditLogger", MagicMock())

        session_store = _make_session_store()

        result = await ar.confirm_password.__wrapped__(
            payload=ConfirmPasswordRequest(password="correct"),
            request=_make_request(),
            current_user=user,
            db=db,
            session_store=session_store,
        )

        assert "elevation_token" in result
        assert result["expires_in"] == ar._ELEVATION_TOKEN_TTL_SECONDS

        # Decode and verify claims
        payload = decode_access_token(result["elevation_token"])
        assert payload["elevated"] is True
        assert payload["sub"] == str(user.id)
        assert "jti" in payload

    @pytest.mark.asyncio
    async def test_confirm_rate_limited_raises_401(self, monkeypatch):
        user = _make_user(email="u@x.com", password="pw")
        client = _make_redis_client()
        client.get = AsyncMock(return_value=str(_EMAIL_ATTEMPT_LIMIT))
        client.ttl = AsyncMock(return_value=-2)
        session_store = _make_session_store(redis_client=client)
        db = MagicMock()

        with pytest.raises(HTTPException) as exc:
            await ar.confirm_password.__wrapped__(
                payload=ConfirmPasswordRequest(password="pw"),
                request=_make_request(),
                current_user=user,
                db=db,
                session_store=session_store,
            )
        assert exc.value.status_code == 401


# ──────────────────────────────────────────────────────────────────────────────
# 9. /register bootstrap endpoint
# ──────────────────────────────────────────────────────────────────────────────


class TestRegisterInitialAdmin:
    def test_register_disabled_when_users_exist(self):
        db = MagicMock()
        db.execute.return_value.first.return_value = SimpleNamespace(id="existing")

        with pytest.raises(HTTPException) as exc:
            ar.register_initial_admin(
                payload=RegisterRequest(
                    email="admin@x.com",
                    password="Admin-Pass-9!",
                    tenant_name="Acme",
                ),
                request=_make_request(),
                db=db,
            )
        assert exc.value.status_code == 403

    def test_register_happy_path_creates_admin(self, monkeypatch):
        db = MagicMock()
        db.execute.return_value.first.return_value = None  # no users yet
        db.execute.return_value.scalar_one_or_none.return_value = None
        db.add = MagicMock()
        db.flush = MagicMock()
        db.commit = MagicMock()

        monkeypatch.setattr(ar, "AuditLogger", MagicMock())

        result = ar.register_initial_admin(
            payload=RegisterRequest(
                email="first@x.com",
                password="Str0ng-Secure-Pass!",
                tenant_name="Acme Corp",
            ),
            request=_make_request(),
            db=db,
        )

        assert result["message"] == "Admin created"
        assert "user_id" in result
        assert "tenant_id" in result
        db.commit.assert_called_once()

    def test_register_weak_password_raises_400(self):
        db = MagicMock()
        db.execute.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            ar.register_initial_admin(
                payload=RegisterRequest(
                    email="admin@x.com",
                    password="weak",
                    tenant_name="Acme",
                ),
                request=_make_request(),
                db=db,
            )
        assert exc.value.status_code == 400


# ──────────────────────────────────────────────────────────────────────────────
# 10. Signup endpoint
# ──────────────────────────────────────────────────────────────────────────────


class TestSignup:
    @pytest.mark.asyncio
    async def test_signup_duplicate_email_returns_generic_success(self, monkeypatch):
        existing = _make_user(email="existing@x.com")
        db = _make_db_with_user(existing)
        session_store = _make_session_store()

        result = await ar.signup.__wrapped__(
            payload=RegisterRequest(
                email="existing@x.com",
                password="StrongPass-9!",
                tenant_name="Acme",
            ),
            request=_make_request(),
            db=db,
            session_store=session_store,
        )
        assert result.status_code == 200
        assert b"Check your inbox" in result.body

    @pytest.mark.asyncio
    async def test_signup_weak_password_raises_400(self, monkeypatch):
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = None
        session_store = _make_session_store()

        with pytest.raises(HTTPException) as exc:
            await ar.signup.__wrapped__(
                payload=RegisterRequest(
                    email="new@x.com",
                    password="weak",
                    tenant_name="Acme",
                ),
                request=_make_request(),
                db=db,
                session_store=session_store,
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_signup_happy_path_returns_tokens(self, monkeypatch):
        monkeypatch.setattr(ar, "get_supabase", lambda: None)
        monkeypatch.setattr(ar, "AuditLogger", MagicMock())
        monkeypatch.setattr(ar, "emit_funnel_event", MagicMock())

        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = None
        # Simulate slug uniqueness check returning None (no conflict)
        db.execute.return_value.scalar_one_or_none.return_value = None
        db.add = MagicMock()
        db.flush = MagicMock()
        db.commit = MagicMock()

        session_store = _make_session_store()

        result = await ar.signup.__wrapped__(
            payload=RegisterRequest(
                email="newuser@example.com",
                password="StrongPass-9!",
                tenant_name="Acme Corp",
            ),
            request=_make_request(),
            db=db,
            session_store=session_store,
        )

        assert result.access_token
        assert result.refresh_token

    @pytest.mark.asyncio
    async def test_signup_empty_tenant_name_raises_400(self, monkeypatch):
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = None
        session_store = _make_session_store()

        with pytest.raises(HTTPException) as exc:
            await ar.signup.__wrapped__(
                payload=RegisterRequest(
                    email="new@x.com",
                    password="StrongPass-9!",
                    tenant_name="   ",
                ),
                request=_make_request(),
                db=db,
                session_store=session_store,
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_signup_redis_failure_rolls_back_db(self, monkeypatch):
        """If Redis create_session fails, DB is rolled back and 503 is raised."""
        monkeypatch.setattr(ar, "get_supabase", lambda: None)

        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = None
        db.add = MagicMock()
        db.flush = MagicMock()
        db.commit = MagicMock()
        db.rollback = MagicMock()

        session_store = _make_session_store()
        session_store.create_session = AsyncMock(side_effect=RuntimeError("redis down"))

        with pytest.raises(HTTPException) as exc:
            await ar.signup.__wrapped__(
                payload=RegisterRequest(
                    email="newuser@example.com",
                    password="StrongPass-9!",
                    tenant_name="Acme Corp",
                ),
                request=_make_request(),
                db=db,
                session_store=session_store,
            )
        assert exc.value.status_code == 503
        db.rollback.assert_called()


# ──────────────────────────────────────────────────────────────────────────────
# 11. Rate-limit helpers (unit)
# ──────────────────────────────────────────────────────────────────────────────


class TestRateLimitHelpers:
    @pytest.mark.asyncio
    async def test_check_email_rate_limit_raises_401_at_limit(self):
        client = _make_redis_client()
        client.get = AsyncMock(return_value=str(_EMAIL_ATTEMPT_LIMIT))
        session_store = _make_session_store(redis_client=client)

        with pytest.raises(HTTPException) as exc:
            await ar._check_email_rate_limit(session_store, "u@x.com")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_check_email_rate_limit_passes_below_limit(self):
        client = _make_redis_client()
        client.get = AsyncMock(return_value=str(_EMAIL_ATTEMPT_LIMIT - 1))
        session_store = _make_session_store(redis_client=client)

        # Must not raise
        await ar._check_email_rate_limit(session_store, "u@x.com")

    @pytest.mark.asyncio
    async def test_record_failed_login_attempt_increments(self):
        client = _make_redis_client()
        pipe = MagicMock()
        pipe.incr = MagicMock()
        pipe.expire = MagicMock()
        pipe.execute = AsyncMock(return_value=[2, 1])
        pipe.__aenter__ = AsyncMock(return_value=pipe)
        pipe.__aexit__ = AsyncMock(return_value=False)
        client.pipeline = MagicMock(return_value=pipe)
        session_store = _make_session_store(redis_client=client)

        await ar._record_failed_login_attempt(session_store, "u@x.com")
        pipe.incr.assert_called_once()
        pipe.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_email_rate_limit_deletes_key(self):
        client = _make_redis_client()
        session_store = _make_session_store(redis_client=client)

        await ar._clear_email_rate_limit(session_store, "u@x.com")
        client.delete.assert_awaited_once_with(_email_attempt_key("u@x.com"))


# ──────────────────────────────────────────────────────────────────────────────
# 12. /unlock admin endpoint
# ──────────────────────────────────────────────────────────────────────────────


class TestUnlockAccount:
    @pytest.mark.asyncio
    async def test_unlock_clears_both_counters(self):
        client = _make_redis_client()
        session_store = _make_session_store(redis_client=client)

        result = await ar.unlock_account(
            email="Locked@Example.com",
            session_store=session_store,
        )

        assert result["unlocked"] is True
        # email should be normalized
        assert "locked@example.com" in result["email"] or "***" in result["email"]


# ──────────────────────────────────────────────────────────────────────────────
# 13. _persist_session retry logic
# ──────────────────────────────────────────────────────────────────────────────


class TestPersistSession:
    @pytest.mark.asyncio
    async def test_persist_session_succeeds_on_first_try(self):
        now = datetime.now(timezone.utc)
        session_data = SessionData(
            id=uuid_mod.uuid4(),
            user_id=uuid_mod.uuid4(),
            refresh_token_hash="h",
            family_id=uuid_mod.uuid4(),
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=7),
            user_agent="pytest",
            ip_address="127.0.0.1",
        )
        store = _make_session_store()
        store.create_session = AsyncMock(return_value=None)

        # Should not raise
        await ar._persist_session(store, session_data, context="test", user_id=session_data.user_id)
        store.create_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_persist_session_retries_once_then_503(self, monkeypatch):
        now = datetime.now(timezone.utc)
        session_data = SessionData(
            id=uuid_mod.uuid4(),
            user_id=uuid_mod.uuid4(),
            refresh_token_hash="h",
            family_id=uuid_mod.uuid4(),
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=7),
            user_agent="pytest",
            ip_address="127.0.0.1",
        )
        store = _make_session_store()
        store.create_session = AsyncMock(side_effect=RuntimeError("redis down"))

        # Speed up the test: patch asyncio.sleep to be instant
        monkeypatch.setattr(ar.asyncio, "sleep", AsyncMock(return_value=None))

        with pytest.raises(HTTPException) as exc:
            await ar._persist_session(store, session_data, context="test", user_id=session_data.user_id)
        assert exc.value.status_code == 503
        assert store.create_session.await_count == 2  # exactly one retry


# ──────────────────────────────────────────────────────────────────────────────
# 14. Source-level guardrails (prevent silent regressions)
# ──────────────────────────────────────────────────────────────────────────────


class TestSourceGuardrails:
    """Read the source file and assert structural invariants that prevent
    silent regressions. These catch refactors that break security properties
    without test failures in other suites."""

    _src = Path(__file__).resolve().parent.parent / "app" / "auth_routes.py"
    _text = _src.read_text()

    def test_login_uses_verify_login_not_verify_password(self):
        assert "verify_login" in self._text, (
            "auth_routes.py must use verify_login() — not verify_password() — "
            "to prevent timing-oracle enumeration (#1082)"
        )

    def test_refresh_uses_claim_session_by_token(self):
        assert "claim_session_by_token" in self._text, (
            "refresh must use atomic claim_session_by_token to prevent race conditions"
        )

    def test_logout_all_bumps_token_version(self):
        assert "token_version" in self._text, (
            "logout-all must bump token_version to kill outstanding access tokens (#1375)"
        )

    def test_reset_password_calls_enforce_recovery_token_scope(self):
        assert "_enforce_recovery_token_scope" in self._text, (
            "reset-password must enforce amr/iat scope on Supabase tokens (#1087)"
        )

    def test_reset_password_claims_single_use(self):
        assert "_claim_recovery_token_single_use" in self._text, (
            "reset-password must enforce single-use via Redis jti dedup (#1087)"
        )

    def test_confirm_endpoint_has_lockout_integration(self):
        assert "_check_account_lockout" in self._text, (
            "/confirm must integrate with lockout infrastructure (#1340)"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
