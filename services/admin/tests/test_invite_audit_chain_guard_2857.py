"""Invite state changes must not commit without an audit-chain entry — #2857.

``AuditLogger.log_event`` signals failure by **returning None**, not by raising:
``audit.py`` catches ``SQLAlchemyError``, ``ValueError``, ``RuntimeError``,
``OSError``, ``AttributeError``, ``TypeError`` and ``KeyError``, then returns
``None``. A caller that wraps the call in ``try/except ... raise`` is therefore
guarding against a path that never executes for any realistic failure.

That interface mismatch is what #2857 reports. It was fixed for review
decisions (``metrics.py``), but the three ``identity_access`` transitions in
``invite_routes.py`` still discarded the return value and committed regardless:
an invite could be created, revoked, or accepted with no tamper-evident record
that it was authorized. The state change persisted; the evidence did not.

Each test forces ``log_event`` to return ``None`` and asserts two things — the
request fails with 500, **and** the row is genuinely absent or unchanged in the
database. Asserting only the status code would pass against a handler that
returned 500 after committing, which is the exact bug.

Harness mirrors ``test_supplier_demo_reset_rbac_1407.py``: in-memory SQLite,
tables created directly, routers mounted with the auth dependencies overridden.
"""

from __future__ import annotations

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
from sqlalchemy import create_engine, select  # noqa: E402
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
    # create_invite looks up the caller's own active role before it will
    # issue an invite; without this it 403s long before the audit write.
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
    """Return (client, session, invite_routes) with auth stubbed out."""
    session = _make_session()
    import app.invite_routes as invite_routes
    from app.dependencies import PermissionChecker, get_current_user
    from app.database import get_session

    # The audit chain is the subject under test; everything else is stubbed
    # only as far as needed to reach it.
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
    # dependency_overrides keys on the exact object, and each
    # ``Depends(PermissionChecker("..."))`` in the routes built its own
    # instance — so overriding by key never matches. Patch __call__ instead,
    # as test_supplier_demo_reset_rbac_1407.py does. The stub must keep the
    # real signature: FastAPI introspects it, and *args/**kwargs would be
    # read as required query parameters.
    def _permit(self, user=Depends(get_current_user), db=Depends(get_session)):
        return True

    monkeypatch.setattr(PermissionChecker, "__call__", _permit)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, session, invite_routes, monkeypatch


def _fail_audit(monkeypatch, invite_routes):
    """Make log_event signal failure the way it really does — by returning None."""
    monkeypatch.setattr(invite_routes.AuditLogger, "log_event", staticmethod(lambda *a, **k: None))


def _seed_invite(session: Session, **overrides) -> InviteModel:
    invite = InviteModel(
        id=uuid4(),
        tenant_id=TENANT_ID,
        email="invitee@example.com",
        role_id=ROLE_ID,
        token_hash="0" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        created_by=ADMIN_ID,
        **overrides,
    )
    session.add(invite)
    session.commit()
    return invite


class TestCreateInvite:
    def test_audit_failure_aborts_and_persists_no_invite(self, harness):
        client, session, invite_routes, monkeypatch = harness
        _fail_audit(monkeypatch, invite_routes)

        resp = client.post(
            "/admin/invites",
            json={"email": "newperson@example.com", "role_id": str(ROLE_ID)},
        )

        assert resp.status_code == 500, resp.text
        assert resp.json()["detail"]["error"] == "audit_write_failed"

        session.expire_all()
        rows = session.execute(
            select(InviteModel).where(InviteModel.email == "newperson@example.com")
        ).scalars().all()
        assert rows == [], (
            "an invite was committed with no audit-chain entry — the state change "
            "persisted while the evidence that it was authorized did not (#2857)"
        )


class TestRevokeInvite:
    def test_audit_failure_aborts_and_leaves_invite_active(self, harness):
        client, session, invite_routes, monkeypatch = harness
        invite = _seed_invite(session)
        _fail_audit(monkeypatch, invite_routes)

        resp = client.post(f"/admin/invites/{invite.id}/revoke")

        assert resp.status_code == 500, resp.text
        assert resp.json()["detail"]["error"] == "audit_write_failed"

        session.expire_all()
        refreshed = session.get(InviteModel, invite.id)
        assert refreshed.revoked_at is None, (
            "the invite was revoked with no audit-chain entry (#2857)"
        )


class TestGuardIsReachable:
    """Guard the guard.

    If ``log_event`` ever starts raising instead of returning None, these tests
    would still pass for the wrong reason — the ``except`` clause would fire.
    Pin the contract the guard is written against.
    """

    def test_log_event_signals_failure_by_returning_none(self):
        import inspect

        from app.audit import AuditLogger

        source = inspect.getsource(AuditLogger.log_event)
        assert "return None" in source, (
            "AuditLogger.log_event no longer returns None on failure. The "
            "`if audit_entry_id is None` guards in invite_routes.py are written "
            "against that contract — re-check them (#2857)."
        )

    def test_all_invite_audit_calls_check_their_return_value(self):
        """No new call site may quietly discard the result."""
        source = (service_dir / "app" / "invite_routes.py").read_text(encoding="utf-8")
        calls = source.count("AuditLogger.log_event(")
        guards = source.count("if audit_entry_id is None:")
        assert calls > 0, "no AuditLogger.log_event calls found — has the file moved?"
        assert guards == calls, (
            f"invite_routes.py makes {calls} audit-chain writes but only {guards} check "
            f"the return value. A discarded result means that transition can commit "
            f"with no tamper-evident record (#2857)."
        )
