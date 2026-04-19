"""Tests for :mod:`shared.kafka_auth` — HMAC event signing / verification (#1078).

The module is a security primitive: a bug here means the Kafka
consumers will either accept forged events (bypass → cross-tenant
data injection) or reject legitimate ones (outage). These tests
exercise both directions and the full matrix of failure modes the
consumer must treat as unauthorized.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from shared.kafka_auth import (
    BODY_FIELD_PRODUCER_SERVICE,
    BODY_FIELD_SIGNED_AT,
    CURRENT_SIG_VERSION,
    ENV_SIGNING_KEY,
    ENV_STRICT,
    HEADER_PRODUCER_SERVICE,
    HEADER_SIGNATURE,
    HEADER_SIG_VERSION,
    KafkaAuthError,
    get_allowed_producers,
    sign_event,
    verify_event,
)


TEST_KEY = b"test-signing-key-32-bytes-long--"
OTHER_KEY = b"other-signing-key-also-32-bytes-"


# ---------------------------------------------------------------------------
# Happy path: sign + verify round trip
# ---------------------------------------------------------------------------


def test_sign_then_verify_round_trip() -> None:
    payload = {
        "document_id": "doc-123",
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "text_clean": "Lorem ipsum",
    }
    signed_body, headers = sign_event(
        payload,
        producer_service="ingestion-service",
        signing_key=TEST_KEY,
    )

    assert signed_body[BODY_FIELD_PRODUCER_SERVICE] == "ingestion-service"
    assert isinstance(signed_body[BODY_FIELD_SIGNED_AT], str)
    # Caller's dict must not be mutated.
    assert BODY_FIELD_PRODUCER_SERVICE not in payload

    header_names = {name for name, _ in headers}
    assert HEADER_SIGNATURE in header_names
    assert HEADER_PRODUCER_SERVICE in header_names
    assert HEADER_SIG_VERSION in header_names

    evt, producer = verify_event(
        signed_body,
        headers,
        topic="ingest.normalized",
        signing_key=TEST_KEY,
    )
    assert producer == "ingestion-service"
    assert evt["document_id"] == "doc-123"
    assert evt["tenant_id"] == "00000000-0000-0000-0000-000000000001"


def test_verify_accepts_raw_json_bytes() -> None:
    """Consumers that haven't deserialized yet pass bytes to verify_event."""
    import json as _json

    payload = {"tenant_id": "t1", "doc_id": "d1"}
    signed_body, headers = sign_event(
        payload, producer_service="ingestion-service", signing_key=TEST_KEY
    )
    raw_bytes = _json.dumps(signed_body).encode("utf-8")

    evt, producer = verify_event(
        raw_bytes,
        headers,
        topic="ingest.normalized",
        signing_key=TEST_KEY,
    )
    assert producer == "ingestion-service"
    assert evt["tenant_id"] == "t1"


def test_sign_preserves_existing_correlation_headers() -> None:
    existing = [
        ("correlation-id", b"req-42"),
        ("x-request-id", b"trace-1"),
    ]
    _, headers = sign_event(
        {"tenant_id": "t1"},
        producer_service="ingestion-service",
        signing_key=TEST_KEY,
        existing_headers=existing,
    )
    names = [name for name, _ in headers]
    assert "correlation-id" in names
    assert "x-request-id" in names
    assert HEADER_SIGNATURE in names


# ---------------------------------------------------------------------------
# Tamper detection — the core property this module exists to provide.
# ---------------------------------------------------------------------------


def test_verify_rejects_body_tamper() -> None:
    """Flipping a single field in the body after signing must fail verification.

    This is the cross-tenant injection scenario: attacker captures a
    valid message, swaps ``tenant_id`` to a target tenant's id, republishes.
    """
    signed_body, headers = sign_event(
        {"tenant_id": "tenant-A", "doc_id": "d1"},
        producer_service="ingestion-service",
        signing_key=TEST_KEY,
    )
    tampered = dict(signed_body)
    tampered["tenant_id"] = "tenant-B"

    with pytest.raises(KafkaAuthError) as excinfo:
        verify_event(
            tampered,
            headers,
            topic="ingest.normalized",
            signing_key=TEST_KEY,
        )
    assert excinfo.value.reason == "signature_mismatch"


def test_verify_rejects_header_tamper() -> None:
    """Flipping the signature header value alone must fail verification."""
    signed_body, headers = sign_event(
        {"tenant_id": "t1"},
        producer_service="ingestion-service",
        signing_key=TEST_KEY,
    )
    tampered_headers = [
        (name, b"deadbeef" * 8 if name == HEADER_SIGNATURE else value)
        for name, value in headers
    ]
    with pytest.raises(KafkaAuthError) as excinfo:
        verify_event(
            signed_body,
            tampered_headers,
            topic="ingest.normalized",
            signing_key=TEST_KEY,
        )
    assert excinfo.value.reason == "signature_mismatch"


def test_verify_rejects_producer_service_body_swap() -> None:
    """Attacker cannot rewrite the in-body producer claim to impersonate.

    The body field is what gets signed, so rewriting it breaks the HMAC.
    Verify that the failure surfaces as signature_mismatch (not as a
    silent accept).
    """
    signed_body, headers = sign_event(
        {"tenant_id": "t1"},
        producer_service="ingestion-service",
        signing_key=TEST_KEY,
    )
    tampered = dict(signed_body)
    tampered[BODY_FIELD_PRODUCER_SERVICE] = "scheduler-service"

    with pytest.raises(KafkaAuthError):
        verify_event(
            tampered,
            headers,
            topic="ingest.normalized",
            signing_key=TEST_KEY,
        )


def test_verify_rejects_producer_service_header_body_mismatch() -> None:
    """Header-only rewrite (without re-signing) is caught before HMAC check."""
    signed_body, headers = sign_event(
        {"tenant_id": "t1"},
        producer_service="ingestion-service",
        signing_key=TEST_KEY,
    )
    # Swap the header producer claim but leave body + sig intact.
    tampered_headers = [
        (name, b"scheduler-service" if name == HEADER_PRODUCER_SERVICE else value)
        for name, value in headers
    ]
    with pytest.raises(KafkaAuthError) as excinfo:
        verify_event(
            signed_body,
            tampered_headers,
            topic="ingest.normalized",
            signing_key=TEST_KEY,
        )
    assert excinfo.value.reason == "producer_service_header_body_mismatch"


def test_verify_rejects_wrong_key() -> None:
    """A message signed with key A must not verify with key B."""
    signed_body, headers = sign_event(
        {"tenant_id": "t1"},
        producer_service="ingestion-service",
        signing_key=TEST_KEY,
    )
    with pytest.raises(KafkaAuthError) as excinfo:
        verify_event(
            signed_body,
            headers,
            topic="ingest.normalized",
            signing_key=OTHER_KEY,
        )
    assert excinfo.value.reason == "signature_mismatch"


# ---------------------------------------------------------------------------
# Missing / malformed header cases — every one must raise.
# ---------------------------------------------------------------------------


def test_verify_rejects_missing_signature_header() -> None:
    signed_body, headers = sign_event(
        {"tenant_id": "t1"},
        producer_service="ingestion-service",
        signing_key=TEST_KEY,
    )
    stripped = [(n, v) for n, v in headers if n != HEADER_SIGNATURE]
    with pytest.raises(KafkaAuthError) as excinfo:
        verify_event(signed_body, stripped, topic="t", signing_key=TEST_KEY)
    assert excinfo.value.reason == "missing_signature_header"


def test_verify_rejects_missing_producer_header() -> None:
    signed_body, headers = sign_event(
        {"tenant_id": "t1"},
        producer_service="ingestion-service",
        signing_key=TEST_KEY,
    )
    stripped = [(n, v) for n, v in headers if n != HEADER_PRODUCER_SERVICE]
    with pytest.raises(KafkaAuthError) as excinfo:
        verify_event(signed_body, stripped, topic="t", signing_key=TEST_KEY)
    assert excinfo.value.reason == "missing_producer_service_header"


def test_verify_rejects_missing_version_header() -> None:
    signed_body, headers = sign_event(
        {"tenant_id": "t1"},
        producer_service="ingestion-service",
        signing_key=TEST_KEY,
    )
    stripped = [(n, v) for n, v in headers if n != HEADER_SIG_VERSION]
    with pytest.raises(KafkaAuthError) as excinfo:
        verify_event(signed_body, stripped, topic="t", signing_key=TEST_KEY)
    assert excinfo.value.reason == "missing_sig_version_header"


def test_verify_rejects_unsupported_version() -> None:
    signed_body, headers = sign_event(
        {"tenant_id": "t1"},
        producer_service="ingestion-service",
        signing_key=TEST_KEY,
    )
    munged = [
        (n, b"v99" if n == HEADER_SIG_VERSION else v)
        for n, v in headers
    ]
    with pytest.raises(KafkaAuthError) as excinfo:
        verify_event(signed_body, munged, topic="t", signing_key=TEST_KEY)
    assert excinfo.value.reason == "unsupported_sig_version"


def test_verify_rejects_no_headers_at_all() -> None:
    """Consumer reads a message with no auth headers → reject."""
    with pytest.raises(KafkaAuthError):
        verify_event(
            {"tenant_id": "t1", BODY_FIELD_PRODUCER_SERVICE: "x"},
            headers=None,
            topic="t",
            signing_key=TEST_KEY,
        )


# ---------------------------------------------------------------------------
# Producer allowlist
# ---------------------------------------------------------------------------


def test_verify_rejects_producer_not_in_allowlist() -> None:
    """Scheduler cannot publish to ingest.normalized (wrong producer for topic).

    This is the layer-3 defense in the issue: even if an attacker has
    the signing key, the topic-level producer allowlist refuses
    messages from unauthorized services.
    """
    signed_body, headers = sign_event(
        {"tenant_id": "t1"},
        producer_service="scheduler-service",
        signing_key=TEST_KEY,
    )
    with pytest.raises(KafkaAuthError) as excinfo:
        verify_event(
            signed_body,
            headers,
            topic="ingest.normalized",
            signing_key=TEST_KEY,
            allowed_producers={"ingestion-service"},
        )
    assert excinfo.value.reason == "producer_not_allowed_for_topic"
    assert excinfo.value.fields["producer_service"] == "scheduler-service"


def test_verify_allows_producer_in_allowlist() -> None:
    signed_body, headers = sign_event(
        {"tenant_id": "t1"},
        producer_service="ingestion-service",
        signing_key=TEST_KEY,
    )
    evt, producer = verify_event(
        signed_body,
        headers,
        topic="ingest.normalized",
        signing_key=TEST_KEY,
        allowed_producers={"ingestion-service", "scheduler-service"},
    )
    assert producer == "ingestion-service"


def test_verify_empty_allowlist_rejects_all() -> None:
    """Empty set is an incident-lockout signal: reject every producer."""
    signed_body, headers = sign_event(
        {"tenant_id": "t1"},
        producer_service="ingestion-service",
        signing_key=TEST_KEY,
    )
    with pytest.raises(KafkaAuthError):
        verify_event(
            signed_body,
            headers,
            topic="ingest.normalized",
            signing_key=TEST_KEY,
            allowed_producers=set(),
        )


# ---------------------------------------------------------------------------
# Rollout / strict mode
# ---------------------------------------------------------------------------


def test_verify_strict_mode_requires_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Consumer in strict mode with no key raises, not warns.

    Service conftests may preset ``KAFKA_EVENT_SIGNING_KEY`` for their
    own test fixtures; this test is specifically about the
    unconfigured path so we clear it.
    """
    monkeypatch.delenv(ENV_SIGNING_KEY, raising=False)
    with pytest.raises(KafkaAuthError) as excinfo:
        verify_event(
            {"tenant_id": "t1"},
            headers=[],
            topic="t",
            signing_key=None,
            strict=True,
        )
    assert excinfo.value.reason == "signing_key_not_configured"


def test_verify_non_strict_mode_bypasses_when_no_key(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Rollout path: no key configured → WARN and pass through."""
    monkeypatch.delenv(ENV_SIGNING_KEY, raising=False)
    evt, producer = verify_event(
        {"tenant_id": "t1", "doc_id": "d1"},
        headers=[],
        topic="t",
        signing_key=None,
        strict=False,
    )
    assert evt["tenant_id"] == "t1"
    # We tolerate either "unsigned" literal or whatever was in the body.
    assert producer == "unsigned"


def test_strict_default_is_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """Absent config → strict. This is the safe default."""
    monkeypatch.delenv(ENV_SIGNING_KEY, raising=False)
    monkeypatch.delenv(ENV_STRICT, raising=False)
    with pytest.raises(KafkaAuthError) as excinfo:
        verify_event(
            {"tenant_id": "t1"},
            headers=[],
            topic="t",
            signing_key=None,
            # strict not specified — use env / default
        )
    assert excinfo.value.reason == "signing_key_not_configured"


def test_strict_env_override_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_SIGNING_KEY, raising=False)
    monkeypatch.setenv(ENV_STRICT, "false")
    evt, producer = verify_event(
        {"tenant_id": "t1"},
        headers=[],
        topic="t",
        signing_key=None,
    )
    assert evt["tenant_id"] == "t1"
    assert producer == "unsigned"


def test_signing_key_env_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Producer / consumer read the signing key from the env by default."""
    monkeypatch.setenv(ENV_SIGNING_KEY, "env-key-from-deploy")
    signed_body, headers = sign_event(
        {"tenant_id": "t1"},
        producer_service="ingestion-service",
    )
    # Round-trips with the same env key.
    evt, _ = verify_event(
        signed_body, headers, topic="t"
    )
    assert evt["tenant_id"] == "t1"


def test_sign_without_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """You cannot sign without a key. (Consumers can bypass; producers can't.)"""
    monkeypatch.delenv(ENV_SIGNING_KEY, raising=False)
    with pytest.raises(KafkaAuthError) as excinfo:
        sign_event(
            {"tenant_id": "t1"},
            producer_service="ingestion-service",
            signing_key=None,
        )
    assert excinfo.value.reason == "signing_key_not_configured"


# ---------------------------------------------------------------------------
# Payload shape edge cases
# ---------------------------------------------------------------------------


def test_verify_rejects_non_dict_body() -> None:
    """Top-level arrays / primitives are never valid RegEngine events."""
    with pytest.raises(KafkaAuthError) as excinfo:
        verify_event(b'"just a string"', headers=[], topic="t", signing_key=TEST_KEY)
    # Could raise at json-parse (if quotes survive to str) or body_not_object.
    assert excinfo.value.reason in {"body_not_object", "missing_sig_version_header"}


def test_verify_rejects_non_json_bytes() -> None:
    with pytest.raises(KafkaAuthError) as excinfo:
        verify_event(b"not-json-at-all", headers=[], topic="t", signing_key=TEST_KEY)
    assert excinfo.value.reason == "body_not_json"


def test_sign_rejects_empty_producer_name() -> None:
    with pytest.raises(KafkaAuthError) as excinfo:
        sign_event({"tenant_id": "t1"}, producer_service="", signing_key=TEST_KEY)
    assert excinfo.value.reason == "producer_service_empty"


def test_sign_rejects_non_mapping_payload() -> None:
    with pytest.raises(KafkaAuthError):
        sign_event(
            ["not", "a", "dict"],  # type: ignore[arg-type]
            producer_service="ingestion-service",
            signing_key=TEST_KEY,
        )


# ---------------------------------------------------------------------------
# Canonicalization determinism — different dict ordering, same signature.
# ---------------------------------------------------------------------------


def test_signature_is_key_order_independent() -> None:
    """Same content, different key order → same signature.

    Dict iteration order is CPython implementation-defined; the
    signature must not depend on it.
    """
    payload_a = {"a": 1, "b": 2, "c": 3}
    payload_b = {"c": 3, "a": 1, "b": 2}

    _, headers_a = sign_event(
        payload_a,
        producer_service="ingestion-service",
        signing_key=TEST_KEY,
        now_fn=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    _, headers_b = sign_event(
        payload_b,
        producer_service="ingestion-service",
        signing_key=TEST_KEY,
        now_fn=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    sig_a = dict(headers_a)[HEADER_SIGNATURE]
    sig_b = dict(headers_b)[HEADER_SIGNATURE]
    assert sig_a == sig_b


def test_signature_covers_nested_fields() -> None:
    """Nested dict tamper must be detected."""
    payload = {
        "tenant_id": "t1",
        "kdes": {"product_description": "Spinach"},
    }
    signed_body, headers = sign_event(
        payload,
        producer_service="ingestion-service",
        signing_key=TEST_KEY,
    )
    tampered = {**signed_body, "kdes": {"product_description": "Lettuce"}}
    with pytest.raises(KafkaAuthError) as excinfo:
        verify_event(tampered, headers, topic="t", signing_key=TEST_KEY)
    assert excinfo.value.reason == "signature_mismatch"


# ---------------------------------------------------------------------------
# Allowlist helper
# ---------------------------------------------------------------------------


def test_get_allowed_producers_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KAFKA_ALLOWED_PRODUCERS_INGEST_NORMALIZED", raising=False)
    assert get_allowed_producers("ingest.normalized") is None


def test_get_allowed_producers_parses_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "KAFKA_ALLOWED_PRODUCERS_INGEST_NORMALIZED",
        "ingestion-service,scheduler-service",
    )
    assert get_allowed_producers("ingest.normalized") == {
        "ingestion-service",
        "scheduler-service",
    }


def test_get_allowed_producers_handles_dashes_in_topic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "KAFKA_ALLOWED_PRODUCERS_NLP_NEEDS_REVIEW",
        "nlp-service",
    )
    assert get_allowed_producers("nlp.needs-review") == {"nlp-service"}


def test_get_allowed_producers_empty_means_reject_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty string is deliberate: deploy-time lockout of a topic."""
    monkeypatch.setenv("KAFKA_ALLOWED_PRODUCERS_GRAPH_UPDATE", "")
    result = get_allowed_producers("graph.update")
    assert result == set()
