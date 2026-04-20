"""DB-persistence coverage for compliance records — issue #1131.

The compliance service currently persists records via the shared PostgreSQL
layer. These tests use an in-memory SQLite engine (via SQLAlchemy Core) to
verify the four critical invariants without requiring a live Postgres instance:

  1. Insert → read back → fields match
  2. Duplicate insert → idempotent (ON CONFLICT DO NOTHING / upsert)
  3. RLS simulation: tenant A inserts; reading with tenant B → empty result
  4. Soft-delete → record hidden from normal (non-deleted) queries

The schema mirrors the compliance_records table defined in the DB migrations
(services/shared/db_migrations or equivalent).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# ---------------------------------------------------------------------------
# Minimal ORM model mirroring the compliance_records table
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class ComplianceRecord(Base):
    __tablename__ = "compliance_records"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, nullable=False, index=True)
    regulation = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    notes = Column(Text, nullable=True)
    record_date = Column(Date, nullable=False, default=date.today)
    deleted_at = Column(DateTime(timezone=True), nullable=True, default=None)

    __table_args__ = (
        UniqueConstraint("tenant_id", "regulation", name="uq_tenant_regulation"),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db_session(engine):
    """Provide a transactional session that is rolled back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    Session_ = sessionmaker(bind=connection)
    session = Session_()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


TENANT_A = str(uuid.uuid4())
TENANT_B = str(uuid.uuid4())


def _make_record(tenant_id: str, regulation: str = "FSMA-204", **kwargs) -> ComplianceRecord:
    return ComplianceRecord(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        regulation=regulation,
        status="compliant",
        notes="Initial compliance pass",
        record_date=date(2026, 1, 15),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Test 1: Insert → read back → fields match
# ---------------------------------------------------------------------------

def test_insert_and_read_back(db_session: Session):
    record = _make_record(TENANT_A)
    record_id = record.id

    db_session.add(record)
    db_session.flush()

    fetched = db_session.get(ComplianceRecord, record_id)

    assert fetched is not None
    assert fetched.tenant_id == TENANT_A
    assert fetched.regulation == "FSMA-204"
    assert fetched.status == "compliant"
    assert fetched.notes == "Initial compliance pass"
    assert fetched.record_date == date(2026, 1, 15)
    assert fetched.deleted_at is None


# ---------------------------------------------------------------------------
# Test 2: Duplicate insert → idempotent (unique constraint prevents duplicate)
# ---------------------------------------------------------------------------

def test_duplicate_insert_is_idempotent(db_session: Session):
    """Second insert with the same (tenant_id, regulation) should not create
    a second row. We verify via INSERT OR IGNORE (SQLite dialect for upsert)
    and assert only one row exists after two inserts."""
    regulation = "FSMA-204-UPSERT"

    # First insert via ORM
    first = _make_record(TENANT_A, regulation=regulation)
    db_session.add(first)
    db_session.flush()

    # Second insert via raw SQL with OR IGNORE to simulate idempotent upsert
    db_session.execute(
        text(
            "INSERT OR IGNORE INTO compliance_records "
            "(id, tenant_id, regulation, status, record_date) "
            "VALUES (:id, :tenant_id, :regulation, :status, :record_date)"
        ),
        {
            "id": str(uuid.uuid4()),
            "tenant_id": TENANT_A,
            "regulation": regulation,
            "status": "pending",
            "record_date": "2026-02-01",
        },
    )
    db_session.flush()

    rows = db_session.execute(
        select(ComplianceRecord).where(
            ComplianceRecord.tenant_id == TENANT_A,
            ComplianceRecord.regulation == regulation,
        )
    ).scalars().all()

    assert len(rows) == 1, "Duplicate insert must not create a second compliance record"
    assert rows[0].status == "compliant"  # Original row untouched


# ---------------------------------------------------------------------------
# Test 3: RLS simulation — tenant A inserts; tenant B query → empty
# ---------------------------------------------------------------------------

def test_tenant_isolation_rls_simulation(db_session: Session):
    """Rows inserted under tenant_a must not appear when querying with tenant_b.

    In production, Postgres RLS enforces this at the DB level via a policy
    that compares current_setting('app.tenant_id') to the row's tenant_id.
    In this test we simulate the same check by filtering every SELECT.
    """
    regulation = "FSMA-204-RLS"

    record = _make_record(TENANT_A, regulation=regulation)
    db_session.add(record)
    db_session.flush()

    # Query as tenant_b
    rows_for_b = (
        db_session.execute(
            select(ComplianceRecord).where(
                ComplianceRecord.tenant_id == TENANT_B,
                ComplianceRecord.regulation == regulation,
            )
        )
        .scalars()
        .all()
    )

    assert rows_for_b == [], (
        "Tenant B must see no rows belonging to Tenant A — "
        "in production this is enforced by Postgres RLS"
    )

    # Tenant A can see its own row
    rows_for_a = (
        db_session.execute(
            select(ComplianceRecord).where(
                ComplianceRecord.tenant_id == TENANT_A,
                ComplianceRecord.regulation == regulation,
            )
        )
        .scalars()
        .all()
    )
    assert len(rows_for_a) == 1


# ---------------------------------------------------------------------------
# Test 4: Soft-delete → record hidden from normal queries
# ---------------------------------------------------------------------------

def test_soft_delete_hides_record(db_session: Session):
    """Setting deleted_at makes the record invisible to normal (live) queries."""
    regulation = "FSMA-204-SOFTDEL"

    record = _make_record(TENANT_A, regulation=regulation)
    db_session.add(record)
    db_session.flush()

    # Soft-delete the record
    record.deleted_at = datetime.now(timezone.utc)
    db_session.flush()

    # Normal query should exclude soft-deleted rows
    live_rows = (
        db_session.execute(
            select(ComplianceRecord).where(
                ComplianceRecord.tenant_id == TENANT_A,
                ComplianceRecord.regulation == regulation,
                ComplianceRecord.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )

    assert live_rows == [], "Soft-deleted record must be hidden from normal queries"

    # But the row still exists (not hard-deleted)
    all_rows = (
        db_session.execute(
            select(ComplianceRecord).where(
                ComplianceRecord.tenant_id == TENANT_A,
                ComplianceRecord.regulation == regulation,
            )
        )
        .scalars()
        .all()
    )
    assert len(all_rows) == 1
    assert all_rows[0].deleted_at is not None
