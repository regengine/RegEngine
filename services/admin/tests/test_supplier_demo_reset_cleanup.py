"""Demo reset must not leave graph and canonical rows behind.

The reset hard-deletes the supplier's Postgres rows (facilities, lots,
CTE events, funnel events) and reseeds Salinas Valley fixtures. Before
this fix it left two mirrors live:

1. Neo4j nodes mirrored by ``supplier_graph_sync`` (CTEEvent, TLC,
   SupplierFacility) kept their live shape, so lineage traversal still
   returned the wiped demo data.
2. Canonical ``fsma.traceability_events`` rows bridged from the deleted
   supplier events (``source_system='supplier_portal'``) stayed
   ``status='active'``, so FDA export and compliance scoring still saw
   the wiped data.

The fix tombstones the graph nodes (``status='void'`` marker, never a
hard delete so shared TLC evidence survives) and voids the bridged
canonical rows (``status='rejected'``, which every canonical reader
already excludes).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
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
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

TEST_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000002")


def _make_db() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    for t in (
        TenantModel.__table__,
        UserModel.__table__,
        SupplierFacilityModel.__table__,
        SupplierFacilityFTLCategoryModel.__table__,
        SupplierTraceabilityLotModel.__table__,
        SupplierCTEEventModel.__table__,
        SupplierFunnelEventModel.__table__,
        AuditLogModel.__table__,
    ):
        t.create(bind=engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
    session = session_local()
    session.add(
        TenantModel(
            id=TEST_TENANT_ID,
            name="Demo Tenant",
            slug="demo-tenant",
            status="active",
            settings={"is_demo": True},
        )
    )
    session.add(
        UserModel(
            id=TEST_USER_ID,
            email="supplier@example.com",
            status="active",
            is_sysadmin=False,
        )
    )
    session.commit()
    return session


def _attach_fsma(session: Session) -> None:
    """Create a minimal stand-in for the canonical table.

    Production keeps it at ``fsma.traceability_events`` in Postgres. SQLite
    has no schemas, so we attach a second in-memory database under the
    ``fsma`` name; the schema-qualified UPDATE under test then runs for
    real instead of raising "no such table".
    """
    session.execute(text("ATTACH DATABASE ':memory:' AS fsma"))
    session.execute(
        text("""
            CREATE TABLE fsma.traceability_events (
                event_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                source_system TEXT NOT NULL,
                source_record_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
            )
        """)
    )


def _seed_supplier_rows(session: Session) -> dict[str, str]:
    facility = SupplierFacilityModel(
        tenant_id=TEST_TENANT_ID,
        supplier_user_id=TEST_USER_ID,
        name="Old Farm",
        street="1 Old Rd",
        city="Salinas",
        state="CA",
        postal_code="93908",
        roles=["Grower"],
    )
    session.add(facility)
    session.flush()
    lot = SupplierTraceabilityLotModel(
        tenant_id=TEST_TENANT_ID,
        supplier_user_id=TEST_USER_ID,
        facility_id=facility.id,
        tlc_code="TLC-OLD-1",
        product_description="Baby Spinach",
        status="active",
    )
    session.add(lot)
    session.flush()
    event = SupplierCTEEventModel(
        tenant_id=TEST_TENANT_ID,
        supplier_user_id=TEST_USER_ID,
        facility_id=facility.id,
        lot_id=lot.id,
        cte_type="harvesting",
        kde_data={"quantity": 10, "unit_of_measure": "cases"},
        payload_sha256="0" * 64,
        merkle_hash="1" * 64,
        sequence_number=1,
        obligation_ids=[],
    )
    session.add(event)
    session.commit()
    return {
        "facility_id": str(facility.id),
        "tlc_code": "TLC-OLD-1",
        "event_id": str(event.id),
    }


def _seed_canonical_row(session: Session, source_record_id: str, status: str = "active") -> None:
    session.execute(
        text("""
            INSERT INTO fsma.traceability_events
                (event_id, tenant_id, source_system, source_record_id, status)
            VALUES (:event_id, :tenant_id, 'supplier_portal', :source_record_id, :status)
        """),
        {
            "event_id": f"canonical-{source_record_id}",
            "tenant_id": str(TEST_TENANT_ID),
            "source_record_id": source_record_id,
            "status": status,
        },
    )


def _install_app(session: Session, monkeypatch: pytest.MonkeyPatch, tombstone_calls: list) -> FastAPI:
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

    def _permit_stub(self, user=Depends(get_current_user), db=Depends(get_session)):
        return True

    monkeypatch.setattr(PermissionChecker, "__call__", _permit_stub)
    monkeypatch.setattr(funnel_routes.TenantContext, "get_tenant_context", lambda _db: TEST_TENANT_ID)
    monkeypatch.setattr(
        funnel_routes.supplier_graph_sync,
        "record_facility_ftl_scoping",
        lambda **_kw: None,
    )
    monkeypatch.setattr(funnel_routes.supplier_graph_sync, "record_cte_event", lambda **_kw: None)
    monkeypatch.setattr(
        funnel_routes.supplier_graph_sync,
        "record_supplier_demo_reset",
        lambda **kw: tombstone_calls.append(kw),
    )
    funnel_routes._DEMO_RESET_RATE_LIMIT.reset(f"{TEST_TENANT_ID}:{TEST_USER_ID}")
    return test_app


# ---------------------------------------------------------------- graph sync


class _FakeSession:
    def __init__(self, sink):
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, params):
        self._sink.append((query, params))

        class _Result:
            def single(self):
                return None

        return _Result()


class _FakeDriver:
    def __init__(self):
        self.calls = []

    def session(self):
        return _FakeSession(self.calls)


def test_tombstone_query_is_tenant_scoped_and_marks_void():
    from app.supplier_graph_sync import SupplierGraphSync

    driver = _FakeDriver()
    sync = SupplierGraphSync(enabled=True, driver=driver)
    sync.record_supplier_demo_reset(
        tenant_id="tenant-1",
        supplier_user_id="user-1",
        cte_event_ids=["cte-1"],
        tlc_codes=["TLC-1"],
        facility_ids=["fac-1"],
    )

    assert len(driver.calls) == 1
    query, params = driver.calls[0]
    assert params["operation"] == "supplier_demo_reset"
    assert params["tenant_id"] == "tenant-1"
    assert params["cte_event_ids"] == ["cte-1"]
    assert params["tlc_codes"] == ["TLC-1"]
    assert params["facility_ids"] == ["fac-1"]
    # Tenant-scoped tombstone, never a hard delete.
    assert "tenant_id" in query
    assert "void" in query
    assert "DETACH DELETE" not in query
    assert "CTEEvent" in query
    assert "SupplierFacility" in query


def test_tombstone_noop_when_sync_disabled():
    from app.supplier_graph_sync import SupplierGraphSync

    sync = SupplierGraphSync(enabled=False, driver=None)
    sync.record_supplier_demo_reset(
        tenant_id="tenant-1",
        supplier_user_id="user-1",
        cte_event_ids=["cte-1"],
        tlc_codes=["TLC-1"],
        facility_ids=["fac-1"],
    )


# ------------------------------------------------------------------- route


def test_reset_tombstones_graph_nodes_for_doomed_rows(monkeypatch: pytest.MonkeyPatch):
    session = _make_db()
    try:
        ids = _seed_supplier_rows(session)
        tombstone_calls: list = []
        app = _install_app(session, monkeypatch, tombstone_calls)
        with TestClient(app) as client:
            resp = client.post("/v1/supplier/demo/reset?confirm=reset-supplier-demo-data")
        assert resp.status_code == 200, resp.text

        assert len(tombstone_calls) == 1
        call = tombstone_calls[0]
        assert call["tenant_id"] == str(TEST_TENANT_ID)
        assert call["supplier_user_id"] == str(TEST_USER_ID)
        assert call["cte_event_ids"] == [ids["event_id"]]
        assert call["tlc_codes"] == [ids["tlc_code"]]
        assert call["facility_ids"] == [ids["facility_id"]]

        # The Postgres rows are still hard-deleted as before: the seeded
        # event id is gone (the reseed plants fresh events afterwards,
        # so the table itself is not empty).
        session.expire_all()
        assert (
            session.execute(
                select(SupplierCTEEventModel).where(SupplierCTEEventModel.id == UUID(ids["event_id"]))
            ).all()
            == []
        )
    finally:
        session.close()


def test_reset_voids_bridged_canonical_rows_only(monkeypatch: pytest.MonkeyPatch):
    session = _make_db()
    try:
        _attach_fsma(session)
        ids = _seed_supplier_rows(session)
        _seed_canonical_row(session, ids["event_id"])
        _seed_canonical_row(session, "unrelated-event-id")
        other_event_id = str(uuid4())
        _seed_canonical_row(session, other_event_id)
        session.commit()

        tombstone_calls: list = []
        app = _install_app(session, monkeypatch, tombstone_calls)
        with TestClient(app) as client:
            resp = client.post("/v1/supplier/demo/reset?confirm=reset-supplier-demo-data")
        assert resp.status_code == 200, resp.text

        statuses = {
            row.source_record_id: row.status
            for row in session.execute(text("SELECT source_record_id, status FROM fsma.traceability_events"))
            .mappings()
            .all()
        }
        # The bridged row for the wiped supplier event is voided; the
        # canonical readers that filter status='active' no longer see it.
        assert statuses[ids["event_id"]] == "rejected"
        assert statuses["unrelated-event-id"] == "active"
        # Reseed bridged fresh rows as active; they share no ids with the
        # wiped ones, so every other row is untouched.
        assert statuses[other_event_id] == "active"
    finally:
        session.close()


def test_reset_still_succeeds_without_canonical_schema(monkeypatch: pytest.MonkeyPatch):
    """Dev/test databases without the ``fsma`` schema must not 500.

    The void step degrades to a logged warning when the canonical table
    is absent; the supplier delete plus reseed still commits.
    """
    session = _make_db()
    try:
        _seed_supplier_rows(session)
        tombstone_calls: list = []
        app = _install_app(session, monkeypatch, tombstone_calls)
        with TestClient(app) as client:
            resp = client.post("/v1/supplier/demo/reset?confirm=reset-supplier-demo-data")
        assert resp.status_code == 200, resp.text
        assert len(tombstone_calls) == 1
    finally:
        session.close()
