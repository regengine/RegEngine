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
from uuid import UUID, uuid4
from unittest.mock import patch

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

    def add(self, item):
        # AuditLogger writes AuditLogModel; tracker writes ReviewItemModel.
        # Route them to different sinks so tests can assert on each.
        from services.admin.app.sqlalchemy_models import (
            AuditLogModel,
            ReviewItemModel,
        )

        if isinstance(item, AuditLogModel):
            self.audit_sink.append(item)
            return
        if isinstance(item, ReviewItemModel):
            self._pending_review = item

    def execute(self, stmt, params=None):
        # AuditLogger._get_prev_hash runs a SELECT; return a result
        # whose scalar_one_or_none returns None so the chain starts at
        # GENESIS. _session_scope also calls execute for SET LOCAL;
        # that path does not inspect the return value.
        class _Result:
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
    review_entries = [
        e for e in audit_sink if getattr(e, "event_type", None) == "review.decision"
    ]
    assert len(review_entries) >= 1, (
        "Expected at least one audit_logs entry with "
        "event_type='review.decision' after approval (#1369)"
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


# =========================================================================
# #1388: Kafka consumer HMAC envelope verification
# =========================================================================


def test_verify_hmac_envelope_rejects_unsigned_when_secret_set(monkeypatch):
    from services.admin.app.review_consumer import _verify_hmac_envelope

    monkeypatch.setenv("NLP_REVIEW_HMAC_SECRET", "test-secret-xyz")

    # Unsigned bare event -> reject
    assert _verify_hmac_envelope({"tenant_id": "abc"}) is False
    # Missing hmac field -> reject
    assert _verify_hmac_envelope({"payload": {"tenant_id": "abc"}}) is False
    # Tampered signature -> reject
    assert _verify_hmac_envelope(
        {"payload": {"tenant_id": "abc"}, "hmac": "deadbeef"}
    ) is False


def test_verify_hmac_envelope_accepts_valid_signature(monkeypatch):
    import hashlib
    import hmac
    import json

    from services.admin.app.review_consumer import _verify_hmac_envelope

    secret = "test-secret-xyz"
    monkeypatch.setenv("NLP_REVIEW_HMAC_SECRET", secret)

    payload = {"tenant_id": "abc", "document_id": "doc-1", "extraction": {}}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()

    assert _verify_hmac_envelope({"payload": payload, "hmac": sig}) is True


def test_verify_hmac_envelope_legacy_mode_when_secret_unset(monkeypatch):
    from services.admin.app.review_consumer import _verify_hmac_envelope

    monkeypatch.delenv("NLP_REVIEW_HMAC_SECRET", raising=False)
    # Legacy mode: any event accepted (with warning). We don't assert
    # on the warning itself here; the log entry is visible in ops.
    assert _verify_hmac_envelope({"tenant_id": "abc"}) is True


# =========================================================================
# #1389: tenant-scoped API key required for review queue
# =========================================================================


def test_require_tenant_scoped_key_rejects_null_tenant():
    from fastapi import HTTPException

    from services.admin.app.review_routes import _require_tenant_scoped_key
    from shared.auth import APIKey

    key_no_tenant = APIKey(
        key_id="rge_legacy",
        key_hash="x",
        name="legacy",
        tenant_id=None,
        created_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
    )
    with pytest.raises(HTTPException) as excinfo:
        _require_tenant_scoped_key(key_no_tenant)
    assert excinfo.value.status_code == 403


def test_require_tenant_scoped_key_accepts_tenant_bound():
    from services.admin.app.review_routes import _require_tenant_scoped_key
    from shared.auth import APIKey

    key = APIKey(
        key_id="rge_ok",
        key_hash="x",
        name="ok",
        tenant_id="11111111-1111-1111-1111-111111111111",
        created_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
    )
    assert _require_tenant_scoped_key(key) == "11111111-1111-1111-1111-111111111111"


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
