"""Regression coverage for admin tenant provisioning."""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from services.admin.app.routes import TenantCreateRequest, create_tenant
from services.admin.app.sqlalchemy_models import TenantModel


def _run(coro):
    return asyncio.run(coro)


def _session():
    engine = create_engine("sqlite:///:memory:")
    TenantModel.__table__.create(engine)
    return sessionmaker(bind=engine)()


def test_admin_create_tenant_persists_row_and_returns_existing_id():
    db = _session()

    response = _run(create_tenant(TenantCreateRequest(name="Acme Foods"), True, db))

    tenant_id = uuid.UUID(response.tenant_id)
    row = db.get(TenantModel, tenant_id)
    assert row is not None
    assert row.name == "Acme Foods"
    assert row.slug == "acme-foods"
    assert row.status == "active"
    assert response.status == "active"


def test_admin_create_tenant_generates_unique_slugs():
    db = _session()

    first = _run(create_tenant(TenantCreateRequest(name="Acme Foods"), True, db))
    second = _run(create_tenant(TenantCreateRequest(name="Acme Foods"), True, db))

    rows = db.execute(select(TenantModel).order_by(TenantModel.slug)).scalars().all()
    assert {str(row.id) for row in rows} == {first.tenant_id, second.tenant_id}
    assert [row.slug for row in rows] == ["acme-foods", "acme-foods-2"]
