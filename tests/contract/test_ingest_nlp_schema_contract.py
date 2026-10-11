"""Offline contract: ingestion producer output vs the NLP inbound schema.

The ingestion service emits ``NormalizedEvent`` messages to the
normalized Kafka topic; the NLP consumer validates every inbound message
against ``data-schemas/events/ingest.normalized.schema.json``.

Unlike ``test_service_contracts.py`` (which needs live services and
runs in no blocking job), every test here runs offline with mocked
storage, parser, settings, and Kafka transport, so this file belongs in
the blocking ``repo-root-suite`` offline list in
``.github/workflows/backend-ci.yml``. A producer or schema break fails
the merge gate here instead of in production.
"""

import sys
from pathlib import Path

service_dir = Path(__file__).resolve().parents[2] / "services" / "ingestion"
sys.path.insert(0, str(service_dir))

import pytest  # noqa: E402


def _load_inbound_schema():
    """Load the schema the NLP consumer enforces on ingestion messages."""
    import json

    from jsonschema import Draft7Validator

    schema_path = Path(__file__).resolve().parents[2] / "data-schemas" / "events" / "ingest.normalized.schema.json"
    assert schema_path.exists(), f"inbound schema missing: {schema_path}"
    return Draft7Validator(json.loads(schema_path.read_text()))


def _real_producer_message(**overrides):
    """Build a message exactly as the ingestion producer emits it."""
    import uuid
    from datetime import datetime, timezone

    from app.models import NormalizedEvent

    doc_id = str(uuid.uuid4())
    event = NormalizedEvent(
        event_id=str(uuid.uuid4()),
        document_id=doc_id,
        document_hash="0" * 64,
        tenant_id=str(uuid.uuid4()),
        source_system="federal_register",
        source_url="https://www.federalregister.gov/documents/2026/01/01/test",
        raw_s3_path="s3://regengine-test/raw/doc-1.pdf",
        normalized_s3_path="s3://regengine-test/normalized/doc-1.txt",
        timestamp=datetime.now(timezone.utc),
        content_sha256="1" * 64,
        is_duplicate=False,
    )
    message = event.model_dump(mode="json")
    message.update(overrides)
    return message


class TestIngestionToNLPContract:
    """Contract between Ingestion and NLP services."""

    def test_ingestion_produces_expected_message_format(self):
        """A real producer message must validate against the NLP inbound schema."""
        validator = _load_inbound_schema()
        message = _real_producer_message()

        errors = list(validator.iter_errors(message))
        assert errors == [], f"producer message rejected by the NLP inbound schema: {[e.message for e in errors]}"

    def test_message_without_content_pointer_is_rejected(self):
        """A message with no normalized pointer and no inline text must not validate."""
        validator = _load_inbound_schema()
        message = _real_producer_message()
        del message["normalized_s3_path"]

        errors = list(validator.iter_errors(message))
        assert errors != [], (
            "schema accepted a message with no content pointer. The NLP consumer would have nothing to extract"
        )

    def test_message_with_malformed_tenant_id_is_rejected(self):
        """Tenant IDs on the wire must be UUIDs when present."""
        validator = _load_inbound_schema()
        message = _real_producer_message(tenant_id="not-a-uuid")

        errors = list(validator.iter_errors(message))
        assert errors != [], "schema accepted a malformed tenant_id"


class TestProducerEmissionContract:
    """The real producer function emits schema-valid Kafka payloads.

    The tests above construct the model inside the test. These tests call
    the actual emission path (``_process_and_emit`` with mocked storage,
    parser, settings, and transport) and validate what it really sends, so
    reverting the producer to a hand-built dict fails here.
    """

    @staticmethod
    def _emit(monkeypatch):
        import uuid
        from types import SimpleNamespace

        from app import routes_ingest

        sent = []
        from datetime import datetime, timezone

        monkeypatch.setattr(routes_ingest.PARSER_REGISTRY, "parse", lambda *a, **k: ("probe text", "probe-parser"))
        monkeypatch.setattr(
            routes_ingest,
            "normalize_document",
            lambda *a, **k: (
                {
                    "document_id": "doc-probe-1",
                    "source_url": "https://www.federalregister.gov/documents/2026/01/01/test",
                    "source_system": "federal_register",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "text": "probe text",
                    "title": "Probe doc",
                    "content_sha256": "0" * 64,
                },
                "doc-probe-1",
                None,
            ),
        )
        monkeypatch.setattr(
            routes_ingest,
            "get_settings",
            lambda: SimpleNamespace(
                raw_bucket="raw", processed_bucket="processed", kafka_topic_normalized="normalized"
            ),
        )
        monkeypatch.setattr(routes_ingest, "put_bytes", lambda *a, **k: "s3://raw/raw/doc-probe-1.bin")
        monkeypatch.setattr(routes_ingest, "put_json", lambda *a, **k: "s3://processed/normalized/doc-probe-1.json")
        monkeypatch.setattr(routes_ingest, "send", lambda topic, payload, key=None: sent.append((topic, payload, key)))
        event = routes_ingest._process_and_emit(
            b"probe document bytes",
            "https://www.federalregister.gov/documents/2026/01/01/test",
            "federal_register",
            str(uuid.uuid4()),
            "text/plain",
        )
        return event, sent

    def test_producer_function_returns_model_instance(self, monkeypatch):
        """The emission path returns a NormalizedEvent, not a plain dict."""
        from app.models import NormalizedEvent

        event, _ = self._emit(monkeypatch)
        assert isinstance(event, NormalizedEvent), (
            f"producer returned {type(event).__name__}; the Kafka payload builder must stay a model"
        )

    def test_producer_emission_validates_against_nlp_schema(self, monkeypatch):
        """What the producer really emits must validate against the NLP schema."""
        validator = _load_inbound_schema()
        event, sent = self._emit(monkeypatch)

        payload = event.model_dump(mode="json")
        errors = list(validator.iter_errors(payload))
        assert errors == [], f"real producer output rejected by the NLP inbound schema: {[e.message for e in errors]}"

        assert sent, "producer must publish exactly one Kafka message"
        assert sent[0][1] == payload, "the published Kafka payload must be the emitted event"
        wire_errors = list(validator.iter_errors(sent[0][1]))
        assert wire_errors == [], "published Kafka payload rejected by the NLP inbound schema"
