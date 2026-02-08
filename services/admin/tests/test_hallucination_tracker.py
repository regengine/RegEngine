"""Integration-style tests for the HallucinationTracker plumbing."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from services.admin.app.metrics import (
    HallucinationTracker,
    hallucination_active_reviews,
    hallucination_duplicates_total,
    hallucination_events_total,
)


class FakeRedis:
    """Minimal Redis stub for caching assertions."""

    def __init__(self):
        self.store: dict[str, tuple[str, int | None]] = {}
        self.lists: dict[str, list[str]] = {}

    def set(self, key: str, value: str, ex: int | None = None):
        self.store[key] = (value, ex)

    def lpush(self, key: str, value: str):
        self.lists.setdefault(key, []).insert(0, value)

    def ltrim(self, key: str, start: int, end: int):
        if key not in self.lists:
            return
        self.lists[key] = self.lists[key][start : end + 1]

    def get(self, key: str) -> str | None:
        entry = self.store.get(key)
        return entry[0] if entry else None


class FakeSession:
    """Lightweight session stub with in-memory persistence."""

    def __init__(self, storage: dict[UUID, object]):
        self.storage = storage
        self._pending = None

    def add(self, item):
        self._pending = item

    def execute(self, stmt):
        """No-op: absorbs SET LOCAL tenant context in tests."""
        return None

    def flush(self):
        return None

    def refresh(self, item):
        if getattr(item, "id", None) is None:
            item.id = uuid4()
        self.storage[item.id] = item

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None

    def get(self, _model, key: UUID):
        return self.storage.get(key)


@pytest.fixture(autouse=True)
def reset_metrics():
    """Ensure each test starts with clean metric state."""

    hallucination_events_total._metrics.clear()  # type: ignore[attr-defined]
    hallucination_active_reviews._metrics.clear()  # type: ignore[attr-defined]
    yield
    hallucination_events_total._metrics.clear()  # type: ignore[attr-defined]
    hallucination_active_reviews._metrics.clear()  # type: ignore[attr-defined]


@pytest.fixture
def tracker_fixture():
    storage: dict[UUID, object] = {}
    fake_redis = FakeRedis()

    def session_factory():
        return FakeSession(storage)

    tracker = HallucinationTracker(session_factory, fake_redis)
    return tracker, storage, fake_redis


def _example_extraction():
    return {
        "subject": "bank",
        "action": "must maintain",
        "obligation_type": "MUST",
        "thresholds": [],
        "confidence_score": 0.42,
        "source_text": "Banks must maintain liquidity.",
        "source_offset": 0,
        "attributes": {},
    }


def test_record_hallucination_tracks_state(tracker_fixture):
    tracker, storage, fake_redis = tracker_fixture
    tenant_id = "550e8400-e29b-41d4-a716-446655440000"

    record = tracker.record_hallucination(
        tenant_id=tenant_id,
        document_id="doc-123",
        doc_hash="hash-abc",
        extractor="GENERIC",
        confidence_score=0.41,
        extraction=_example_extraction(),
        provenance={"source_url": "https://example.com"},
        text_raw="Banks must maintain liquidity.",
    )

    review_uuid = UUID(record["review_id"])
    assert storage[review_uuid].status == "PENDING"
    cache_key = f"hallucination:{record['review_id']}"
    assert fake_redis.get(cache_key) is not None

    counter_value = (
        hallucination_events_total.labels(tenant_id=tenant_id, extractor="GENERIC")._value.get()  # type: ignore[attr-defined]
    )
    gauge_value = hallucination_active_reviews.labels(tenant_id=tenant_id)._value.get()  # type: ignore[attr-defined]

    assert counter_value == 1.0
    assert gauge_value == 1.0


def test_resolve_hallucination_updates_metrics(tracker_fixture):
    tracker, storage, _ = tracker_fixture
    tenant_id = "550e8400-e29b-41d4-a716-446655440000"
    record = tracker.record_hallucination(
        tenant_id=tenant_id,
        document_id="doc-999",
        doc_hash="hash-xyz",
        extractor="GENERIC",
        confidence_score=0.2,
        extraction=_example_extraction(),
    )

    tracker.resolve_hallucination(
        record["review_id"], new_status="APPROVED", reviewer_id="human-reviewer", notes="looks good"
    )

    review_uuid = UUID(record["review_id"])
    item = storage[review_uuid]
    assert item.status == "APPROVED"
    assert item.reviewer_id == "human-reviewer"

    gauge_value = hallucination_active_reviews.labels(tenant_id=tenant_id)._value.get()  # type: ignore[attr-defined]
    assert gauge_value == 0.0


def test_resolve_hallucination_missing_item(tracker_fixture):
    tracker, _storage, _ = tracker_fixture
    with pytest.raises(LookupError):
        tracker.resolve_hallucination(str(uuid4()), new_status="APPROVED", reviewer_id="ops")


def test_record_hallucinations_batch(tracker_fixture):
    """Test batch insert of multiple hallucinations."""
    tracker, storage, _ = tracker_fixture
    tenant_id = "550e8400-e29b-41d4-a716-446655440000"
    
    items = [
        {
            "tenant_id": tenant_id,
            "document_id": f"doc-{i}",
            "doc_hash": f"hash-{i}",
            "extractor": "GENERIC",
            "confidence_score": 0.3 + (i * 0.1),
            "extraction": _example_extraction(),
        }
        for i in range(3)
    ]
    
    result = tracker.record_hallucinations_batch(items)
    
    # New return format: {successful, failed, results}
    assert "successful" in result
    assert "failed" in result
    assert "results" in result
    assert result["successful"] == 3
    assert result["failed"] == 0
    assert len(result["results"]) == 3


def test_list_hallucinations_pagination_format(tracker_fixture):
    """Test that list_hallucinations returns paginated format."""
    tracker, storage, _ = tracker_fixture
    
    # Create a fake query method on FakeSession
    class QueryableFakeSession(FakeSession):
        def execute(self, stmt):
            """No-op: absorbs SET LOCAL tenant context in tests."""
            return None

        def query(self, model):
            return FakeQuery(self.storage)
    
    class FakeQuery:
        def __init__(self, storage):
            self._storage = storage
            self._filters = []
        
        def filter(self, *args):
            return self
        
        def order_by(self, *args):
            return self
        
        def limit(self, n):
            self._limit = n
            return self
        
        def all(self):
            items = list(self._storage.values())
            return items[:getattr(self, "_limit", 50)]
    
    storage.clear()
    queryable_storage = {}
    
    def session_factory():
        return QueryableFakeSession(queryable_storage)
    
    tracker_paginated = HallucinationTracker(session_factory, None)
    
    # Record one item first  
    record = tracker_paginated.record_hallucination(
        tenant_id="550e8400-e29b-41d4-a716-446655440000",
        document_id="doc-test",
        doc_hash="hash-test",
        extractor="GENERIC",
        confidence_score=0.5,
        extraction=_example_extraction(),
    )
    
    result = tracker_paginated.list_hallucinations()
    
    assert "items" in result
    assert "next_cursor" in result
    assert "has_more" in result
    assert isinstance(result["items"], list)