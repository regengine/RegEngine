"""Regression tests for NLP consumer Kafka-message authentication (#1078).

These tests pin the behavior that every downstream emission from the
NLP consumer carries an HMAC signature (so ``graph.update`` /
``nlp.needs_review`` subscribers can verify producer identity), and
that every upstream message reaching :func:`_route_extraction` or the
FSMA router goes out with the correct producer-service claim bound to
the signed body.

The cross-tenant injection primitive the issue describes is that
consumers downstream of NLP (graph consumer, review queue consumer)
trust ``tenant_id`` in the event body. These tests prove that the
NLP consumer's emit path cannot publish an event without a signature,
so a downstream consumer running strict verification will refuse any
unsigned event — closing the injection window.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


from shared.kafka_auth import (
    HEADER_PRODUCER_SERVICE,
    HEADER_SIGNATURE,
    HEADER_SIG_VERSION,
    KafkaAuthError,
    verify_event,
)


def _call_kwargs_headers(call) -> list[tuple[str, bytes]]:
    """Pull the ``headers=`` kwarg out of a producer.send mock call."""
    return list(call.kwargs.get("headers") or [])


def _call_kwargs_value(call) -> dict:
    """Pull the ``value=`` kwarg out of a producer.send mock call."""
    return dict(call.kwargs.get("value") or {})


class TestRouteExtractionSigns:
    """Every emit out of _route_extraction must be signed (#1078)."""

    @pytest.fixture
    def producer(self) -> MagicMock:
        mock = MagicMock()
        mock.send.return_value = MagicMock()
        return mock

    def test_high_confidence_emit_is_signed(self, producer: MagicMock) -> None:
        from services.nlp.app.consumer import (
            NLP_PRODUCER_SERVICE,
            _route_extraction,
            ExtractionPayload,
        )

        extraction = ExtractionPayload(
            subject="Banks",
            action="must maintain",
            obligation_type="MUST",
            confidence_score=0.95,
            source_text="Banks must maintain capital",
            source_offset=0,
            attributes={},
        )
        tenant_id = str(uuid4())
        _route_extraction(
            extraction=extraction,
            doc_id="doc-123",
            doc_hash="hash-abc",
            source_url="https://example.com",
            producer=producer,
            tenant_id=tenant_id,
        )

        producer.send.assert_called_once()
        call = producer.send.call_args
        # Topic
        assert call.args[0] == "graph.update"
        # Signed body + headers round-trip through verify_event
        value = _call_kwargs_value(call)
        headers = _call_kwargs_headers(call)

        header_names = {name for name, _ in headers}
        assert HEADER_SIGNATURE in header_names
        assert HEADER_PRODUCER_SERVICE in header_names
        assert HEADER_SIG_VERSION in header_names

        evt, producer_service = verify_event(
            value,
            headers,
            topic="graph.update",
        )
        assert producer_service == NLP_PRODUCER_SERVICE
        # The sensitive routing field survives the sign / verify round trip.
        assert evt["tenant_id"] == tenant_id

    def test_low_confidence_emit_is_signed(self, producer: MagicMock) -> None:
        from services.nlp.app.consumer import (
            NLP_PRODUCER_SERVICE,
            _route_extraction,
            ExtractionPayload,
        )

        extraction = ExtractionPayload(
            subject="banks",
            action="should maintain",
            obligation_type="SHOULD",
            confidence_score=0.50,
            source_text="Maybe banks should maintain capital",
            source_offset=0,
            attributes={},
        )
        tenant_id = str(uuid4())
        _route_extraction(
            extraction=extraction,
            doc_id="doc-456",
            doc_hash="hash-def",
            source_url="https://example.com",
            producer=producer,
            tenant_id=tenant_id,
        )

        producer.send.assert_called_once()
        call = producer.send.call_args
        assert call.args[0] == "nlp.needs_review"
        evt, producer_service = verify_event(
            _call_kwargs_value(call),
            _call_kwargs_headers(call),
            topic="nlp.needs_review",
        )
        assert producer_service == NLP_PRODUCER_SERVICE
        assert evt["tenant_id"] == tenant_id

    def test_review_priority_header_survives_signing(
        self, producer: MagicMock
    ) -> None:
        """X-Review-Priority is a correlation header — must not get stripped."""
        from services.nlp.app.consumer import _route_extraction, ExtractionPayload

        extraction = ExtractionPayload(
            subject="x",
            action="y",
            obligation_type="MUST",
            confidence_score=0.50,
            source_text="z",
            source_offset=0,
            attributes={},
        )
        _route_extraction(
            extraction=extraction,
            doc_id="doc-p",
            doc_hash="h",
            source_url="s",
            producer=producer,
            tenant_id=str(uuid4()),
        )

        headers = _call_kwargs_headers(producer.send.call_args)
        header_names = {name for name, _ in headers}
        assert "X-Review-Priority" in header_names

    def test_signature_covers_tenant_id_field(self, producer: MagicMock) -> None:
        """Swap tenant_id post-sign → verify must fail. The cross-tenant
        injection primitive from the issue description."""
        from services.nlp.app.consumer import _route_extraction, ExtractionPayload

        extraction = ExtractionPayload(
            subject="x",
            action="y",
            obligation_type="MUST",
            confidence_score=0.99,
            source_text="z",
            source_offset=0,
            attributes={},
        )
        legitimate_tenant = str(uuid4())
        _route_extraction(
            extraction=extraction,
            doc_id="doc-t",
            doc_hash="h",
            source_url="s",
            producer=producer,
            tenant_id=legitimate_tenant,
        )

        call = producer.send.call_args
        value = _call_kwargs_value(call)
        headers = _call_kwargs_headers(call)

        # Attacker swaps tenant_id after the sign — verify must catch it.
        tampered = dict(value)
        tampered["tenant_id"] = "ATTACKER-TENANT-ID"
        with pytest.raises(KafkaAuthError) as excinfo:
            verify_event(tampered, headers, topic="graph.update")
        assert excinfo.value.reason == "signature_mismatch"


class TestIngestionSendSigns:
    """ingestion/app/kafka_utils.send() must sign every message (#1078)."""

    def test_send_signs_payload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from services.ingestion.app import kafka_utils

        captured: dict = {}

        class _FakeProducer:
            def produce(self, topic, key, value, headers):
                captured["topic"] = topic
                captured["key"] = key
                captured["value"] = value
                captured["headers"] = list(headers)

            def flush(self):
                pass

        monkeypatch.setattr(kafka_utils, "get_producer", lambda: _FakeProducer())

        payload = {"tenant_id": "tenant-x", "doc_id": "d1"}
        kafka_utils.send("ingest.normalized", payload, key="k1")

        assert captured["topic"] == "ingest.normalized"
        header_names = {name for name, _ in captured["headers"]}
        assert HEADER_SIGNATURE in header_names
        assert HEADER_PRODUCER_SERVICE in header_names

        evt, producer_service = verify_event(
            captured["value"],
            captured["headers"],
            topic="ingest.normalized",
        )
        assert producer_service == kafka_utils.INGESTION_PRODUCER_SERVICE
        assert evt["tenant_id"] == "tenant-x"
        assert evt["doc_id"] == "d1"
