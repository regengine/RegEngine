"""Passwordless identity provisioning for user-creation flows.

Users created after the v094 backfill (invite acceptance) must get a
verified ``user_emails`` row with an ``email_fingerprint`` plus an
``organization_memberships`` row, or ``_load_valid_identity`` never matches
and their sign-in code emails are silently suppressed
(``auth_challenge_email_suppressed_ineligible_identity``).
"""

from __future__ import annotations

import hashlib
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from services.admin.app.auth.challenges_router import _load_valid_identity
from services.admin.app.auth.identity_helpers import ensure_passwordless_identity
from services.admin.app.auth_crypto import AuthCryptoService
from services.admin.app.sqlalchemy_models import (
    AuditLogModel,
    InviteModel,
    MembershipModel,
    OrganizationMembershipModel,
    OrganizationModel,
    RoleModel,
    TenantModel,
    UserEmailModel,
    UserModel,
)

TEST_HMAC_SECRET = "unit-test-otp-hmac-secret-0123456789abcdef"  # pragma: allowlist secret
TENANT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
ROLE_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
INVITER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c1")


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    table_bindings = [
        TenantModel.__table__,
        UserModel.__table__,
        UserEmailModel.__table__,
        OrganizationModel.__table__,
        OrganizationMembershipModel.__table__,
        RoleModel.__table__,
        MembershipModel.__table__,
        InviteModel.__table__,
        AuditLogModel.__table__,
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

    session.add(TenantModel(id=TENANT_ID, name="Acme Foods", slug="acme-foods", status="active", settings={}))
    session.add(RoleModel(id=ROLE_ID, tenant_id=None, name="Viewer", permissions=["users.read"]))
    session.add(
        UserModel(id=INVITER_ID, email="inviter@acme.test", global_status="active", status="active", is_sysadmin=False)
    )
    session.commit()

    try:
        yield session
    finally:
        session.close()
        for table in reversed(table_bindings):
            table.drop(bind=engine)
        engine.dispose()


@pytest.fixture
def crypto() -> AuthCryptoService:
    return AuthCryptoService(hmac_secret=TEST_HMAC_SECRET)


def _add_user(db: Session, email: str) -> UserModel:
    user = UserModel(email=email, global_status="active", status="active", is_sysadmin=False)
    db.add(user)
    db.flush()
    return user


def _seed_invite(db: Session, email: str) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        InviteModel(
            tenant_id=TENANT_ID,
            email=email,
            role_id=ROLE_ID,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            created_by=INVITER_ID,
        )
    )
    db.commit()
    return token


def _make_starlette_request():
    """Real starlette Request on a fake ASGI scope (SlowAPI rejects mocks)."""
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/accept-invite",
        "headers": [],
        "client": ("127.0.0.1", 0),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
        "http_version": "1.1",
        "root_path": "",
        "state": {},
    }
    return Request(scope)


async def _accept_invite(db: Session, token: str, monkeypatch: pytest.MonkeyPatch) -> dict:
    from services.admin.app.invite_routes import AcceptInviteRequest, accept_invite

    monkeypatch.setenv("AUTH_OTP_HMAC_SECRET", TEST_HMAC_SECRET)
    monkeypatch.setattr(
        "services.admin.app.invite_routes.supplier_graph_sync",
        MagicMock(record_invite_accepted=MagicMock(return_value=None)),
    )
    payload = AcceptInviteRequest(token=token, name="Invitee")
    return await accept_invite.__wrapped__(payload=payload, request=_make_starlette_request(), db=db)


# ─────────────────────────────────────────────────────────────────────
# ensure_passwordless_identity — unit
# ─────────────────────────────────────────────────────────────────────


def test_ensure_passwordless_identity_creates_all_rows(db_session, crypto):
    user = _add_user(db_session, "newbie@acme.test")

    ensure_passwordless_identity(
        db_session,
        user=user,
        email="Newbie@Acme.test",
        organization_id=TENANT_ID,
        role_name="Viewer",
        crypto_service=crypto,
    )
    db_session.commit()

    user_email = db_session.execute(select(UserEmailModel).where(UserEmailModel.user_id == user.id)).scalar_one()
    assert user_email.email == "newbie@acme.test"
    assert user_email.email_fingerprint == crypto.fingerprint_email("newbie@acme.test")
    assert user_email.is_verified is True

    organization = db_session.get(OrganizationModel, TENANT_ID)
    assert organization is not None
    assert organization.name == "Acme Foods"
    assert organization.enforced_auth_policy == "standard"

    membership = db_session.execute(
        select(OrganizationMembershipModel).where(OrganizationMembershipModel.user_id == user.id)
    ).scalar_one()
    assert membership.organization_id == TENANT_ID
    assert membership.role == "viewer"

    # The whole point: the sign-in eligibility gate now matches.
    identity = _load_valid_identity(db=db_session, email_fingerprint=user_email.email_fingerprint)
    assert identity is not None
    assert identity[0].id == user.id


def test_ensure_passwordless_identity_is_idempotent(db_session, crypto):
    user = _add_user(db_session, "repeat@acme.test")

    for _ in range(2):
        ensure_passwordless_identity(
            db_session,
            user=user,
            email="repeat@acme.test",
            organization_id=TENANT_ID,
            role_name="Viewer",
            crypto_service=crypto,
        )
        db_session.commit()

    emails = db_session.execute(select(func.count()).select_from(UserEmailModel)).scalar()
    memberships = db_session.execute(select(func.count()).select_from(OrganizationMembershipModel)).scalar()
    organizations = db_session.execute(select(func.count()).select_from(OrganizationModel)).scalar()
    assert (emails, memberships, organizations) == (1, 1, 1)


def test_ensure_passwordless_identity_upgrades_v084_shaped_row(db_session, crypto):
    """A pre-existing unverified/unfingerprinted user_emails row gets repaired."""
    user = _add_user(db_session, "legacy@acme.test")
    db_session.add(UserEmailModel(user_id=user.id, email="legacy@acme.test", email_fingerprint=None, is_verified=False))
    db_session.commit()

    ensure_passwordless_identity(
        db_session,
        user=user,
        email="legacy@acme.test",
        organization_id=TENANT_ID,
        role_name=None,
        crypto_service=crypto,
    )
    db_session.commit()

    user_email = db_session.execute(select(UserEmailModel).where(UserEmailModel.user_id == user.id)).scalar_one()
    assert user_email.email_fingerprint == crypto.fingerprint_email("legacy@acme.test")
    assert user_email.is_verified is True

    membership = db_session.execute(
        select(OrganizationMembershipModel).where(OrganizationMembershipModel.user_id == user.id)
    ).scalar_one()
    assert membership.role == "member"


def test_ensure_passwordless_identity_defaults_org_name_without_tenant(db_session, crypto):
    user = _add_user(db_session, "orphan@acme.test")
    unknown_org_id = uuid.uuid4()

    ensure_passwordless_identity(
        db_session,
        user=user,
        email="orphan@acme.test",
        organization_id=unknown_org_id,
        role_name="Owner",
        crypto_service=crypto,
    )
    db_session.commit()

    organization = db_session.get(OrganizationModel, unknown_org_id)
    assert organization is not None
    assert organization.name == "Organization"


# ─────────────────────────────────────────────────────────────────────
# accept-invite — end to end against a real session
# ─────────────────────────────────────────────────────────────────────


async def test_accept_invite_new_user_can_pass_signin_eligibility(db_session, monkeypatch):
    token = _seed_invite(db_session, "fresh@acme.test")

    out = await _accept_invite(db_session, token, monkeypatch)
    assert out["status"] == "success"

    user = db_session.execute(select(UserModel).where(UserModel.email == "fresh@acme.test")).scalar_one()

    crypto = AuthCryptoService(hmac_secret=TEST_HMAC_SECRET)
    fingerprint = crypto.fingerprint_email("fresh@acme.test")
    identity = _load_valid_identity(db=db_session, email_fingerprint=fingerprint)
    assert identity is not None, "user created via invite acceptance must be eligible for passwordless sign-in"
    assert identity[0].id == user.id
    assert identity[1].organization_id == TENANT_ID
    assert identity[1].role == "viewer"


async def test_accept_invite_existing_user_gets_identity_rows(db_session, monkeypatch):
    user = _add_user(db_session, "existing@acme.test")
    db_session.commit()
    token = _seed_invite(db_session, "existing@acme.test")

    out = await _accept_invite(db_session, token, monkeypatch)
    assert out["status"] == "success"
    assert out["user_id"] == str(user.id)

    crypto = AuthCryptoService(hmac_secret=TEST_HMAC_SECRET)
    identity = _load_valid_identity(db=db_session, email_fingerprint=crypto.fingerprint_email("existing@acme.test"))
    assert identity is not None
    assert identity[0].id == user.id
