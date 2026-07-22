"""get_current_user falls back to the opaque __Host-regengine_session cookie.

Passwordless browser sessions never receive a Bearer JWT — before this
fallback, every get_current_user route returned 401 for logged-in browsers,
so the prod dashboard rendered demo zeros behind a healthy system banner.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from services.admin.app.auth.session_auth import AUTH_SESSION_COOKIE
from services.admin.app.auth.sessions_router import router as sessions_router
from services.admin.app.auth_crypto import AuthCryptoService
from services.admin.app.database import get_session
from services.admin.app.dependencies import get_current_user, get_session_store
from services.admin.app.session_store import InMemorySessionStore
from services.admin.app.sqlalchemy_models import (
    MembershipModel,
    RoleModel,
    SessionModel,
    UserModel,
)

RAW_SESSION_TOKEN = "raw-opaque-session-token-for-tests"


@pytest.fixture(autouse=True)
def _hmac_secret(monkeypatch):
    """AuthCryptoService demands this secret when another test in the suite
    has leaked REGENGINE_ENV=production into the process environment."""
    monkeypatch.setenv("AUTH_OTP_HMAC_SECRET", "unit-test-hmac-secret-0123456789abcdef")


@pytest.fixture
def db_session() -> Session:
    """Private engine with the real auth tables.

    The shared conftest engine pre-creates 2-column mock ``users``/``tenants``
    tables that shadow the ORM models, so we build our own (same pattern as
    test_passwordless_identity_provisioning.py).
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    table_bindings = [
        UserModel.__table__,
        RoleModel.__table__,
        MembershipModel.__table__,
        SessionModel.__table__,
    ]
    for table in table_bindings:
        table.create(bind=engine)

    session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )
    session = session_local()
    try:
        yield session
    finally:
        session.close()
        for table in reversed(table_bindings):
            table.drop(bind=engine)
        engine.dispose()


def _make_app(db_session) -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    async def protected(user: UserModel = Depends(get_current_user)):
        return {"user_id": str(user.id), "email": user.email}

    app.include_router(sessions_router, prefix="/auth")

    store = InMemorySessionStore()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_session_store] = lambda: store
    return app


@pytest.fixture
def client(db_session):
    with TestClient(_make_app(db_session)) as test_client:
        yield test_client


@pytest.fixture
def seeded(db_session):
    """User with one active membership and a live opaque-cookie session.

    No TenantModel row: conftest's mock ``tenants`` table lacks the real
    columns, and the auth path only reads memberships — a bare UUID is
    enough for tenant scoping here.
    """
    tenant_id = uuid.uuid4()
    user = UserModel(
        id=uuid.uuid4(),
        email=f"cookie-fallback-{uuid.uuid4().hex[:8]}@example.com",
    )
    role = RoleModel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="admin",
        permissions=["*"],
    )
    membership = MembershipModel(
        user_id=user.id,
        tenant_id=tenant_id,
        role_id=role.id,
        is_active=True,
    )
    session_row = SessionModel(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=AuthCryptoService.hash_session_token(RAW_SESSION_TOKEN),
        auth_method="webauthn",
        refresh_token_hash=f"refresh-{uuid.uuid4().hex}",
        family_id=uuid.uuid4(),
        is_revoked=False,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=8),
    )
    db_session.add_all([user, role, membership, session_row])
    db_session.commit()
    return {"tenant_id": tenant_id, "user": user, "session": session_row}


def _cookie(value: str = RAW_SESSION_TOKEN) -> dict[str, str]:
    return {AUTH_SESSION_COOKIE: value}


class TestSessionCookieFallback:
    def test_cookie_only_request_authenticates(self, client, seeded):
        resp = client.get("/protected", cookies=_cookie())
        assert resp.status_code == 200
        assert resp.json()["user_id"] == str(seeded["user"].id)

    def test_no_credentials_still_rejected(self, client, seeded):
        resp = client.get("/protected")
        assert resp.status_code == 401

    def test_garbage_cookie_rejected(self, client, seeded):
        resp = client.get("/protected", cookies=_cookie("not-a-real-token"))
        assert resp.status_code == 401

    def test_revoked_session_rejected(self, client, seeded, db_session):
        seeded["session"].is_revoked = True
        seeded["session"].revoked_at = datetime.now(timezone.utc)
        db_session.commit()
        resp = client.get("/protected", cookies=_cookie())
        assert resp.status_code == 401

    def test_expired_session_rejected(self, client, seeded, db_session):
        seeded["session"].expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()
        resp = client.get("/protected", cookies=_cookie())
        assert resp.status_code == 401

    def test_bumped_token_version_does_not_block_cookie_session(self, client, seeded, db_session):
        # Cookie sessions carry no tv claim; their revocation lives on the
        # session row. A historical token_version bump must not lock the
        # browser out (JWTs minted before the bump are still rejected by
        # the claim comparison path).
        seeded["user"].token_version = 3
        db_session.commit()
        resp = client.get("/protected", cookies=_cookie())
        assert resp.status_code == 200

    def test_inactive_membership_rejected(self, client, seeded, db_session):
        membership = db_session.query(MembershipModel).filter_by(user_id=seeded["user"].id).one()
        membership.is_active = False
        db_session.commit()
        resp = client.get("/protected", cookies=_cookie())
        assert resp.status_code == 401


class TestLogoutAllRevokesCookieSessions:
    def test_logout_all_kills_opaque_sessions(self, client, seeded, db_session):
        assert client.get("/protected", cookies=_cookie()).status_code == 200

        resp = client.post("/auth/logout-all", cookies=_cookie())
        assert resp.status_code == 200

        db_session.expire_all()
        assert seeded["session"].is_revoked is True
        assert seeded["session"].revoked_at is not None
        assert client.get("/protected", cookies=_cookie()).status_code == 401
