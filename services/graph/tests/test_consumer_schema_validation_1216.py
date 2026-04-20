"""Tests for inbound schema validation on the ``graph.update`` topic (#1216).

Previously the graph consumer accepted any dict-shaped payload on the
legacy path and blindly called ``evt.get(...)``. A non-dict payload would
crash the worker and a junk dict would silently upsert garbage into
Neo4j. These tests exercise the validation branch added in #1216:

1. Non-dict payload  → route to DLQ with ``reason=invalid_schema``
2. Dict missing required fields → route to DLQ with ``reason=invalid_schema``
3. Dict matching the legacy schema → parses into ``LegacyGraphEvent``
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from services.shared.schemas import LegacyGraphEvent


class TestLegacyGraphEventModel:
    """The new Pydantic model itself enforces the fields the consumer reads."""

    def test_accepts_minimal_valid_payload(self):
        evt = LegacyGraphEvent.model_validate(
            {"document_id": "doc-1", "entities": []}
        )
        assert evt.document_id == "doc-1"
        assert evt.entities == []
        assert evt.source_url is None
        assert evt.tenant_id is None

    def test_accepts_full_legacy_payload(self):
        evt = LegacyGraphEvent.model_validate(
            {
                "document_id": "doc-2",
                "entities": [{"type": "OBLIGATION", "attrs": {"name": "foo"}}],
                "source_url": "https://example.com/doc.pdf",
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
            }
        )
        assert evt.document_id == "doc-2"
        assert len(evt.entities) == 1
        assert evt.source_url == "https://example.com/doc.pdf"

    def test_rejects_missing_document_id(self):
        with pytest.raises(ValidationError):
            LegacyGraphEvent.model_validate({"entities": []})

    def test_rejects_empty_document_id(self):
        with pytest.raises(ValidationError):
            LegacyGraphEvent.model_validate({"document_id": "", "entities": []})

    def test_rejects_non_list_entities(self):
        with pytest.raises(ValidationError):
            LegacyGraphEvent.model_validate(
                {"document_id": "doc-3", "entities": "not-a-list"}
            )

    def test_rejects_non_dict_entity_items(self):
        with pytest.raises(ValidationError):
            LegacyGraphEvent.model_validate(
                {"document_id": "doc-4", "entities": ["string-instead-of-dict"]}
            )

    def test_ignores_extra_fields(self):
        """Forward-compat: additional fields should not cause rejection."""
        evt = LegacyGraphEvent.model_validate(
            {
                "document_id": "doc-5",
                "entities": [],
                "experimental_field": "future-value",
            }
        )
        assert evt.document_id == "doc-5"


class TestConsumerInvalidPayloadRouting:
    """The consumer must DLQ malformed messages and not crash.

    These tests drive a single iteration of the consumer loop with a
    mocked ``confluent_kafka`` consumer. We bypass the schema registry /
    Avro deserializer wiring and assert the DLQ path fires with
    ``reason=invalid_schema``.
    """

    def _make_record(self, value, topic: str = "graph.update"):
        record = MagicMock()
        record.value.return_value = value
        record.error.return_value = None
        record.headers.return_value = []
        record.topic.return_value = topic
        return record

    def _drive_once_with_payload(self, payload):
        """Run the consumer loop for a single message, then stop.

        Returns the mocked ``_send_to_dlq`` call list and the mocked
        Kafka consumer so the caller can assert on commit behaviour.
        """
        import asyncio

        from services.graph.app import consumer as consumer_mod

        record = self._make_record(payload)
        fake_consumer = MagicMock()
        # First poll returns the message; the shutdown flag will stop
        # the loop before a second poll happens.
        fake_consumer.poll.return_value = record

        # verify_event passes the payload through unchanged and returns
        # a stub producer identity — isolates auth from schema concerns.
        def _fake_verify(evt, headers, topic, allowed_producers):
            return evt, "scheduler"

        async def _drive():
            # Trigger shutdown after a short delay so run_consumer exits.
            async def _stop():
                await asyncio.sleep(0.1)
                consumer_mod._shutdown_event.set()

            stop_task = asyncio.create_task(_stop())
            try:
                await consumer_mod.run_consumer()
            finally:
                await stop_task

        consumer_mod._shutdown_event.clear()
        with patch.object(
            consumer_mod, "DeserializingConsumer", return_value=fake_consumer
        ), patch.object(
            consumer_mod, "SchemaRegistryClient", return_value=MagicMock()
        ), patch.object(
            consumer_mod, "AvroDeserializer", return_value=lambda v, c: v
        ), patch.object(
            consumer_mod, "load_schema", return_value="{}"
        ), patch.object(
            consumer_mod, "_init_dlq_producer", return_value=MagicMock()
        ), patch.object(
            consumer_mod, "_send_to_dlq"
        ) as mock_send_dlq, patch.object(
            consumer_mod, "verify_event", side_effect=_fake_verify
        ):
            try:
                asyncio.run(_drive())
            finally:
                consumer_mod._shutdown_event.clear()
            return mock_send_dlq, fake_consumer

    def test_non_dict_payload_routes_to_dlq_and_does_not_crash(self):
        """Bytes-shaped payload must not reach ``evt.get(...)``."""
        mock_send_dlq, fake_consumer = self._drive_once_with_payload(b"not a dict")

        reasons = [
            call.kwargs.get("reason") for call in mock_send_dlq.call_args_list
        ]
        assert "invalid_schema" in reasons, (
            f"expected invalid_schema DLQ call, got {reasons}"
        )
        fake_consumer.commit.assert_called()

    def test_dict_payload_failing_both_schemas_routes_to_dlq(self):
        """Dict missing ``document_id`` must be DLQ'd, not silently dropped."""
        mock_send_dlq, fake_consumer = self._drive_once_with_payload(
            {"entities": [], "source_url": "http://x"}
        )

        reasons = [
            call.kwargs.get("reason") for call in mock_send_dlq.call_args_list
        ]
        assert "invalid_schema" in reasons, (
            f"expected invalid_schema DLQ call, got {reasons}"
        )
        fake_consumer.commit.assert_called()
