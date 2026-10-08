"""Regression tests: trial tenants must survive token refresh.

``get_current_user`` (dependencies.py) accepts tenant statuses
``active`` and ``trial`` for opaque cookie sessions, and
``test_trial_tenant_session_passes`` locks that in. But the refresh
flow filtered memberships to ``TenantModel.status == "active"`` only,
so a trial tenant's user could log in yet every ``/auth/refresh``
failed with 403 once the access token expired. The gates must agree.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_repo_root = Path(__file__).resolve().parents[3]
_service_dir = Path(__file__).resolve().parents[2]
for _p in (_repo_root, _service_dir):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

os.environ.setdefault("ADMIN_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AUTH_SECRET_KEY", "trial-refresh-regression-secret")
os.environ.setdefault("SESSION_STORE_BACKEND", "memory")


def _request(headers=None):
    return SimpleNamespace(
        headers=headers or {},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(),
    )


def _seed(status: str):
    """Real SQLite rows: trial/active tenant, user, active membership, role."""
    from services.admin.app.sqlalchemy_models import (
        Base,
        MembershipModel,
        RoleModel,
        TenantModel,
        UserModel,
    )

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for table in ("tenants", "users", "roles", "memberships"):
        Base.metadata.tables[table].create(engine, checkfirst=True)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    tenant = TenantModel(id=uuid.uuid4(), name="Trial Co", slug=f"trial-{uuid.uuid4().hex[:8]}", status=status)
    user = UserModel(id=uuid.uuid4(), email="trial@example.com", status="active")
    role = RoleModel(id=uuid.uuid4(), tenant_id=None, name="Owner", permissions=["*"])
    db.add_all([tenant, user, role])
    db.flush()
    db.add(MembershipModel(user_id=user.id, tenant_id=tenant.id, role_id=role.id, is_active=True))
    db.commit()
    return db, tenant, user


async def _refresh(db, tenant, user):
    from services.admin.app.auth.refresh_router import RefreshRequest, refresh_session
    from services.admin.app.auth_utils import create_access_token, hash_token
    from services.admin.app.session_store import InMemorySessionStore, SessionData

    raw_refresh = "refresh-token-" + uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    store = InMemorySessionStore()
    await store.create_session(
        SessionData(
            id=uuid.uuid4(),
            user_id=user.id,
            refresh_token_hash=hash_token(raw_refresh),
            family_id=uuid.uuid4(),
            is_revoked=False,
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=7),
            user_agent="pytest",
            ip_address="127.0.0.1",
        )
    )
    old_access = create_access_token({"sub": str(user.id), "tenant_id": str(tenant.id), "tv": 0})
    return await refresh_session.__wrapped__(
        RefreshRequest(refresh_token=raw_refresh),
        _request({"Authorization": f"Bearer {old_access}"}),
        db=db,
        session_store=store,
    )


@pytest.mark.asyncio
async def test_refresh_succeeds_for_trial_tenant():
    from services.admin.app.auth_utils import decode_access_token

    db, tenant, user = _seed("trial")
    tenant_id = str(tenant.id)
    try:
        result = await _refresh(db, tenant, user)
    finally:
        db.close()

    assert str(result.tenant_id) == tenant_id
    claims = decode_access_token(result.access_token)
    assert claims["tenant_status"] == "trial"


@pytest.mark.asyncio
async def test_refresh_still_succeeds_for_active_tenant():
    db, tenant, user = _seed("active")
    tenant_id = str(tenant.id)
    try:
        result = await _refresh(db, tenant, user)
    finally:
        db.close()

    assert str(result.tenant_id) == tenant_id
