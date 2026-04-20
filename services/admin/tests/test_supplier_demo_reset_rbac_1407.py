"""#1407 — RBAC + guards on supplier demo reset.

Covers the six guards the issue requires:

1. caller without ``supplier.demo.reset`` → 403
2. tenant not flagged ``settings.is_demo`` → 403
3. missing / wrong ``confirm`` query param → 400
4. second call within the 24h per-tenant window → 429
5. happy path → 200, audit entry written, rows deleted
6. audit write fails (monkeypatched) → 500, no deletes committed

The fixture style mirrors ``test_supplier_onboarding_routes.py``
(in-memory SQLite + manual table create, routers mounted directly,
``PermissionChecker.__call__`` patched so we can exercise both
permitted and denied paths without a real roles/memberships table).
"""
from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.sqlalchemy_models import (
    AuditLogModel,
    SupplierCTEEventModel,
    SupplierFacilityFTLCategoryModel,
    SupplierFacilityModel,
    SupplierFunnelEventModel,
    SupplierTraceabilityLotModel,
    TenantModel,
    UserModel,
)


TEST_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000002")


def _make_db(is_demo: bool) -> tuple[Session, list]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    tables = [
        TenantModel.__table__,
        UserModel.__table__,
        SupplierFacilityModel.__table__,
        SupplierFacilityFTLCategoryModel.__table__,
        SupplierTraceabilityLotModel.__table__,
        SupplierCTEEventModel.__table__,
        SupplierFunnelEventModel.__table__,
        AuditLogModel.__table__,
    ]
    for t in tables:
        t.create(bind=engine)

    session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True
    )
    session = session_local()
    session.add(
        TenantModel(
            id=TEST_TENANT_ID,
            name="Demo Tenant" if is_demo else "Real Tenant",
            slug="demo-tenant" if is_demo else "real-tenant",
            status="active",
            settings={"is_demo": True} if is_demo else {"is_demo": False},
        )
    )
    session.add(
        UserModel(
            id=TEST_USER_ID,
            email="supplier@example.com",
            password_hash="hashed",
            status="active",
            is_sysadmin=False,
        )
    )
    session.commit()
    return session, tables


def _install_app(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    *,
    permit: bool = True,
) -> FastAPI:
    import app.supplier_funnel_routes as funnel_routes
    from app.database import get_session
    from app.dependencies import PermissionChecker, get_current_user

    test_app = FastAPI()
    test_app.include_router(funnel_routes.router, prefix="/v1")

    current_user = session.get(UserModel, TEST_USER_ID)

    def override_get_session():
        yield session

    def override_get_current_user() -> UserModel:
        assert current_user is not None
        return current_user

    test_app.dependency_overrides[get_session] = override_get_session
    test_app.dependency_overrides[get_current_user] = override_get_current_user

    # Permission stub: must keep the same Depends signature as the real
    # __call__ so FastAPI doesn't interpret *args/**kwargs as query params.
    def _permit_stub(self, user=Depends(get_current_user), db=Depends(get_session)):
        return True

    def _deny_stub(self, user=Depends(get_current_user), db=Depends(get_session)):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    monkeypatch.setattr(
        PermissionChecker, "__call__", _permit_stub if permit else _deny_stub
    )

    # Tenant context + graph sync shims.
    monkeypatch.setattr(
        funnel_routes.TenantContext, "get_tenant_context", lambda _db: TEST_TENANT_ID
    )
    monkeypatch.setattr(
        funnel_routes.supplier_graph_sync,
        "record_facility_ftl_scoping",
        lambda **_kw: None,
    )
    monkeypatch.setattr(
        funnel_routes.supplier_graph_sync, "record_cte_event", lambda **_kw: None
    )

    # Reset the per-process rate limiter between tests — the
    # BruteForceLimiter is module-global, so the in-memory counter
    # leaks across tests if we don't clear it.
    funnel_routes._DEMO_RESET_RATE_LIMIT.reset(f"{TEST_TENANT_ID}:{TEST_USER_ID}")

    return test_app


# --------------------------------------------------------------------- guards


def test_denied_without_permission_returns_403(monkeypatch: pytest.MonkeyPatch):
    # Guard 1: caller without ``supplier.demo.reset`` → 403.
    session, _ = _make_db(is_demo=True)
    try:
        app = _install_app(session, monkeypatch, permit=False)
        with TestClient(app) as client:
            resp = client.post(
                "/v1/supplier/demo/reset?confirm=reset-supplier-demo-data"
            )
        assert resp.status_code == 403
    finally:
        session.close()


def test_non_demo_tenant_returns_403(monkeypatch: pytest.MonkeyPatch):
    # Guard 2: tenant without settings.is_demo=True → 403.
    session, _ = _make_db(is_demo=False)
    try:
        app = _install_app(session, monkeypatch, permit=True)
        with TestClient(app) as client:
            resp = client.post(
                "/v1/supplier/demo/reset?confirm=reset-supplier-demo-data"
            )
        assert resp.status_code == 403
        body = resp.json()
        assert body["detail"]["error"] == "not_a_demo_tenant"

        # And no rows were modified — the tenant was never eligible.
        audit_rows = session.execute(select(AuditLogModel)).all()
        assert audit_rows == []
    finally:
        session.close()


def test_missing_confirmation_returns_400(monkeypatch: pytest.MonkeyPatch):
    # Guard 3a: no confirm param → 400.
    session, _ = _make_db(is_demo=True)
    try:
        app = _install_app(session, monkeypatch, permit=True)
        with TestClient(app) as client:
            resp = client.post("/v1/supplier/demo/reset")
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "confirmation_required"
    finally:
        session.close()


def test_wrong_confirmation_returns_400(monkeypatch: pytest.MonkeyPatch):
    # Guard 3b: wrong confirm value → 400 (not a substring match).
    session, _ = _make_db(is_demo=True)
    try:
        app = _install_app(session, monkeypatch, permit=True)
        with TestClient(app) as client:
            resp = client.post("/v1/supplier/demo/reset?confirm=yes-please")
        assert resp.status_code == 400
    finally:
        session.close()


def test_rate_limit_429_on_second_call(monkeypatch: pytest.MonkeyPatch):
    # Guard 4: second call in the 24h window → 429.
    session, _ = _make_db(is_demo=True)
    try:
        app = _install_app(session, monkeypatch, permit=True)
        with TestClient(app) as client:
            first = client.post(
                "/v1/supplier/demo/reset?confirm=reset-supplier-demo-data"
            )
            assert first.status_code == 200, first.text

            second = client.post(
                "/v1/supplier/demo/reset?confirm=reset-supplier-demo-data"
            )
            assert second.status_code == 429
            assert second.json()["detail"]["error"] == "rate_limited"
    finally:
        session.close()


def test_happy_path_writes_audit_and_deletes(monkeypatch: pytest.MonkeyPatch):
    # Guard 5: all guards satisfied → 200 + audit + deletes.
    session, _ = _make_db(is_demo=True)

    # Seed a facility + funnel event that should be deleted.
    session.add(
        SupplierFunnelEventModel(
            tenant_id=TEST_TENANT_ID,
            supplier_user_id=TEST_USER_ID,
            event_name="baseline",
        )
    )
    session.commit()
    pre = session.execute(
        select(SupplierFunnelEventModel).where(
            SupplierFunnelEventModel.supplier_user_id == TEST_USER_ID
        )
    ).all()
    assert len(pre) == 1

    try:
        app = _install_app(session, monkeypatch, permit=True)
        with TestClient(app) as client:
            resp = client.post(
                "/v1/supplier/demo/reset?confirm=reset-supplier-demo-data"
            )
        assert resp.status_code == 200, resp.text

        # Baseline funnel event was wiped (the reset deletes all
        # supplier-owned funnel events, facilities, CTEs, TLCs).
        session.expire_all()
        remaining = session.execute(
            select(SupplierFunnelEventModel).where(
                SupplierFunnelEventModel.event_name == "baseline"
            )
        ).all()
        assert remaining == []

        # Audit entry with the right event_type and the pre-counts
        # recorded in metadata.
        audit_rows = session.execute(
            select(AuditLogModel).where(
                AuditLogModel.event_type == "supplier.demo.reset"
            )
        ).scalars().all()
        assert len(audit_rows) == 1
        md = audit_rows[0].metadata_
        assert md["confirm_phrase_matched"] is True
        assert md["is_demo_tenant"] is True
        assert "row_counts" in md
        assert md["row_counts"]["supplier_funnel_events"] == 1
    finally:
        session.close()


def test_audit_failure_aborts_delete(monkeypatch: pytest.MonkeyPatch):
    # Guard 6: audit insert returns None → 500, no DELETE committed.
    session, _ = _make_db(is_demo=True)

    # Seed a funnel event so we can assert it survives.
    session.add(
        SupplierFunnelEventModel(
            tenant_id=TEST_TENANT_ID,
            supplier_user_id=TEST_USER_ID,
            event_name="must-survive",
        )
    )
    session.commit()

    try:
        app = _install_app(session, monkeypatch, permit=True)
        import app.supplier_funnel_routes as funnel_routes

        # Force audit logging to signal failure.
        monkeypatch.setattr(
            funnel_routes.AuditLogger, "log_event", staticmethod(lambda *a, **k: None)
        )

        with TestClient(app) as client:
            resp = client.post(
                "/v1/supplier/demo/reset?confirm=reset-supplier-demo-data"
            )
        assert resp.status_code == 500
        assert resp.json()["detail"]["error"] == "audit_write_failed"

        # The seeded funnel event must still exist — nothing was
        # deleted because the audit step failed.
        session.expire_all()
        survivors = session.execute(
            select(SupplierFunnelEventModel).where(
                SupplierFunnelEventModel.event_name == "must-survive"
            )
        ).all()
        assert len(survivors) == 1

        # And the rate limit budget was NOT consumed — a follow-up
        # call (after restoring audit) should not be 429.
        assert not funnel_routes._DEMO_RESET_RATE_LIMIT.is_limited(
            f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        )
    finally:
        session.close()
