"""Size envelope for supplier-linked S3 objects.

``services/nlp/app/s3_utils.py:get_bytes`` used to buffer the whole
object with a single ``Body.read()``, so one oversized supplier object
bypassed the HTTP size envelope (``MAX_DOC_BYTES`` in text_loader.py)
and could exhaust consumer memory. It now checks the declared
``ContentLength`` first and caps the streamed bytes, and the consumer
loop skips an over-cap object instead of buffering it.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from services.nlp.app.s3_utils import S3ObjectTooLargeError, get_bytes


def _install_fake_s3(monkeypatch, *, declared, body: bytes):
    """Patch s3_client() so get_object returns a fake response."""
    from services.nlp.app import s3_utils as s3_utils_mod

    stream = io.BytesIO(body)

    fake_client = MagicMock(name="s3_client")
    fake_client.get_object.return_value = {
        "ContentLength": declared,
        "Body": stream,
    }
    monkeypatch.setattr(s3_utils_mod, "s3_client", lambda: fake_client)
    return fake_client, stream


class TestGetBytesSizeCap:
    def test_declared_over_cap_raises_before_buffering(self, monkeypatch):
        _, stream = _install_fake_s3(monkeypatch, declared=100_000_000, body=b'{"text": "x"}')
        with pytest.raises(S3ObjectTooLargeError, match="E_DOC_TOO_LARGE"):
            get_bytes("b", "k", max_bytes=1024)
        # Declared length is checked first: the body stream is untouched.
        assert stream.tell() == 0

    def test_declared_over_cap_message_carries_marker(self, monkeypatch):
        _install_fake_s3(monkeypatch, declared=2048, body=b"{}")
        with pytest.raises(S3ObjectTooLargeError, match="E_DOC_TOO_LARGE"):
            get_bytes("b", "k", max_bytes=1024)

    def test_streamed_over_cap_raises_when_declared_lies(self, monkeypatch):
        # Wrong or missing ContentLength must not let an unbounded body
        # into memory: the streamed bytes are capped too.
        _install_fake_s3(monkeypatch, declared=10, body=b"y" * 4096)
        with pytest.raises(S3ObjectTooLargeError, match="E_DOC_TOO_LARGE"):
            get_bytes("b", "k", max_bytes=1024)

    def test_missing_content_length_still_capped(self, monkeypatch):
        _install_fake_s3(monkeypatch, declared=None, body=b"z" * 4096)
        with pytest.raises(S3ObjectTooLargeError, match="E_DOC_TOO_LARGE"):
            get_bytes("b", "k", max_bytes=1024)

    def test_under_cap_returns_bytes(self, monkeypatch):
        body = b'{"text": "hello"}'
        _install_fake_s3(monkeypatch, declared=len(body), body=body)
        assert get_bytes("b", "k", max_bytes=1024) == body


TENANT = "11111111-1111-1111-1111-111111111111"


def _run_loop_with_s3(monkeypatch, get_bytes_side_effect):
    """Drive one consumer-loop batch whose record points at S3."""
    from services.nlp.app import consumer as consumer_mod

    consumer_mod._shutdown_event.clear()

    evt = {
        "document_id": "doc-oversize",
        "tenant_id": TENANT,
        "normalized_s3_path": "s3://bucket/key.json",
    }
    record = MagicMock()
    record.value = json.dumps(evt).encode("utf-8")
    record.offset = 7
    record.topic = "ingest.normalized"
    record.headers = []

    consumer = MagicMock(name="KafkaConsumer")
    calls = {"n": 0}
    tp = MagicMock()

    def _poll(*_a, **_kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return {tp: [record]}
        consumer_mod._shutdown_event.set()
        return {}

    consumer.poll.side_effect = _poll
    producer = MagicMock(name="KafkaProducer")
    producer.flush.return_value = None

    monkeypatch.setattr(consumer_mod, "KafkaConsumer", MagicMock(return_value=consumer))
    monkeypatch.setattr(consumer_mod, "KafkaProducer", MagicMock(return_value=producer))
    monkeypatch.setattr(consumer_mod, "_ensure_topic", MagicMock())
    monkeypatch.setattr(consumer_mod, "_start_health_server", MagicMock())
    monkeypatch.setattr(
        consumer_mod,
        "verify_event",
        lambda evt, headers, topic, allowed_producers: (evt, "tester"),
    )
    monkeypatch.setattr(consumer_mod, "get_allowed_producers", lambda topic: [])
    monkeypatch.setattr(consumer_mod, "_INBOUND_VALIDATOR", None)
    monkeypatch.setattr(consumer_mod, "get_bytes", MagicMock(side_effect=get_bytes_side_effect))

    consumer_mod.run_consumer()
    return consumer, producer


class TestConsumerSkipsOversizeS3Object:
    def test_oversize_object_is_skipped_not_buffered(self, monkeypatch):
        consumer, producer = _run_loop_with_s3(
            monkeypatch,
            S3ObjectTooLargeError("E_DOC_TOO_LARGE: s3://bucket/key.json exceeds 1024 bytes"),
        )

        # The offset is committed so the record does not spin forever.
        assert consumer.commit.called
        # Nothing is routed downstream and nothing is dead-lettered:
        # a skip, not a retry or a DLQ escalation.
        assert producer.send.call_count == 0
