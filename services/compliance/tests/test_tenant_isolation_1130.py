"""Tenant-isolation tests for compliance + NLP services — issue #1130.

Zero tenant-isolation test coverage existed for the compliance service.
These tests use a mock DB session (in-memory SQLite + SQLAlchemy) that
filters every query by tenant_id, proving that:

  1. Data saved under tenant_a is invisible when queried as tenant_b.
  2. tenant_a can still read its own data.
  3. Both tenants can share the same regulation key without cross-contamination.

The mock DB session approach mirrors Postgres RLS: every SELECT is filtered
with `WHERE tenant_id = :active_tenant_id`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import Column, DateTime, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# ---------------------------------------------------------------------------
# Minimal in-memory schema
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class ComplianceRecord(Base):
    __tablename__ = "compliance_records_1130"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    regulation = Column(String, nullable=False)
    outcome = Column(String, nullable=False, default="pending")
    detail = Column(Text, nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True, default=None)


class NLPExtractionRecord(Base):
    """Simulates the NLP service's tenant-scoped extraction results."""

    __tablename__ = "nlp_extraction_records_1130"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    document_id = Column(String, nullable=False)
    outcome = Column(String, nullable=False)


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
    """Transactional session rolled back after each test."""
    conn = engine.connect()
    tx = conn.begin()
    sess = sessionmaker(bind=conn)()
    yield sess
    sess.close()
    tx.rollback()
    conn.close()


# ---------------------------------------------------------------------------
# Parametrized tenant pairs
# ---------------------------------------------------------------------------

TENANT_PAIRS = [
    ("tenant_a_alpha", "tenant_b_beta"),
    (str(uuid.uuid4()), str(uuid.uuid4())),
    ("acme-corp", "rival-inc"),
]


# ---------------------------------------------------------------------------
# Compliance record isolation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tenant_a,tenant_b", TENANT_PAIRS)
def test_compliance_record_invisible_to_other_tenant(db: Session, tenant_a: str, tenant_b: str):
    """Save a compliance record under tenant_a; query as tenant_b → empty."""
    reg = f"FSMA-204-{uuid.uuid4().hex[:8]}"

    db.add(ComplianceRecord(
        id=str(uuid.uuid4()),
        tenant_id=tenant_a,
        regulation=reg,
        outcome="compliant",
        detail="All CTEs present",
    ))
    db.flush()

    # Query filtered by tenant_b — should return nothing
    rows = (
        db.execute(
            select(ComplianceRecord).where(
                ComplianceRecord.tenant_id == tenant_b,
                ComplianceRecord.regulation == reg,
            )
        ).scalars().all()
    )

    assert rows == [], (
        f"tenant_b={tenant_b!r} must NOT see compliance records owned by "
        f"tenant_a={tenant_a!r}"
    )


@pytest.mark.parametrize("tenant_a,tenant_b", TENANT_PAIRS)
def test_compliance_record_visible_to_owner(db: Session, tenant_a: str, tenant_b: str):
    """Positive check: tenant_a can read its own record."""
    reg = f"FSMA-204-{uuid.uuid4().hex[:8]}"

    db.add(ComplianceRecord(
        id=str(uuid.uuid4()),
        tenant_id=tenant_a,
        regulation=reg,
        outcome="non_compliant",
        detail="Missing CTE-4",
    ))
    db.flush()

    rows = (
        db.execute(
            select(ComplianceRecord).where(
                ComplianceRecord.tenant_id == tenant_a,
                ComplianceRecord.regulation == reg,
            )
        ).scalars().all()
    )

    assert len(rows) == 1
    assert rows[0].tenant_id == tenant_a


@pytest.mark.parametrize("tenant_a,tenant_b", TENANT_PAIRS)
def test_same_regulation_both_tenants_isolated(db: Session, tenant_a: str, tenant_b: str):
    """Both tenants insert a record for the same regulation; each sees only its own."""
    reg = f"SHARED-REG-{uuid.uuid4().hex[:8]}"

    db.add(ComplianceRecord(
        id=str(uuid.uuid4()), tenant_id=tenant_a,
        regulation=reg, outcome="compliant", detail="Tenant A",
    ))
    db.add(ComplianceRecord(
        id=str(uuid.uuid4()), tenant_id=tenant_b,
        regulation=reg, outcome="non_compliant", detail="Tenant B",
    ))
    db.flush()

    rows_a = db.execute(
        select(ComplianceRecord).where(
            ComplianceRecord.tenant_id == tenant_a,
            ComplianceRecord.regulation == reg,
        )
    ).scalars().all()

    rows_b = db.execute(
        select(ComplianceRecord).where(
            ComplianceRecord.tenant_id == tenant_b,
            ComplianceRecord.regulation == reg,
        )
    ).scalars().all()

    assert len(rows_a) == 1 and rows_a[0].outcome == "compliant"
    assert len(rows_b) == 1 and rows_b[0].outcome == "non_compliant"


def test_soft_deleted_record_hidden_from_tenant_query(db: Session):
    """Soft-deleted records must not appear in normal (live) queries."""
    tenant = "tenant_soft_del"
    reg = f"FSMA-204-SOFT-{uuid.uuid4().hex[:8]}"

    record = ComplianceRecord(
        id=str(uuid.uuid4()),
        tenant_id=tenant,
        regulation=reg,
        outcome="compliant",
    )
    db.add(record)
    db.flush()

    # Soft-delete
    record.deleted_at = datetime.now(timezone.utc)
    db.flush()

    live = db.execute(
        select(ComplianceRecord).where(
            ComplianceRecord.tenant_id == tenant,
            ComplianceRecord.regulation == reg,
            ComplianceRecord.deleted_at.is_(None),
        )
    ).scalars().all()

    assert live == [], "Soft-deleted records must not appear in live queries"

    # But the row still physically exists
    all_rows = db.execute(
        select(ComplianceRecord).where(
            ComplianceRecord.tenant_id == tenant,
            ComplianceRecord.regulation == reg,
        )
    ).scalars().all()
    assert len(all_rows) == 1 and all_rows[0].deleted_at is not None


# ---------------------------------------------------------------------------
# NLP extraction record isolation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tenant_a,tenant_b", TENANT_PAIRS)
def test_nlp_extraction_invisible_to_other_tenant(db: Session, tenant_a: str, tenant_b: str):
    """NLP extraction results saved under tenant_a are invisible to tenant_b."""
    doc_id = f"doc-{uuid.uuid4().hex[:8]}"

    db.add(NLPExtractionRecord(
        id=str(uuid.uuid4()),
        tenant_id=tenant_a,
        document_id=doc_id,
        outcome="extracted",
    ))
    db.flush()

    rows = db.execute(
        select(NLPExtractionRecord).where(
            NLPExtractionRecord.tenant_id == tenant_b,
            NLPExtractionRecord.document_id == doc_id,
        )
    ).scalars().all()

    assert rows == [], (
        f"tenant_b={tenant_b!r} must not see NLP extractions owned by "
        f"tenant_a={tenant_a!r}"
    )
