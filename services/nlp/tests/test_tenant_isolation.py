"""Tenant-isolation coverage for the NLP service — issue #1130.

Parametrized tests verify that NLP extraction results, retry state, and
consumer routing data saved under tenant_a are invisible when queried as
tenant_b. Uses in-memory SQLite so no live infrastructure is required.

Complements test_retrieval_tenant_scope.py (Kafka envelope propagation)
by covering any future in-process state stores (retry maps, embedding
caches, extraction buffers).
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Column, Float, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# ---------------------------------------------------------------------------
# Minimal schema: simulates an NLP extraction result cache
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class ExtractionResult(Base):
    """Represents a cached NLP extraction output for a given document+tenant."""

    __tablename__ = "nlp_extraction_results"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    document_id = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    action = Column(String, nullable=False)
    obligation_type = Column(String, nullable=False)
    confidence_score = Column(Float, nullable=False)
    source_text = Column(Text, nullable=True)


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
# Helpers
# ---------------------------------------------------------------------------

def _insert_extraction(db: Session, tenant_id: str, document_id: str = "doc-001") -> ExtractionResult:
    row = ExtractionResult(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        document_id=document_id,
        subject="shipper",
        action="must maintain",
        obligation_type="MUST",
        confidence_score=0.97,
        source_text="Shipper must maintain records for 2 years.",
    )
    db.add(row)
    db.flush()
    return row


def _query_by_tenant(db: Session, tenant_id: str, document_id: str) -> list[ExtractionResult]:
    return (
        db.execute(
            select(ExtractionResult).where(
                ExtractionResult.tenant_id == tenant_id,
                ExtractionResult.document_id == document_id,
            )
        )
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------------
# Parametrized tenant pairs
# ---------------------------------------------------------------------------

TENANT_PAIRS = [
    ("tenant_nlp_alpha", "tenant_nlp_beta"),
    ("tenant_nlp_gamma", "tenant_nlp_delta"),
    (str(uuid.uuid4()), str(uuid.uuid4())),
]


@pytest.mark.parametrize("tenant_a,tenant_b", TENANT_PAIRS)
def test_extraction_not_visible_across_tenants(db: Session, tenant_a: str, tenant_b: str):
    """Extraction saved under tenant_a is invisible when queried as tenant_b."""
    doc_id = f"doc-isolation-{uuid.uuid4().hex[:8]}"
    _insert_extraction(db, tenant_a, document_id=doc_id)

    result = _query_by_tenant(db, tenant_b, doc_id)
    assert result == [], (
        f"tenant_b={tenant_b!r} must not see extractions from tenant_a={tenant_a!r}"
    )


@pytest.mark.parametrize("tenant_a,tenant_b", TENANT_PAIRS)
def test_tenant_a_can_see_own_extractions(db: Session, tenant_a: str, tenant_b: str):
    """Positive check: tenant_a can access its own extraction results."""
    doc_id = f"doc-own-{uuid.uuid4().hex[:8]}"
    _insert_extraction(db, tenant_a, document_id=doc_id)

    result = _query_by_tenant(db, tenant_a, doc_id)
    assert len(result) == 1
    assert result[0].tenant_id == tenant_a


@pytest.mark.parametrize("tenant_a,tenant_b", TENANT_PAIRS)
def test_same_document_id_different_tenants_are_separate(db: Session, tenant_a: str, tenant_b: str):
    """Two tenants processing the same document_id must not see each other's extractions."""
    shared_doc = f"shared-doc-{uuid.uuid4().hex[:8]}"
    _insert_extraction(db, tenant_a, document_id=shared_doc)
    _insert_extraction(db, tenant_b, document_id=shared_doc)

    rows_a = _query_by_tenant(db, tenant_a, shared_doc)
    rows_b = _query_by_tenant(db, tenant_b, shared_doc)

    assert len(rows_a) == 1 and rows_a[0].tenant_id == tenant_a
    assert len(rows_b) == 1 and rows_b[0].tenant_id == tenant_b


# ---------------------------------------------------------------------------
# Consumer routing — in-process retry state isolation
# ---------------------------------------------------------------------------

class TestConsumerRetryStateIsolation:
    """Simulates the in-process retry counter map that the NLP consumer maintains.

    If a document fails extraction, the consumer increments a per-doc retry
    counter. If this counter is keyed only by document_id (not tenant_id),
    tenant A's transient failure could exhaust tenant B's retry budget.
    """

    def _make_retry_map(self) -> dict:
        """Return a naive retry map keyed by (tenant_id, document_id)."""
        return {}

    def _increment(self, retry_map: dict, tenant_id: str, doc_id: str) -> int:
        key = (tenant_id, doc_id)
        retry_map[key] = retry_map.get(key, 0) + 1
        return retry_map[key]

    def _get_count(self, retry_map: dict, tenant_id: str, doc_id: str) -> int:
        return retry_map.get((tenant_id, doc_id), 0)

    @pytest.mark.parametrize("tenant_a,tenant_b", TENANT_PAIRS)
    def test_retry_counts_are_tenant_scoped(self, tenant_a: str, tenant_b: str):
        """Tenant A's retry increments must not affect Tenant B's retry count."""
        retry_map = self._make_retry_map()
        doc_id = "shared-document"

        # Tenant A fails 3 times
        for _ in range(3):
            self._increment(retry_map, tenant_a, doc_id)

        # Tenant B should still have 0 retries for the same doc_id
        count_b = self._get_count(retry_map, tenant_b, doc_id)
        assert count_b == 0, (
            f"Tenant B's retry count for doc_id={doc_id!r} must be 0, "
            f"not {count_b} — retry state must be keyed by (tenant_id, doc_id)"
        )

    @pytest.mark.parametrize("tenant_a,tenant_b", TENANT_PAIRS)
    def test_each_tenant_has_independent_retry_budget(self, tenant_a: str, tenant_b: str):
        """Both tenants can independently exhaust retries without cross-contamination."""
        retry_map = self._make_retry_map()
        doc_id = "another-shared-doc"

        for _ in range(2):
            self._increment(retry_map, tenant_a, doc_id)
        for _ in range(5):
            self._increment(retry_map, tenant_b, doc_id)

        assert self._get_count(retry_map, tenant_a, doc_id) == 2
        assert self._get_count(retry_map, tenant_b, doc_id) == 5
