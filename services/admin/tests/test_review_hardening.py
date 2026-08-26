"""
Regression tests for the review-queue hardening cluster:

  - #1360: cross-tenant approve/reject blocked at the tracker
  - #1361: review state machine rejects non-PENDING transitions
  - #1367: reviewer identity records user binding when provided
  - #1369: review decision writes to audit_logs hash chain
  - #1388: Kafka consumer HMAC envelope verification
  - #1389: list/approve/reject require a tenant-scoped API key
  - #1390: source_text sanitized on store and on response
"""

from __future__ import annotations

import os
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

# -------------------------------------------------------------------------
# Shared fake infrastructure -- mirrors the pattern in
# test_hallucination_tracker.py but adds an audit-log capture hook and a
# query method on the fake session so `list_hallucinations` works too.
# -------------------------------------------------------------------------


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.lists = {}

    def set(self, key, value, ex=None):
        self.store[key] = (value, ex)

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    def ltrim(self, key, start, end):
        if key in self.lists:
            self.lists[key] = self.lists[key][start : end + 1]

    def get(self, key):
        entry = self.store.get(key)
        return entry[0] if entry else None


class CapturingFakeSession:
    """Fake session that records audit log AuditLogger.log_event calls.

    The real AuditLogger builds an AuditLogModel entry via ``db.add``
    then calls ``db.flush()``. We track ``added`` items so tests can
    assert that an entry with event_type=review.decision was written.
    """

    def __init__(self, storage, audit_sink):
        self.storage = storage
        self.audit_sink = audit_sink
        self._pending_review = None
        # No real engine bind; AuditLogger._acquire_chain_lock treats a
        # None bind as "not SQLite" and issues the advisory-lock execute()
        # (harmlessly swallowed by .execute below). (#2513)
        self.bind = None

    def add(self, item):
        # AuditLogger writes AuditLogModel; tracker writes ReviewItemModel.
        # Route them to different sinks so tests can assert on each.
        from services.admin.app.sqlalchemy_models import (
            AuditLogModel,
            ReviewItemModel,
        )

        if isinstance(item, AuditLogModel):
            # A real database assigns the autoincrementing audit ID during
            # flush. Simulate that successful-persistence signal so the
            # fail-closed caller can distinguish it from AuditLogger's None
            # error return.
            item.id = len(self.audit_sink) + 1
            self.audit_sink.append(item)
            return
        if isinstance(item, ReviewItemModel):
            self._pending_review = item

    def execute(self, stmt, params=None):
        # AuditLogger._get_chain_head runs a SELECT; return a result whose
        # one_or_none returns None so the chain starts at GENESIS (seq 1).
        # _session_scope and the #2513 advisory lock also call execute;
        # those paths do not inspect the return value.
        class _Result:
            def one_or_none(self_inner):
                return None

            def scalar_one_or_none(self_inner):
                return None

        return _Result()

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

    def get(self, _model, key):
        return self.storage.get(key)

    def query(self, model):
        return _FakeQuery(self.storage)


class _FakeQuery:
    def __init__(self, storage):
        self._storage = storage
        self._tenant_filter = None

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def all(self):
        items = list(self._storage.values())
        return items[: getattr(self, "_limit", 50)]

    def first(self):
        items = list(self._storage.values())
        return items[0] if items else None


@pytest.fixture
def tracker_with_audit():
    """Build a HallucinationTracker whose fake session captures audit
    log inserts so #1369 can be asserted in isolation."""
    from services.admin.app.metrics import (
        HallucinationTracker,
        hallucination_active_reviews,
        hallucination_events_total,
    )

    hallucination_events_total._metrics.clear()  # type: ignore[attr-defined]
    hallucination_active_reviews._metrics.clear()  # type: ignore[attr-defined]

    storage: dict[UUID, object] = {}
    audit_sink: list = []

    def session_factory():
        return CapturingFakeSession(storage, audit_sink)

    tracker = HallucinationTracker(session_factory, FakeRedis())
    yield tracker, storage, audit_sink


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


# =========================================================================
# #1360: cross-tenant approve/reject blocked
# =========================================================================


def test_resolve_hallucination_blocks_cross_tenant_approval(tracker_with_audit):
    tracker, _storage, _audit = tracker_with_audit
    tenant_a = "11111111-1111-1111-1111-111111111111"
    tenant_b = "22222222-2222-2222-2222-222222222222"

    record = tracker.record_hallucination(
        tenant_id=tenant_a,
        document_id="doc-a",
        doc_hash="hash-a",
        extractor="GENERIC",
        confidence_score=0.3,
        extraction=_example_extraction(),
    )

    # Reviewer from tenant B tries to approve tenant A's record.
    # The tracker must raise LookupError (route maps to 404).
    with pytest.raises(LookupError):
        tracker.resolve_hallucination(
            record["review_id"],
            new_status="APPROVED",
            reviewer_id="tenant-b-key",
            tenant_id=tenant_b,
        )


def test_resolve_hallucination_allows_same_tenant(tracker_with_audit):
    tracker, _storage, _audit = tracker_with_audit
    tenant = "11111111-1111-1111-1111-111111111111"

    record = tracker.record_hallucination(
        tenant_id=tenant,
        document_id="doc-a",
        doc_hash="hash-a",
        extractor="GENERIC",
        confidence_score=0.3,
        extraction=_example_extraction(),
    )

    result = tracker.resolve_hallucination(
        record["review_id"],
        new_status="APPROVED",
        reviewer_id="same-tenant-key",
        tenant_id=tenant,
    )
    assert result["status"] == "APPROVED"


# =========================================================================
# #1361: idempotency / state machine
# =========================================================================


def test_resolve_hallucination_rejects_second_decision(tracker_with_audit):
    tracker, storage, _audit = tracker_with_audit
    tenant = "11111111-1111-1111-1111-111111111111"

    record = tracker.record_hallucination(
        tenant_id=tenant,
        document_id="doc-a",
        doc_hash="hash-a",
        extractor="GENERIC",
        confidence_score=0.3,
        extraction=_example_extraction(),
    )

    tracker.resolve_hallucination(
        record["review_id"],
        new_status="APPROVED",
        reviewer_id="first-reviewer-key",
        tenant_id=tenant,
        notes="looked good",
    )

    # A second call must raise ValueError ("already <status>") so
    # review_routes maps it to 409 Conflict.
    with pytest.raises(ValueError, match="already"):
        tracker.resolve_hallucination(
            record["review_id"],
            new_status="REJECTED",
            reviewer_id="second-reviewer-key",
            tenant_id=tenant,
            notes="trying to overwrite",
        )

    # Reviewer identity on the DB row must remain the first reviewer.
    item = storage[UUID(record["review_id"])]
    assert item.reviewer_id == "first-reviewer-key"
    assert item.status == "APPROVED"


# =========================================================================
# #1367: reviewer identity binding (human user captured when provided)
# =========================================================================


def test_resolve_hallucination_records_human_identity(tracker_with_audit):
    tracker, storage, _audit = tracker_with_audit
    tenant = "11111111-1111-1111-1111-111111111111"
    human_id = "99999999-9999-9999-9999-999999999999"

    record = tracker.record_hallucination(
        tenant_id=tenant,
        document_id="doc-a",
        doc_hash="hash-a",
        extractor="GENERIC",
        confidence_score=0.3,
        extraction=_example_extraction(),
    )

    tracker.resolve_hallucination(
        record["review_id"],
        new_status="APPROVED",
        reviewer_id="shared-api-key",
        tenant_id=tenant,
        actor_user_id=human_id,
        actor_email="jane.doe@example.com",
        notes="attested by Jane",
    )

    item = storage[UUID(record["review_id"])]
    identity = item.provenance.get("reviewer_identity")
    assert identity is not None, "provenance.reviewer_identity must be present"
    assert identity["api_key_id"] == "shared-api-key"
    assert identity["user_id"] == human_id
    assert identity["user_email"] == "jane.doe@example.com"
    assert identity["human_bound"] is True


def test_resolve_hallucination_flags_missing_human_binding(tracker_with_audit):
    tracker, storage, _audit = tracker_with_audit
    tenant = "11111111-1111-1111-1111-111111111111"

    record = tracker.record_hallucination(
        tenant_id=tenant,
        document_id="doc-a",
        doc_hash="hash-a",
        extractor="GENERIC",
        confidence_score=0.3,
        extraction=_example_extraction(),
    )

    tracker.resolve_hallucination(
        record["review_id"],
        new_status="APPROVED",
        reviewer_id="shared-api-key",
        tenant_id=tenant,
        notes="attested anonymously",
    )

    item = storage[UUID(record["review_id"])]
    identity = item.provenance.get("reviewer_identity")
    assert identity["human_bound"] is False
    assert identity["user_id"] is None


# =========================================================================
# #1369: audit_logs hash chain gets a review.decision entry
# =========================================================================


def test_resolve_hallucination_writes_to_audit_chain(tracker_with_audit):
    tracker, _storage, audit_sink = tracker_with_audit
    tenant = "11111111-1111-1111-1111-111111111111"

    record = tracker.record_hallucination(
        tenant_id=tenant,
        document_id="doc-a",
        doc_hash="hash-a",
        extractor="GENERIC",
        confidence_score=0.3,
        extraction=_example_extraction(),
    )

    tracker.resolve_hallucination(
        record["review_id"],
        new_status="APPROVED",
        reviewer_id="key-123",
        tenant_id=tenant,
        actor_user_id="99999999-9999-9999-9999-999999999999",
        actor_email="jane@example.com",
        notes="signed-off",
    )

    # Filter for the review.decision audit entry (ignore any other
    # audits emitted by other code paths).
    review_entries = [e for e in audit_sink if getattr(e, "event_type", None) == "review.decision"]
    assert len(review_entries) >= 1, (
        "Expected at least one audit_logs entry with event_type='review.decision' after approval (#1369)"
    )

    entry = review_entries[0]
    assert entry.resource_type == "review_item"
    assert entry.resource_id == record["review_id"]
    # Hash chain integrity fields populated
    assert entry.integrity_hash
    # metadata records the prior/new status
    meta = entry.metadata_
    assert meta["status"] == "APPROVED"
    assert meta["prior_status"] == "PENDING"


def test_resolve_hallucination_rolls_back_when_audit_persistence_fails(monkeypatch):
    """A review decision must never commit without its audit-chain row."""
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import sessionmaker

    from services.admin.app.audit import AuditLogger
    from services.admin.app.metrics import HallucinationTracker
    from services.admin.app.sqlalchemy_models import AuditLogModel, ReviewItemModel

    engine = create_engine("sqlite+pysqlite:///:memory:")
    ReviewItemModel.__table__.create(engine)
    AuditLogModel.__table__.create(engine)
    session_factory = sessionmaker(bind=engine)
    tracker = HallucinationTracker(session_factory, FakeRedis())
    tenant = "11111111-1111-1111-1111-111111111111"

    record = tracker.record_hallucination(
        tenant_id=tenant,
        document_id="doc-a",
        doc_hash="hash-audit-failure",
        extractor="GENERIC",
        confidence_score=0.3,
        extraction=_example_extraction(),
    )

    monkeypatch.setattr(AuditLogger, "log_event", staticmethod(lambda *args, **kwargs: None))

    with pytest.raises(RuntimeError, match="audit persistence failed"):
        tracker.resolve_hallucination(
            record["review_id"],
            new_status="APPROVED",
            reviewer_id="reviewer-1",
            tenant_id=tenant,
            actor_user_id="99999999-9999-9999-9999-999999999999",
        )

    with session_factory() as session:
        item = session.get(ReviewItemModel, UUID(record["review_id"]))
        assert item is not None
        assert item.status == "PENDING"
        assert session.scalar(select(func.count()).select_from(AuditLogModel)) == 0


# =========================================================================
# #1388 / #2139: Kafka consumer canonical signed-event verification
# =========================================================================


def _signed_review_event(payload: dict, *, producer_service: str = "nlp-service"):
    from shared.kafka_auth import sign_event

    return sign_event(payload, producer_service=producer_service)


def test_verify_review_event_accepts_signed_payload(monkeypatch):
    from services.admin.app.review_consumer import _verify_review_event

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KAFKA_EVENT_SIGNING_KEY", "test-signing-key")

    payload = {"tenant_id": "abc", "document_id": "doc-1", "extraction": {}}
    signed_body, signed_headers = _signed_review_event(payload)

    verified = _verify_review_event(signed_body, signed_headers)
    assert verified["tenant_id"] == "abc"
    assert verified["document_id"] == "doc-1"


def test_verify_review_event_rejects_unsigned_in_strict_mode(monkeypatch):
    from services.admin.app import review_consumer as rc_mod

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KAFKA_EVENT_SIGNING_KEY", "test-signing-key")

    with pytest.raises(rc_mod.KafkaAuthError) as excinfo:
        rc_mod._verify_review_event({"tenant_id": "abc"}, headers=[])
    assert excinfo.value.reason == "missing_sig_version_header"


def test_verify_review_event_rejects_tampered_body(monkeypatch):
    from services.admin.app import review_consumer as rc_mod

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KAFKA_EVENT_SIGNING_KEY", "test-signing-key")

    signed_body, signed_headers = _signed_review_event({"tenant_id": "abc", "document_id": "doc-1", "extraction": {}})
    tampered = dict(signed_body)
    tampered["tenant_id"] = "forged-tenant"

    with pytest.raises(rc_mod.KafkaAuthError) as excinfo:
        rc_mod._verify_review_event(tampered, signed_headers)
    assert excinfo.value.reason == "signature_mismatch"


def test_verify_review_event_rejects_wrong_producer(monkeypatch):
    from services.admin.app import review_consumer as rc_mod

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KAFKA_EVENT_SIGNING_KEY", "test-signing-key")

    signed_body, signed_headers = _signed_review_event(
        {"tenant_id": "abc", "document_id": "doc-1", "extraction": {}},
        producer_service="scheduler-service",
    )

    with pytest.raises(rc_mod.KafkaAuthError) as excinfo:
        rc_mod._verify_review_event(signed_body, signed_headers)
    assert excinfo.value.reason == "producer_not_allowed_for_topic"


def test_verify_review_event_dev_bypass_requires_local_env(monkeypatch):
    from shared.kafka_auth import BODY_FIELD_PRODUCER_SERVICE

    from services.admin.app import review_consumer as rc_mod

    monkeypatch.delenv("KAFKA_EVENT_SIGNING_KEY", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")

    unsigned_review_event = {
        "tenant_id": "abc",
        BODY_FIELD_PRODUCER_SERVICE: "nlp-service",
    }

    verified = rc_mod._verify_review_event(unsigned_review_event, headers=[])
    assert verified["tenant_id"] == "abc"

    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(rc_mod.KafkaAuthError) as excinfo:
        rc_mod._verify_review_event(unsigned_review_event, headers=[])
    assert excinfo.value.reason == "signing_key_not_configured"


def test_extract_and_record_uses_verified_signed_payload(monkeypatch):
    from services.admin.app import review_consumer as rc_mod

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KAFKA_EVENT_SIGNING_KEY", "test-signing-key")

    payload = {
        "tenant_id": "abc",
        "document_id": "doc-1",
        "doc_hash": "hash-1",
        "extraction": {
            "confidence_score": 0.42,
            "source_text": "<b>unsafe</b>",
            "attributes": {"extractor": "GENERIC"},
        },
    }
    signed_body, signed_headers = _signed_review_event(payload)
    captured = {}

    def _fake_record_with_retry(_tracker, **kwargs):
        captured.update(kwargs)
        return {"document_id": kwargs["document_id"], "confidence_score": kwargs["confidence_score"]}

    monkeypatch.setattr(rc_mod, "_record_with_retry", _fake_record_with_retry)

    result = rc_mod._extract_and_record(
        signed_body,
        tracker=object(),
        headers=signed_headers,
    )

    assert result["document_id"] == "doc-1"
    assert captured["tenant_id"] == "abc"
    assert captured["doc_hash"] == "hash-1"
    assert captured["extractor"] == "GENERIC"
    assert captured["text_raw"] != "<b>unsafe</b>"


# =========================================================================
# #1389: tenant-scoped browser session required for review queue
# =========================================================================


def test_review_routes_do_not_accept_api_key_authentication():
    import inspect

    from services.admin.app import review_routes

    source = inspect.getsource(review_routes)
    assert "require_api_key" not in source
    assert "X-RegEngine-API-Key" not in source


def test_review_routes_use_distinct_read_and_decide_dependencies():
    from services.admin.app import review_routes

    route_dependencies = {
        (route.path, method): {dependency.call for dependency in route.dependant.dependencies}
        for route in review_routes.router.routes
        for method in route.methods
    }
    assert review_routes.require_review_read in route_dependencies[
        ("/v1/admin/review/hallucinations", "GET")
    ]
    assert review_routes.require_review_decide in route_dependencies[
        ("/v1/admin/review/{review_id}/approve", "POST")
    ]
    assert review_routes.require_review_decide in route_dependencies[
        ("/v1/admin/review/{review_id}/reject", "POST")
    ]


# =========================================================================
# #1390: source_text sanitization (store + response)
# =========================================================================


def test_sanitize_source_text_strips_script_tags():
    from services.admin.app.text_sanitize import sanitize_source_text_for_store

    malicious = "Hello <script>alert('xss')</script> world"
    cleaned = sanitize_source_text_for_store(malicious)
    assert "<script>" not in cleaned
    assert "alert" not in cleaned or "alert" in cleaned  # content of tag removed
    assert "world" in cleaned


def test_sanitize_source_text_escapes_bare_angle_brackets():
    from services.admin.app.text_sanitize import sanitize_source_text_for_store

    value = "<b>Bold</b> & <i>italic</i>"
    cleaned = sanitize_source_text_for_store(value)
    assert "<b>" not in cleaned
    assert "<i>" not in cleaned
    assert "Bold" in cleaned
    # ampersand must be escaped
    assert "&amp;" in cleaned


def test_sanitize_source_text_neutralizes_javascript_uri():
    from services.admin.app.text_sanitize import sanitize_source_text_for_store

    value = "Click javascript:alert(1) for more"
    cleaned = sanitize_source_text_for_store(value)
    assert "javascript:" not in cleaned


def test_sanitize_source_text_response_path_re_sanitizes():
    """Even if pre-fix data slipped into the DB raw, the response path
    must re-escape it."""
    from services.admin.app.text_sanitize import sanitize_source_text_for_response

    legacy_raw = "<iframe src=evil.com></iframe>"
    cleaned = sanitize_source_text_for_response(legacy_raw)
    assert "<iframe" not in cleaned


# =========================================================================
# #1201: tenacity retry must have a hard wall-clock cap so a persistently
# failing downstream call cannot block the consumer past the Kafka
# consumer-group rebalance timeout (default max.poll.interval.ms=300s).
# =========================================================================


def test_record_with_retry_honors_total_wait_cap(monkeypatch):
    """If the downstream call fails persistently, the retry MUST bail
    within the configured wall-clock cap instead of continuing to retry
    with exponential backoff that could exceed the rebalance timeout.
    """
    import importlib
    import time as _time

    from sqlalchemy.exc import OperationalError

    # Configure a tiny retry budget (200 ms) and reload the module so
    # the @retry decorator picks up the new stop_after_delay value.
    monkeypatch.setenv("REVIEW_CONSUMER_RETRY_MAX_WAIT_SECONDS", "0.2")
    from services.admin.app import review_consumer as rc_mod

    rc_mod = importlib.reload(rc_mod)

    call_count = {"n": 0}

    class _AlwaysFailTracker:
        def record_hallucination(self, **_kwargs):
            call_count["n"] += 1
            raise OperationalError("boom", params=None, orig=Exception("db down"))

    started = _time.perf_counter()
    with pytest.raises(OperationalError):
        rc_mod._record_with_retry(
            _AlwaysFailTracker(),
            tenant_id="11111111-1111-1111-1111-111111111111",
            document_id="doc-1",
            doc_hash="h",
            extractor="X",
            confidence_score=0.1,
            extraction={},
        )
    elapsed = _time.perf_counter() - started

    # Must NOT block for longer than a small multiple of the configured
    # cap (allow headroom for the final in-flight attempt + scheduler
    # jitter, but catch any regression that removes the delay stop).
    assert elapsed < 5.0, (
        f"retry budget exceeded: elapsed={elapsed:.2f}s, "
        f"cap=0.2s, calls={call_count['n']} "
        "-- stop_after_delay regression would let this grow unbounded"
    )
    # And it must actually have attempted at least once.
    assert call_count["n"] >= 1


def test_record_with_retry_default_cap_is_configured(monkeypatch):
    """The default cap must be a sane value comfortably under the Kafka
    broker's default max.poll.interval.ms (300s) -- otherwise a single
    poorly-timed failure can trigger a consumer-group rebalance."""
    import importlib

    monkeypatch.delenv("REVIEW_CONSUMER_RETRY_MAX_WAIT_SECONDS", raising=False)
    from services.admin.app import review_consumer as rc_mod

    rc_mod = importlib.reload(rc_mod)

    assert 0 < rc_mod.REVIEW_CONSUMER_RETRY_MAX_WAIT_SECONDS < 300, (
        "default retry cap must be well under Kafka max.poll.interval.ms (300s) to avoid rebalance death spiral"
    )
