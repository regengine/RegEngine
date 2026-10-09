"""Regression tests: alert state transitions must guard terminal states
and leave an audit entry.

Finding: ``acknowledge_alert`` / ``resolve_alert`` in
``ComplianceServiceSync`` accepted every transition, so a RESOLVED alert
could be moved back to ACKNOWLEDGED (reversing a terminal state), and no
row in ``compliance_status_log`` recorded the change.

These tests lock in the fixed behavior:
- transitions out of RESOLVED / EXPIRED are rejected (row untouched),
- repeated acknowledge / resolve calls are idempotent (no overwrite),
- every real transition appends one ``ComplianceStatusLogModel`` entry
  naming the previous status, the new status, and the actor.
"""

from __future__ import annotations

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
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

TENANT = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.fixture
def session() -> Session:
    from services.admin.app.compliance_models import (
        ComplianceAlertModel,
        ComplianceStatusLogModel,
        TenantComplianceStatusModel,
    )

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ComplianceAlertModel.__table__.create(engine, checkfirst=True)
    TenantComplianceStatusModel.__table__.create(engine, checkfirst=True)
    ComplianceStatusLogModel.__table__.create(engine, checkfirst=True)

    SessionLocal = sessionmaker(bind=engine)
    sess = SessionLocal()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


def _make_alert(session: Session, status: str = "ACTIVE") -> uuid.UUID:
    from services.admin.app.compliance_models import ComplianceAlertModel

    now = datetime.now(timezone.utc)
    alert = ComplianceAlertModel(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        source_type="MANUAL",
        source_id=f"test-{uuid.uuid4()}",
        title="Test alert",
        summary="For alert-transition regression tests.",
        severity="HIGH",
        countdown_start=now,
        countdown_end=now + timedelta(hours=24),
        countdown_hours=24,
        required_actions=[],
        status=status,
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert.id


def _log_entries(session: Session):
    from services.admin.app.compliance_models import ComplianceStatusLogModel

    return session.execute(select(ComplianceStatusLogModel)).scalars().all()


def test_resolved_alert_cannot_be_reopened_by_acknowledge(session):
    """A RESOLVED alert is terminal: acknowledge must leave it resolved."""
    from services.admin.app.compliance_models import ComplianceAlertModel
    from services.admin.app.compliance_service_sync import ComplianceServiceSync

    service = ComplianceServiceSync(session)
    alert_id = _make_alert(session)
    service.resolve_alert(alert_id, TENANT, user_id="owner", notes="done")

    out = service.acknowledge_alert(alert_id, TENANT, user_id="owner")

    assert out is not None
    assert out.status == "RESOLVED"
    session.expire_all()
    row = session.get(ComplianceAlertModel, alert_id)
    assert row.status == "RESOLVED"
    assert row.resolved_by == "owner"


def test_resolve_is_idempotent_and_keeps_first_resolution(session):
    """Resolving twice must not overwrite the original actor and notes."""
    from services.admin.app.compliance_models import ComplianceAlertModel
    from services.admin.app.compliance_service_sync import ComplianceServiceSync

    service = ComplianceServiceSync(session)
    alert_id = _make_alert(session)
    service.resolve_alert(alert_id, TENANT, user_id="owner", notes="first")

    out = service.resolve_alert(alert_id, TENANT, user_id="intruder", notes="second")

    assert out is not None
    assert out.status == "RESOLVED"
    session.expire_all()
    row = session.get(ComplianceAlertModel, alert_id)
    assert row.resolved_by == "owner"
    assert row.resolution_notes == "first"


def test_expired_alert_cannot_transition(session):
    """An EXPIRED alert is terminal: neither acknowledge nor resolve moves it."""
    from services.admin.app.compliance_models import ComplianceAlertModel
    from services.admin.app.compliance_service_sync import ComplianceServiceSync

    service = ComplianceServiceSync(session)
    alert_id = _make_alert(session, status="EXPIRED")

    assert service.acknowledge_alert(alert_id, TENANT, user_id="owner").status == "EXPIRED"
    assert service.resolve_alert(alert_id, TENANT, user_id="owner").status == "EXPIRED"
    session.expire_all()
    row = session.get(ComplianceAlertModel, alert_id)
    assert row.status == "EXPIRED"
    assert row.acknowledged_by is None
    assert row.resolved_by is None


def test_acknowledge_writes_audit_entry(session):
    """ACTIVE -> ACKNOWLEDGED appends one log row naming actor and states."""
    from services.admin.app.compliance_service_sync import ComplianceServiceSync

    service = ComplianceServiceSync(session)
    alert_id = _make_alert(session)

    service.acknowledge_alert(alert_id, TENANT, user_id="owner")

    entries = _log_entries(session)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.trigger_alert_id == alert_id
    assert entry.tenant_id == TENANT
    assert entry.previous_status == "ACTIVE"
    assert entry.new_status == "ACKNOWLEDGED"
    assert "owner" in (entry.trigger_description or "")


def test_resolve_writes_audit_entry(session):
    """ACKNOWLEDGED -> RESOLVED appends one log row naming actor and states."""
    from services.admin.app.compliance_service_sync import ComplianceServiceSync

    service = ComplianceServiceSync(session)
    alert_id = _make_alert(session)
    service.acknowledge_alert(alert_id, TENANT, user_id="owner")

    service.resolve_alert(alert_id, TENANT, user_id="owner", notes="fixed")

    entries = _log_entries(session)
    assert len(entries) == 2
    entry = entries[-1]
    assert entry.trigger_alert_id == alert_id
    assert entry.previous_status == "ACKNOWLEDGED"
    assert entry.new_status == "RESOLVED"
    assert "owner" in (entry.trigger_description or "")


def test_rejected_transition_writes_no_audit_entry(session):
    """A guarded (rejected) transition must not append a log row."""
    from services.admin.app.compliance_service_sync import ComplianceServiceSync

    service = ComplianceServiceSync(session)
    alert_id = _make_alert(session)
    service.resolve_alert(alert_id, TENANT, user_id="owner", notes="done")
    assert len(_log_entries(session)) == 1

    service.acknowledge_alert(alert_id, TENANT, user_id="owner")
    service.resolve_alert(alert_id, TENANT, user_id="owner", notes="again")

    assert len(_log_entries(session)) == 1
