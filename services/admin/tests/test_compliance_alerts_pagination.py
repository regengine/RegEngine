"""Regression tests: compliance alert listing must support pagination.

``GET /v1/compliance/alerts/{tenant_id}`` accepts ``limit`` and ``offset``
query params and passes both to ``ComplianceServiceSync.get_alerts``. The
service accepted only ``limit``, so every list call raised ``TypeError``
(``got an unexpected keyword argument 'offset'``), which the route maps to
HTTP 500. The endpoint was completely unusable.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

_SERVICE_DIR = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SERVICE_DIR.parent
for _p in (_SERVICE_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

TENANT = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.fixture
def session() -> Session:
    from services.admin.app.compliance_models import (  # noqa: F401
        ComplianceAlertModel,
        TenantComplianceStatusModel,
    )

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ComplianceAlertModel.__table__.create(engine, checkfirst=True)
    TenantComplianceStatusModel.__table__.create(engine, checkfirst=True)
    SessionLocal = sessionmaker(bind=engine)
    sess = SessionLocal()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


def _make_alert(session: Session, title: str, created_minute: int = 0) -> None:
    from services.admin.app.compliance_models import ComplianceAlertModel

    # Explicit timestamps: SQLite's CURRENT_TIMESTAMP has one-second
    # granularity, so same-second inserts tie and page order is undefined.
    now = datetime.now(timezone.utc) + timedelta(minutes=created_minute)
    session.add(
        ComplianceAlertModel(
            id=uuid.uuid4(),
            tenant_id=TENANT,
            source_type="MANUAL",
            source_id=f"test-source-{title}",
            title=title,
            summary="pagination regression",
            severity="MEDIUM",
            countdown_start=now,
            countdown_end=now + timedelta(hours=24),
            countdown_hours=24,
            required_actions=[],
            status="ACTIVE",
            created_at=now,
        )
    )
    session.commit()


def test_get_alerts_accepts_offset_kwarg(session):
    """The route always passes ``offset``; the service must accept it."""
    from services.admin.app.compliance_service_sync import ComplianceServiceSync

    _make_alert(session, "alert one")
    service = ComplianceServiceSync(session)

    alerts = service.get_alerts(TENANT, limit=10, offset=0)

    assert len(alerts) == 1


def test_get_alerts_paginates_with_offset(session):
    """Page two skips page one's rows (newest first)."""
    from services.admin.app.compliance_service_sync import ComplianceServiceSync

    for minute, title in enumerate(("alert one", "alert two", "alert three")):
        _make_alert(session, title, created_minute=minute)
    service = ComplianceServiceSync(session)

    page_one = service.get_alerts(TENANT, limit=2, offset=0)
    page_two = service.get_alerts(TENANT, limit=2, offset=2)

    assert len(page_one) == 2
    assert len(page_two) == 1
    assert {a.title for a in page_two} == {"alert one"}
    assert {a.title for a in page_one} == {"alert two", "alert three"}
