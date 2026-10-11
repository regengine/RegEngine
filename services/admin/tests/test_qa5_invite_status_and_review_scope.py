"""QA5: invite acceptance must honor both user status fields.

Authentication requires ``users.status == 'active'`` AND
``users.global_status == 'active'`` (see user_routes). ``accept_invite``
checked only ``status``, so a globally-suspended user could accept a
pending invite and walk away with a live membership plus fresh
passwordless identity rows.

Also pins ``get_hallucination`` tenant scoping: the detail getter had
no tenant check while ``resolve_hallucination`` rejects cross-tenant
access (#1360). A caller passing another tenant's review UUID could
read its full ``text_raw``.
"""

from __future__ import annotations

import hashlib
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytest.importorskip("sqlalchemy")

_REPO_ADMIN = Path(__file__).resolve().parents[1]
if str(_REPO_ADMIN) not in sys.path:
    sys.path.insert(0, str(_REPO_ADMIN))


# ---------------------------------------------------------------------------
# accept_invite: fake session mirroring test_accept_invite_rls_2899.py
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, invite, user, membership=None):
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
        self.info = {}
        self._invite = invite
        self._user = user
        self._membership = membership
        self.added = []
        self.committed = False

    def execute(self, statement, params=None):
        sql = str(statement)
        if "FROM invites" in sql:
            return _Result(self._invite)
        if "FROM users" in sql:
            return _Result(self._user)
        if "FROM memberships" in sql:
            return _Result(self._membership)
        return _Result(None)

    def get(self, _model, _pk):
        return SimpleNamespace(name="Member")

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


def _make_invite(tenant_id, email="invitee@example.com"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email=email,
        role_id=uuid.uuid4(),
        token_hash=hashlib.sha256(b"raw-token").hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        revoked_at=None,
        accepted_at=None,
    )


def _starlette_request():
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/accept-invite",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


async def _accept(db):
    from app.invite_routes import AcceptInviteRequest, accept_invite

    payload = AcceptInviteRequest(token="raw-token", name="Invitee")
    target = accept_invite.__wrapped__ if hasattr(accept_invite, "__wrapped__") else accept_invite
    with (
        patch("app.invite_routes.ensure_passwordless_identity"),
        patch("app.invite_routes.AuditLogger.log_event"),
        patch("app.invite_routes.supplier_graph_sync"),
    ):
        return await target(payload=payload, request=_starlette_request(), db=db)


@pytest.mark.asyncio
async def test_globally_suspended_user_cannot_accept_invite():
    """status='active' but global_status='suspended' must hit the
    uniform 400 and create no membership (pre-fix: membership created)."""
    from app.sqlalchemy_models import MembershipModel
    from fastapi import HTTPException

    tenant_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), email="invitee@example.com", status="active", global_status="suspended")
    db = _FakeSession(invite=_make_invite(tenant_id), user=user)

    with pytest.raises(HTTPException) as exc:
        await _accept(db)

    assert exc.value.status_code == 400
    assert not [o for o in db.added if isinstance(o, MembershipModel)]


@pytest.mark.asyncio
async def test_fully_active_user_still_accepts_invite():
    """Negative control: both flags active keeps the happy path."""
    tenant_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), email="invitee@example.com", status="active", global_status="active")
    db = _FakeSession(invite=_make_invite(tenant_id), user=user)

    result = await _accept(db)

    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_erased_user_cannot_accept_invite():
    """status='erased' stays rejected (pre-existing #1337 behavior)."""
    from fastapi import HTTPException

    tenant_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), email="invitee@example.com", status="erased", global_status="erased")
    db = _FakeSession(invite=_make_invite(tenant_id), user=user)

    with pytest.raises(HTTPException) as exc:
        await _accept(db)

    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# get_hallucination tenant scoping (metrics.HallucinationTracker)
# ---------------------------------------------------------------------------


class _GetSession:
    def __init__(self, item):
        self._item = item

    def get(self, _model, _pk):
        return self._item

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class TestGetHallucinationTenantScope:
    def _tracker(self, item):
        from contextlib import contextmanager

        from app.metrics import HallucinationTracker

        @contextmanager
        def scope(tenant_id=None):
            yield _GetSession(item)

        tracker = HallucinationTracker(session_factory=lambda: _GetSession(item), redis_client=None)
        tracker._session_scope = scope
        return tracker

    def test_matching_tenant_returns_item(self):
        tenant = uuid.uuid4()
        item = SimpleNamespace(
            id=uuid.uuid4(),
            tenant_id=tenant,
            doc_hash="h",
            confidence_score=0.5,
            status="PENDING",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
            extraction={"attributes": {}},
            provenance=None,
            reviewer_id=None,
            text_raw="raw",
        )
        result = self._tracker(item).get_hallucination(str(item.id), tenant_id=str(tenant))
        assert result["doc_hash"] == "h"

    def test_cross_tenant_uuid_is_404(self):
        from app.metrics import HallucinationTracker  # noqa: F401

        item = SimpleNamespace(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            doc_hash="h",
            confidence_score=0.5,
            status="PENDING",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
            extraction={"attributes": {}},
            provenance=None,
            reviewer_id=None,
            text_raw="raw",
        )
        with pytest.raises(LookupError, match="review_item_not_found"):
            self._tracker(item).get_hallucination(str(item.id), tenant_id=str(uuid.uuid4()))

    def test_omitted_tenant_keeps_legacy_lookup(self):
        item = SimpleNamespace(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            doc_hash="h",
            confidence_score=0.5,
            status="PENDING",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
            extraction={"attributes": {}},
            provenance=None,
            reviewer_id=None,
            text_raw="raw",
        )
        result = self._tracker(item).get_hallucination(str(item.id))
        assert result["doc_hash"] == "h"
