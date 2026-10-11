"""create_invite must fold email case the same way accept_invite does (#3225).

accept_invite looks users up with ``lower(trim(email))``, but create_invite
used exact equality for the tenant-member check and the pending-invite
check. A case variant of a member's address therefore got a mailed invite
whose token burned on the existing-membership 400 at accept, and a case
variant of a live invite produced a second email. Both checks now compare
``lower(email)`` so the duplicates are rejected up front with 409.
"""

from __future__ import annotations

import hashlib
import secrets
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
    RoleModel,
    TenantModel,
    UserModel,
)
from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, func, select  # noqa: E402
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
    # The audit chain is not under test; a stubbed success lets the request
    # reach the 201 it would return in production.
    monkeypatch.setattr(invite_routes.AuditLogger, "log_event", staticmethod(lambda *a, **k: "audit-id"))

    app = FastAPI()
    app.include_router(invite_routes.router)
    admin = session.get(UserModel, ADMIN_ID)
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_session] = lambda: session

    def _permit(self, user=Depends(get_current_user), db=Depends(get_session)):
        return True

    monkeypatch.setattr(PermissionChecker, "__call__", _permit)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, session


def _add_member(session: Session, email: str) -> None:
    user = UserModel(id=uuid4(), email=email, status="active", is_sysadmin=False)
    session.add(user)
    session.flush()
    session.add(
        MembershipModel(
            user_id=user.id,
            tenant_id=TENANT_ID,
            role_id=ROLE_ID,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
    )
    session.commit()


def _invite_count(session: Session, email: str) -> int:
    session.expire_all()
    return session.execute(
        select(func.count()).select_from(InviteModel).where(func.lower(InviteModel.email) == email.lower())
    ).scalar()


class TestCreateInviteCaseFolding:
    def test_case_variant_of_member_returns_409(self, harness):
        client, session = harness
        _add_member(session, "Member@Acme.test")

        resp = client.post(
            "/admin/invites",
            json={"email": "member@acme.test", "role_id": str(ROLE_ID)},
        )

        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == "User already a member of this tenant"
        assert _invite_count(session, "member@acme.test") == 0

    def test_case_variant_of_pending_invite_returns_409(self, harness):
        client, session = harness
        session.add(
            InviteModel(
                tenant_id=TENANT_ID,
                email="Pending@Acme.test",
                role_id=ROLE_ID,
                token_hash=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                created_by=ADMIN_ID,
            )
        )
        session.commit()

        resp = client.post(
            "/admin/invites",
            json={"email": "pending@acme.test", "role_id": str(ROLE_ID)},
        )

        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == "Active invite already exists for this email"
        assert _invite_count(session, "pending@acme.test") == 1

    def test_unrelated_email_still_invites(self, harness):
        client, session = harness
        _add_member(session, "someone@acme.test")

        resp = client.post(
            "/admin/invites",
            json={"email": "newperson@acme.test", "role_id": str(ROLE_ID)},
        )

        assert resp.status_code == 200, resp.text
        assert _invite_count(session, "newperson@acme.test") == 1
