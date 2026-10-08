"""Regression tests: GET /v1/compliance/alerts/{tenant_id} pagination.

The list endpoint passes ``offset`` to ``ComplianceServiceSync.get_alerts``,
which did not accept it, so every call raised TypeError and the route
returned 500. The route-level tests below call the handler directly with
a real session (TestClient round-trips are blocked by #1435) against a
throwaway local Postgres database and assert correct limit/offset
pagination with tenant scoping intact. Postgres (not SQLite) is used
because ``ComplianceAlertModel.to_dict()`` needs tz-aware datetimes and
SQLite returns naive ones on re-read, while production Postgres returns
tz-aware values.
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
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

BASE_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

DB_NAME = "fleet_compliance_alerts_offset"
PG_URL = f"postgresql+psycopg://sellers@/{DB_NAME}?host=/tmp"


def _ensure_pg_db() -> None:
    """Create the throwaway database if it is missing."""
    import psycopg

    conn = psycopg.connect(host="/tmp", dbname="postgres", connect_timeout=3, autocommit=True)
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{DB_NAME}"')
    conn.close()


def _ensure_pg_tables(engine) -> None:
    from services.admin.app.compliance_models import (  # noqa: F401: registers tables
        ComplianceAlertModel,
        TenantComplianceStatusModel,
    )

    ComplianceAlertModel.__table__.create(engine, checkfirst=True)
    TenantComplianceStatusModel.__table__.create(engine, checkfirst=True)


@pytest.fixture(scope="module", autouse=True)
def _drop_pg_db_after_module():
    """Drop the throwaway database when the module run is done."""
    yield
    try:
        import psycopg

        conn = psycopg.connect(host="/tmp", dbname="postgres", connect_timeout=3, autocommit=True)
    except Exception:
        return
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (DB_NAME,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{DB_NAME}"')
    conn.close()


@pytest.fixture
def pg_session() -> Session:
    """Function-scoped session on the throwaway Postgres DB, emptied first."""
    from services.admin.app.compliance_models import (
        ComplianceAlertModel,
        TenantComplianceStatusModel,
    )

    try:
        _ensure_pg_db()
    except Exception as exc:
        pytest.skip(f"local postgres unavailable: {exc}")
    engine = create_engine(PG_URL)
    _ensure_pg_tables(engine)
    SessionLocal = sessionmaker(bind=engine)
    sess = SessionLocal()
    sess.execute(delete(ComplianceAlertModel))
    sess.execute(delete(TenantComplianceStatusModel))
    sess.commit()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


@pytest.fixture
def session() -> Session:
    """Isolated in-memory SQLite session for the service-level test
    (no ``to_dict`` involved, so naive datetimes are harmless)."""
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
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


def _make_alert(
    session: Session,
    tenant_id: uuid.UUID,
    slug: str,
    created_at: datetime,
    status: str = "ACTIVE",
) -> uuid.UUID:
    """Insert an alert with explicit timestamps."""
    from services.admin.app.compliance_models import ComplianceAlertModel

    alert = ComplianceAlertModel(
        id=uuid.uuid4(),
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


def _titles(responses) -> list:
    return [r.title for r in responses]


def test_route_list_alerts_first_page(pg_session: Session):
    """Route-level: limit=2 offset=0 returns the two newest tenant alerts."""
    from services.admin.app.compliance_routes import list_alerts as route_list_alerts

    _seed(pg_session)
    out = route_list_alerts(
        tenant_id=str(TENANT_A),
        status=None,
        limit=2,
        offset=0,
        session=pg_session,
    )
    assert _titles(out) == ["title-alert-4", "title-alert-3"]
    assert {r.tenant_id for r in out} == {str(TENANT_A)}


def test_route_list_alerts_second_page(pg_session: Session):
    """Route-level: limit=2 offset=2 skips the first page (the offset
    regression: pre-fix this call raised TypeError in the service and the
    route returned 500)."""
    from services.admin.app.compliance_routes import list_alerts as route_list_alerts

    _seed(pg_session)
    out = route_list_alerts(
        tenant_id=str(TENANT_A),
        status=None,
        limit=2,
        offset=2,
        session=pg_session,
    )
    assert _titles(out) == ["title-alert-2", "title-alert-1"]


def test_route_list_alerts_offset_beyond_end_returns_empty(pg_session: Session):
    """Route-level: an offset past the last row returns []."""
    from services.admin.app.compliance_routes import list_alerts as route_list_alerts

    _seed(pg_session)
    out = route_list_alerts(
        tenant_id=str(TENANT_A),
        status=None,
        limit=2,
        offset=10,
        session=pg_session,
    )
    assert out == []


def test_route_list_alerts_excludes_other_tenant(pg_session: Session):
    """Route-level: tenant scoping intact, other tenant rows never leak."""
    from services.admin.app.compliance_routes import list_alerts as route_list_alerts

    _seed(pg_session)
    out = route_list_alerts(
        tenant_id=str(TENANT_A),
        status=None,
        limit=100,
        offset=0,
        session=pg_session,
    )
    assert len(out) == 5
    assert {r.tenant_id for r in out} == {str(TENANT_A)}


def test_route_list_alerts_status_filter_with_offset(pg_session: Session):
    """Route-level: status filter composes with pagination."""
    from services.admin.app.compliance_routes import list_alerts as route_list_alerts

    _seed(pg_session)
    out = route_list_alerts(
        tenant_id=str(TENANT_A),
        status="ACKNOWLEDGED",
        limit=100,
        offset=0,
        session=pg_session,
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
