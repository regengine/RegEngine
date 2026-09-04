"""Regression coverage for admin tenant provisioning."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from services.admin.app.privileged_auth import PrivilegedActor
from services.admin.app.routes import TenantCreateRequest, create_tenant
from services.admin.app.sqlalchemy_models import TenantModel


def _run(coro):
    return asyncio.run(coro)


def _session():
    engine = create_engine("sqlite:///:memory:")
    TenantModel.__table__.create(engine)
    return sessionmaker(bind=engine)()


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/admin/tenants",
            "headers": [],
            "client": ("203.0.113.50", 12345),
            "server": ("testserver", 443),
            "scheme": "https",
            "query_string": b"",
            "http_version": "1.1",
            "root_path": "",
            "state": {},
            "app": SimpleNamespace(state=SimpleNamespace()),
        }
    )


def _actor() -> PrivilegedActor:
    return PrivilegedActor(
        actor_type="staff_user",
        actor_id="00000000-0000-0000-0000-000000000099",
        session_id="00000000-0000-0000-0000-000000000098",
        auth_method="webauthn",
    )


def test_admin_create_tenant_persists_row_and_returns_existing_id():
    db = _session()

    response = _run(
        create_tenant(
            request=_request(),
            body=TenantCreateRequest(name="Acme Foods"),
            actor=_actor(),
            db=db,
        )
    )

    tenant_id = uuid.UUID(response.tenant_id)
    row = db.get(TenantModel, tenant_id)
    assert row is not None
    assert row.name == "Acme Foods"
    assert row.slug == "acme-foods"
    assert row.status == "active"
    assert response.status == "active"


def test_admin_create_tenant_generates_unique_slugs():
    db = _session()

    first = _run(
        create_tenant(
            request=_request(),
            body=TenantCreateRequest(name="Acme Foods"),
            actor=_actor(),
            db=db,
        )
    )
    second = _run(
        create_tenant(
            request=_request(),
            body=TenantCreateRequest(name="Acme Foods"),
            actor=_actor(),
            db=db,
        )
    )

    rows = db.execute(select(TenantModel).order_by(TenantModel.slug)).scalars().all()
    assert {str(row.id) for row in rows} == {first.tenant_id, second.tenant_id}
    assert [row.slug for row in rows] == ["acme-foods", "acme-foods-2"]
