"""Invite acceptance must revalidate the role at accept time.

An invite stores a role_id checked at creation. If the role is deleted or
moved to another tenant before the invite is accepted, the old code created
the membership anyway (dangling or cross-tenant role) and provisioned the
identity with role_name None. The fix rechecks existence and tenant and
returns the uniform 400 for a stale role.
"""

from __future__ import annotations

import hashlib
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

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
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

TENANT_ID = UUID("00000000-0000-0000-0000-0000000000b1")
OTHER_TENANT_ID = UUID("00000000-0000-0000-0000-0000000000b2")
ROLE_ID = UUID("00000000-0000-0000-0000-0000000000b3")


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
    session.add(TenantModel(id=OTHER_TENANT_ID, name="O", slug="o", status="active", settings={}))
    session.add(RoleModel(id=ROLE_ID, tenant_id=TENANT_ID, name="member", permissions=[]))
    session.commit()
    return session


def _harness(monkeypatch):
    session = _make_session()
    import app.invite_routes as invite_routes
    from app.database import get_session

    monkeypatch.setattr(invite_routes, "ensure_passwordless_identity", lambda *a, **k: None)
    monkeypatch.setattr(invite_routes.supplier_graph_sync, "record_invite_accepted", lambda *a, **k: None)

    app = FastAPI()
    app.include_router(invite_routes.router)
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app, raise_server_exceptions=False)
    return client, session


def _seed_invite(session: Session, role_id, tenant_id=TENANT_ID):
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    invite = InviteModel(
        id=uuid4(),
        tenant_id=tenant_id,
        email="invitee@example.com",
        role_id=role_id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        created_by=uuid4(),
    )
    session.add(invite)
    session.commit()
    return invite, raw_token


def test_accept_rejects_deleted_role(monkeypatch):
    client, session = _harness(monkeypatch)
    missing_role_id = uuid4()
    invite, raw_token = _seed_invite(session, missing_role_id)

    resp = client.post("/auth/accept-invite", json={"token": raw_token, "name": "Invitee"})

    assert resp.status_code == 400, resp.text
    session.expire_all()
    memberships = session.execute(select(MembershipModel)).scalars().all()
    assert memberships == []
    refreshed = session.get(InviteModel, invite.id)
    assert refreshed.accepted_at is None


def test_accept_rejects_role_from_other_tenant(monkeypatch):
    client, session = _harness(monkeypatch)
    other_role_id = uuid4()
    session.add(RoleModel(id=other_role_id, tenant_id=OTHER_TENANT_ID, name="member", permissions=[]))
    session.commit()
    invite, raw_token = _seed_invite(session, other_role_id)

    resp = client.post("/auth/accept-invite", json={"token": raw_token, "name": "Invitee"})

    assert resp.status_code == 400, resp.text
    session.expire_all()
    memberships = session.execute(select(MembershipModel)).scalars().all()
    assert memberships == []


def test_accept_succeeds_with_valid_role(monkeypatch):
    client, session = _harness(monkeypatch)
    _invite, raw_token = _seed_invite(session, ROLE_ID)

    resp = client.post("/auth/accept-invite", json={"token": raw_token, "name": "Invitee"})

    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "success"
    session.expire_all()
    memberships = session.execute(select(MembershipModel)).scalars().all()
    assert len(memberships) == 1
    assert memberships[0].role_id == ROLE_ID


def test_accept_succeeds_with_system_role(monkeypatch):
    client, session = _harness(monkeypatch)
    system_role_id = uuid4()
    session.add(RoleModel(id=system_role_id, tenant_id=None, name="viewer", permissions=[]))
    session.commit()
    _invite, raw_token = _seed_invite(session, system_role_id)

    resp = client.post("/auth/accept-invite", json={"token": raw_token, "name": "Invitee"})

    assert resp.status_code == 201, resp.text
    session.expire_all()
    memberships = session.execute(select(MembershipModel)).scalars().all()
    assert len(memberships) == 1
    assert memberships[0].role_id == system_role_id
