"""Store-both contract for review-item source text.

The ``text_sanitize`` module docstring promises the raw document text is
stored verbatim in the DB while clients only ever see a sanitized copy.
This test pins that contract at the Kafka consumer boundary
(``review_consumer._extract_and_record``):

* ``text_raw`` passed to the tracker must be the raw verbatim text, so
  downstream analytics, model training and audit exports can access the
  original.
* ``extraction["source_text"]`` must hold the sanitized copy, so any
  downstream reader of the extraction dict cannot leak stored XSS.
* The tracker detail projection (``_serialize``) must sanitize
  ``text_raw`` on read, so the verbatim column value is never returned
  to a client directly.

Tracks the audit finding: sanitizer docstring vs destructive overwrite.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

from app.text_sanitize import (  # noqa: E402
    sanitize_source_text_for_response,
    sanitize_source_text_for_store,
)

RAW = "<script>alert(1)</script>Banks must maintain liquidity & report <b>daily</b>"


def _extract_and_record_kwargs(monkeypatch, raw_text=RAW):
    from shared.kafka_auth import sign_event

    from services.admin.app import review_consumer as rc_mod

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KAFKA_EVENT_SIGNING_KEY", "test-signing-key")

    captured: dict = {}

    def _fake_record_with_retry(_tracker, **kwargs):
        captured.update(kwargs)
        return {"document_id": kwargs["document_id"]}

    monkeypatch.setattr(rc_mod, "_record_with_retry", _fake_record_with_retry)
    signed_body, signed_headers = sign_event(
        {
            "tenant_id": "abc",
            "document_id": "doc-1",
            "doc_hash": "hash-1",
            "extraction": {
                "confidence_score": 0.42,
                "source_text": raw_text,
                "attributes": {"extractor": "GENERIC"},
            },
        },
        producer_service="nlp-service",
    )
    rc_mod._extract_and_record(
        signed_body,
        tracker=object(),
        headers=signed_headers,
    )
    return captured


class TestStoreBothContract:
    def test_text_raw_keeps_verbatim_original(self, monkeypatch):
        """``text_raw`` must carry the raw bytes, not the sanitized copy."""
        captured = _extract_and_record_kwargs(monkeypatch)
        assert captured["text_raw"] == RAW

    def test_extraction_source_text_is_sanitized(self, monkeypatch):
        """Readers of ``extraction["source_text"]`` must see the safe copy."""
        captured = _extract_and_record_kwargs(monkeypatch)
        sanitized = captured["extraction"]["source_text"]
        assert sanitized == sanitize_source_text_for_store(RAW)
        assert "<script>" not in sanitized
        assert "Banks must maintain liquidity" in sanitized

    def test_both_versions_available_together(self, monkeypatch):
        """The whole point: raw for analytics, sanitized for display."""
        captured = _extract_and_record_kwargs(monkeypatch)
        assert captured["text_raw"] != captured["extraction"]["source_text"]
        assert "alert" not in captured["extraction"]["source_text"]
        assert "alert(1)" in captured["text_raw"]


class TestDetailReadNeverReturnsRaw:
    def test_serialize_sanitizes_text_raw(self):
        """The detail projection must re-sanitize, so the verbatim DB
        value is never handed to a client directly."""
        from app.metrics import HallucinationTracker

        item = SimpleNamespace(
            id="11111111-2222-3333-4444-555555555555",
            tenant_id=None,
            doc_hash="hash-abc",
            confidence_score=0.5,
            status="PENDING",
            created_at=None,
            updated_at=None,
            extraction={"attributes": {}},
            provenance=None,
            reviewer_id=None,
            text_raw=RAW,
        )
        tracker = HallucinationTracker(session_factory=lambda: None)
        result = tracker._serialize(item)
        assert result["text_raw"] == sanitize_source_text_for_response(RAW)
        assert "<script>" not in result["text_raw"]

    def test_sanitizer_helpers_agree(self):
        assert sanitize_source_text_for_response(RAW) == sanitize_source_text_for_store(RAW)
