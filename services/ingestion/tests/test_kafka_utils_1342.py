"""Coverage for app/kafka_utils.py — SerializingProducer wrapper.

Locks:
- KeySerializer: None passthrough, bytes passthrough, str → UTF-8.
- get_producer:
    * cached: same instance returned across calls (lru_cache size=1)
    * raises RuntimeError when confluent_kafka.SerializingProducer is None
    * builds producer with bootstrap.servers from settings, a
      KeySerializer for keys, and a JSON serializer for values.
- send:
    * correlation headers injected via helper; custom bytes headers and
      str headers both forwarded (str encoded to bytes).
    * sign_event() is invoked with producer_service=INGESTION_PRODUCER_SERVICE
      and the correlation-injected header list as ``existing_headers``; its
      returned (enriched_payload, signed_headers) tuple is what actually
      hits producer.produce().
    * RuntimeError from get_producer() → HTTPException(503).
    * OSError/IOError/TypeError/ValueError/AttributeError from produce()
      → HTTPException(500).
    * KafkaAuthError from sign_event() → HTTPException(500)
      with "Kafka message signing unavailable" detail.

Issue: #1342
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List

import pytest
from fastapi import HTTPException

from app import kafka_utils as ku
from shared.kafka_auth import KafkaAuthError


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _silence_logger(monkeypatch):
    class _Silent:
        def info(self, *a, **k): pass
        def warning(self, *a, **k): pass
        def error(self, *a, **k): pass
        def debug(self, *a, **k): pass
    monkeypatch.setattr(ku, "logger", _Silent())


@pytest.fixture(autouse=True)
def _clear_cache():
    ku.get_producer.cache_clear()
    yield
    ku.get_producer.cache_clear()


class _FakeProducer:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.produce_calls: List[dict] = []
        self.flush_called = 0
        self.produce_raises: Exception | None = None

    def produce(self, **kwargs):
        self.produce_calls.append(kwargs)
        if self.produce_raises is not None:
            raise self.produce_raises

    def flush(self):
        self.flush_called += 1


# ---------------------------------------------------------------------------
# KeySerializer
# ---------------------------------------------------------------------------


class TestKeySerializer:

    def test_none_returns_none(self):
        assert ku.KeySerializer()(None) is None

    def test_bytes_passthrough(self):
        assert ku.KeySerializer()(b"\x00\x01") == b"\x00\x01"

    def test_str_encoded_utf8(self):
        assert ku.KeySerializer()("hello") == b"hello"

    def test_int_stringified_and_encoded(self):
        assert ku.KeySerializer()(42) == b"42"

    def test_ctx_kwarg_ignored(self):
        """Confluent calls ``serializer(obj, ctx)`` — ensure we accept it."""
        assert ku.KeySerializer()("x", ctx="whatever") == b"x"


# ---------------------------------------------------------------------------
# get_producer
# ---------------------------------------------------------------------------


class TestGetProducer:

    def test_raises_when_library_missing(self, monkeypatch):
        monkeypatch.setattr(ku, "SerializingProducer", None)
        with pytest.raises(RuntimeError, match="not installed"):
            ku.get_producer()

    def test_builds_with_expected_config(self, monkeypatch):
        monkeypatch.setattr(ku, "SerializingProducer", _FakeProducer)
        monkeypatch.setattr(ku, "get_settings", lambda: SimpleNamespace(
            kafka_bootstrap_servers="broker:9092",
        ))
        p = ku.get_producer()
        assert p.cfg["bootstrap.servers"] == "broker:9092"
        assert isinstance(p.cfg["key.serializer"], ku.KeySerializer)
        # Value serializer: callable that JSON-dumps and encodes utf-8
        v_serializer = p.cfg["value.serializer"]
        assert v_serializer({"a": 1}, None) == b'{"a": 1}'

    def test_lru_cache_returns_same_instance(self, monkeypatch):
        monkeypatch.setattr(ku, "SerializingProducer", _FakeProducer)
        monkeypatch.setattr(ku, "get_settings", lambda: SimpleNamespace(
            kafka_bootstrap_servers="b",
        ))
        p1 = ku.get_producer()
        p2 = ku.get_producer()
        assert p1 is p2


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


def _install_fake(
    monkeypatch,
    *,
    produce_raises: Exception | None = None,
    get_producer_raises: Exception | None = None,
    sign_raises: Exception | None = None,
):
    """Install a fake producer and stub the correlation + signing helpers.

    The fake ``sign_event`` pass-through enriches the payload with a
    ``_signed_by`` marker and appends an ``x-signature`` header, so tests
    can assert that the signed tuple is what actually reaches produce().
    """
    fake = _FakeProducer({"bootstrap.servers": "b"})
    if produce_raises is not None:
        fake.produce_raises = produce_raises

    if get_producer_raises is not None:
        def _gp():
            raise get_producer_raises
    else:
        def _gp():
            return fake

    monkeypatch.setattr(ku, "get_producer", _gp)

    # Correlation helper: append a fixed correlation header to existing list
    def _inject(existing):
        return list(existing) + [("x-corr-id", b"corr-123")]
    monkeypatch.setattr(ku, "inject_correlation_headers_tuples", _inject)

    # sign_event: enrich payload and signed headers. Captures call args on fake.
    captured: dict[str, Any] = {}

    def _sign(payload, *, producer_service, existing_headers):
        if sign_raises is not None:
            raise sign_raises
        captured["payload"] = payload
        captured["producer_service"] = producer_service
        captured["existing_headers"] = list(existing_headers)
        enriched = dict(payload)
        enriched["_signed_by"] = producer_service
        new_headers = list(existing_headers) + [("x-signature", b"sig-v1")]
        return enriched, new_headers

    monkeypatch.setattr(ku, "sign_event", _sign)
    fake.signing_captured = captured  # type: ignore[attr-defined]
    return fake


class TestSend:

    def test_happy_path_sends_and_flushes(self, monkeypatch):
        fake = _install_fake(monkeypatch)
        ku.send("events", {"hello": "world"}, key="k1")
        assert len(fake.produce_calls) == 1
        call = fake.produce_calls[0]
        assert call["topic"] == "events"
        assert call["key"] == "k1"
        # sign_event enriched the payload
        assert call["value"]["hello"] == "world"
        assert call["value"]["_signed_by"] == ku.INGESTION_PRODUCER_SERVICE
        # Correlation header was forwarded into sign_event and returned back
        assert ("x-corr-id", b"corr-123") in call["headers"]
        # Signer added its own header
        assert ("x-signature", b"sig-v1") in call["headers"]
        assert fake.flush_called == 1

    def test_sign_event_called_with_producer_service_constant(self, monkeypatch):
        fake = _install_fake(monkeypatch)
        ku.send("t", {"a": 1})
        assert fake.signing_captured["producer_service"] == "ingestion-service"
        # kafka_headers passed to sign_event include the correlation header
        assert ("x-corr-id", b"corr-123") in fake.signing_captured["existing_headers"]

    def test_str_custom_headers_encoded_to_bytes(self, monkeypatch):
        fake = _install_fake(monkeypatch)
        ku.send("t", {}, headers={"x-source": "web"})
        # sign_event saw the str-encoded extras merged with correlation
        existing = fake.signing_captured["existing_headers"]
        assert ("x-source", b"web") in existing
        assert ("x-corr-id", b"corr-123") in existing
        # Final headers forwarded to produce() retain both
        call = fake.produce_calls[0]
        assert ("x-source", b"web") in call["headers"]
        assert ("x-corr-id", b"corr-123") in call["headers"]

    def test_bytes_custom_headers_preserved(self, monkeypatch):
        fake = _install_fake(monkeypatch)
        ku.send("t", {}, headers={"x-bin": b"\x00\xff"})
        call = fake.produce_calls[0]
        assert ("x-bin", b"\x00\xff") in call["headers"]

    def test_bytearray_custom_headers_preserved(self, monkeypatch):
        """bytearray counts as (bytes, bytearray) — no re-encoding."""
        fake = _install_fake(monkeypatch)
        ku.send("t", {}, headers={"x-bin": bytearray(b"abc")})
        call = fake.produce_calls[0]
        names = [n for n, _ in call["headers"]]
        assert "x-bin" in names

    def test_numeric_custom_header_is_stringified(self, monkeypatch):
        """Non-bytes, non-str header values get str()+encode."""
        fake = _install_fake(monkeypatch)
        ku.send("t", {}, headers={"x-attempt": 3})
        call = fake.produce_calls[0]
        assert ("x-attempt", b"3") in call["headers"]

    def test_runtime_error_from_get_producer_becomes_503(self, monkeypatch):
        _install_fake(monkeypatch, get_producer_raises=RuntimeError("not installed"))
        with pytest.raises(HTTPException) as exc_info:
            ku.send("t", {})
        assert exc_info.value.status_code == 503
        assert "Kafka client unavailable" in exc_info.value.detail

    @pytest.mark.parametrize("exc", [
        OSError("network down"),
        IOError("socket closed"),
        TypeError("bad payload"),
        ValueError("bad value"),
        AttributeError("no attr"),
    ])
    def test_produce_errors_become_500(self, monkeypatch, exc):
        _install_fake(monkeypatch, produce_raises=exc)
        with pytest.raises(HTTPException) as exc_info:
            ku.send("t", {})
        assert exc_info.value.status_code == 500
        assert "Kafka publish failed" in exc_info.value.detail

    def test_kafka_auth_error_from_sign_becomes_500(self, monkeypatch):
        """Signing failure → 500 'Kafka message signing unavailable'.

        The producer should never be consulted when signing fails.
        """
        fake = _install_fake(
            monkeypatch,
            sign_raises=KafkaAuthError("signing_key_not_configured"),
        )
        with pytest.raises(HTTPException) as exc_info:
            ku.send("t", {"a": 1})
        assert exc_info.value.status_code == 500
        assert "Kafka message signing unavailable" in exc_info.value.detail
        # Producer was never called — signing gate short-circuits
        assert fake.produce_calls == []
        assert fake.flush_called == 0

    def test_no_custom_headers_still_injects_correlation(self, monkeypatch):
        fake = _install_fake(monkeypatch)
        ku.send("t", {})
        call = fake.produce_calls[0]
        # extras=[], inject → [('x-corr-id',...)], sign appends ('x-signature',...)
        assert ("x-corr-id", b"corr-123") in call["headers"]
        assert ("x-signature", b"sig-v1") in call["headers"]

    def test_key_defaults_to_none(self, monkeypatch):
        fake = _install_fake(monkeypatch)
        ku.send("t", {})
        assert fake.produce_calls[0]["key"] is None

    def test_ingestion_producer_service_constant(self):
        """Lock the producer-service allowlist string (#1078)."""
        assert ku.INGESTION_PRODUCER_SERVICE == "ingestion-service"
