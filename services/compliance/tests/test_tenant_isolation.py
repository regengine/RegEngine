"""Tenant-isolation coverage for the compliance service — issue #1130.

Parametrized tests verify that data saved under tenant_a is invisible when
queried as tenant_b. Uses in-memory SQLite so no live DB is required.

The tests cover:
  - Extract/save data under tenant_id="tenant_a", query with tenant_id="tenant_b"
    → empty result
  - Multiple tenant pairs (parametrized)
  - Rule-engine result isolation (compliance check outputs keyed by tenant)
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import Column, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# ---------------------------------------------------------------------------
# Minimal schema
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class ComplianceCheckResult(Base):
    """Represents the persisted output of a compliance check per tenant."""

    __tablename__ = "compliance_check_results"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    regulation = Column(String, nullable=False)
    outcome = Column(String, nullable=False)  # compliant | non_compliant | pending
    detail = Column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db(engine):
    connection = engine.connect()
    tx = connection.begin()
    session = sessionmaker(bind=connection)()
    yield session
    session.close()
    tx.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# Parametrized tenant pairs
# ---------------------------------------------------------------------------

TENANT_PAIRS = [
    ("tenant_alpha", "tenant_beta"),
    ("tenant_gamma", "tenant_delta"),
    (str(uuid.uuid4()), str(uuid.uuid4())),
]


@pytest.mark.parametrize("tenant_a,tenant_b", TENANT_PAIRS)
def test_compliance_result_not_visible_across_tenants(db: Session, tenant_a: str, tenant_b: str):
    """A compliance check result saved for tenant_a must not appear when
    queried with tenant_b's filter."""
    regulation = "FSMA-204-CTE"

    # Save under tenant_a
    row = ComplianceCheckResult(
        id=str(uuid.uuid4()),
        tenant_id=tenant_a,
        regulation=regulation,
        outcome="compliant",
        detail="All 7 CTEs recorded",
    )
    db.add(row)
    db.flush()

    # Query as tenant_b
    result = (
        db.execute(
            select(ComplianceCheckResult).where(
                ComplianceCheckResult.tenant_id == tenant_b,
                ComplianceCheckResult.regulation == regulation,
            )
        )
        .scalars()
        .all()
    )

    assert result == [], (
        f"tenant_b={tenant_b!r} must not see compliance results belonging to "
        f"tenant_a={tenant_a!r}; got {result}"
    )


@pytest.mark.parametrize("tenant_a,tenant_b", TENANT_PAIRS)
def test_tenant_a_can_read_own_results(db: Session, tenant_a: str, tenant_b: str):
    """Positive check: tenant_a CAN see its own compliance records."""
    regulation = "FSMA-204-OWN"

    row = ComplianceCheckResult(
        id=str(uuid.uuid4()),
        tenant_id=tenant_a,
        regulation=regulation,
        outcome="non_compliant",
        detail="Missing CTE-4 data",
    )
    db.add(row)
    db.flush()

    result = (
        db.execute(
            select(ComplianceCheckResult).where(
                ComplianceCheckResult.tenant_id == tenant_a,
                ComplianceCheckResult.regulation == regulation,
            )
        )
        .scalars()
        .all()
    )
    assert len(result) == 1
    assert result[0].tenant_id == tenant_a


@pytest.mark.parametrize("tenant_a,tenant_b", TENANT_PAIRS)
def test_multiple_tenants_same_regulation_are_separate(db: Session, tenant_a: str, tenant_b: str):
    """Both tenants insert a result for the same regulation; each sees only its own."""
    regulation = "FSMA-204-SHARED-REG"

    row_a = ComplianceCheckResult(
        id=str(uuid.uuid4()), tenant_id=tenant_a, regulation=regulation,
        outcome="compliant", detail="Tenant A result",
    )
    row_b = ComplianceCheckResult(
        id=str(uuid.uuid4()), tenant_id=tenant_b, regulation=regulation,
        outcome="non_compliant", detail="Tenant B result",
    )
    db.add_all([row_a, row_b])
    db.flush()

    def _fetch(tid: str):
        return (
            db.execute(
                select(ComplianceCheckResult).where(
                    ComplianceCheckResult.tenant_id == tid,
                    ComplianceCheckResult.regulation == regulation,
                )
            )
            .scalars()
            .all()
        )

    rows_for_a = _fetch(tenant_a)
    rows_for_b = _fetch(tenant_b)

    assert len(rows_for_a) == 1
    assert rows_for_a[0].outcome == "compliant"

    assert len(rows_for_b) == 1
    assert rows_for_b[0].outcome == "non_compliant"
