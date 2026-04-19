"""Regression tests for graph consumer Kafka-message authentication (#1078).

The graph consumer is the principal victim of the forged-tenant_id
attack described in #1078: its ``tenant_id`` determines which Neo4j
tenant DB an upsert writes to. Before the fix, any producer with
publish access to ``graph.update`` could pick an arbitrary
``tenant_id`` and have the write applied to a foreign tenant's graph.

These tests exercise the authentication edge directly by constructing
a signed message and then tampering with it — independent of the
production consumer loop's networking, poll timeout, and Neo4j
dependencies, which are a separate test concern.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


from shared.kafka_auth import (
    BODY_FIELD_PRODUCER_SERVICE,
    HEADER_PRODUCER_SERVICE,
    HEADER_SIGNATURE,
    KafkaAuthError,
    get_allowed_producers,
    sign_event,
    verify_event,
)


class TestGraphConsumerAuthImport:
    """Pin the consumer's auth imports so refactors can't silently drop them."""

    def test_consumer_imports_verify_event(self) -> None:
        """Graph consumer must import verify_event — if this is missing
        the module would still load but the auth step would be gone."""
        from services.graph.app import consumer

        assert hasattr(consumer, "verify_event")
        assert hasattr(consumer, "KafkaAuthError")
        assert hasattr(consumer, "get_allowed_producers")


class TestGraphConsumerVerificationSemantics:
    """The behavior the graph consumer depends on — verified via
    direct calls to verify_event so the test is hermetic."""

    def test_signed_nlp_message_verifies_for_graph_topic(self) -> None:
        """An NLP-signed event is accepted by the graph topic's allowlist."""
        payload = {
            "tenant_id": "00000000-0000-0000-0000-000000000001",
            "document_id": "doc-1",
            "event_type": "create_provision",
        }
        signed_body, signed_headers = sign_event(
            payload,
            producer_service="nlp-service",
        )
        evt, producer_service = verify_event(
            signed_body,
            signed_headers,
            topic="graph.update",
            allowed_producers={"nlp-service"},
        )
        assert producer_service == "nlp-service"
        assert evt["tenant_id"] == "00000000-0000-0000-0000-000000000001"

    def test_forged_tenant_id_is_rejected(self) -> None:
        """The core #1078 regression: an attacker who swaps tenant_id
        after a legitimate sign cannot get past the verifier."""
        legitimate = {"tenant_id": "tenant-A", "document_id": "doc-1"}
        signed_body, signed_headers = sign_event(
            legitimate, producer_service="nlp-service"
        )

        # Attacker rewrites tenant_id to a target tenant.
        forged = dict(signed_body)
        forged["tenant_id"] = "tenant-B"

        with pytest.raises(KafkaAuthError) as excinfo:
            verify_event(
                forged,
                signed_headers,
                topic="graph.update",
                allowed_producers={"nlp-service"},
            )
        assert excinfo.value.reason == "signature_mismatch"

    def test_unsigned_message_is_rejected(self) -> None:
        """Consumer default is strict — no signature header → reject."""
        payload = {"tenant_id": "t1", "document_id": "d1"}
        with pytest.raises(KafkaAuthError):
            verify_event(
                payload,
                headers=[],  # No signature headers at all.
                topic="graph.update",
                allowed_producers={"nlp-service"},
            )

    def test_unauthorized_producer_rejected_even_with_valid_signature(
        self,
    ) -> None:
        """A valid signature from a service not allowed on the topic
        must still be rejected. This is layer-3 defense: if an attacker
        steals the scheduler's signing key but graph.update only allows
        nlp-service, the injection still fails."""
        signed_body, signed_headers = sign_event(
            {"tenant_id": "t1"},
            producer_service="scheduler-service",
        )
        with pytest.raises(KafkaAuthError) as excinfo:
            verify_event(
                signed_body,
                signed_headers,
                topic="graph.update",
                allowed_producers={"nlp-service"},
            )
        assert excinfo.value.reason == "producer_not_allowed_for_topic"

    def test_allowlist_from_env_round_trip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The per-topic allowlist resolver is exactly what the consumer
        passes to verify_event; prove the wiring."""
        monkeypatch.setenv(
            "KAFKA_ALLOWED_PRODUCERS_GRAPH_UPDATE",
            "nlp-service,scheduler-service",
        )
        signed_body, signed_headers = sign_event(
            {"tenant_id": "t1"},
            producer_service="scheduler-service",
        )
        evt, producer_service = verify_event(
            signed_body,
            signed_headers,
            topic="graph.update",
            allowed_producers=get_allowed_producers("graph.update"),
        )
        assert producer_service == "scheduler-service"
        assert evt["tenant_id"] == "t1"

    def test_signed_body_retains_producer_claim(self) -> None:
        """The signed body must carry _producer_service so an auditor
        can reconstruct who emitted the event, not just who the
        Kafka-header claims it came from."""
        signed_body, _ = sign_event(
            {"tenant_id": "t1"}, producer_service="nlp-service"
        )
        assert signed_body[BODY_FIELD_PRODUCER_SERVICE] == "nlp-service"

    def test_header_tamper_without_resign_rejected(self) -> None:
        """An attacker who swaps the x-producer-service header alone
        (without re-signing) should be caught by the header/body
        consistency check before the HMAC compare."""
        signed_body, signed_headers = sign_event(
            {"tenant_id": "t1"}, producer_service="nlp-service"
        )
        tampered_headers = [
            (name, b"scheduler-service" if name == HEADER_PRODUCER_SERVICE else value)
            for name, value in signed_headers
        ]
        with pytest.raises(KafkaAuthError) as excinfo:
            verify_event(
                signed_body,
                tampered_headers,
                topic="graph.update",
            )
        assert excinfo.value.reason == "producer_service_header_body_mismatch"

    def test_signature_header_stripped_rejected(self) -> None:
        """Drop the x-evt-sig header → reject with precise diagnostic."""
        signed_body, signed_headers = sign_event(
            {"tenant_id": "t1"}, producer_service="nlp-service"
        )
        stripped = [(n, v) for (n, v) in signed_headers if n != HEADER_SIGNATURE]
        with pytest.raises(KafkaAuthError) as excinfo:
            verify_event(signed_body, stripped, topic="graph.update")
        assert excinfo.value.reason == "missing_signature_header"
