"""Regression tests: GET /v1/compliance/alerts/{tenant_id} pagination.

The list endpoint passes ``offset`` to ``ComplianceServiceSync.get_alerts``,
which did not accept it, so every call raised TypeError and the route
returned 500. The route-level tests below call the handler directly with
a real session (TestClient round-trips are blocked by #1435) against an
isolated in-memory SQLite database and assert correct limit/offset
pagination with tenant scoping intact.

SQLite note: production Postgres returns tz-aware datetimes, while SQLite
re-reads DateTime(timezone=True) columns as naive values. A naive
``countdown_end`` would make ``ComplianceAlertModel.to_dict()`` raise
(naive minus aware) inside the route handler. The ``session`` fixture
attaches a small test-only ``loaded_as_persistent`` listener that re-tags
naive timestamps as UTC on rows read back in that session. The query,
ordering, pagination, tenant filter, and route handler under test are the
real production code paths.
"""

from __future__ import annotations

# Admin-test sys.path bootstrap: mirrors test_compliance_routes_idor.py so
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
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

BASE_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

# Fixed ids for the equal-timestamp tie tests. Canonical UUID strings sort
# lexicographically (SQLite CHAR(36) ORDER BY) in the same order as their
# integer values (Python sorted()), so the expected order is unambiguous.
TIE_IDS = (
    uuid.UUID("11111111-1111-1111-1111-111111111111"),
    uuid.UUID("22222222-2222-2222-2222-222222222222"),
    uuid.UUID("33333333-3333-3333-3333-333333333333"),
)

_TZ_ATTRS = (
    "countdown_start",
    "countdown_end",
    "created_at",
    "acknowledged_at",
    "resolved_at",
)


@pytest.fixture
def session() -> Session:
    """Isolated in-memory SQLite session with compliance tables created.

    Each test gets a run-owned engine; teardown detaches the listener and
    then closes only this session and disposes only this engine, so cleanup
    can never touch a shared or pre-existing database. A session-scoped
    load listener re-tags naive SQLite timestamps as UTC to match
    production Postgres behavior (see module docstring).
    """
    from services.admin.app.compliance_models import (  # noqa: F401: registers tables
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

    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    sess = SessionLocal()

    def _retag_naive_as_utc(session_: Session, instance: object) -> None:
        if not isinstance(instance, ComplianceAlertModel):
            return
        for attr in _TZ_ATTRS:
            value = getattr(instance, attr, None)
            if isinstance(value, datetime) and value.tzinfo is None:
                setattr(instance, attr, value.replace(tzinfo=timezone.utc))

    event.listen(sess, "loaded_as_persistent", _retag_naive_as_utc)
    try:
        yield sess
    finally:
        event.remove(sess, "loaded_as_persistent", _retag_naive_as_utc)
        sess.close()
        engine.dispose()


def _make_alert(
    session: Session,
    tenant_id: uuid.UUID,
    slug: str,
    created_at: datetime,
    status: str = "ACTIVE",
    alert_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert an alert with explicit timestamps (and optional id)."""
    from services.admin.app.compliance_models import ComplianceAlertModel

    alert = ComplianceAlertModel(
        id=alert_id or uuid.uuid4(),
        tenant_id=tenant_id,
        source_type="MANUAL",
        source_id=f"source-{slug}",
        title=f"title-{slug}",
        summary="Pagination regression seed.",
        severity="HIGH",
        countdown_start=created_at,
        countdown_end=created_at + timedelta(hours=24),
        countdown_hours=24,
        created_at=created_at,
        required_actions=[],
        status=status,
    )
    session.add(alert)
    session.flush()
    return alert.id


def _seed(session: Session) -> None:
    """Five tenant-A alerts (alert-0 oldest .. alert-4 newest, alert-0
    acknowledged), plus two tenant-B alerts that must never leak."""
    for i in range(5):
        _make_alert(
            session,
            TENANT_A,
            f"alert-{i}",
            BASE_TIME + timedelta(minutes=i),
            status="ACKNOWLEDGED" if i == 0 else "ACTIVE",
        )
    for i in range(2):
        _make_alert(session, TENANT_B, f"other-{i}", BASE_TIME + timedelta(minutes=i))
    session.commit()


def _seed_ties(session: Session) -> None:
    """Three tenant-A alerts sharing one created_at, inserted out of id
    order so the test proves ordering comes from the id tiebreaker."""
    for slug, alert_id in (
        ("tie-c", TIE_IDS[2]),
        ("tie-a", TIE_IDS[0]),
        ("tie-b", TIE_IDS[1]),
    ):
        _make_alert(session, TENANT_A, slug, BASE_TIME, alert_id=alert_id)
    session.commit()


def _titles(responses) -> list:
    return [r.title for r in responses]


def test_route_list_alerts_first_page(session: Session):
    """Route-level: limit=2 offset=0 returns the two newest tenant alerts."""
    from services.admin.app.compliance_routes import list_alerts as route_list_alerts

    _seed(session)
    out = route_list_alerts(
        tenant_id=str(TENANT_A),
        status=None,
        limit=2,
        offset=0,
        session=session,
    )
    assert _titles(out) == ["title-alert-4", "title-alert-3"]
    assert {r.tenant_id for r in out} == {str(TENANT_A)}


def test_route_list_alerts_second_page(session: Session):
    """Route-level: limit=2 offset=2 skips the first page (the offset
    regression: pre-fix this call raised TypeError in the service and the
    route returned 500)."""
    from services.admin.app.compliance_routes import list_alerts as route_list_alerts

    _seed(session)
    out = route_list_alerts(
        tenant_id=str(TENANT_A),
        status=None,
        limit=2,
        offset=2,
        session=session,
    )
    assert _titles(out) == ["title-alert-2", "title-alert-1"]


def test_route_list_alerts_offset_beyond_end_returns_empty(session: Session):
    """Route-level: an offset past the last row returns []."""
    from services.admin.app.compliance_routes import list_alerts as route_list_alerts

    _seed(session)
    out = route_list_alerts(
        tenant_id=str(TENANT_A),
        status=None,
        limit=2,
        offset=10,
        session=session,
    )
    assert out == []


def test_route_list_alerts_excludes_other_tenant(session: Session):
    """Route-level: tenant scoping intact, other tenant rows never leak."""
    from services.admin.app.compliance_routes import list_alerts as route_list_alerts

    _seed(session)
    out = route_list_alerts(
        tenant_id=str(TENANT_A),
        status=None,
        limit=100,
        offset=0,
        session=session,
    )
    assert len(out) == 5
    assert {r.tenant_id for r in out} == {str(TENANT_A)}


def test_route_list_alerts_status_filter_with_offset(session: Session):
    """Route-level: status filter composes with pagination."""
    from services.admin.app.compliance_routes import list_alerts as route_list_alerts

    _seed(session)
    out = route_list_alerts(
        tenant_id=str(TENANT_A),
        status="ACKNOWLEDGED",
        limit=100,
        offset=0,
        session=session,
    )
    assert _titles(out) == ["title-alert-0"]


def test_service_get_alerts_pagination_is_stable(session: Session):
    """Service-level: repeated pages are deterministic and disjoint."""
    from services.admin.app.compliance_service_sync import ComplianceServiceSync

    _seed(session)
    service = ComplianceServiceSync(session)
    page1 = service.get_alerts(TENANT_A, limit=2, offset=0)
    page1_again = service.get_alerts(TENANT_A, limit=2, offset=0)
    page2 = service.get_alerts(TENANT_A, limit=2, offset=2)

    assert [a.id for a in page1] == [a.id for a in page1_again]
    assert {a.id for a in page1}.isdisjoint({a.id for a in page2})


def test_service_get_alerts_tie_on_created_at_orders_by_id(session: Session):
    """Service-level: equal created_at rows sort by id ascending, and pages
    over the tie are stable and disjoint."""
    from services.admin.app.compliance_service_sync import ComplianceServiceSync

    _seed_ties(session)
    service = ComplianceServiceSync(session)

    all_rows = service.get_alerts(TENANT_A, limit=10, offset=0)
    assert [a.id for a in all_rows] == sorted(TIE_IDS)

    page1 = service.get_alerts(TENANT_A, limit=2, offset=0)
    page2 = service.get_alerts(TENANT_A, limit=2, offset=2)
    assert [a.id for a in page1] == sorted(TIE_IDS)[:2]
    assert [a.id for a in page2] == sorted(TIE_IDS)[2:]
    assert {a.id for a in page1}.isdisjoint({a.id for a in page2})


def test_route_list_alerts_tie_on_created_at_paginates_by_id(session: Session):
    """Route-level: the real handler returns tie rows in id order across pages."""
    from services.admin.app.compliance_routes import list_alerts as route_list_alerts

    _seed_ties(session)
    page1 = route_list_alerts(
        tenant_id=str(TENANT_A),
        status=None,
        limit=2,
        offset=0,
        session=session,
    )
    page2 = route_list_alerts(
        tenant_id=str(TENANT_A),
        status=None,
        limit=2,
        offset=2,
        session=session,
    )
    assert [r.id for r in page1] == [str(i) for i in sorted(TIE_IDS)[:2]]
    assert [r.id for r in page2] == [str(i) for i in sorted(TIE_IDS)[2:]]
    assert _titles(page1) == ["title-tie-a", "title-tie-b"]
    assert _titles(page2) == ["title-tie-c"]
