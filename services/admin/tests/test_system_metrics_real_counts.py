"""System metrics must report real counts, not hardcoded placeholders."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from services.admin.app import system_routes as routes_mod
from services.admin.app.sqlalchemy_models import (
    Base,
    MembershipModel,
    ReviewItemModel,
    SupplierCTEEventModel,
    SupplierFacilityModel,
)


def _session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            MembershipModel.__table__,
            ReviewItemModel.__table__,
            SupplierCTEEventModel.__table__,
            SupplierFacilityModel.__table__,
        ],
    )
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


class _FakeResponse:
    status_code = 200

    def json(self):
        return {}


class _FakeClient:
    async def get(self, url, **kwargs):
        return _FakeResponse()


class _FakeResilientClient:
    async def __aenter__(self):
        return _FakeClient()

    async def __aexit__(self, exc_type, exc, tb):
        return False


async def test_system_metrics_reports_real_tenant_and_job_counts(monkeypatch):
    tenant_id = uuid.uuid4()
    other_tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    factory = _session_factory()
    with factory() as session:
        session.add_all(
            [
                MembershipModel(user_id=user_id, tenant_id=tenant_id, role_id=uuid.uuid4(), is_active=True),
                MembershipModel(user_id=user_id, tenant_id=other_tenant_id, role_id=uuid.uuid4(), is_active=True),
                # Inactive memberships are not active tenants.
                MembershipModel(user_id=user_id, tenant_id=uuid.uuid4(), role_id=uuid.uuid4(), is_active=False),
                # Another user's membership must not leak into this caller's count.
                MembershipModel(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role_id=uuid.uuid4(), is_active=True),
                ReviewItemModel(
                    tenant_id=tenant_id,
                    doc_hash="h1",
                    text_raw="t1",
                    extraction={},
                    confidence_score=0.5,
                    status="PENDING",
                ),
                ReviewItemModel(
                    tenant_id=tenant_id,
                    doc_hash="h2",
                    text_raw="t2",
                    extraction={},
                    confidence_score=0.9,
                    status="RESOLVED",
                ),
                ReviewItemModel(
                    tenant_id=other_tenant_id,
                    doc_hash="h3",
                    text_raw="t3",
                    extraction={},
                    confidence_score=0.5,
                    status="PENDING",
                ),
            ]
        )
        session.commit()

    monkeypatch.setattr(routes_mod, "_resolve_tenant", lambda _db: str(tenant_id))
    monkeypatch.setattr(routes_mod, "_get_ingestion_base", lambda: "https://ingestion.test")
    monkeypatch.setattr(routes_mod, "resilient_client", lambda **_kwargs: _FakeResilientClient())

    db = factory()
    try:
        response = await routes_mod.get_system_metrics(current_user=SimpleNamespace(id=user_id), db=db)
    finally:
        db.close()

    assert response.total_tenants == 2
    assert response.active_jobs == 1
