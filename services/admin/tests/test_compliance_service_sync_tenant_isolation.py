"""Regression tests for #1405 — service-layer tenant filter on compliance alerts.

``ComplianceServiceSync.get_alert``/``acknowledge_alert``/``resolve_alert``
MUST scope every lookup by ``tenant_id``. Even when the caller forgets (or
the route layer's path-tenant check from #1328 is bypassed), a request
with alert id belonging to tenant A and ``tenant_id`` parameter B must
behave as if the alert does not exist — no row returned, no row mutated.

Defense-in-depth: the route layer (#1328) is the primary gate; this
service-layer filter is the second wall. These tests lock that wall in.
"""
from __future__ import annotations

# Admin-test sys.path bootstrap — mirrors test_compliance_routes_idor.py so
# the file loads even when the parent conftest is bypassed (#1435).
import sys
from pathlib import Path as _Path

_SERVICE_DIR = _Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SERVICE_DIR.parent
for _p in (_SERVICE_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture
def session() -> Session:
    """Isolated in-memory SQLite session with compliance tables created.

    Local to this test file so we don't couple to the session-scoped
    engine in conftest (which shares state across tests).
    """
    from services.admin.app.compliance_models import (  # noqa: F401 — registers tables
        ComplianceAlertModel,
        TenantComplianceStatusModel,
    )
    from services.admin.app.sqlalchemy_models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # create_all is best-effort — the admin models include Postgres-only
    # columns (ARRAY, JSONB) that SQLite silently rejects; we only need
    # the two compliance tables here.
    ComplianceAlertModel.__table__.create(engine, checkfirst=True)
    TenantComplianceStatusModel.__table__.create(engine, checkfirst=True)

    SessionLocal = sessionmaker(bind=engine)
    sess = SessionLocal()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


def _make_alert(session: Session, tenant_id: uuid.UUID) -> uuid.UUID:
    """Insert an ACTIVE alert for ``tenant_id`` and return its id."""
    from services.admin.app.compliance_models import ComplianceAlertModel

    now = datetime.now(timezone.utc)
    alert = ComplianceAlertModel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        source_type="MANUAL",
        source_id="test-source",
        title="Test alert",
        summary="For tenant-isolation regression tests.",
        severity="HIGH",
        countdown_start=now,
        countdown_end=now + timedelta(hours=24),
        countdown_hours=24,
        required_actions=[],
        status="ACTIVE",
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert.id


@pytest.mark.security
def test_get_alert_returns_alert_for_owning_tenant(session):
    """#1405: ``get_alert(id, tenant_A)`` returns the alert when it belongs to A."""
    from services.admin.app.compliance_service_sync import ComplianceServiceSync

    alert_id = _make_alert(session, TENANT_A)
    service = ComplianceServiceSync(session)

    got = service.get_alert(alert_id, TENANT_A)

    assert got is not None
    assert got.id == alert_id
    assert got.tenant_id == TENANT_A


@pytest.mark.security
def test_get_alert_returns_none_for_foreign_tenant(session):
    """#1405: tenant_B cannot fetch tenant_A's alert, even with the correct id."""
    from services.admin.app.compliance_service_sync import ComplianceServiceSync

    alert_id = _make_alert(session, TENANT_A)
    service = ComplianceServiceSync(session)

    got = service.get_alert(alert_id, TENANT_B)

    # Intentionally indistinguishable from "does not exist" — must not
    # leak the existence of another tenant's alert id.
    assert got is None


@pytest.mark.security
def test_acknowledge_alert_refuses_cross_tenant(session):
    """#1405: acknowledging tenant_A's alert as tenant_B must not mutate state."""
    from services.admin.app.compliance_models import ComplianceAlertModel
    from services.admin.app.compliance_service_sync import ComplianceServiceSync

    alert_id = _make_alert(session, TENANT_A)
    service = ComplianceServiceSync(session)

    out = service.acknowledge_alert(alert_id, TENANT_B, user_id="attacker")

    assert out is None
    # Verify the alert row is untouched.
    session.expire_all()
    row = session.get(ComplianceAlertModel, alert_id)
    assert row is not None
    assert row.status == "ACTIVE"
    assert row.acknowledged_at is None
    assert row.acknowledged_by is None


@pytest.mark.security
def test_acknowledge_alert_succeeds_for_owning_tenant(session):
    """Positive control: owning-tenant acknowledge still works end-to-end."""
    from services.admin.app.compliance_models import ComplianceAlertModel
    from services.admin.app.compliance_service_sync import ComplianceServiceSync

    alert_id = _make_alert(session, TENANT_A)
    service = ComplianceServiceSync(session)

    out = service.acknowledge_alert(alert_id, TENANT_A, user_id="owner")

    assert out is not None
    assert out.status == "ACKNOWLEDGED"
    assert out.acknowledged_by == "owner"

    session.expire_all()
    row = session.get(ComplianceAlertModel, alert_id)
    assert row.status == "ACKNOWLEDGED"


@pytest.mark.security
def test_resolve_alert_refuses_cross_tenant(session):
    """#1405: resolving tenant_A's alert as tenant_B must not mutate state."""
    from services.admin.app.compliance_models import ComplianceAlertModel
    from services.admin.app.compliance_service_sync import ComplianceServiceSync

    alert_id = _make_alert(session, TENANT_A)
    service = ComplianceServiceSync(session)

    out = service.resolve_alert(
        alert_id, TENANT_B, user_id="attacker", notes="mass-resolve attempt",
    )

    assert out is None
    session.expire_all()
    row = session.get(ComplianceAlertModel, alert_id)
    assert row is not None
    assert row.status == "ACTIVE"
    assert row.resolved_at is None
    assert row.resolved_by is None
    assert row.resolution_notes is None


@pytest.mark.security
def test_resolve_alert_succeeds_for_owning_tenant(session):
    """Positive control: owning-tenant resolve still works end-to-end."""
    from services.admin.app.compliance_models import ComplianceAlertModel
    from services.admin.app.compliance_service_sync import ComplianceServiceSync

    alert_id = _make_alert(session, TENANT_A)
    service = ComplianceServiceSync(session)

    out = service.resolve_alert(
        alert_id, TENANT_A, user_id="owner", notes="fixed it",
    )

    assert out is not None
    assert out.status == "RESOLVED"
    assert out.resolved_by == "owner"
    assert out.resolution_notes == "fixed it"

    session.expire_all()
    row = session.get(ComplianceAlertModel, alert_id)
    assert row.status == "RESOLVED"


@pytest.mark.security
def test_cross_tenant_id_does_not_leak_via_wrong_tenant_resolve(session):
    """Combined scenario — tenant_A has alert; tenant_B both reads and
    writes using that id. Both must be no-ops; tenant_A's alert must
    remain exactly as created."""
    from services.admin.app.compliance_models import ComplianceAlertModel
    from services.admin.app.compliance_service_sync import ComplianceServiceSync

    alert_id = _make_alert(session, TENANT_A)
    service = ComplianceServiceSync(session)

    assert service.get_alert(alert_id, TENANT_B) is None
    assert service.acknowledge_alert(alert_id, TENANT_B, user_id="attacker") is None
    assert (
        service.resolve_alert(alert_id, TENANT_B, user_id="attacker", notes="x")
        is None
    )

    session.expire_all()
    row = session.get(ComplianceAlertModel, alert_id)
    assert row.status == "ACTIVE"
    assert row.acknowledged_by is None
    assert row.resolved_by is None


# ---------------------------------------------------------------------------
# Route-layer integration (direct handler invocation)
# ---------------------------------------------------------------------------
# TestClient-based round-trips are blocked by #1435 (admin settings require
# admin_master_key at import time). We invoke the handler callables directly
# with a real session — identical to how FastAPI would call them — to assert
# defense-in-depth: even when the route layer's ``verify_path_tenant_matches``
# dependency has been bypassed (e.g. sysadmin mode, or a future refactor that
# drops the dep), the handler still returns 404 for cross-tenant ids because
# the service layer filter rejects them.


def _alert_action_request(notes: str | None = None):
    """Build an AlertActionRequest. The body only carries ``notes`` —
    actor is derived from ``current_user`` per #1384."""
    from services.admin.app.compliance_routes import AlertActionRequest

    return AlertActionRequest(notes=notes)


def _fake_user():
    from types import SimpleNamespace

    return SimpleNamespace(id=uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"))


@pytest.mark.security
def test_route_get_alert_returns_404_for_cross_tenant(session):
    """Route-level: GET with tenant_B's id but tenant_A's alert -> 404."""
    from fastapi import HTTPException

    from services.admin.app.compliance_routes import get_alert as route_get_alert

    alert_id = _make_alert(session, TENANT_A)

    with pytest.raises(HTTPException) as exc:
        route_get_alert(
            tenant_id=str(TENANT_B),
            alert_id=str(alert_id),
            session=session,
        )
    assert exc.value.status_code == 404
    assert "not found" in exc.value.detail.lower()


@pytest.mark.security
def test_route_acknowledge_alert_returns_404_for_cross_tenant(session):
    """Route-level: acknowledge with wrong tenant_id -> 404, no state change."""
    from fastapi import HTTPException

    from services.admin.app.compliance_models import ComplianceAlertModel
    from services.admin.app.compliance_routes import (
        acknowledge_alert as route_acknowledge_alert,
    )

    alert_id = _make_alert(session, TENANT_A)

    with pytest.raises(HTTPException) as exc:
        route_acknowledge_alert(
            tenant_id=str(TENANT_B),
            alert_id=str(alert_id),
            request=_alert_action_request(),
            current_user=_fake_user(),
            session=session,
        )
    assert exc.value.status_code == 404

    session.expire_all()
    row = session.get(ComplianceAlertModel, alert_id)
    assert row.status == "ACTIVE"
    assert row.acknowledged_by is None


@pytest.mark.security
def test_route_resolve_alert_returns_404_for_cross_tenant(session):
    """Route-level: resolve with wrong tenant_id -> 404, no state change."""
    from fastapi import HTTPException

    from services.admin.app.compliance_models import ComplianceAlertModel
    from services.admin.app.compliance_routes import (
        resolve_alert as route_resolve_alert,
    )

    alert_id = _make_alert(session, TENANT_A)

    with pytest.raises(HTTPException) as exc:
        route_resolve_alert(
            tenant_id=str(TENANT_B),
            alert_id=str(alert_id),
            request=_alert_action_request(notes="hostile takeover"),
            current_user=_fake_user(),
            session=session,
        )
    assert exc.value.status_code == 404

    session.expire_all()
    row = session.get(ComplianceAlertModel, alert_id)
    assert row.status == "ACTIVE"
    assert row.resolved_by is None
    assert row.resolution_notes is None
