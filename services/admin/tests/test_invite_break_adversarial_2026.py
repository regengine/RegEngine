"""Break-testing regression tests: invite email case handling, invite write
conflicts, optional accept name, grant_owner scope.

Covers findings from the Oct 2026 break-test pass over
``services/admin/app/invite_routes.py`` and
``services/shared/permissions.py``:

* ``create_invite`` compared emails with exact ``==`` while every downstream
  consumer (``accept_invite``, ``ensure_passwordless_identity``, challenges)
  matches case-insensitively, so a case variant of a member address or of a
  pending invite slipped past the 409 guards and produced duplicate invites.
* Concurrent duplicate creates, and re-invites hitting the unique index on
  backends where it covers revoked rows, raised an unhandled
  ``IntegrityError`` (HTTP 500). Concurrent duplicate accepts had the same
  500 via the membership primary key.
* ``AcceptInviteRequest.name`` was required but never read, so token-only
  clients got a 422.
* ``can_invite_role``'s docstring claimed ``users.invite.grant_owner`` lifts
  the basic tier check for sub-Owner targets; the code (correctly, least
  privilege) honors it for Owner-tier targets only.

Harness mirrors ``test_invite_audit_chain_guard_2857.py``: in-memory SQLite,
tables created directly, routers mounted with the auth dependencies
overridden. SQLite renders ``ix_invites_tenant_email`` as a FULL unique
index (``postgresql_where`` is Postgres-only), so a re-invite after revoke
conflicts there while Postgres (partial index over still-active rows) accepts
it; the re-invite test pins the fail-closed behavior (handled 409, nothing
half-written), not the backend-specific success code.
"""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.sqlalchemy_models import (  # noqa: E402
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
from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

TENANT_ID = UUID("00000000-0000-0000-0000-0000000000a1")
ADMIN_ID = UUID("00000000-0000-0000-0000-0000000000a2")
ROLE_ID = UUID("00000000-0000-0000-0000-0000000000a3")


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    for table in (
        TenantModel.__table__,
        UserModel.__table__,
        RoleModel.__table__,
        MembershipModel.__table__,
        InviteModel.__table__,
        AuditLogModel.__table__,
        UserEmailModel.__table__,
        OrganizationModel.__table__,
        OrganizationMembershipModel.__table__,
    ):
        table.create(bind=engine)

    maker = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
    session = maker()
    session.add(TenantModel(id=TENANT_ID, name="T", slug="t", status="active", settings={}))
    session.add(UserModel(id=ADMIN_ID, email="admin@example.com", status="active", is_sysadmin=False))
    session.add(RoleModel(id=ROLE_ID, tenant_id=TENANT_ID, name="member", permissions=[]))
    session.add(
        MembershipModel(
            user_id=ADMIN_ID,
            tenant_id=TENANT_ID,
            role_id=ROLE_ID,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
    )
    session.commit()
    return session


@pytest.fixture
def harness(monkeypatch):
    session = _make_session()
    import app.invite_routes as invite_routes
    from app.database import get_session
    from app.dependencies import PermissionChecker, get_current_user

    monkeypatch.setattr(invite_routes.TenantContext, "get_tenant_context", staticmethod(lambda db: TENANT_ID))
    monkeypatch.setattr(invite_routes, "can_invite_role", lambda *a, **k: True)
    monkeypatch.setattr(invite_routes, "_send_invite_email", lambda *a, **k: None)
    monkeypatch.setattr(invite_routes.supplier_graph_sync, "record_invite_created", lambda *a, **k: None)
    monkeypatch.setattr(invite_routes.supplier_graph_sync, "record_invite_accepted", lambda *a, **k: None)

    app = FastAPI()
    app.include_router(invite_routes.router)
    admin = session.get(UserModel, ADMIN_ID)
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_session] = lambda: session

    def _permit(self, user=Depends(get_current_user), db=Depends(get_session)):
        return True

    monkeypatch.setattr(PermissionChecker, "__call__", _permit)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, session, invite_routes, monkeypatch


def _seed_invite(session: Session, email: str = "invitee@example.com", **overrides) -> InviteModel:
    invite = InviteModel(
        id=uuid4(),
        tenant_id=TENANT_ID,
        email=email,
        role_id=ROLE_ID,
        token_hash=hashlib.sha256(uuid4().bytes).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        created_by=ADMIN_ID,
        **overrides,
    )
    session.add(invite)
    session.commit()
    return invite


class TestCaseVariantInvites:
    def test_case_variant_of_existing_member_is_rejected(self, harness):
        """Pre-fix this returned 200 and issued a live invite to an address
        that resolves to an existing member, bypassing the 409 guard."""
        client, session, _, _ = harness

        resp = client.post("/admin/invites", json={"email": "ADMIN@EXAMPLE.COM", "role_id": str(ROLE_ID)})

        assert resp.status_code == 409, resp.text
        session.expire_all()
        rows = session.execute(select(InviteModel).where(InviteModel.tenant_id == TENANT_ID)).scalars().all()
        assert rows == []

    def test_case_variant_of_pending_invite_is_rejected(self, harness):
        """Pre-fix both creates returned 200, leaving two usable tokens for
        one mailbox."""
        client, session, _, _ = harness

        first = client.post("/admin/invites", json={"email": "User@example.com", "role_id": str(ROLE_ID)})
        assert first.status_code == 200, first.text
        second = client.post("/admin/invites", json={"email": "user@EXAMPLE.com", "role_id": str(ROLE_ID)})

        assert second.status_code == 409, second.text

    def test_invite_email_is_stored_normalized(self, harness):
        """Pre-fix the raw mixed-case address was stored while accept matched
        case-insensitively, splitting one mailbox across spellings."""
        client, _, _, _ = harness

        resp = client.post("/admin/invites", json={"email": "MixedCase@Example.COM", "role_id": str(ROLE_ID)})

        assert resp.status_code == 200, resp.text
        assert resp.json()["email"] == "mixedcase@example.com"

    def test_guards_compare_case_insensitively_against_legacy_rows(self, harness):
        """Rows written before normalization (raw case in the DB) must still
        be caught by the pre-checks."""
        client, session, _, _ = harness
        _seed_invite(session, email="LegacyCase@Example.com")

        resp = client.post("/admin/invites", json={"email": "legacycase@example.com", "role_id": str(ROLE_ID)})

        assert resp.status_code == 409, resp.text


class TestInviteWriteConflicts:
    def test_flush_conflict_returns_409_not_500(self, harness):
        """Simulates losing a concurrent-create race at flush time. Pre-fix
        this surfaced as an unhandled 500."""
        client, session, _, monkeypatch = harness

        def _boom():
            raise IntegrityError("INSERT INTO invites", {}, Exception("unique"))

        monkeypatch.setattr(session, "flush", _boom)
        resp = client.post("/admin/invites", json={"email": "raced@example.com", "role_id": str(ROLE_ID)})

        assert resp.status_code == 409, resp.text

    def test_commit_conflict_returns_409_and_persists_nothing(self, harness):
        """Simulates losing a concurrent-create race at commit time."""
        client, session, _, monkeypatch = harness
        real_commit = session.commit
        calls = {"n": 0}

        def _boom_once():
            calls["n"] += 1
            if calls["n"] == 1:
                raise IntegrityError("INSERT INTO invites", {}, Exception("unique"))
            return real_commit()

        monkeypatch.setattr(session, "commit", _boom_once)
        resp = client.post("/admin/invites", json={"email": "raced2@example.com", "role_id": str(ROLE_ID)})

        assert resp.status_code == 409, resp.text
        session.expire_all()
        rows = session.execute(select(InviteModel).where(InviteModel.email == "raced2@example.com")).scalars().all()
        assert rows == []

    def test_reinvite_after_revoke_is_handled_without_500(self, harness):
        """Pre-fix this returned 500 on backends whose unique index covers
        revoked rows. The handler now fails closed with 409."""
        client, session, _, _ = harness
        created = client.post("/admin/invites", json={"email": "back@example.com", "role_id": str(ROLE_ID)})
        assert created.status_code == 200, created.text
        revoked = client.post(f"/admin/invites/{created.json()['id']}/revoke")
        assert revoked.status_code == 200, revoked.text

        resp = client.post("/admin/invites", json={"email": "back@example.com", "role_id": str(ROLE_ID)})

        assert resp.status_code == 409, resp.text
        assert "detail" in resp.json()

    def test_accept_commit_conflict_returns_uniform_400(self, harness):
        """Simulates a double-accept race colliding at commit time. Pre-fix
        this surfaced as an unhandled 500; the endpoint promises a uniform
        400 for every unusable-invite outcome."""
        client, session, _, monkeypatch = harness
        token = "race-token-accept"
        session.add(
            InviteModel(
                id=uuid4(),
                tenant_id=TENANT_ID,
                email="racer@example.com",
                role_id=ROLE_ID,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                created_by=ADMIN_ID,
            )
        )
        session.commit()
        real_commit = session.commit

        def _boom_once():
            monkeypatch.setattr(session, "commit", real_commit)
            raise IntegrityError("INSERT INTO memberships", {}, Exception("unique"))

        monkeypatch.setattr(session, "commit", _boom_once)
        resp = client.post("/auth/accept-invite", json={"token": token})

        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"] == "Invite is not usable"


class TestAcceptInvitePayload:
    def test_accept_without_name_succeeds(self, harness):
        """``name`` is never read by the handler. Pre-fix omitting it was a
        422; token-only clients must get the normal outcome."""
        client, session, _, _ = harness
        token = "nameless-token"
        session.add(
            InviteModel(
                id=uuid4(),
                tenant_id=TENANT_ID,
                email="nameless@example.com",
                role_id=ROLE_ID,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                created_by=ADMIN_ID,
            )
        )
        session.commit()

        resp = client.post("/auth/accept-invite", json={"token": token})

        assert resp.status_code == 201, resp.text
        assert resp.json()["status"] == "success"

    def test_accept_stores_normalized_user_email(self, harness):
        """A legacy mixed-case invite must not create a case-split duplicate
        user identity on accept."""
        client, session, _, _ = harness
        token = "legacy-case-token"
        session.add(
            InviteModel(
                id=uuid4(),
                tenant_id=TENANT_ID,
                email="LegacyUser@Example.COM",
                role_id=ROLE_ID,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                created_by=ADMIN_ID,
            )
        )
        session.commit()

        resp = client.post("/auth/accept-invite", json={"token": token, "name": "Legacy"})

        assert resp.status_code == 201, resp.text
        session.expire_all()
        user = session.execute(
            select(UserModel).where(UserModel.email == "legacyuser@example.com")
        ).scalar_one_or_none()
        assert user is not None


class TestGrantOwnerScope:
    def test_grant_owner_does_not_lift_sub_owner_tier_check(self):
        """Pins the least-privilege behavior: ``users.invite.grant_owner``
        authorizes Owner-tier targets only, never roles above the caller's
        own tier below Owner."""
        from shared.permissions import can_invite_role

        assert (
            can_invite_role(
                caller_role_name="manager",
                caller_permissions=["users.invite.grant_owner"],
                target_role_name="admin",
                target_permissions=[],
            )
            is False
        )
        assert (
            can_invite_role(
                caller_role_name="admin",
                caller_permissions=["users.invite", "users.invite.grant_owner"],
                target_role_name="owner",
                target_permissions=[],
            )
            is True
        )
